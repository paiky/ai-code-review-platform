from pathlib import Path

import pytest

from app.agent_review.runtime import (
    CUSTOM_RUNTIME,
    DEFAULT_RUNTIME,
    custom_base_url_host,
    normalize_custom_base_url,
    normalize_worker_capabilities,
)
from app.core.errors import AppError


def test_custom_base_url_is_normalized_and_exposes_validated_host() -> None:
    base_url = normalize_custom_base_url("https://Relay.Example.com/v1/")

    assert base_url == "https://relay.example.com/v1"
    assert custom_base_url_host(base_url) == "relay.example.com"


@pytest.mark.parametrize(
    "value",
    [
        "http://relay.example.com/v1",
        "https://127.0.0.1/v1",
        "https://relay.example.com:8443/v1",
        "https://relay.example.com/v1?token=secret",
        "https://*.example.com/v1",
    ],
)
def test_custom_base_url_rejects_unsafe_targets(value: str) -> None:
    with pytest.raises(AppError):
        normalize_custom_base_url(value)


def test_worker_capabilities_keep_legacy_default_and_drop_unknown_values() -> None:
    assert normalize_worker_capabilities(None) == [DEFAULT_RUNTIME]
    assert normalize_worker_capabilities([CUSTOM_RUNTIME, "SHELL", CUSTOM_RUNTIME]) == [
        CUSTOM_RUNTIME
    ]


def test_egress_proxy_allows_only_https_connect_without_environment_host_list() -> None:
    repository_root = Path(__file__).resolve().parents[3]
    entrypoint = (repository_root / "deploy/agent-egress-proxy-entrypoint.sh").read_text(
        encoding="utf-8"
    )
    windows_script = (repository_root / "scripts/run-agent-worker.ps1").read_text(
        encoding="utf-8"
    )

    assert "AGENT_REVIEW_CUSTOM_EGRESS_HOSTS" not in entrypoint
    assert "http_access allow CONNECT SSL_ports" in entrypoint
    assert "http_access deny all" in entrypoint
    assert "Get-AgentCustomEgressHosts" not in windows_script
    assert '"http_access allow CONNECT SSL_ports"' in windows_script
    assert '"http_access allow windows_backend windows_backend_port"' in windows_script
    for name in (
        "docker-compose.yml",
        "docker-compose.runtime.yml",
        "docker-compose.windows-agent.yml",
    ):
        compose = (repository_root / "deploy" / name).read_text(encoding="utf-8")
        assert "AGENT_REVIEW_CUSTOM_EGRESS_HOSTS" not in compose
        proxy_section = compose.split("\n  agent-egress-proxy:", 1)[1].split(
            "\n  frontend:", 1
        )[0]
        assert "read_only: true" in proxy_section
        assert "/tmp:rw,noexec,nosuid,size=8m" in proxy_section

    windows_compose = (
        repository_root / "deploy/docker-compose.windows-agent.yml"
    ).read_text(encoding="utf-8")
    windows_proxy = windows_compose.split("\n  agent-egress-proxy:", 1)[1]
    assert 'entrypoint: ["squid", "-N", "-f", "/etc/squid/squid.conf"]' in windows_proxy
