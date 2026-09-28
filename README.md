# Nail Verifier

Precision-first verifier for NailMap CSV data.

## Main goal

The primary goal is to find NailMap rows that are **not actually nail salons** so they can be removed safely.

V3.7 no longer treats a business name, NailMap category, review count, or a calibrated rule as proof. Those signals only prioritize research. A business is `VERIFIED_*` only when business-specific evidence matches the same real-world identity and passes the source-consensus gate.

```text
VERIFIED_NAIL       -> eligible KEEP
VERIFIED_NOT_NAIL   -> eligible REMOVE
LIKELY / UNKNOWN    -> REVIEW
CONFLICTING         -> REVIEW
identity collision  -> REVIEW
```

## Current version: Precision v3.7 Multi-Source Verification

V3.7 introduces a seven-stage evidence-first pipeline:

1. normalize business identity;
2. match evidence to the exact business;
3. assess existence/status;
4. classify business category;
5. verify nail-service evidence;
6. combine independent sources and detect conflicts;
7. apply action policy, then run dataset-level collision guards.

The old v3.6 exact identity allowlists have been removed from `policy.py`. Business-specific truth now lives in the evidence registry:

```text
benchmarks/verified_business_evidence.csv
```

The registry is auditable: each evidence row keeps the business identity, source, source tier, source URL, category/service evidence, direction, notes, and checked date.

## Verification states

- `VERIFIED_NAIL`
- `VERIFIED_NOT_NAIL`
- `LIKELY_NAIL`
- `LIKELY_NOT_NAIL`
- `CONFLICTING_EVIDENCE`
- `UNKNOWN`

These are separate from legacy `Decision` / `Candidate_Action` fields. Legacy fields stay in the CSV for debugging and research prioritization, but **they do not authorize Auto_Action in v3.7**.

## Source tiers

### Tier A — primary / official

Examples:

- official state/license registry;
- official business website;
- official booking/service page;
- official chain/store locator.

One exact Tier A directional source may be enough for `VERIFIED_NAIL` or `VERIFIED_NOT_NAIL` when it affirmatively proves the relevant category/service and there is no strong conflict.

### Tier B — established independent source

Examples:

- BBB;
- Chamber of Commerce;
- Apple Maps;
- established local newspaper/business directory.

### Tier C — secondary directory

Examples:

- BestProsInTown;
- Loc8NearMe;
- Birdeye;
- YellowPages;
- specialized salon directories.

A single Tier B or C source produces at most `LIKELY_*`. At least two independent agreeing B/C sources are required to reach VERIFIED.

### Tier D — heuristic only

Examples:

- NailMap business name;
- rating/review count;
- NailMap operational status;
- local name/category rules.

Tier D never creates VERIFIED status by itself.

## Critical NOT_NAIL rule

`VERIFIED_NOT_NAIL` requires business-specific identity evidence and affirmative evidence that the exact business is a clearly different category, such as hardware, retail, grocery, restaurant, fuel stop, hotel/gaming, etc.

A hair salon, spa, day spa, beauty salon, or aesthetics business is **not** considered NOT_NAIL merely because one page does not mention nails. Absence of nail evidence is not evidence of absence.

## Consensus gate

A result can become VERIFIED when either:

```text
1 exact Tier A directional source
```

or:

```text
2+ independent Tier B/C directional sources that agree
```

Strong NAIL and NOT_NAIL evidence for the same identity produces:

```text
Verification_Status = CONFLICTING_EVIDENCE
Auto_Action = REVIEW
```

Duplicate evidence rows from the same provider/domain do not count as independent sources.

## Identity matching

Stored registry evidence must match:

```text
state
+ normalized company
+ full normalized street including suite/unit
+ normalized city
+ ZIP
```

Phone handling is conservative:

- if both evidence and NailMap expose a phone, the normalized phones must agree;
- if one side lacks phone, exact name/location identity may still match;
- two non-empty conflicting phones reject the registry evidence.

Dataset collision detection remains separate and uses same phone + same base street + city/state/ZIP with multiple business names. A collision can block any otherwise valid KEEP/REMOVE.

## Production action policy

### Auto KEEP

Only:

```text
Verification_Status = VERIFIED_NAIL
```

and no collision/source safety guard blocks the action.

### Auto REMOVE

Only:

```text
Verification_Status = VERIFIED_NOT_NAIL
```

and no collision/source safety guard blocks the action.

### REVIEW

Everything else, including:

- `LIKELY_NAIL`;
- `LIKELY_NOT_NAIL`;
- `UNKNOWN`;
- `CONFLICTING_EVIDENCE`;
- a single Tier B/C source;
- rule-only nail/non-nail guesses;
- unresolved beauty/hair/spa businesses;
- identity collisions;
- source-error runs that would otherwise auto-act.

## Output audit fields

Important v3.7 columns include:

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
- `Auto_Action`
- `Policy_Status`
- `Identity_Collision`
- normalized identity fields
- legacy rule/candidate fields for audit

Before the Streamlit app exposes the production CSV download, `audit_verification_output()` checks that:

- every Auto REMOVE is `VERIFIED_NOT_NAIL`;
- every Auto KEEP is `VERIFIED_NAIL`;
- no collision row still auto-acts;
- every VERIFIED row has at least one evidence source;
- every VERIFIED row has a primary source URL.

If any invariant fails, production download is blocked.

## Evidence migration

Existing researched calibration rows can be migrated with:

```bash
python scripts/build_verified_business_evidence.py
```

Inputs:

- `benchmarks/sd_rule_calibration_v33.csv`
- `benchmarks/sd_rule_calibration_v34_addendum.csv`
- `benchmarks/sd_address_strong_v35.csv`

Outputs:

- `benchmarks/verified_business_evidence.csv`
- `benchmarks/evidence_migration_rejections.csv`

`UNKNOWN` or missing-source rows are rejected rather than silently treated as evidence.

## Cache safety

The engine version is `3.7.0`.

The verification cache key includes the SHA-256 digest of the evidence registry. Editing the registry therefore invalidates old verification results automatically; a v3.6 or older cached action cannot silently survive a registry change.

## Research workflow

After each bulk run, the validation/research sample prioritizes unresolved rows instead of already verified rows, especially:

1. `CONFLICTING_EVIDENCE`;
2. `R_BEAUTY_AMBIGUOUS`;
3. `UNKNOWN`;
4. `LIKELY_NAIL` / `LIKELY_NOT_NAIL`;
5. weak/name-only cases.

This is the path for improving South Dakota coverage without weakening precision.

## Run on macOS

```bash
cd ~/nail-verifier
git pull
bash run_mac.sh
```

Open:

```text
http://localhost:8501
```

Expected title:

```text
Nail Verifier — Precision v3.7 Multi-Source Verification
```

For the 534-row South Dakota dataset choose:

```text
Chạy toàn bộ CSV — evidence-first production candidate
```

Bulk mode disables public Nominatim.

Download result:

```text
*-precision-v37.csv
```

No final 534-row KEEP/REMOVE count is hard-coded in this README. V3.7 intentionally downgrades old rule-only or single-secondary-source actions, so production counts must come from a fresh v3.7 run.

## Tests

```bash
python -m pytest -q
```

Regression coverage includes exact registry matching, phone conflict handling, source-tier classification, independent-source consensus, conflict handling, evidence-only action policy, cache invalidation, collision overrides, shifted-address recovery, unresolved sampling, and output safety auditing.

---

No public-data verifier can guarantee 100% real-world accuracy. This project deliberately trades coverage for precision: unsupported conclusions stay REVIEW until stronger business-specific evidence is available.
