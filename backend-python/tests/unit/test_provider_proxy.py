from __future__ import annotations

from app.code_quality import providers
from app.core.config import Settings


def test_provider_proxy_prefers_explicit_setting(monkeypatch) -> None:
    monkeypatch.setenv("AGENT_REVIEW_UPSTREAM_PROXY", "http://agent-proxy:3128")
    monkeypatch.setenv("CODE_QUALITY_REVIEW_PROXY", "http://provider-proxy:7897")

    assert Settings.from_env().code_quality_review_proxy == "http://provider-proxy:7897"


def test_provider_proxy_falls_back_to_agent_upstream_proxy(monkeypatch) -> None:
    monkeypatch.delenv("CODE_QUALITY_REVIEW_PROXY", raising=False)
    monkeypatch.setenv("AGENT_REVIEW_UPSTREAM_PROXY", "http://lan-proxy:7897")

    assert Settings.from_env().code_quality_review_proxy == "http://lan-proxy:7897"


def test_provider_http_client_uses_only_dedicated_proxy(monkeypatch) -> None:
    captured: dict = {}
    sentinel = object()

    def fake_client(**kwargs):
        captured.update(kwargs)
        return sentinel

    monkeypatch.setenv("CODE_QUALITY_REVIEW_PROXY", "http://provider-proxy:7897")
    monkeypatch.setenv("HTTPS_PROXY", "http://global-proxy:9999")
    monkeypatch.setattr(providers.httpx, "Client", fake_client)

    client = providers._provider_http_client(45)

    assert client is sentinel
    assert captured == {
        "timeout": 45,
        "proxy": "http://provider-proxy:7897",
        "trust_env": False,
    }
