"""LLM HTTP client, provider config, and env settings management."""
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from features.llm_settings.model_catalog import normalize_model_id
from features.llm_settings.reasoning import (
    is_supported_reasoning_effort,
    normalize_reasoning_effort,
)

ROOT = Path(__file__).resolve().parent.parent.parent

OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
ANTHROPIC_MESSAGES_URL = "https://api.anthropic.com/v1/messages"
GEMINI_GENERATE_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
DEFAULT_OPENAI_MODEL = "gpt-5.6-sol"
DEFAULT_GEMINI_MODEL = "gemini-3.5-flash"
DEFAULT_ANTHROPIC_MODEL = "claude-sonnet-5"
GLOBAL_REASONING_ENV = "AI_AGENT_REASONING_EFFORT"
TOSS_OPEN_API_DEFAULT_BASE_URL = "https://openapi.tossinvest.com"
SECRET_STORE_SERVICE = "Folio OS"
SECRET_ENV_KEYS = {
    "OPENAI_API_KEY",
    "GEMINI_API_KEY",
    "ANTHROPIC_API_KEY",
    "DART_API_KEY",
    "FRED_API_KEY",
    "BOK_API_KEY",
    "TOSS_OPEN_API_KEY",
    "TOSS_OPEN_API_CLIENT_SECRET",
    "NOTION_TOKEN",
    "IMGBB_API_KEY",
}


class LlmRequestError(RuntimeError):
    def __init__(self, status_code, message, body=""):
        self.status_code = status_code
        self.body = body
        super().__init__(f"HTTP {status_code}: {message}" + (f" · {body[:500]}" if body else ""))


# A producer binds one resolved task configuration for the duration of its
# request.  Feature modules intentionally import ``selected_llm_config``
# directly, so a ContextVar gives all nested calls the same provider/model
# without mutating ``os.environ`` or the process-wide global setting.
_TASK_LLM_CONFIG: ContextVar[dict | None] = ContextVar("folio_task_llm_config", default=None)


@contextmanager
def bind_task_llm_config(config):
    """Bind an in-memory API configuration to the current producer context.

    The config may contain a credential while it is being used, but this
    context never serializes or logs it.  Callers should pass a fresh mapping
    obtained at execution time; nested contexts restore the previous value.
    """
    token = _TASK_LLM_CONFIG.set(deepcopy(dict(config)) if isinstance(config, dict) else None)
    try:
        yield
    finally:
        _TASK_LLM_CONFIG.reset(token)


# ---------------------------------------------------------------------------
# Env / settings
# ---------------------------------------------------------------------------

def load_dotenv():
    env_path = ROOT / ".env"
    rows = []
    migrated_secret_keys = set()
    try:
        if env_path.exists():
            rows = env_path.read_text(encoding="utf-8").splitlines()
        for line in rows:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value
            if key in SECRET_ENV_KEYS and value:
                try:
                    _store_secret_value(key, value)
                except Exception:
                    continue
                migrated_secret_keys.add(key)
    except Exception:
        rows = []
    if migrated_secret_keys:
        next_rows = []
        for line in rows:
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                next_rows.append(line)
                continue
            key, _ = line.split("=", 1)
            if key.strip() not in migrated_secret_keys:
                next_rows.append(line)
        try:
            # Successfully migrated secrets are removed from the legacy .env file.
            # codeql[py/clear-text-storage-sensitive-data]
            env_path.write_text(
                "\n".join(next_rows).rstrip() + ("\n" if next_rows else ""),
                encoding="utf-8",
            )
        except Exception:
            pass
    for key in SECRET_ENV_KEYS:
        if key in os.environ:
            continue
        value = _load_secret_value(key)
        if value:
            os.environ[key] = value


