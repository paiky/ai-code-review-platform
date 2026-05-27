from __future__ import annotations

from datetime import datetime, timezone
from fnmatch import fnmatchcase
import json
from typing import Any
from urllib.parse import urlparse, urlunparse

from sqlalchemy.orm import Session

from app.change_analysis.service import analyze_changes
from app.code_quality.service import trigger_auto_review
from app.code_quality.repository import get_settings_record
from app.core.config import get_settings
from app.core.errors import AppError
from app.notification.service import send_review_summary, send_risk_card
from app.project_integration import gitlab_client
from app.project_integration.models import GitLabMergeRequestEvent, GitLabPushEvent
from app.project_integration.repository import (
    ambiguous_auto_detected_target_types,
    get_project_group_push_policy,
    resolve_project_review_profile_code,
    resolve_project_target_config,
    update_project_target_detection,
    upsert_gitlab_project,
)
from app.review_record.repository import (
    create_review_task,
    mark_task_failed,
    mark_task_success,
    save_notification_records,
    save_review_result,
)
from app.risk_engine.service import generate_risk_card
from app.rule_template.repository import get_enabled_template


def handle_gitlab_webhook(db: Session, gitlab_event: str | None, payload: dict[str, Any]) -> dict:
    object_kind = _text(payload, "object_kind")
    if gitlab_event == "Merge Request Hook" or object_kind == "merge_request":
        return handle_merge_request_webhook(db, payload)
    if gitlab_event == "Push Hook" or object_kind == "push":
        return handle_push_webhook(db, payload)
    raise AppError("BAD_REQUEST", f"Unsupported GitLab event: {gitlab_event}", 400)


def handle_merge_request_webhook(db: Session, payload: dict[str, Any]) -> dict:
    _validate_mr_payload(payload)
    event = _parse_mr_event(payload)
    if not _is_opened_mr(event):
        return {
            "taskId": None,
            "status": "SKIPPED",
            "gitProjectId": event["gitProjectId"],
            "projectName": event["projectName"],
            "mrId": event["mrId"],
        }

    event = _enrich_mr_detail(event)
    project = upsert_gitlab_project(
        db,
        event["gitProjectId"],
        event["projectName"],
        event["repositoryUrl"],
        event["changedFilesSummary"].get("files", []),
    )
    ambiguous_types = ambiguous_auto_detected_target_types(db, project)
    if ambiguous_types:
        task = _create_failed_mr_task_for_ambiguous_targets(db, project, event, payload, ambiguous_types)
        db.commit()
        return {
            "taskId": task.id,
            "status": "FAILED",
            "gitProjectId": event["gitProjectId"],
            "projectName": event["projectName"],
            "mrId": event["mrId"],
            "reasonCode": "TARGET_TYPE_AMBIGUOUS",
            "message": task.error_message,
        }
    target_config = resolve_project_target_config(
        db,
        project,
        event["changedFilesSummary"].get("files", []),
    )
    task = create_review_task(
        db,
        project_id=project.id,
        trigger_type="GITLAB_MR_WEBHOOK",
        external_source_id=event["mrId"],
        external_url=event["externalUrl"],
        source_branch=event["sourceBranch"],
        target_branch=event["targetBranch"],
        commit_sha=event["commitSha"],
        before_sha=None,
        after_sha=None,
        author_name=event["authorName"],
        author_username=event["authorUsername"],
        template_code=target_config["templateCode"],
        target_type=target_config["targetType"],
        target_types=target_config["targetTypes"],
        code_quality_profile_code=target_config["profileCode"],
    )
    now = datetime.now()
    mr_record = GitLabMergeRequestEvent(
        task_id=task.id,
        git_project_id=event["gitProjectId"],
        project_name=event["projectName"],
        mr_id=event["mrId"],
        event_action=event["eventAction"],
        event_time=event["eventTime"],
        source_branch=event["sourceBranch"],
        target_branch=event["targetBranch"],
        author_name=event["authorName"],
        author_username=event["authorUsername"],
        changed_files_summary=json.dumps(event["changedFilesSummary"], ensure_ascii=False),
        raw_payload=json.dumps(payload, ensure_ascii=False),
        created_at=now,
        updated_at=now,
    )
    db.add(mr_record)
    try:
        if event["changedFilesSummary"].get("source") != "payload":
            event["changedFilesSummary"] = _build_gitlab_changed_files_summary(
                gitlab_client.list_merge_request_diffs(event["gitProjectId"], event["mrId"]),
                "gitlab_api",
            )
            mr_record.changed_files_summary = json.dumps(
                event["changedFilesSummary"], ensure_ascii=False
            )
            update_project_target_detection(
                db,
                project,
                event["projectName"],
                event["changedFilesSummary"].get("files", []),
            )
            ambiguous_types = ambiguous_auto_detected_target_types(db, project)
            if ambiguous_types:
                _mark_existing_task_failed_for_ambiguous_targets(task, ambiguous_types)
                db.commit()
                return {
                    "taskId": task.id,
                    "status": "FAILED",
                    "gitProjectId": event["gitProjectId"],
                    "projectName": event["projectName"],
                    "mrId": event["mrId"],
                    "reasonCode": "TARGET_TYPE_AMBIGUOUS",
                    "message": task.error_message,
                }
        result = _process_task(db, task, event["changedFilesSummary"].get("files", []), None)
        db.commit()
        return {
            "taskId": task.id,
            "status": "SUCCESS",
            "gitProjectId": event["gitProjectId"],
            "projectName": event["projectName"],
            "mrId": event["mrId"],
            "riskLevel": result["riskCard"]["riskLevel"],
        }
    except Exception as exception:
        if task is not None:
            mark_task_failed(task, str(exception))
        db.commit()
        raise


