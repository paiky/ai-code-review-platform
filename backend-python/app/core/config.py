from dataclasses import dataclass
import os
from urllib.parse import parse_qsl, quote_plus, urlencode, urlparse


def _parse_csv(value: str) -> tuple[str, ...]:
    items = [item.strip() for item in value.split(",")]
    return tuple(item for item in items if item)


@dataclass(frozen=True)
class Settings:
    application_name: str
    server_port: int
    cors_allow_origins: tuple[str, ...]
    database_url: str
    dingtalk_enabled: bool
    dingtalk_webhook_url: str
    platform_base_url: str
    gitlab_api_enabled: bool
    gitlab_base_url: str
    gitlab_token: str
    gitlab_diff_per_page: int
    code_quality_review_enabled: bool
    code_quality_review_provider: str
    openai_api_key: str
    openai_responses_url: str
    openai_code_review_model: str
    openai_code_review_timeout_seconds: int
    anthropic_api_key: str
    anthropic_messages_url: str
    anthropic_code_review_model: str
    anthropic_code_review_timeout_seconds: int
    deepseek_api_key: str
    deepseek_base_url: str
    deepseek_code_review_model: str
    deepseek_code_review_timeout_seconds: int
    xiaomimo_api_key: str
    xiaomimo_base_url: str
    xiaomimo_code_review_model: str
    xiaomimo_code_review_timeout_seconds: int
    glm_api_key: str
    glm_base_url: str
    glm_code_review_model: str
    glm_code_review_timeout_seconds: int

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            application_name=os.getenv("APP_NAME", "ai-code-review-platform"),
            server_port=int(os.getenv("SERVER_PORT", "8090")),
            cors_allow_origins=_parse_csv(
                os.getenv("CORS_ALLOW_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
            ),
            database_url=resolve_database_url(),
            dingtalk_enabled=os.getenv("DINGTALK_ENABLED", "true").lower() != "false",
            dingtalk_webhook_url=os.getenv("DINGTALK_WEBHOOK_URL", ""),
            platform_base_url=os.getenv("PLATFORM_BASE_URL", "http://localhost:5173"),
            gitlab_api_enabled=os.getenv("GITLAB_API_ENABLED", "false").lower() == "true",
            gitlab_base_url=os.getenv("GITLAB_BASE_URL", ""),
            gitlab_token=os.getenv("GITLAB_TOKEN", ""),
            gitlab_diff_per_page=int(os.getenv("GITLAB_DIFF_PER_PAGE", "100")),
            code_quality_review_enabled=os.getenv("CODE_QUALITY_REVIEW_ENABLED", "false").lower()
            == "true",
            code_quality_review_provider=os.getenv("CODE_QUALITY_REVIEW_PROVIDER", "DEEPSEEK"),
            openai_api_key=os.getenv("OPENAI_API_KEY", ""),
            openai_responses_url=os.getenv(
                "OPENAI_RESPONSES_URL", "https://api.openai.com/v1/responses"
            ),
            openai_code_review_model=os.getenv("OPENAI_CODE_REVIEW_MODEL", "gpt-5.4"),
            openai_code_review_timeout_seconds=int(
                os.getenv("OPENAI_CODE_REVIEW_TIMEOUT_SECONDS", "1000")
            ),
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
            anthropic_messages_url=os.getenv(
                "ANTHROPIC_MESSAGES_URL", "https://api.anthropic.com/v1/messages"
            ),
            anthropic_code_review_model=os.getenv(
                "ANTHROPIC_CODE_REVIEW_MODEL", "claude-sonnet-4-5"
            ),
            anthropic_code_review_timeout_seconds=int(
                os.getenv("ANTHROPIC_CODE_REVIEW_TIMEOUT_SECONDS", "1000")
            ),
            deepseek_api_key=os.getenv("DEEPSEEK_API_KEY", ""),
            deepseek_base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
            deepseek_code_review_model=os.getenv("DEEPSEEK_CODE_REVIEW_MODEL", "deepseek-v4-pro"),
            deepseek_code_review_timeout_seconds=int(
                os.getenv("DEEPSEEK_CODE_REVIEW_TIMEOUT_SECONDS", "1000")
            ),
            xiaomimo_api_key=os.getenv("XIAOMIMO_API_KEY", ""),
            xiaomimo_base_url=os.getenv("XIAOMIMO_BASE_URL", "https://api.xiaomimimo.com/v1"),
            xiaomimo_code_review_model=os.getenv("XIAOMIMO_CODE_REVIEW_MODEL", "mimo-v2.5-pro"),
            xiaomimo_code_review_timeout_seconds=int(
                os.getenv("XIAOMIMO_CODE_REVIEW_TIMEOUT_SECONDS", "1000")
            ),
            glm_api_key=os.getenv("GLM_API_KEY", ""),
            glm_base_url=os.getenv("GLM_BASE_URL", "https://open.bigmodel.cn/api/paas/v4"),
            glm_code_review_model=os.getenv("GLM_CODE_REVIEW_MODEL", "glm-5.1"),
            glm_code_review_timeout_seconds=int(
                os.getenv("GLM_CODE_REVIEW_TIMEOUT_SECONDS", "1000")
            ),
        )


def get_settings() -> Settings:
    return Settings.from_env()


def resolve_database_url() -> str:
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        return database_url

    mysql_url = os.getenv(
        "MYSQL_URL",
        "jdbc:mysql://localhost:3306/ai_code_review"
        "?useUnicode=true&characterEncoding=utf8&serverTimezone=Asia/Shanghai"
        "&allowPublicKeyRetrieval=true&useSSL=false",
    )
    username = os.getenv("MYSQL_USERNAME", "root")
    password = os.getenv("MYSQL_PASSWORD", "root")
    return jdbc_mysql_url_to_sqlalchemy(mysql_url, username, password)


def jdbc_mysql_url_to_sqlalchemy(jdbc_url: str, username: str, password: str) -> str:
    if not jdbc_url.startswith("jdbc:mysql://"):
        raise ValueError("MYSQL_URL must start with jdbc:mysql://")

    parsed = urlparse(jdbc_url.removeprefix("jdbc:"))
    database = parsed.path.lstrip("/")
    if not parsed.hostname or not database:
        raise ValueError("MYSQL_URL must include host and database name")

    query_params = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        if key == "characterEncoding":
            query_params.append(("charset", _normalize_mysql_charset(value)))
        elif key in {"serverTimezone"}:
            continue

    if not any(key == "charset" for key, _value in query_params):
        query_params.append(("charset", "utf8mb4"))

    host = parsed.hostname
    port = f":{parsed.port}" if parsed.port else ""
    auth = f"{quote_plus(username)}:{quote_plus(password)}"
    query = urlencode(query_params)
    return f"mysql+pymysql://{auth}@{host}{port}/{database}?{query}"


def _normalize_mysql_charset(value: str) -> str:
    normalized = value.lower().replace("-", "")
    if normalized in {"utf8", "utf8mb4"}:
        return "utf8mb4"
    return value
