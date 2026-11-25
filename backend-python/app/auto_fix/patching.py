from __future__ import annotations

import os
import re
import subprocess
from collections.abc import Collection, Iterable
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from typing import Any

from sqlalchemy.orm import Session

from app.code_quality.models import CodeQualityModelProvider
from app.code_quality.providers import run_fix_provider
from app.core.errors import AppError


MAX_PATCH_BYTES = 128 * 1024
MAX_SOURCE_BYTES = 256 * 1024
MAX_REVIEW_DIFF_BYTES = 256 * 1024
MAX_REVIEW_FILES = 64
MAX_PATCHES_PER_ROUND = 16
_GIT_TIMEOUT_SECONDS = 30
_SHA = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")
_REGULAR_MODES = {b"100644", b"100755"}
_SOURCE_EXTENSIONS = {
    ".c", ".cc", ".cpp", ".cs", ".css", ".dart", ".go", ".h", ".hpp", ".java",
    ".js", ".jsx", ".kt", ".mjs", ".php", ".py", ".rb", ".rs", ".scss",
    ".sql", ".swift", ".ts", ".tsx", ".vue",
}
_RESTRICTED_DIRECTORIES = {
    "build", "ci", "deploy", "deployment", "docker", "helm", "infra", "infrastructure",
    "k8s", "kubernetes", "migration", "migrations", "scripts", "terraform",
}
_DIFF_OPTIONS = (
    "--no-ext-diff", "--no-textconv", "--no-renames", "--no-color", "--text",
    "--src-prefix=a/", "--dst-prefix=b/", "--unified=3", "--ignore-submodules=none",
)
_RAW_DIFF_OPTIONS = (
    "--raw", "-z", "--no-abbrev", "--no-renames", "--no-ext-diff", "--no-textconv",
    "--ignore-submodules=none",
)


