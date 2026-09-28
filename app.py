from __future__ import annotations

import io

import pandas as pd
import streamlit as st

from nailverifier_v3.engine import ENGINE_VERSION, OFFICIAL_ADAPTERS, verify_dataframe
from nailverifier_v3.normalize import detect_columns, validate_mapping
from nailverifier_v3.sampling import make_validation_sample

st.set_page_config(page_title="Nail Verifier — Precision v3.4.1", page_icon="💅", layout="wide")

st.title("Nail Verifier — Precision v3.4.1 Production Candidate")
st.caption(
    "South Dakota: chỉ R_NAIL_EXPLICIT_STRONG được phép Auto KEEP sau calibration. "
    "Identity collision guard sẽ chặn auto-action nếu cùng phone + cùng base address xuất hiện dưới nhiều tên business."
)
st.caption(
    "Auto REMOVE vẫn bị khóa. Bulk run dùng official batch + calibrated local policy + SQLite cache; public Nominatim tự tắt."
)

with st.expander("V3.4.1 thêm gì?", expanded=False):
    st.markdown(
        """
**Được bật ở South Dakota**
- `R_NAIL_EXPLICIT_STRONG` → `Auto_Action = KEEP`.
- Rule yêu cầu tên nail rõ ràng + OPERATIONAL + location + phone + >=3 reviews.
- Calibration hiện có 74/74 case được gắn nhãn độc lập là nail; Wilson 95% lower bound khoảng 95.06%.

**Safety guard mới**
- Cùng normalized phone + cùng base address nhưng khác business name → `Identity_Collision = YES`.
- Nếu row đó đang `Auto KEEP/REMOVE`, v3.4.1 ép về `REVIEW` với `Policy_Status = IDENTITY_COLLISION_REVIEW`.
- Cùng phone nhưng khác địa chỉ không bị coi là collision.
- Exact duplicate cùng tên được báo bằng `Exact_Record_Duplicate_Count`, không bị xem là identity collision.
- Output có thêm `Normalized_Street`, `Normalized_City`, `Normalized_ZIP`, `Normalized_Phone`.

**Vẫn bị khóa**
- `R_NON_NAIL_CATEGORY_STRONG` dù 35/35 case kiểm tra là non-nail, vì Wilson lower bound chỉ khoảng 90.11% → vẫn `REVIEW`, không auto-remove.
- `R_NAIL_EXPLICIT_ADDRESS_STRONG`, beauty ambiguous, weak/styling hint, UNKNOWN → `REVIEW`.
- `Nail Supply / Nail Academy / Nail Products / Nail Wholesale...` → conflict guard, luôn `REVIEW`.
- Các bang ngoài SD không được dùng auto-policy của SD.

Các tỷ lệ trên là kết quả calibration của mẫu đã kiểm tra, không phải bảo đảm 100% ngoài thực tế.
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
    states = sorted(
        {str(x).strip().upper() for x in df[state_col].tolist() if str(x).strip()}
    ) if state_col else []

    official_states = set(OFFICIAL_ADAPTERS.keys())
    unsupported = [state for state in states if state not in official_states]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Rows", f"{len(df):,}")
    c2.metric("States", len(states) if states else 1)
    c3.metric("Auto-policy", "SD KEEP v1 + collision guard")
    c4.metric("Engine", ENGINE_VERSION)

    if unsupported:
        st.warning(
            "Bang chưa calibrated: %s. SD auto-rule sẽ không áp dụng cho các bang này."
            % ", ".join(unsupported)
        )

    st.dataframe(df.head(10), use_container_width=True, hide_index=True)

    mode = st.radio(
        "2. Chọn kiểu chạy",
        [
            "Test 20 dòng",
            "Test 50 dòng",
            "Chạy toàn bộ CSV — SD production candidate",
        ],
        horizontal=False,
    )

    if mode.startswith("Test 20"):
        limit = 20
        allow_osm = True
    elif mode.startswith("Test 50"):
        limit = 50
        allow_osm = True
    else:
        limit = None
        allow_osm = False

    if allow_osm:
        use_osm = st.checkbox(
            "Dùng OpenStreetMap/Nominatim cho test nhỏ",
            value=True,
            help="Chỉ dùng cho test nhỏ; bulk run không dùng public Nominatim.",
        )
    else:
        use_osm = False
        st.info(
            "Bulk run: Nominatim public đã tắt. Auto KEEP chỉ áp dụng cho SD strong-nail rule và sẽ bị collision guard chặn khi identity không rõ."
        )

    force_refresh = st.checkbox(
        "Bỏ qua verification cache",
        value=False,
        help="V3.4.1 có engine version mới nên verification cache v3.4 không bị dùng nhầm.",
    )

    if st.button("3. Chạy Precision v3.4.1", type="primary", use_container_width=True):
        progress = st.progress(0)
        progress_text = st.empty()

        def update_progress(done: int, total: int, name: str) -> None:
            progress.progress(done / max(total, 1))
            progress_text.caption(f"{done}/{total} — {name}")

        with st.spinner("Đang xác minh..."):
            result = verify_dataframe(
                df,
                limit=limit,
                progress=update_progress,
                use_osm=use_osm,
                force_refresh=force_refresh,
            )

        st.session_state["v341_result"] = result
        st.session_state["v341_source"] = uploaded.name
        st.session_state["v341_mode"] = mode
        progress_text.success("Xong")

if "v341_result" in st.session_state:
    result = st.session_state["v341_result"]
    st.divider()
    st.subheader("Kết quả Precision v3.4.1")

    decisions = result["Decision"].value_counts(dropna=False).to_dict()
    candidate_keep = int((result["Candidate_Action"] == "KEEP").sum())
    candidate_remove = int((result["Candidate_Action"] == "REMOVE").sum())
    auto_keep = int((result["Auto_Action"] == "KEEP").sum())
    auto_remove = int((result["Auto_Action"] == "REMOVE").sum())
    official_matches = int(result["Official_Source"].astype(str).str.strip().ne("").sum())
    source_errors = int(result["Source_Errors"].astype(str).str.strip().ne("").sum())
    collisions = int((result["Identity_Collision"] == "YES").sum())
    collision_blocks = int((result["Policy_Status"] == "IDENTITY_COLLISION_REVIEW").sum())

    cols = st.columns(7)
    cols[0].metric("Checked", len(result))
    cols[1].metric("Candidate KEEP", candidate_keep)
    cols[2].metric("Candidate REMOVE", candidate_remove)
    cols[3].metric("Auto KEEP", auto_keep)
    cols[4].metric("Auto REMOVE", auto_remove)
    cols[5].metric("Collision rows", collisions)
    cols[6].metric("Collision blocks", collision_blocks)

    st.markdown(
        "LIKELY_NAIL: %d · LIKELY_NOT_NAIL: %d · REVIEW: %d · Official matches: %d · Source errors: %d"
        % (
            int(decisions.get("LIKELY_NAIL", 0)),
            int(decisions.get("LIKELY_NOT_NAIL", 0)),
            int(decisions.get("REVIEW", 0)),
            official_matches,
            source_errors,
        )
    )

    if source_errors:
        st.error("Có source error. Không dùng row lỗi nguồn cho production filtering.")

    enabled = int((result["Policy_Status"] == "BENCHMARK_VALIDATED_RULE").sum())
    gated = int((result["Policy_Status"] == "CANDIDATE_NEEDS_BENCHMARK").sum())
    st.info(
        "Rows được calibrated local policy tự động KEEP: %d · Candidate rows vẫn bị gate: %d · Auto-action bị collision guard chặn: %d."
        % (enabled, gated, collision_blocks)
    )

    if auto_remove:
        st.error(
            "V3.4.1 SD policy không dự kiến auto-remove bằng local rule. Hãy kiểm tra các Auto REMOVE trước khi dùng file."
        )

    if collision_blocks:
        st.warning(
            "%d row có identity collision từng đủ điều kiện auto-action nhưng đã bị ép về REVIEW." % collision_blocks
        )

    important = [
        col
        for col in [
            "State", "Company", "Street", "City", "ZIP", "Phone",
            "Normalized_Street", "Normalized_City", "Normalized_ZIP", "Normalized_Phone",
            "Status", "Business_Exists", "Nail_Service", "Decision", "Confidence",
            "Rule_ID", "Candidate_Action", "Auto_Action", "Policy_Status",
            "Policy_Profile", "Identity_Collision", "Collision_Group_Size", "Collision_Names",
            "Local_Signal", "Local_Score", "Risk_Flags", "Shared_Address_Count",
            "Exact_Record_Duplicate_Count", "Evidence_Tier", "Official_Matched_Name",
            "Official_Matched_Address", "Official_License_Type", "Reason",
            "Source_Errors", "Cache_Hit",
        ]
        if col in result.columns
    ]
    st.dataframe(result[important], use_container_width=True, hide_index=True)

    source_name = st.session_state.get("v341_source", "nail-map.csv")
    base_name = source_name.rsplit(".", 1)[0]

    st.download_button(
        "Tải CSV Precision v3.4.1",
        data=result.to_csv(index=False).encode("utf-8-sig"),
        file_name=base_name + "-precision-v341.csv",
        mime="text/csv",
        type="primary",
        use_container_width=True,
    )

    try:
        sample = make_validation_sample(result)
    except Exception as exc:
        st.warning("Chưa tạo được validation sample: %s" % exc)
        sample = None

    if sample is not None and not sample.empty:
        st.download_button(
            "Tải validation sample tiếp theo",
            data=sample.to_csv(index=False).encode("utf-8-sig"),
            file_name=base_name + "-validation-sample-v341.csv",
            mime="text/csv",
            use_container_width=True,
        )
        st.caption("Sample tiếp theo dùng để tăng confidence cho các rule vẫn REVIEW, đặc biệt REMOVE.")
