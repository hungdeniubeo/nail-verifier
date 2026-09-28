# Nail Verifier

Precision-first verifier for NailMap CSV data.

## Current version: Precision v3.5 Production Candidate

V3.5 stays conservative:

- South Dakota `R_NAIL_EXPLICIT_STRONG` may Auto KEEP after calibration.
- Seven independently verified South Dakota `R_NAIL_EXPLICIT_ADDRESS_STRONG` identities may Auto KEEP only through an **exact identity allowlist**.
- The generic address-strong rule is still REVIEW-only.
- Identity-collision guard can override any otherwise valid Auto KEEP/REMOVE back to REVIEW.
- South Dakota local REMOVE rules are still REVIEW-only.
- Other states do not inherit South Dakota auto-policy.
- Public Nominatim is disabled for bulk runs.
- Official state evidence remains higher priority than local heuristics.

## Calibrated strong KEEP rule

Across the base calibration plus the v3.4 addendum:

- 74 labeled `R_NAIL_EXPLICIT_STRONG` cases were independently checked;
- 74/74 matched real nail-service businesses;
- empirical precision on that checked sample = 100%;
- Wilson 95% lower bound is about 95.06%.

This supports a production candidate. It is not a guarantee of 100% real-world accuracy.

## V3.5 exact verified identity allowlist

The complete South Dakota `R_NAIL_EXPLICIT_ADDRESS_STRONG` cohort in the current 534-row dataset contains eight businesses. Independent public-source calibration produced:

- 7 `NAIL`;
- 1 `UNKNOWN` (`K & E Nail Studio LLC`).

Seven observations are far too few to enable the generic rule statistically, so V3.5 does **not** add `R_NAIL_EXPLICIT_ADDRESS_STRONG` to `VALIDATED_RULES`.

Instead, only these seven already-verified identities can Auto KEEP:

- Anna's Nails — 712 University Ave Ste A, Hot Springs, SD 57747
- Nails By Alayna Reyes — 901 N Main St Ste 4, Mitchell, SD 57301
- Olive & Opal Nail Studio — 501 Main St Studio 4, Rapid City, SD 57701
- Simplee Nails — 317 Main St Ste 1, Rapid City, SD 57701
- The Nail Room — 822 Main St Ste 5, Rapid City, SD 57701
- The Nail Haus By Adamari — 5201 S Solberg Ave Suite 205, Sioux Falls, SD 57108
- Zen Nail Studio — 5201 S Solberg Ave Suite 200, Sioux Falls, SD 57108

The match is exact after normalization of:

```text
company name + full street/suite + city + ZIP + state scope
```

A business with the same name but a different address does not qualify. A new business that merely resembles one of these patterns does not qualify. `K & E Nail Studio LLC` remains REVIEW.

Allowlisted rows use:

```text
Auto_Action = KEEP
Policy_Status = VERIFIED_IDENTITY_ALLOWLIST
```

Calibration evidence is stored in:

```text
benchmarks/sd_address_strong_v35.csv
```

## Auto REMOVE remains disabled

The strong SD non-nail cohort is empirically clean in the current dataset, but the statistical lower bound is still below the production gate. Therefore V3.5 continues to keep local REMOVE candidates in REVIEW.

## Identity-collision guard

A row is marked `Identity_Collision = YES` when:

- normalized phone is the same;
- normalized base street address is the same (suite/unit ignored for collision grouping);
- city/state/ZIP agree;
- more than one distinct normalized company name appears in that group.

When a collision row would otherwise be Auto KEEP or Auto REMOVE:

```text
Auto_Action = REVIEW
Policy_Status = IDENTITY_COLLISION_REVIEW
```

The original candidate action and rule remain visible for audit. This guard runs after the allowlist and calibrated-rule policy, so an exact allowlisted identity can still be blocked if the dataset itself shows an identity collision.

## Other safety guards

Names such as these never qualify for the strong nail Auto KEEP rule:

- Nail Supply
- Nail Wholesale
- Nail Academy
- Nail School
- Nail Products
- Nail Equipment
- Nail Distributor

They are routed to `R_NAIL_NON_SERVICE_CONFLICT` and remain REVIEW.

## Main output fields

- `Decision`
- `Candidate_Action`
- `Auto_Action`
- `Policy_Status`
- `Policy_Profile`
- `Rule_ID`
- `Business_Exists`
- `Nail_Service`
- `Identity_Collision`
- `Collision_Group_Size`
- `Collision_Names`
- `Normalized_Street`
- `Normalized_City`
- `Normalized_ZIP`
- `Normalized_Phone`
- `Risk_Flags`
- `Shared_Address_Count`
- `Exact_Record_Duplicate_Count`
- official-source evidence columns
- `Reason`
- `Source_Errors`

## South Dakota policy

### Auto KEEP

1. `R_NAIL_EXPLICIT_STRONG` when the calibrated state rule applies and no collision guard blocks it.
2. Exact independently verified v3.5 identities from the address-strong allowlist, with exact normalized identity match and no collision guard block.
3. Nail-specific current official-state evidence, when available.

### Still REVIEW

- generic `R_NAIL_EXPLICIT_ADDRESS_STRONG` rows not in the exact allowlist;
- `K & E Nail Studio LLC` until independently verified;
- `R_NAIL_EXPLICIT_WEAK`;
- `R_NAIL_STYLING_HINT`;
- `R_BEAUTY_AMBIGUOUS`;
- `R_UNKNOWN`;
- `R_NON_NAIL_CATEGORY_STRONG`;
- `R_NON_NAIL_CATEGORY_ADDRESS_STRONG`;
- permanently/temporarily closed local-source rules unless independently handled by stronger evidence;
- any identity-collision row that would otherwise auto-act.

## Calibration files

- `benchmarks/sd_rule_calibration_v33.csv`
- `benchmarks/sd_rule_calibration_v34_addendum.csv`
- `benchmarks/sd_address_strong_v35.csv`

`UNKNOWN` labels are excluded from precision calculations and never treated as positive evidence.

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

You should see:

```text
Nail Verifier — Precision v3.5 Production Candidate
```

For the 534-row South Dakota dataset choose:

```text
Chạy toàn bộ CSV — SD production candidate
```

Bulk mode automatically disables public Nominatim.

Download result:

```text
*-precision-v35.csv
```

## Tests

```bash
python -m pytest -q
```

Regression coverage includes:

- Audra must not false-match Revive;
- Revive DBA/legal-name variant requires address agreement;
- nail-specific official license is safe KEEP;
- Nail Supply / Nail Academy conflicts never qualify for Auto KEEP;
- SD strong nail rule may Auto KEEP;
- SD strong non-nail rule remains REVIEW;
- state-scoped rules do not leak to other states;
- same phone + same base address + different names blocks auto-action;
- exact duplicate name is not treated as identity collision;
- normalized identity fields are exported;
- exact verified address-strong identity may Auto KEEP;
- the same verified name at a wrong address stays REVIEW;
- `K & E Nail Studio LLC` remains REVIEW;
- exact allowlist does not leak outside South Dakota.

## Phase 1 exporter

`export_visible_table.js` exports the NailMap virtual table, deduplicates records and checks exported row count against NailMap's expected total before accepting the CSV.

---

No public-data verifier can guarantee 100% accuracy. V3.5 deliberately prioritizes precision over coverage and keeps uncertain cases in REVIEW.
