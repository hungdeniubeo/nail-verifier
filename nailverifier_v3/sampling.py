from __future__ import annotations

from typing import Dict, List, Optional

import pandas as pd

DEFAULT_TARGETS: Dict[str, int] = {
    "R_BEAUTY_AMBIGUOUS": 30,
    "R_UNKNOWN": 20,
    "R_NAIL_EXPLICIT_WEAK": 15,
    "R_NAIL_STYLING_HINT": 10,
    "R_NAIL_NON_SERVICE_CONFLICT": 10,
    "R_NAIL_EXPLICIT_ADDRESS_STRONG": 10,
    "R_NAIL_EXPLICIT_STRONG": 10,
    "R_NON_NAIL_CATEGORY_STRONG": 10,
    "R_NON_NAIL_CATEGORY_ADDRESS_STRONG": 10,
}

VERIFIED = {"VERIFIED_NAIL", "VERIFIED_NOT_NAIL"}


def make_validation_sample(
    result: pd.DataFrame,
    seed: int = 320,
    targets: Optional[Dict[str, int]] = None,
) -> pd.DataFrame:
    targets = targets or DEFAULT_TARGETS
    if "Rule_ID" not in result.columns:
        raise ValueError("Result must contain Rule_ID.")

    pool = result
    if "Verification_Status" in result.columns:
        unresolved = result[~result["Verification_Status"].isin(VERIFIED)]
        if not unresolved.empty:
            pool = unresolved

    sampled: List[pd.DataFrame] = []
    used_indexes = set()

    # Conflicts are always research-worthy and are kept before stratified sampling.
    if "Verification_Status" in pool.columns:
        conflicts = pool[pool["Verification_Status"] == "CONFLICTING_EVIDENCE"]
        if not conflicts.empty:
            sampled.append(conflicts)
            used_indexes.update(conflicts.index.tolist())

    for rule_id, target in targets.items():
        bucket = pool[(pool["Rule_ID"] == rule_id) & ~pool.index.isin(used_indexes)]
        if bucket.empty:
            continue
        take = bucket.sample(n=min(target, len(bucket)), random_state=seed)
        sampled.append(take)
        used_indexes.update(take.index.tolist())

    if not sampled:
        return result.head(0).copy()

    out = pd.concat(sampled, axis=0).drop_duplicates()
    sort_cols = [c for c in ["Verification_Status", "Rule_ID", "Company"] if c in out.columns]
    if sort_cols:
        out = out.sort_values(sort_cols, kind="stable").copy()

    front = [
        col
        for col in [
            "State", "Company", "Street", "City", "ZIP", "Phone",
            "Rating", "Reviews", "Status", "Verification_Status",
            "Identity_Status", "Existence_Status", "Nail_Service_Status",
            "Evidence_Source_Count", "Strong_Evidence_Count", "Primary_Source",
            "Primary_Source_Tier", "Primary_Source_URL", "Verification_Reason",
            "Rule_ID", "Candidate_Action", "Auto_Action", "Decision", "Confidence",
            "Local_Signal", "Local_Score", "Risk_Flags", "Identity_Collision",
            "Shared_Address_Count", "Exact_Record_Duplicate_Count",
        ]
        if col in out.columns
    ]

    out = out[front].copy()
    out["Research_Label"] = ""
    out["Research_Source_URL"] = ""
    out["Research_Notes"] = ""
    return out.reset_index(drop=True)
