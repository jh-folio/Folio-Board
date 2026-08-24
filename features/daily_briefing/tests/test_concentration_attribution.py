from __future__ import annotations

from features.daily_briefing.concentration.attribution import attribute_document


def test_same_article_preserves_distinct_company_claims() -> None:
    doc = {
        "id": "doc-a",
        "title": "삼성전자 파운드리 수주, SK하이닉스 HBM 공급계약",
        "content": (
            "삼성전자는 신규 파운드리 수주로 가동률 개선을 기대한다. "
            "SK하이닉스는 HBM 공급계약으로 고부가 제품 비중을 높인다. "
            "AI 데이터센터 투자는 두 회사의 공통 배경이다."
        ),
        "wordCount": 150,
        "companies": [{"name": "삼성전자", "ticker": "005930"}, {"name": "SK하이닉스", "ticker": "000660"}],
    }
    samsung = attribute_document(doc, "삼성전자")
    hynix = attribute_document(doc, "SK하이닉스")
    assert samsung["directEvidenceCount"] >= 1
    assert hynix["directEvidenceCount"] >= 1
    assert any("파운드리" in row["excerpt"] for row in samsung["claimUnits"] if row["role"] == "direct")
    assert any("HBM" in row["excerpt"] for row in hynix["claimUnits"] if row["role"] == "direct")


def test_incidental_company_mention_gets_no_leader_credit() -> None:
    doc = {
        "id": "doc-b",
        "title": "반도체주 상승",
        "summary": "관련 종목은 삼성전자, SK하이닉스 등",
        "companies": [{"name": "삼성전자"}, {"name": "SK하이닉스"}],
    }
    result = attribute_document(doc, "삼성전자")
    assert result["directEvidenceCount"] == 0
    assert all(row["credit"] < 1 for row in result["claimUnits"])
