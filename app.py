from __future__ import annotations

import io

import pandas as pd
import streamlit as st

from nailverifier_v3.audit import audit_verification_output
from nailverifier_v3.engine import ENGINE_VERSION, OFFICIAL_ADAPTERS, verify_dataframe
from nailverifier_v3.normalize import detect_columns, validate_mapping
from nailverifier_v3.sampling import make_validation_sample

st.set_page_config(page_title="Nail Verifier — Precision v3.7", page_icon="💅", layout="wide")

st.title("Nail Verifier — Precision v3.7 Multi-Source Verification")
st.caption(
    "Mục tiêu: tìm business trong NailMap nhưng thực tế KHÔNG phải tiệm nail bằng evidence riêng từng business. "
    "Tên business/rule chỉ là gợi ý; không còn được coi là bằng chứng VERIFIED."
)
st.caption(
    "Auto REMOVE chỉ khi VERIFIED_NOT_NAIL; Auto KEEP chỉ khi VERIFIED_NAIL. "
    "Identity collision hoặc conflict evidence luôn ép về REVIEW."
)

with st.expander("V3.7 xác minh như thế nào?", expanded=False):
    st.markdown(
        """
**Multi-stage evidence-first**
1. Chuẩn hóa identity: name, full address, city/state/ZIP, phone.
2. Match evidence vào đúng business.
3. Kiểm tra existence/status.
4. Phân loại category.
5. Kiểm tra nail service trực tiếp.
6. Cross-check nhiều nguồn và phát hiện conflict.
7. Consensus mới quyết định VERIFIED / LIKELY / UNKNOWN.

**Source gate**
- Tier A: official/state/business website/official booking/store locator.
- Tier B: BBB/Chamber/Apple Maps/established local directory.
- Tier C: secondary directories.
- Tier D: NailMap/name/rule heuristic.

Một Tier B/C đơn lẻ không đủ VERIFIED. Tier D không bao giờ tạo VERIFIED.
"""
    )

uploaded = st.file_uploader("1. Chọn CSV", type=["csv"])

if uploaded is not None:
    try:
        df = pd.read_csv(io.BytesIO(uploaded.getvalue()), dtype=str, keep_default_na=False)
        mapping = detect_columns(df.columns)
        validate_mapping(mapping)
    except Exception as exc:
        st.error("Không đọc được CSV: %s" % exc)
        st.stop()

    state_col = mapping.get("state")
    states = sorted({str(x).strip().upper() for x in df[state_col].tolist() if str(x).strip()}) if state_col else []
    unsupported = [state for state in states if state not in set(OFFICIAL_ADAPTERS)]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Rows", f"{len(df):,}")
    c2.metric("States", len(states) if states else 1)
    c3.metric("Policy", "Evidence-first")
    c4.metric("Engine", ENGINE_VERSION)

    if unsupported:
        st.warning("Bang chưa có official adapter: %s. Registry evidence vẫn có thể dùng khi exact identity khớp." % ", ".join(unsupported))

    st.dataframe(df.head(10), use_container_width=True, hide_index=True)

    mode = st.radio(
        "2. Chọn kiểu chạy",
        ["Test 20 dòng", "Test 50 dòng", "Chạy toàn bộ CSV — evidence-first production candidate"],
    )
    if mode.startswith("Test 20"):
        limit, allow_osm = 20, True
    elif mode.startswith("Test 50"):
        limit, allow_osm = 50, True
    else:
        limit, allow_osm = None, False

    use_osm = st.checkbox("Dùng OpenStreetMap/Nominatim cho test nhỏ", value=True) if allow_osm else False
    if not allow_osm:
        st.info("Bulk run: public Nominatim tắt. Stored registry + official state source + local heuristics vẫn chạy.")

    force_refresh = st.checkbox("Bỏ qua verification cache", value=False, help="Registry digest nằm trong cache version; đổi registry sẽ tự invalid cache cũ.")

    if st.button("3. Chạy Precision v3.7", type="primary", use_container_width=True):
        progress = st.progress(0)
        progress_text = st.empty()

        def update_progress(done: int, total: int, name: str) -> None:
            progress.progress(done / max(total, 1))
            progress_text.caption(f"{done}/{total} — {name}")

        with st.spinner("Đang xác minh evidence..."):
            result = verify_dataframe(df, limit=limit, progress=update_progress, use_osm=use_osm, force_refresh=force_refresh)

        st.session_state["v37_result"] = result
        st.session_state["v37_source"] = uploaded.name
        progress_text.success("Xong")

