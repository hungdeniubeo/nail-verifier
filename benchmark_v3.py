from __future__ import annotations

import argparse

import pandas as pd

from nailverifier_v3.engine import verify_dataframe


def predicted_label(decision: str) -> str:
    if decision in {"VERIFIED_NAIL", "LIKELY_NAIL"}:
        return "NAIL"
    if decision in {"VERIFIED_NOT_NAIL", "LIKELY_NOT_NAIL"}:
        return "NOT_NAIL"
    return "ABSTAIN"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", default="benchmarks/sd_gold.csv")
    parser.add_argument("--no-osm", action="store_true")
    args = parser.parse_args()

    gold = pd.read_csv(args.file, dtype=str, keep_default_na=False)
    input_columns = [c for c in gold.columns if c not in {"Expected", "Gold_Source_URL", "Gold_Notes"}]
    checked = verify_dataframe(gold[input_columns], use_osm=not args.no_osm, force_refresh=True)
    checked["Expected"] = gold["Expected"].values
    checked["Predicted_Label"] = checked["Decision"].map(predicted_label)

    decided = checked[checked["Predicted_Label"] != "ABSTAIN"].copy()
    correct = int((decided["Predicted_Label"] == decided["Expected"]).sum()) if len(decided) else 0
    precision = correct / len(decided) if len(decided) else 0.0
    coverage = len(decided) / len(checked) if len(checked) else 0.0

    print(checked[["Company", "Expected", "Decision", "Confidence", "Predicted_Label", "Reason"]].to_string(index=False))
    print()
    print("Gold rows:", len(checked))
    print("Auto-decided:", len(decided))
    print("Coverage: %.1f%%" % (coverage * 100))
    print("Precision among auto-decisions: %.1f%%" % (precision * 100))

    if len(checked) < 20:
        print("GATE: NOT READY — gold set is still too small (<20 rows). Expand benchmark before production gating.")
    elif precision < 0.98:
        print("GATE: FAIL — precision target is 98%+.")
    else:
        print("GATE: PASS — benchmark precision target met.")


if __name__ == "__main__":
    main()