def openai_config():
    load_dotenv()
    provider = os.environ.get("LLM_PROVIDER", "openai").strip().lower() or "openai"
    enabled = ai_agent_enabled()
    return {
        "provider": provider,
        "apiKey": os.environ.get("OPENAI_API_KEY", "").strip(),
        "geminiApiKey": os.environ.get("GEMINI_API_KEY", "").strip(),
        "anthropicApiKey": os.environ.get("ANTHROPIC_API_KEY", "").strip(),
        "model": os.environ.get("OPENAI_MODEL", DEFAULT_OPENAI_MODEL).strip() or DEFAULT_OPENAI_MODEL,
        "geminiModel": os.environ.get("GEMINI_MODEL", DEFAULT_GEMINI_MODEL).strip() or DEFAULT_GEMINI_MODEL,
        "anthropicModel": normalize_model_id(
            "claude",
            os.environ.get("ANTHROPIC_MODEL", DEFAULT_ANTHROPIC_MODEL).strip() or DEFAULT_ANTHROPIC_MODEL,
        ),
        "enabled": enabled,
    }


def ai_agent_enabled() -> bool:
    load_dotenv()
    explicit = os.environ.get("AI_AGENT_ENABLED")
    if explicit is not None:
        return str(explicit).strip().lower() not in {"0", "false", "no", "off"}
    legacy = os.environ.get("USE_LLM_BRIEFING", os.environ.get("USE_OPENAI_BRIEFING", "1"))
    return str(legacy).strip().lower() not in {"0", "false", "no", "off"}


def ai_agent_mode() -> str:
    load_dotenv()
    mode = os.environ.get("AI_AGENT_MODE", "cli").strip().lower().replace("-", "_")
    if mode in {"api", "llm_api"}:
        return "api"
    if mode in {"cli", "agent", "llm_cli"}:
        return "cli"
    return "cli"


def configured_global_reasoning_effort(*, mode: str, provider: str, model: str, runtime: bool = False) -> str:
    """Read the global effort without treating a display label as transport.

    A missing new setting is deliberately exposed as ``provider_default`` so
    existing installations do not acquire a new persisted preference.  At
    runtime, an older Astra-only environment setting keeps its prior behavior
    (including the historical low default) until the user explicitly saves a
    global effort in Settings.
    """
    load_dotenv()
    raw = os.environ.get(GLOBAL_REASONING_ENV)
    if raw is None:
        if runtime and str(mode or "").strip().lower() in {"api", "llm_api"} and str(provider or "").strip().lower() == "openai" and str(model or "").strip().lower() == "gpt-6-astra":
            raw = os.environ.get("OPENAI_ASTRA_REASONING_EFFORT", "low") or "low"
        else:
            return "provider_default"
    try:
        normalized = normalize_reasoning_effort(raw)
    except ValueError as exc:
        raise ValueError("Invalid AI_AGENT_REASONING_EFFORT") from exc
    if not is_supported_reasoning_effort(mode, provider, model, normalized):
        raise ValueError("Unsupported AI_AGENT_REASONING_EFFORT for selected model")
    return normalized


def default_generation_mode() -> str:
    if not ai_agent_enabled():
        return "rules"
    return "llm_api" if ai_agent_mode() == "api" else "llm_cli"


def config_for_provider(provider=None, *, model=None, reasoning_effort=None):
    """Build an API client config for an explicit provider at call time.

    Task defaults must be able to keep using their own provider when the
    global provider changes.  ``selected_llm_config`` intentionally follows
    the global setting; this helper selects only the provider-specific key and
    model while retaining the existing credential store.
    """
    cfg = openai_config()
    selected = str(provider or cfg.get("provider") or "openai").strip().lower()
    if selected == "anthropic":
        selected = "claude"
    if selected not in {"openai", "gemini", "claude"}:
        raise ValueError(f"Unsupported API provider: {selected}")
    if selected == "gemini":
        api_key = cfg.get("geminiApiKey", "")
        default_model = cfg.get("geminiModel", DEFAULT_GEMINI_MODEL)
    elif selected == "claude":
        api_key = cfg.get("anthropicApiKey", "")
        default_model = cfg.get("anthropicModel", DEFAULT_ANTHROPIC_MODEL)
    else:
        api_key = cfg.get("apiKey", "")
        default_model = cfg.get("model", DEFAULT_OPENAI_MODEL)
    result = {
        "provider": selected,
        "apiKey": str(api_key or "").strip(),
        "model": str(model or default_model or "").strip(),
        "enabled": bool(cfg.get("enabled")),
    }
    # Keep this field present for task snapshots so provider_default means
    # "let the selected model decide" rather than inheriting a hidden global
    # Astra environment variable.
    result["reasoningEffort"] = str(reasoning_effort or "provider_default").strip().lower().replace("-", "_")
    return result