if "v37_result" in st.session_state:
    result = st.session_state["v37_result"]
    st.divider()
    st.subheader("Kết quả Precision v3.7")

    statuses = result["Verification_Status"].value_counts(dropna=False).to_dict()
    verified_nail = int(statuses.get("VERIFIED_NAIL", 0))
    verified_not_nail = int(statuses.get("VERIFIED_NOT_NAIL", 0))
    conflicting = int(statuses.get("CONFLICTING_EVIDENCE", 0))
    likely_unverified = int(result["Verification_Status"].isin(["LIKELY_NAIL", "LIKELY_NOT_NAIL", "UNKNOWN"]).sum())
    auto_remove = int((result["Auto_Action"] == "REMOVE").sum())
    review = int((result["Auto_Action"] == "REVIEW").sum())

    cols = st.columns(6)
    cols[0].metric("Verified NAIL", verified_nail)
    cols[1].metric("Verified NOT_NAIL", verified_not_nail)
    cols[2].metric("Likely / Unverified", likely_unverified)
    cols[3].metric("Conflicting", conflicting)
    cols[4].metric("Auto REMOVE", auto_remove)
    cols[5].metric("Review", review)

    collisions = int((result["Identity_Collision"] == "YES").sum())
    source_errors = int(result["Source_Errors"].astype(str).str.strip().ne("").sum())
    st.caption(f"Identity collision rows: {collisions} · Source errors: {source_errors}")

    important = [
        col for col in [
            "State", "Company", "Street", "City", "ZIP", "Phone",
            "Verification_Status", "Identity_Status", "Existence_Status", "Nail_Service_Status",
            "Evidence_Source_Count", "Strong_Evidence_Count", "Evidence_Agrees", "Evidence_Conflicts",
            "Primary_Source", "Primary_Source_Tier", "Primary_Source_URL", "Verification_Reason",
            "Identity_Collision", "Collision_Group_Size", "Collision_Names",
            "Auto_Action", "Policy_Status", "Candidate_Action", "Rule_ID", "Decision",
            "Normalized_Street", "Normalized_City", "Normalized_ZIP", "Normalized_Phone",
            "Verification_Evidence", "Source_Errors", "Cache_Hit",
        ] if col in result.columns
    ]
    st.dataframe(result[important], use_container_width=True, hide_index=True)

    audit_errors = audit_verification_output(result)
    if audit_errors:
        st.error("Production safety audit FAILED. Không cho tải production CSV cho đến khi sửa xong.")
        for error in audit_errors:
            st.write("- " + error)
    else:
        st.success("Production safety audit passed: mọi Auto KEEP/REMOVE đều có VERIFIED evidence phù hợp.")
        source_name = st.session_state.get("v37_source", "nail-map.csv")
        base_name = source_name.rsplit(".", 1)[0]
        st.download_button(
            "Tải CSV Precision v3.7",
            data=result.to_csv(index=False).encode("utf-8-sig"),
            file_name=base_name + "-precision-v37.csv",
            mime="text/csv",
            type="primary",
            use_container_width=True,
        )

    try:
        sample = make_validation_sample(result)
    except Exception as exc:
        st.warning("Chưa tạo được research sample: %s" % exc)
        sample = None

    if sample is not None and not sample.empty:
        source_name = st.session_state.get("v37_source", "nail-map.csv")
        base_name = source_name.rsplit(".", 1)[0]
        st.download_button(
            "Tải unresolved research sample",
            data=sample.to_csv(index=False).encode("utf-8-sig"),
            file_name=base_name + "-research-sample-v37.csv",
            mime="text/csv",
            use_container_width=True,
        )
        st.caption("Sample ưu tiên conflict, beauty/hair/spa ambiguous, UNKNOWN và LIKELY chưa đủ evidence.")