def handle_push_webhook(db: Session, payload: dict[str, Any]) -> dict:
    if _text(payload, "object_kind") != "push":
        raise AppError("BAD_REQUEST", "object_kind must be push", 400)
    git_project_id = str(_nested(payload, "project", "id") or payload.get("project_id") or "")
    if not git_project_id:
        raise AppError("BAD_REQUEST", "GitLab project id is required", 400)
    project = payload.get("project") or {}
    project_name = project.get("path_with_namespace") or project.get("name") or f"gitlab-project-{git_project_id}"
    repository_url = project.get("web_url") or (payload.get("repository") or {}).get("homepage") or (payload.get("repository") or {}).get("git_http_url")
    event = _parse_push_event(payload, git_project_id, project_name, repository_url)
    project_record = upsert_gitlab_project(
        db,
        git_project_id,
        project_name,
        repository_url,
        event["changedFilesSummary"].get("files", []),
    )
    branch_gate = _push_webhook_branch_gate(db, project_record, event["branchName"])
    if not branch_gate["allowed"]:
        db.commit()
        return {
            "taskId": None,
            "status": "SKIPPED",
            "gitProjectId": git_project_id,
            "projectName": project_name,
            "mrId": None,
            "branchName": event["branchName"],
            "reasonCode": "PUSH_BRANCH_NOT_ALLOWED",
            "message": (
                "GitLab Push branch is not configured in project group pushBranchPatterns; "
                "platform review flow was skipped."
            ),
            "profileCode": branch_gate["profileCode"],
            "pushBranchPatterns": branch_gate["patterns"],
        }
    ambiguous_types = ambiguous_auto_detected_target_types(db, project_record)
    if ambiguous_types:
        task = _create_failed_push_task_for_ambiguous_targets(db, project_record, event, payload, ambiguous_types)
        db.commit()
        return {
            "taskId": task.id,
            "status": "FAILED",
            "gitProjectId": git_project_id,
            "projectName": project_name,
            "mrId": None,
            "branchName": event["branchName"],
            "reasonCode": "TARGET_TYPE_AMBIGUOUS",
            "message": task.error_message,
        }
    task = None
    try:
        if event["changedFilesSummary"].get("source") != "payload":
            event["changedFilesSummary"] = _build_gitlab_changed_files_summary(
                gitlab_client.compare(git_project_id, event["beforeSha"], event["afterSha"]),
                "gitlab_compare_api",
            )
            project_record = update_project_target_detection(
                db,
                project_record,
                project_name,
                event["changedFilesSummary"].get("files", []),
            )
            ambiguous_types = ambiguous_auto_detected_target_types(db, project_record)
            if ambiguous_types:
                task = _create_failed_push_task_for_ambiguous_targets(db, project_record, event, payload, ambiguous_types)
                db.commit()
                return {
                    "taskId": task.id,
                    "status": "FAILED",
                    "gitProjectId": git_project_id,
                    "projectName": project_name,
                    "mrId": None,
                    "branchName": event["branchName"],
                    "reasonCode": "TARGET_TYPE_AMBIGUOUS",
                    "message": task.error_message,
                }
        target_config = resolve_project_target_config(
            db,
            project_record,
            event["changedFilesSummary"].get("files", []),
        )
        task = create_review_task(
            db,
            project_id=project_record.id,
            trigger_type="GITLAB_PUSH_WEBHOOK",
            external_source_id=event["afterSha"],
            external_url=event["externalUrl"],
            source_branch=event["branchName"],
            target_branch=None,
            commit_sha=event["afterSha"],
            before_sha=event["beforeSha"],
            after_sha=event["afterSha"],
            author_name=event["authorName"],
            author_username=event["authorUsername"],
            template_code=target_config["templateCode"],
            target_type=target_config["targetType"],
            target_types=target_config["targetTypes"],
            code_quality_profile_code=target_config["profileCode"],
        )
        now = datetime.now()
        push_record = GitLabPushEvent(
            task_id=task.id,
            git_project_id=git_project_id,
            project_name=project_name,
            ref=event["ref"],
            branch_name=event["branchName"],
            before_sha=event["beforeSha"],
            after_sha=event["afterSha"],
            event_time=event["eventTime"],
            author_name=event["authorName"],
            author_username=event["authorUsername"],
            changed_files_summary=json.dumps(event["changedFilesSummary"], ensure_ascii=False),
            raw_payload=json.dumps(payload, ensure_ascii=False),
            created_at=now,
            updated_at=now,
        )
        db.add(push_record)
        result = _process_task(db, task, event["changedFilesSummary"].get("files", []), None)
        db.commit()
        return {
            "taskId": task.id,
            "status": "SUCCESS",
            "gitProjectId": git_project_id,
            "projectName": project_name,
            "mrId": None,
            "riskLevel": result["riskCard"]["riskLevel"],
        }
    except Exception as exception:
        if task is not None:
            mark_task_failed(task, str(exception))
        db.commit()
        raise


