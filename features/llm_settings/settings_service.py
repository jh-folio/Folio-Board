"""Application settings — read public view and save credential-backed configuration."""
import os
from pathlib import Path

from features.llm_settings.client import (
    ai_agent_enabled,
    ai_agent_mode,
    dart_api_key,
    fred_api_key,
    bok_api_key,
    mask_secret,
    load_dotenv,
    openai_config,
    toss_open_api_base_url,
    toss_open_api_client_id,
    toss_open_api_client_secret,
    toss_open_api_enabled,
    toss_open_api_key,
    use_llm_analysis,
    write_env_values,
)
from features.notion_export.service import public_notion_settings
from features.llm_settings.provider_status import PROVIDER_INFO
from features.llm_settings.model_catalog import API_MODEL_FALLBACKS, choices_from_catalog, discover_api_models, normalize_model_id
from features.llm_settings.reasoning import (
    reasoning_choices,
    supported_reasoning_efforts,
)
from features.llm_settings.task_policy import public_task_policy, save_task_policy
from features.common.workspace import data_dir

ROOT = Path(__file__).resolve().parent.parent.parent
FEATURES_DIR = ROOT / "features"
MARKET_MEMORY_PROMPT_PATH = FEATURES_DIR / "market_memory" / "prompt.md"
DATA_DIR = data_dir()

API_MODEL_CHOICES = API_MODEL_FALLBACKS


def _reasoning_by_model(mode: str, provider: str, model_choices: list[dict]) -> dict[str, list[dict[str, str]]]:
    """Project provider/model-specific effort choices for the Settings UI."""
    return {
        str(choice.get("value")): reasoning_choices(mode, provider, str(choice.get("value")))
        for choice in model_choices
        if isinstance(choice, dict) and choice.get("value")
    }


def read_market_memory_prompt():
    try:
        return MARKET_MEMORY_PROMPT_PATH.read_text(encoding="utf-8")
    except Exception:
        return ""


def public_settings(*, refresh: bool = False):
    load_dotenv()
    cfg = openai_config()
    openai_catalog = discover_api_models("openai", api_key=cfg["apiKey"], refresh=refresh)
    gemini_catalog = discover_api_models("gemini", api_key=cfg["geminiApiKey"], refresh=refresh)
    claude_catalog = discover_api_models("claude", api_key=cfg["anthropicApiKey"], refresh=refresh)
    global_reasoning_effort = _public_global_reasoning_effort()
    payload = {
        "agent": {
            "enabled": ai_agent_enabled(),
            "mode": ai_agent_mode(),
        },
        "llm": {
            "provider": cfg["provider"],
            "enabled": cfg["enabled"],
            # ``provider_default`` is the in-memory default for installations
            # that have never saved a global effort.  Runtime preserves the
            # legacy Astra environment behavior until the user saves a value.
            "reasoningEffort": global_reasoning_effort,
            "envPath": str(ROOT / ".env"),
            "providers": {
                "openai": {"hasApiKey": bool(cfg["apiKey"]), "apiKeyMasked": mask_secret(cfg["apiKey"]), "model": cfg["model"], "modelChoices": choices_from_catalog(openai_catalog), "reasoningChoices": reasoning_choices("api", "openai", cfg["model"]), "reasoningByModel": _reasoning_by_model("api", "openai", choices_from_catalog(openai_catalog)), "modelDiscovery": {k: v for k, v in openai_catalog.items() if k != "modelChoices"}, **PROVIDER_INFO["openai"]},
                "gemini": {"hasApiKey": bool(cfg["geminiApiKey"]), "apiKeyMasked": mask_secret(cfg["geminiApiKey"]), "model": cfg["geminiModel"], "modelChoices": choices_from_catalog(gemini_catalog), "reasoningChoices": reasoning_choices("api", "gemini", cfg["geminiModel"]), "reasoningByModel": _reasoning_by_model("api", "gemini", choices_from_catalog(gemini_catalog)), "modelDiscovery": {k: v for k, v in gemini_catalog.items() if k != "modelChoices"}, **PROVIDER_INFO["gemini"]},
                "claude": {"hasApiKey": bool(cfg["anthropicApiKey"]), "apiKeyMasked": mask_secret(cfg["anthropicApiKey"]), "model": cfg["anthropicModel"], "modelChoices": choices_from_catalog(claude_catalog), "reasoningChoices": reasoning_choices("api", "claude", cfg["anthropicModel"]), "reasoningByModel": _reasoning_by_model("api", "claude", choices_from_catalog(claude_catalog)), "modelDiscovery": {k: v for k, v in claude_catalog.items() if k != "modelChoices"}, **PROVIDER_INFO["claude"]},
            },
        },
        "analysis": {
            "enabled": use_llm_analysis(),
        },
        "dart": {
            "hasApiKey": bool(dart_api_key()),
            "apiKeyMasked": mask_secret(dart_api_key()),
        },
        "fred": {
            "hasApiKey": bool(fred_api_key()),
            "apiKeyMasked": mask_secret(fred_api_key()),
        },
        "bok": {
            "hasApiKey": bool(bok_api_key()),
            "apiKeyMasked": mask_secret(bok_api_key()),
        },
        "openai": {
            "hasApiKey": bool(cfg["apiKey"]),
            "apiKeyMasked": mask_secret(cfg["apiKey"]),
            "model": cfg["model"],
            "enabled": cfg["enabled"],
            "envPath": str(ROOT / ".env"),
        },
        "notion": public_notion_settings(),
        # Task overrides contain no credentials.  Keep them beside the global
        # Agent settings so one Settings read gives the UI a consistent
        # revisioned snapshot.
        "taskPolicies": public_task_policy(),
    }
    # Settings must expose the opt-in path even while the provider is disabled;
    # otherwise the UI has no supported way to turn it on. This projection is
    # local and safe: it does not activate OAuth, acquire a process lock, or
    # expose an account, token, or secret.
    from features.common.market_data.toss_open_api import toss_provider_health

    toss_enabled = toss_open_api_enabled()
    toss_client_id = toss_open_api_client_id()
    toss_client_secret = toss_open_api_client_secret()
    toss_legacy_key = toss_open_api_key()
    payload["toss"] = {
        "enabled": toss_enabled,
        "hasApiKey": bool(toss_client_secret or toss_legacy_key),
        "apiKeyMasked": mask_secret(toss_client_secret or toss_legacy_key),
        "hasClientId": bool(toss_client_id),
        "clientIdMasked": mask_secret(toss_client_id),
        "hasClientSecret": bool(toss_client_secret),
        "clientSecretMasked": mask_secret(toss_client_secret),
        "baseUrl": toss_open_api_base_url(),
        "ready": bool(toss_enabled and toss_client_id and toss_client_secret),
        "health": toss_provider_health(),
    }
    return payload


