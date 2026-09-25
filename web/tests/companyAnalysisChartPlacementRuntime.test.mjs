import test from "node:test";
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import { createServer } from "vite";

const webRoot = fileURLToPath(new URL("..", import.meta.url));

async function load(t) {
  const vite = await createServer({ configFile: false, root: webRoot, server: { middlewareMode: true, hmr: false }, appType: "custom" });
  t.after(() => vite.close());
  return vite.ssrLoadModule("/src/app/reportReader/CompanyAnalysisBody.tsx");
}

const CHARTS = {
  available: true,
  charts: [{ id: "performance" }, { id: "margins" }, { id: "cashflow" }, { id: "dcf" }, { id: "scenario_price" }, { id: "price_return" }],
};

const NINE_SECTIONS = [
  "## 핵심 판단", "여기 판단.",
  "## 기업 개요와 돈 버는 방식", "사업 설명.",
  "## 실적과 재무 품질", "숫자 변화.",
  "## 밸류에이션", "가정.",
  "## 경쟁우위", "해자.",
  "## 리스크와 반증조건", "위험.",
  "## 성장 전망과 체크포인트", "성장.",
  "## 어떻게 접근할까", "조건부 해석.",
  "## 자료 한계와 참고자료", "한계.",
].join("\n\n");

test("실적·마진 차트는 '기업 개요'가 아니라 '실적과 재무 품질'에 놓인다", async (t) => {
  const mod = await load(t);
  const sections = mod.splitAnalysisSections(NINE_SECTIONS);
  const { bySection } = mod.assignSectionCharts(sections, CHARTS);

  const titleOf = (i) => sections[i].title;
  const findByChart = (id) => [...bySection.entries()].find(([, ids]) => ids.includes(id))?.[0];

  assert.equal(titleOf(findByChart("performance")), "실적과 재무 품질");
  assert.equal(titleOf(findByChart("margins")), "실적과 재무 품질");
  assert.equal(titleOf(findByChart("cashflow")), "실적과 재무 품질");
  assert.equal(titleOf(findByChart("dcf")), "밸류에이션");
  assert.equal(titleOf(findByChart("scenario_price")), "밸류에이션");
  assert.equal(titleOf(findByChart("price_return")), "핵심 판단");
});

test("서론 문단이 앞에 붙어도 차트 배치가 밀리지 않는다", async (t) => {
  const mod = await load(t);
  const withIntro = "이 보고서는 요약 문단으로 시작합니다.\n\n" + NINE_SECTIONS;
  const sections = mod.splitAnalysisSections(withIntro);
  assert.equal(sections[0].key, "intro");
  const { bySection } = mod.assignSectionCharts(sections, CHARTS);
  const titleOf = (i) => sections[i].title;
  const findByChart = (id) => [...bySection.entries()].find(([, ids]) => ids.includes(id))?.[0];
  assert.equal(titleOf(findByChart("performance")), "실적과 재무 품질");
  // intro 섹션(배열 index 0)은 차트를 받지 않는다.
  assert.deepEqual(bySection.get(0) ?? [], []);
});

test("의미상 맞는 섹션이 없으면 고정 위치 fallback으로 떨어진다", async (t) => {
  const mod = await load(t);
  // 옛 제목: 규칙 패턴과 안 맞는다.
  const legacy = ["## 회사 소개", "옛 본문 1.", "## 숫자 이야기", "옛 본문 2.", "## 정리", "옛 본문 3."].join("\n\n");
  const sections = mod.splitAnalysisSections(legacy);
  const { bySection, used } = mod.assignSectionCharts(sections, CHARTS);
  // "숫자 이야기"가 /숫자/에 걸려 실적 차트를 semantic으로 가져간다.
  const findByChart = (id) => [...bySection.entries()].find(([, ids]) => ids.includes(id))?.[0];
  assert.equal(sections[findByChart("performance")].title, "숫자 이야기");
  // 나머지 차트는 배정되거나 remaining으로 남는다 — 유실은 없다.
  const placed = [...bySection.values()].flat();
  const remaining = mod.remainingChartIds(CHARTS, used);
  assert.equal(new Set([...placed, ...remaining]).size, 6);
});