def _ambiguous_target_message(target_types: list[str]) -> str:
    return (
        "端类型路径映射命中多个端类型："
        + "、".join(target_types)
        + "。请在设置页确认最近路径匹配结果，并调整全局端类型路径映射或项目端类型配置后重新触发审阅。"
    )


def _create_failed_mr_task_for_ambiguous_targets(
    db: Session,
    project,
    event: dict[str, Any],
    payload: dict[str, Any],
    target_types: list[str],
):
    task = create_review_task(
        db,
        project_id=project.id,
        trigger_type="GITLAB_MR_WEBHOOK",
        external_source_id=event["mrId"],
        external_url=event["externalUrl"],
        source_branch=event["sourceBranch"],
        target_branch=event["targetBranch"],
        commit_sha=event["commitSha"],
        before_sha=None,
        after_sha=None,
        author_name=event["authorName"],
        author_username=event["authorUsername"],
        template_code="general-default",
        target_type=None,
        target_types=target_types,
        code_quality_profile_code=None,
    )
    now = datetime.now()
    db.add(
        GitLabMergeRequestEvent(
            task_id=task.id,
            git_project_id=event["gitProjectId"],
            project_name=event["projectName"],
            mr_id=event["mrId"],
            event_action=event["eventAction"],
            event_time=event["eventTime"],
            source_branch=event["sourceBranch"],
            target_branch=event["targetBranch"],
            author_name=event["authorName"],
            author_username=event["authorUsername"],
            changed_files_summary=json.dumps(event["changedFilesSummary"], ensure_ascii=False),
            raw_payload=json.dumps(payload, ensure_ascii=False),
            created_at=now,
            updated_at=now,
        )
    )
    mark_task_failed(task, _ambiguous_target_message(target_types))
    return task


