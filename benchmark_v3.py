from __future__ import annotations

import argparse
import math

import pandas as pd

from nailverifier_v3.calibration import load_gold_files
from nailverifier_v3.engine import ENGINE_VERSION, verify_dataframe
from nailverifier_v3.policy import (
    MIN_KEEP_PRECISION,
    MIN_REMOVE_PRECISION,
    MIN_RULE_SAMPLES_KEEP,
    MIN_RULE_SAMPLES_REMOVE,
    MIN_WILSON_LOWER_BOUND,
)


def action_to_label(action: str) -> str:
    if action == "KEEP":
        return "NAIL"
    if action == "REMOVE":
        return "NOT_NAIL"
    return "ABSTAIN"


def ratio(a: int, b: int) -> float:
    return a / b if b else 0.0


def wilson_lower_bound(correct: int, total: int, z: float = 1.96) -> float:
    if total <= 0:
        return 0.0
    p = correct / total
    z2 = z * z
    denominator = 1.0 + z2 / total
    center = p + z2 / (2.0 * total)
    margin = z * math.sqrt((p * (1.0 - p) + z2 / (4.0 * total)) / total)
    return max(0.0, (center - margin) / denominator)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--file",
        action="append",
        default=None,
        help="Gold CSV. Repeat --file to combine multiple calibration files.",
    )
    parser.add_argument("--with-osm", action="store_true")
    args = parser.parse_args()

    gold_files = args.file or ["benchmarks/sd_gold.csv"]
    gold = load_gold_files(gold_files)
    expected_col = "Gold_Label" if "Gold_Label" in gold.columns else "Expected"
    if expected_col not in gold.columns:
        raise ValueError("Benchmark CSV needs Expected or Gold_Label.")

    metadata = {"Expected", "Gold_Label"}
    metadata.update(col for col in gold.columns if col.startswith("Gold_"))
    input_columns = [col for col in gold.columns if col not in metadata]

    checked = verify_dataframe(
        gold[input_columns],
        use_osm=args.with_osm,
        force_refresh=True,
    )
    checked["Expected"] = gold[expected_col].astype(str).str.upper().values
    checked["Gold_File"] = gold["Gold_File"].values
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
                "Gold_File",
                "Reason",
            ]
        ].to_string(index=False)
    )

    print()
    print("Engine:", ENGINE_VERSION)
    print("Profile:", "TEST_WITH_OSM" if args.with_osm else "PRODUCTION_OFFICIAL_BATCH")
    print("Gold files:", ", ".join(gold_files))
    print("Gold rows:", len(checked))

    print()
    print("Candidate rule report:")
    candidates = checked[checked["Candidate_Prediction"] != "ABSTAIN"].copy()
    if candidates.empty:
        print("No KEEP/REMOVE candidate rules found.")
    else:
        for (rule_id, action), group in candidates.groupby(["Rule_ID", "Candidate_Action"]):
            labeled = group[group["Expected"].isin({"NAIL", "NOT_NAIL"})].copy()
            expected_label = action_to_label(action)
            correct = int((labeled["Expected"] == expected_label).sum())
            n = len(labeled)
            precision = ratio(correct, n)
            lower = wilson_lower_bound(correct, n)
            false_remove = int(
                ((labeled["Candidate_Action"] == "REMOVE") & (labeled["Expected"] == "NAIL")).sum()
            )

            if action == "KEEP":
                min_n = MIN_RULE_SAMPLES_KEEP
                threshold = MIN_KEEP_PRECISION
            else:
                min_n = MIN_RULE_SAMPLES_REMOVE
                threshold = MIN_REMOVE_PRECISION

            empirical_ok = n >= min_n and precision >= threshold and false_remove == 0
            statistical_ok = lower >= MIN_WILSON_LOWER_BOUND
            eligible = empirical_ok and statistical_ok

            print(
                "%s / %s: labeled=%d precision=%.2f%% Wilson95LB=%.2f%% false_remove=%d -> %s"
                % (
                    rule_id,
                    action,
                    n,
                    precision * 100,
                    lower * 100,
                    false_remove,
                    "ELIGIBLE" if eligible else (
                        "EMPIRICALLY_CLEAN_BUT_MORE_SAMPLES_NEEDED" if empirical_ok else "NEEDS_MORE_VALIDATION"
                    ),
                )
            )

    auto = checked[checked["Auto_Prediction"] != "ABSTAIN"].copy()
    auto_labeled = auto[auto["Expected"].isin({"NAIL", "NOT_NAIL"})].copy()
    auto_correct = int((auto_labeled["Auto_Prediction"] == auto_labeled["Expected"]).sum()) if len(auto_labeled) else 0
    print()
    print("Actual auto-actions enabled by policy:", len(auto))
    print("Actual labeled auto-action precision: %.2f%%" % (ratio(auto_correct, len(auto_labeled)) * 100))

    false_auto_remove = int(
        ((checked["Auto_Action"] == "REMOVE") & (checked["Expected"] == "NAIL")).sum()
    )
    print("False automatic removals:", false_auto_remove)

    if false_auto_remove:
        print("GATE: FAIL — automatic false removal detected.")
    elif len(auto) == 0:
        print("GATE: SAFE BUT NOT ENABLED — local rules remain shadow-only.")
    else:
        print("GATE: PARTIAL — only policy-enabled rules are active; inspect per-rule report.")


if __name__ == "__main__":
    main()
