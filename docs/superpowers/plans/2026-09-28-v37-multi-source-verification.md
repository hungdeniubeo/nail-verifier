# Nail Verifier v3.7 Multi-Source Verification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace v3.6 exact allowlist actions with an evidence-first, per-business multi-source verification pipeline where only business-specific VERIFIED evidence may Auto KEEP or Auto REMOVE.

**Architecture:** Add a CSV-backed evidence registry, normalize registry/live evidence into common signals, resolve those signals through a deterministic consensus engine, then let policy act only on the final verification status. Existing NailMap heuristics remain for prioritization and audit but no longer prove a business is nail or not-nail. Dataset-level duplicate and identity-collision guards stay last and can override any automatic action.

**Tech Stack:** Python 3.11, pandas 2.2+, pytest 8+, existing requests/BeautifulSoup/rapidfuzz stack, Streamlit 1.40+.

**Spec:** `docs/superpowers/specs/2026-09-28-multi-source-verification-design.md`

## Global Constraints

- Precision first: unsupported KEEP/REMOVE must become REVIEW.
- `VERIFIED_NAIL`, `VERIFIED_NOT_NAIL`, `LIKELY_NAIL`, `LIKELY_NOT_NAIL`, `CONFLICTING_EVIDENCE`, and `UNKNOWN` are the only evidence-level final statuses.
- Auto REMOVE requires `Verification_Status = VERIFIED_NOT_NAIL`.
- Auto KEEP in the v3.7 evidence-first profile requires `Verification_Status = VERIFIED_NAIL`.
- A Tier D NailMap/name-rule signal can never create VERIFIED status.
- One Tier B/C source alone can never create VERIFIED status.
- VERIFIED requires either one exact Tier A directional source, or two independent agreeing Tier B/C directional sources.
- Beauty/hair/spa absence-of-nail evidence is not sufficient for VERIFIED_NOT_NAIL.
- Strong contradictory NAIL and NOT_NAIL evidence produces `CONFLICTING_EVIDENCE` and REVIEW.
- Identity collision runs after evidence policy and overrides KEEP/REMOVE to REVIEW.
- Bulk mode continues to disable public Nominatim.
- No new runtime dependency is required for v3.7.

## Review Focus

1. **Duplicate evidence from the same provider/domain:** two rows from one source must count as one independent source and must not satisfy the two-source gate. Covered in Task 3 consensus tests.
2. **Registry changes with an existing SQLite verification cache:** changing evidence must invalidate old verification results. Covered in Task 6 engine/cache tests.
3. **Missing or differently formatted phone numbers:** exact name + full address + city/state/ZIP may still match when one phone is missing, but two non-empty conflicting phones must reject the registry row. Covered in Task 1 registry tests.
4. **Strong evidence conflict for one exact identity:** NAIL + NOT_NAIL directional evidence must never auto-act. Covered in Task 3 and Task 6 tests.
5. **Malformed shifted address plus dataset collision:** the existing Hang Nails address recovery and same-phone/base-address collision logic must survive the new pipeline. Covered in Task 6 regression tests.

---

### Task 1: Evidence registry loader and exact identity matching

**Files:**
- Create: `nailverifier_v3/evidence_registry.py`
- Create: `tests/test_v37_evidence_registry.py`

**Interfaces:**
- Produces `RegistryEvidence` dataclass with registry columns plus normalized/source-key helpers.
- Produces `EvidenceRegistry(path: str = "benchmarks/verified_business_evidence.csv")`.
- Produces `EvidenceRegistry.match(record: BusinessRecord) -> list[RegistryEvidence]`.
- Produces read-only `EvidenceRegistry.version: str`, a SHA-256 digest derived from registry bytes for cache invalidation.

- [ ] **Step 1: Write failing registry tests**

Add tests asserting:

```python
assert registry.match(exact_record)[0].source_url == expected_url
assert registry.match(same_name_wrong_address) == []
assert registry.match(same_identity_wrong_state) == []
assert registry.match(nonempty_conflicting_phone) == []
assert len(registry.match(record_with_missing_phone_but_exact_full_address)) == 1
```