def _create_failed_push_task_for_ambiguous_targets(
    db: Session,
    project,
    event: dict[str, Any],
    payload: dict[str, Any],
    target_types: list[str],
):
    task = create_review_task(
        db,
        project_id=project.id,
        trigger_type="GITLAB_PUSH_WEBHOOK",
        external_source_id=event["afterSha"],
        external_url=event["externalUrl"],
        source_branch=event["branchName"],
        target_branch=None,
        commit_sha=event["afterSha"],
        before_sha=event["beforeSha"],
        after_sha=event["afterSha"],
        author_name=event["authorName"],
        author_username=event["authorUsername"],
        template_code="general-default",
        target_type=None,
        target_types=target_types,
        code_quality_profile_code=None,
    )
    now = datetime.now()
    db.add(
        GitLabPushEvent(
            task_id=task.id,
            git_project_id=event["gitProjectId"],
            project_name=event["projectName"],
            ref=event["ref"],
            branch_name=event["branchName"],
            before_sha=event["beforeSha"],
            after_sha=event["afterSha"],
            event_time=event["eventTime"],
            author_name=event["authorName"],
            author_username=event["authorUsername"],
            changed_files_summary=json.dumps(event["changedFilesSummary"], ensure_ascii=False),
            raw_payload=json.dumps(payload, ensure_ascii=False),
            created_at=now,
            updated_at=now,
        )
    )
    mark_task_failed(task, _ambiguous_target_message(target_types))
    return task


def _mark_existing_task_failed_for_ambiguous_targets(task, target_types: list[str]) -> None:
    task.target_type = None
    task.target_types_json = json.dumps(target_types, ensure_ascii=False)
    task.code_quality_profile_code = None
    mark_task_failed(task, _ambiguous_target_message(target_types))


def _process_task(
    db: Session,
    task,
    changed_files: list[dict[str, Any]],
    diff_text: str | None,
) -> dict:
    project = task_project(db, task.project_id)
    target_config = resolve_project_target_config(db, project, changed_files)
    task.target_type = target_config["targetType"]
    task.target_types_json = json.dumps(target_config["targetTypes"], ensure_ascii=False)
    task.template_code = target_config["templateCode"]
    task.code_quality_profile_code = target_config["profileCode"]
    template = get_enabled_template(db, task.template_code)
    rule_codes = template.get("focusRuleCodes") or template.get("enabledRuleCodes", [])
    analysis = analyze_changes(changed_files, diff_text)
    risk_card = generate_risk_card(
        analysis,
        rule_codes,
        template.get("recommendedChecks", []),
    )
    result = save_review_result(
        db,
        task=task,
        analysis=analysis,
        risk_card=risk_card,
        reminder_card_enabled=target_config["reminderCardEnabled"],
    )
    mark_task_success(task, risk_card["riskLevel"])
    notification_context = {
        "title": f"{task.trigger_type} {task.external_source_id or ''}".strip(),
        "projectName": project.name,
        "triggerType": task.trigger_type,
        "authorName": task.author_name,
        "authorUsername": task.author_username,
        "sourceBranch": task.source_branch,
        "targetBranch": task.target_branch,
    }
    ai_review_scheduled = trigger_auto_review(
        db,
        task_id=task.id,
        project=project,
        changed_files=changed_files,
        diff_text=diff_text,
        rule_result_id=result.id,
        risk_card=risk_card,
        focus_change_types=template.get("focusChangeTypes", []),
        focus_rule_codes=template.get("focusRuleCodes", []),
        notification_context=notification_context,
        reminder_card_enabled=target_config["reminderCardEnabled"],
    )
    if not ai_review_scheduled:
        settings = get_settings_record(db)
        if task.trigger_type == "GITLAB_PUSH_WEBHOOK":
            notification = send_review_summary(
                db,
                task.id,
                risk_card,
                template.get("focusChangeTypes", []),
                None,
                notification_context,
                settings.dingtalk_notification_enabled,
                focus_rule_codes=template.get("focusRuleCodes", []),
                reminder_card_enabled=target_config["reminderCardEnabled"],
            )
        else:
            notification = send_risk_card(
                db,
                task.id,
                risk_card,
                template.get("focusChangeTypes", []),
                notification_context,
                settings.dingtalk_notification_enabled,
                focus_rule_codes=template.get("focusRuleCodes", []),
                reminder_card_enabled=target_config["reminderCardEnabled"],
            )
        save_notification_records(
            db,
            task_id=task.id,
            result_id=result.id,
            notifications=notification["records"],
        )
    return {"analysis": analysis, "riskCard": risk_card, "resultId": result.id}


