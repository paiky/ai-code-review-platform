from datetime import datetime, timedelta
import json
import logging
import re
import shutil
from uuid import uuid4

from sqlalchemy import inspect, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auto_fix import comparison, config, patching
from app.auto_fix.gitlab import GitLab, RemoteError, full_sha, prepare_repo
from app.auto_fix.models import AutoFixSettings, FixRound, FixRun
from app.code_quality.models import CodeQualityReviewResult, CodeQualityReviewSettings, CodeQualitySchedulerJob
from app.code_quality.repository import get_provider, get_settings_record, settings_to_dict
from app.core.database import SessionLocal
from app.core.errors import AppError
from app.notification.service import _task_detail_url
from app.project_integration.models import Project
from app.project_integration.repository import project_auto_fix_enabled
from app.review_record.models import ReviewTask


LOG = logging.getLogger(__name__)
MAX_ROUNDS = 3
WORK_STATUSES = ("QUEUED", "RUNNING")
TRACKED_STATUSES = (*WORK_STATUSES, "AWAITING_APPROVAL", "STALE")
REVIEW_TIMEOUT = timedelta(minutes=60)
LEASE_DURATION = timedelta(minutes=60)
RETRY_SECONDS = (10, 30)


def schema_ready(db: Session) -> bool:
    inspector = inspect(db.connection())
    return all(inspector.has_table(model.__tablename__) for model in (AutoFixSettings, FixRun, FixRound))


def critical_findings(findings: list[dict]) -> list[dict]:
    return [finding for finding in findings if finding.get("severity") == "CRITICAL"]


def branch_name(run: FixRun) -> str:
    return f"ai-fix/{run.id}"


def _findings(raw: str | None) -> list[dict]:
    entries = json.loads(raw or "[]")
    return [item for item in entries if isinstance(item, dict)]


def _compact_finding(finding: dict) -> dict:
    return {
        key: finding[key] for key in (
            "title", "filePath", "startLine", "endLine", "severity", "category",
            "body", "suggestion", "confidence", "contextStatus", "evidence",
        ) if key in finding
    }


def record_review_candidate(db: Session, saved: CodeQualityReviewResult) -> None:
    if saved.status != "SUCCESS" or not config.configured():
        return
    task = db.get(ReviewTask, saved.task_id)
    if not task or task.trigger_type != "GITLAB_MR_WEBHOOK":
        return
    project = db.get(Project, task.project_id)
    if not project:
        return
    snapshot = json.loads(saved.review_snapshot_json or "{}")
    findings = _findings(saved.findings_json)
    if (
        snapshot.get("isPrimary") is not True or snapshot.get("complete") is not True
        or snapshot.get("trustedIngress") is not True
        or not critical_findings(findings) or not snapshot.get("executionId") or not snapshot.get("hunkDigest")
        or saved.effective_engine not in {"AGENT", "STANDARD"}
        or not full_sha(snapshot.get("baseSha")) or not full_sha(snapshot.get("headSha"))
        or task.before_sha != snapshot["baseSha"]
        or (task.after_sha or task.commit_sha) != snapshot["headSha"]
        or not task.source_branch or task.source_branch.startswith("ai-fix/")
        or not task.external_source_id or not re.fullmatch(r"[0-9]{1,32}", task.external_source_id)
        or not schema_ready(db)
    ):
        return
    settings = db.get(AutoFixSettings, 1)
    review_settings = db.get(CodeQualityReviewSettings, 1)
    if (
        not settings or not settings.enabled or settings.enabled_at is None
        or not review_settings or not review_settings.review_enabled
        or not project_auto_fix_enabled(db, project.id)
    ):
        return
    now = datetime.now()
    source = {
        "reviewKey": saved.review_key, "profileCode": saved.profile_code,
        "provider": saved.provider, "model": saved.model, "effectiveEngine": saved.effective_engine,
        "displayName": saved.display_name, "sortOrder": saved.sort_order, "reviewSnapshot": snapshot,
    }
    attributes = {
        "project_id": project.id, "source_task_id": task.id, "source_mr_iid": task.external_source_id,
        "source_review_key": saved.review_key, "source_review_version": snapshot["executionId"],
        "inputs_json": json.dumps({
            "review": source,
            "fixProvider": config.provider_code(settings_to_dict(review_settings)["defaultProviderCode"]),
            "findings": [_compact_finding(finding) for finding in findings],
        }, ensure_ascii=False),
        "enabled_at": settings.enabled_at, "base_sha": snapshot["baseSha"],
        "developer_sha": snapshot["headSha"], "developer_branch": task.source_branch,
        "status": "QUEUED", "step": "PREPARING", "next_at": now, "created_at": now, "updated_at": now,
    }
    if _same_source(db, attributes, lock=False):
        return
    try:
        with db.begin_nested():
            db.add(FixRun(**attributes, active_slot=1))
            db.flush()
    except IntegrityError:
        if _same_source(db, attributes):
            return
        attributes.update(status="STOPPED", step=None, reason_code="BRANCH_BUSY", reason="开发分支已有自动修复任务")
        try:
            with db.begin_nested():
                db.add(FixRun(**attributes))
                db.flush()
        except IntegrityError:
            if not _same_source(db, attributes):
                raise


