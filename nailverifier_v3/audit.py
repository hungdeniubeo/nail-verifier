from __future__ import annotations

from typing import List

import pandas as pd

REQUIRED = {
    "Verification_Status",
    "Auto_Action",
    "Identity_Collision",
    "Evidence_Source_Count",
    "Primary_Source_URL",
}


def audit_verification_output(df: pd.DataFrame) -> List[str]:
    missing = REQUIRED - set(df.columns)
    if missing:
        return ["Missing required v3.7 audit columns: %s" % ", ".join(sorted(missing))]

    errors: List[str] = []
    bad_remove = df[(df["Auto_Action"] == "REMOVE") & (df["Verification_Status"] != "VERIFIED_NOT_NAIL")]
    if not bad_remove.empty:
        errors.append(f"{len(bad_remove)} Auto REMOVE row(s) are not VERIFIED_NOT_NAIL.")

    bad_keep = df[(df["Auto_Action"] == "KEEP") & (df["Verification_Status"] != "VERIFIED_NAIL")]
    if not bad_keep.empty:
        errors.append(f"{len(bad_keep)} Auto KEEP row(s) are not VERIFIED_NAIL.")

    collision_auto = df[(df["Identity_Collision"] == "YES") & df["Auto_Action"].isin(["KEEP", "REMOVE"])]
    if not collision_auto.empty:
        errors.append(f"{len(collision_auto)} identity collision row(s) still have an automatic action.")

    verified = df[df["Verification_Status"].isin(["VERIFIED_NAIL", "VERIFIED_NOT_NAIL"])]
    counts = pd.to_numeric(verified["Evidence_Source_Count"], errors="coerce").fillna(0)
    if int((counts < 1).sum()):
        errors.append(f"{int((counts < 1).sum())} VERIFIED row(s) have zero evidence sources.")

    blank_url = verified["Primary_Source_URL"].astype(str).str.strip().eq("")
    if int(blank_url.sum()):
        errors.append(f"{int(blank_url.sum())} VERIFIED row(s) have a blank primary source URL.")

    return errors
