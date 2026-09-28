from __future__ import annotations

import argparse

import pandas as pd

from nailverifier_v3.calibration import evaluate_gold
from nailverifier_v3.policy import (
    MIN_KEEP_PRECISION,
    MIN_REMOVE_PRECISION,
    MIN_RULE_SAMPLES_KEEP,
    MIN_RULE_SAMPLES_REMOVE,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", default="benchmarks/sd_rule_gold_v33.csv")
    args = parser.parse_args()

    gold = pd.read_csv(args.file, dtype=str, keep_default_na=False)
    report = evaluate_gold(gold)

    print("Gold file:", args.file)
    print("Rows:", len(gold))
    print()

    all_eligible = True
    for rule_id in sorted(report):
        item = report[rule_id]
        action = item["action"]
        n = item["n"]
        precision = item["precision"]
        false_remove = item["false_remove"]

        if action == "KEEP":
            min_n = MIN_RULE_SAMPLES_KEEP
            threshold = MIN_KEEP_PRECISION
        elif action == "REMOVE":
            min_n = MIN_RULE_SAMPLES_REMOVE
            threshold = MIN_REMOVE_PRECISION
        else:
            min_n = 10**9
            threshold = 1.0

        eligible = n >= min_n and precision >= threshold and false_remove == 0
        all_eligible = all_eligible and eligible

        print(
            "%s | %s | n=%d | correct=%d | empirical_precision=%.2f%% | false_remove=%d | %s"
            % (
                rule_id,
                action,
                n,
                item["correct"],
                precision * 100,
                false_remove,
                "ELIGIBLE" if eligible else "NOT_ELIGIBLE",
            )
        )

    print()
    if all_eligible:
        print("CALIBRATION: PASS for the rules represented in this gold file.")
    else:
        print("CALIBRATION: FAIL / NEEDS MORE VALIDATION.")

    print(
        "Note: empirical precision on a finite checked sample is not a guarantee of real-world 99%+ accuracy."
    )


if __name__ == "__main__":
    main()
