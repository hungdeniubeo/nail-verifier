# Nail Verifier

Precision-first verifier for NailMap CSV data.

## Main goal

The primary goal is to find NailMap rows that are **not actually nail salons** so they can be removed safely.

The system therefore prefers:

```text
uncertain -> REVIEW
verified nail -> KEEP
exact independently verified NOT_NAIL -> REMOVE
```

over aggressive filtering that could delete a real nail business.

## Current version: Precision v3.6 NOT-NAIL Candidate

V3.6 keeps the existing South Dakota KEEP safeguards and adds an exact verified NOT_NAIL removal path:

- South Dakota `R_NAIL_EXPLICIT_STRONG` may Auto KEEP after calibration.
- Seven independently verified address-strong nail identities may Auto KEEP through an exact identity allowlist.
- All 35 current South Dakota `R_NON_NAIL_CATEGORY_STRONG` identities were independently checked as NOT_NAIL across the existing calibration files.
- Those 35 identities may Auto REMOVE only when **exact normalized name + full street + city + ZIP + phone** match the verified allowlist.
- The generic `R_NON_NAIL_CATEGORY_STRONG` rule is still REVIEW-only for unseen businesses.
- Identity-collision guard can override any Auto KEEP/REMOVE back to REVIEW.
- Other states do not inherit South Dakota exact allowlists or calibrated rules.
- Public Nominatim is disabled for bulk runs.

This design deliberately separates **verified identities** from **generic rules**. A future business named `Ace Hardware`, `Dollar General`, `Restaurant`, etc. does not become Auto REMOVE merely because its name matches a non-nail category.

## Verified NOT_NAIL removal in V3.6

The current 534-row South Dakota cohort contains 35 `R_NON_NAIL_CATEGORY_STRONG` businesses. Their exact identities were independently checked using public/official evidence in:

- `benchmarks/sd_rule_calibration_v33.csv`
- `benchmarks/sd_rule_calibration_v34_addendum.csv`

The cohort includes hardware/building stores, general retail, grocery, restaurants/steakhouse, fuel stops and a hotel/gaming/restaurant complex. Examples include Bowdle Building & Hardware, Ace Hardware locations, Dollar General locations, Hy-Vee Grocery Store, Ruby House Restaurant and Coffee Cup Fuel Stop.

V3.6 matches REMOVE identities using:

```text
state scope
+ normalized company name
+ full normalized street
+ normalized city
+ ZIP
+ normalized phone
```

If any of those identity fields do not match, the row remains REVIEW.

Verified rows use:

```text
Auto_Action = REMOVE
Policy_Status = VERIFIED_IDENTITY_ALLOWLIST
```

### Why the generic REMOVE rule is still disabled

The full checked cohort was 35/35 NOT_NAIL, but that sample is still too small to justify treating every future business matching the rule as safe to remove. The Wilson 95% lower bound for 35/35 is only about 90.11%, below the production gate.

Therefore V3.6 does **not** add `R_NON_NAIL_CATEGORY_STRONG` to `VALIDATED_RULES`. Only already-verified exact identities may Auto REMOVE.

## Expected behavior on the current 534-row SD dataset

The previous v3.5 file contains 35 strong NOT_NAIL candidates. One of them, `Hy-Vee Grocery Store`, shares normalized phone/base address with another business identity (`Hy-Vee Pickup`), so the collision guard is expected to block that exact removal.

Therefore a fresh v3.6 run is expected to produce approximately:

```text
124 Auto KEEP
34 Auto REMOVE
1 verified strong NOT_NAIL candidate blocked by collision -> REVIEW
remaining rows -> REVIEW
```

This is an expected result based on the v3.5 dataset, not a substitute for running v3.6 and checking the output.

## Existing KEEP calibration

### Calibrated strong KEEP rule

Across the base calibration plus the v3.4 addendum:

- 74 labeled `R_NAIL_EXPLICIT_STRONG` cases were independently checked;
- 74/74 matched real nail-service businesses;
- empirical precision on that checked sample = 100%;
- Wilson 95% lower bound is about 95.06%.

This supports the South Dakota production candidate. It is not a guarantee of 100% real-world accuracy.

### Exact address-strong KEEP allowlist

The complete current South Dakota address-strong cohort contained eight businesses. Independent calibration produced 7 NAIL and 1 UNKNOWN (`K & E Nail Studio LLC`). Seven observations are too few to enable the generic rule, so only the seven verified exact identities may Auto KEEP.

Calibration evidence is stored in:

```text
benchmarks/sd_address_strong_v35.csv
```

`K & E Nail Studio LLC` remains REVIEW.

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

The original candidate action and rule remain visible for audit. This guard runs after exact allowlists and calibrated-rule policy.

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

## South Dakota policy

### Auto KEEP

1. `R_NAIL_EXPLICIT_STRONG` when the calibrated state rule applies and no collision blocks it.
2. Exact independently verified address-strong nail identities.
3. Nail-specific current official-state evidence, when available.

### Auto REMOVE

Only exact independently verified v3.6 NOT_NAIL identities from the current SD calibration cohort, with exact normalized identity match and no collision guard block.

### Still REVIEW

- any unseen `R_NON_NAIL_CATEGORY_STRONG` business not in the exact verified allowlist;
- `R_NON_NAIL_CATEGORY_ADDRESS_STRONG`;
- generic `R_NAIL_EXPLICIT_ADDRESS_STRONG` rows not in the exact KEEP allowlist;
- `K & E Nail Studio LLC` until independently verified;
- `R_NAIL_EXPLICIT_WEAK`;
- `R_NAIL_STYLING_HINT`;
- `R_BEAUTY_AMBIGUOUS`;
- `R_UNKNOWN`;
- permanently/temporarily closed local-source rules unless independently handled by stronger evidence;
- any identity-collision row that would otherwise auto-act.

## Next target: beauty / hair / spa ambiguity

After the exact NOT_NAIL cohort is confirmed in a v3.6 full run, the next focus is `R_BEAUTY_AMBIGUOUS`. Hair salons, spas and beauty businesses cannot be removed just because their name lacks the word `nail`: many multi-service salons offer nail services. Those rows require independent service/category evidence before any NOT_NAIL conclusion.

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
Nail Verifier — Precision v3.6 NOT-NAIL Candidate
```

For the 534-row South Dakota dataset choose:

```text
Chạy toàn bộ CSV — SD production candidate
```

Bulk mode automatically disables public Nominatim.

Download result:

```text
*-precision-v36.csv
```

## Tests

```bash
python -m pytest -q
```

Regression coverage includes:

- Audra must not false-match Revive;
- nail-specific official license is safe KEEP;
- Nail Supply / Nail Academy conflicts never qualify for Auto KEEP;
- SD strong nail rule may Auto KEEP;
- exact verified address-strong nail identity may Auto KEEP;
- `K & E Nail Studio LLC` remains REVIEW;
- exact verified NOT_NAIL identity may Auto REMOVE;
- same verified NOT_NAIL name at a wrong address remains REVIEW;
- unseen strong non-nail business remains REVIEW;
- exact allowlists do not leak outside South Dakota;
- same phone + same base address + different names blocks both KEEP and REMOVE auto-actions;
- v3.6 uses a new engine/cache version and policy profile.

## Phase 1 exporter

`export_visible_table.js` exports the NailMap virtual table, deduplicates records and checks exported row count against NailMap's expected total before accepting the CSV.

---

No public-data verifier can guarantee 100% accuracy. V3.6 deliberately prioritizes precision over coverage and only removes exact identities already supported by independent NOT_NAIL evidence.
