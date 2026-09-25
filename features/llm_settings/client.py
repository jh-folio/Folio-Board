"""CLI generation configuration and shared environment settings."""
import json
import os
import re
from pathlib import Path

from features.llm_settings.model_catalog import normalize_model_id
from features.llm_settings.reasoning import (
    is_supported_reasoning_effort,
    normalize_reasoning_effort,
)

ROOT = Path(__file__).resolve().parent.parent.parent

GLOBAL_REASONING_ENV = "AI_AGENT_REASONING_EFFORT"
TOSS_OPEN_API_DEFAULT_BASE_URL = "https://openapi.tossinvest.com"
SECRET_STORE_SERVICE = "Folio OS"
SECRET_ENV_KEYS = {
    "DART_API_KEY",
    "FRED_API_KEY",
    "BOK_API_KEY",
    "TOSS_OPEN_API_KEY",
    "TOSS_OPEN_API_CLIENT_SECRET",
    "NOTION_TOKEN",
    "IMGBB_API_KEY",
}


# A producer binds one resolved task configuration for the duration of its
# request.  Feature modules intentionally import ``selected_cli_config``
# directly, so a ContextVar gives all nested calls the same provider/model
# without mutating ``os.environ`` or the process-wide global setting.


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
            if key in {"OPENAI_API_KEY", "GEMINI_API_KEY", "ANTHROPIC_API_KEY"}:
                continue
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
    require_cli_mode()
    return "llm_cli"


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
            seen.add(key)
        else:
            next_rows.append(line)
    for key, value in updates.items():
        if key not in seen and value is not None and key not in SECRET_ENV_KEYS:
            next_rows.append(f"{key}={value}")
    # Secret values are stored through the OS credential service, never in .env.
    # codeql[py/clear-text-storage-sensitive-data]
    from features.common.atomic_replace import write_bytes_atomic
    if env_path.exists() and updates.get("AI_AGENT_MODE") == "cli":
        previous_modes = [line.split("=", 1)[1].strip().strip("\"'").lower().replace("-", "_")
                          for line in rows if "=" in line and line.split("=", 1)[0].strip() == "AI_AGENT_MODE"]
        if any(mode in {"api", "llm_api"} for mode in previous_modes):
            backup = env_path.with_name(".env.llm-api-transition.bak")
            if not backup.exists():
                write_bytes_atomic(backup, env_path.read_bytes())
    write_bytes_atomic(env_path, ("\n".join(next_rows).rstrip() + "\n").encode("utf-8"))
    for key, value in updates.items():
        if value is not None:
            os.environ[key] = str(value)


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
    """Whether the briefing find-pass may use web search — distinct from
    whether LLM generation itself is on.

    This used to read `USE_LLM_BRIEFING` (the legacy LLM-enable flag `
    ai_agent_enabled()` also reads), so the documented `USE_WEB_SEARCH_FOR_BRIEFING`
    variable had no effect at all — turning it off did nothing. Web search
    obviously still needs the LLM path enabled to run at all.
    """
    if not ai_agent_enabled():
        return False
    load_dotenv()
    return os.environ.get("USE_WEB_SEARCH_FOR_BRIEFING", "1").strip().lower() not in {"0", "false", "no", "off"}


def use_web_search_for_analysis():
    """Same distinction as `use_web_search_for_briefing()`: this used to just
    return `use_llm_analysis()` outright, so `USE_WEB_SEARCH_FOR_ANALYSIS` was
    never actually read."""
    if not use_llm_analysis():
        return False
    load_dotenv()
    return os.environ.get("USE_WEB_SEARCH_FOR_ANALYSIS", "1").strip().lower() not in {"0", "false", "no", "off"}


# ---------------------------------------------------------------------------
# HTTP transport
# ---------------------------------------------------------------------------



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


def require_cli_mode():
    if ai_agent_mode() == "api":
        from features.llm_settings.task_policy import TaskPolicyError
        raise TaskPolicyError("llm_api_removed", "LLM API 지원이 종료되었습니다. 설정에서 CLI를 선택해 저장하거나 AI를 꺼 주세요.", status=409)


def selected_cli_config():
    """Resolve a credential-free CLI configuration, inheriting the frozen task."""
    from features.llm_settings.task_runtime import current_task_policy, generation_mode
    policy = current_task_policy()
    if policy is not None:
        enabled = generation_mode(policy) == "llm_cli"
        return {**policy, "enabled": enabled}
    if not ai_agent_enabled():
        return {"enabled": False, "provider": "", "model": ""}
    require_cli_mode()
    from features.agent_mode.setup import configured_provider, configured_model
    provider = configured_provider()
    model = configured_model(provider) if provider != "auto" else ""
    return {"enabled": True, "provider": provider, "model": model,
            "reasoningEffort": configured_global_reasoning_effort(mode="cli", provider=provider, model=model)}


def request_cli_text(cfg, prompt, context, *, web_search=False, max_output_tokens=None,
                     json_mode=False, include_usage=False, timeout_seconds=None, facts_sink=None,
                     result_sink=None):
    """Execute through the existing CLI bridge; never resolve API credentials.

    CLI adapters do not promise an exact output token cap. Keep the caller's
    argument for compatibility, and let the bridge enforce its output bound.
    result_sink is opt-in and memory-only; never serialize it into report data.
    """
    if cfg.get("mode") in {"api", "llm_api"}:
        raise ValueError("llm_api_removed")
    if not cfg.get("enabled") or not ai_agent_enabled():
        raise RuntimeError("ai_disabled")
    from features.agent_mode.bridge import run_agent_prompt
    suffix = "\nReturn only valid JSON." if json_mode else ""
    response = run_agent_prompt(
        str(prompt) + suffix + "\n\n" + str(context),
        adapter=str(cfg.get("provider") or ""), model=str(cfg.get("model") or ""),
        reasoning_effort=str(cfg.get("reasoningEffort") or ""),
        timeout=timeout_seconds or 300, web_search=web_search,
        diagnostic_primary=False,
        **({"observe_result": True} if facts_sink is not None else {}),
        **({"result_sink": result_sink} if result_sink is not None else {}),
    )
    if facts_sink is not None:
        facts_sink.update(response.get("executionFacts") or {})
    output = str(response.get("output") or "").strip()
    if not output:
        raise RuntimeError("cli_empty_response")
    result = (output, str(response.get("responseId") or ""))
    usage = {**(response.get("usage") or {}), "transport": "cli", "outputTokenCapEnforced": False}
    return (*result, usage) if include_usage else result
