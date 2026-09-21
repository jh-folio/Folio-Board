"""Dynamic model catalog discovery for CLI providers.

The catalog is best-effort and cache-first. Normal settings reads reuse the last
known catalog so UI startup never blocks on CLI subprocesses.
Manual refresh is the only path that reaches out to providers.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import subprocess
from pathlib import Path
from features.common.workspace import data_dir

ROOT = Path(__file__).resolve().parent.parent.parent
CACHE_PATH = data_dir() / "llm-model-cache.json"

CLI_MODEL_FALLBACKS = {'codex': [{'value': 'gpt-6-astra', 'label': 'GPT-6 Astra'},
           {'value': 'gpt-5.6-sol', 'label': 'GPT-5.6 Sol'},
           {'value': 'gpt-5.6-terra', 'label': 'GPT-5.6 Terra'},
           {'value': 'gpt-5.6-luna', 'label': 'GPT-5.6 Luna'},
           {'value': 'gpt-5.5', 'label': 'GPT-5.5'},
           {'value': 'gpt-5.4-mini', 'label': 'GPT-5.4-mini'}],
 'claude': [{'value': 'claude-fable-5', 'label': 'Claude Fable 5'},
            {'value': 'claude-sonnet-5', 'label': 'Claude Sonnet 5'},
            {'value': 'claude-opus-5', 'label': 'Claude Opus 5'},
            {'value': 'claude-haiku-4-5', 'label': 'Claude Haiku 4.5'},
            {'value': 'claude-opus-4-8', 'label': 'Claude Opus 4.8'},
            {'value': 'claude-sonnet-4-6', 'label': 'Claude Sonnet 4.6'}],
 'antigravity': [{'value': 'gemini-3.6-flash-medium', 'label': 'Gemini 3.6 Flash Medium'},
                 {'value': 'gemini-3.1-pro-high', 'label': 'Gemini 3.1 Pro High'},
                 {'value': 'claude-sonnet-4-6', 'label': 'Claude Sonnet 4.6'}]}

DEPRECATED_MODEL_REPLACEMENTS: dict[str, dict[str, str]] = {}

# Display order follows recency. Keep a deliberate default for each adapter so
# a reordered selector cannot silently change a no-override workflow.
CLI_DEFAULT_MODELS = {
    "codex": "gpt-5.6-sol",
}

MAX_MODEL_ID_LENGTH = 128
_MODEL_ID_CHARS = frozenset("abcdefghijklmnopqrstuvwxyz0123456789._:-")


def _is_generation_model_id(value: str) -> bool:
    model_id = str(value or "").strip().lower()
    if not model_id or len(model_id) > MAX_MODEL_ID_LENGTH:
        return False
    valid_prefix = model_id.startswith(("gpt", "claude", "gemini")) or (
        len(model_id) >= 2 and model_id[0] == "o" and model_id[1].isdigit()
    )
    return valid_prefix and all(char in _MODEL_ID_CHARS for char in model_id)


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _label_for(model_id: str) -> str:
    pieces = str(model_id or "").replace("_", "-").split("-")
    return " ".join(piece.upper() if piece.lower() in {"gpt", "api"} else piece.capitalize() for piece in pieces if piece)


def _choice(model_id: str) -> dict:
    value = str(model_id or "").strip()
    return {"value": value, "label": _label_for(value)}


def normalize_model_id(provider: str, model_id: str) -> str:
    provider_id = str(provider or "").strip().lower()
    value = str(model_id or "").strip()
    return DEPRECATED_MODEL_REPLACEMENTS.get(provider_id, {}).get(value, value)


def _sanitize_choices(provider: str, choices: list[dict]) -> list[dict]:
    deprecated = DEPRECATED_MODEL_REPLACEMENTS.get(str(provider or "").strip().lower(), {})
    return [
        item for item in choices
        if str((item or {}).get("value") or "").strip() not in deprecated
    ]


def _sanitize_catalog(provider: str, catalog: dict) -> dict:
    return {
        **catalog,
        "modelChoices": _sanitize_choices(provider, list(catalog.get("modelChoices") or [])),
    }


def _dedupe_choices(primary: list[dict], fallback: list[dict]) -> list[dict]:
    seen = set()
    out = []
    for item in [*primary, *fallback]:
        value = str((item or {}).get("value") or "").strip()
        if not value or value in seen:
            continue
        label = str((item or {}).get("label") or "").strip() or _label_for(value)
        out.append({"value": value, "label": label})
        seen.add(value)
    return out


def _fallback_result(provider: str, transport: str, fallback: list[dict], status: str, message: str = "") -> dict:
    return {
        "provider": provider,
        "transport": transport,
        "source": "fallback",
        "status": status,
        "message": message,
        "modelChoices": _sanitize_choices(provider, _dedupe_choices([], fallback)),
        "checkedAt": _now_iso(),
    }


def _remote_result(provider: str, transport: str, models: list[str], fallback: list[dict]) -> dict:
    return {
        "provider": provider,
        "transport": transport,
        "source": "remote",
        "status": "available",
        "message": "모델 목록을 가져왔습니다.",
        "modelChoices": _sanitize_choices(provider, _dedupe_choices([_choice(model_id) for model_id in models], fallback)),
        "checkedAt": _now_iso(),
    }


def _read_cache() -> dict:
    try:
        if CACHE_PATH.exists():
            payload = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
            return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}
    return {}


def _write_cache(cache: dict) -> None:
    try:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        return


def _get_cached(key: str, *, refresh: bool) -> dict | None:
    if refresh:
        return None
    return _get_any_cached(key)


def _get_any_cached(key: str) -> dict | None:
    entry = _read_cache().get(key)
    if isinstance(entry, dict):
        return entry
    return None


def _cached_after_refresh_failure(key: str, provider: str, status: str, message: str) -> dict | None:
    cached = _get_any_cached(key)
    if not cached:
        return None
    return _sanitize_catalog(provider, {
        **cached,
        "source": "cache",
        "status": status,
        "message": message,
    })


def _set_cached(key: str, entry: dict) -> dict:
    cache = _read_cache()
    cache[key] = entry
    _write_cache(cache)
    return entry


def _parse_cli_models(stdout: str) -> list[str]:
    out = []
    for line in str(stdout or "").splitlines():
        raw = line.strip()
        if len(raw) > MAX_MODEL_ID_LENGTH + 8:
            continue
        text = raw.strip("-*•").strip()
        if not text:
            continue
        candidate = text.split()[0].strip("`'\",")
        if _is_generation_model_id(candidate):
            out.append(candidate)
    return out


def _parse_claude_help_models(stdout: str) -> list[str]:
    text = str(stdout or "")
    out = []
    for model_id in re.findall(r"\bclaude-[a-z0-9._:-]+\b", text[:100_000], re.I):
        if _is_generation_model_id(model_id):
            out.append(model_id)
    if re.search(r"\bfable\b", text, re.I):
        out.append("claude-fable-5")
    if re.search(r"\bsonnet\b", text, re.I):
        out.append("claude-sonnet-5")
    if re.search(r"\bopus\b", text, re.I):
        out.append("claude-opus-5")
    return list(dict.fromkeys(out))


def discover_cli_models(
    adapter: str,
    *,
    executable: str = "",
    refresh: bool = False,
    timeout: int = 8,
    runner=subprocess.run,
    fallback: list[dict] | None = None,
) -> dict:
    adapter = str(adapter or "").strip().lower()
    fallback_choices = fallback if fallback is not None else CLI_MODEL_FALLBACKS.get(adapter, [])
    if adapter not in CLI_MODEL_FALLBACKS:
        raise ValueError(f"Unsupported CLI provider: {adapter}")
    if not executable:
        return _fallback_result(adapter, "cli", fallback_choices, "not_configured", "실행 파일을 찾지 못해 기본 모델 목록을 사용합니다.")
    key = f"cli:{adapter}:{executable}"
    cached = _get_cached(key, refresh=refresh)
    if cached:
        return _sanitize_catalog(adapter, cached)
    if not refresh:
        return _fallback_result(adapter, "cli", fallback_choices, "cached_missing", "저장된 모델 목록이 없어 기본 모델 목록을 사용합니다.")
    commands = [[executable, "models"], [executable, "model", "list"]]
    for command in commands:
        try:
            proc = runner(command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
            if getattr(proc, "returncode", 1) != 0:
                continue
            models = _parse_cli_models(getattr(proc, "stdout", ""))
            if models:
                return _set_cached(key, _remote_result(adapter, "cli", models, fallback_choices))
        except (OSError, subprocess.SubprocessError, TimeoutError):
            continue
    if adapter == "claude":
        try:
            proc = runner([executable, "--help"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
            if getattr(proc, "returncode", 1) == 0:
                models = _parse_claude_help_models(getattr(proc, "stdout", ""))
                if models:
                    return _set_cached(key, _remote_result(adapter, "cli", models, fallback_choices))
        except (OSError, subprocess.SubprocessError, TimeoutError):
            pass
    cached = _cached_after_refresh_failure(key, adapter, "unsupported_cached", "CLI 모델 조회에 실패해 저장된 모델 목록을 유지합니다.")
    if cached:
        return cached
    return _fallback_result(adapter, "cli", fallback_choices, "unsupported", "CLI가 모델 목록 명령을 제공하지 않아 기본 모델 목록을 사용합니다.")


def choices_from_catalog(catalog: dict) -> list[dict]:
    return list(catalog.get("modelChoices") or [])