Also assert malformed/missing required columns and invalid `Source_Tier` / `Evidence_Direction` raise `ValueError` rather than silently loading bad evidence.

- [ ] **Step 2: Run registry tests and verify RED**

Run: `python -m pytest tests/test_v37_evidence_registry.py -q`

Expected: FAIL because `evidence_registry.py` does not exist.

- [ ] **Step 3: Implement the registry**

Implement exact normalized identity matching using existing `normalize_name`, `normalize_street`, `normalize_text`, `normalize_zip`, and `normalize_phone`.

Matching rule is fixed:

```text
state + company + full street + city + ZIP must match exactly after normalization.
If both phones are non-empty, phones must match.
If either phone is empty, the exact five-field location/name identity may still match.
```

`source_key` must prefer normalized URL hostname and fall back to normalized `Source_Name`, so duplicate rows from one provider do not look independent later.

- [ ] **Step 4: Run registry tests and verify GREEN**

Run: `python -m pytest tests/test_v37_evidence_registry.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add nailverifier_v3/evidence_registry.py tests/test_v37_evidence_registry.py
git commit -m "feat(v3.7): add exact evidence registry matching"
```

### Task 2: Normalize registry and live evidence into common signals

**Files:**
- Create: `nailverifier_v3/evidence_classifier.py`
- Create: `tests/test_v37_evidence_classifier.py`
- Read/consume: `nailverifier_v3/models.py`, `nailverifier_v3/features.py`

**Interfaces:**
- Produces `EvidenceSignal` dataclass with: `source_name`, `source_key`, `source_tier`, `source_url`, `direction`, `identity_verified`, `category`, `service_evidence`, `existence_status`, `checked_at`, `notes`.
- Produces `classify_registry_evidence(rows: list[RegistryEvidence]) -> list[EvidenceSignal]`.
- Produces `classify_live_evidence(items: list[Evidence]) -> list[EvidenceSignal]`.
- Produces `heuristic_signal(local: LocalAssessment, record: BusinessRecord) -> EvidenceSignal | None` with Tier D only.

- [ ] **Step 1: Write failing classifier tests**

Pin these mappings:

```text
registry Tier A + NAIL -> Tier A NAIL directional signal
registry Tier A + NOT_NAIL -> Tier A NOT_NAIL directional signal
SD_COSMETOLOGY nail-specific current license -> Tier A NAIL
SD_COSMETOLOGY broad beauty/apprentice license -> AMBIGUOUS/identity signal, not NAIL
OPENSTREETMAP directional evidence -> Tier C
R_NAIL_EXPLICIT_STRONG heuristic -> Tier D NAIL hint only
R_NON_NAIL_CATEGORY_STRONG heuristic -> Tier D NOT_NAIL hint only
```

- [ ] **Step 2: Run classifier tests and verify RED**

Run: `python -m pytest tests/test_v37_evidence_classifier.py -q`

Expected: FAIL because classifier interfaces do not exist.

- [ ] **Step 3: Implement classifier functions**

Do not let this module decide VERIFIED status or Auto_Action. Preserve explicit service/category text and source URLs so consensus/output can be audited.

- [ ] **Step 4: Run classifier tests and verify GREEN**

Run: `python -m pytest tests/test_v37_evidence_classifier.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add nailverifier_v3/evidence_classifier.py tests/test_v37_evidence_classifier.py
git commit -m "feat(v3.7): normalize verification evidence signals"
```

### Task 3: Deterministic multi-source consensus

**Files:**
- Create: `nailverifier_v3/consensus.py`
- Create: `tests/test_v37_consensus.py`

**Interfaces:**
- Produces `ConsensusResult.to_dict() -> dict[str, object]`.
- Produces `resolve_consensus(signals: list[EvidenceSignal]) -> ConsensusResult`.
- `ConsensusResult` exports exactly: `Verification_Status`, `Identity_Status`, `Existence_Status`, `Nail_Service_Status`, `Evidence_Source_Count`, `Strong_Evidence_Count`, `Evidence_Agrees`, `Evidence_Conflicts`, `Primary_Source`, `Primary_Source_Tier`, `Primary_Source_URL`, `Verification_Evidence`, `Verification_Reason`, `Verified_At`.

