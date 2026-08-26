from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Iterator

from sqlalchemy import inspect, text
from sqlalchemy.engine import make_url

from app.database_targets import DatabaseTarget


class DatabaseCopyError(RuntimeError):
    pass


@dataclass(frozen=True)
class DatabaseCopyPlan:
    source_table_count: int
    source_rows_estimate: int
    source_data_bytes: int
    source_index_bytes: int
    target_table_count: int
    mysqldump_path: str
    mysql_path: str


def inspect_database_copy_plan(
    source_engine, target_engine
) -> DatabaseCopyPlan:
    mysqldump_path = shutil.which("mysqldump")
    mysql_path = shutil.which("mysql")
    if not mysqldump_path or not mysql_path:
        raise DatabaseCopyError("mysqldump and mysql clients must both be installed")
    with source_engine.connect() as source_connection:
        source = source_connection.execute(
            text(
                "SELECT COUNT(*) AS table_count, "
                "COALESCE(SUM(TABLE_ROWS), 0) AS rows_estimate, "
                "COALESCE(SUM(DATA_LENGTH), 0) AS data_bytes, "
                "COALESCE(SUM(INDEX_LENGTH), 0) AS index_bytes "
                "FROM information_schema.TABLES WHERE TABLE_SCHEMA = DATABASE()"
            )
        ).mappings().one()
    with target_engine.connect() as target_connection:
        target_table_count = int(
            target_connection.execute(
                text(
                    "SELECT COUNT(*) FROM information_schema.TABLES "
                    "WHERE TABLE_SCHEMA = DATABASE()"
                )
            ).scalar()
            or 0
        )
    return DatabaseCopyPlan(
        source_table_count=int(source["table_count"]),
        source_rows_estimate=int(source["rows_estimate"]),
        source_data_bytes=int(source["data_bytes"]),
        source_index_bytes=int(source["index_bytes"]),
        target_table_count=target_table_count,
        mysqldump_path=mysqldump_path,
        mysql_path=mysql_path,
    )


