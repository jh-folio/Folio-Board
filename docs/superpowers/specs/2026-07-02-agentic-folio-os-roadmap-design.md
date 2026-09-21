# Agentic Folio OS Roadmap Design

Date: 2026-07-02
Status: Draft for user review

## Purpose

Folio OS should evolve from a collection of manual research tools into an agentic investment research workspace.

The next version should keep the core two-layer model intact:

- Canonical reports remain source-grounded outputs based on external evidence.
- Personal interpretation remains a separate overlay or hypothesis layer.
- User notes, portfolio views, and preferences guide analysis but do not become evidence.

The product direction is to make Folio OS feel less like a set of buttons that the user operates manually and more like a local research system that continuously gathers short-term evidence, maintains medium-term market understanding, and lets the user talk to an AI Agent anywhere in the app.

## Product Principles

1. Agent is always available, but not always intrusive.
2. The Agent starts as a companion and becomes a task manager only when the user asks it to perform work.
3. RSS and article intake are the short-term memory layer.
4. Market Memory is the medium-term memory layer.
5. Briefings, company analyses, deep research, overlays, and reviews consume both short-term and medium-term memory.
6. Market Memory UI should show the user's market state, not the database machinery behind it.
7. Automation should prepare the workspace before the user arrives.
8. Native Folio investment notes and a gradual React shell migration remain part of the roadmap, even if they follow the Agent and Market Memory work.

## Target Memory Hierarchy

```text
RSS / Articles / Evidence Items
  = short-term memory
  = incoming events, raw evidence, daily market noise

Market Memory / Market State
  = medium-term memory
  = repeated narratives, regime state, drivers, uncertainty, checkpoints

Briefing / Company Analysis / Topic Report / Investment Review
  = generated outputs
  = short-term evidence + medium-term market state + optional user hypothesis
```

Today, Market Memory is mainly accumulated from briefings. The target architecture reverses that dependency: Market Memory should be able to read directly from the RSS/evidence layer and should exist before a briefing is generated.

## Phase 1: Global Agent Layer

### Goal

Add a persistent Agent experience that works across every screen and understands the user's current context.

The Agent is not a separate tab. It is a global layer that can answer questions about the current screen, explain visible reports, suggest next actions, and, when explicitly asked, execute controlled Folio OS tasks through existing feature services and Agent Mode.

### Interaction Model

The Agent has two behavioral modes:

```text
Companion Mode
  - default on every screen
  - answers questions
  - summarizes current context
  - explains market or report implications
  - suggests actions
  - does not mutate saved reports or memory by default

Task Mode
  - entered when the user asks for a concrete action
  - proposes a plan
  - gathers or prepares context
  - drafts changes or outputs
  - asks for approval before writeback
```

Examples:

- "What matters most in this briefing?" stays in Companion Mode.
- "Rewrite this company analysis with a bear-case section" enters Task Mode.
- "Update Market Memory from the latest RSS" enters Task Mode.
- "Create tomorrow morning automation for RSS, memory, and briefing" enters Task Mode.

### Surface-Aware Behavior

The Agent should not be hard-limited by screen type, but each surface should provide a default posture and suggested actions.

| Surface | Default posture | Typical actions |
| --- | --- | --- |
| Briefing | Companion | explain briefing, portfolio impact, connect to market state, show counterpoints |
| Company Analysis | Companion first, Task on request | revise section, add scenario, improve evidence, create overlay |
| Topic Report | Companion first, Task on request | refine question, expand evidence pack, rewrite report, add challenging evidence |
| Market State | Companion | explain medium-term regime, show drivers, compare with portfolio/thesis |
| Portfolio | Companion | exposure review, risk interpretation, link holdings to market drivers |
| Notes | Companion | structure thesis, identify assumptions, create checkpoints, challenge hypothesis |

### UI Model

Use a three-state Agent UI:

```text
Collapsed
  small floating Agent button with connection/status indicator

Docked
  right-side Agent panel on desktop
  bottom sheet on mobile

Focused
  larger workspace for multi-step tasks, plans, drafts, and approval flows
```

For briefing/report reader modals, the global dock should not remain trapped behind the modal. The reader should expose an in-modal Ask Agent drawer:

```text
Report Reader Modal
  - normal reading view by default
  - small Ask Agent control
  - drawer opens inside the modal when needed
  - long tasks can escalate into Focused Agent Workspace
```

This preserves reading width while keeping the Agent available.

### Context Contract

The frontend should maintain a lightweight `currentAgentContext` object and send it with Agent messages.

Example:

```json
{
  "surface": "briefing_reader",
  "viewId": "briefing",
  "reportKind": "briefing",
  "reportId": "2026-07-02.us",
  "marketScope": "us",
  "selectedText": "",
  "visibleSection": "leading_companies",
  "portfolioLinked": true
}
```