def selected_llm_config():
    bound = _TASK_LLM_CONFIG.get()
    if isinstance(bound, dict):
        return deepcopy(bound)
    cfg = openai_config()
    provider = cfg["provider"]
    if provider == "gemini":
        model = cfg["geminiModel"]
        return {
            "provider": provider,
            "apiKey": cfg["geminiApiKey"],
            "model": model,
            "enabled": cfg["enabled"],
            "reasoningEffort": configured_global_reasoning_effort(mode="api", provider=provider, model=model, runtime=True),
        }
    if provider in {"claude", "anthropic"}:
        model = cfg["anthropicModel"]
        return {
            "provider": "claude",
            "apiKey": cfg["anthropicApiKey"],
            "model": model,
            "enabled": cfg["enabled"],
            "reasoningEffort": configured_global_reasoning_effort(mode="api", provider="claude", model=model, runtime=True),
        }
    model = cfg["model"]
    return {
        "provider": "openai",
        "apiKey": cfg["apiKey"],
        "model": model,
        "enabled": cfg["enabled"],
        "reasoningEffort": configured_global_reasoning_effort(mode="api", provider="openai", model=model, runtime=True),
    }


def mask_secret(value):
    value = str(value or "").strip()
    if not value:
        return ""
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:3]}...{value[-4:]}"


def read_env_file():
    env_path = ROOT / ".env"
    rows = []
    if env_path.exists():
        try:
            rows = env_path.read_text(encoding="utf-8").splitlines()
        except Exception:
            rows = []
    return rows


def _keyring_module():
    try:
        import keyring
    except ImportError as exc:
        raise RuntimeError("OS credential store support is not installed") from exc
    return keyring


def _store_secret_value(key: str, value: str) -> None:
    _keyring_module().set_password(SECRET_STORE_SERVICE, key, str(value))


def _load_secret_value(key: str) -> str:
    try:
        return str(_keyring_module().get_password(SECRET_STORE_SERVICE, key) or "")
    except Exception:
        return ""


def write_env_values(updates):
    env_path = ROOT / ".env"
    rows = read_env_file()
    for key, value in updates.items():
        if key in SECRET_ENV_KEYS and value is not None:
            _store_secret_value(key, str(value))
    seen = set()
    next_rows = []
    for line in rows:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            next_rows.append(line)
            continue
        key, _ = line.split("=", 1)
        key = key.strip()
        if key in updates:
            value = updates[key]
            if value is None:
                next_rows.append(line)
            elif key in SECRET_ENV_KEYS:
                pass
            else:
                next_rows.append(f"{key}={value}")
                os.environ[key] = str(value)
            seen.add(key)
        else:
            next_rows.append(line)
    for key, value in updates.items():
        if key not in seen and value is not None and key not in SECRET_ENV_KEYS:
            next_rows.append(f"{key}={value}")
            os.environ[key] = str(value)
        elif value is not None and key in SECRET_ENV_KEYS:
            os.environ[key] = str(value)
    # Secret values are stored through the OS credential service, never in .env.
    # codeql[py/clear-text-storage-sensitive-data]
    env_path.write_text("\n".join(next_rows).rstrip() + "\n", encoding="utf-8")


def bool_override(value):
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return None


def dart_api_key():
    load_dotenv()
    return os.environ.get("DART_API_KEY", "").strip()


def fred_api_key():
    load_dotenv()
    return os.environ.get("FRED_API_KEY", "").strip()


def bok_api_key():
    load_dotenv()
    return os.environ.get("BOK_API_KEY", "").strip()


def toss_open_api_key():
    load_dotenv()
    return os.environ.get("TOSS_OPEN_API_KEY", "").strip()


