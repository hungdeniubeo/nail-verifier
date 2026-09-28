from __future__ import annotations

from typing import Any, Dict

import pandas as pd


def evaluate_gold(df: pd.DataFrame) -> Dict[str, Dict[str, Any]]:
    required = {"Rule_ID", "Expected", "Candidate_Action"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError("Missing required columns: %s" % ", ".join(sorted(missing)))

    # UNKNOWN is useful for auditing ambiguous rows, but it must not be counted
    # as either a correct or incorrect classification in precision metrics.
    known = df[df["Expected"].isin(["NAIL", "NOT_NAIL"])].copy()
    report: Dict[str, Dict[str, Any]] = {}

    for rule_id, group in known.groupby("Rule_ID"):
        actions = group["Candidate_Action"].dropna().astype(str)
        action = actions.mode().iloc[0] if len(actions) else "REVIEW"

        if action == "KEEP":
            expected_label = "NAIL"
        elif action == "REMOVE":
            expected_label = "NOT_NAIL"
        else:
            expected_label = "UNKNOWN"

        correct = int((group["Expected"] == expected_label).sum()) if expected_label != "UNKNOWN" else 0
        n = int(len(group))
        false_remove = int(
            ((group["Candidate_Action"] == "REMOVE") & (group["Expected"] == "NAIL")).sum()
        )

        report[str(rule_id)] = {
            "action": action,
            "n": n,
            "correct": correct,
            "precision": correct / n if n else 0.0,
            "false_remove": false_remove,
        }

    return report
