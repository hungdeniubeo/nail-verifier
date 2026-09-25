from __future__ import annotations

from typing import Dict, List, Optional

import pandas as pd

DEFAULT_TARGETS: Dict[str, int] = {
    "R_NAIL_EXPLICIT_STRONG": 25,
    "R_NAIL_EXPLICIT_ADDRESS_STRONG": 15,
    "R_NON_NAIL_CATEGORY_STRONG": 15,
    "R_NON_NAIL_CATEGORY_ADDRESS_STRONG": 10,
    "R_BEAUTY_AMBIGUOUS": 20,
    "R_NAIL_EXPLICIT_WEAK": 10,
    "R_NAIL_STYLING_HINT": 10,
    "R_UNKNOWN": 10,
}


def make_validation_sample(
    result: pd.DataFrame,
    seed: int = 320,
    targets: Optional[Dict[str, int]] = None,
) -> pd.DataFrame:
    targets = targets or DEFAULT_TARGETS
    if "Rule_ID" not in result.columns:
        raise ValueError("Result must contain Rule_ID. Run with Precision v3.2 first.")

    sampled: List[pd.DataFrame] = []
    used_indexes = set()

    for rule_id, target in targets.items():
        bucket = result[result["Rule_ID"] == rule_id]
        if bucket.empty:
            continue
        take = bucket.sample(n=min(target, len(bucket)), random_state=seed)
        sampled.append(take)
        used_indexes.update(take.index.tolist())

    if "Official_Source" in result.columns:
        official = result[
            result["Official_Source"].astype(str).str.strip().ne("")
            & ~result.index.isin(used_indexes)
        ]
        if not official.empty:
            sampled.append(official)

    if not sampled:
        return result.head(0).copy()

    out = pd.concat(sampled, axis=0).drop_duplicates()
    out = out.sort_values(["Rule_ID", "Company"], kind="stable").copy()

    front = [
        col
        for col in [
            "State", "Company", "Street", "City", "ZIP", "Phone",
            "Rating", "Reviews", "Status", "Rule_ID", "Candidate_Action",
            "Decision", "Confidence", "Local_Signal", "Local_Score",
            "Risk_Flags", "Official_Source", "Official_Matched_Name",
            "Official_Matched_Address", "Official_License_Type",
            "Shared_Address_Count", "Exact_Record_Duplicate_Count",
        ]
        if col in out.columns
    ]

    out = out[front].copy()
    out["Gold_Label"] = ""
    out["Gold_Source_URL"] = ""
    out["Gold_Notes"] = ""
    return out.reset_index(drop=True)
