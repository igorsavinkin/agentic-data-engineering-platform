# TASK-041 Review Report

## 1. Review Header

- **Task ID:** TASK-041
- **Review Date:** 2026-09-16
- **Reviewer:** Qwen Code (non-interactive review via qwen review run, no code modified)
- **Reviewed Change Set:** main...feature/TASK-041 (commit 8a81a4d)
- **Scope:** eBay Browse API adapter implementation with typed models, OAuth2 authentication, retry logic, and canonical event mapping
- **Verdict:** CHANGES REQUIRED

## 5. Findings

### H1: Missing tenacity dependency declaration [HIGH]
**Severity:** High
**File:** libs/adapters/ebay/client.py:9, requirements files
**Problem:** tenacity is imported at line 9 but not declared in requirements.txt, requirements-dev.txt, or pyproject.toml.
**Impact:** Clean installs and CI builds will fail with ModuleNotFoundError.
**Recommendation:** Add tenacity to the project's dependency declarations.

### H2: mypy strict mode violations [HIGH]
**Severity:** High
**File:** libs/adapters/ebay/client.py:217, client.py:268
**Problem:** With strict mypy settings, two lines fail type checking.
**Impact:** Blocks Definition-of-Done gate which requires mypy to pass.
**Recommendation:** Fix type annotations to satisfy strict mypy mode.

### H3: Model strictness incompatible with real eBay API [HIGH]
**Severity:** High
**File:** libs/adapters/ebay/models.py (all models)
**Problem:** All eBay models use ConfigDict(extra="forbid"), but the real eBay Browse API returns far more fields than modeled.
**Impact:** When connected to the real eBay API, parsing will fail with ValidationError for unmodeled fields.
**Recommendation:** Change all eBay models to use extra="ignore" like BestBuyProduct.

### H4: Basic auth without base64 encoding [HIGH]
**Severity:** High
**File:** libs/adapters/ebay/client.py:92
**Problem:** _authenticate() constructs Basic auth without base64 encoding. RFC 6749 requires base64 encoding.
**Impact:** Authentication will fail against the real eBay API.
**Recommendation:** Use base64.b64encode for proper Basic auth encoding per RFC 7617.

## 7. Verdict

**CHANGES REQUIRED**

Four HIGH severity findings must be addressed before acceptance:
1. H1: Missing tenacity dependency will break CI/clean installs
2. H2: mypy strict mode violations block Definition-of-Done
3. H3: extra="forbid" models will fail against real eBay API
4. H4: Basic auth without base64 encoding violates RFC 6749

**Reviewed HEAD:** 8a81a4d
