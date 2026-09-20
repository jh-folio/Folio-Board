# Third-party notices

## TradingView Lightweight Charts™

Folio Board bundles TradingView Lightweight Charts version 5.2.0 for interactive
briefing price charts. The file is served from `public/vendor/lightweight-charts.js`,
an unmodified copy of the npm release (its license header is kept in the file).

- Project: <https://github.com/tradingview/lightweight-charts>
- License: Apache License 2.0
- Copyright © 2025 TradingView, Inc. <https://www.tradingview.com/>

The user-facing chart area retains the required TradingView attribution and
link through `layout.attributionLogo`, with an additional visible notice below
the briefing visuals.

## Apache ECharts and zrender

Folio Board bundles Apache ECharts version 6.1.0 for charts that need more than
the hand-drawn SVG charts provide, such as the market heat map. The file is served
from `public/vendor/echarts.js`, a custom build that registers only the chart
types and components Folio Board uses and renders to SVG. It includes zrender
6.1.0, the rendering library ECharts is built on. The license notices are kept at
the top of the file.

- Project: <https://echarts.apache.org/> and <https://github.com/apache/echarts>
- License: Apache License 2.0
- Copyright 2017-2026 The Apache Software Foundation. This product includes
  software developed at The Apache Software Foundation
  (<https://www.apache.org/>).

zrender (<https://github.com/ecomfe/zrender>) is licensed under the BSD 3-Clause
License. Copyright (c) 2017, Baidu Inc. All rights reserved.

To rebuild the bundle after changing the pinned version or the registered
components, run `npm run build:vendor` in `web/` and update this section.

## Tesseract OCR

Folio Board can call a user-installed Tesseract executable for local-first
portfolio screenshot recognition. Tesseract is not installed automatically.

- Project: <https://github.com/tesseract-ocr/tesseract>
- License: Apache License 2.0

The import flow requests the `kor` and `eng` language data, returns only a
normalized editable draft, and does not retain the image, raw OCR text, or word
bounding boxes.

## Fast-origin news services

Fast-origin leads are promoted from Korean RSS items Folio Board already
collected. No additional network call, credential, or provider setting is
involved, and no external service is bundled. Publisher names and links
identify the origin of the feeds the user enabled; publisher terms continue to
apply.

Leads enter Folio Board as metadata-only and unconfirmed. They do not count as
report evidence until corroborated through an eligible evidence path.

## Market index names and constituent lists

Folio Board ships reference lists of the companies in several market indices so
that charts, heat maps, and company lookup work offline. The index names —
including S&P 500, KOSPI 200, Nikkei 225, FTSE 100, DAX, CAC 40, and AEX — are
trademarks of their respective owners. They are used here to identify which
market a list of companies refers to. Folio Board is not affiliated with, endorsed
by, or licensed by any index provider, and the lists are reference data for
local research rather than a redistribution of an index product.

## SEC and DART official data

Company identification and official filing text come from public filing
systems: the U.S. Securities and Exchange Commission (EDGAR, company tickers,
companyfacts) and, for Korean companies, DART. Requests identify Folio Board
through `SEC_USER_AGENT`. Folio Board reads what these systems publish openly and
does not bypass access controls.

## Optional OpenAI Vision import

When the user explicitly selects external Vision and consents for that request,
Folio Board can send only the browser-cropped/redacted image to the configured
OpenAI API with storage disabled in the request. The local import remains the
default. Users should review the current provider privacy and retention terms
before enabling this option.