def _same_source(db: Session, attributes: dict, *, lock: bool = True) -> bool:
    query = select(FixRun.id).where(
        FixRun.project_id == attributes["project_id"],
        FixRun.source_mr_iid == attributes["source_mr_iid"],
        FixRun.developer_sha == attributes["developer_sha"],
    )
    return db.scalar(query.with_for_update() if lock else query) is not None


def rounds_for(db: Session, run: FixRun) -> list[FixRound]:
    return list(db.scalars(select(FixRound).where(FixRound.run_id == run.id).order_by(FixRound.number)))


def is_managed_ref(db: Session, git_project_id: str, branch: str | None, *shas: str | None) -> bool:
    match = re.fullmatch(r"ai-fix/([1-9][0-9]{0,18})", branch or "")
    commits = [sha for sha in shas if full_sha(sha)]
    if not match or not commits or not schema_ready(db):
        return False
    return db.scalar(
        select(FixRun.id)
        .join(Project, Project.id == FixRun.project_id)
        .join(FixRound, FixRound.run_id == FixRun.id)
        .where(
            FixRun.id == int(match[1]), Project.git_project_id == git_project_id,
            FixRound.commit_sha.in_(commits),
        ).limit(1)
    ) is not None


def _claim(db: Session) -> tuple[int, str] | None:
    now = datetime.now()
    available = or_(FixRun.lease_until.is_(None), FixRun.lease_until <= now)
    selection = select(FixRun.id).where(
        FixRun.status.in_(TRACKED_STATUSES), FixRun.next_at <= now, available,
    ).order_by(FixRun.next_at, FixRun.id).limit(1)
    run_id = db.scalar(selection)
    if run_id is None:
        return None
    token = str(uuid4())
    matched = db.execute(update(FixRun).where(
        FixRun.id == run_id, FixRun.status.in_(TRACKED_STATUSES), FixRun.next_at <= now, available,
    ).values(lease_token=token, lease_until=now + LEASE_DURATION))
    db.commit()
    return (run_id, token) if matched.rowcount == 1 else None


def sweep() -> None:
    with SessionLocal() as db:
        if not schema_ready(db):
            return
        claim = _claim(db)
    if claim is None:
        return
    run_id, token = claim
    with SessionLocal() as db:
        run = db.get(FixRun, run_id)
        if not run or run.lease_token != token:
            return
        try:
            _advance(db, run, token)
        except (RemoteError, patching.PatchError) as error:
            db.rollback()
            run = _owned(db, run_id, token, strict=False)
            if run:
                _record_failure(run, error)
        except Exception as error:
            LOG.error("Auto-fix step failed for run %s (%s)", run_id, type(error).__name__)
            db.rollback()
            run = _owned(db, run_id, token, strict=False)
            if run:
                _record_failure(run, RemoteError("INTERNAL_ERROR", "自动修复步骤执行失败"))
        finally:
            run = _owned(db, run_id, token, strict=False)
            if run:
                run.lease_token = None
                run.lease_until = None
                run.updated_at = datetime.now()
                db.commit()
                _cleanup_if_finished(run)


def _owned(db: Session, run_id: int, token: str, *, strict: bool = True) -> FixRun | None:
    locked = db.execute(
        select(FixRun.lease_token, FixRun.cancel_requested_at).where(FixRun.id == run_id).with_for_update(),
    ).one_or_none()
    if locked is None or locked.lease_token != token:
        if strict:
            raise RemoteError("LEASE_LOST", "自动修复任务已由其它执行器接手")
        return None
    run = db.get(FixRun, run_id)
    run.cancel_requested_at = locked.cancel_requested_at
    return run


