"""Offline evidence replay. Input materials stay in the operator's isolated checkout."""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.agent_review_spike.diff import diff_by_file
from app.agent_review_spike.tool_executor import ReviewToolExecutor
from app.agent_review_spike.workspace import ReviewToolError, ReviewWorkspace, ToolBudget, validate_review_path
from app.core.config import get_settings
from app.core.database import SessionLocal
from app.core.errors import AppError
from app.evaluation.models import EvaluationRun, EvaluationRunItem
from app.evaluation.service import update_evaluation_run_item_response
from app.review_quality.monitoring import require_monitoring_enabled
from app.review_context.service import build_review_context_pack


_SHA = re.compile(r"[0-9a-f]{40}")
_CI_RUN_URL = re.compile(r"https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/actions/runs/[0-9]+")
_MAX_MATERIAL_BYTES = 1_048_576


def _git(root: Path, *args: str) -> str:
    environment = {key: val for key, val in os.environ.items() if not key.startswith("GIT_")}
    environment.update(GIT_TERMINAL_PROMPT="0", GIT_NO_LAZY_FETCH="1", GIT_OPTIONAL_LOCKS="0")
    with tempfile.TemporaryFile() as stream:
        subprocess.run(
            ["git", "--no-replace-objects", "--literal-pathspecs", "-c", "core.fsmonitor=false", "-C", str(root), *args],
            env=environment, stdout=stream, stderr=subprocess.DEVNULL, timeout=20, check=True,
        )
        stream.seek(0)
        value = stream.read(_MAX_MATERIAL_BYTES + 1)
    if len(value) > _MAX_MATERIAL_BYTES:
        raise ValueError("Replay material exceeds the size limit")
    return value.decode("utf-8")


def _commit(value: Any) -> str:
    if not isinstance(value, str) or _SHA.fullmatch(value) is None:
        raise ValueError("Replay requires pinned 40-character Git commit IDs")
    return value


def _read_source(worktree: Path, head: str, path: str) -> list[str]:
    try:
        safe_path = validate_review_path(path)
        return _git(worktree, "show", f"{head}:{safe_path}").splitlines()
    except (ReviewToolError, subprocess.SubprocessError, UnicodeError, ValueError) as exc:
        raise AppError("REPLAY_SOURCE_UNAVAILABLE", "Pinned source is unavailable") from exc


def _agent_replay(case: dict, worktree: Path, changed_paths: list[str], diff: str, temporary: Path) -> dict:
    probes = case["probes"]
    if not isinstance(probes, list) or not 1 <= len(probes) <= 10:
        raise ValueError("Replay requires one to ten evidence probes")
    patches = diff_by_file({"changedFiles": changed_paths, "diff": diff})
    executor = ReviewToolExecutor(
        ReviewWorkspace(worktree), changed_paths, temporary / "result.json", temporary / "audit.json",
        ToolBudget(), patches,
    )
    outcomes = []
    for probe in probes:
        path = validate_review_path(probe["path"])
        start_line, end_line = probe["startLine"], probe["endLine"]
        if type(start_line) is not int or type(end_line) is not int or not 1 <= start_line <= end_line <= start_line + 399:
            raise ValueError("Replay probe range must contain 1 to 400 lines")
        expected_hash, expected_error = probe.get("expectedContentSha256"), probe.get("expectedErrorCode")
        if bool(expected_hash) == bool(expected_error) or (
            expected_hash and re.fullmatch(r"[0-9a-f]{64}", expected_hash) is None
        ) or (expected_error and expected_error not in {"DIFF_CONTENT_UNAVAILABLE", "DIFF_RANGE_OUT_OF_BOUNDS"}):
            raise ValueError("Each probe requires an expected content hash or a supported error code")
        result = executor.execute(
            "read_diff_range", {"path": path, "startLine": start_line, "endLine": end_line},
        )
        content = result.value.get("content")
        error = result.value.get("errorCode") if result.is_error else None
        passed = bool(
            (expected_error and result.is_error and error == expected_error)
            or (expected_hash and isinstance(content, str) and sha256(content.encode("utf-8")).hexdigest() == expected_hash)
        )
        outcomes.append({"passed": passed, "lineCount": result.value.get("lineCount"), "errorCode": error})
    return {"passed": all(row["passed"] for row in outcomes), "readablePatchCount": len(patches), "probes": outcomes}