def task_project(db: Session, project_id: int):
    from app.project_integration.repository import find_project_by_id

    project = find_project_by_id(db, project_id)
    if project is None:
        raise AppError("RESOURCE_NOT_FOUND", f"Project not found: {project_id}", 404)
    return project


def _validate_mr_payload(payload: dict[str, Any]) -> None:
    if _text(payload, "object_kind") != "merge_request":
        raise AppError("BAD_REQUEST", "object_kind must be merge_request", 400)
    if not (_nested(payload, "project", "id") or _nested(payload, "object_attributes", "target_project_id")):
        raise AppError("BAD_REQUEST", "GitLab project id is required", 400)
    if not (_nested(payload, "object_attributes", "iid") or _nested(payload, "object_attributes", "id")):
        raise AppError("BAD_REQUEST", "Merge request id is required", 400)


def _parse_mr_event(payload: dict[str, Any]) -> dict:
    project = payload.get("project") or {}
    attrs = payload.get("object_attributes") or {}
    git_project_id = str(project.get("id") or attrs.get("target_project_id"))
    project_name = project.get("name") or project.get("path_with_namespace") or f"gitlab-project-{git_project_id}"
    return {
        "gitProjectId": git_project_id,
        "projectName": project_name,
        "repositoryUrl": _normalize_gitlab_web_url(
            project.get("web_url") or (payload.get("repository") or {}).get("homepage")
        ),
        "mrId": str(attrs.get("iid") or attrs.get("id")),
        "eventAction": attrs.get("action"),
        "eventTime": _parse_time(attrs.get("updated_at") or attrs.get("created_at") or payload.get("event_time")),
        "externalUrl": _normalize_gitlab_web_url(attrs.get("url")),
        "sourceBranch": attrs.get("source_branch"),
        "targetBranch": attrs.get("target_branch"),
        "commitSha": ((attrs.get("last_commit") or {}).get("id") or (attrs.get("last_commit") or {}).get("sha") or payload.get("checkout_sha")),
        "authorName": _nested(payload, "user", "name") or payload.get("user_username") or _nested(attrs, "author", "name"),
        "authorUsername": _nested(payload, "user", "username") or payload.get("user_username") or _nested(attrs, "author", "username"),
        "changedFilesSummary": _build_changed_files_summary(payload),
        "rawPayload": payload,
    }


def _enrich_mr_detail(event: dict[str, Any]) -> dict[str, Any]:
    if event["changedFilesSummary"].get("source") == "payload":
        return event
    try:
        project_detail = gitlab_client.get_project_detail(event["gitProjectId"])
        mr_detail = gitlab_client.get_merge_request_detail(event["gitProjectId"], event["mrId"])
    except AppError:
        return event
    enriched = dict(event)
    enriched["projectName"] = (
        project_detail.get("pathWithNamespace")
        or project_detail.get("name")
        or event["projectName"]
    )
    enriched["repositoryUrl"] = _normalize_gitlab_web_url(project_detail.get("webUrl")) or event["repositoryUrl"]
    enriched["mrId"] = mr_detail.get("iid") or event["mrId"]
    enriched["externalUrl"] = _normalize_gitlab_web_url(mr_detail.get("webUrl")) or event["externalUrl"]
    enriched["sourceBranch"] = mr_detail.get("sourceBranch") or event["sourceBranch"]
    enriched["targetBranch"] = mr_detail.get("targetBranch") or event["targetBranch"]
    enriched["commitSha"] = mr_detail.get("commitSha") or event["commitSha"]
    enriched["authorName"] = mr_detail.get("authorName") or event["authorName"]
    enriched["authorUsername"] = mr_detail.get("authorUsername") or event["authorUsername"]
    return enriched


