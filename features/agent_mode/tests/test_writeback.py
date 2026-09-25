import gzip
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pytest

from features.common.utils import read_json, write_json
from features.agent_mode import service
from features.agent_mode.briefing_contract import briefing_output_contract


def _valid_briefing_markdown(scope="both", us_companies=("NVIDIA", "Alphabet"), kr_companies=("Samsung Electronics", "SK hynix")):
    def block(market, companies):
        contract = briefing_output_contract(market, markets=[market])
        headings = []
        for section in contract["requiredSections"]:
            if section == "US Market Briefing":
                headings.append("# US Market Briefing — 2099.12.31")
            elif section == "Korea Market Briefing":
                headings.append("# Korea Market Briefing — 2099.12.31")
            elif "주도한 기업 ①" in section:
                headings.append(f"## {section} — {companies[0]}")
            elif "주도한 기업 ②" in section:
                headings.append(f"## {section} — {companies[1]}")
            else:
                headings.append(f"## {section}")
        conclusions = "\n".join(
            "**한 줄 결론:** 시장의 가격 반응과 내부 구조를 함께 해석합니다."
            for _ in range(contract["minimumOneLineConclusions"])
        )
        bullets = "\n".join(
            "· 핵심 수치와 원인, 다음 확인점을 점검합니다."
            for _ in range(contract["minimumMiddleDotBullets"])
        )
        prose = "시장 흐름과 근거, 반대 신호, 체크포인트를 자연스러운 줄글로 설명합니다. " * 300
        return "\n\n".join(headings + [conclusions, bullets, prose])

    if scope == "both":
        return "\n\n---\n\n".join((
            block("us", us_companies), block("kr", kr_companies),
        ))
    companies = us_companies if scope == "us" else kr_companies
    return block(scope, companies)


def test_briefing_writeback_uses_agent_generation_without_touching_real_store():
    with TemporaryDirectory() as tmp:
        original_dir = service.BRIEFINGS_DIR
        original_memory = service.MARKET_MEMORY_DB_PATH
        service.BRIEFINGS_DIR = Path(tmp) / "briefings"
        service.MARKET_MEMORY_DB_PATH = Path(tmp) / "market-memory.sqlite3"
        try:
            pack = {
                "taskType": "briefing",
                "artifactId": "2099-12-31",
                "draftArtifact": {
                    "date": "2099-12-31",
                    "title": "Daily Market Briefing - 2099.12.31",
                    "marketScope": "both",
                    "briefingType": "concise",
                    "generatedAt": "2099-12-31T08:00:00+09:00",
                    "stats": {"documents": 1},
                    "marketSnapshot": {"ok": True},
                    "koreaMarketData": {"ok": True},
                },
                "sources": [{"title": "Source", "source": "Test", "date": "2099-12-31"}],
                "marketTape": {"date": "2099-12-31"},
                "internal": {"qualityMode": "diagnose_only", "qualityPreflight": {}},
            }
            with (
                patch.object(service, "build_memory_from_briefing", return_value=[{"id": "memory-entry"}]) as build_memory,
                patch.object(service, "upsert_memory", side_effect=lambda _path, entry: entry) as upsert_memory,
            ):
                report = service.write_briefing_from_markdown(
                    pack,
                    _valid_briefing_markdown("both"),
                )
            assert report["generation"]["mode"] == "agent"
            assert report["generation"]["status"] == "ok_agent_authored"
            assert not (service.BRIEFINGS_DIR / "2099-12-31.json").exists()
            assert (service.BRIEFINGS_DIR / "2099-12-31.us.json").exists()
            assert (service.BRIEFINGS_DIR / "2099-12-31.kr.json").exists()
            build_memory.assert_called_once()
            assert build_memory.call_args.args[0]["marketScope"] == "both"
            upsert_memory.assert_called_once()
            for scope in ("us", "kr"):
                section = report["briefings"][scope]
                assert section["marketScope"] == scope
                assert section["briefingType"] == "concise"
                assert section["generatedAt"] == report["generatedAt"]
        finally:
            service.BRIEFINGS_DIR = original_dir
            service.MARKET_MEMORY_DB_PATH = original_memory


