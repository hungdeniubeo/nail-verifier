from __future__ import annotations

import pandas as pd

from nailverifier_v3.calibration import evaluate_gold


def test_evaluate_gold_excludes_unknown_and_reports_false_remove():
    df = pd.DataFrame(
        [
            {
                "Rule_ID": "R_NAIL_EXPLICIT_STRONG",
                "Expected": "NAIL",
                "Candidate_Action": "KEEP",
            },
            {
                "Rule_ID": "R_NAIL_EXPLICIT_STRONG",
                "Expected": "UNKNOWN",
                "Candidate_Action": "KEEP",
            },
            {
                "Rule_ID": "R_NON_NAIL_CATEGORY_STRONG",
                "Expected": "NOT_NAIL",
                "Candidate_Action": "REMOVE",
            },
            {
                "Rule_ID": "R_NON_NAIL_CATEGORY_STRONG",
                "Expected": "NAIL",
                "Candidate_Action": "REMOVE",
            },
        ]
    )

    report = evaluate_gold(df)
    keep = report["R_NAIL_EXPLICIT_STRONG"]
    remove = report["R_NON_NAIL_CATEGORY_STRONG"]

    assert keep["n"] == 1
    assert keep["correct"] == 1
    assert keep["precision"] == 1.0
    assert remove["n"] == 2
    assert remove["correct"] == 1
    assert remove["false_remove"] == 1