def copy_test_database_to_local(
    source: DatabaseTarget,
    target: DatabaseTarget,
    plan: DatabaseCopyPlan,
    target_engine,
) -> dict[str, int]:
    if plan.target_table_count != 0:
        raise DatabaseCopyError("Local target must be empty before the one-time copy")
    with _mysql_option_file(source) as source_options, _mysql_option_file(
        target
    ) as target_options:
        dump_command = [
            plan.mysqldump_path,
            f"--defaults-extra-file={source_options}",
            "--single-transaction",
            "--quick",
            "--hex-blob",
            "--default-character-set=utf8mb4",
            "--set-gtid-purged=OFF",
            "--column-statistics=0",
            "--no-tablespaces",
            "--skip-lock-tables",
            "--skip-comments",
            source.identity.database,
        ]
        load_command = [
            plan.mysql_path,
            f"--defaults-extra-file={target_options}",
            "--default-character-set=utf8mb4",
            target.identity.database,
        ]
        dump = subprocess.Popen(
            dump_command,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        if dump.stdout is None:
            dump.kill()
            raise DatabaseCopyError("mysqldump stdout pipe was not created")
        load = subprocess.Popen(
            load_command,
            stdin=dump.stdout,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        dump.stdout.close()
        load_code = load.wait()
        dump_code = dump.wait()
        if dump_code != 0 or load_code != 0:
            raise DatabaseCopyError(
                "Database stream copy failed; client stderr is hidden to protect connection details"
            )
    return sanitize_local_database(target_engine)


def sanitize_local_database(engine) -> dict[str, int]:
    affected: dict[str, int] = {}
    with engine.begin() as connection:
        inspector = inspect(connection)
        tables = set(inspector.get_table_names())

        def execute_if_table(table_name: str, sql: str) -> None:
            if table_name not in tables:
                return
            result = connection.execute(text(sql))
            affected[table_name] = affected.get(table_name, 0) + max(
                int(result.rowcount or 0), 0
            )

        execute_if_table(
            "projects", "UPDATE projects SET dingtalk_webhook_id = NULL"
        )
        execute_if_table("notification_webhooks", "DELETE FROM notification_webhooks")
        execute_if_table(
            "notification_records",
            "UPDATE notification_records SET target = NULL, request_digest = NULL, "
            "response_body = NULL, error_message = NULL",
        )
        execute_if_table(
            "code_quality_model_providers",
            "UPDATE code_quality_model_providers SET api_key = NULL, enabled = FALSE",
        )
        execute_if_table(
            "code_quality_review_settings",
            "UPDATE code_quality_review_settings SET openai_api_key = NULL, "
            "anthropic_api_key = NULL, mr_auto_review_enabled = FALSE, "
            "dingtalk_notification_enabled = FALSE, review_enabled = FALSE",
        )
        execute_if_table(
            "code_quality_agent_settings",
            "UPDATE code_quality_agent_settings SET enabled = FALSE, "
            "runtime_type = 'CLAUDE_CODE_DEEPSEEK', "
            "selected_runtime_code = 'CLAUDE_CODE_DEEPSEEK', api_key_ciphertext = NULL, "
            "api_key_fingerprint = NULL, custom_display_name = NULL, "
            "custom_base_url = NULL, custom_model = NULL, "
            "custom_reasoning_effort = NULL, custom_tls_verify = TRUE, "
            "custom_api_key_ciphertext = NULL, "
            "custom_api_key_fingerprint = NULL, worker_id = NULL, "
            "worker_version = NULL, cli_version = NULL, last_worker_heartbeat_at = NULL, "
            "test_request_id = NULL, test_status = NULL, test_message = NULL, "
            "test_duration_ms = NULL, test_started_at = NULL, test_finished_at = NULL",
        )
        execute_if_table(
            "code_quality_agent_runtimes",
            "UPDATE code_quality_agent_runtimes SET api_key_ciphertext = NULL, "
            "api_key_fingerprint = NULL, test_request_id = NULL, test_status = NULL, "
            "test_message = NULL, test_duration_ms = NULL, test_started_at = NULL, "
            "test_finished_at = NULL",
        )
        execute_if_table("code_quality_agent_workers", "DELETE FROM code_quality_agent_workers")
        execute_if_table("code_quality_scheduler_jobs", "DELETE FROM code_quality_scheduler_jobs")
        execute_if_table(
            "agent_review_runs",
            "UPDATE agent_review_runs SET status = 'CANCELLED', "
            "failure_code = 'LOCAL_MIGRATION_RESET', "
            "failure_message = 'Pending run disabled during local database migration', "
            "finished_at = COALESCE(finished_at, CURRENT_TIMESTAMP(3)) "
            "WHERE status IN ('PENDING', 'RUNNING')",
        )
    return affected


@contextmanager
def _mysql_option_file(target: DatabaseTarget) -> Iterator[str]:
    url = make_url(target.database_url)
    username = str(url.username or "")
    password = str(url.password or "")
    if not username or not password:
        raise DatabaseCopyError("Database client username and password are required")
    directory = Path(tempfile.mkdtemp(prefix="ai-review-db-client-"))
    path = directory / "client.cnf"
    content = "\n".join(
        (
            "[client]",
            f'host="{_escape_option_value(target.identity.host)}"',
            f"port={target.identity.port}",
            f'user="{_escape_option_value(username)}"',
            f'password="{_escape_option_value(password)}"',
            "default-character-set=utf8mb4",
            "",
        )
    )
    path.write_text(content, encoding="utf-8")
    os.chmod(path, 0o600)
    try:
        yield str(path)
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def _escape_option_value(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace("\r", "\\r")
        .replace("\n", "\\n")
        .replace("\t", "\\t")
        .replace('"', '\\"')
    )