def _record_failure(run: FixRun, error: RemoteError | patching.PatchError) -> None:
    if run.status == "AWAITING_APPROVAL" and error.code == "GITLAB_POLICY_CHANGED":
        _finish(run, "STALE", error.code, str(error))
        return
    if run.status in {"AWAITING_APPROVAL", "STALE"}:
        run.reason_code, run.reason = error.code, str(error)
        _schedule(run, 60)
    elif getattr(error, "retryable", False) and run.failures < len(RETRY_SECONDS):
        seconds = RETRY_SECONDS[run.failures]
        run.failures += 1
        run.next_at = datetime.now() + timedelta(seconds=seconds)
        run.reason_code, run.reason = error.code, str(error)
    else:
        _finish(run, "STALE" if error.code == "BRANCH_CHANGED" else "STOPPED", error.code, str(error))


def _schedule(run: FixRun, seconds: int = 0) -> None:
    run.next_at = datetime.now() + timedelta(seconds=seconds)
    run.failures = 0


def _finish(run: FixRun, status: str, code: str | None = None, reason: str | None = None) -> None:
    run.status, run.reason_code, run.reason = status, code, reason
    run.step = None
    run.active_slot = None
    _schedule(run, 60 if run.mr_iid else 0)


def _cleanup_if_finished(run: FixRun) -> None:
    if run.status in WORK_STATUSES or not config.configured():
        return
    repo = config.workspace_root() / f"fix-{run.id}.git"
    if repo.is_dir() and not repo.is_symlink() and repo.resolve() == repo and (repo / "HEAD").is_file():
        shutil.rmtree(repo, ignore_errors=True)


def _write_allowed(db: Session, run: FixRun) -> bool:
    settings = db.get(AutoFixSettings, 1, populate_existing=True, with_for_update=True)
    return bool(
        config.configured()
        and settings and settings.enabled and settings.enabled_at == run.enabled_at
        and get_settings_record(db).review_enabled
    )


def _verify_write(db: Session, run: FixRun, token: str) -> bool:
    run = _owned(db, run.id, token)
    if run.cancel_requested_at is not None:
        _finish(run, "CANCELLED", "USER_CANCELLED", "自动修复已取消")
        return False
    if not _write_allowed(db, run):
        _finish(run, "STOPPED", "AUTO_FIX_DISABLED", "自动修复或全局 AI Review 已关闭")
        return False
    if not project_auto_fix_enabled(db, run.project_id, for_update=True):
        _finish(run, "STOPPED", "PROJECT_AUTO_FIX_DISABLED", "项目自动修复开关已关闭")
        return False
    run.lease_until = datetime.now() + LEASE_DURATION
    return True


def _advance(db: Session, run: FixRun, token: str) -> None:
    project = db.get(Project, run.project_id)
    if project is None:
        _finish(run, "STOPPED", "PROJECT_NOT_AUTHORIZED", "项目未授权自动修复")
        return
    rounds = rounds_for(db, run)
    current = rounds[-1] if rounds else None
    remote = GitLab(project.git_project_id)
    if run.status not in WORK_STATUSES:
        if run.mr_iid:
            _track_mr(db, run, current, remote)
        else:
            run.next_at = datetime.max.replace(year=2099)
        return
    if not _verify_write(db, run, token):
        _reconcile_cancelled_write(db, run, current, remote)
        return
    db.commit()
    run.status = "RUNNING"
    run.reason_code = run.reason = None
    if run.step == "PREPARING" or run.step == "GENERATING_PATCH":
        _generate_round(db, run, current, remote, token)
    elif run.step == "PUSHING":
        _push_round(db, run, current, remote, token)
    elif run.step in {"REVIEW_QUEUED", "REVIEWING"}:
        _review_round(db, run, current, remote)
    elif run.step == "CREATING_MR":
        _publish_mr(db, run, current, remote, token)


