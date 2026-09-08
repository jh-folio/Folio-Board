# Folio Board React SPA (web/)

`web/` owns the Folio Board frontend. It is a Vite + React + TypeScript app that
builds into `public/react/folio-react.js`, which is loaded by the FastAPI static
entrypoint at `public/index.html`.

## How It Fits Together

```text
public/index.html      # minimal static entrypoint with #folioReactRoot
public/app.js          # bridge-only helpers used by React readers and Agent context
public/styles.css      # shared Folio Board design tokens and component styles
web/src/main.tsx       # mounts the React SPA
web/src/app/           # AppShell, routes, Agent Home, readers, feature screens
web/src/islands/       # reusable React surfaces consumed by routes
public/react/          # committed Vite build output
```

- React owns routing, navigation, Agent Home, Deep Research, report readers,
  RSS, Market Memory, Company Analysis, Dashboard, Watchlist, and Settings.
- Deep Research is a default 0.2 surface in the left navigation, Home quick
  actions, and command palette. Dashboard and Watchlist remain routable for
  compatibility but stay hidden from those default surfaces.
- `public/app.js` no longer owns view routing. It remains as a compatibility
  bridge for `FolioBridge` methods such as `renderMarkdown`,
  `briefingSourcePanelHtml`, `renderBriefingVisuals`, `updateAgentContext`, and
  `openAgentDock`.
- The built bundle in `public/react/` is committed so users can run Folio Board
  without a local Node build step.

## Build

```bash
cd web
npm install
npm run build      # -> ../public/react/folio-react.js
npm run typecheck  # tsc --noEmit
npm test           # source contract tests
```

Run `npm run build` after changing `web/src` so `public/react/folio-react.js`
matches the source.
