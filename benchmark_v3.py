from __future__ import annotations

import argparse

import pandas as pd

from nailverifier_v3.engine import ENGINE_VERSION, verify_dataframe


def auto_prediction(auto_action: str) -> str:
    if auto_action == "KEEP":
        return "NAIL"
    if auto_action == "REMOVE":
        return "NOT_NAIL"
    return "ABSTAIN"


def safe_ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", default="benchmarks/sd_gold.csv")
    parser.add_argument("--no-osm", action="store_true")
    args = parser.parse_args()

    gold = pd.read_csv(args.file, dtype=str, keep_default_na=False)
    metadata = {"Expected"}
    metadata.update(col for col in gold.columns if col.startswith("Gold_"))
    input_columns = [col for col in gold.columns if col not in metadata]

    checked = verify_dataframe(
        gold[input_columns],
        use_osm=not args.no_osm,
        force_refresh=True,
    )
    checked["Expected"] = gold["Expected"].values
    checked["Auto_Prediction"] = checked["Auto_Action"].map(auto_prediction)

    auto = checked[checked["Auto_Prediction"] != "ABSTAIN"].copy()
    keeps = auto[auto["Auto_Action"] == "KEEP"].copy()
    removes = auto[auto["Auto_Action"] == "REMOVE"].copy()

    auto_correct = int((auto["Auto_Prediction"] == auto["Expected"]).sum())
    keep_correct = int((keeps["Expected"] == "NAIL").sum())
    remove_correct = int((removes["Expected"] == "NOT_NAIL").sum())
    false_removals = int((removes["Expected"] == "NAIL").sum())

    overall_precision = safe_ratio(auto_correct, len(auto))
    keep_precision = safe_ratio(keep_correct, len(keeps))
    remove_precision = safe_ratio(remove_correct, len(removes))
    coverage = safe_ratio(len(auto), len(checked))

    print(
        checked[
            [
                "Company",
                "Expected",
                "Decision",
                "Confidence",
                "Auto_Action",
                "Auto_Prediction",
                "Business_Exists",
                "Nail_Service",
                "Reason",
            ]
        ].to_string(index=False)
    )
    print()
    print("Engine:", ENGINE_VERSION)
    print("Gold rows:", len(checked))
    print("Auto-decided KEEP/REMOVE:", len(auto))
    print("KEEP decisions:", len(keeps))
    print("REMOVE decisions:", len(removes))
    print("Coverage: %.1f%%" % (coverage * 100))
    print("Overall auto precision: %.2f%%" % (overall_precision * 100))
    print("KEEP precision: %.2f%%" % (keep_precision * 100))
    print("REMOVE precision: %.2f%%" % (remove_precision * 100))
    print("False removals:", false_removals)

    failures = []
    if len(checked) < 20:
        failures.append("gold set must contain at least 20 manually verified rows")
    if int((gold["Expected"] == "NAIL").sum()) < 10:
        failures.append("gold set needs at least 10 NAIL rows")
    if int((gold["Expected"] == "NOT_NAIL").sum()) < 5:
        failures.append("gold set needs at least 5 NOT_NAIL rows")
    if len(keeps) < 5:
        failures.append("need at least 5 automatic KEEP decisions before production")
    if len(removes) < 3:
        failures.append("need at least 3 automatic REMOVE decisions before production")
    if keep_precision < 0.99:
        failures.append("KEEP precision must be >= 99%")
    if remove_precision < 0.995:
        failures.append("REMOVE precision must be >= 99.5%")
    if false_removals != 0:
        failures.append("false removals must be zero")

    if failures:
        print("GATE: FAIL / NOT PRODUCTION READY")
        for failure in failures:
            print(" -", failure)
    else:
        print("GATE: PASS — precision gate met for this state's gold set.")


if __name__ == "__main__":
    main()
