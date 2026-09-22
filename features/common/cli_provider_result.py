"""CLI events to the shared private E0 result. No raw events are retained."""
from __future__ import annotations

import json
from urllib.parse import urlsplit

from features.common.execution_result import ExecutionResult, UsageFacts
from features.common.provider_result import Citation, ProviderPayload, ResponseBlock


def _string(value):
    return value if isinstance(value, str) else None


def _count(value):
    return value if type(value) is int and 0 <= value <= 1_000_000_000_000 else None


def _usage(value, adapter: str) -> UsageFacts:
    value = value if isinstance(value, dict) else {}
    counts = {name: _count(value.get(key)) for name, key in (
        ("input_tokens", "input_tokens"), ("output_tokens", "output_tokens"),
        ("total_tokens", "total_tokens"), ("reasoning_tokens", "reasoning_output_tokens"),
        ("cached_tokens", "cache_read_input_tokens" if adapter == "claude" else "cached_input_tokens"),
    )}
    return UsageFacts(**counts, source="provider" if any(v is not None for v in counts.values()) else "unavailable")


def _citations(block, index, start, end):
    values = block.get("citations")
    if not isinstance(values, list):
        return ()
    output = []
    for value in values:
        if not isinstance(value, dict):
            continue
        kind = _string(value.get("type"))
        units = {"char_location": ("char", "start_char_index", "end_char_index"),
                 "page_location": ("page", "start_page_number", "end_page_number"),
                 "content_block_location": ("block", "start_block_index", "end_block_index")}
        if kind not in {*units, "web_search_result_location", "search_result_location"}:
            continue
        url = _string(value.get("url"))
        try:
            parsed = urlsplit(url or "")
            if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
                url = None
        except ValueError:
            url = None
        unit, lo, hi = units.get(kind, (None, "", ""))
        source_id = _string(value.get("encrypted_index"))
        doc = _count(value.get("document_index"))
        if source_id is None and doc is not None:
            source_id = f"document:{doc}"
        output.append(Citation(index, start, end, source_id, url,
                               _string(value.get("document_title") or value.get("title")),
                               _string(value.get("cited_text")), _count(value.get(lo)), _count(value.get(hi)), unit))
    return tuple(output)


def observe_execution(adapter: str, stdout: str, *, returncode: int | None = None) -> ExecutionResult:
    """No requested-model fallback, inferred totals or automatic resumption.

    Claude text-block citations survive only if actually present. Codex exec has
    no verified native-citation schema here; Markdown links are not citations.
    A session ID alone does not enable continuation in the Folio CLI bridge.
    """
    text = None
    blocks, citations = (), ()
    model = raw_stop = session = response_id = None
    status = reason = "unknown"
    continuation = "unknown"
    usage = UsageFacts()
    message_parts, message_blocks, message_citations = [], [], []
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except (ValueError, TypeError):
            continue
        if not isinstance(event, dict):
            continue
        kind = event.get("type")
        if adapter == "claude":
            if event.get("parent_tool_use_id") is not None:
                continue
            session = _string(event.get("session_id")) or session
            if kind == "assistant":
                message = event.get("message")
                if not isinstance(message, dict):
                    continue
                model = _string(message.get("model")) or model
                message_id = _string(message.get("id"))
                if message_id is None or message_id != response_id:
                    message_parts, message_blocks, message_citations = [], [], []
                    status = reason = "unknown"
                    continuation = "unknown"
                response_id = message_id
                content = message.get("content")
                if not isinstance(content, list):
                    continue
                parts, current_blocks, current_citations = message_parts, message_blocks, message_citations
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    if block.get("type") == "text" and isinstance(block.get("text"), str):
                        start = len("\n".join(parts)) + bool(parts)
                        body = block["text"]
                        parts.append(body)
                        current_citations.extend(_citations(block, len(current_blocks), start, start + len(body)))
                        current_blocks.append(ResponseBlock("text", body))
                    elif _string(block.get("type")) in {"tool_use", "server_tool_use"}:
                        current_blocks.append(ResponseBlock("tool_use", identifier=_string(block.get("id"))))
                if parts:
                    text = "\n".join(parts)
                    citations = tuple(current_citations)
                blocks = tuple(current_blocks)
                stop = _string(message.get("stop_reason"))
            elif kind == "result":
                body = _string(event.get("result"))
                if body is not None:
                    citations = tuple(c.remap(text or "", body) for c in citations)
                    text = body
                usage = _usage(event.get("usage"), adapter)
                stop = _string(event.get("stop_reason"))
                subtype = event.get("subtype")
                if subtype == "error_max_turns":
                    stop = "max_turns"
                if event.get("is_error") is True:
                    status, reason = "failed", "other"
                elif subtype == "success" and status != "incomplete":
                    status, reason, continuation = "completed", "end", "none"
            else:
                continue
            if stop:
                raw_stop = stop
            if stop in {"max_tokens", "max_turns"}:
                status, reason = "incomplete", "limit"
            elif stop in {"pause_turn", "tool_use"}:
                status, reason = "incomplete", "other"
                continuation = "paused" if stop == "pause_turn" else "tool_pending"
            elif stop == "end_turn":
                continuation = "none"
                if status == "incomplete" and reason == "other":
                    status = reason = "unknown"
            elif stop == "tool_error":
                status, reason = "failed", "tool_error"
        elif adapter == "codex":
            if kind == "thread.started":
                session = _string(event.get("thread_id"))
            item = event.get("item")
            item = item if isinstance(item, dict) else {}
            if kind == "item.completed" and item.get("type") == "agent_message" and isinstance(item.get("text"), str):
                text = item["text"]
                blocks = (ResponseBlock("text", text, _string(item.get("id"))),)
            if kind == "turn.completed":
                status, reason, raw_stop, continuation = "completed", "end", kind, "none"
                usage = _usage(event.get("usage"), adapter)
            elif kind == "turn.failed":
                status, reason, raw_stop = "failed", "other", kind
    if returncode not in {None, 0} and status != "incomplete":
        status, reason = "failed", "other"
    provider = ProviderPayload(
        adapter=adapter if adapter in {"codex", "claude", "antigravity"} else "unknown",
        model=model, raw_stop_reason=raw_stop, blocks=blocks, citations=citations,
        citation_capability="observed" if citations else "unknown",
        continuation_state=continuation, session_id=session,
    )
    return ExecutionResult(text=text, response_id=response_id, provider=provider,
                           completion_status=status, stop_reason=reason, usage=usage,
                           transport_status="unknown" if returncode is None else "succeeded" if returncode == 0 else "failed")
