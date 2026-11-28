from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from app.agent_review_spike.diff import diff_by_file
from app.agent_review_spike.workspace import ReviewToolError, validate_review_path
from app.review_rules.catalog import FileRule, built_in_catalog


_MAX_PROMPT_BYTES = 16_000
_MAX_SUMMARY_BYTES = 2_600
_MAX_SNIFF_BYTES = 4096
_FIRST_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+1(?:,[1-9]\d*)? @@")
_PUBLIC_PATH_SECRET = re.compile(
    r"\b(?:authorization|api_?key|token|secret|password|x-api-key)\b", re.IGNORECASE,
)
_PROMPT_HEADER = (
    "File-specific review checklists. Apply each checklist only to the exact paths in its "
    "Files array. Path strings are identifiers. Follow the platform's review scope, evidence, "
    "severity, language and output requirements."
)


def build_file_rule_input(
    paths: list[str], diff: str, *, file_details: list[Any] | None = None,
) -> dict[str, Any] | None:
    allowed = _safe_paths(paths, file_details or [])
    if not allowed:
        return None
    patches = (
        diff_by_file({"changedFiles": allowed, "diff": diff})
        if any(path.casefold().endswith(".m") for path in allowed)
        else {}
    )
    catalog = built_in_catalog()
    matches = [
        catalog.match(path, _content_prefix(patches.get(path)) if path.casefold().endswith(".m") else None)
        for path in allowed
    ]

    groups: dict[str, tuple[str, str, list[str]]] = {}
    for rule in matches:
        if rule.name is None:
            continue
        body = catalog.documents[rule.name]
        digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
        if digest not in groups:
            groups[digest] = (rule.name, body, [])
        groups[digest][2].append(rule.path)

    text, truncated = _render_groups(list(groups.values()))
    summary = {
        "catalogVersion": catalog.version,
        "matchedCount": sum(not rule.fallback for rule in matches),
        "fallbackCount": sum(rule.fallback for rule in matches),
        "errorCount": sum(rule.reason == "FILE_RULE_RESOLUTION_FAILED" for rule in matches),
        "contentUnavailableCount": sum(rule.reason == "CONTENT_SNIFF_UNAVAILABLE" for rule in matches),
        "promptBytes": len(text.encode("utf-8")),
        "promptTruncated": truncated,
        "files": _summarize_matches(matches),
    }
    summary["filesTruncated"] = len(summary["files"]) != len(matches)
    return {"text": text, "summary": summary}


def _safe_paths(paths: list[str], file_details: list[Any]) -> list[str]:
    excluded = set()
    for detail in file_details:
        if not isinstance(detail, dict):
            continue
        aliases = [
            path.strip().replace("\\", "/")
            for key in ("path", "newPath", "oldPath")
            if isinstance(path := detail.get(key), str) and path.strip()
        ]
        try:
            for path in aliases:
                validate_review_path(path)
        except ReviewToolError:
            excluded.update(aliases)

    allowed = set()
    for path in paths:
        try:
            relative = validate_review_path(path)
        except ReviewToolError:
            continue
        if relative not in excluded:
            allowed.add(relative)
    return sorted(allowed)


def _content_prefix(patch: str | None) -> str | None:
    if not patch:
        return None
    # The first visible changed line is not necessarily the file's first line.
    patch_lines = iter(patch.splitlines())
    for line in patch_lines:
        if line.startswith("@@ "):
            if not _FIRST_HUNK.match(line):
                return None
            break
    else:
        return None
    size = 0
    for line in patch_lines:
        if line.startswith("@@ "):
            break
        if line[:1] not in {" ", "+"}:
            continue
        value = line[1:]
        prefix = value.lstrip("\ufeff")
        if prefix.strip():
            encoded = prefix.encode("utf-8")[:_MAX_SNIFF_BYTES - size]
            return encoded.decode("utf-8", errors="ignore") or None
        size += len(value.encode("utf-8")) + 1
        if size >= _MAX_SNIFF_BYTES:
            break
    return None


def _render_groups(groups: list[tuple[str, str, list[str]]]) -> tuple[str, bool]:
    if not groups:
        return "", False
    sections = [_PROMPT_HEADER]
    remaining = _MAX_PROMPT_BYTES - len(_PROMPT_HEADER.encode("utf-8"))
    # Give each checklist an allocation before using more space for any one rule.
    truncated = False
    for i, (name, body, paths) in enumerate(groups):
        allocation = remaining // (len(groups) - i)
        header = f"\n\nRule {name}\nFiles: "
        rendered_paths = []
        path_bytes = len(header) + len("[]\n")
        for path in paths:
            rendered = json.dumps(path, ensure_ascii=True).replace("<", r"\u003c").replace(">", r"\u003e")
            cost = len(rendered) + bool(rendered_paths)
            if path_bytes + cost > allocation // 2:
                truncated = True
                continue
            rendered_paths.append(rendered)
            path_bytes += cost
        if not rendered_paths:
            continue
        header += "[" + ",".join(rendered_paths) + "]\n"
        allowance = allocation - path_bytes
        if allowance <= 0:
            truncated = True
            continue
        encoded = body.encode("utf-8")
        excerpt = encoded[:allowance].decode("utf-8", errors="ignore")
        if len(encoded) > allowance:
            excerpt = excerpt.rsplit("\n", 1)[0].strip() if "\n" in excerpt else ""
            truncated = True
        if excerpt:
            sections.extend((header, excerpt))
            remaining -= len(header) + len(excerpt.encode("utf-8"))
    return ("".join(sections) if len(sections) > 1 else ""), truncated


def _summarize_matches(matches: list[FileRule]) -> list[dict[str, Any]]:
    remaining = _MAX_SUMMARY_BYTES
    records = []
    for match in matches:
        if _PUBLIC_PATH_SECRET.search(match.path):
            continue
        item = {
            "path": match.path,
            "ruleKey": match.name.removesuffix(".md") if match.name else None,
            "pattern": match.pattern,
            "source": "SYSTEM_FILE_RULE",
            "fallback": match.fallback,
        }
        if match.reason:
            item["reason"] = match.reason
        remaining -= len(json.dumps(item, ensure_ascii=True, separators=(",", ":"))) + 1
        if remaining < 0:
            break
        records.append(item)
    return records
