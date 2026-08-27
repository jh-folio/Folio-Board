# Europe/Japan source capability matrix

> Assessed: 2026-08-04  
> Release target: 0.5.0  
> Scope: Japan and the six European core markets (`GB`, `DE`, `FR`, `NL`, `IT`, `ES`)

This document is the source, access, and redistribution decision record for the
0.5 Europe/Japan expansion. It is a feasibility contract, not an implementation
claim. A provider is not supported until its adapter and fixtures pass the gates
in `plan/release/0.5_PLAN.md`.

## Status vocabulary

| Status | Meaning |
|---|---|
| `verified_api` | Official, documented machine interface verified. |
| `verified_download` | Official search plus stable document download verified; no public API contract. |
| `browser_only` | Official browser discovery exists, but automation is not contractually stable. |
| `key_required` | Public registration/key is required; the key is never bundled. |
| `manual_save_required` | Runtime must ask the user to save an official/IR document locally. |
| `unavailable` | Not selected for an automated 0.5.0 path. |

## Release-gate decision

| Layer | Decision | Evidence and boundary |
|---|---|---|
| RSS / briefing | **GO** | Existing BBC/Guardian feeds cover the UK. Localized Google News public RSS probes for `JP`, `DE`, `FR`, `NL`, `IT`, and `ES` returned HTTP 200 and fresh items on 2026-08-04. These are headline/summary-only aggregator inputs, not a full-text contract. Original-language items remain visible; no RSS translation is introduced. |
| Exchange calendar | **GO** | JPX, LSE, Xetra, Euronext (Amsterdam/Paris/Milan), and BME publish official annual calendars. Dates are copied into versioned fixtures and must be refreshed annually. |
| Representative indices | **GO, line-only** | The selected delayed/EOD yfinance symbols returned data in a bounded live probe. No constituent snapshot is bundled. |
| Tier 0 — SEC 20-F | **GO** | SEC submissions and Company Facts cover 20-F without a key. Both `us-gaap` and `ifrs-full` namespaces must be handled; missing IFRS concepts remain missing, never zero. |
| Tier 1 — EDINET | **GO, key required** | EDINET code lookup and API v2 document-list/download paths are official and documented. A user-issued Subscription Key is required. |
| Tier 2 — UK | **PILOT** | Companies House provides official company identity, filing history, and document APIs. FCA NSM remains official browser discovery for regulated annual reports. |
| Tier 2 — Netherlands | **PILOT** | AFM is the OAM and exposes register exports plus direct ESEF ZIP downloads. |
| Tier 2 — Spain | **PILOT** | CNMV exposes official issuer searches and direct PDF/ESEF ZIP downloads, but no public API contract was found. |
| Tier 2 — Germany | **DEFER / manual only** | Unternehmensregister requires a security query/CAPTCHA for accounting documents. Use official discovery plus issuer IR/manual save. |
| Tier 2 — France | **DEFER / manual only** | AMF sends filings to the DILA OAM, but no stable public API/bulk contract was verified for `info-financiere.fr`. |
| Tier 2 — Italy | **DEFER / manual only** | CONSOB-authorized OAMs are public browser repositories, but no stable public API/bulk contract was verified. |

Tier 2 pilots are source-feasibility decisions only. They do not become user-facing
support until a bounded adapter, fixture, provenance record, and failure behavior
exist. The three deferred countries stay explicitly `unavailable` for automated
company analysis; this does not remove them from RSS, briefing, calendars, or
representative-index coverage.

## Required market layer

### News/RSS intake

