// 벤더 파일을 `public/vendor/`에 만든다.
//
//   echarts.js               ← `vite.vendor.config.ts`로 커스텀 빌드(등록한 차트·컴포넌트만)
//   lightweight-charts.js    ← npm 배포본을 **그대로 복사**(가공하지 않는다 — 저작권 고지와 출처 로고 계약 보존)
//
// 두 파일 모두 커밋한다. 사용자 설치본은 Node 없이 이 파일을 서빙한다.
// 버전을 올릴 때는 package.json의 정확 고정 버전과 THIRD_PARTY_NOTICES.md를 함께 고친다.
import { copyFile, mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { gzipSync } from "node:zlib";
import { build } from "vite";

const web = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const out = resolve(web, "../public/vendor");
await mkdir(out, { recursive: true });

await build({ configFile: resolve(web, "vite.vendor.config.ts"), root: web, logLevel: "warn" });

// 저작권 고지는 재배포 조건이다(Apache-2.0 ECharts, BSD-3 zrender). 압축기가 주석을 지우므로
// 번들러 옵션에 맡기지 않고 여기서 파일 머리에 직접 붙인다 — 붙었는지는 vendorScriptsSource 테스트가 지킨다.
const echartsFile = resolve(out, "echarts.js");
const banner =
  "/*! Apache ECharts 6.1.0 - Copyright 2017-2026 The Apache Software Foundation, Apache License 2.0.\n" +
  " *  Includes zrender 6.1.0 - Copyright (c) 2017, Baidu Inc., BSD 3-Clause License.\n" +
  " *  Custom build (SVG renderer; see web/src/vendor/echarts.ts). Notices: THIRD_PARTY_NOTICES.md */\n";
await writeFile(echartsFile, banner + (await readFile(echartsFile, "utf8")));

const lightweight = resolve(web, "node_modules/lightweight-charts/dist/lightweight-charts.standalone.production.js");
await copyFile(lightweight, resolve(out, "lightweight-charts.js"));

for (const name of ["echarts.js", "lightweight-charts.js"]) {
  const bytes = await readFile(resolve(out, name));
  console.log(`${name.padEnd(24)} ${String(bytes.length).padStart(9)} raw  ${String(gzipSync(bytes).length).padStart(9)} gzip`);
}