class PatchError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _git(
    repo_path: str | Path,
    *args: str,
    index_path: Path | None = None,
    data: bytes | None = None,
    error_code: str = "REPAIR_REPOSITORY_UNAVAILABLE",
) -> bytes:
    env = {name: value for name, value in os.environ.items() if not name.upper().startswith("GIT_")}
    env.update(
        GIT_ATTR_NOSYSTEM="1",
        GIT_CONFIG_GLOBAL=os.devnull,
        GIT_CONFIG_NOSYSTEM="1",
        GIT_NO_LAZY_FETCH="1",
        GIT_OPTIONAL_LOCKS="0",
        GIT_TERMINAL_PROMPT="0",
        GIT_AUTHOR_NAME="AI Code Review Platform",
        GIT_AUTHOR_EMAIL="auto-fix@localhost",
        GIT_COMMITTER_NAME="AI Code Review Platform",
        GIT_COMMITTER_EMAIL="auto-fix@localhost",
    )
    if index_path is not None:
        env["GIT_INDEX_FILE"] = str(index_path)
    try:
        completed = subprocess.run(
            [
                "git", "--no-replace-objects", "--literal-pathspecs", "-C", str(repo_path),
                "-c", f"core.hooksPath={os.devnull}", "-c", "core.fsmonitor=false",
                "-c", "gc.auto=0", "-c", "maintenance.auto=false",
                "-c", "apply.ignoreWhitespace=no", *args,
            ],
            input=data,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            timeout=_GIT_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exception:
        raise PatchError(error_code, f"Git {args[0]} could not complete") from exception
    if completed.returncode != 0:
        raise PatchError(error_code, f"Git {args[0]} rejected the operation")
    return completed.stdout


def _commit(repo_path: str | Path, sha: str) -> str:
    if not isinstance(sha, str) or not _SHA.fullmatch(sha):
        raise PatchError("INVALID_REPAIR_REF", "A full commit SHA is required")
    actual = _git(repo_path, "rev-parse", "--verify", f"{sha}^{{commit}}", error_code="INVALID_REPAIR_REF")
    if actual.strip().decode("ascii") != sha:
        raise PatchError("INVALID_REPAIR_REF", "The supplied SHA does not identify an exact commit")
    return sha


def _text(data: bytes, max_bytes: int, error_code: str) -> str:
    if len(data) > max_bytes or b"\0" in data:
        raise PatchError(error_code, "Git material is too large or is not text")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exception:
        raise PatchError(error_code, "Git material is not UTF-8 text") from exception


def _object_text(repo_path: str | Path, object_id: str, error_code: str) -> str:
    byte_count = int(_git(repo_path, "cat-file", "-s", object_id, error_code=error_code))
    if byte_count > MAX_SOURCE_BYTES:
        raise PatchError(error_code, "Source file exceeds the automatic repair input limit")
    return _text(_git(repo_path, "cat-file", "blob", object_id, error_code=error_code), MAX_SOURCE_BYTES, error_code)


def is_repair_source_path(path: str) -> bool:
    if not isinstance(path, str) or not path or any(ord(character) < 32 for character in path):
        return False
    if any(character in path for character in '\\:<>"|?*'):
        return False
    parts = path.lower().split("/")
    if any(not part or part.startswith(".") or part.endswith((" ", ".")) for part in parts):
        return False
    if _RESTRICTED_DIRECTORIES.intersection(parts[:-1]):
        return False
    filename = parts[-1]
    stem = filename.split(".", 1)[0]
    if stem in {"jenkinsfile", "makefile", "dockerfile", "vite", "webpack", "rollup", "gulpfile", "gradle"}:
        return False
    if filename.endswith((".config.js", ".config.mjs", ".config.ts")):
        return False
    return PurePosixPath(path).suffix.lower() in _SOURCE_EXTENSIONS


def _source_file(repo_path: str | Path, sha: str, path: str) -> str:
    entry = _git(repo_path, "ls-tree", "-z", sha, "--", path)
    if not entry or entry.count(b"\0") != 1:
        raise PatchError("REPAIR_FILE_NOT_EDITABLE", "The requested file is absent from the input commit")
    metadata, _, entry_path = entry[:-1].partition(b"\t")
    mode, object_type, object_id = metadata.split()
    if mode not in _REGULAR_MODES or object_type != b"blob" or entry_path != path.encode("utf-8"):
        raise PatchError("REPAIR_FILE_NOT_EDITABLE", "Only existing regular source files are editable")
    return _object_text(repo_path, object_id.decode("ascii"), "REPAIR_FILE_NOT_EDITABLE")


def _raw_changes(payload: bytes, error_code: str) -> list[tuple[bytes, bytes, str, str, str, str]]:
    parts = payload.split(b"\0")
    if parts.pop() != b"" or len(parts) % 2:
        raise PatchError(error_code, "Git change listing is incomplete")
    changes = []
    for offset in range(0, len(parts), 2):
        metadata, path = parts[offset : offset + 2]
        old_mode, new_mode, old_id, new_id, kind = metadata.removeprefix(b":").split()
        changes.append(
            (old_mode, new_mode, old_id.decode("ascii"), new_id.decode("ascii"), kind.decode("ascii"),
             _text(path, MAX_SOURCE_BYTES, error_code))
        )
    return changes


def _patch_bytes(patch: str) -> bytes:
    if not isinstance(patch, str) or not patch.startswith("diff --git "):
        raise PatchError("PATCH_REJECTED", "Patch output is not a unified diff")
    try:
        encoded = (patch if patch.endswith("\n") else patch + "\n").encode("utf-8")
    except UnicodeEncodeError as exception:
        raise PatchError("PATCH_REJECTED", "Patch output is not UTF-8 text") from exception
    if len(encoded) > MAX_PATCH_BYTES or b"\0" in encoded:
        raise PatchError("PATCH_REJECTED", "Patch output is too large or contains binary changes")
    return encoded


def _patch_paths(repo_path: str | Path, encoded: bytes) -> set[str]:
    error_code = "PATCH_REJECTED"
    entries = _git(repo_path, "apply", "--numstat", "-z", "-", data=encoded, error_code=error_code).split(b"\0")
    if entries.pop() != b"" or not entries or len(entries) > MAX_REVIEW_FILES:
        raise PatchError(error_code, "Patch has no editable source paths or exceeds the file limit")
    paths = set()
    for entry in entries:
        parts = entry.split(b"\t", 2)
        if len(parts) != 3:
            raise PatchError(error_code, "Patch contains an unsupported file change")
        added, removed, file_path = parts
        path = _text(file_path, MAX_PATCH_BYTES, error_code)
        if not path or path in paths or not added.isdigit() or not removed.isdigit():
            raise PatchError(error_code, "Patch contains a duplicate path or unsupported file change")
        paths.add(path)
    return paths


def verified_review_diff(repo_path: str | Path, base_sha: str, head_sha: str) -> dict[str, Any]:
    base_sha = _commit(repo_path, base_sha)
    head_sha = _commit(repo_path, head_sha)
    error_code = "REVIEW_DIFF_INCOMPLETE"
    _git(repo_path, "merge-base", "--is-ancestor", base_sha, head_sha, error_code=error_code)
    changes = _raw_changes(
        _git(repo_path, "diff", *_RAW_DIFF_OPTIONS, base_sha, head_sha, "--"),
        error_code,
    )
    if len(changes) > MAX_REVIEW_FILES:
        raise PatchError(error_code, "Comparison contains too many files for a complete review")
    parts = []
    files = []
    total_bytes = 0
    change_types = {"A": "ADDED", "D": "DELETED", "M": "MODIFIED"}
    for old_mode, new_mode, old_id, new_id, kind, path in changes:
        if kind not in change_types or any(mode not in _REGULAR_MODES | {b"000000"} for mode in (old_mode, new_mode)):
            raise PatchError(error_code, "A comparison file cannot be reviewed as a regular text file")
        if any(character in path for character in "\r\n\t"):
            raise PatchError(error_code, "A comparison file has an unsupported path")
        if old_mode != b"000000":
            _object_text(repo_path, old_id, error_code)
        if new_mode != b"000000" and new_id != old_id:
            _object_text(repo_path, new_id, error_code)
        diff_bytes = _git(
            repo_path, "diff", *_DIFF_OPTIONS, base_sha, head_sha, "--", path, error_code=error_code,
        )
        total_bytes += len(diff_bytes)
        if not diff_bytes or total_bytes > MAX_REVIEW_DIFF_BYTES:
            raise PatchError(error_code, "Complete comparison diff could not fit the review input")
        diff = _text(diff_bytes, MAX_REVIEW_DIFF_BYTES, error_code)
        parts.append(diff)
        files.append({
            "path": path,
            "oldPath": path,
            "newPath": path,
            "diffText": diff,
            "newFile": kind == "A",
            "deletedFile": kind == "D",
            "renamedFile": False,
            "collapsed": False,
            "tooLarge": False,
            "changeType": change_types[kind],
        })
    return {"diffText": "".join(parts), "changedFiles": files}


def generate_finding_patch(
    db: Session,
    task_id: int,
    provider: CodeQualityModelProvider,
    repo_path: str | Path,
    base_sha: str,
    input_sha: str,
    finding: dict[str, Any],
    allowed_paths: Collection[str],
) -> str:
    path = finding.get("filePath")
    if not isinstance(path, str) or path not in allowed_paths or not is_repair_source_path(path):
        raise PatchError("REPAIR_FILE_NOT_EDITABLE", "The Finding is outside the editable source files")
    if str(finding.get("severity") or "").strip().upper() != "CRITICAL":
        raise PatchError("REPAIR_FINDING_INELIGIBLE", "Only a critical Finding can generate a repair patch")
    base_sha = _commit(repo_path, base_sha)
    input_sha = _commit(repo_path, input_sha)
    source = _source_file(repo_path, input_sha, path)
    diff = _text(
        _git(repo_path, "diff", *_DIFF_OPTIONS, base_sha, input_sha, "--", path),
        MAX_REVIEW_DIFF_BYTES,
        "REVIEW_DIFF_INCOMPLETE",
    )
    if not diff:
        raise PatchError("REPAIR_FILE_NOT_EDITABLE", "The source file is absent from the current comparison")
    try:
        result = run_fix_provider(
            db, task_id, provider,
            {
                "mode": "AUTO_FIX",
                "filePath": path,
                "finding": finding,
                "changedFiles": [path],
                "diffText": diff,
                "sourceText": source,
                "commitSha": input_sha,
            },
        )
    except AppError as exception:
        raise PatchError("REPAIR_PROVIDER_FAILED", "Repair model request failed") from exception
    patch = result.get("patchText")
    if result.get("status") != "SUCCESS" or not isinstance(patch, str) or not patch.strip():
        raise PatchError("REPAIR_PROVIDER_FAILED", "Repair model did not return a usable patch")
    if _patch_paths(repo_path, _patch_bytes(patch)) != {path}:
        raise PatchError("PATCH_REJECTED", "Patch touched a file outside the Finding")
    return patch


def create_candidate_commit(
    repo_path: str | Path,
    input_sha: str,
    allowed_paths: Collection[str],
    patches: Iterable[str],
    *,
    message: str,
) -> str:
    input_sha = _commit(repo_path, input_sha)
    allowed = {path for path in allowed_paths if is_repair_source_path(path)}
    if not allowed:
        raise PatchError("REPAIR_FILE_NOT_EDITABLE", "There are no editable source files")
    with TemporaryDirectory(prefix="review-auto-fix-") as temp:
        index_path = Path(temp) / "index"
        _git(repo_path, "read-tree", input_sha, index_path=index_path)
        total_bytes = 0
        changes = []
        for patch_number, patch in enumerate(patches, start=1):
            if patch_number > MAX_PATCHES_PER_ROUND:
                raise PatchError("PATCH_REJECTED", "The round exceeds the patch count limit")
            encoded = _patch_bytes(patch)
            total_bytes += len(encoded)
            if total_bytes > MAX_PATCH_BYTES:
                raise PatchError("PATCH_REJECTED", "The round exceeds the total patch byte limit")
            paths = _patch_paths(repo_path, encoded)
            if not paths <= allowed:
                raise PatchError("PATCH_REJECTED", "Patch touches a non-editable path")
            for path in paths:
                _source_file(repo_path, input_sha, path)
            _git(
                repo_path, "apply", "--cached", "--whitespace=nowarn", "-",
                data=encoded, index_path=index_path, error_code="PATCH_REJECTED",
            )
            changes = _raw_changes(
                _git(
                    repo_path, "diff", "--cached", *_RAW_DIFF_OPTIONS,
                    input_sha, "--", index_path=index_path,
                ),
                "PATCH_REJECTED",
            )
            for old_mode, new_mode, _, new_id, kind, path in changes:
                if kind != "M" or path not in allowed or old_mode != new_mode or old_mode not in _REGULAR_MODES:
                    raise PatchError("PATCH_REJECTED", "Patch changes protected paths, file modes or file presence")
                _object_text(repo_path, new_id, "PATCH_REJECTED")
        if not changes:
            raise PatchError("PATCH_EMPTY", "The repair round did not change any source files")
        tree = _git(repo_path, "write-tree", index_path=index_path).strip().decode("ascii")
        return _git(
            repo_path, "-c", "commit.gpgSign=false", "commit-tree", tree, "-p", input_sha,
            data=message.encode("utf-8"),
        ).strip().decode("ascii")
