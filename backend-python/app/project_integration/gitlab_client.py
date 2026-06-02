from __future__ import annotations

from typing import Any
from urllib.parse import quote

import httpx

from app.core.config import get_settings
from app.core.errors import AppError


class GitLabDiffsEndpointNotFoundError(Exception):
    pass


MAX_RAW_FILE_BYTES = 1024 * 1024
MAX_RAW_FILE_LINES = 20_000


def list_merge_request_diffs(project_id: str, merge_request_iid: str) -> list[dict[str, Any]]:
    _validate_ready()
    if not project_id:
        raise AppError("BAD_REQUEST", "GitLab project id is required to fetch MR diffs", 400)
    if not merge_request_iid:
        raise AppError("BAD_REQUEST", "GitLab merge request iid is required to fetch MR diffs", 400)
    try:
        return _list_merge_request_diffs_from_diffs(project_id, merge_request_iid)
    except GitLabDiffsEndpointNotFoundError:
        return _list_merge_request_diffs_from_changes(project_id, merge_request_iid)


def compare(project_id: str, from_sha: str | None, to_sha: str | None) -> list[dict[str, Any]]:
    _validate_ready()
    if not project_id:
        raise AppError("BAD_REQUEST", "GitLab project id is required to compare refs", 400)
    if not from_sha:
        raise AppError("BAD_REQUEST", "GitLab compare from sha is required", 400)
    if not to_sha:
        raise AppError("BAD_REQUEST", "GitLab compare to sha is required", 400)
    response = _get(
        f"/api/v4/projects/{_quote(project_id)}/repository/compare",
        params={"from": from_sha, "to": to_sha},
        error_prefix="Failed to fetch GitLab compare diff",
    )
    diffs = response.get("diffs")
    if not isinstance(diffs, list):
        raise AppError("INTERNAL_ERROR", "GitLab compare response must contain a diffs array", 500)
    return [_to_diff_file(item) for item in diffs]


def get_project_detail(project_id: str) -> dict[str, Any]:
    _validate_ready()
    response = _get(
        f"/api/v4/projects/{_quote(project_id)}",
        error_prefix="Failed to fetch GitLab API",
    )
    return {
        "id": _text(response.get("id")),
        "name": response.get("name"),
        "pathWithNamespace": response.get("path_with_namespace"),
        "webUrl": response.get("web_url"),
    }


def get_merge_request_detail(project_id: str, merge_request_iid: str) -> dict[str, Any]:
    _validate_ready()
    response = _get(
        f"/api/v4/projects/{_quote(project_id)}/merge_requests/{_quote(merge_request_iid)}",
        error_prefix="Failed to fetch GitLab API",
    )
    author = response.get("author") or {}
    diff_refs = response.get("diff_refs") or {}
    return {
        "iid": _text(response.get("iid")),
        "title": response.get("title"),
        "webUrl": response.get("web_url"),
        "sourceBranch": response.get("source_branch"),
        "targetBranch": response.get("target_branch"),
        "commitSha": response.get("sha")
        or diff_refs.get("head_sha")
        or response.get("merge_commit_sha")
        or response.get("squash_commit_sha"),
        "baseSha": diff_refs.get("base_sha"),
        "headSha": diff_refs.get("head_sha") or response.get("sha"),
        "startSha": diff_refs.get("start_sha"),
        "authorName": author.get("name"),
        "authorUsername": author.get("username"),
    }


def get_raw_file(project_id: str, file_path: str, ref: str) -> list[str]:
    _validate_ready()
    if not project_id:
        raise AppError("BAD_REQUEST", "GitLab project id is required to fetch repository file", 400)
    if not file_path:
        raise AppError("BAD_REQUEST", "GitLab repository file path is required", 400)
    if not ref:
        raise AppError("BAD_REQUEST", "GitLab repository file ref is required", 400)
    content = _get_raw(
        f"/api/v4/projects/{_quote(project_id)}/repository/files/{_quote(file_path)}/raw",
        params={"ref": ref},
        error_prefix="Failed to fetch GitLab repository file",
    )
    if len(content) > MAX_RAW_FILE_BYTES:
        raise AppError("BAD_REQUEST", f"GitLab repository file exceeds {MAX_RAW_FILE_BYTES} bytes", 400)
    text = content.decode("utf-8", errors="replace")
    lines = text.splitlines()
    if len(lines) > MAX_RAW_FILE_LINES:
        raise AppError("BAD_REQUEST", f"GitLab repository file exceeds {MAX_RAW_FILE_LINES} lines", 400)
    return lines