def _parse_push_event(
    payload: dict[str, Any],
    git_project_id: str,
    project_name: str,
    repository_url: str | None,
) -> dict[str, Any]:
    after_sha = payload.get("after")
    if not after_sha:
        raise AppError("BAD_REQUEST", "GitLab push after sha is required", 400)
    ref = payload.get("ref")
    branch_name = _branch_name(ref)
    return {
        "gitProjectId": git_project_id,
        "projectName": project_name,
        "repositoryUrl": _normalize_gitlab_web_url(repository_url),
        "ref": ref,
        "branchName": branch_name,
        "beforeSha": payload.get("before"),
        "afterSha": after_sha,
        "eventTime": _parse_time(payload.get("event_time") or _nested(payload, "head_commit", "timestamp")),
        "externalUrl": _build_commit_url(_normalize_gitlab_web_url(repository_url), after_sha),
        "authorName": payload.get("user_name") or _nested(payload, "user", "name") or _nested(payload, "commits", 0, "author", "name"),
        "authorUsername": payload.get("user_username") or _nested(payload, "user", "username") or payload.get("user_email"),
        "changedFilesSummary": _build_push_changed_files_summary(payload),
        "rawPayload": payload,
    }


def _push_webhook_branch_gate(db: Session, project_record, branch_name: str | None) -> dict[str, Any]:
    patterns = get_project_group_push_policy(db, project_record)["pushBranchPatterns"]
    return {
        "allowed": _branch_matches(branch_name, patterns),
        "profileCode": resolve_project_review_profile_code(db, project_record, None),
        "patterns": patterns,
    }


def _is_opened_mr(event: dict) -> bool:
    action = event.get("eventAction")
    if action and str(action).lower() in {"close", "closed", "merge", "merged", "destroy"}:
        return False
    state = _nested(event["rawPayload"], "object_attributes", "state") or _nested(
        event["rawPayload"], "object_attributes", "state_name"
    )
    if state:
        return str(state).lower() in {"opened", "open"}
    if not action:
        return True
    return True


def _build_changed_files_summary(payload: dict[str, Any]) -> dict:
    changed_files = (
        payload.get("changedFiles")
        or payload.get("changed_files")
        or _nested(payload, "object_attributes", "changed_files")
        or _nested(payload, "changes", "changed_files", "current")
    )
    files = [_normalize_changed_file(file_node) for file_node in changed_files] if isinstance(changed_files, list) else []
    return {"count": len(files), "source": "payload" if changed_files is not None else "not_provided", "files": files}


def _build_push_changed_files_summary(payload: dict[str, Any]) -> dict:
    changed_files = payload.get("changedFiles") or payload.get("changed_files")
    if isinstance(changed_files, list):
        files = [_normalize_changed_file(file_node) for file_node in changed_files]
        for file in files:
            file["source"] = "payload"
            file["commitCount"] = len(payload.get("commits") or [])
        return {
            "count": len(files),
            "source": "payload",
            "commitCount": len(payload.get("commits") or []),
            "ref": payload.get("ref"),
            "beforeSha": payload.get("before"),
            "afterSha": payload.get("after"),
            "files": files,
        }
    files_by_path: dict[str, dict[str, Any]] = {}
    commits = payload.get("commits")
    if isinstance(commits, list):
        for commit in commits:
            if not isinstance(commit, dict):
                continue
            _add_commit_files(files_by_path, commit.get("added"), "ADDED")
            _add_commit_files(files_by_path, commit.get("modified"), "MODIFIED")
            _add_commit_files(files_by_path, commit.get("removed"), "DELETED")
    for file in files_by_path.values():
        file["source"] = "push_payload"
        file["commitCount"] = len(commits) if isinstance(commits, list) else 0
    return {
        "count": len(files_by_path),
        "source": "push_payload",
        "commitCount": len(commits) if isinstance(commits, list) else 0,
        "ref": payload.get("ref"),
        "beforeSha": payload.get("before"),
        "afterSha": payload.get("after"),
        "files": list(files_by_path.values()),
    }


def _build_gitlab_changed_files_summary(diff_files: list[dict[str, Any]], source: str) -> dict:
    files = [_normalize_gitlab_diff_file(diff_file) for diff_file in diff_files]
    for file in files:
        file["source"] = source
    return {"count": len(files), "source": source, "files": files}


