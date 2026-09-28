# Nail Verifier v3.7 — Multi-Source Verification Design

Date: 2026-09-28
Status: Design approved in chat; implementation not started

## 1. Purpose

The project’s final goal is not to guess which NailMap businesses are nail salons. It is to produce an auditable real-world classification for each business using business-specific evidence.

The verifier must answer, as conservatively as possible:

1. Does this exact business identity exist?
2. Is it currently active, closed, or unclear?
3. Does this exact business offer nail services?
4. Is there enough independent evidence to classify it as nail or not-nail?
5. Are there identity collisions or contradictory sources that require human review?

The system must prefer REVIEW over an unsupported KEEP or REMOVE.

## 2. Core principle

Rules such as business-name patterns, review count, category words, or NailMap metadata may prioritize investigation, but they are not ground truth.

A row is only VERIFIED when there is business-specific evidence tied to the same real-world identity.

Absence of evidence is not evidence of absence. A salon website that does not mention nails is not enough by itself to prove NOT_NAIL.

## 3. Final verification states

Every row receives one of these evidence-level statuses:

- `VERIFIED_NAIL`
- `VERIFIED_NOT_NAIL`
- `LIKELY_NAIL`
- `LIKELY_NOT_NAIL`
- `CONFLICTING_EVIDENCE`
- `UNKNOWN`

These statuses are separate from `Candidate_Action` and `Auto_Action`.

### Action policy

- `VERIFIED_NAIL` → eligible for KEEP, subject to collision/safety guards.
- `VERIFIED_NOT_NAIL` → eligible for REMOVE, subject to collision/safety guards.
- `LIKELY_NAIL` → no verified claim; default REVIEW unless a separate existing policy explicitly permits KEEP.
- `LIKELY_NOT_NAIL` → REVIEW.
- `CONFLICTING_EVIDENCE` → REVIEW.
- `UNKNOWN` → REVIEW.

V3.7 must never Auto REMOVE a row unless its final verification status is `VERIFIED_NOT_NAIL`.

## 4. Verification pipeline

Each row passes through seven stages.

### Stage 1 — Data quality and normalization

Normalize and retain:

- company name
- street, including suite/unit for exact identity
- base street without suite/unit for collision detection
- city
- state
- ZIP
- phone

Detect:

- malformed shifted fields
- exact duplicates
- shared addresses
- same-phone/same-base-address/different-name identity collisions

A collision does not determine nail status; it prevents automatic action until identity ambiguity is resolved.

### Stage 2 — Identity verification

Before using a source as category or service evidence, the source must be tied to the NailMap row.

Identity matching considers:

- normalized business name
- address
- phone
- ZIP/city
- stable license/store ID where available

Evidence that cannot be tied to the exact business identity may be recorded but cannot create a VERIFIED result.

### Stage 3 — Business existence/status

Determine whether evidence supports:

- `VERIFIED_ACTIVE`
- `VERIFIED_CLOSED`
- `LIKELY_ACTIVE`
- `UNKNOWN`

Source freshness must be retained when available.

A closed business is not automatically NOT_NAIL. Operational status and nail-service classification are independent dimensions.

### Stage 4 — Category classification

Classify business category evidence independently from nail-service evidence.

Examples:

- nail salon
- hair salon
- beauty salon
- spa
- hardware store
- grocery store
- restaurant
- fuel stop
- hotel/gaming
- other

A non-beauty category from a strong identity-matched source is strong NOT_NAIL evidence. Beauty/hair/spa categories remain ambiguous until services are checked.

### Stage 5 — Nail-service verification

Positive nail evidence includes explicit services such as:

- manicure
- pedicure
- acrylic nails
- gel nails
- Gel-X
- dip powder
- nail extensions
- nail art
- manicurist/pedicurist licensing

Strong negative nail evidence requires more than a missing nail word. It should come from a business-specific category/service context that affirmatively identifies the business as a different type of business, or from multiple aligned sources with no contradictory nail evidence.

### Stage 6 — Cross-source consensus

Evidence is aggregated by source tier and direction.

The consensus engine must track:

- number of evidence sources
- number of strong sources
- positive nail evidence
- strong not-nail evidence
- identity confidence
- conflicting evidence
- source diversity

Conflicting strong evidence always produces `CONFLICTING_EVIDENCE` and REVIEW.

### Stage 7 — Final status and action gate

The consensus result produces `Verification_Status`.

Only after this status is produced does policy decide KEEP/REMOVE/REVIEW.

Identity-collision guard runs after policy and may override KEEP/REMOVE to REVIEW.

## 5. Source tiers