| Country | Selected public feed | Language | Full text | Freshness probe | Stability/cache | Failure behavior |
|---|---|---:|---:|---|---|---|
| GB | BBC Business and Guardian Business direct RSS | `en` | allowed when publicly available | 49/41 items; latest `2026-08-04T10:34:45Z` / `10:48:19Z`, checked `11:10Z` | Cache normalized items permanently; poll on the existing RSS schedule | Keep other Europe/global feeds and emit a GB coverage gap if both direct feeds fail. |
| JP | Google News RSS queries for `日経平均 OR 日本経済` (`JP:ja`) and `Nikkei 225 OR Japan economy` (`JP:en`) | `ja`, `en` | no | 100/50 items; latest `2026-08-04T11:05:00Z` / `09:37:33Z`, checked `11:10Z` | Public RSS but undocumented automation contract; headline/summary only | Retry with bounded backoff, then retain prior items and emit a JP gap. |
| DE | Google News RSS query for `DAX OR deutsche Wirtschaft`, locale `DE:de` | `de` | no | 29 items; latest `2026-08-04T10:40:51Z`, checked `11:10Z` | Same aggregator boundary | Retain prior items; global English corroboration may supplement but must not silently claim DE coverage. |
| FR | Google News RSS query for `CAC 40 OR économie française`, locale `FR:fr` | `fr` | no | 63 items; latest `2026-08-04T10:44:21Z`, checked `11:10Z` | Same aggregator boundary | Same. |
| NL | Google News RSS query for `AEX OR Nederlandse economie`, locale `NL:nl` | `nl` | no | 40 items; latest `2026-08-04T09:12:49Z`, checked `11:10Z` | Same aggregator boundary | Same. |
| IT | Google News RSS query for `FTSE MIB OR economia italiana`, locale `IT:it` | `it` | no | 21 items; latest `2026-08-04T08:10:00Z`, checked `11:10Z` | Same aggregator boundary | Same. |
| ES | Google News RSS query for `IBEX 35 OR economía española`, locale `ES:es` | `es` | no | 47 items; latest `2026-08-04T10:12:43Z`, checked `11:10Z` | Same aggregator boundary | Same. |

Feed configuration must record `language`, `country`, `default_market`,
`source_type`, `reliability_tier`, and the probe date. Google News entries follow
the existing aggregator redirect policy: do not fetch the aggregator HTML as
article content and do not replace the RSS summary. Briefings may use these items
as leads, but local-language headline-only items cannot dominate an issue without
corroboration, price evidence, or an official source.

The enabled 0.5 rows are `source_type=news`, `reliability_tier=2`. The config
loader rejects non-canonical market values, countries outside the fixed universe,
unknown languages/source types, country-market mismatches, empty probes, and
probe snapshots whose latest parsed item was already more than 72 hours old.

### Exchange calendars and representative indices

