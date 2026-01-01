# Auernyx Governance Roadmap (v1)

## Invariants

- Explicit governance boundaries.
- Repo-wide QA tooling is operational.

**Invariant:** If any future change weakens these guardrails, it is a regression.

---

## Phase 1 — Repo Awareness

**Goal:** Auernyx understands where it is before acting.

### Capabilities

- Detect SQUAD repo structure.
- Identify presence of:
  - Clerk
  - Schemas
  - QA tooling
- Refuse actions if repo is not recognized as SQUAD.

### Success Criteria

- Agent can answer “What repo am I in?” deterministically.
- Agent fails safely outside governed context.

---

## Phase 2 — Artifact Classification

**Goal:** Auernyx knows what it is touching.

### Capabilities

- Classify files into:
  - Case artifacts
  - Schemas
  - Agents
  - Tools
  - Docs
- Apply different rules per category.
- Warn on boundary crossings.

### Success Criteria

- No “free edits” on governed artifacts.
- Clear warnings when edits cross categories.

---

## Phase 3 — Validation & QA Integration

**Goal:** Auernyx enforces correctness without inventing fixes.

### Capabilities

- Explain JSON parse and schema failures.
- Reference governing schema explicitly.
- Orchestrate repo QA runs.
- Explain QA failures in plain language.

### Explicit Non-Behavior

- No auto-fixing files to make checks pass.
- No guessing missing values.

### Success Criteria

- QA failures are understandable, not mysterious.
- Human remains the decision-maker.

---

## Phase 4 — Case Review Modes

**Goal:** Truth review, not authorship.

Reference examples (inputs + generated outputs):
- `AGENTS/CORE/BATTLEBUDDY/example_input.intake_review.contract.v1.json`
- `AGENTS/CORE/BATTLEBUDDY/example_output.intake_review.contract.v1.json`
- `AGENTS/CORE/BATTLEBUDDY/example_input.strategy_review.contract.v1.json`
- `AGENTS/CORE/BATTLEBUDDY/example_output.strategy_review.contract.v1.json`

### Intake Review Mode

Identify:

- Known facts
- Unknowns
- Required evidence

Flag contradictions and assumptions.

### Strategy Review Mode

- Verify alignment with intake.
- Flag invented programs or assumed eligibility.
- Validate blocking vs non-blocking steps.

### Success Criteria

- Agent never proposes programs.
- Agent never claims eligibility.
- Output is review-oriented, not prescriptive.

---

## Phase 5 — Change Discipline (GitHub-Like)

**Goal:** Prevent silent mutation of truth.

### Capabilities

- Summarize proposed edits before write.
- Describe diffs in plain English.
- Require explicit confirmation for governed writes.
- Maintain a human-readable change explanation.

### Success Criteria

- No “I don’t remember changing that” moments.
- Every change has intent attached.

---

## Phase 6 — Self-Explanation & Governance Literacy

**Goal:** Auernyx can justify itself.

### Capabilities

- Explain refusals.
- Cite governance rules.
- Point to documentation.

### Success Criteria

- If Auernyx can’t explain why, it doesn’t act.

---

## Secondary Addendum — Training While Building

### Intent

Auernyx is being trained in parallel with its construction. This is intentional and acknowledged.

The agent is not expected to be “complete” at any phase. Instead, it is expected to:

- Learn boundaries by encountering them
- Improve explanations over time
- Become more conservative, not more clever

### Training Principles

#### 1. Behavior over cleverness

Auernyx is rewarded for:

- Refusing unsafe actions
- Asking for clarification
- Saying “I don’t know”

It is penalized for:

- Filling gaps
- Being helpful at the cost of accuracy
- Optimizing prematurely

#### 2. Fun is allowed, hallucination is not

Exploration, iteration, and discovery are part of the process. Inventing facts, programs, or authority is not.

The agent may:

- Surface patterns
- Ask structural questions
- Highlight risks

The agent may not:

- Make decisions for humans
- Pretend uncertainty doesn’t exist

#### 3. Training data is lived work

Training comes from:

- Real schema failures
- Real QA results
- Real governance conflicts
- Real human corrections

Not synthetic “example” cases.

---

## Completion Definition (for now)

Auernyx is “good enough” when:

- It reliably stops bad actions
- It explains its reasoning clearly
- It makes the human’s job easier without replacing judgment

Anything beyond that is optional polish.