def _reconcile_cancelled_write(db: Session, run: FixRun, current: FixRound | None, remote: GitLab) -> None:
    try:
        if current and current.commit_sha and not current.pushed:
            current.pushed = remote.branch_sha(branch_name(run)) == current.commit_sha
        if current and current.critical_count == 0 and not run.mr_iid:
            mr = remote.find_fix_mr(run.id, branch_name(run), run.developer_branch)
            if mr:
                run.mr_iid = str(mr["iid"])
                run.mr_url = remote.trusted_url(mr["web_url"])
                run.status = "STALE"
                run.notification_json = json.dumps({"status": "SKIPPED"})
                _schedule(run, 60)
    except RemoteError:
        LOG.info("Auto-fix cancellation reconciliation could not verify run %s", run.id)
        run.reason = "修复已停止，最后一次 GitLab 写入结果待核对"
    db.flush()


def _previous(db: Session, run: FixRun, number: int) -> tuple[str, list[dict]]:
    if number == 1:
        return run.developer_sha, json.loads(run.inputs_json)["findings"]
    previous = db.get(FixRound, (run.id, number - 1))
    return previous.commit_sha, _findings(_result(db, previous).findings_json)


def _result(db: Session, round_: FixRound) -> CodeQualityReviewResult | None:
    return db.scalar(select(CodeQualityReviewResult).where(
        CodeQualityReviewResult.task_id == round_.review_task_id,
        CodeQualityReviewResult.review_key == round_.review_key,
    ).execution_options(populate_existing=True))


def _repository(run: FixRun, remote: GitLab, *shas: str):
    project = remote.project()
    run.project_url = project["web_url"]
    repo = prepare_repo(config.workspace_root(), run.id)
    remote.fetch(repo, project["http_url_to_repo"], *dict.fromkeys(shas))
    return repo, project["http_url_to_repo"]


def _generate_round(db: Session, run: FixRun, current: FixRound | None, remote: GitLab, token: str) -> None:
    from app.code_quality.service import review_hunk_digest

    remote.verify_original(run.source_mr_iid, run.developer_branch, run.developer_sha)
    number = 1 if current is None else current.number + (current.finished_at is not None)
    input_sha, previous = _previous(db, run, number)
    inputs = json.loads(run.inputs_json)
    repo, _ = _repository(run, remote, run.base_sha, run.developer_sha, input_sha)
    original = patching.verified_review_diff(repo, run.base_sha, run.developer_sha)
    changed = original["changedFiles"]
    snapshot = inputs["review"]["reviewSnapshot"]
    if (
        {file["path"] for file in changed} != set(snapshot.get("changedPaths") or [])
        or not snapshot.get("hunkDigest")
        or review_hunk_digest(changed) != snapshot.get("hunkDigest")
    ):
        raise RemoteError("REVIEW_SNAPSHOT_INVALID", "实际提交的完整差异与原 Review 不一致")
    allowed = {file["path"] for file in changed if not file["deletedFile"]}
    critical = critical_findings(previous)
    if len(critical) > 12:
        raise RemoteError("PATCH_SCOPE_TOO_LARGE", "紧急风险数超出单轮可处理范围")
    if not critical or any(
        finding.get("filePath") not in allowed or not patching.is_repair_source_path(finding["filePath"])
        for finding in critical
    ):
        raise RemoteError("PATCH_SCOPE_UNSUPPORTED", "存在无法定位到可修复文件的紧急风险")
    round_ = current if current is not None and current.number == number else FixRound(
        run_id=run.id, number=number, input_sha=input_sha, created_at=datetime.now(),
    )
    db.add(round_)
    run.step = "GENERATING_PATCH"
    db.commit()
    default_provider = settings_to_dict(get_settings_record(db))["defaultProviderCode"]
    if inputs["fixProvider"] != config.provider_code(default_provider):
        raise RemoteError("FIX_PROVIDER_CHANGED", "自动修复模型配置已变更")
    provider = get_provider(db, inputs["fixProvider"])
    if not provider.enabled:
        raise RemoteError("FIX_PROVIDER_DISABLED", "自动修复模型已停用")
    patches = []
    for finding in critical:
        if not _verify_write(db, run, token):
            return
        db.commit()
        patches.append(patching.generate_finding_patch(
            db, run.source_task_id, provider, repo, run.base_sha, input_sha, finding, allowed,
        ))
    if not _verify_write(db, run, token):
        return
    db.commit()
    candidate = patching.create_candidate_commit(repo, input_sha, allowed, patches, message=f"Fix urgent review findings (run {run.id}, round {number})")
    round_.commit_sha = candidate
    run.step = "PUSHING"
    _schedule(run)