def test_partial_agent_writeback_preserves_sibling_scope_and_overlay():
    with TemporaryDirectory() as tmp:
        original_dir = service.BRIEFINGS_DIR
        original_memory = service.MARKET_MEMORY_DB_PATH
        service.BRIEFINGS_DIR = Path(tmp) / "briefings"
        service.MARKET_MEMORY_DB_PATH = Path(tmp) / "market-memory.sqlite3"
        try:
            us_path = service.BRIEFINGS_DIR / "2099-12-30.us.json"
            kr_path = service.BRIEFINGS_DIR / "2099-12-30.kr.json"
            write_json(us_path, {
                "date": "2099-12-30",
                "marketScope": "us",
                "markdown": "old us",
                "personalOverlay": {"enabled": True, "stale": False},
            })
            write_json(kr_path, {
                "date": "2099-12-30",
                "marketScope": "kr",
                "markdown": "old kr",
            })
            pack = {
                "taskType": "briefing",
                "artifactId": "2099-12-30",
                "draftArtifact": {
                    "date": "2099-12-30", "marketScope": "us",
                    "stats": {"documents": 1},
                    "marketSnapshot": {"ok": True}, "koreaMarketData": {"ok": True},
                    "visualRecommendations": [{"id": "recommendation-us", "market": "US"}],
                    "visualSnapshots": [{"id": "heatmap-us", "market": "US", "freshness": "close_snapshot"}],
                },
                "sources": [], "marketTape": {},
                "internal": {
                    "qualityMode": "diagnose_only", "qualityPreflight": {},
                    "visualSidecar": {
                        "date": "2099-12-30",
                        "snapshots": {"heatmap-us": {"id": "heatmap-us", "market": "US", "rows": [{"ticker": "NVDA"}]}},
                    },
                },
            }
            with patch.object(service, "build_memory_from_briefing", return_value=[]) as build_memory:
                service.write_briefing_from_markdown(pack, _valid_briefing_markdown("us"))
            saved = read_json(us_path, {})
            sibling = read_json(kr_path, {})
            assert not (service.BRIEFINGS_DIR / "2099-12-30.json").exists()
            build_memory.assert_not_called()
            assert saved["markdown"].startswith("# US Market Briefing")
            assert sibling["markdown"] == "old kr"
            assert saved["personalOverlay"]["stale"] is True
            with gzip.open(service.BRIEFINGS_DIR / "2099-12-30.us.visuals.json.gz", "rt", encoding="utf-8") as stream:
                sidecar = json.load(stream)
            assert sidecar["snapshots"]["heatmap-us"]["rows"][0]["ticker"] == "NVDA"
        finally:
            service.BRIEFINGS_DIR = original_dir
            service.MARKET_MEMORY_DB_PATH = original_memory


def test_partial_kr_agent_writeback_preserves_us_sibling():
    with TemporaryDirectory() as tmp:
        original_dir = service.BRIEFINGS_DIR
        original_memory = service.MARKET_MEMORY_DB_PATH
        service.BRIEFINGS_DIR = Path(tmp) / "briefings"
        service.MARKET_MEMORY_DB_PATH = Path(tmp) / "market-memory.sqlite3"
        try:
            us_path = service.BRIEFINGS_DIR / "2099-12-27.us.json"
            kr_path = service.BRIEFINGS_DIR / "2099-12-27.kr.json"
            write_json(us_path, {"date": "2099-12-27", "marketScope": "us", "markdown": "old us sibling"})
            write_json(kr_path, {
                "date": "2099-12-27",
                "marketScope": "kr",
                "markdown": "old kr",
                "personalOverlay": {"enabled": True, "stale": False},
            })
            sibling_before = us_path.read_bytes()
            pack = {
                "taskType": "briefing",
                "artifactId": "2099-12-27",
                "draftArtifact": {
                    "date": "2099-12-27",
                    "marketScope": "kr",
                    "stats": {"documents": 1},
                    "marketSnapshot": {"ok": True},
                    "koreaMarketData": {"ok": True},
                },
                "sources": [],
                "marketTape": {},
                "internal": {"qualityMode": "diagnose_only", "qualityPreflight": {}},
            }
            with patch.object(service, "build_memory_from_briefing", return_value=[]) as build_memory:
                service.write_briefing_from_markdown(pack, _valid_briefing_markdown("kr"))
            saved = read_json(kr_path, {})
            assert build_memory.call_count == 0
            assert saved["markdown"].startswith("# Korea Market Briefing")
            assert saved["personalOverlay"]["stale"] is True
            assert us_path.read_bytes() == sibling_before
        finally:
            service.BRIEFINGS_DIR = original_dir
            service.MARKET_MEMORY_DB_PATH = original_memory