def _standard_replay(case: dict, worktree: Path, head: str, changed_paths: list[str], diff: str) -> dict:
    requested = case["expectedEvidencePaths"]
    if not isinstance(requested, list):
        raise ValueError("Expected evidence paths must be a list")
    expected = [validate_review_path(path) for path in requested]
    if not 1 <= len(expected) <= 10 or len(set(expected)) != len(expected):
        raise ValueError("Replay requires one to ten unique expected evidence paths")
    workspace_root = Path(get_settings().local_repo_workspace_root).resolve()
    if not worktree.is_relative_to(workspace_root):
        raise AppError("REPLAY_WORKSPACE_OUTSIDE_ROOT", "Worktree is outside the configured replay workspace")
    pack = build_review_context_pack(
        None, project_id=None, changed_files=changed_paths, diff_text=diff, mode="DIFF_TEXT", head_ref=head,
        replay_worktree=worktree, replay_source_reader=lambda path: _read_source(worktree, head, path),
    )
    final_pack = json.loads(pack["promptText"])["contextPack"]
    paths = {
        item.get("path") or item.get("relativePath")
        for item in final_pack.get("sameFileContext", {}).get("sourceSnippets", [])
        if item.get("snippets")
    }
    references = final_pack.get("localReferenceContext", {})
    for search in references.get("searches", []):
        paths.update(item.get("path") or item.get("relativePath") for item in search.get("snippets", []))
    meta = pack["meta"]
    target = case["targetContextChars"]
    if type(target) is not int or not 1 <= target <= 20_000:
        raise ValueError("Invalid Context Pack target for replay")
    found_count = sum(path in paths for path in expected)
    return {
        "passed": found_count == len(expected) and meta["promptLength"] <= target,
        "expectedEvidenceCount": len(expected), "retainedExpectedEvidenceCount": found_count,
        "queryCount": meta["localReferenceQueryCount"], "includedSnippetCount": meta["localReferenceSnippetCount"],
        "contextPromptChars": meta["promptLength"], "targetContextChars": target,
    }


def replay(fixture: Path, worktree: Path) -> dict:
    with fixture.open("rb") as stream:
        raw = stream.read(_MAX_MATERIAL_BYTES + 1)
    if len(raw) > _MAX_MATERIAL_BYTES:
        raise ValueError("Replay fixture exceeds the size limit")
    case = json.loads(raw)
    base, head = _commit(case["base"]), _commit(case["head"])
    root = worktree.resolve(strict=True)
    if Path(_git(root, "rev-parse", "--show-toplevel").strip()).resolve() != root:
        raise ValueError("Replay requires a repository root")
    if _git(root, "rev-parse", "HEAD").strip() != head or _git(
        root, "status", "--porcelain", "--untracked-files=all", "--ignored", "--ignore-submodules=none",
    ).strip():
        raise ValueError("Replay requires a clean checkout at the pinned head")
    for entry in _git(root, "ls-files", "--stage", "-v", "-z").split("\0"):
        if entry and (entry[0] != "H" or entry[2:8] not in {"100644", "100755"}):
            raise ValueError("Replay requires a full checkout of regular tracked files")
    included = case["changedFiles"]
    if not isinstance(included, list):
        raise ValueError("Replay changed files must be a list")
    changed_paths = [validate_review_path(path) for path in included]
    if not 1 <= len(changed_paths) <= 200 or len(changed_paths) != len(set(changed_paths)):
        raise ValueError("Replay requires one to 200 unique changed files")
    diff = _git(root, "diff", "--no-ext-diff", "--no-textconv", f"{base}^{{commit}}", f"{head}^{{commit}}", "--", *changed_paths)
    kind = case["kind"]
    with tempfile.TemporaryDirectory() as sandbox:
        if kind == "AGENT_DIFF":
            summary = _agent_replay(case, root, changed_paths, diff, Path(sandbox))
        elif kind == "STANDARD_CONTEXT":
            # The existing retriever reads its working tree. Use the verified local checkout only.
            if os.getenv("RIPGREP_CONFIG_PATH"):
                raise ValueError("Run deterministic replay without a custom ripgrep configuration")
            summary = _standard_replay(case, root, head, changed_paths, diff)
        else:
            raise ValueError("Unsupported replay kind")
    return {"fixtureSha256": sha256(raw).hexdigest(), "kind": kind, **summary}


def record_comparison(run_id: int, item_id: int, baseline: dict, candidate: dict) -> None:
    if (baseline["kind"], baseline["fixtureSha256"]) != (candidate["kind"], candidate["fixtureSha256"]):
        raise ValueError("Results must use the same pinned fixture")
    with SessionLocal() as db:
        require_monitoring_enabled(db)
        run = db.scalar(select(EvaluationRun).where(
            EvaluationRun.id == run_id, EvaluationRun.project_id.is_not(None),
            EvaluationRun.run_type == "REVIEW_REPLAY",
        ).with_for_update())
        if run is None:
            raise AppError("REPLAY_ITEM_UNAVAILABLE", "The scoped replay item is unavailable", 404)
        item = db.scalar(select(EvaluationRunItem).where(
            EvaluationRunItem.id == item_id, EvaluationRunItem.run_id == run_id,
            EvaluationRunItem.project_id == run.project_id,
        ).with_for_update())
        if item is None:
            raise AppError("REPLAY_ITEM_UNAVAILABLE", "The scoped replay item is unavailable", 404)
        if item.status != "PENDING":
            saved = (json.loads(item.baseline_summary_json or "null"), json.loads(item.candidate_summary_json or "null"))
            if saved == (baseline, candidate):
                return
            raise AppError("REPLAY_ITEM_CONFLICT", "The replay item already holds an outcome", 409)
        update_evaluation_run_item_response(db, run_id, item_id, {
            "status": "COMPLETED" if candidate["passed"] else "FAILED",
            "baselineSummary": baseline,
            "candidateSummary": candidate,
            "resultSummary": {
                "kind": candidate["kind"], "passed": candidate["passed"],
                **({"ciRunUrl": candidate["ciRunUrl"]} if "ciRunUrl" in candidate else {}),
            },
        })