def _push_round(db: Session, run: FixRun, round_: FixRound, remote: GitLab, token: str) -> None:
    remote.verify_original(run.source_mr_iid, run.developer_branch, run.developer_sha)
    existing = remote.branch_sha(branch_name(run))
    if existing != round_.commit_sha:
        expected = None if round_.number == 1 else round_.input_sha
        if existing != expected:
            raise RemoteError("BRANCH_CHANGED", "修复分支提交已发生变化")
        repo, git_url = _repository(run, remote, run.base_sha, round_.input_sha)
        if not _verify_write(db, run, token):
            return
        db.commit()
        remote.push(repo, git_url, branch_name(run), round_.commit_sha, expected, round_.input_sha)
        if remote.branch_sha(branch_name(run)) != round_.commit_sha:
            raise RemoteError("PUSH_UNCONFIRMED", "暂时无法确认修复分支写入结果", retryable=True)
    round_.pushed = True
    run.step = "REVIEW_QUEUED"
    _schedule(run)


def _review_round(db: Session, run: FixRun, round_: FixRound, remote: GitLab) -> None:
    from app.code_quality.service import dispatch_auto_fix_review

    inputs = json.loads(run.inputs_json)["review"]
    if round_.review_task_id is None:
        source = db.get(ReviewTask, run.source_task_id)
        task = ReviewTask(
            project_id=run.project_id, trigger_type="AUTO_FIX_REVIEW", source_branch=branch_name(run),
            target_branch=run.developer_branch, before_sha=run.base_sha, after_sha=round_.commit_sha,
            commit_sha=round_.commit_sha, template_code=source.template_code, target_type=source.target_type,
            target_types_json=source.target_types_json, code_quality_profile_code=inputs["profileCode"],
            status="PENDING", review_status="REVIEWING", created_at=datetime.now(), updated_at=datetime.now(),
        )
        db.add(task)
        db.flush()
        round_.review_task_id, round_.review_key = task.id, inputs["reviewKey"]
        db.commit()
    result = _result(db, round_)
    if result is None:
        repo, _ = _repository(run, remote, run.base_sha, round_.commit_sha)
        canonical = patching.verified_review_diff(repo, run.base_sha, round_.commit_sha)
        try:
            dispatch_auto_fix_review(
                db, task_id=round_.review_task_id, source=inputs,
                diff_text=canonical["diffText"], changed_files=canonical["changedFiles"],
            )
        except AppError as error:
            raise RemoteError(error.code, str(error)) from error
        _schedule(run, 5)
        return
    if result.status in {"QUEUED", "RUNNING"}:
        job = db.scalar(select(CodeQualitySchedulerJob).where(
            CodeQualitySchedulerJob.task_id == round_.review_task_id,
            CodeQualitySchedulerJob.review_key == round_.review_key,
            CodeQualitySchedulerJob.job_type.in_(("AI_REVIEW", "AGENT_REVIEW")),
        ).order_by(CodeQualitySchedulerJob.id.desc()).limit(1))
        since = (job.queued_at if job else None) or result.created_at or round_.created_at
        if job and job.status in {"FAILED", "SKIPPED", "CANCELLED"}:
            raise RemoteError("REVIEW_INCOMPLETE", "复审队列已结束，本轮没有可用的正式结果")
        if datetime.now() - since >= REVIEW_TIMEOUT:
            raise RemoteError("REVIEW_TIMEOUT", "复审超时，已停止自动修复")
        run.step = "REVIEW_QUEUED" if (job.status if job else result.status) == "QUEUED" else "REVIEWING"
        _schedule(run, 5)
        return
    snapshot = json.loads(result.review_snapshot_json or "{}")
    current = _findings(result.findings_json)
    if (
        result.status != "SUCCESS" or snapshot.get("complete") is not True
        or snapshot.get("headSha") != round_.commit_sha or snapshot.get("baseSha") != run.base_sha
        or result.effective_engine != inputs["effectiveEngine"] or result.model != inputs["model"]
        or result.provider != inputs["provider"] or result.profile_code != inputs["profileCode"]
        or any(finding.get("severity") not in {"CRITICAL", "MAJOR", "MINOR"} for finding in current)
        or (result.overall_level == "CRITICAL" and not critical_findings(current))
    ):
        raise RemoteError("REVIEW_INCOMPLETE", "本轮缺少可作为判定依据的完整复审结果")
    _, previous = _previous(db, run, round_.number)
    repo, _ = _repository(run, remote, run.base_sha, round_.input_sha, round_.commit_sha)
    delta = patching.verified_review_diff(repo, round_.input_sha, round_.commit_sha)
    items = comparison.compare_findings(
        previous, current, {item["path"]: item["diffText"] for item in delta["changedFiles"]},
        complete=True, reviewed_paths=set(snapshot.get("changedPaths") or []),
    )
    count = len(critical_findings(current))
    round_.critical_count = count
    round_.review_version = snapshot.get("executionId")
    round_.findings_json = json.dumps(items, ensure_ascii=False)
    round_.finished_at = datetime.now()
    if count == 0:
        run.step = "CREATING_MR"
    elif round_.number >= MAX_ROUNDS:
        _finish(run, "STOPPED", "ROUND_LIMIT_REACHED", f"已完成 3 轮，仍有 {count} 项紧急风险")
    elif comparison.same_critical_findings(previous, current, items):
        _finish(run, "STOPPED", "NO_PROGRESS", "本轮复审仍发现同一批紧急风险")
    else:
        run.step = "GENERATING_PATCH"
    _schedule(run)