def toss_open_api_enabled() -> bool:
    """Return whether the optional read-only Toss provider may be used.

    Credentials alone never activate the REST/realtime provider: the local
    operator must explicitly opt in with ``FOLIO_ENABLE_TOSS_OPEN_API``.
    """
    load_dotenv()
    return os.environ.get("FOLIO_ENABLE_TOSS_OPEN_API", "").strip().lower() in {"1", "true", "yes", "on"}


def toss_open_api_client_id():
    load_dotenv()
    return os.environ.get("TOSS_OPEN_API_CLIENT_ID", "").strip()


def toss_open_api_client_secret():
    load_dotenv()
    return os.environ.get("TOSS_OPEN_API_CLIENT_SECRET", os.environ.get("TOSS_OPEN_API_KEY", "")).strip()


def toss_open_api_base_url():
    load_dotenv()
    # REST and realtime share this opt-in settings boundary.  A blank value in
    # a copied template is not a custom endpoint; use the pinned official REST
    # origin instead.
    value = os.environ.get("TOSS_OPEN_API_BASE_URL", "").strip()
    return value or TOSS_OPEN_API_DEFAULT_BASE_URL


def sec_user_agent():
    load_dotenv()
    return os.environ.get("SEC_USER_AGENT", "MarketResearchArchive/1.0 contact@example.com").strip()


def use_llm_analysis():
    load_dotenv()
    if os.environ.get("AI_AGENT_ENABLED") is not None:
        return ai_agent_enabled()
    explicit = os.environ.get("USE_LLM_ANALYSIS")
    if explicit is not None:
        return explicit.strip().lower() not in {"0", "false", "no", "off"}
    return ai_agent_enabled()


def use_web_search_for_briefing():
    load_dotenv()
    return os.environ.get("USE_LLM_BRIEFING", os.environ.get("USE_OPENAI_BRIEFING", "1")).strip().lower() not in {"0", "false", "no", "off"}


def use_web_search_for_analysis():
    return use_llm_analysis()


# ---------------------------------------------------------------------------
# HTTP transport
# ---------------------------------------------------------------------------

def post_json(url, body, headers, timeout):
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            body_text = exc.read().decode("utf-8", errors="replace")
        except Exception:
            body_text = ""
        raise LlmRequestError(exc.code, exc.reason, body_text[:900]) from exc


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------

def strip_llm_citation_markers(text):
    text = str(text or "")
    text = re.sub(r"[-]*cite[-]*(?:turn\d+(?:search|news|source|ref)\d+[-]*)+", "", text)
    text = re.sub(r"cite\S+", "", text)
    text = re.sub(r"□cite□(?:turn\d+(?:search|news|source|ref)\d+□?)+", "", text)
    text = re.sub(r"\[\s*(?:turn\d+(?:search|news|source|ref)\d+\s*)+\]", "", text)
    text = re.sub(r"\s+([.,;:!?])", r"\1", text)
    return text


def extract_response_text(payload):
    if isinstance(payload.get("output_text"), str):
        return strip_llm_citation_markers(payload["output_text"]).strip()
    parts = []
    for item in payload.get("output", []) or []:
        for content in item.get("content", []) or []:
            if isinstance(content.get("text"), str):
                parts.append(content["text"])
    return strip_llm_citation_markers("\n".join(parts)).strip()


def extract_gemini_text(payload):
    parts = []
    for candidate in payload.get("candidates", []) or []:
        content = candidate.get("content", {}) or {}
        for part in content.get("parts", []) or []:
            if isinstance(part.get("text"), str):
                parts.append(part["text"])
    return "\n".join(parts).strip()


def extract_anthropic_text(payload):
    parts = []
    for block in payload.get("content", []) or []:
        if block.get("type") == "text" and isinstance(block.get("text"), str):
            parts.append(block["text"])
    return "\n".join(parts).strip()


def extract_openai_usage(payload):
    usage = payload.get("usage") or {}
    if not isinstance(usage, dict):
        return {}
    return {
        "inputTokens": usage.get("input_tokens"),
        "outputTokens": usage.get("output_tokens"),
        "totalTokens": usage.get("total_tokens"),
        "providerRaw": usage,
    }


