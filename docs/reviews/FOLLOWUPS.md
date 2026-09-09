# Deferred review recommendations

Track accepted non-blocking work here instead of extending the current task.
Critical/High findings require resolution before acceptance; any rejected finding
needs a documented rationale. The owner decides disputed findings.

| Task / reviewed commit | Finding / report link | Reason deferred | Revisit trigger | Status |
| --- | --- | --- | --- | --- |
| TASK-009 / 463012b | M1: KafkaConsumerSettings.__init__ passthrough with type ignore | Internal implementation detail; no runtime impact | When adding new config validation or mypy reports unused ignore | Resolved in TASK-010: inherited settings initializer |
| TASK-009 / 463012b | M2: Missing settings validation and allow.auto.create.topics=false | Broker-level enforcement per ADR-001; not a runtime risk for local scope | TASK-012 production hardening | Partially resolved in TASK-010: client auto-creation disabled; settings validators remain open |
| TASK-009 / 463012b | Min1: Broad except Exception in poll() | Current behavior correctly surfaces all errors via DeserializationError list | If bug discovered where legitimate errors are swallowed | Resolved in TASK-010: explicit validation/decode exception types |
| TASK-009 / 463012b | Min2: Signal handler registration as library side effect | Acceptable for standalone service pattern; already has try/except fallback | If service needs custom signal handling or runs consumer in non-main thread | Open |
| TASK-009 / 463012b | Min3: Documentation/config gaps (.env.example, README, port discrepancy) | Cosmetic polish; doesn't affect functionality | When onboarding new developers or creating official docs | Open |
| TASK-009 / 463012b | Min4: Stale comment in test_commit_after_successful_processing | Comment-only issue with zero runtime impact | Next time this test file is modified | Resolved in TASK-010 |
| TASK-009 / dc54cc4 | Min5: Test module mutates global environment at import | Cosmetic; doesn't affect test outcomes for current scope | When refactoring test isolation or adding new consumer tests | Resolved in TASK-010: scoped environment fixture |
| TASK-009 / d35c04c | M3: Required restart/duplicate tests are mock tautologies; malformed-offset skip path untested | Real-broker integration deferred to TASK-012 per roadmap; unit-test coverage sufficient for local scope | TASK-012 production hardening with real Kafka broker | Open |
| TASK-009 / d35c04c | Min5: Stale review artifact committed (prior review against non-HEAD commit) | Process/hygiene issue; will be replaced by current report | Next review cycle when committing review artifacts | Resolved by this report |
