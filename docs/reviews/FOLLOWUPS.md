# Deferred review recommendations

Track accepted non-blocking work here instead of extending the current task.
Critical/High findings require resolution before acceptance; any rejected finding
needs a documented rationale. The owner decides disputed findings.

| Task / reviewed commit | Finding / report link | Reason deferred | Revisit trigger | Status |
| --- | --- | --- | --- | --- |
| TASK-009 / 463012b | M1: KafkaConsumerSettings.__init__ passthrough with type ignore | Internal implementation detail; no runtime impact | When adding new config validation or mypy reports unused ignore | Open |
| TASK-009 / 463012b | M2: Missing settings validation and allow.auto.create.topics=false | Broker-level enforcement per ADR-001; not a runtime risk for local scope | TASK-012 production hardening | Open |
| TASK-009 / 463012b | Min1: Broad except Exception in poll() | Current behavior correctly surfaces all errors via DeserializationError list | If bug discovered where legitimate errors are swallowed | Open |
| TASK-009 / 463012b | Min2: Signal handler registration as library side effect | Acceptable for standalone service pattern; already has try/except fallback | If service needs custom signal handling or runs consumer in non-main thread | Open |
| TASK-009 / 463012b | Min3: Documentation/config gaps (.env.example, README, port discrepancy) | Cosmetic polish; doesn't affect functionality | When onboarding new developers or creating official docs | Open |
| TASK-009 / 463012b | Min4: Stale comment in test_commit_after_successful_processing | Comment-only issue with zero runtime impact | Next time this test file is modified | Open |