The backend should turn this into a safe context pack using existing `features/agent_mode` boundaries. Secrets and `.env` values must never enter the pack.

### Writeback Safety

Any task that changes saved state requires explicit user approval.

Examples:

- Updating a report markdown requires preview or diff approval.
- Saving a Personal Overlay writes only the overlay field.
- Updating Market Memory writes only normalized enum-validated state.
- User notes remain hypothesis, not evidence.

## Phase 2: RSS Short-Term Memory to Market Memory

### Goal

Market Memory should no longer depend only on generated briefings. It should read directly from the RSS/evidence layer and maintain medium-term market state as an independent shared memory.

### Target Flow

```text
RSS collection
  -> evidence_items / rss_feed_items
  -> short-term digest
  -> market memory candidates
  -> medium-term market state update
  -> briefings/reports/Agent consume market state
```

### Short-Term Digest

Do not promote raw articles directly into Market Memory. Add a digest step that clusters and summarizes short-term evidence into event groups.

Digest items should capture:

- event or driver summary
- source count and publisher diversity
- related tickers, industries, regions, tags
- likely story family
- whether the item supports, challenges, or is neutral to an existing market state
- whether the item is new noise, a repeated signal, or a possible regime change

The digest should be stored as structured data, not only markdown. It can live in `market-memory.sqlite3` because it participates in joins with story families, states, thesis links, and future notes.

### Promotion Rules

Only some digest items should update Market Memory.

Promotion signals:

- repeated across multiple sources
- high source reliability
- connected to an active/watch story family
- market impact evidence exists
- contradicts a high-confidence current narrative
- introduces a new risk or checkpoint that affects existing states

Non-promotion examples:

- single low-signal article
- duplicate wire copy
- article with weak market relevance
- one-off headline without market or thesis connection

### Result Consumption

Briefings should consume:

- latest relevant RSS/articles as short-term evidence
- current Market State as medium-term context

Company Analysis and Topic Reports should consume:

- local evidence selected for the company/topic
- relevant Market State drivers
- user hypothesis only as separate Personal Overlay or Task Mode context

## Phase 3: Market State Dashboard v2

### Goal

Replace the current operator-style Market Memory UI with a user-facing market state dashboard.

The current screen exposes too much internal machinery: active states, taxonomy, evidence counts, audit, suggestions, story maps, settings, and maintenance controls. Those remain useful backend tools, but the default user experience should be a concise interpretation of the current medium-term market situation.

### User-Facing Shape

Top section:

```text
Current Medium-Term Market State

AI infrastructure remains the dominant market axis, but rates, power constraints,
and China demand risk are limiting the breadth of winners.
```

Driver cards:

```text
1. AI semiconductor supply chain - strengthening
2. Data center power bottleneck - strengthening
3. Rates and dollar liquidity - conflicted
4. Korea semiconductor exports - improving
5. Middle East energy risk - watch
```

Each driver card should show only the useful surface fields:

- title
- status or momentum
- confidence, simplified as high/medium/low
- one-sentence interpretation
- next checkpoint
- optional "Ask Agent" action

### Hidden/Internal Tools

The following should move out of the default view:

- taxonomy tables
- story map maintenance
- family suggestions
- audit details
- raw evidence count tables
- state edit forms
- relation graph internals

They can remain available in an advanced/debug view or only through Agent actions.

### Agent Integration

Market State is default context for the Agent.

Example prompts:

- "What does the current market state mean for my portfolio?"
- "Which driver has strengthened this week?"
- "Which of my thesis notes conflicts with the market state?"
- "What should I check before changing exposure?"

## Phase 4: Automation

### Goal

Add local automation so the user does not manually trigger RSS collection, indexing, Market Memory cleanup, and briefing generation every day.

### Feature Location

Add a new feature module:

```text
features/automation/
  README.md
  service.py
  scheduler.py
  schema.py
```

`app.py` should expose only thin API endpoints and startup hooks.

Settings storage:

```text
data/automation-settings.json
data/automation-runs.json
```

Use JSON because this is a small singleton user setting and run summary. If run history becomes large or query-heavy, migrate run logs into `market-memory.sqlite3` or a dedicated table later.

### Automation Types

Initial automations:

| Automation | Purpose |
| --- | --- |
| RSS collection | fetch enabled RSS feeds and refresh RSS cache |
| Index refresh | run incremental index after collection |
| Market Memory update | build digest from RSS/evidence and update medium-term state |
| Briefing generation | generate selected market briefing at configured time |

### Scheduling Model

Support simple schedules first:

- enabled/disabled
- interval minutes or daily time
- market scope for briefing: `us`, `kr`, `both`
- briefing type: `default`, `market_focused`, `concise`
- generation mode: `rules`, `llm_cli`
- quality mode
- run missed jobs on startup: yes/no

### Dependency Order

