import { readFile } from "node:fs/promises";
import { test } from "node:test";
import assert from "node:assert/strict";

test("Briefing route owns archive and saved briefing APIs", async () => {
  const source = await readFile(new URL("../src/app/BriefingRoute.tsx", import.meta.url), "utf8");

  assert.match(source, /data-briefing-route/);
  assert.match(source, /\/api\/briefings\/index/);
  assert.match(source, /\/api\/briefings\/\$\{encodeURIComponent\(date\)\}/);
  assert.match(source, /includePersonal=true/);
  assert.match(source, /marketScope/);
  assert.match(source, /ReportReaderShell/);
  assert.match(source, /ReportBody/);
});

test("Briefing route mirrors the legacy generation and archive controls", async () => {
  const source = await readFile(new URL("../src/app/BriefingRoute.tsx", import.meta.url), "utf8");

  assert.match(source, /brief-gen-box input-panel react-briefing-generation/);
  assert.match(source, /brief-market-segment/);
  assert.match(source, /brief-gen-actionbar/);
  assert.match(source, /오늘 브리핑 생성/);
  // 날짜 선택은 발행일이 아니라 시장 세션 기준일이다. 문구가 그걸 말해야 한다.
  assert.match(source, /이 기준일로 생성/);
  assert.match(source, /기준일`/);
  assert.doesNotMatch(source, />품질 모드</);
  assert.doesNotMatch(source, /setQualityMode/);
  // 검색·시장·유형·기간·보기가 한 찾기 바에 모여야 한다(예전에는 패널 안팎으로 갈렸다).
  assert.match(source, /className="find-bar"/);
  assert.doesNotMatch(source, /className="report-feed-outside-controls"/);
  assert.match(source, /archiveQuery/);
  assert.match(source, /archiveMarket/);
  assert.match(source, /archiveType/);
  assert.match(source, /archiveStart/);
  assert.match(source, /archiveEnd/);
  assert.match(source, /archiveView/);
  assert.match(source, /ArchiveViewMode = "recent" \| "month" \| "market"/);
  assert.match(source, /RECENT_BRIEFING_LIMIT/);
  assert.match(source, /formatArchiveMonth/);
  // 시장·유형·보기는 패널 밖 별도 줄이 아니라 찾기 바 안의 필드다.
  assert.match(source, /find-bar__field/);
  assert.match(source, /value="recent"/);
  assert.match(source, /value="month"/);
  assert.match(source, /URLSearchParams/);
  assert.match(source, /limit:\s*"100"/);
  assert.match(source, /marketScope:\s*archiveMarket/);
  assert.match(source, /briefingType:\s*archiveType/);
  assert.match(source, /strictDate/);
});

test("Briefing archive list does not re-filter what the server already filtered", async () => {
  const source = await readFile(new URL("../src/app/BriefingRoute.tsx", import.meta.url), "utf8");
  const filter = source.match(/const filteredItems = useMemo\(\(\) => \{[\s\S]*?\}, \[[^\]]*\]\);/)?.[0];
  assert.ok(filter, "filteredItems memo not found");

  // 서버가 제목·요약·**본문**으로 이미 거른다. 화면이 제목·태그만으로 다시 좁히면
  // 본문에서만 일치한 브리핑이 통째로 사라지고 목록이 `0건`으로 보인다.
  assert.doesNotMatch(filter, /haystack/);
  assert.doesNotMatch(filter, /archiveQuery/);
  // 기간은 서버와 같은 규칙(발행일 또는 세션일)을 쓴다. 발행일 단독 비교가 남으면
  // 카드에 적힌 세션일로 기간을 잡은 순간 그 브리핑이 사라진다.
  assert.doesNotMatch(filter, /date < archiveStart/);
  assert.doesNotMatch(filter, /date > archiveEnd/);
  assert.match(filter, /archiveDateInRange\(item, archiveStart, archiveEnd\)/);
  assert.match(source, /export function archiveDateInRange\(/);
  assert.match(source, /item\.sessionDate/);
});

test("Briefing route owns reader actions and native note persistence", async () => {
  const source = await readFile(new URL("../src/app/BriefingRoute.tsx", import.meta.url), "utf8");
  const shellSource = await readFile(new URL("../src/app/reportReader/ReportReaderShell.tsx", import.meta.url), "utf8");
  const noteSource = await readFile(new URL("../src/app/reportReader/FolioNotePanel.tsx", import.meta.url), "utf8");

  assert.match(source, /\/api\/briefings\/\$\{encodeURIComponent\(date\)\}\/export-notion/);
  assert.match(source, /\/api\/briefings\/\$\{encodeURIComponent\(date\)\}\/export-obsidian/);
  assert.match(source, /\/api\/briefings\/\$\{encodeURIComponent\(date\)\}\/personal-overlay/);
  assert.match(source, /noteType: "market_memo"/);
  assert.match(source, /noteIdentity=\{briefingNoteIdentity/);
  assert.match(source, /noteLinkedTitle=\{readerTitle\}/);
  assert.match(source, /noteOverlay=\{parsePersonalOverlayPayload\(briefing\.personalOverlay, briefing\.canonicalRevision\)\}/);
  assert.match(shellSource, /FolioNotePanel/);
  assert.match(noteSource, /\/api\/investment-notes/);
  assert.match(source, /ReaderActionGroup title="AI"/);
  assert.match(source, /ReaderActionGroup title="노트"/);
  assert.match(source, /ReaderActionGroup title="내보내기"/);
  assert.match(source, /message: `\$\{readerTitle\}/);
  assert.match(source, /KST 발행/);
  assert.match(source, /meta=\{`보고서 날짜/);
  assert.match(source, /생성 시각 미상/);
  assert.match(source, /autoSubmit: true/);
  assert.doesNotMatch(source, />\s*목록\s*</);
});

test("AppShell renders BriefingRoute on the briefing route", async () => {
  const source = await readFile(new URL("../src/app/AppShell.tsx", import.meta.url), "utf8");

  assert.match(source, /<BriefingRoute\s*\/>/);
  assert.match(source, /route\.id === "briefing"/);
  assert.match(source, /renderRoutePane/);
});

test("briefing route no longer falls back to the legacy briefing view", async () => {
  const source = await readFile(new URL("../src/app/routes.ts", import.meta.url), "utf8");

  assert.doesNotMatch(source, /id: "briefing", label: "브리핑", group: "research", legacyViewId: "briefing"/);
});

test("Report Reader foundation mirrors the legacy inline reader contract", async () => {
  const source = await readFile(new URL("../src/app/reportReader/ReportReaderShell.tsx", import.meta.url), "utf8");
  const bodySource = await readFile(new URL("../src/app/reportReader/ReportBody.tsx", import.meta.url), "utf8");

  assert.match(source, /data-report-reader-shell/);
  assert.match(source, /actionSlot/);
  assert.match(source, /noteIdentity/);
  assert.doesNotMatch(source, /proposalSurface/);
  assert.doesNotMatch(source, /report-proposal-surface/);
  assert.match(source, /setReactAgentContextScope/);
  assert.match(source, /onClose/);
  assert.match(source, /report-reader-inline/);
  assert.match(source, /report-reader-stage/);
  assert.match(source, /report-reader-dialog/);
  assert.match(source, /report-reader-rail/);
  assert.match(source, /report-note-panel is-open/);
  assert.match(bodySource, /stripInlineReferenceSections/);
  assert.match(bodySource, /참고\\s\*자료/);
  // 안전-느슨 헤딩 계약: 변형(`## 7. 참고자료`)은 잡고 "Sources of Uncertainty" 같은
  // 분석 섹션은 잡지 않는다 — 리터럴 "Sources Used" 대신 선택 그룹 형태를 검사한다.
  assert.match(bodySource, /Sources\(\?:\\s\+Used\)\?/);
  assert.match(bodySource, /sourcePanelHtml/);
});

test("브리핑 삭제는 응답을 확인하고 multi를 날짜 전체로 지운다", async () => {
  const source = await readFile(new URL("../src/app/BriefingRoute.tsx", import.meta.url), "utf8");
  const body = source.slice(source.indexOf("async function deleteBriefing"), source.indexOf("async function generateBriefing"));

  // 공통 HTTP helper가 비정상 응답을 거부하고, 정상 JSON도 삭제 확정을 확인한다.
  assert.match(body, /await deleteJson</);
  assert.match(body, /result\.deleted !== true/);
  // `multi`는 서버가 아는 단일 시장이 아니라 `?market=multi`가 400이었다.
  // 통합 범위이므로 그 날짜 전체를 지운다.
  assert.match(body, /scope === "both" \|\| scope === "all" \|\| scope === "multi"/);
});
