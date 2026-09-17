# TASK-051 — Difficult-Source Adapter

## Objective and Scope
Introduce Amazon or an equivalent difficult source only after the source abstraction, observability, retry behavior, and retailer integration gate are established.

Requirements:
- Select/document the difficult source if the repository has not already fixed one.
- Implement it behind the existing `SourceAdapterProtocol`; no source-specific structures may leak downstream.
- Prefer the least complex reliable collection mechanism that demonstrates the intended difficult-source behavior.
- Preserve stable source/external identity and canonical event compatibility.
- Externalize headers, endpoints, timeouts, credentials/tokens if any, and other configuration.
- Treat blocking, rate limiting, unavailable pages, structural changes, and partial parseability as explicit outcomes.
- Never add stealth/evasion behavior whose purpose is to defeat access controls. Respect the source's access constraints.
- CI must use deterministic fixtures/mocks and must not require live access.
- Do not redesign downstream Kafka/processor/lake/warehouse schemas for this source.
- Keep detailed backoff policy, degradation classification, and freshness scenarios for TASK-052–054.

Tests:
- adapter protocol compliance
- representative response/page mapping
- unavailable/blocked response
- malformed/partial source content
- timeout/network failure
- canonical compatibility
- stable source identity
- deterministic mocked execution

Acceptance:
The difficult source can be represented behind the same adapter boundary and can fail independently without requiring downstream architecture changes.

## Required Context Before Coding
Read the current repository versions of `ai/PROJECT.md`, applicable ADRs, `ai/SPECIFICATION.md`, `ai/ROADMAP.md`, `ai/AGENTS.md`, `ai/AGENT_WORKFLOW.md`, and relevant completed source-adapter tasks. Higher-authority repository documents win on conflicts.

## Engineering Rules
- Implement this task only.
- Use typed Python, explicit interfaces, deterministic tests, and existing repository conventions.
- Preserve source-adapter isolation and canonical downstream contracts.
- Preserve documented at-least-once/idempotent semantics; never claim exactly-once without proof.
- Never commit/log credentials or secrets.
- Do not weaken/delete tests to make CI green.
- Run relevant unit/integration tests plus configured lint/format/type checks after final edits.
- Inspect the final Git diff and verify acceptance criteria.
- Escalate if implementation requires a fundamental architecture/schema change or broad unrelated refactoring.

## Agent Instructions
Implement TASK-051 only. Stop when its acceptance criteria and final verification are satisfied.