Briefing automation should optionally run prerequisites:

```text
Briefing scheduled run
  1. RSS collection if stale or configured
  2. incremental index refresh
  3. Market Memory digest/update
  4. briefing generation
```

This should prevent "automated briefing from stale inputs" as the default outcome.

### Local Runtime Constraints

Automation is local and should clearly communicate these limits:

- It runs only while Folio OS server is running.
- It may miss runs when the PC is asleep or shut down.
- Missed jobs can be skipped or caught up based on setting.
- Only one instance of each automation should run at a time.
- Long jobs should use existing job status infrastructure.
- A failed automation should not crash the server.

### Safety

- No destructive cleanup by default.
- No paid content bypass.
- No evidence promotion from user notes.
- No automatic overwrite of Canonical reports without the same save semantics already used by the feature.
- If an Agent-authored result fails validation, do not write it back.

## Phase 5: Native Investment Notes

### Goal

Move investment notes from an Obsidian-first workflow to a Folio-first workflow.

This preserves the earlier roadmap idea of "Phase 3: Native Investment Notes" as a later phase in the expanded agentic roadmap. It is deferred behind Agent, Market State, and Automation work, but it remains a required destination.

Obsidian remains supported for users who want it, but Folio OS should work fully without Obsidian.

### Target Model

Native notes should be stored and indexed as user hypothesis, not evidence.

Possible note types:

- company thesis
- market memo
- topic review
- portfolio decision note
- checkpoint note

Storage should remain compatible with the existing knowledge graph direction:

```text
market-memory.sqlite3
  - native_note_index
  - thesis links
  - regime links
  - checkpoints
```

Obsidian importer can become one source of user notes rather than the primary note system.

### Agent Role

The Agent helps the user:

- structure a thesis
- identify assumptions
- find counter-evidence
- create future checkpoints
- connect notes to market drivers and reports

The Agent must continue to treat notes as hypothesis.

## Phase 6: Gradual React Shell

### Goal

Move frontend complexity out of the large vanilla `public/app.js` surface without rewriting the whole app at once.

This preserves the earlier roadmap idea of "Phase 4: React Shell gradual adoption" as a later phase in the expanded agentic roadmap. It should not block the Agent or Market Memory product shift.

### Migration Strategy

Start with new high-value surfaces rather than a full rewrite:

```text
web/
  Agent Dock
  Market State Dashboard v2
  Native Notes
  Automation Settings
```

Keep FastAPI as the backend and static `public/` as the existing app shell during transition.

Possible stages:

1. Add a Node/Vite toolchain for new React screens.
2. Mount React widgets into existing static pages.
3. Move Agent Dock and Market State Dashboard first.
4. Gradually port report readers and heavy interactive screens.
5. Retire duplicate vanilla UI only after parity.

This reduces migration risk and avoids delaying the Agent/Market Memory product shift.

## Suggested Implementation Order

1. Global Agent Layer design and API contract.
2. Agent Dock UI with Companion Mode and current context.
3. In-modal Ask Agent drawer for briefing/report readers.
4. Market Memory RSS digest pipeline.
5. Market State Dashboard v2.
6. Automation settings and local scheduler.
7. Task Mode writeback flows for company analysis and topic reports.
8. Native Investment Notes.
9. React shell migration for new surfaces.

## Open Decisions

1. Whether the first Agent Dock implementation should use existing vanilla frontend or start inside a new React island.
   Recommended default: use the existing frontend for v1 unless the React shell work is explicitly started first.
2. Whether automation run history should remain JSON or start in SQLite immediately.
   Recommended default: use JSON for settings and short run summaries, then migrate only if run history becomes query-heavy.
3. Whether Market State Dashboard v2 should replace the current Market Memory tab entirely or hide advanced tools behind a secondary advanced view.
   Recommended default: replace the default view with Market State Dashboard v2 and move current maintenance tools behind an advanced/debug entry.
4. Whether RSS digest generation should be rules-first with optional LLM refinement, or LLM-first with rules fallback.
   Recommended default: rules-first clustering and promotion, with optional LLM refinement for summaries and state phrasing.
5. Whether automated briefing generation should default to `rules`, or the user's last selected generation mode.
   Recommended default: use the user's saved generation mode, falling back to `rules` if no mode is configured.

## Acceptance Criteria

The roadmap succeeds when:

1. The user can talk to the Agent from any screen.
2. The Agent understands the current surface and report context without repeated manual explanation.
3. Report modifications require explicit approval before writeback.
4. Market Memory can update from RSS/evidence without requiring a briefing first.
5. The Market Memory screen presents one clear medium-term market state and a small set of drivers.
6. RSS collection, Market Memory update, and briefing generation can run on a local schedule.
7. User notes can eventually exist inside Folio OS without Obsidian.
8. React migration remains incremental and does not block core product improvements.
