"""`company_analysis_sources` — reader가 표시하는 출처 목록.

점검(2026-09-04)에서 확인한 결함:
- companyfacts 항목이 실제로는 submissions URL을 가리켰다.
- 컨텍스트가 "## 최근 분기 공시 서술 (10-Q MD&A)"로 10-Q를 읽는데 출처 목록엔 없었다.
- 웹 조회로 인용한 자료가 sourceLedger에만 있고 sources에서 빠졌다.
"""
from __future__ import annotations

from features.company_analysis.sec_companyfacts import SEC_FACTS_URL
from features.company_analysis.service import company_analysis_sources


def _materials(**overrides):
    base = {
        "company": {"ticker": "HWM", "name": "Howmet", "market": "US"},
        "secFacts": {"cik": "0000004281"},
        "rankedFiling": {
            "ok": True,
            "form": "10-K",
            "metadata": {"form": "10-K", "filingDate": "2026-02-14", "url": "https://sec.gov/hwm-10k"},
        },
        "rankedQuarterlyFiling": {
            "ok": True,
            "form": "10-Q",
            "metadata": {"form": "10-Q", "filingDate": "2026-08-01", "url": "https://sec.gov/hwm-10q"},
        },
    }
    base.update(overrides)
    return base


def test_the_companyfacts_link_points_at_companyfacts_not_submissions():
    sources = company_analysis_sources(_materials(), [])
    facts = next(s for s in sources if s["source"] == "SEC companyfacts")
    assert facts["url"] == SEC_FACTS_URL.format(cik="0000004281")
    assert "/submissions/" not in facts["url"]
    assert "/api/xbrl/companyfacts/" in facts["url"]


def test_the_recent_10q_appears_in_the_list_with_its_own_form():
    sources = company_analysis_sources(_materials(), [])
    forms = {s["url"]: s["type"] for s in sources}
    assert forms["https://sec.gov/hwm-10k"] == "10-K"
    assert forms["https://sec.gov/hwm-10q"] == "10-Q"


def test_a_missing_10q_does_not_add_a_row():
    sources = company_analysis_sources(_materials(rankedQuarterlyFiling={"ok": False, "reason": "no_quarterly_report"}), [])
    assert not any(s["type"] == "10-Q" for s in sources)


def test_a_fetch_failed_filing_is_not_listed_even_though_it_has_a_url():
    """HTML fetch가 실패하면 `{"ok": False, "metadata": {url: ...}}`이지만 컨텍스트는
    "확보하지 못했습니다"로 적는다 — 출처 목록이 본문과 어긋나면 안 된다."""
    failed = {"ok": False, "reason": "fetch_failed", "form": "10-Q",
              "metadata": {"form": "10-Q", "url": "https://sec.gov/hwm-10q", "error": "timeout"}}
    sources = company_analysis_sources(_materials(rankedQuarterlyFiling=failed), [])
    assert not any(s["url"] == "https://sec.gov/hwm-10q" for s in sources)


def test_local_docs_come_before_web_citations():
    """Rule 9 — 웹은 로컬 자료의 보완이지 대체가 아니다. 상한을 웹이 먼저 채우면 안 된다."""
    docs = [{"title": "IR deck", "source": "company", "url": "https://ir.example/deck", "type": "reports"}]
    web_items = [{"title": "guidance", "url": "https://news.example/g", "type": "web_reference"}]
    sources = company_analysis_sources(_materials(), docs, web_items)
    urls = [s["url"] for s in sources]
    assert urls.index("https://ir.example/deck") < urls.index("https://news.example/g")


def test_web_lookup_citations_reach_the_reader_list():
    web_items = [
        {"title": "Q2 guidance raised", "source": "investor.example.com",
         "url": "https://investor.example.com/q2", "date": "2026-07-30", "type": "web_reference"},
    ]
    sources = company_analysis_sources(_materials(), [], web_items)
    assert any(s["url"] == "https://investor.example.com/q2" for s in sources)


def test_web_items_without_a_real_url_are_skipped():
    sources = company_analysis_sources(_materials(), [], [{"title": "x", "url": ""}])
    assert all(s.get("url") != "" or s.get("path") for s in sources)