def extract_gemini_usage(payload):
    usage = payload.get("usageMetadata") or {}
    if not isinstance(usage, dict):
        return {}
    input_tokens = usage.get("promptTokenCount")
    output_tokens = usage.get("candidatesTokenCount")
    total_tokens = usage.get("totalTokenCount")
    return {
        "inputTokens": input_tokens,
        "outputTokens": output_tokens,
        "totalTokens": total_tokens,
        "providerRaw": usage,
    }


def extract_anthropic_usage(payload):
    usage = payload.get("usage") or {}
    if not isinstance(usage, dict):
        return {}
    input_tokens = usage.get("input_tokens")
    output_tokens = usage.get("output_tokens")
    total = None
    if input_tokens is not None or output_tokens is not None:
        total = int(input_tokens or 0) + int(output_tokens or 0)
    return {
        "inputTokens": input_tokens,
        "outputTokens": output_tokens,
        "totalTokens": total,
        "providerRaw": usage,
    }


def extract_json_object(text):
    raw = str(text or "").strip()
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.I | re.S).strip()
    try:
        return json.loads(raw)
    except Exception:
        pass
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        return json.loads(raw[start:end + 1])
    raise ValueError("LLM response did not contain a JSON object")


def json_repair_prompt():
    return (
        "You convert malformed model output into valid JSON for a market narrative memory tool. "
        "Return only one JSON object with an `entries` array. "
        "If the input does not contain usable entries, return {\"entries\": []}."
    )


# ---------------------------------------------------------------------------
# Provider request functions
# ---------------------------------------------------------------------------

def request_openai(cfg, prompt, context, web_search=False, max_output_tokens=None, json_mode=False, include_usage=False, timeout_seconds=None):
    body = {
        "model": cfg["model"],
        "instructions": prompt,
        "input": context,
        "max_output_tokens": int(max_output_tokens or os.environ.get("LLM_MAX_OUTPUT_TOKENS", os.environ.get("OPENAI_MAX_OUTPUT_TOKENS", "7000"))),
    }
    if cfg["model"] == "gpt-6-astra":
        # A task snapshot with ``provider_default`` deliberately omits the
        # reasoning field.  A legacy/global config that does not carry the
        # field continues to honor the existing environment default.
        configured_effort = cfg.get("reasoningEffort")
        if configured_effort is not None and str(configured_effort).strip().lower() in {
            "provider_default", "default", "providerdefault",
        }:
            effort = ""
        else:
            effort = str(configured_effort or os.environ.get("OPENAI_ASTRA_REASONING_EFFORT", "low")).strip().lower() or "low"
            if effort in {"none", "minimal"}:
                effort = "low"
            if effort not in {"low", "medium", "high", "xhigh", "max"}:
                raise ValueError("Invalid OPENAI_ASTRA_REASONING_EFFORT")
        if effort:
            body["reasoning"] = {"effort": effort}
    if json_mode:
        body["text"] = {"format": {"type": "json_object"}}
        # OpenAI Responses API는 json_object 포맷 사용 시 input 안에 literal "json"을 요구한다.
        # 프롬프트(instructions)가 아니라 input(context)을 검사하므로, 없으면 지시문을 덧붙인다.
        if "json" not in (context or "").lower():
            body["input"] = f"{context}\n\n위 자료를 바탕으로 하나의 유효한 JSON 객체로만 응답하세요."
    if web_search:
        body["tools"] = [{"type": os.environ.get("OPENAI_WEB_SEARCH_TOOL", "web_search")}]
    payload = post_json(
        OPENAI_RESPONSES_URL,
        body,
        {
            "Authorization": f"Bearer {cfg['apiKey']}",
            "Content-Type": "application/json",
        },
        int(timeout_seconds or os.environ.get("LLM_TIMEOUT_SECONDS", os.environ.get("OPENAI_TIMEOUT_SECONDS", "120"))),
    )
    # A partial paragraph is not a completed report. Let each producer's existing
    # failure/fallback policy handle it without leaking response content to logs.
    if payload.get("status") not in {None, "completed"} or payload.get("error"):
        raise RuntimeError("OpenAI response did not complete")
    if any(
        content.get("type") == "refusal"
        for item in payload.get("output", []) or []
        for content in item.get("content", []) or []
    ):
        raise RuntimeError("OpenAI response refused")
    response_text = extract_response_text(payload)
    if not response_text:
        raise RuntimeError("OpenAI response contained no text")
    result = (response_text, payload.get("id", ""))
    if include_usage:
        return (*result, extract_openai_usage(payload))
    return result


