from features.daily_briefing.claim_integrity import enforce_claim_integrity


def _source(text: str, identifier: str = "src_1") -> dict:
    return {"sourceId": identifier, "title": text, "summary": text}


def test_unsupported_capital_flow_is_downgraded_without_llm_call() -> None:
    markdown = "채권에서 이탈한 자금이 반도체로 이동했다. 반도체는 자금의 대체 목적지였다."
    guarded, ledger = enforce_claim_integrity(markdown, [_source("채권 약세와 반도체 강세")], mode="active")
    assert "이탈한 자금이" not in guarded
    assert "자금의 대체 목적지" not in guarded
    assert "동시에 나타났지만" in guarded
    assert "근거는 부족하다" in guarded
    assert ledger["integrity"]["status"] == "review"
    assert {row["status"] for row in ledger["integrity"]["findings"]} == {"downgraded"}


def test_explicit_capital_flow_source_preserves_claim() -> None:
    markdown = "채권에서 이탈한 자금이 반도체로 이동했다."
    guarded, ledger = enforce_claim_integrity(
        markdown, [_source("채권 자금 이탈 뒤 반도체로 자금 이동", "src_flow")], mode="active",
    )
    assert guarded == markdown
    assert ledger["integrity"]["findings"][0]["status"] == "supported"
    assert ledger["integrity"]["findings"][0]["supportingSourceIds"] == ["src_flow"]


def test_sector_breadth_requires_direct_breadth_evidence() -> None:
    guarded, ledger = enforce_claim_integrity(
        "삼성전자가 올랐고 반도체 소부장 강세가 이어졌다.",
        [_source("삼성전자 3% 상승")],
        mode="active",
    )
    assert "일부 반도체 소부장 종목의 강세" in guarded
    assert ledger["integrity"]["reasonCodes"] == ["direct_source_relationship_missing"]


def test_diagnose_mode_records_but_does_not_rewrite() -> None:
    markdown = "업종 전반의 강세가 나타났다."
    guarded, ledger = enforce_claim_integrity(markdown, [], mode="diagnose")
    assert guarded == markdown
    assert ledger["integrity"]["findings"][0]["status"] == "review"


class TestDowngradeWritesRealKorean:
    """치환문이 문서와 같은 문체로 끝나고 조사가 맞아야 한다.

    기본 모드가 `active`라 이 문장은 Canonical 본문·리더·내보내기에 그대로 실린다.
    """

    def _run(self, body: str) -> str:
        from features.daily_briefing.claim_integrity import enforce_claim_integrity

        markdown, _ = enforce_claim_integrity(
            "## 1. 개요\n\n" + body + "\n",
            [{"title": "무관한 기사", "url": "https://example.com/a"}],
            {},
            mode="active",
        )
        return markdown.strip().splitlines()[-1]

    def test_polite_sentences_stay_polite(self):
        out = self._run("코스피에서 이탈한 자금이 코스닥으로 이동했습니다.")
        assert out.endswith("부족합니다.")
        assert "부족하다습니다" not in out

    def test_passive_and_plain_endings_are_consumed(self):
        assert self._run("코스피에서 이탈한 자금이 코스닥으로 유입되었다.").endswith("부족하다.")
        assert self._run("반도체에서 이탈한 자금이 바이오로 몰렸다.").endswith("부족하다.")
        for body in ("코스피에서 이탈한 자금이 코스닥으로 유입되었다.", "반도체에서 이탈한 자금이 바이오로 몰렸다."):
            assert "부족하다되었다" not in self._run(body)
            assert "부족하다다" not in self._run(body)

    def test_the_topic_particle_follows_the_final_consonant(self):
        """하드코딩한 `은`은 모음으로 끝나는 명사에서 틀린다 — 실측 `반도체은`."""
        vowel = self._run("반도체는 자금의 대체 목적지였다.")
        assert vowel.startswith("반도체는"), vowel
        consonant = self._run("건설은 자금의 대체 목적지였다.")
        assert consonant.startswith("건설은"), consonant
