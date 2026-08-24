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

    http_base_url = normalize_custom_base_url("http://127.0.0.1:8080/v1/")
    assert http_base_url == "http://127.0.0.1:8080/v1"
    assert custom_base_url_host(http_base_url) == "127.0.0.1"


@pytest.mark.parametrize(
    "value",
    [
        "ftp://relay.example.com/v1",
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


def test_egress_proxy_allows_custom_http_and_https_without_environment_host_list() -> None:
    repository_root = Path(__file__).resolve().parents[3]
    entrypoint_path = repository_root / "deploy/agent-egress-proxy-entrypoint.sh"
    entrypoint_bytes = entrypoint_path.read_bytes()
    entrypoint = entrypoint_bytes.decode("utf-8")
    dockerfile = (repository_root / "deploy/agent-egress-proxy.Dockerfile").read_text(
        encoding="utf-8"
    )
    git_attributes = (repository_root / ".gitattributes").read_text(encoding="utf-8")
    windows_script = (repository_root / "scripts/run-agent-worker.ps1").read_text(
        encoding="utf-8"
    )

    assert entrypoint_bytes.startswith(b"#!/bin/sh\n")
    assert b"\r\n" not in entrypoint_bytes
    assert "*.sh text eol=lf" in git_attributes.splitlines()
    assert "sed -i 's/\\r$//' /usr/local/bin/agent-egress-proxy-entrypoint" in dockerfile
    assert "AGENT_REVIEW_CUSTOM_EGRESS_HOSTS" not in entrypoint
    assert "acl SSL_ports port 1-65535" in entrypoint
    assert "http_access allow CONNECT SSL_ports" in entrypoint
    assert "http_access allow !CONNECT allowed_http_ports" in entrypoint
    assert "http_access deny all" in entrypoint
    assert "Get-AgentCustomEgressHosts" not in windows_script
    assert '"acl SSL_ports port 1-65535"' in windows_script
    assert '"http_access allow CONNECT SSL_ports"' in windows_script
    assert '"http_access allow !CONNECT allowed_http_ports"' in windows_script
    assert '"http_access allow windows_backend windows_backend_port"' in windows_script
    for name in (
        "docker-compose.yml",
        "docker-compose.runtime.yml",
        "docker-compose.windows-agent.yml",
    ):
        compose = (repository_root / "deploy" / name).read_text(encoding="utf-8")
        assert "AGENT_REVIEW_CUSTOM_EGRESS_HOSTS" not in compose
        worker_section = compose.split("\n  agent-worker:", 1)[1].split(
            "\n  agent-egress-proxy:", 1
        )[0]
        assert "HTTP_PROXY: http://agent-egress-proxy:3128" in worker_section
        assert "HTTPS_PROXY: http://agent-egress-proxy:3128" in worker_section
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
