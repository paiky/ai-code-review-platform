from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import create_app

# Import models so SQLAlchemy registers all stage-2 tables in Base.metadata.
from app.code_quality import models as code_quality_models  # noqa: F401
from app.deterministic_checks import models as deterministic_check_models  # noqa: F401
from app.evaluation import models as evaluation_models  # noqa: F401
from app.notification import models as notification_models  # noqa: F401
from app.project_integration import models as project_models  # noqa: F401
from app.project_review_policy import models as project_review_policy_models  # noqa: F401
from app.review_feedback import models as review_feedback_models  # noqa: F401
from app.review_record import models as review_models  # noqa: F401
from app.rule_template import models as rule_template_models  # noqa: F401


@pytest.fixture(autouse=True)
def isolate_external_integrations(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITLAB_API_ENABLED", "false")
    monkeypatch.delenv("GITLAB_BASE_URL", raising=False)
    monkeypatch.delenv("GITLAB_TOKEN", raising=False)
    monkeypatch.delenv("LOCAL_REPO_CONTEXT_ENABLED", raising=False)
    monkeypatch.delenv("LOCAL_REPO_WORKSPACE_ROOT", raising=False)
    monkeypatch.delenv("LOCAL_REPO_MAX_FETCH_SECONDS", raising=False)
    monkeypatch.delenv("LOCAL_REPO_CLEANUP_ENABLED", raising=False)
    monkeypatch.delenv("LOCAL_REPO_WORKTREE_RETENTION_HOURS", raising=False)
    monkeypatch.delenv("LOCAL_REPO_MIRROR_RETENTION_DAYS", raising=False)
    monkeypatch.delenv("DINGTALK_WEBHOOK_URL", raising=False)
    monkeypatch.setenv("CODE_QUALITY_REVIEW_ENABLED", "false")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_CODE_REVIEW_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("XIAOMIMO_API_KEY", raising=False)
    monkeypatch.delenv("XIAOMIMO_BASE_URL", raising=False)
    monkeypatch.delenv("XIAOMIMO_CODE_REVIEW_MODEL", raising=False)
    monkeypatch.delenv("XIAOMIMO_CODE_REVIEW_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("GLM_API_KEY", raising=False)
    monkeypatch.delenv("GLM_BASE_URL", raising=False)
    monkeypatch.delenv("GLM_CODE_REVIEW_MODEL", raising=False)
    monkeypatch.delenv("GLM_CODE_REVIEW_TIMEOUT_SECONDS", raising=False)


@pytest.fixture()
def db_session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture()
def client(db_session: Session) -> Generator[TestClient, None, None]:
    app = create_app()

    def override_get_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
