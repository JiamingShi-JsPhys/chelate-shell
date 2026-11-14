"""The AI endpoint decides where the API key travels.

``_ai_chat`` reads ``TASK_ORG_AI_BASE_URL`` from the environment and attaches
``Authorization: Bearer <key>`` to whatever URL comes out of it. These tests
pin the rule that keeps a key from leaking: a bearer token either stays on
this machine or travels over TLS.

The router itself is fine with any OpenAI-compatible endpoint (DeepSeek, Qwen,
Moonshot, vLLM, Ollama); what is refused is a plaintext remote one, because
that is where the difference between "the user chose this endpoint" and "the
key went out in clear text" lives.
"""
from __future__ import annotations

import urllib.request

import pytest
from scripts.utils import _ai_chat, _key_safe_base_url


class _Response:
    def __init__(self, body: bytes) -> None:
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *_: object) -> bool:
        return False


@pytest.mark.parametrize(
    "url",
    [
        "https://api.openai.com/v1",
        "https://api.deepseek.com/v1",
        "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "http://localhost:11434/v1",
        "http://127.0.0.1:8000/v1",
        "http://127.8.9.10:8080/v1",
        "http://[::1]:11434/v1",
    ],
)
def test_accepted_endpoints(url: str) -> None:
    assert _key_safe_base_url(url) is True


@pytest.mark.parametrize(
    "url",
    [
        "http://api.example.com/v1",     # plaintext, remote: the key would travel in the clear
        "http://10.0.0.5:8000/v1",       # plaintext, private network: still not this machine
        "file:///etc/passwd",            # not a network scheme at all
        "ftp://example.com/x",
        "//example.com/v1",              # no scheme
        "https://user:pass@example.com/v1",  # credentials embedded in the URL
    ],
)
def test_refused_endpoints(url: str) -> None:
    assert _key_safe_base_url(url) is False


def test_the_key_is_not_sent_to_a_plaintext_remote_host(monkeypatch: pytest.MonkeyPatch) -> None:
    """The whole point: a refused endpoint means no request, not a redacted one."""
    sent: list[object] = []

    def _spy(*args: object, **_: object) -> _Response:
        sent.append(args)
        return _Response(b'{"choices":[{"message":{"content":"leaked"}}]}')

    monkeypatch.setenv("TASK_ORG_AI_BASE_URL", "http://collector.example.com/v1")
    monkeypatch.setattr(urllib.request, "urlopen", _spy)

    assert _ai_chat("sys", "user", 10, "sk-secret") == ""
    assert sent == []


def test_a_tls_endpoint_still_works(monkeypatch: pytest.MonkeyPatch) -> None:
    """Hardening must not break the documented feature."""
    seen: list[urllib.request.Request] = []

    def _fake(request: urllib.request.Request, **_: object) -> _Response:
        seen.append(request)
        return _Response(b'{"choices":[{"message":{"content":" ok "}}]}')

    monkeypatch.setenv("TASK_ORG_AI_BASE_URL", "https://api.deepseek.com/v1")
    monkeypatch.setattr(urllib.request, "urlopen", _fake)

    assert _ai_chat("sys", "user", 10, "sk-secret") == "ok"
    assert len(seen) == 1
    assert seen[0].full_url == "https://api.deepseek.com/v1/chat/completions"
    assert seen[0].get_header("Authorization") == "Bearer sk-secret"


def test_a_local_endpoint_still_works(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ollama and vLLM listen on plain http on loopback; that stays supported."""
    seen: list[urllib.request.Request] = []

    def _fake(request: urllib.request.Request, **_: object) -> _Response:
        seen.append(request)
        return _Response(b'{"choices":[{"message":{"content":"ok"}}]}')

    monkeypatch.setenv("TASK_ORG_AI_BASE_URL", "http://localhost:11434/v1")
    monkeypatch.setattr(urllib.request, "urlopen", _fake)

    assert _ai_chat("sys", "user", 10, "sk-secret") == "ok"
    assert seen[0].full_url == "http://localhost:11434/v1/chat/completions"