def test_invalid_agent_briefing_is_rejected_before_store_write():
    with TemporaryDirectory() as tmp:
        original_dir = service.BRIEFINGS_DIR
        service.BRIEFINGS_DIR = Path(tmp) / "briefings"
        try:
            pack = {
                "taskType": "briefing",
                "artifactId": "2099-12-29",
                "draftArtifact": {"date": "2099-12-29", "marketScope": "both"},
                "outputContract": briefing_output_contract("both"),
            }
            with pytest.raises(ValueError, match="CLI 브리핑 출력 계약 위반"):
                service.write_briefing_from_markdown(
                    pack,
                    "# Daily Market Briefing\n\n## US Market Briefing\n짧은 요약",
                )
            assert not (service.BRIEFINGS_DIR / "2099-12-29.json").exists()
        finally:
            service.BRIEFINGS_DIR = original_dir


def test_cli_writeback_replaces_candidate_chart_with_final_heading_company():
    with TemporaryDirectory() as tmp:
        original_dir = service.BRIEFINGS_DIR
        service.BRIEFINGS_DIR = Path(tmp) / "briefings"
        markdown = _valid_briefing_markdown("us", us_companies=("NVIDIA", "Alphabet"))
        aligned = {
            "visualSnapshots": [
                {"id": "nvda", "role": "leading_company", "market": "US", "subject": {"ticker": "NVDA"}},
                {"id": "googl", "role": "leading_company", "market": "US", "subject": {"ticker": "GOOGL"}},
            ],
            "visualRecommendations": [
                {"snapshotId": "nvda", "role": "leading_company", "market": "US"},
                {"snapshotId": "googl", "role": "leading_company", "market": "US"},
            ],
            "warnings": [],
        }
        pack = {
            "taskType": "briefing",
            "artifactId": "2099-12-28",
            "draftArtifact": {
                "date": "2099-12-28", "marketScope": "us",
                "visualSnapshots": [{"id": "msft", "role": "leading_company", "market": "US"}],
                "visualRecommendations": [{"snapshotId": "msft", "role": "leading_company", "market": "US"}],
            },
            "outputContract": briefing_output_contract("us"),
            "internal": {
                "visualScopeResults": {"us": {"marketSessionDate": "2099-12-28", "groups": []}},
                "qualityMode": "diagnose_only", "qualityPreflight": {},
            },
        }
        try:
            with patch.object(service, "collect_briefing_visuals", return_value=aligned) as collect:
                report = service.write_briefing_from_markdown(pack, markdown)
            assert [row["id"] for row in report["visualSnapshots"]] == ["nvda", "googl"]
            parsed = collect.call_args.kwargs["leader_subjects"]
            assert [row["ticker"] for row in parsed["us"]] == ["NVDA", "GOOGL"]
            assert collect.call_args.kwargs["include_market_visuals"] is False
        finally:
            service.BRIEFINGS_DIR = original_dir


if __name__ == "__main__":
    test_briefing_writeback_uses_agent_generation_without_touching_real_store()