- [ ] **Step 1: Write failing consensus tests**

Tests must assert:

```text
one Tier A explicit NAIL -> VERIFIED_NAIL
one Tier A affirmative non-beauty NOT_NAIL -> VERIFIED_NOT_NAIL
one Tier C NAIL -> LIKELY_NAIL
one Tier C NOT_NAIL -> LIKELY_NOT_NAIL
two independent B/C NAIL -> VERIFIED_NAIL
two independent B/C NOT_NAIL -> VERIFIED_NOT_NAIL
two rows from same source_key -> still one independent source, not VERIFIED
strong NAIL + strong NOT_NAIL -> CONFLICTING_EVIDENCE
beauty/hair identity source with no nail claim -> UNKNOWN, not VERIFIED_NOT_NAIL
Tier D only -> LIKELY_* at most, never VERIFIED
```

Use `Evidence_Source_Count` as the count of unique `source_key` values. `Strong_Evidence_Count` counts unique identity-verified Tier A/B/C directional sources. `Evidence_Agrees` is `YES` only when all directional strong sources point the same way; `Evidence_Conflicts` is the number of opposing strong directions detected.

- [ ] **Step 2: Run consensus tests and verify RED**

Run: `python -m pytest tests/test_v37_consensus.py -q`

Expected: FAIL because consensus does not exist.

- [ ] **Step 3: Implement deterministic consensus**

Primary source ordering is fixed: Tier A before B before C before D; within a tier prefer explicit directional service/category evidence; then prefer the newest `checked_at` when available.

`CONFLICTING_EVIDENCE` takes precedence over VERIFIED/LIKELY states.

- [ ] **Step 4: Run consensus tests and verify GREEN**

Run: `python -m pytest tests/test_v37_consensus.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add nailverifier_v3/consensus.py tests/test_v37_consensus.py
git commit -m "feat(v3.7): add multi-source evidence consensus"
```

### Task 4: Evidence-first action policy and remove business identities from policy code

**Files:**
- Modify: `nailverifier_v3/policy.py`
- Create: `tests/test_v37_evidence_policy.py`
- Modify: `tests/test_v33_calibrated_policy.py`
- Modify: `tests/test_v35_verified_identity_allowlist.py`
- Modify: `tests/test_v36_verified_remove_allowlist.py`

**Interfaces:**
- Produces `apply_evidence_policy(verification_status: str) -> dict[str, str]`.
- Engine-facing outputs:
  - `VERIFIED_NAIL` -> `Auto_Action=KEEP`, `Policy_Status=EVIDENCE_VERIFIED_NAIL`
  - `VERIFIED_NOT_NAIL` -> `Auto_Action=REMOVE`, `Policy_Status=EVIDENCE_VERIFIED_NOT_NAIL`
  - every other status -> `Auto_Action=REVIEW`, `Policy_Status=EVIDENCE_REVIEW`

- [ ] **Step 1: Write failing evidence-policy tests**

Assert VERIFIED states auto-act and LIKELY/UNKNOWN/CONFLICTING do not.

Update legacy policy tests so calibrated rules remain testable as heuristic/calibration metadata but are no longer expected to drive v3.7 engine Auto_Action.

- [ ] **Step 2: Run policy tests and verify RED**

Run: `python -m pytest tests/test_v37_evidence_policy.py tests/test_v33_calibrated_policy.py tests/test_v35_verified_identity_allowlist.py tests/test_v36_verified_remove_allowlist.py -q`

Expected: FAIL on old allowlist/auto-action expectations.

- [ ] **Step 3: Implement evidence-first policy and remove hard-coded identity allowlists**

Delete `VERIFIED_IDENTITY_ALLOWLIST`, `VERIFIED_NOT_NAIL_ALLOWLIST`, identity-key helpers, and `apply_verified_identity_policy` from `policy.py`. Business-specific truth belongs only in the registry.

Keep statistical calibration constants/functions only if still used by benchmark tooling; they must not be called by the v3.7 evidence-first engine path.