def _read_record(path: Path) -> dict:
    common = {"kind", "fixtureSha256", "build", "passed"}
    context_measurements = {
        "expectedEvidenceCount", "retainedExpectedEvidenceCount", "queryCount",
        "includedSnippetCount", "contextPromptChars", "targetContextChars",
    }
    with path.open("rb") as stream:
        raw = stream.read(16_385)
    if len(raw) > 16_384:
        raise ValueError("Replay summary exceeds the size limit")
    value = json.loads(raw)
    if not isinstance(value, dict) or type(value.get("passed")) is not bool:
        raise ValueError("Invalid replay summary shape")
    kind = value.get("kind")
    if kind == "AGENT_DIFF":
        measurements = {"readablePatchCount"}
        required = common | measurements | {"probes"}
    elif kind == "STANDARD_CONTEXT":
        measurements = context_measurements
        required = common | measurements
    else:
        raise ValueError("Invalid replay kind")
    if value.keys() - {"ciRunUrl"} != required:
        raise ValueError("Replay summary is missing required measurements or contains extra fields")
    if "ciRunUrl" in value and (
        not isinstance(value["ciRunUrl"], str) or len(value["ciRunUrl"]) > 255
        or _CI_RUN_URL.fullmatch(value["ciRunUrl"]) is None
    ):
        raise ValueError("Invalid GitHub Actions run URL")
    if re.fullmatch(r"[0-9a-f]{64}", value.get("fixtureSha256", "")) is None:
        raise ValueError("Replay summary is missing the fixture fingerprint")
    _commit(value.get("build"))
    for key in measurements:
        if type(value[key]) is not int or not 0 <= value[key] <= _MAX_MATERIAL_BYTES:
            raise ValueError("Invalid replay measurement")
    if kind == "STANDARD_CONTEXT":
        expected, retained = value["expectedEvidenceCount"], value["retainedExpectedEvidenceCount"]
        target = value["targetContextChars"]
        if not 0 <= retained <= expected or not 1 <= expected <= 10 or not 1 <= target <= 20_000 or (
            value["passed"] != (retained == expected and value["contextPromptChars"] <= target)
        ):
            raise ValueError("Invalid Context Pack comparison outcome")
        return value
    probes = value["probes"]
    if not isinstance(probes, list) or not 1 <= len(probes) <= 10:
        raise ValueError("Invalid replay probe summaries")
    for probe in probes:
        if not isinstance(probe, dict) or probe.keys() != {"passed", "lineCount", "errorCode"}:
            raise ValueError("Invalid replay probe summary")
        if type(probe["passed"]) is not bool or (
            probe["lineCount"] is not None and (type(probe["lineCount"]) is not int or not 0 <= probe["lineCount"] <= 400)
        ) or (probe["errorCode"] is not None and re.fullmatch(r"[A-Z_]{1,64}", probe["errorCode"]) is None):
            raise ValueError("Invalid replay probe measurement")
    if value["passed"] != all(probe["passed"] for probe in probes):
        raise ValueError("Invalid Diff comparison outcome")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="Replay evidence under the current platform code without opening a database")
    run.add_argument("--fixture", type=Path, required=True)
    run.add_argument("--worktree", type=Path, required=True)
    run.add_argument("--build", required=True, help="Immutable code revision supplied by the checkout or CI runner")
    run.add_argument("--ci-run-url", help="GitHub Actions run URL for the evaluation record")
    store = commands.add_parser("record", help="Store two verified summaries in a pending evaluation item")
    store.add_argument("--baseline", type=Path, required=True)
    store.add_argument("--candidate", type=Path, required=True)
    store.add_argument("--run-id", type=int, required=True)
    store.add_argument("--item-id", type=int, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "run":
            summary = replay(args.fixture, args.worktree)
            summary["build"] = _commit(args.build)
            if args.ci_run_url is not None:
                if len(args.ci_run_url) > 255 or _CI_RUN_URL.fullmatch(args.ci_run_url) is None:
                    raise ValueError("Invalid GitHub Actions run URL")
                summary["ciRunUrl"] = args.ci_run_url
            print(json.dumps(summary))
            return 0 if summary["passed"] else 1
        baseline, candidate = _read_record(args.baseline), _read_record(args.candidate)
        record_comparison(args.run_id, args.item_id, baseline, candidate)
    except (AppError, ReviewToolError, KeyError, OSError, SQLAlchemyError, ValueError, TypeError, subprocess.SubprocessError) as exc:
        code = exc.code if isinstance(exc, AppError) else type(exc).__name__
        print(json.dumps({"passed": False, "errorCode": code}))
        return 2
    print(json.dumps({"recorded": True, "passed": candidate["passed"]}))
    return 0 if candidate["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