def test_agent_briefing_checkpoints_are_extracted_per_market():
    """Agent 경로도 시장별 markdown에서 자기 라벨로 체크포인트를 뽑는다(§builder와 같은 규칙).

    예전 라벨 목록("내일 확인할 체크포인트" 등)은 어느 시장 프롬프트에도 없어 Agent 생성
    브리핑은 체크포인트가 항상 0건이었고, 저장 파일이 남의 시장 체크포인트를 가질 수 있었다.
    """
    with TemporaryDirectory() as tmp:
        original_dir = service.BRIEFINGS_DIR
        original_memory = service.MARKET_MEMORY_DB_PATH
        service.BRIEFINGS_DIR = Path(tmp) / "briefings"
        service.MARKET_MEMORY_DB_PATH = Path(tmp) / "market-memory.sqlite3"
        try:
            pack = {
                "taskType": "briefing",
                "artifactId": "2099-12-31",
                "draftArtifact": {
                    "date": "2099-12-31",
                    "title": "Daily Market Briefing - 2099.12.31",
                    "marketScope": "both",
                    "briefingType": "concise",
                    "generatedAt": "2099-12-31T08:00:00+09:00",
                    "stats": {"documents": 1},
                    "marketSnapshot": {"ok": True},
                    "koreaMarketData": {"ok": True},
                },
                "sources": [{"title": "Source", "source": "Test", "date": "2099-12-31"}],
                "marketTape": {"date": "2099-12-31"},
                "internal": {"qualityMode": "diagnose_only", "qualityPreflight": {}},
            }
            markdown = _valid_briefing_markdown("both")
            markdown = markdown.replace(
                "## 6. 다음 미국장 체크포인트",
                "## 6. 다음 미국장 체크포인트\n- 미국 CPI 발표 확인\n- 국채 금리 반응 확인",
            )
            markdown = markdown.replace(
                "## 6. 다음 한국장 체크포인트",
                "## 6. 다음 한국장 체크포인트\n- 원·달러 환율 확인",
            )
            with (
                patch.object(service, "build_memory_from_briefing", return_value=[]),
                patch.object(service, "upsert_memory", side_effect=lambda _path, entry: entry),
            ):
                report = service.write_briefing_from_markdown(pack, markdown)

            assert report["checkpoints"], "통합 결과에 체크포인트가 있어야 한다"
            us_saved = read_json(service.BRIEFINGS_DIR / "2099-12-31.us.json", {})
            kr_saved = read_json(service.BRIEFINGS_DIR / "2099-12-31.kr.json", {})
            us_texts = [c.get("checkpoint", "") for c in us_saved.get("checkpoints", [])]
            kr_texts = [c.get("checkpoint", "") for c in kr_saved.get("checkpoints", [])]
            assert us_texts and all("미국" in t or "국채" in t for t in us_texts)
            assert kr_texts and all("환율" in t for t in kr_texts)
            assert not any("환율" in t for t in us_texts)
            assert not any("미국 CPI" in t for t in kr_texts)
        finally:
            service.BRIEFINGS_DIR = original_dir
            service.MARKET_MEMORY_DB_PATH = original_memory


def test_a_market_without_checkpoints_gets_its_own_gap():
    """갭이 합본 기준이면 한 시장만 비었을 때 그 사실이 어디에도 남지 않는다.

    저장 파일은 시장별인데 갭은 "전부 비었을 때"만 붙어서, 체크포인트가 0건인
    보고서가 아무 표시 없이 나갔다(§builder와 같은 규칙).
    """
    with TemporaryDirectory() as tmp:
        original_dir = service.BRIEFINGS_DIR
        original_memory = service.MARKET_MEMORY_DB_PATH
        service.BRIEFINGS_DIR = Path(tmp) / "briefings"
        service.MARKET_MEMORY_DB_PATH = Path(tmp) / "market-memory.sqlite3"
        try:
            pack = {
                "taskType": "briefing",
                "artifactId": "2099-12-26",
                "draftArtifact": {
                    "date": "2099-12-26",
                    "marketScope": "both",
                    "stats": {"documents": 1},
                    "marketSnapshot": {"ok": True},
                    "koreaMarketData": {"ok": True},
                },
                "sources": [],
                "marketTape": {},
                "internal": {"qualityMode": "diagnose_only", "qualityPreflight": {}},
            }
            # 미국장에만 체크포인트를 준다. 한국장 섹션은 제목만 있고 비어 있다.
            markdown = _valid_briefing_markdown("both").replace(
                "## 6. 다음 미국장 체크포인트",
                "## 6. 다음 미국장 체크포인트\n- 미국 CPI 발표 확인\n- 국채 금리 반응 확인",
            )
            with (
                patch.object(service, "build_memory_from_briefing", return_value=[]),
                patch.object(service, "upsert_memory", side_effect=lambda _path, entry: entry),
            ):
                report = service.write_briefing_from_markdown(pack, markdown)

            messages = [str(gap.get("message") or "") for gap in report.get("dataGaps") or []]
            assert "한국장: 체크포인트 섹션을 찾지 못했습니다." in messages
            assert not any(text.startswith("미국장: 체크포인트") for text in messages)
            # 합본에는 미국장 체크포인트가 남아 있으므로 예전 전체 갭은 붙지 않는다.
            assert not any(text.startswith("브리핑에서 구조화 가능한") for text in messages)
            kr_saved = read_json(service.BRIEFINGS_DIR / "2099-12-26.kr.json", {})
            assert kr_saved.get("checkpoints") == []
        finally:
            service.BRIEFINGS_DIR = original_dir
            service.MARKET_MEMORY_DB_PATH = original_memory