- [ ] **Step 4: Run policy tests and verify GREEN**

Run the same command. Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add nailverifier_v3/policy.py tests/test_v37_evidence_policy.py tests/test_v33_calibrated_policy.py tests/test_v35_verified_identity_allowlist.py tests/test_v36_verified_remove_allowlist.py
git commit -m "refactor(v3.7): make verified evidence the action gate"
```

### Task 5: Migrate existing researched evidence into the registry

**Files:**
- Create: `scripts/build_verified_business_evidence.py`
- Create: `benchmarks/verified_business_evidence.csv`
- Create: `benchmarks/evidence_migration_rejections.csv`
- Create: `tests/test_v37_evidence_migration.py`
- Read: `benchmarks/sd_rule_calibration_v33.csv`
- Read: `benchmarks/sd_rule_calibration_v34_addendum.csv`
- Read: `benchmarks/sd_address_strong_v35.csv`

**Interfaces:**
- Produces `build_registry(input_paths: list[str]) -> tuple[pd.DataFrame, pd.DataFrame]`, returning accepted evidence and rejected/insufficient rows.
- CLI writes deterministic CSVs in the two paths above.

- [ ] **Step 1: Write failing migration tests**

Tests must pin source tiers and conservative downgrades using known records:

```text
official business/booking/store locator domains -> Tier A
BBB / Apple Maps / Chamber / established local directory -> Tier B
BestProsInTown / Loc8NearMe / Birdeye / YellowPages / specialist directories -> Tier C
unknown provider -> Tier C, never guessed as Tier A
UNKNOWN or missing-source calibration row -> rejection file, not directional registry evidence
```

Pin representative rows:

```text
The Nail Haus By Adamari / Zen Nail Studio -> Tier A NAIL
Buche Ace Hardware / official Ace -> Tier A NOT_NAIL
Ruby House Restaurant official site -> Tier A NOT_NAIL
Bowdle Building & Hardware official city directory -> Tier B NOT_NAIL, therefore not VERIFIED from this source alone
Anna's Nails directory-only evidence -> B/C NAIL and therefore not VERIFIED from one source alone
K & E Nail Studio LLC -> rejected/insufficient
```

- [ ] **Step 2: Run migration tests and verify RED**

Run: `python -m pytest tests/test_v37_evidence_migration.py -q`

Expected: FAIL because migration script does not exist.

- [ ] **Step 3: Implement deterministic migration**

For each accepted source, copy exact business identity, original URL, original note, direction, and source-derived checked date. For NAIL rows put the explicit supporting note into `Nail_Service_Evidence`; for NOT_NAIL rows put the affirmative non-beauty category claim into `Observed_Category`/notes. Deduplicate only exact identity + source URL + direction duplicates; never merge different providers.

- [ ] **Step 4: Generate registry artifacts**

Run:

```bash
python scripts/build_verified_business_evidence.py
```

Expected: both registry and rejection CSVs are produced deterministically.

- [ ] **Step 5: Run migration + registry tests and verify GREEN**

Run: `python -m pytest tests/test_v37_evidence_migration.py tests/test_v37_evidence_registry.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add scripts/build_verified_business_evidence.py benchmarks/verified_business_evidence.csv benchmarks/evidence_migration_rejections.csv tests/test_v37_evidence_migration.py
git commit -m "data(v3.7): migrate researched business evidence registry"
```

### Task 6: Integrate registry, classifier, consensus and evidence policy into the engine

**Files:**
- Modify: `nailverifier_v3/engine.py`
- Modify: `nailverifier_v3/__init__.py` only if exports are useful to tests/UI
- Create: `tests/test_v37_engine.py`
- Modify: `tests/test_v341_identity_collision.py`
- Modify: `tests/test_v3_precision.py` as required by new evidence-first semantics

**Interfaces:**
- `VerificationEngine.__init__(..., registry_path: str = "benchmarks/verified_business_evidence.csv")` owns one `EvidenceRegistry`.
- `ENGINE_VERSION = "3.7.0"`.
- Verification cache version includes `registry.version`, e.g. `3.7.0+registry:<digest>+noosm`, so editing evidence cannot reuse stale actions.
- Existing `Decision`, `Candidate_Action`, local-rule and official/OSM audit fields stay present.
- New consensus fields are merged into every successful result.
- `Policy_Profile = "EVIDENCE_FIRST_V1_COLLISION_GUARD"` for the v3.7 path.

- [ ] **Step 1: Write failing engine tests**

Pin the end-to-end behaviors:

```text
Tier A official nail registry/registry source -> Verification_Status VERIFIED_NAIL + Auto KEEP
Tier A official hardware/store/restaurant -> VERIFIED_NOT_NAIL + Auto REMOVE
single Tier B/C old allowlist source -> LIKELY_* + REVIEW (no grandfathering)
strong-name NailMap row with no per-business evidence -> LIKELY_NAIL + REVIEW
unseen strong non-nail name with no evidence -> LIKELY_NOT_NAIL + REVIEW
strong conflict -> CONFLICTING_EVIDENCE + REVIEW
Hy-Vee-style identity collision -> REVIEW even if consensus says VERIFIED_NOT_NAIL
Cobe/Rose-style nail collision -> REVIEW even if evidence says VERIFIED_NAIL
shifted Hang Nails address still exports Normalized_Street = "500 e figzel ct"
changing registry contents changes cache key/version and prevents stale cached Auto_Action
```

- [ ] **Step 2: Run engine/regression tests and verify RED**

Run: `python -m pytest tests/test_v37_engine.py tests/test_v341_identity_collision.py tests/test_v3_precision.py -q`

Expected: FAIL under v3.6 engine behavior.

- [ ] **Step 3: Implement the seven-stage engine flow**

Per record:

```text
normalize/local assessment
-> live official/OSM evidence
-> exact registry matches
-> classify all evidence + Tier D heuristic
-> resolve consensus
-> apply evidence-first policy
-> cache evidence-level result
```

Dataset pass then adds normalized identity/duplicate counts and runs the existing collision override last.

Do not let `decide()`/legacy rule policy overwrite consensus Auto_Action; legacy decision fields may remain for audit until a later cleanup.

- [ ] **Step 4: Make error rows export the new fields safely**

On exceptions, emit `Verification_Status=UNKNOWN`, zero source counts, blank source URL, and `Auto_Action=REVIEW`; never omit required v3.7 columns.

- [ ] **Step 5: Run engine/regression tests and verify GREEN**

Run the same command. Expected: PASS.

- [ ] **Step 6: Run full suite**

Run: `python -m pytest -q`

Expected: zero failures.

- [ ] **Step 7: Commit**

```bash
git add nailverifier_v3/engine.py nailverifier_v3/__init__.py tests/test_v37_engine.py tests/test_v341_identity_collision.py tests/test_v3_precision.py
git commit -m "feat(v3.7): integrate evidence-first verification engine"
```

### Task 7: Update validation sampling for unresolved evidence acquisition

**Files:**
- Modify: `nailverifier_v3/sampling.py`
- Create: `tests/test_v37_sampling.py`

**Interfaces:**
- `make_validation_sample()` keeps existing rule columns but fronts v3.7 verification fields.
- Sampling prioritizes unresolved `R_BEAUTY_AMBIGUOUS`, `UNKNOWN`, conflicting, and LIKELY rows rather than already VERIFIED rows.

- [ ] **Step 1: Write failing sampling tests**

Assert VERIFIED rows are not preferentially sampled when unresolved rows exist, `CONFLICTING_EVIDENCE` is retained, and output includes blank research fields for adding new source URL/notes.

- [ ] **Step 2: Run tests and verify RED**

Run: `python -m pytest tests/test_v37_sampling.py -q`

- [ ] **Step 3: Implement evidence-aware sampling**

Preserve deterministic `random_state`; do not remove Rule_ID stratification entirely because it remains useful for coverage.

- [ ] **Step 4: Run tests and verify GREEN**

Run: `python -m pytest tests/test_v37_sampling.py -q`

- [ ] **Step 5: Commit**

```bash
git add nailverifier_v3/sampling.py tests/test_v37_sampling.py
git commit -m "feat(v3.7): prioritize unresolved evidence sampling"
```

### Task 8: Surface evidence truth in Streamlit and add runtime safety checks

**Files:**
- Modify: `app.py`
- Create: `nailverifier_v3/audit.py`
- Create: `tests/test_v37_audit.py`

**Interfaces:**
- Produces `audit_verification_output(df: pd.DataFrame) -> list[str]`.
- Audit errors include:
  - Auto REMOVE where status is not VERIFIED_NOT_NAIL
  - Auto KEEP where status is not VERIFIED_NAIL
  - auto-action on `Identity_Collision=YES`
  - VERIFIED row with zero evidence sources
  - VERIFIED row with blank `Primary_Source_URL`

- [ ] **Step 1: Write failing audit tests**

Each invariant above gets one failing fixture plus one valid clean fixture.

- [ ] **Step 2: Run audit tests and verify RED**

Run: `python -m pytest tests/test_v37_audit.py -q`

- [ ] **Step 3: Implement audit and v3.7 UI**

UI title: `Nail Verifier — Precision v3.7 Multi-Source Verification`.

Top metrics: Verified NAIL, Verified NOT_NAIL, Likely/Unverified, Conflicting, Auto REMOVE, Review.

Move these columns near the front of the table:

```text
Verification_Status
Identity_Status
Existence_Status
Nail_Service_Status
Evidence_Source_Count
Strong_Evidence_Count
Primary_Source
Primary_Source_Tier
Primary_Source_URL
Verification_Reason
Identity_Collision
Auto_Action
```

Before rendering the production download button, run `audit_verification_output(result)`. If any audit errors exist, show a blocking error and do not expose the production download button.

Bulk mode remains `use_osm=False`.

- [ ] **Step 4: Run audit tests and full suite**

Run:

```bash
python -m pytest tests/test_v37_audit.py -q
python -m pytest -q
```

Expected: zero failures.

- [ ] **Step 5: Commit**

```bash
git add app.py nailverifier_v3/audit.py tests/test_v37_audit.py
git commit -m "ui(v3.7): surface evidence truth and block unsafe outputs"
```

### Task 9: Documentation and final v3.7 verification

**Files:**
- Modify: `README.md`
- Modify: `docs/superpowers/specs/2026-09-28-multi-source-verification-design.md` only to change implementation status, not requirements

**Interfaces:** None; documentation must match actual implemented behavior and measured output.

- [ ] **Step 1: Run the complete test suite fresh**

Run: `python -m pytest -q`

Expected: zero failures.

- [ ] **Step 2: Run deterministic evidence migration twice and compare**

Run the migration script twice and confirm `git diff --exit-code benchmarks/verified_business_evidence.csv benchmarks/evidence_migration_rejections.csv` after the second run.

Expected: no diff.

- [ ] **Step 3: Update README using measured facts only**

Document v3.7 source tiers, verification states, action gates, registry path, collision behavior, and how to run/download `*-precision-v37.csv`.

Do not carry the v3.6 claim that 124 KEEP / 34 REMOVE are inherently valid under v3.7. Counts must come from a fresh v3.7 534-row run because weaker old evidence is intentionally downgraded.

- [ ] **Step 4: Run the current South Dakota 534-row CSV when available**

Required invariants on the generated result:

```text
all Auto REMOVE rows have Verification_Status == VERIFIED_NOT_NAIL
all Auto KEEP rows have Verification_Status == VERIFIED_NAIL
all collision rows with otherwise automatic action finish as REVIEW
all VERIFIED rows have Primary_Source_URL and Evidence_Source_Count >= 1
no registry-pipeline source error
```

If the 534-row source file is not available in the executor session, do not invent counts; leave the README without final cohort counts and request/run the file at handoff.

- [ ] **Step 5: Commit documentation**

```bash
git add README.md docs/superpowers/specs/2026-09-28-multi-source-verification-design.md
git commit -m "docs(v3.7): document evidence-first verification workflow"
```

- [ ] **Step 6: Verify final commit CI**

Confirm the GitHub Actions `tests` workflow for the final commit is `completed / success` before calling v3.7 complete.