| Market | Official calendar operator and URL | Calendar acquisition | Representative symbol | Probe result | Constituent redistribution |
|---|---|---|---|---|---|
| Japan | [JPX market holidays](https://www.jpx.co.jp/english/corporate/about-jpx/calendar/) | Copy the published annual dates into a reviewed fixture | `^N225` | data returned | Nikkei retains index IP and describes licensing for display/business use. Do not bundle Nikkei constituents or weights. |
| UK | [London Stock Exchange business days](https://www.londonstockexchange.com/trade/trading-access/business-days) | Copy full closures and half days annually | `^FTSE` | data returned | No FTSE constituent snapshot is approved for redistribution; do not bundle. |
| Germany | [Xetra trading calendar](https://www.xetra.com/xetra-en/trading/trading-calendar-and-trading-hours) | Copy Xetra closures and exceptional trading days annually | `^GDAXI` | data returned | STOXX/DAX data access and redistribution can require a licence; do not bundle. |
| France | [Euronext trading hours and holidays](https://www.euronext.com/en/trading/trading-hours-holidays) — Paris | Copy venue-specific closures/half days annually | `^FCHI` | data returned | Euronext requires licensing for redistribution/commercial use of index data; do not bundle. |
| Netherlands | Same Euronext source — Amsterdam | Same | `^AEX` | data returned | Same Euronext restriction. |
| Italy | Same Euronext source — Milan | Same; Milan differs on some year-end sessions | `FTSEMIB.MI` | data returned; `^FTMIB` did not | Same Euronext restriction. |
| Spain | [BME stock exchange calendar](https://www.bolsasymercados.es/en/bme-exchange/trading/trading-calendar.html) | Copy closures and shortened sessions annually | `^IBEX` | data returned | No IBEX constituent snapshot is approved for redistribution; do not bundle. |
| Europe aggregate | Venue sources above | Derived only after all required country calendars load | `^STOXX` | data returned | STOXX Europe 600 constituents/weights are not bundled. |

yfinance is a best-effort delayed/EOD runtime provider, not an official index
source and not a real-time quote contract. Every value carries provider, as-of,
and stale/unavailable state. A failed symbol produces a `dataGap`; it is not
replaced by an inferred value. `^TOPX` and `^FTMIB` failed the bounded probe and
are excluded.

## Tier 0 — SEC 20-F

| Field | Decision |
|---|---|
| Operator / URL | U.S. SEC: `https://data.sec.gov/submissions/CIK##########.json`, `https://data.sec.gov/api/xbrl/companyfacts/CIK##########.json`, and the filing archive on `sec.gov/Archives`. |
| Company identifier | CIK is canonical. Resolve exchange ticker/name with the SEC company tickers dataset before aliases. Preserve home-country identifiers as secondary identities. |
| Documents | 20-F/20-F-A annual reports; 6-K can be discovered but is not promoted to annual financial evidence. Filing HTML/iXBRL and exhibits are available from the accession. |
| Structured / narrative | Company Facts JSON and filing iXBRL for facts; primary 20-F HTML for narrative paragraph scoring. |
| Taxonomy | Accept `us-gaap` and `ifrs-full`. Record the source namespace on every mapped concept. An unmapped IFRS fact is missing, not zero. |
| Language | Usually English for SEC filings. Preserve filing language metadata when different. |
| Authentication / rate | No key. Use a declared User-Agent, bounded concurrency, semantic cache, conditional retry, and the SEC fair-access policy. Prefer nightly bulk archives for true bulk work. |
| History / freshness | Submission history includes current and older filing shards. APIs update in real time as filings disseminate; bulk archives refresh nightly. |
| Stability | `verified_api`. Existing SEC paths remain primary for eligible Europe/Japan issuers. |
| Fixture acquisition | Save a minimized, synthetic/redacted shape from a public 20-F Company Facts response with both taxonomy namespaces represented. Never embed a private path or request header. |
| Failure / fallback | Use a fresh or bounded last-known-good cache. If structured facts fail, keep the official 20-F narrative path and expose numeric gaps; then allow a user-saved official filing. Never substitute article numbers. |

## Tier 1 — Japan EDINET and JPX

| Field | EDINET | JPX listed-company resources |
|---|---|---|
| Operator / URL | Japan Financial Services Agency, [EDINET API guidance](https://disclosure2dl.edinet-fsa.go.jp/guide/static/disclosure/WEEK0060.html), base `https://api.edinet-fsa.go.jp/api/v2` | Japan Exchange Group, [Listed Company Search](https://www.jpx.co.jp/english/listing/co-search/01.html) |
| Company identifier | EDINET code; preserve securities code and corporate number when present | Securities code and ISIN; exchange/segment metadata |
| Documents | Annual Securities Report, amendments, semiannual/quarterly and extraordinary reports | Listed-company master/disclosure links; not the primary annual-document API |
| Structured / narrative | XBRL package and converted CSV (`type=5` when `csvFlag=1`); body/audit bundle (`type=1`) | Browser HTML/search metadata; linked disclosures may be PDF/HTML |
| Language | Japanese primary; English file package is available when the filer submitted it (`type=4`) | Japanese/English site metadata varies by issuer |
| Authentication | `Subscription-Key` is mandatory for API v2. User registration is required; the key stays in local settings/environment. | Public browser search; no key and no verified public bulk/API contract |
| Rate/cache | Official FAQ says the list changes about once per minute and recommends no more than roughly one request per minute. Cache daily lists and downloaded immutable documents permanently; back off on throttling. | Cache lookup metadata; do not crawl or depend on browser markup as a high-volume API. |
| History / freshness | Document-list dates can be requested within the previous ten years. New disclosures normally converge within about one minute. | Search is updated daily; historical financial-result disclosures are browser-oriented. |
| Stability | `verified_api`, `key_required` | `browser_only` secondary identity/discovery source |
| Fixture acquisition | Use an official public filing, strip the key/request URL, retain only the minimal list metadata and a small taxonomy sample. Record accession-like document ID and public source URL. | Hand-author a minimal synthetic lookup result based on documented fields. |
| Failure / fallback | Last-known-good cache, then JPX/issuer IR discovery and explicit `manual_save_required`. Tier 1 cannot claim success without an official annual report. | Fall back to EDINET code list or issuer IR; expose a lookup gap. |

EDINET API download types selected for implementation are `1` (body and audit
package), `2` (PDF), `4` (English package when filed), and `5` (converted CSV).
Attachments (`3`) remain opt-in until document relevance scoring is defined.

## Tier 2 — European country sources

### UK

| Field | FCA National Storage Mechanism | Companies House |
|---|---|---|
| Operator / URL | Financial Conduct Authority, [NSM](https://data.fca.org.uk/#/nsm/nationalstoragemechanism) and [user FAQ](https://data.fca.org.uk/artefacts/NSM_user_help_and_FAQs.pdf) | UK Companies House, [API get started](https://developer.company-information.service.gov.uk/get-started), [authentication](https://developer.company-information.service.gov.uk/authentication) |
| Identifier | Issuer name/LEI and filing metadata | Company number canonical; name aliases secondary |
| Documents | Regulated information, annual reports, structured annual financial reports | Company profile, filing history, document metadata/content including filed accounts |
| Format | ESEF package/PDF when filed; browser discovery | REST JSON metadata plus document download, commonly PDF |
| Language | English; issuer filings may include other languages | English/Welsh metadata and filed documents as submitted |
| Auth/rate/cache | No documented public API contract verified; cache discovered immutable files | API key via HTTP Basic. Default limit: 600 requests per five minutes. Cache company identity and immutable filing documents. |
| History/freshness | Public NSM archive; freshness follows issuer submission | Live public register/filing history |
| Stability | `browser_only` | `verified_api`, `key_required` |
| Fixture | Synthetic NSM search row plus one public ESEF/PDF shape | Minimized public JSON response with company number and one filing/document link |
| Failure/fallback | Companies House, issuer IR, then manual save | FCA NSM/issuer IR; return explicit identity or document gap |

**Tier 2 decision: `PILOT`.** Companies House supplies a stable official identity
and document route; FCA NSM remains the regulated-source cross-check.

### Germany

| Field | Decision |
|---|---|
| Operator / URL | Bundesanzeiger Verlag on behalf of the German state, [Unternehmensregister search](https://www.unternehmensregister.de/en/howto/search); BaFin/regulatory notices are secondary discovery. |
| Identifier | Company name and EUID/register identity; preserve LEI/ISIN when a filing exposes them. |
| Documents | Annual financial statements, annual financial reports, company reports, capital-market disclosures. |
| Structured / narrative | Domestic issuer ESEF XHTML; PDF/Office may also appear. |
| Language | German primary, issuer English variants possible. |
| Auth/rate/cache | General public search does not require registration, but accounting/company-report retrieval requires a CAPTCHA/security query. Some deposited micro-company accounts require registration/fees. No automated rate contract selected. |
| History/freshness | Official register history subject to the register's publication/retention rules. |
| Stability | `manual_save_required` for report retrieval; not an automated 0.5.0 adapter. |
| Redistribution | Cache user-acquired official documents locally for analysis; do not redistribute register datasets. |
| Fixture | Hand-authored synthetic search/result shape only; a user-saved public issuer IR ESEF ZIP can test parsing. |
| Failure/fallback | Issuer IR official annual report, then user manual save. Return `unavailable` for automated Tier 2. |

**Tier 2 decision: `DEFER / manual only`.** Automating around the security query is
explicitly out of scope.

### France

| Field | Decision |
|---|---|
| Operator / URL | Autorité des marchés financiers (AMF) filing intake; DILA is the French OAM at [info-financiere.fr](https://www.info-financiere.fr/). See [AMF ESEF filing guidance](https://www.amf-france.org/fr/actualites-publications/actualites/formats-et-modalites-de-depot-des-rapports-financiers-annuels-et-des-documents-denregistrement). |
| Identifier | Issuer name plus LEI/ISIN/SIREN when present; no new Folio canonical identifier until an adapter proves one stable. |
| Documents | Annual financial report and URD that serves as the annual report; issuer IR copies. |
| Structured / narrative | Official ESEF XHTML/iXBRL from 2022 onward; PDF/URD narrative variants. |
| Language | French primary; English variants may be separate issuer documents. Preserve variants separately. |
| Auth/rate/cache | Public browser archive; no verified stable public API/bulk or numerical rate contract. Cache immutable downloaded reports. |
| History/freshness | OAM archive; ESEF requirement applies to covered annual reports from 2022 filing workflows. |
| Stability | `browser_only`; issuer IR/manual save fallback. |
| Redistribution | No OAM dataset redistribution is approved; package only synthetic fixtures. |
| Fixture | Synthetic OAM row plus a small, public issuer ESEF sample acquired manually with source metadata. |
| Failure/fallback | Issuer IR official report, then manual save; automated Tier 2 remains `unavailable`. |

**Tier 2 decision: `DEFER / manual only`.** Re-evaluate when a documented API or
stable download contract is verified.

### Netherlands

| Field | Decision |
|---|---|
| Operator / URL | Netherlands Authority for the Financial Markets (AFM), [Financial Reporting register](https://www.afm.nl/nl-nl/sector/registers/meldingenregisters/financiele-verslaggeving) and [ESEF guidance](https://www.afm.nl/en/sector/effectenuitgevende-ondernemingen/financiele-en-duurzaamheidsverslaggeving/jaarlijkse-verslaggeving-in-esef). |
| Identifier | Issuer name and AFM register entry; preserve LEI/ISIN/KVK when supplied. |
| Documents | Annual/half-year financial reporting entries and attached official documents. |
| Structured / narrative | Register offers CSV/XML exports; ESEF entries expose direct ZIP downloads containing XHTML/iXBRL. PDF variants may be present. |
| Language | Dutch/English metadata and documents as filed. |
| Auth/rate/cache | Public search/export/download; no key and no numerical public rate contract verified. Use low concurrency and cache exports/documents. |
| History/freshness | Public reporting register; freshness follows AFM publication. |
| Stability | `verified_download`; pilot must prove export schema and direct-link stability. |
| Redistribution | Do not bundle register exports or index constituents. Synthetic fixtures only. |
| Fixture | Download one public ESEF ZIP, minimize to taxonomy/manifest shapes, and hand-author a synthetic register row. |
| Failure/fallback | Issuer IR, then manual save; retain last-known-good identity and report metadata with a stale badge. |

**Tier 2 decision: `PILOT`.** This is the strongest euro-area automated candidate.

### Italy

| Field | Decision |
|---|---|
| Operator / URL | CONSOB authorizes OAM storage mechanisms. Current public repositories include [1INFO](https://www.1info.it/) and [eMarket STORAGE](https://www.emarketstorage.it/). [CONSOB issuer regulation](https://www.consob.it/documents/d/area-pubblica/reg11971_1999_modificato_23463_2025) defines authorized storage requirements. |
| Identifier | Issuer name plus tax/LEI/ISIN identifiers when exposed by the OAM or issuer. |
| Documents | Regulated information including periodic financial reports and annual reports. |
| Structured / narrative | ESEF XHTML/iXBRL packages and PDF/press documents as filed. |
| Language | Italian primary; issuer English variants possible. |
| Auth/rate/cache | Public browser search; no verified stable public API/bulk or numerical rate contract. Cache immutable files acquired through supported downloads. |
| History/freshness | OAM archives receive regulated disclosures; exact public retention/download contracts must be proven in a pilot. |
| Stability | `browser_only`; two repositories increase discovery coverage but not API stability. |
| Redistribution | Do not bundle OAM datasets or index constituents. Synthetic fixtures only. |
| Fixture | Synthetic OAM metadata plus a manually acquired public issuer ESEF sample. |
| Failure/fallback | Try the alternate authorized OAM, then issuer IR/manual save; automated Tier 2 stays `unavailable`. |

**Tier 2 decision: `DEFER / manual only`.** Do not build a scraper around unstable
browser markup.

### Spain

| Field | Decision |
|---|---|
| Operator / URL | Comisión Nacional del Mercado de Valores (CNMV), [official annual financial reports register](https://www.cnmv.es/portal/consultas/em_inffinanual?id=EE&lang=es). |
| Identifier | Issuer record/NIF plus issuer name; preserve LEI/ISIN when supplied. |
| Documents | Audited annual accounts, audit reports, annual financial reports and related filings. |
| Structured / narrative | The issuer report page exposes ESEF XHTML and consolidated ZIP/XBRL downloads, plus PDF via the official registration number. |
| Language | Spanish primary; English/other variants as filed. |
| Auth/rate/cache | Public browser search/download; no key and no documented public API/rate contract. Use bounded requests and permanent immutable-document cache. |
| History/freshness | Official issuer archive; publication dates are part of the result. |
| Stability | `verified_download`; pilot must prove search parameters/direct download stability without brittle HTML assumptions. |
| Redistribution | Do not bundle registry datasets or IBEX constituents. Synthetic fixtures only. |
| Fixture | Minimize a public ESEF ZIP to manifest/taxonomy shapes and hand-author a synthetic result row. |
| Failure/fallback | Issuer IR, then manual save; if discovery markup changes, return `unavailable`, not guessed results. |

**Tier 2 decision: `PILOT`, conditional on a bounded download proof.**

## Common European ESEF contract

| Field | Decision |
|---|---|
| Authority / URL | European Securities and Markets Authority, [ESEF](https://www.esma.europa.eu/issuer-disclosure/electronic-reporting). |
| Scope | Annual financial reports of issuers on EU regulated markets are XHTML; IFRS consolidated financial statements are tagged with Inline XBRL. |
| Taxonomy | Detect the ESEF taxonomy version from the filing package. Preserve original QName and taxonomy year before mapping to Folio concepts. Extension concepts require anchoring-aware handling. |
| Narrative | XHTML is the canonical narrative source. PDF is a view/fallback and must not silently replace a different official ESEF version. |
| Language | Store document language and original title. Separate local-language and English variants; never overwrite one with a translation. |
| Parser | Arelle is the planned parser dependency. Its Windows packaging, licence, resource limits, and malformed-package behavior remain a Stage 0/implementation gate. |
| Cache | The official package is immutable evidence. Store content hash, source URL, filing identity, fetched-at time, and parser/taxonomy version. |
| Failure | If structured parsing fails, retain the official XHTML/PDF as narrative evidence, add a structured-data gap, and do not infer numbers. |
| ESAP | ESAP collection began in July 2026, but its public portal is planned for July 2027. It is not a 0.5 runtime provider. |

## Licensing and packaging rules

1. No paid-only source is a core acceptance dependency.
2. API keys, request URLs containing keys, cookies, and authenticated responses are
   never fixtures or release assets.
3. No FTSE, STOXX/DAX, Euronext, Nikkei, or IBEX constituent/weight snapshot enters
   `config/`, `defaults/`, tests, or a release package until redistribution approval
   is documented. The 0.5 fallback is representative line indices with explicit
   provider attribution.
4. Public official filings may be downloaded into a user's private
   `research-inbox/filings/`; Folio OS does not republish those filings in its source
   distribution.
5. Repository fixtures are synthetic or aggressively minimized structural samples.
   They contain no private titles, browsing history, local paths, credentials, or
   unrelated document content.

## Adapter acceptance checklist

Before any row changes from `PILOT` or `manual_save_required` to supported:

- resolve a canonical company identity and preserve secondary identifiers;
- acquire one current and one older annual report through the documented path;
- record source URL, operator, document language, filing date, identifier, content
  hash, fetched-at time, parser version, and taxonomy namespace;
- prove bounded timeout, retry, cache, stale, and circuit-breaker behavior;
- prove missing structured facts stay missing rather than becoming zero;
- preserve the local-language original and any English variant as separate sources;
- add synthetic/minimized fixtures and offline tests;
- return an explicit `dataGap` plus issuer-IR/manual-save action on failure;
- re-check provider terms and page/API behavior immediately before release.

## Primary references

- SEC: [EDGAR APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)
- EDINET: [operation guides and API v2 specification](https://disclosure2dl.edinet-fsa.go.jp/guide/static/disclosure/WEEK0060.html)
- JPX: [listed company search](https://www.jpx.co.jp/english/listing/co-search/01.html)
- FCA: [NSM user FAQ](https://data.fca.org.uk/artefacts/NSM_user_help_and_FAQs.pdf)
- Companies House: [developer guidelines](https://developer.company-information.service.gov.uk/developer-guidelines/)
- Germany: [Unternehmensregister search rules](https://www.unternehmensregister.de/en/howto/search)
- France: [AMF ESEF FAQ](https://www.amf-france.org/fr/actualites-publications/dossiers-thematiques/esef/esef-vos-questions-frequentes)
- Netherlands: [AFM financial reporting register](https://www.afm.nl/nl-nl/sector/registers/meldingenregisters/financiele-verslaggeving)
- Italy: [CONSOB ESAP/OAM explanation](https://www.consob.it/web/consob/esap-european-single-access-point)
- Spain: [CNMV annual financial reports](https://www.cnmv.es/portal/consultas/em_inffinanual?id=EE&lang=es)
- ESMA: [ESEF](https://www.esma.europa.eu/issuer-disclosure/electronic-reporting) and [ESAP](https://www.esma.europa.eu/esmas-activities/data/european-single-access-point-esap)
- Index terms: [Euronext index data use](https://live.euronext.com/en/products/indices/data-use), [STOXX licence application](https://www.stoxx.com/license-agreement-form), [Nikkei licensing](https://indexes.nikkei.co.jp/nkave/license/index.en.html)
