from __future__ import annotations

import argparse
from collections import defaultdict

import pandas as pd

from nailverifier_v3.engine import ENGINE_VERSION, verify_dataframe
from nailverifier_v3.policy import (
    MIN_KEEP_PRECISION,
    MIN_REMOVE_PRECISION,
    MIN_RULE_SAMPLES_KEEP,
    MIN_RULE_SAMPLES_REMOVE,
)


def action_to_label(action: str) -> str:
    if action == "KEEP":
        return "NAIL"
    if action == "REMOVE":
        return "NOT_NAIL"
    return "ABSTAIN"


def ratio(a: int, b: int) -> float:
    return a / b if b else 0.0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", default="benchmarks/sd_gold.csv")
    parser.add_argument("--with-osm", action="store_true")
    args = parser.parse_args()

    gold = pd.read_csv(args.file, dtype=str, keep_default_na=False)
    metadata = {"Expected"}
    metadata.update(col for col in gold.columns if col.startswith("Gold_"))
    input_columns = [col for col in gold.columns if col not in metadata]

    checked = verify_dataframe(
        gold[input_columns],
        use_osm=args.with_osm,
        force_refresh=True,
    )
    checked["Expected"] = gold["Expected"].values
    checked["Candidate_Prediction"] = checked["Candidate_Action"].map(action_to_label)
    checked["Auto_Prediction"] = checked["Auto_Action"].map(action_to_label)

    print(
        checked[
            [
                "Company",
                "Expected",
                "Rule_ID",
                "Decision",
                "Candidate_Action",
                "Auto_Action",
                "Policy_Status",
                "Reason",
            ]
        ].to_string(index=False)
    )

    print()
    print("Engine:", ENGINE_VERSION)
    print("Profile:", "TEST_WITH_OSM" if args.with_osm else "PRODUCTION_OFFICIAL_BATCH")
    print("Gold rows:", len(checked))

    print()
    print("Candidate rule report:")
    candidates = checked[checked["Candidate_Prediction"] != "ABSTAIN"].copy()
    if candidates.empty:
        print("No KEEP/REMOVE candidate rules found.")
    else:
        for (rule_id, action), group in candidates.groupby(["Rule_ID", "Candidate_Action"]):
            expected_label = action_to_label(action)
            correct = int((group["Expected"] == expected_label).sum())
            n = len(group)
            precision = ratio(correct, n)
            false_remove = int(((group["Candidate_Action"] == "REMOVE") & (group["Expected"] == "NAIL")).sum())

            if action == "KEEP":
                min_n = MIN_RULE_SAMPLES_KEEP
                threshold = MIN_KEEP_PRECISION
            else:
                min_n = MIN_RULE_SAMPLES_REMOVE
                threshold = MIN_REMOVE_PRECISION

            eligible = n >= min_n and precision >= threshold and false_remove == 0
            print(
                "%s / %s: n=%d precision=%.2f%% false_remove=%d -> %s"
                % (
                    rule_id,
                    action,
                    n,
                    precision * 100,
                    false_remove,
                    "ELIGIBLE" if eligible else "NEEDS_MORE_VALIDATION",
                )
            )

    auto = checked[checked["Auto_Prediction"] != "ABSTAIN"].copy()
    auto_correct = int((auto["Auto_Prediction"] == auto["Expected"]).sum()) if len(auto) else 0
    print()
    print("Actual auto-actions enabled by policy:", len(auto))
    print("Actual auto-action precision: %.2f%%" % (ratio(auto_correct, len(auto)) * 100))

    false_auto_remove = int(
        ((checked["Auto_Action"] == "REMOVE") & (checked["Expected"] == "NAIL")).sum()
    )
    print("False automatic removals:", false_auto_remove)

    if false_auto_remove:
        print("GATE: FAIL — automatic false removal detected.")
    elif len(auto) == 0:
        print("GATE: SAFE BUT NOT ENABLED — no benchmark-validated local auto rules yet.")
    else:
        print("GATE: PARTIAL — only policy-enabled rules are active; inspect per-rule report.")


if __name__ == "__main__":
    main()