Sources are classified by reliability and directness.

### Tier A — primary/official

Examples:

- official state/license registry
- official business website
- official booking/service menu
- official chain/store locator

### Tier B — established independent source

Examples:

- BBB
- Chamber of Commerce
- Apple Maps when category/identity is clearly matched
- established local newspaper/business directory

### Tier C — secondary directory

Examples:

- specialized salon directories
- BestProsInTown
- Loc8NearMe
- Birdeye listings
- similar independent directories

### Tier D — heuristic/source listing

Examples:

- NailMap name
- NailMap reviews/rating
- NailMap operational status
- name-pattern rules

Tier D may prioritize or support investigation but cannot by itself create `VERIFIED_NAIL` or `VERIFIED_NOT_NAIL`.

## 6. Evidence registry

V3.7 introduces a business-specific evidence registry rather than expanding hard-coded allowlists in `policy.py`.

### File

`benchmarks/verified_business_evidence.csv`

### Minimum columns

- `State`
- `Company`
- `Street`
- `City`
- `ZIP`
- `Phone`
- `Source_Name`
- `Source_Tier`
- `Source_URL`
- `Observed_Category`
- `Nail_Service_Evidence`
- `Business_Status_Evidence`
- `Evidence_Direction`
- `Evidence_Notes`
- `Checked_At`

`Evidence_Direction` values:

- `NAIL`
- `NOT_NAIL`
- `IDENTITY_ONLY`
- `STATUS_ONLY`
- `AMBIGUOUS`

Multiple rows may exist for one business identity, one per source.

## 7. New code boundaries

### `nailverifier_v3/evidence_registry.py`

Responsibilities:

- load the CSV registry
- normalize registry identities
- return evidence rows matching one `BusinessRecord`
- reject wrong-address/wrong-phone matches according to source requirements

It must not decide final status.

### `nailverifier_v3/evidence_classifier.py`

Responsibilities:

- convert registry rows and live-source `Evidence` objects into normalized evidence signals
- assign source tier
- classify each signal as nail/not-nail/identity/status/ambiguous

It must not decide Auto_Action.

### `nailverifier_v3/consensus.py`

Responsibilities:

- combine evidence signals
- detect contradictions
- derive:
  - `Verification_Status`
  - `Identity_Status`
  - `Existence_Status`
  - `Nail_Service_Status`
  - source counts
  - primary source
  - human-readable verification reason

It must not contain state-specific policy allowlists.

### `policy.py`

Responsibilities after v3.7:

- consume final verification status
- decide whether a row is eligible for KEEP, REMOVE, or REVIEW
- retain state-scoped safety rules during migration

Business identity data must move out of `policy.py` into the evidence registry.

### `engine.py`

Responsibilities:

- execute stages in order
- merge live official/OSM evidence with registry evidence
- call consensus
- call policy
- run dataset-level duplicate/collision guards
- export audit fields

## 8. Required output fields

V3.7 adds:

- `Verification_Status`
- `Identity_Status`
- `Existence_Status`
- `Nail_Service_Status`
- `Evidence_Source_Count`
- `Strong_Evidence_Count`
- `Evidence_Agrees`
- `Evidence_Conflicts`
- `Primary_Source`
- `Primary_Source_Tier`
- `Primary_Source_URL`
- `Verification_Evidence`
- `Verification_Reason`
- `Verified_At`

Existing audit fields remain, including rules, candidate actions, collisions, normalized identity, official evidence, and source errors.

## 9. Initial migration scope

V3.7 will first migrate already researched business-specific evidence. This avoids pretending the entire 534-row dataset is already verified.

Phase 1 migration:

- 35 current SD strong NOT_NAIL identities from v3.3/v3.4 calibration
- 7 v3.5 address-strong NAIL identities

Phase 2 migration:

- every additional nail business in existing calibration files that already has a source URL and business-specific evidence

Rows that were only inferred through the 74/74 strong-name calibration remain `LIKELY_NAIL` unless they also have individual evidence in the registry.

The current calibrated strong KEEP rule may remain visible during transition, but `Verification_Status` must make clear whether a row is individually verified or only rule-derived.

## 10. Consensus rules for v3.7

The first implementation should be conservative and deterministic.

### VERIFIED_NAIL

Requires:

- verified identity, and
- at least one strong business-specific source with explicit nail-service/category evidence, and
- no strong NOT_NAIL conflict.

A Tier A explicit nail service source is sufficient when identity is exact.

A Tier B/C source may be sufficient when it explicitly classifies the exact business as a nail salon or explicitly lists nail services and identity matching is strong.