def _publish_mr(db: Session, run: FixRun, round_: FixRound, remote: GitLab, token: str) -> None:
    remote.project()
    remote.verify_original(run.source_mr_iid, run.developer_branch, run.developer_sha)
    if remote.branch_sha(branch_name(run)) != round_.commit_sha:
        raise RemoteError("BRANCH_CHANGED", "修复分支已更新，复审结论已过期")
    if not _verify_write(db, run, token):
        return
    db.commit()
    description = (
        f"原 MR !{run.source_mr_iid} · 修复任务 #{run.id}\n\n"
        f"开发分支提交：`{run.developer_sha}`\n\n"
        f"最终复审提交：`{round_.commit_sha}`\n\n"
        f"[最终复审]({_task_detail_url(round_.review_task_id, review_key=round_.review_key)})"
    )
    mr = remote.create_fix_mr(run.id, branch_name(run), run.developer_branch, description)
    run.mr_iid, run.mr_url = str(mr["iid"]), remote.trusted_url(mr["web_url"])
    run.status, run.step = "AWAITING_APPROVAL", None
    run.notification_json = json.dumps({"status": "PENDING"})
    if mr.get("state") in {"merged", "closed"}:
        _track_mr(db, run, round_, remote)
    _schedule(run)


def _track_mr(db: Session, run: FixRun, round_: FixRound, remote: GitLab) -> None:
    from app.auto_fix.notify import send_if_pending, skip_if_pending

    mr = remote.merge_request(run.mr_iid)
    if (
        str(mr.get("source_project_id")) != remote.project_id
        or str(mr.get("target_project_id")) != remote.project_id
        or mr.get("source_branch") != branch_name(run)
        or mr.get("target_branch") != run.developer_branch
    ):
        _finish(run, "STALE", "FIX_MR_CHANGED", "修复 MR 的来源或目标分支已变化")
        skip_if_pending(run)
        return
    if mr.get("state") == "merged":
        run.merge_sha = mr.get("merge_commit_sha")
        merged_at = mr.get("merged_at")
        if merged_at:
            run.merged_at = datetime.fromisoformat(merged_at.replace("Z", "+00:00")).replace(tzinfo=None)
        if not full_sha(run.merge_sha):
            _finish(run, "MERGED", "MERGE_SHA_UNVERIFIED", "GitLab 已合并，实际合入提交无法核对")
        elif round_ is None or run.merge_sha != round_.commit_sha:
            _finish(run, "MERGED", "MERGE_SHA_MISMATCH", "实际合并提交与通过复审的提交不同")
        else:
            _finish(run, "MERGED")
    elif mr.get("state") == "closed":
        _finish(run, "MR_CLOSED")
    elif run.status == "AWAITING_APPROVAL":
        remote.project()
        if remote.branch_sha(run.developer_branch) != run.developer_sha or remote.branch_sha(branch_name(run)) != round_.commit_sha:
            _finish(run, "STALE", "BRANCH_CHANGED", "分支已更新，复审结论已过期")
        else:
            run.reason_code = run.reason = None
            send_if_pending(db, run, round_)
    if run.status != "AWAITING_APPROVAL":
        skip_if_pending(run)
    _schedule(run, 60)
