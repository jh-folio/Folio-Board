# CLI Briefing Shared Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make CLI-authored briefings satisfy the same active prompt, evidence context, section structure, summary/prose format, and visual-placement contract defined by the shared report contract.

**Architecture:** Add a focused `briefing_contract.py` module shared by context-pack creation, bridge validation, and writeback defense. The bridge validates Markdown before writeback, retries the same CLI adapter once with explicit violations, and refuses to overwrite the saved report if the retry still fails.

**Tech Stack:** Python 3, pytest, existing Agent Mode context packs and subprocess bridge.

---

### Task 1: Define the shared briefing output contract

**Files:**
- Create: `features/agent_mode/briefing_contract.py`
- Test: `features/agent_mode/tests/test_briefing_contract.py`

- [x] **Step 1: Write failing scope-contract tests**

Test that `briefing_output_contract("both")` requires the full US and KR `0~6 + 오늘의 결론 + Source & Data Notes` headings, 10,000 characters, 14 one-line conclusions, 36 middle-dot bullets, and one retry. Test single-market thresholds at half those values.

- [x] **Step 2: Run the contract tests and confirm import failure**

Run: `py -3 -m pytest features/agent_mode/tests/test_briefing_contract.py -q`

Expected: FAIL because `briefing_contract.py` does not exist.

- [x] **Step 3: Implement the contract builder**

Create constants for US and KR stable heading fragments and return this public shape:

```python
{
    "format": "markdown",
    "requiredSections": [...],
    "minimumCharacters": 10000,
    "minimumOneLineConclusions": 14,
    "minimumMiddleDotBullets": 36,
    "retryOnViolation": 1,
}
```

- [x] **Step 4: Run tests and commit the contract**

Run: `py -3 -m pytest features/agent_mode/tests/test_briefing_contract.py -q`

Expected: PASS.

### Task 2: Validate Markdown quality and structure

**Files:**
- Modify: `features/agent_mode/briefing_contract.py`
- Test: `features/agent_mode/tests/test_briefing_contract.py`

- [x] **Step 1: Write failing validation tests**

Cover a five-heading abbreviated CLI output, a complete output assembled from every required heading and required marker counts, missing `한 줄 결론`, missing middle-dot bullets, and insufficient length. Assert `briefing_contract_violations()` returns human-readable violations.

- [x] **Step 2: Run tests and confirm failures**

Run: `py -3 -m pytest features/agent_mode/tests/test_briefing_contract.py -q`

- [x] **Step 3: Implement heading-only validation**

Extract ATX Markdown headings with `^#{1,6}\s+(.+)$`; search required section fragments only inside headings. Count `**한 줄 결론:**`, lines beginning with `·`, and total stripped characters. Return a list of violations and never mutate Markdown.

- [x] **Step 4: Run tests and commit validation**

Run: `py -3 -m pytest features/agent_mode/tests/test_briefing_contract.py -q`

Expected: PASS.

### Task 3: Use the shared contract in briefing context packs and writeback

**Files:**
- Modify: `features/agent_mode/service.py`
- Modify: `features/agent_mode/tests/test_writeback.py`
- Modify: `features/agent_mode/tests/test_extended_tasks.py`

- [x] **Step 1: Write failing pack and writeback tests**

Assert prepared briefing packs use `briefing_output_contract(scope)`, preserve the same active prompt/context inputs, and reject malformed Markdown before `write_json`. Update existing writeback fixtures to generate contract-valid Markdown through a test helper.

- [x] **Step 2: Run focused tests and confirm failure**

Run: `py -3 -m pytest features/agent_mode/tests/test_writeback.py features/agent_mode/tests/test_extended_tasks.py -q`

- [x] **Step 3: Wire contract creation and defensive validation**

Replace the hand-written three-section `output_contract` in `prepare_briefing_pack()` with `briefing_output_contract(market_scope)`. At the start of `write_briefing_from_markdown()`, call the validator and raise `ValueError` before creating directories or writing files if violations remain.

- [x] **Step 4: Run tests and commit service integration**

Run: `py -3 -m pytest features/agent_mode/tests/test_writeback.py features/agent_mode/tests/test_extended_tasks.py -q`

Expected: PASS.

### Task 4: Retry one malformed CLI response before writeback

**Files:**
- Modify: `features/agent_mode/bridge.py`
- Modify: `features/agent_mode/tests/test_bridge.py`

- [x] **Step 1: Write failing retry tests**

Introduce a patched `_invoke_agent_cli()` seam. Assert malformed-first/valid-second invokes CLI twice and writeback once; malformed twice raises and never calls writeback; valid first invokes once. Assert the correction prompt lists contract violations and instructs regeneration from the same pack without shortening.

- [x] **Step 2: Run focused tests and confirm failure**

Run: `py -3 -m pytest features/agent_mode/tests/test_bridge.py -q`

- [x] **Step 3: Extract process invocation without behavior changes**

Move command construction, `Popen`, job registration, timeout, return-code handling, output stripping, and max-size enforcement into `_invoke_agent_cli(selected, prompt, timeout, job_id)`.

- [x] **Step 4: Add Markdown validation and one corrective retry**

After the first Markdown output, call `briefing_contract_violations()` only for `taskType=briefing`. If invalid and retry budget is one, report progress, build a correction prompt containing each violation and every required heading, then invoke the same adapter once more. Validate again before writeback.

- [x] **Step 5: Run tests and commit bridge retry**

Run: `py -3 -m pytest features/agent_mode/tests/test_bridge.py -q`

Expected: PASS.

### Task 5: Regression verification and documentation

**Files:**
- Modify: `features/agent_mode/README.md`
- Modify: `docs/superpowers/specs/2026-06-21-cli-briefing-contract-design.md`

- [x] **Step 1: Document shared report contract and retry behavior**

State that CLI generation uses the shared active prompt/context/evidence, malformed CLI Markdown is retried once, and invalid retry output is not saved.

- [x] **Step 2: Run all verification commands**

Run:

```powershell
py -3 -m pytest -q
py -3 -m py_compile features\agent_mode\briefing_contract.py features\agent_mode\service.py features\agent_mode\bridge.py
node --test public\*.test.js
node --check public\app.js
git diff --check
```

Expected: every command exits 0.

- [x] **Step 3: Commit final docs and verification state**

Commit only Agent Mode code/tests/docs; do not stage `data/`, `research-inbox/`, `.env`, or generated context packs.
