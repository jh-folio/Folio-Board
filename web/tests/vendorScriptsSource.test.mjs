import assert from "node:assert/strict";
import { readdir, readFile, stat } from "node:fs/promises";
import path from "node:path";
import test from "node:test";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("../../", import.meta.url));
const read = (relative) => readFile(path.join(root, relative), "utf8");

const html = await read("public/index.html");
const pkg = JSON.parse(await read("web/package.json"));
const notices = await read("THIRD_PARTY_NOTICES.md");
const echartsBundle = await read("public/vendor/echarts.js");

// 차트 라이브러리는 CDN이 아니라 앱 폴더에서 서빙한다. 순서가 어긋나면
// `public/briefing-visuals.js`(히트맵)가 `window.echarts`를 못 본다.
test("index.html serves the chart libraries locally, before the scripts that use them", () => {
  const order = ["/vendor/echarts.js", "/vendor/lightweight-charts.js", "/briefing-visuals.js", "/app.js", "/react/folio-react.js"]
    .map((src) => html.indexOf(`src="${src}"`));
  assert.ok(order.every((index) => index >= 0), `missing script tag: ${order}`);
  assert.deepEqual(order, [...order].sort((a, b) => a - b), "scripts out of order");
  assert.doesNotMatch(html, /cdn\.jsdelivr\.net\/npm\/lightweight-charts/);
});

// 벤더 파일이 슬며시 다른 버전으로 바뀌면 히트맵 라벨 계획이 읽는 배치(계획 §6.5)도 바뀔 수 있다.
test("vendored chart libraries are pinned to exact versions", () => {
  assert.match(pkg.devDependencies.echarts, /^\d+\.\d+\.\d+$/, "echarts must not use ^ or ~");
  assert.match(pkg.devDependencies["lightweight-charts"], /^\d+\.\d+\.\d+$/, "lightweight-charts must not use ^ or ~");
  assert.equal(pkg.scripts["build:vendor"], "node scripts/build-vendor.mjs");
});

test("ECharts bundle keeps its license notice and matches the pinned version", () => {
  const version = pkg.devDependencies.echarts;
  assert.ok(echartsBundle.startsWith(`/*! Apache ECharts ${version} `), "license banner missing or version mismatch");
  assert.match(echartsBundle.slice(0, 400), /Apache License 2\.0/);
  assert.match(echartsBundle.slice(0, 400), /zrender/);
  assert.match(echartsBundle.slice(0, 400), /BSD 3-Clause/);
  assert.match(notices, /## Apache ECharts and zrender/);
  assert.match(notices, /BSD 3-Clause/);
});

test("Lightweight Charts copy is unmodified and keeps its license header", async () => {
  const bundle = await read("public/vendor/lightweight-charts.js");
  const version = pkg.devDependencies["lightweight-charts"];
  assert.match(bundle.slice(0, 300), new RegExp(`Lightweight Charts™ v${version.replaceAll(".", "\.")}`));
  assert.match(bundle.slice(0, 300), /Apache License 2\.0/);
  const upstream = await read(`web/node_modules/lightweight-charts/dist/lightweight-charts.standalone.production.js`).catch(() => null);
  if (upstream !== null) assert.equal(bundle, upstream, "copy differs from the npm release");
});

// 이 번들이 실제로 차트를 그리는지 — 등록 목록이 빠지면 화면이 아니라 여기서 먼저 걸린다.
test("ECharts vendor bundle exposes window.echarts and renders every registered chart type", () => {
  const context = { setTimeout, clearTimeout, setInterval, clearInterval, console };
  context.window = context;
  context.self = context;
  vm.createContext(context);
  vm.runInContext(echartsBundle, context);
  const { echarts } = context;
  assert.deepEqual(Object.keys(echarts).sort(), ["getInstanceByDom", "init", "registerTheme", "use", "version"]);
  assert.equal(echarts.version, pkg.devDependencies.echarts);

  const series = {
    line: { type: "line", data: [1, 2] },
    bar: { type: "bar", data: [1, 2] },
    scatter: { type: "scatter", data: [1, 2] },
    candlestick: { type: "candlestick", data: [[1, 2, 0, 3]] },
    boxplot: { type: "boxplot", data: [[1, 2, 3, 4, 5]] },
    treemap: { type: "treemap", data: [{ name: "a", value: 1 }] },
    sankey: { type: "sankey", data: [{ name: "a" }, { name: "b" }], links: [{ source: "a", target: "b", value: 1 }] },
    heatmap: { type: "heatmap", data: [[0, 0, 1]] },
  };
  for (const [type, one] of Object.entries(series)) {
    const option = { animation: false, series: [one] };
    if (["line", "bar", "scatter", "candlestick", "boxplot"].includes(type)) {
      option.xAxis = { type: "category", data: ["a", "b"] };
      option.yAxis = {};
    }
    if (type === "heatmap") {
      option.xAxis = { type: "category", data: ["a"] };
      option.yAxis = { type: "category", data: ["a"] };
      option.visualMap = { min: 0, max: 1 };
    }
    // ssr 인스턴스는 dispose하지 않으면 Node가 끝나지 않는다(6.1.0 실측).
    const chart = echarts.init(null, null, { renderer: "svg", ssr: true, width: 300, height: 200 });
    try {
      chart.setOption(option);
      assert.match(chart.renderToSVGString(), /<svg/, `${type} did not render`);
    } finally {
      chart.dispose();
    }
  }
});

// React 번들에 ECharts가 또 실리면 같은 의존성이 두 벌이 된다(계획 §4 중단 조건).
// 앱 소스는 타입만 가져올 수 있다 — 실행 코드는 `window.echarts`로만 받는다.
test("app source never imports the ECharts runtime, only its types", async () => {
  const offenders = [];
  const walk = async (dir) => {
    for (const entry of await readdir(dir, { withFileTypes: true })) {
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) await walk(full);
      else if (/\.(ts|tsx)$/.test(entry.name) && !full.includes(`${path.sep}vendor${path.sep}`)) {
        const source = await readFile(full, "utf8");
        for (const match of source.matchAll(/^\s*import\s+(?!type\b)[^;]*from\s+["'](echarts|zrender)(\/[^"']*)?["']/gm)) {
          offenders.push(`${path.relative(root, full)}: ${match[0].trim()}`);
        }
      }
    }
  };
  await walk(path.join(root, "web/src"));
  assert.deepEqual(offenders, []);
});

test("vendor folder is inside the packaged public directory", async () => {
  assert.ok((await stat(path.join(root, "public/vendor"))).isDirectory());
  const manifest = JSON.parse(await read("release-manifest.json"));
  assert.ok(manifest.runtimeDirectories.includes("public"), "public/ must ship, or vendor files are missing from the package");
});
