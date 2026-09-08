from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from features.agent_mode import schema
from features.agent_mode import service


def _read_text_arg(value: str) -> str:
    if value == "-":
        return sys.stdin.read()
    path = Path(value)
    if not path.is_absolute():
        path = schema.ROOT / path
    return path.read_text(encoding="utf-8")


def _read_json_arg(value: str) -> dict:
    text = _read_text_arg(value)
    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise ValueError("JSON writeback payload must be an object")
    return payload


def _print_json(payload: dict) -> None:
    # scrub_secrets is the CLI's mandatory final output boundary.
    # codeql[py/clear-text-logging-sensitive-data]
    print(  # lgtm[py/clear-text-logging-sensitive-data]
        json.dumps(schema.scrub_secrets(payload), ensure_ascii=False, indent=2)
    )


def _result_summary(result: Any) -> dict:
    if not isinstance(result, dict):
        return {"ok": True, "resultType": type(result).__name__}
    summary = {"ok": True}
    for key in [
        "id",
        "filename",
        "date",
        "title",
        "headline",
        "topicKey",
        "topicLabel",
        "path",
        "savedAt",
    ]:
        if result.get(key):
            summary[key] = result.get(key)
    if result.get("generation"):
        summary["generation"] = result.get("generation")
    if result.get("quality"):
        quality = result.get("quality") or {}
        summary["quality"] = {
            "score": quality.get("score"),
            "grade": quality.get("grade"),
            "status": quality.get("status"),
            "warningCount": len(quality.get("warnings") or []),
        }
    if "personalOverlay" in result:
        overlay = result.get("personalOverlay") or {}
        summary["personalOverlay"] = {
            "status": overlay.get("status") or overlay.get("generation", {}).get("status"),
            "stance": overlay.get("stance"),
        }
    if "delta" in result:
        delta = result.get("delta") or {}
        summary["delta"] = {
            "ticker": delta.get("ticker"),
            "verdict": delta.get("verdict"),
            "savedAt": delta.get("saved_at") or delta.get("savedAt"),
        }
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m features.agent_mode.cli",
        description="Prepare Folio Board Agent Context Packs and write agent-authored outputs back to the normal stores.",
    )
    parser.add_argument("task_type", choices=sorted(schema.TASK_TYPES), help="Agent task type")
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--prepare", action="store_true", help="Build and save an Agent Context Pack")
    action.add_argument("--write-markdown", metavar="PATH|-", help="Write an agent-authored Markdown result back")
    action.add_argument("--write-json", metavar="PATH|-", help="Write an agent-authored JSON result back")

    parser.add_argument("--pack", help="Context pack path for writeback")
    parser.add_argument("--date", help="Report date, YYYY-MM-DD")
    parser.add_argument("--strict-date", action="store_true", help="For briefing, require the requested date window")
    parser.add_argument("--query", help="Company query or ticker for company_analysis")
    parser.add_argument("--topic-key", default="custom", help="Topic key for topic_report")
    parser.add_argument("--custom-label", default="", help="Custom topic label")
    parser.add_argument("--user-context", default="", help="User context for topic_report")
    parser.add_argument("--no-planner", action="store_true", help="Disable topic planner for topic_report")
    parser.add_argument("--report-kind", help="briefing, company_analysis, or topic_report for personal_overlay")
    parser.add_argument("--report-id", help="Report id/date for personal_overlay")
    parser.add_argument("--artifact-type", help="Target artifact type for quality_repair")
    parser.add_argument("--artifact-id", help="Target artifact id for quality_repair")
    parser.add_argument("--ticker", help="Ticker for thesis_delta")
    parser.add_argument("--period", default="90d", help="Period for thesis_delta")
    parser.add_argument("--limit", type=int, default=12, help="Evidence limit for thesis_delta")
    parser.add_argument("--quality-mode", default="diagnose_only", help="Quality generation mode")
    parser.add_argument("--web-search", action="store_true", help="Add configured company external search context")
    parser.add_argument("--print-context", action="store_true", help="Print prompt/context after prepare")
    return parser


def prepare(args: argparse.Namespace) -> None:
    pack, path = service.prepare_pack(
        args.task_type,
        date=args.date,
        strict_date=args.strict_date,
        query=args.query,
        topic_key=args.topic_key,
        custom_label=args.custom_label,
        user_context=args.user_context,
        use_planner=not args.no_planner,
        report_kind=args.report_kind,
        report_id=args.report_id,
        artifact_type=args.artifact_type,
        artifact_id=args.artifact_id,
        ticker=args.ticker,
        period=args.period,
        limit=args.limit,
        quality_mode=args.quality_mode,
        web_search=args.web_search,
    )
    payload = {
        "ok": True,
        "action": "prepare",
        "taskType": pack.get("taskType"),
        "artifactType": pack.get("artifactType"),
        "artifactId": pack.get("artifactId"),
        "title": pack.get("title"),
        "packPath": str(path),
        "saveTarget": pack.get("saveTarget"),
        "outputContract": pack.get("outputContract"),
        "next": "Read the pack prompt/context, write the requested output, then run this CLI with --write-markdown or --write-json.",
    }
    if args.print_context:
        payload["prompt"] = pack.get("prompt", "")
        payload["context"] = pack.get("context", "")
        payload["agentInstructions"] = pack.get("agentInstructions", "")
    _print_json(payload)


def writeback(args: argparse.Namespace) -> None:
    if not args.pack:
        raise ValueError("--pack is required for writeback")
    pack = schema.read_pack(args.pack)
    requested = schema.normalize_task_type(args.task_type)
    actual = schema.normalize_task_type(pack.get("taskType"))
    if requested != actual:
        raise ValueError(f"Task type mismatch: command={requested}, pack={actual}")
    markdown = None
    payload = None
    if args.write_markdown:
        markdown = _read_text_arg(args.write_markdown)
    if args.write_json:
        payload = _read_json_arg(args.write_json)
    result = service.writeback_pack(pack, markdown=markdown, payload=payload)
    updated = schema.update_pack_status(args.pack, status="done", result=_result_summary(result))
    _print_json({
        "ok": True,
        "action": "writeback",
        "taskType": actual,
        "packPath": str(Path(args.pack)),
        "packStatus": updated.get("status"),
        "result": _result_summary(result),
    })


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.prepare:
            prepare(args)
        else:
            writeback(args)
        return 0
    except Exception:
        if args.pack:
            try:
                schema.update_pack_status(args.pack, status="failed", result={"error": "agent_writeback_failed"})
            except Exception:
                pass
        _print_json({"ok": False, "error": "agent_command_failed"})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