def _normalize_gitlab_diff_file(diff_file: dict[str, Any]) -> dict:
    path = diff_file.get("newPath") or diff_file.get("oldPath") or diff_file.get("path")
    return {
        "path": path,
        "oldPath": diff_file.get("oldPath"),
        "newPath": diff_file.get("newPath"),
        "changeType": diff_file.get("changeType") or "MODIFIED",
        "diffText": diff_file.get("diffText"),
        "collapsed": bool(diff_file.get("collapsed")),
        "tooLarge": bool(diff_file.get("tooLarge")),
    }


def _normalize_changed_file(file_node: Any) -> dict:
    if isinstance(file_node, str):
        return {"path": file_node, "oldPath": file_node, "newPath": file_node, "changeType": "UNKNOWN"}
    old_path = file_node.get("old_path") or file_node.get("oldPath") or file_node.get("path")
    new_path = file_node.get("new_path") or file_node.get("newPath") or file_node.get("path") or file_node.get("filePath")
    path = new_path or old_path
    result = {
        "path": path,
        "oldPath": old_path,
        "newPath": new_path,
        "changeType": _infer_change_type(file_node),
    }
    diff_text = file_node.get("diffText") or file_node.get("diff") or file_node.get("patch")
    if diff_text:
        result["diffText"] = diff_text
    return result


def _infer_change_type(file_node: dict) -> str:
    if file_node.get("new_file") or file_node.get("newFile"):
        return "ADDED"
    if file_node.get("deleted_file") or file_node.get("deletedFile"):
        return "DELETED"
    if file_node.get("renamed_file") or file_node.get("renamedFile"):
        return "RENAMED"
    return str(file_node.get("changeType") or file_node.get("change_type") or file_node.get("status") or "MODIFIED").upper()


def _add_commit_files(files_by_path: dict[str, dict[str, Any]], file_paths: Any, change_type: str) -> None:
    if not isinstance(file_paths, list):
        return
    for path in file_paths:
        if not path:
            continue
        files_by_path[str(path)] = {
            "path": str(path),
            "oldPath": None if change_type == "ADDED" else str(path),
            "newPath": None if change_type == "DELETED" else str(path),
            "changeType": change_type,
        }


def _parse_time(raw_value: str | None) -> datetime:
    if not raw_value:
        return datetime.now(timezone.utc).replace(tzinfo=None)
    try:
        return datetime.fromisoformat(raw_value.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return datetime.now(timezone.utc).replace(tzinfo=None)


def _text(payload: dict[str, Any], key: str) -> str | None:
    value = payload.get(key)
    return str(value) if value is not None else None


def _nested(payload: dict[str, Any], *keys: Any) -> Any:
    value: Any = payload
    for key in keys:
        if isinstance(value, dict):
            value = value.get(key)
        elif isinstance(value, list) and isinstance(key, int) and 0 <= key < len(value):
            value = value[key]
        else:
            return None
    return value


def _branch_name(ref: str | None) -> str | None:
    if not ref:
        return None
    prefix = "refs/heads/"
    return ref[len(prefix) :] if ref.startswith(prefix) else ref


def _branch_matches(branch_name: str | None, patterns: list[str]) -> bool:
    if not patterns:
        return True
    if not branch_name:
        return False
    return any(fnmatchcase(branch_name, pattern) for pattern in patterns)


def _build_commit_url(repository_url: str | None, after_sha: str | None) -> str | None:
    if not repository_url or not after_sha:
        return repository_url
    return repository_url.rstrip("/") + "/-/commit/" + after_sha


def _normalize_gitlab_web_url(url: str | None) -> str | None:
    if not url:
        return url
    settings = get_settings()
    base_url = settings.gitlab_base_url.strip()
    if not base_url:
        return url
    parsed_url = urlparse(str(url))
    parsed_base = urlparse(base_url)
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
        return url
    if parsed_base.scheme not in {"http", "https"} or not parsed_base.netloc:
        return url
    return urlunparse(
        parsed_url._replace(
            scheme=parsed_base.scheme,
            netloc=parsed_base.netloc,
        )
    )
