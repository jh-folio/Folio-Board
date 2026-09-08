import { readFile } from "node:fs/promises";
import { test } from "node:test";
import assert from "node:assert/strict";

test("Company Analysis route owns feed, form, and reader APIs", async () => {
  const source = await readFile(new URL("../src/app/CompanyAnalysisRoute.tsx", import.meta.url), "utf8");

  assert.match(source, /data-company-analysis-route/);
  assert.match(source, /\/api\/analysis-reports/);
  assert.match(source, /\/api\/analyze\?/);
  assert.doesNotMatch(source, /qualityMode/);
  assert.doesNotMatch(source, />품질 모드</);
  assert.match(source, /AnalysisStyle = "beginner" \| "advanced"/);
  assert.match(source, /ANALYSIS_STYLES/);
  assert.match(source, /analysisStyle/);
  assert.match(source, /setAnalysisStyle/);
  assert.match(source, /report\.analysisStyle/);
  assert.match(source, /analysisCharts\?/);
  assert.match(source, /CompanyAnalysisBody/);
  assert.doesNotMatch(source, /<AnalysisCharts payload=\{selected\.analysisCharts\}/);
  assert.match(source, /analysisFeedTitle/);
  assert.match(source, /splitReportTitle\(String\(report\.markdown/);
  assert.match(source, /report\.headline/);
  assert.match(source, /dataGaps\?/);
  assert.match(source, /unresolvedDataGaps/);
  assert.match(source, /자료 한계/);
  assert.match(source, /react-reader-gap-list/);
  assert.match(source, /ReportReaderShell/);
  assert.match(source, /noteIdentity/);
  assert.match(source, /dedupeDataGaps/);
  assert.doesNotMatch(source, /proposalSurface/);
  assert.match(source, /openReactAgentDock/);
  assert.match(source, /setReactAgentContextScope/);
  assert.match(source, /noteType: "company_thesis"/);
  assert.match(source, /reportKind: "company_analysis"/);
  assert.match(source, /AnalysisViewMode = "recent" \| "company" \| "month"/);
  assert.match(source, /reportQuery/);
  assert.match(source, /reportView/);
  assert.match(source, /filteredReports/);
  assert.match(source, /visibleReportGroups/);
  assert.match(source, /RECENT_ANALYSIS_LIMIT/);
  assert.match(source, /displayMonth/);
  // `보기`는 패널 밖에 떠 있었다. 검색과 함께 한 찾기 바로 모았다.
  assert.match(source, /className="find-bar"/);
  assert.doesNotMatch(source, /className="report-feed-outside-controls"/);
  assert.match(source, /find-bar__field/);
  assert.match(source, /티커·회사명·보고서 검색/);
});

test("Company Analysis body interleaves charts into matching report sections", async () => {
  const source = await readFile(new URL("../src/app/reportReader/CompanyAnalysisBody.tsx", import.meta.url), "utf8");
  const chartSource = await readFile(new URL("../src/app/reportReader/AnalysisCharts.tsx", import.meta.url), "utf8");
  const styles = await readFile(new URL("../../public/styles.css", import.meta.url), "utf8");

  assert.match(source, /splitAnalysisSections/);
  assert.match(source, /chartGroupsForSection/);
  assert.match(source, /usedChartIds/);
  assert.match(source, /performance/);
  assert.match(source, /cashflow/);
  assert.match(source, /scenario_price/);
  assert.match(source, /price_return/);
  assert.match(source, /<ReportBody/);
  assert.match(source, /<AnalysisCharts/);
  assert.match(chartSource, /onMouseEnter/);
  assert.match(chartSource, /onFocus/);
  assert.match(chartSource, /analysis-chart-tooltip/);
  assert.match(chartSource, /currencySymbol/);
  assert.match(chartSource, /formatValue/);
  assert.match(styles, /\.markdown-brief table\s*\{/);
  assert.match(styles, /\.table-wrap\s*\{[\s\S]*margin:\s*0\.72em 0/);
  assert.match(styles, /\.markdown-brief table\s*\{[\s\S]*margin:\s*0/);
});

test("Company Analysis route polls agent jobs for generated reports", async () => {
  const source = await readFile(new URL("../src/app/CompanyAnalysisRoute.tsx", import.meta.url), "utf8");

  assert.match(source, /\/api\/jobs\/\$\{encodeURIComponent\(current\.id\)\}/);
  assert.match(source, /reportId \|\| done\.result\?\.artifactId/);
  assert.match(source, /includePersonal=true/);
});

test("Company Analysis keeps an unsaved candidate visible and refreshes the feed second", async () => {
  const source = await readFile(new URL("../src/app/CompanyAnalysisRoute.tsx", import.meta.url), "utf8");

  assert.match(source, /setSelected\(report\);\s*const saved = report\.saved === true;/s);
  assert.match(source, /if \(saved && report\.id\) setAnalysisHash\(report\.id\);/);
  assert.match(source, /await loadReports\(\);/);
  assert.match(source, /생성했지만 저장 여부를 확인하지 못했습니다/);
  assert.match(source, /function closeSelectedReport\(\)/);
  assert.match(source, /onClick=\{closeSelectedReport\}/);
  assert.match(source, /onClose=\{closeSelectedReport\}/);
  assert.doesNotMatch(source, /if \(report\.id\) setAnalysisHash\(report\.id\);/);
});

test("AppShell renders CompanyAnalysisRoute on the analysis route", async () => {
  const source = await readFile(new URL("../src/app/AppShell.tsx", import.meta.url), "utf8");

  assert.match(source, /<CompanyAnalysisRoute\s*\/>/);
  assert.match(source, /route\.id === "analysis"/);
  assert.match(source, /renderRoutePane/);
});

test("analysis route no longer falls back to the legacy analysis view", async () => {
  const source = await readFile(new URL("../src/app/routes.ts", import.meta.url), "utf8");

  assert.doesNotMatch(source, /id: "analysis", label: "기업 분석", group: "research", legacyViewId: "analysis"/);
});