### VERIFIED_NOT_NAIL

Requires:

- verified identity, and
- strong affirmative non-beauty/category evidence for the exact business, and
- no positive nail-service evidence, and
- no unresolved identity collision.

Examples include an exact official Ace Hardware store, Dollar General location, restaurant website, grocery store, fuel stop, or hardware/business directory entry.

Beauty/hair/spa businesses do not qualify for VERIFIED_NOT_NAIL merely because nail services are absent from one source.

### CONFLICTING_EVIDENCE

Set when strong identity-matched sources disagree on nail vs not-nail classification, or when evidence suggests the row may combine two real businesses.

### LIKELY states

Used when heuristics or weaker evidence point in one direction but the VERIFIED threshold is not met.

## 11. Safety invariants

These are non-negotiable regression requirements:

1. Auto REMOVE requires `Verification_Status = VERIFIED_NOT_NAIL`.
2. Identity collision overrides automatic KEEP/REMOVE to REVIEW.
3. Wrong-address same-name evidence must not verify a business.
4. Wrong-state evidence must not leak across state scope.
5. A NailMap name pattern alone can never create VERIFIED status.
6. Missing nail services on one salon page can never by itself create VERIFIED_NOT_NAIL.
7. Strong contradictory evidence produces REVIEW.
8. Source errors never improve confidence or enable auto action.
9. Existing normalized-address recovery must continue to work.
10. Business-specific evidence and the reason for the result must be exportable and auditable.

## 12. Testing strategy

Development uses TDD.

Required test groups:

### Registry matching

- exact business identity loads evidence
- same name/wrong address does not match
- same name/wrong state does not match
- phone mismatch behavior is conservative
- missing phone identities can still match only when the stored evidence identity is otherwise exact and the registry record explicitly permits the missing phone through its own data

### Consensus

- Tier A explicit nail service → VERIFIED_NAIL
- exact official hardware store → VERIFIED_NOT_NAIL
- hair salon with no nail mention → not VERIFIED_NOT_NAIL
- nail and not-nail strong sources → CONFLICTING_EVIDENCE
- heuristic-only record → LIKELY/UNKNOWN, never VERIFIED

### Policy

- VERIFIED_NOT_NAIL → REMOVE eligibility
- LIKELY_NOT_NAIL → REVIEW
- VERIFIED_NAIL → KEEP eligibility
- collision overrides REMOVE
- collision overrides KEEP

### Migration/regression

- Bowdle Building & Hardware remains verified not-nail and removable
- Hy-Vee Grocery Store remains blocked by collision
- Anna's Nails becomes verified nail from registry evidence
- Cobe Nails/Rose Nails collision behavior remains protected
- Hang Nails Salon must not be labeled individually VERIFIED merely because the strong nail-name rule fires unless registry/live evidence verifies it

## 13. UI changes

The Streamlit UI should prioritize evidence-level truth over rule metrics.

Top-level metrics:

- Verified NAIL
- Verified NOT_NAIL
- Likely/Unverified
- Conflicting
- Auto REMOVE
- Review

The table should show `Verification_Status`, source count, primary source, URL, reason, and collision status near the front.

The UI must explicitly distinguish:

- `VERIFIED_NAIL` = business-specific evidence
- `LIKELY_NAIL` = rule/weak evidence only

## 14. Scaling strategy

The registry is a reusable evidence cache for future states and large datasets.

For 50k+ businesses:

1. run local rules to prioritize rows
2. reuse already verified registry identities
3. research only unresolved identities
4. append new evidence, never overwrite history silently
5. rerun consensus deterministically from stored evidence

Live web research and state-specific adapters can feed the same evidence model without changing final policy semantics.

## 15. Success criteria for v3.7

V3.7 is complete when:

- all tests pass
- current 42 exact researched identities are migrated to the registry
- verified statuses include auditable source URLs/evidence
- heuristic-only rows are clearly labeled unverified
- all Auto REMOVE rows are `VERIFIED_NOT_NAIL`
- collision protection remains active
- the 534-row SD run completes without source errors caused by the new registry pipeline
- output clearly explains why each verified business was classified

## 16. Explicit non-goals for v3.7

V3.7 will not yet:

- prove all 534 South Dakota businesses
- auto-research every business on the live web during a bulk run
- enable generic REMOVE rules for future unseen businesses
- treat one missing service list as proof that a beauty business does not offer nails
- solve all 50 states at once

The next phase after v3.7 is evidence acquisition for the unresolved South Dakota cohort, beginning with `R_BEAUTY_AMBIGUOUS` and then other UNKNOWN/weak groups.
