import { defineConfig } from "vite";

// 벤더 번들 — React 앱과 **별도로** 빌드한다.
//
// `public/vendor/echarts.js`는 커밋되는 산출물이다(`public/react/folio-react.js`와 같은 관행).
// 사용자 설치본은 Node 없이 이 파일을 그대로 서빙한다. 그래서 이 빌드는 ECharts 버전을 올리거나
// `src/vendor/echarts.ts`의 등록 목록을 바꿀 때만 돌린다(`npm run build:vendor`).
//
// 앱 빌드(`vite.config.ts`)의 `emptyOutDir`은 `public/react`만 비운다 — 이 폴더는 건드리지 않는다.
export default defineConfig({
  define: {
    "process.env.NODE_ENV": JSON.stringify("production"),
  },
  build: {
    outDir: "../public/vendor",
    // 같은 폴더에 Lightweight Charts 복사본이 함께 산다. 비우면 그것도 지워진다.
    emptyOutDir: false,
    minify: true,
    lib: {
      entry: "src/vendor/echarts.ts",
      formats: ["iife"],
      name: "FolioVendorEcharts",
      fileName: () => "echarts.js",
    },
  },
});
