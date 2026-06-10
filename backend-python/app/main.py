from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.code_quality.api import profile_router as code_quality_profile_router
from app.code_quality.api import provider_router as code_quality_provider_router
from app.code_quality.api import review_router as code_quality_review_router
from app.code_quality.service import recover_stale_running_reviews_on_startup
from app.core.config import get_settings
from app.core.errors import register_exception_handlers
from app.core.response import ok
from app.core.tracing import trace_id_middleware
from app.project_integration.api import group_router
from app.project_integration.api import router as project_router
from app.project_integration.api import target_mapping_router
from app.project_integration.api import webhook_router
from app.review_feedback.api import feedback_pool_router
from app.review_feedback.api import task_feedback_router
from app.review_record.api import router as review_task_router
from app.rule_template.api import router as rule_template_router


log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    try:
        recover_stale_running_reviews_on_startup()
    except Exception as exception:
        log.warning("Code quality startup recovery skipped: %s", exception)
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.application_name, lifespan=lifespan)

    app.middleware("http")(trace_id_middleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_allow_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_exception_handlers(app)
    app.include_router(project_router)
    app.include_router(group_router)
    app.include_router(target_mapping_router)
    app.include_router(webhook_router)
    app.include_router(review_task_router)
    app.include_router(task_feedback_router)
    app.include_router(feedback_pool_router)
    app.include_router(rule_template_router)
    app.include_router(code_quality_review_router)
    app.include_router(code_quality_profile_router)
    app.include_router(code_quality_provider_router)

    @app.get("/api/health")
    async def health() -> dict:
        return ok(
            {
                "status": "UP",
                "application": settings.application_name,
                "time": datetime.now(timezone.utc).isoformat(),
            }
        )

    @app.get("/actuator/health")
    async def actuator_health() -> dict[str, str]:
        return {"status": "UP"}

    return app


app = create_app()
