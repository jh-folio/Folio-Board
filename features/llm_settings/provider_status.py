"""Safe, read-only checks for configured LLM API credentials and model access."""
from __future__ import annotations

import datetime as dt
import urllib.error
import urllib.parse
import urllib.request

from features.llm_settings.client import openai_config

PROVIDER_INFO = {
    "openai": {
        "label": "OpenAI",
        "setupUrl": "https://platform.openai.com/api-keys",
    },
    "gemini": {
        "label": "Gemini",
        "setupUrl": "https://aistudio.google.com/app/apikey",
    },
    "claude": {
        "label": "Claude",
        "setupUrl": "https://console.anthropic.com/settings/keys",
    },
}


def _provider_config(provider: str, *, model: str = "") -> tuple[str, str]:
    cfg = openai_config()
    if provider == "openai":
        return cfg["apiKey"], str(model or cfg["model"] or "").strip()
    if provider == "gemini":
        return cfg["geminiApiKey"], str(model or cfg["geminiModel"] or "").strip()
    if provider == "claude":
        return cfg["anthropicApiKey"], str(model or cfg["anthropicModel"] or "").strip()
    raise ValueError(f"Unsupported LLM API provider: {provider}")


def _request_for(provider: str, api_key: str, model: str) -> urllib.request.Request:
    model_path = urllib.parse.quote(model, safe="")
    if provider == "openai":
        return urllib.request.Request(
            f"https://api.openai.com/v1/models/{model_path}",
            headers={"Authorization": f"Bearer {api_key}"},
            method="GET",
        )
    if provider == "gemini":
        return urllib.request.Request(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model_path}",
            headers={"x-goog-api-key": api_key},
            method="GET",
        )
    return urllib.request.Request(
        f"https://api.anthropic.com/v1/models/{model_path}",
        headers={"x-api-key": api_key, "anthropic-version": "2023-06-01"},
        method="GET",
    )


def _result(provider: str, model: str, status: str, message: str, *, available: bool = False) -> dict:
    return {
        "provider": provider,
        "label": PROVIDER_INFO[provider]["label"],
        "model": model,
        "status": status,
        "available": available,
        "message": message,
        "checkedAt": dt.datetime.now(dt.timezone.utc).isoformat(),
    }


def check_provider(provider: str, *, model: str = "", timeout: int = 15) -> dict:
    provider = str(provider or "").strip().lower()
    if provider not in PROVIDER_INFO:
        raise ValueError(f"Unsupported LLM API provider: {provider}")
    api_key, model = _provider_config(provider, model=model)
    if not api_key:
        return _result(provider, model, "not_configured", "저장된 API Key가 없습니다.")
    try:
        with urllib.request.urlopen(_request_for(provider, api_key, model), timeout=timeout) as response:
            if 200 <= response.status < 300:
                return _result(provider, model, "available", "API Key와 모델 접근을 확인했습니다.", available=True)
            return _result(provider, model, "provider_error", f"Provider 응답 코드: {response.status}")
    except urllib.error.HTTPError as exc:
        if exc.code in {401, 403}:
            return _result(provider, model, "invalid_credentials", "API Key가 유효하지 않거나 권한이 없습니다.")
        if exc.code == 404:
            return _result(provider, model, "model_unavailable", "선택한 모델에 접근할 수 없습니다.")
        if exc.code == 429:
            return _result(provider, model, "rate_limited", "요청 한도 또는 사용량 제한에 도달했습니다.")
        return _result(provider, model, "provider_error", f"Provider 확인 실패 (HTTP {exc.code}).")
    except (urllib.error.URLError, TimeoutError, OSError):
        return _result(provider, model, "network_error", "Provider에 연결할 수 없습니다.")
