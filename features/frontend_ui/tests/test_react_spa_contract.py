from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def test_phase6_index_is_react_spa_entrypoint():
    html = (ROOT / "public" / "index.html").read_text(encoding="utf-8")

    assert '<div id="folioReactRoot"></div>' in html
    assert 'src="/react/folio-react.js"' in html
    assert 'src="/app.js"' in html
    assert 'class="view"' not in html
    assert 'data-view=' not in html
    assert 'id="briefingReaderModal"' not in html
    assert 'id="analysisReaderModal"' not in html
    assert 'id="topicrptReaderModal"' not in html


def test_phase6_app_js_is_bridge_only():
    javascript = (ROOT / "public" / "app.js").read_text(encoding="utf-8")

    for required in (
        "window.FolioBridge",
        "renderMarkdown",
        "splitReportTitle",
        "briefingSourcePanelHtml",
        "renderBriefingVisuals",
        "cleanupBriefingVisuals",
        "updateAgentContext",
        "openAgentDock",
    ):
        assert required in javascript

    for removed in (
        "switchViewById",
        "renderLeftNavigation",
        "FolioMarketWidgetLegacy",
        "LegacyViewHost",
        "DISABLED_FRONTEND_VIEWS",
        "addEventListener(\"keydown\"",
    ):
        assert removed not in javascript


def test_react_routes_cover_current_product_surfaces():
    routes = (ROOT / "web" / "src" / "app" / "routes.ts").read_text(encoding="utf-8")
    shell = (ROOT / "web" / "src" / "app" / "AppShell.tsx").read_text(encoding="utf-8")

    for route_id in (
        "home",
        "dashboard",
        "watchlist",
        "briefing",
        "rss",
        "market-memory",
        "analysis",
        "deep-research",
        "settings",
    ):
        assert f'id: "{route_id}"' in routes
        assert f'route.id === "{route_id}"' in shell

    assert "legacyViewId" not in routes
    assert "LegacyViewHost" not in shell
    assert "reactShell=0" not in shell
    assert "?legacy=1" not in shell


def test_report_rendering_and_visual_wrappers_remain_available():
    app_bridge = (ROOT / "public" / "app.js").read_text(encoding="utf-8")
    visuals = (ROOT / "public" / "briefing-visuals.js").read_text(encoding="utf-8")
    reader = (ROOT / "web" / "src" / "app" / "reportReader" / "ReportBody.tsx").read_text(encoding="utf-8")

    assert "FolioBriefingVisuals?.render" in app_bridge
    assert "FolioBriefingVisuals?.cleanup" in app_bridge
    assert "card.dataset.market = normalizeVisualMarket(snapshot.market)" in visuals
    assert "legacyBridge" in reader
    assert "bridge.renderMarkdown" in reader


def test_frontend_docs_name_react_spa_and_bridge_roles():
    readme = (ROOT / "features" / "frontend_ui" / "README.md").read_text(encoding="utf-8")
    web_readme = (ROOT / "web" / "README.md").read_text(encoding="utf-8")
    smoke_doc = (ROOT / "docs" / "frontend" / "react-spa-smoke-test.md").read_text(encoding="utf-8")

    assert "React SPA가 기본 프론트엔드" in readme
    assert "bridge-only" in readme
    assert "React SPA" in web_readme
    assert "public/app.js" in web_readme
    assert "React SPA Browser Smoke Test" in smoke_doc
    assert "#folioReactRoot .react-shell" in smoke_doc


def test_react_reader_contracts_are_component_owned():
    styles = (ROOT / "public" / "styles.css").read_text(encoding="utf-8")
    shell = (ROOT / "web" / "src" / "app" / "reportReader" / "ReportReaderShell.tsx").read_text(encoding="utf-8")
    dock = (ROOT / "web" / "src" / "app" / "ReactAgentDock.tsx").read_text(encoding="utf-8")
    context = (ROOT / "web" / "src" / "app" / "agentContext.ts").read_text(encoding="utf-8")

    assert "report-reader-shell-grid" not in styles
    assert "report-reader-side-section" not in styles
    assert "report-proposal-surface" not in styles
    assert "FolioNotePanel" in shell
    assert "proposalSurface" not in shell
    assert "agent-proposal" in dock
    assert "window.FolioAgent" in context


def test_report_body_line_spacing_keeps_enter_breaks_readable():
    styles = (ROOT / "public" / "styles.css").read_text(encoding="utf-8")

    assert ".markdown-brief p + p" in styles
    assert "margin-top: 0.72em" in styles
    assert ".markdown-brief h3 + ul" in styles
    assert "margin-top: -4px" not in styles
