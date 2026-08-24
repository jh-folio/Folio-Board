# Market Widgets

This feature stores the user's current-market dashboard widget settings.

It does not store quotes, chart data, briefing evidence, visual snapshots, or market-memory evidence.

**TradingView widgets are gone as of 0.5.4.** The dashboard board went with Legacy mode in 0.5, and the watchlist detail modal — the last consumer of `public/tradingview-widgets.js` — now draws the native `MarketChartFigure` chart. The bridge script, its `<script>` tag, and the `.tv-widget-*` CSS were removed. This settings file is kept **read-only** as the dashboard focus-symbol fallback; nothing writes it from the UI any more.

Settings live in `data/market-widget-settings.json`. If the file is missing or invalid, the app returns a safe default dashboard with a Market Overview widget, a focused NVIDIA chart, and a full-row Economic Calendar widget.

## UI Contract

- Nothing renders these settings as widgets any more. The dashboard reads the first chart symbol as a focus-symbol hint only.
- The widget editor guides symbols as `거래소/데이터소스 + 심볼`: an exchange/datasource dropdown (NASDAQ, KRX, FX_IDC 등) is combined with a free symbol input (`NVDA`) instead of typing the full `NASDAQ:NVDA` prefix. `splitTradingViewSymbol`/`joinTradingViewSymbol` convert between the two forms.

## API

```text
GET  /api/market-widgets/settings
POST /api/market-widgets/settings
```

The service validates widget type, size, symbol, theme, and widget count before saving.