def request_gemini(cfg, prompt, context, web_search=False, max_output_tokens=None, json_mode=False, include_usage=False, timeout_seconds=None):
    model = urllib.parse.quote(cfg["model"], safe="")
    body = {
        "system_instruction": {"parts": [{"text": prompt}]},
        "contents": [{"parts": [{"text": context}]}],
        "generationConfig": {
            "maxOutputTokens": int(max_output_tokens or os.environ.get("LLM_MAX_OUTPUT_TOKENS", os.environ.get("OPENAI_MAX_OUTPUT_TOKENS", "7000"))),
        },
    }
    if web_search:
        body["tools"] = [{"google_search": {}}]
    elif json_mode:
        body["generationConfig"]["responseMimeType"] = "application/json"
    else:
        body["generationConfig"]["responseMimeType"] = "text/plain"
    payload = post_json(
        GEMINI_GENERATE_URL.format(model=model),
        body,
        {
            "x-goog-api-key": cfg["apiKey"],
            "Content-Type": "application/json",
        },
        int(timeout_seconds or os.environ.get("LLM_TIMEOUT_SECONDS", os.environ.get("OPENAI_TIMEOUT_SECONDS", "120"))),
    )
    result = (extract_gemini_text(payload), "")
    if include_usage:
        return (*result, extract_gemini_usage(payload))
    return result


def request_claude(cfg, prompt, context, web_search=False, max_output_tokens=None, json_mode=False, include_usage=False, timeout_seconds=None):
    body = {
        "model": cfg["model"],
        "max_tokens": int(max_output_tokens or os.environ.get("LLM_MAX_OUTPUT_TOKENS", os.environ.get("OPENAI_MAX_OUTPUT_TOKENS", "7000"))),
        "system": prompt + ("\n\nReturn only one valid JSON object. No prose, no Markdown." if json_mode else ""),
        "messages": [{"role": "user", "content": context}],
    }
    if web_search:
        body["tools"] = [{
            "type": os.environ.get("ANTHROPIC_WEB_SEARCH_TOOL", "web_search_20250305"),
            "name": "web_search",
            "max_uses": int(os.environ.get("LLM_WEB_SEARCH_MAX_USES", "5")),
        }]
    payload = post_json(
        ANTHROPIC_MESSAGES_URL,
        body,
        {
            "x-api-key": cfg["apiKey"],
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        },
        int(timeout_seconds or os.environ.get("LLM_TIMEOUT_SECONDS", os.environ.get("OPENAI_TIMEOUT_SECONDS", "120"))),
    )
    result = (extract_anthropic_text(payload), payload.get("id", ""))
    if include_usage:
        return (*result, extract_anthropic_usage(payload))
    return result


def request_llm_text(cfg, prompt, context, *, web_search=False, max_output_tokens=None, json_mode=False, include_usage=False, timeout_seconds=None):
    if cfg["provider"] == "gemini":
        return request_gemini(cfg, prompt, context, web_search=web_search, max_output_tokens=max_output_tokens, json_mode=json_mode, include_usage=include_usage, timeout_seconds=timeout_seconds)
    if cfg["provider"] == "claude":
        return request_claude(cfg, prompt, context, web_search=web_search, max_output_tokens=max_output_tokens, json_mode=json_mode, include_usage=include_usage, timeout_seconds=timeout_seconds)
    return request_openai(cfg, prompt, context, web_search=web_search, max_output_tokens=max_output_tokens, json_mode=json_mode, include_usage=include_usage, timeout_seconds=timeout_seconds)
