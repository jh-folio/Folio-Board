# Personal Overlay

Canonical 보고서(브리핑·기업분석)를 사용자의 Obsidian **hypothesis 노트와 대조**한 개인 해석 레이어를 만든다.
Folio OS 2계층 모델의 Personal Overlay 계층이다.

> 로컬 계획문서 `IMPLEMENTATION_PLAN.md` Step 2 — 백엔드·API·UI·테스트 구현 완료.

## 핵심 원칙 (CLAUDE.md §5)

1. **2계층 분리** — Canonical `markdown`은 **절대 수정하지 않는다.** overlay는 보고서 JSON의 `personalOverlay` 필드로만 붙는다.
2. **노트는 hypothesis** — 사용자 노트는 evidence가 아니라 가설로 취급한다(Obsidian importer에서 importable로 분류된 것만 사용).
3. **확증편향 방지** — 결과에는 `counterEvidence`/`contradictions`/`uncertainties`가 항상 존재한다(`schema.normalize_overlay`가 보장).
4. **결론 enum** — 종합 신호 `stance`는 `reinforced/unchanged/weakened/conflicted/insufficient` 중 하나로만 둔다.
5. **fallback** — LLM이 꺼져 있거나 실패하면 규칙 기반으로 구조를 채운다(연결 노트 목록 + 안내).

## 동작

```text
attach_overlay_to_briefing(date, market_scope, kind) / attach_overlay_to_report(report_id)
  → 저장된 Canonical 보고서 로드
  → Obsidian importer로 Vault 재스캔(노트를 만들면 어느 폴더든 즉시 반영) → list_hypotheses() 조회 (기업분석은 ticker 필터)
  → 노트 0개면 LLM 호출 없이 "연결할 노트 없음"(status=no_notes)으로 단락
  → generate_overlay(): LLM(json_mode)로 대조 → normalize_overlay  (LLM 꺼짐/실패 시 fallback)
  → with_overlay(): personalOverlay 블록만 추가, 기본 markdown 불변 → 같은 JSON에 저장
```

## API

```text
POST /api/briefings/{date}/personal-overlay              # ?marketScope=&kind=  body: {marketScope?, kind?, useLlm?, webSearch?}
GET  /api/briefings/{date}?includePersonal=true          # 기본 응답은 overlay 제외
POST /api/analysis-reports/{report_id}/personal-overlay
GET  /api/analysis-reports/{report_id}?includePersonal=true
```

**브리핑 요청에는 `kind`가 필요하다.** 주간의 저장 키는 발행일이라 같은 날 일간과 날짜가
겹치고, 종류를 빼면 주간을 열어 두고 누른 개인 해석이 그날 **일간 보고서**를 고친다.
CLI 경로는 report id에 종류를 실어 보낸다(`{발행일}.weekly`) — 파일은 시장별로만
저장되므로 `market_scope`도 함께 넘겨야 한다. 시장을 빼면 저장된 적 없는 이름을 열어
항상 실패한다.

합본 범위(`multi`/`both`/`all`)로 물으면 옛 일간 합본 파일(`{날짜}.json`)을 찾고, 없으면
그 날짜의 시장 파일이 **하나뿐일 때만** 그것을 쓴다. 여러 시장이 함께 있으면 어느 쪽에
얹을지 정할 수 없어 404다 — 리더는 생성 직후 시장 하나로 열리므로 이 상태에 닿지 않는다.

`includePersonal`이 false(기본)면 응답에서 `personalOverlay`를 제거한다 — 기본 보고서 응답이 개인 해석에 오염되지 않도록.

## 저장 구조

보고서 JSON 안에 필드로 저장한다(문서형 → JSON-per-report, IMPLEMENTATION_PLAN §4).

```json
{
  "markdown": "...(Canonical, 불변)...",
  "personalOverlay": {
    "enabled": true,
    "status": "ok | disabled | error: ...",
    "generatedAt": "2026-06-10T...",
    "stance": "unchanged",
    "linkedNotes": [{"noteId": "...", "title": "...", "type": "company_thesis", "ticker": "LRCX"}],
    "supportingEvidence": [], "counterEvidence": [], "contradictions": [],
    "uncertainties": [], "personalQuestions": [],
    "markdown": "## 내 노트와 연결\n..."
  }
}
```

## 관련 코드

- `schema.py` — `normalize_overlay()`(편향방지 필드 보장), `STANCE_CHOICES`
- `service.py` — `generate_overlay`, `with_overlay`, `strip_overlay`, `attach_overlay_to_*`
- `prompt.md` — 검증 리뷰어 프롬프트(JSON 출력)
- `tests/test_overlay.py` — 11/11 (스키마·fallback·markdown 불변·strip)
- `app.py` — 위 API 엔드포인트(얇은 래퍼만)

## 테스트

```powershell
py -3 features\personal_overlay\tests\test_overlay.py
```

## UI

- 브리핑/기업분석 화면에 "내 노트와 연결" 버튼 + 별도 카드(`.personal-overlay`)와 "근거에 포함 안 됨" 고지 배너.
- 버튼 → `POST .../personal-overlay` 생성, 저장 보고서를 열 때 `GET ...?includePersonal=true`로 기존 overlay 표시.
- 관련 프론트 코드: `public/app.js`(`renderOverlaySection`, 버튼 핸들러), `public/index.html`(`#briefOverlayArea`·`#briefOverlayContent`·`#analysisOverlayContent`), `public/styles.css`(`.personal-overlay`).
- 기업분석 overlay는 **저장된 보고서(report_id)** 에서만 생성 가능(미저장 보고서는 버튼 비활성).

## 공통 reader projection (0.2.1)

- `schema.public_projection()`은 linked notes, counter-evidence, contradictions,
  uncertainties, personal questions, Canonical revision, stale 상태를 세 보고서에
  동일한 형태로 제공한다.
- 새 Overlay는 생성 당시 `canonicalRevision`을 별도 snapshot으로 저장한다.
- 저장본에 revision이 없으면 삭제/마이그레이션하지 않고
  `legacy_unknown`으로 표시한다. Canonical revision 불일치는 `stale`로 표시한다.
- Overlay 생성과 조회는 Canonical `markdown`, source ledger, evidence count를
  변경하지 않는다.