def _public_global_reasoning_effort() -> str:
    """Read the explicitly saved global effort for the Settings projection."""
    load_dotenv()
    raw = os.environ.get("AI_AGENT_REASONING_EFFORT")
    if raw is None:
        return "provider_default"
    return str(raw).strip().lower().replace("-", "_") or "provider_default"


def save_settings(body):
    load_dotenv()
    data = body if isinstance(body, dict) else {}
    if "taskPolicies" in data:
        # The dedicated policy store owns validation, revision checks, and
        # atomic persistence.  Do this before global updates so an optimistic
        # conflict cannot partially apply a task-policy change.
        policy_body = data.get("taskPolicies") if isinstance(data.get("taskPolicies"), dict) else {}
        save_task_policy(policy_body)
    llm = data.get("llm", {})
    agent = data.get("agent", {}) if isinstance(data.get("agent", {}), dict) else {}
    openai = data.get("openai", {})
    updates = {}
    if "enabled" in agent:
        updates["AI_AGENT_ENABLED"] = "1" if bool(agent.get("enabled")) else "0"
        # Keep legacy switches aligned so older code paths and tools read the same policy.
        updates["USE_LLM_BRIEFING"] = updates["AI_AGENT_ENABLED"]
        updates["USE_LLM_ANALYSIS"] = updates["AI_AGENT_ENABLED"]
    agent_mode = str(agent.get("mode", "") or "").strip().lower().replace("-", "_")
    if agent_mode in {"cli", "llm_cli", "agent"}:
        updates["AI_AGENT_MODE"] = "cli"
    elif agent_mode in {"api", "llm_api"}:
        updates["AI_AGENT_MODE"] = "api"
    # The model panel owns the global reasoning selector.  Validate against
    # the concrete mode/provider/model tuple before touching the environment.
    # The linkage panel can omit this field and therefore cannot accidentally
    # reset a saved effort.
    if isinstance(llm, dict) and "reasoningEffort" in llm:
        from features.llm_settings.reasoning import is_supported_reasoning_effort, normalize_reasoning_effort

        selected_mode = "api" if agent_mode in {"api", "llm_api"} else "cli" if agent_mode in {"cli", "llm_cli", "agent"} else str(os.environ.get("AI_AGENT_MODE", "cli") or "cli").strip().lower()
        if selected_mode not in {"api", "cli"}:
            selected_mode = "cli"
        if selected_mode == "api":
            selected_provider = str(llm.get("provider") or os.environ.get("LLM_PROVIDER", "openai") or "openai").strip().lower()
            provider_data = (llm.get("providers") or {}).get(selected_provider, {}) if isinstance(llm.get("providers"), dict) else {}
            selected_model = str(provider_data.get("model") or (openai_config().get("geminiModel") if selected_provider == "gemini" else openai_config().get("anthropicModel") if selected_provider == "claude" else openai_config().get("model") or "")).strip()
        else:
            selected_provider = str(agent.get("provider") or os.environ.get("AGENT_CLI_PROVIDER", "") or "").strip().lower()
            if selected_provider == "auto":
                from features.agent_mode.setup import configured_provider

                selected_provider = configured_provider()
            from features.agent_mode.setup import configured_model

            selected_model = str(agent.get("model") or (configured_model(selected_provider) if selected_provider in {"codex", "claude", "antigravity"} else "")).strip()
        try:
            effort = normalize_reasoning_effort(llm.get("reasoningEffort"))
        except ValueError as exc:
            raise ValueError("지원하지 않는 추론 강도입니다.") from exc
        if not is_supported_reasoning_effort(selected_mode, selected_provider, selected_model, effort):
            raise ValueError("선택한 모델은 이 추론 강도를 지원하지 않습니다.")
        updates["AI_AGENT_REASONING_EFFORT"] = effort
    provider = str(llm.get("provider", "") or "").strip().lower()
    if provider in {"openai", "gemini", "claude"}:
        updates["LLM_PROVIDER"] = provider
    dart = data.get("dart", {}) if isinstance(data.get("dart", {}), dict) else {}
    dart_key = str(dart.get("apiKey", "") or "").strip()
    if dart_key:
        updates["DART_API_KEY"] = dart_key

    fred = data.get("fred", {}) if isinstance(data.get("fred", {}), dict) else {}
    fred_key = str(fred.get("apiKey", "") or "").strip()
    if fred_key:
        updates["FRED_API_KEY"] = fred_key

    bok = data.get("bok", {}) if isinstance(data.get("bok", {}), dict) else {}
    bok_key = str(bok.get("apiKey", "") or "").strip()
    if bok_key:
        updates["BOK_API_KEY"] = bok_key

    toss = data.get("toss", {}) if isinstance(data.get("toss", {}), dict) else {}
    if isinstance(toss.get("enabled"), bool):
        updates["FOLIO_ENABLE_TOSS_OPEN_API"] = "true" if toss["enabled"] else "false"
    toss_key = str(toss.get("apiKey", "") or "").strip()
    if toss_key:
        updates["TOSS_OPEN_API_KEY"] = toss_key
    toss_client_id = str(toss.get("clientId", "") or "").strip()
    if toss_client_id:
        updates["TOSS_OPEN_API_CLIENT_ID"] = toss_client_id
    toss_client_secret = str(toss.get("clientSecret", "") or "").strip()
    if toss_client_secret:
        updates["TOSS_OPEN_API_CLIENT_SECRET"] = toss_client_secret
    toss_base_url = str(toss.get("baseUrl", "") or "").strip()
    if toss_base_url:
        updates["TOSS_OPEN_API_BASE_URL"] = toss_base_url

    providers = llm.get("providers", {}) if isinstance(llm.get("providers", {}), dict) else {}
    openai_data = providers.get("openai", openai) or {}
    gemini_data = providers.get("gemini", {}) or {}
    claude_data = providers.get("claude", {}) or {}

    for key, model_key, env_key, model_provider in [
        (openai_data, "model", "OPENAI_MODEL", "openai"),
        (gemini_data, "model", "GEMINI_MODEL", "gemini"),
        (claude_data, "model", "ANTHROPIC_MODEL", "claude"),
    ]:
        model = normalize_model_id(model_provider, key.get(model_key, ""))
        if model:
            updates[env_key] = model

    # CLI global model is owned by the model panel.  A linkage-only save has no
    # ``agent.model`` field and therefore leaves this value untouched.
    cli_provider = str(agent.get("provider") or "").strip().lower()
    cli_model = str(agent.get("model") or "").strip()
    if cli_provider in {"codex", "claude", "antigravity"} and cli_model:
        if len(cli_model) > 120 or any(char.isspace() for char in cli_model):
            raise ValueError(f"Unsupported {cli_provider} model: {cli_model}")
        updates[f"FOLIO_AGENT_{cli_provider.upper()}_MODEL"] = normalize_model_id(cli_provider, cli_model)

    for key, api_key_env in [
        (openai_data, "OPENAI_API_KEY"),
        (gemini_data, "GEMINI_API_KEY"),
        (claude_data, "ANTHROPIC_API_KEY"),
    ]:
        api_key = str(key.get("apiKey", "") or "").strip()
        if api_key:
            updates[api_key_env] = api_key

    notion = data.get("notion", {}) if isinstance(data.get("notion", {}), dict) else {}
    notion_token = str(notion.get("token", "") or "").strip()
    if notion_token:
        updates["NOTION_TOKEN"] = notion_token
    notion_db_id = str(notion.get("dbId", "") or "").strip()
    if notion_db_id:
        updates["NOTION_DB_ID"] = notion_db_id

    if updates:
        write_env_values(updates)
    return public_settings()