def _list_merge_request_diffs_from_diffs(project_id: str, merge_request_iid: str) -> list[dict[str, Any]]:
    settings = get_settings()
    per_page = max(settings.gitlab_diff_per_page, 1)
    page = 1
    files: list[dict[str, Any]] = []
    while True:
        try:
            response = _get(
                f"/api/v4/projects/{_quote(project_id)}/merge_requests/{_quote(merge_request_iid)}/diffs",
                params={"page": page, "per_page": per_page},
                error_prefix="Failed to fetch GitLab MR diffs",
                not_found_as_diffs_missing=True,
            )
        except GitLabDiffsEndpointNotFoundError:
            raise
        if not isinstance(response, list):
            raise AppError("INTERNAL_ERROR", "GitLab MR diffs response must be an array", 500)
        files.extend(_to_diff_file(item) for item in response)
        if len(response) < per_page:
            return files
        page += 1


def _list_merge_request_diffs_from_changes(project_id: str, merge_request_iid: str) -> list[dict[str, Any]]:
    response = _get(
        f"/api/v4/projects/{_quote(project_id)}/merge_requests/{_quote(merge_request_iid)}/changes",
        error_prefix="Failed to fetch GitLab MR changes",
    )
    changes = response.get("changes") if isinstance(response, dict) else None
    if not isinstance(changes, list):
        raise AppError("INTERNAL_ERROR", "GitLab MR changes response must contain a changes array", 500)
    return [_to_diff_file(item) for item in changes]


def _get(
    path: str,
    *,
    params: dict[str, Any] | None = None,
    error_prefix: str,
    not_found_as_diffs_missing: bool = False,
) -> Any:
    settings = get_settings()
    url = _base_url(settings.gitlab_base_url) + path
    try:
        with httpx.Client(timeout=15) as client:
            response = client.get(url, params=params, headers={"PRIVATE-TOKEN": settings.gitlab_token})
    except httpx.HTTPError as exception:
        raise AppError("INTERNAL_ERROR", f"{error_prefix}: {exception}", 500) from exception
    if response.status_code == 404 and not_found_as_diffs_missing:
        raise GitLabDiffsEndpointNotFoundError()
    if response.is_error:
        raise AppError("INTERNAL_ERROR", f"{error_prefix}: HTTP {response.status_code}", 500)
    return response.json()


def _get_raw(
    path: str,
    *,
    params: dict[str, Any] | None = None,
    error_prefix: str,
) -> bytes:
    settings = get_settings()
    url = _base_url(settings.gitlab_base_url) + path
    try:
        with httpx.Client(timeout=15) as client:
            response = client.get(url, params=params, headers={"PRIVATE-TOKEN": settings.gitlab_token})
    except httpx.HTTPError as exception:
        raise AppError("INTERNAL_ERROR", f"{error_prefix}: {exception}", 500) from exception
    if response.status_code == 404:
        raise AppError("RESOURCE_NOT_FOUND", f"{error_prefix}: HTTP 404", 404)
    if response.is_error:
        raise AppError("INTERNAL_ERROR", f"{error_prefix}: HTTP {response.status_code}", 500)
    return response.content


def _validate_ready() -> None:
    settings = get_settings()
    if not settings.gitlab_api_enabled:
        raise AppError("BAD_REQUEST", "GitLab diff is not provided and GitLab API is disabled", 400)
    if not settings.gitlab_base_url.strip():
        raise AppError("BAD_REQUEST", "GitLab API base-url is required", 400)
    if not settings.gitlab_token.strip():
        raise AppError("BAD_REQUEST", "GitLab API token is required", 400)


def _to_diff_file(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "oldPath": item.get("old_path"),
        "newPath": item.get("new_path"),
        "path": item.get("new_path") or item.get("old_path"),
        "diffText": item.get("diff"),
        "newFile": bool(item.get("new_file")),
        "renamedFile": bool(item.get("renamed_file")),
        "deletedFile": bool(item.get("deleted_file")),
        "collapsed": bool(item.get("collapsed")),
        "tooLarge": bool(item.get("too_large")),
        "changeType": _infer_change_type(item),
    }


def _infer_change_type(item: dict[str, Any]) -> str:
    if item.get("new_file"):
        return "ADDED"
    if item.get("deleted_file"):
        return "DELETED"
    if item.get("renamed_file"):
        return "RENAMED"
    return "MODIFIED"


def _base_url(base_url: str) -> str:
    return base_url.strip().rstrip("/")


def _quote(value: str) -> str:
    return quote(value, safe="")


def _text(value: Any) -> str | None:
    return str(value) if value is not None else None
