from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.core.json_utils import page_response
from app.project_integration.models import Project


def project_to_dict(project: Project) -> dict:
    return {
        "id": project.id,
        "name": project.name,
        "gitProvider": project.git_provider,
        "gitProjectId": project.git_project_id,
        "repositoryUrl": project.repository_url,
        "defaultTemplateCode": project.default_template_code,
        "defaultCodeQualityProfileCode": project.default_code_quality_profile_code,
        "defaultCodeQualityProviderCode": project.default_code_quality_provider_code,
        "status": project.status,
    }


def list_enabled_projects(db: Session) -> dict:
    stmt: Select[tuple[Project]] = select(Project).where(Project.status == "ENABLED").order_by(Project.id.desc())
    items = [project_to_dict(project) for project in db.scalars(stmt).all()]
    total = db.scalar(select(func.count()).select_from(Project).where(Project.status == "ENABLED")) or 0
    return page_response(items, 1, len(items), total)


def find_project_by_id(db: Session, project_id: int) -> Project | None:
    return db.get(Project, project_id)


def find_project_by_git_project_id(db: Session, git_project_id: str) -> Project | None:
    return db.scalars(
        select(Project).where(Project.git_provider == "GITLAB", Project.git_project_id == git_project_id)
    ).first()


def upsert_gitlab_project(db: Session, git_project_id: str, project_name: str, repository_url: str | None) -> Project:
    project = find_project_by_git_project_id(db, git_project_id)
    if project:
        project.name = project_name
        project.repository_url = repository_url
        project.status = "ENABLED"
        db.flush()
        return project

    project = Project(
        name=project_name,
        git_provider="GITLAB",
        git_project_id=git_project_id,
        repository_url=repository_url,
        default_template_code="backend-default",
        default_code_quality_profile_code="backend-default-ai-review",
        default_code_quality_provider_code=None,
        dingtalk_webhook_id=None,
        status="ENABLED",
        description="Auto-created from GitLab webhook",
    )
    db.add(project)
    db.flush()
    return project
