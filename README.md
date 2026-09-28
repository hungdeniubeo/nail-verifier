# Nail Verifier

Precision-first verifier for NailMap CSV data.

## Current version: Precision v3.4.1 Production Candidate

V3.4.1 is intentionally conservative:

- South Dakota `R_NAIL_EXPLICIT_STRONG` may Auto KEEP.
- Identity-collision guard can override an otherwise valid Auto KEEP/REMOVE back to REVIEW.
- South Dakota local REMOVE rules are still REVIEW-only.
- Other states do not inherit South Dakota auto-policy.
- Public Nominatim is disabled for bulk runs.
- Official state evidence remains higher priority than local heuristics.

## Why only KEEP is enabled

The strong SD nail-name rule was frozen before the latest validation addendum.
Across the base calibration plus the addendum:

- 74 labeled strong-rule cases were independently checked.
- 74/74 matched real nail-service businesses.
- empirical precision on that checked sample = 100%.
- Wilson 95% lower bound is about 95.06%.
- the latest 50-case addendum contains 50/50 nail matches.

This is evidence for a production candidate, not a guarantee of 100% real-world accuracy.

The strong SD non-nail rule is still blocked:

- all 35 candidates in the current 534-row SD dataset were independently checked as non-nail;
- but 35 perfect observations only give a Wilson 95% lower bound of about 90.11%;
- therefore V3.4.1 does **not** auto-remove those rows.

## Identity-collision guard

V3.4.1 adds a dataset-level safety guard.

A row is marked `Identity_Collision = YES` when:

- normalized phone is the same;
- normalized base street address is the same (suite/unit is ignored for collision grouping);
- city/state/ZIP agree;
- more than one distinct normalized company name appears in that group.

When a collision row would otherwise be Auto KEEP or Auto REMOVE:

```text
Auto_Action = REVIEW
Policy_Status = IDENTITY_COLLISION_REVIEW
```

The original `Candidate_Action` and rule are retained for audit.

Important behavior:

- same phone + different address is **not** a collision;
- exact duplicate rows with the same normalized business name are **not** identity collisions;
- collisions on rows that were already REVIEW stay REVIEW but are still flagged for audit.

On the previous 534-row SD v3.4 output, the v3.4.1 collision rule identifies 15 collision rows in total. Four of those rows were Auto KEEP candidates, so applying the new guard would reduce local Auto KEEP from 121 to 117 while keeping local Auto REMOVE at 0.

## Normalized identity output

V3.4.1 exports additional downstream-safe fields:

- `Normalized_Street`
- `Normalized_City`
- `Normalized_ZIP`
- `Normalized_Phone`

This also makes shifted-address recovery visible in output. For example, when a source row accidentally puts a street value in the City column, the raw CSV is preserved while normalized fields reflect the recovered record used by the verifier.

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

`R_NAIL_EXPLICIT_STRONG`

Requires:

- explicit nail-service name;
- `OPERATIONAL`;
- location/ZIP;
- phone;
- at least 3 reviews;
- no non-service nail conflict term;
- no dataset-level identity collision.

### Still REVIEW

- `R_NAIL_EXPLICIT_ADDRESS_STRONG`
- `R_NAIL_EXPLICIT_WEAK`
- `R_NAIL_STYLING_HINT`
- `R_BEAUTY_AMBIGUOUS`
- `R_UNKNOWN`
- `R_NON_NAIL_CATEGORY_STRONG`
- `R_NON_NAIL_CATEGORY_ADDRESS_STRONG`
- permanently/temporarily closed local-source rules unless independently handled by stronger evidence
- any identity-collision row that would otherwise auto-act

## Official South Dakota adapter

The SD adapter:

1. downloads the current business-license roster once;
2. indexes it locally by ZIP/city;
3. shortlists plausible business-name candidates;
4. validates detail pages with distinctive-name + address guards.

Regression case:

```text
Audra Day Spa & Salon
!=
Revive Day Spa - Apprentice Salon
```

while a legal/DBA variant such as Revive can match when distinctive name and address agree.

## Calibration files

- `benchmarks/sd_rule_calibration_v33.csv`
- `benchmarks/sd_rule_calibration_v34_addendum.csv`

The addendum contains 50 independently checked strong-nail cases plus 14 additional strong non-nail cases.

Benchmark multiple files together:

```bash
python benchmark_v3.py \
  --file benchmarks/sd_rule_calibration_v33.csv \
  --file benchmarks/sd_rule_calibration_v34_addendum.csv
```

`UNKNOWN` labels are excluded from precision calculations.

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
Nail Verifier — Precision v3.4.1 Production Candidate
```

For the 534-row South Dakota dataset choose:

```text
Chạy toàn bộ CSV — SD production candidate
```

Bulk mode automatically disables public Nominatim.

Download result:

```text
*-precision-v341.csv
```

## Tests

```bash
python -m pytest -q
```

Important regression coverage includes:

- Audra must not false-match Revive;
- Revive DBA/legal-name variant can match only with address agreement;
- nail-specific official license is safe KEEP;
- Nail Supply / Nail Academy conflicts never qualify for Auto KEEP;
- SD strong nail rule may Auto KEEP;
- SD strong non-nail rule remains REVIEW;
- the same SD rule remains blocked outside SD;
- same phone + same base address + different names blocks auto-action;
- same phone at different addresses does not collide;
- exact duplicate name is not treated as identity collision;
- normalized identity fields are exported;
- calibration loader can combine multiple gold CSVs reproducibly.

## Phase 1 exporter

`export_visible_table.js` exports the NailMap virtual table, deduplicates records and checks exported row count against NailMap's expected total before accepting the CSV.

---

No public-data verifier can guarantee 100% accuracy. V3.4.1 deliberately prioritizes precision over coverage and keeps uncertain cases in REVIEW.
