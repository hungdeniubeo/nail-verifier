from __future__ import annotations

import io

import pandas as pd
import streamlit as st

from nailverifier_v3.engine import ENGINE_VERSION, OFFICIAL_ADAPTERS, verify_dataframe
from nailverifier_v3.normalize import detect_columns, validate_mapping
from nailverifier_v3.sampling import make_validation_sample

st.set_page_config(page_title="Nail Verifier — Precision v3.3 Shadow", page_icon="💅", layout="wide")

st.title("Nail Verifier — Precision v3.3 Shadow Calibration")
st.caption(
    "Local KEEP/REMOVE rules are still SHADOW-ONLY. They can create Candidate_Action, but they do not auto KEEP/REMOVE until stronger calibration passes."
)
st.caption(
    "Official nail-specific state evidence may still auto KEEP. Bulk runs do not use public Nominatim."
)

with st.expander("V3.3 Shadow có gì mới?", expanded=False):
    st.markdown(
        """
- Candidate_Action và Auto_Action tiếp tục tách riêng.
- Local rule SD chưa được auto-enable dù sample hiện tại rất sạch.
- Benchmark v3.3 dùng thêm Wilson 95% lower confidence bound để tránh bật rule quá sớm chỉ vì sample nhỏ.
- `UNKNOWN` gold labels không bị tính như đúng/sai khi đo precision.
- `R_NAIL_NON_SERVICE_CONFLICT` chặn các tên kiểu Nail Supply / Nail Academy / Nail Products / Nail Wholesale khỏi Candidate KEEP.
- Official nail-specific current license vẫn là evidence mạnh nhất.
- Public OpenStreetMap/Nominatim tự tắt trong full/bulk run.

Mục tiêu hiện tại là mở rộng calibration, không phải tối đa hóa coverage bằng mọi giá.
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
    c3.metric("Official adapters", ", ".join(sorted(official_states)))
    c4.metric("Engine", ENGINE_VERSION)

    if unsupported:
        st.warning(
            "Chưa có official adapter cho: %s. Các bang này chỉ được local rule phân nhóm và vẫn REVIEW-only."
            % ", ".join(unsupported)
        )

    st.dataframe(df.head(10), use_container_width=True, hide_index=True)

    mode = st.radio(
        "2. Chọn kiểu chạy",
        [
            "Test 20 dòng",
            "Test 50 dòng",
            "Pilot toàn bộ CSV — shadow calibration",
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
            "Bulk pilot: public OpenStreetMap/Nominatim được tắt. Tool dùng official batch + local shadow rules + cache."
        )

    force_refresh = st.checkbox(
        "Bỏ qua verification cache",
        value=False,
        help="Chỉ bật khi cần refresh source."
    )

    if st.button("3. Chạy Precision v3.3 Shadow", type="primary", use_container_width=True):
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

        st.session_state["v33_result"] = result
        st.session_state["v33_source"] = uploaded.name
        st.session_state["v33_mode"] = mode
        progress_text.success("Xong")

if "v33_result" in st.session_state:
    result = st.session_state["v33_result"]
    st.divider()
    st.subheader("Kết quả Precision v3.3 Shadow")

    decisions = result["Decision"].value_counts(dropna=False).to_dict()
    candidate_keep = int((result["Candidate_Action"] == "KEEP").sum())
    candidate_remove = int((result["Candidate_Action"] == "REMOVE").sum())
    auto_keep = int((result["Auto_Action"] == "KEEP").sum())
    auto_remove = int((result["Auto_Action"] == "REMOVE").sum())
    official_matches = int(result["Official_Source"].astype(str).str.strip().ne("").sum())
    source_errors = int(result["Source_Errors"].astype(str).str.strip().ne("").sum())

    cols = st.columns(6)
    cols[0].metric("Checked", len(result))
    cols[1].metric("Candidate KEEP", candidate_keep)
    cols[2].metric("Candidate REMOVE", candidate_remove)
    cols[3].metric("Auto KEEP", auto_keep)
    cols[4].metric("Auto REMOVE", auto_remove)
    cols[5].metric("Official matches", official_matches)

    st.markdown(
        "LIKELY_NAIL: %d · LIKELY_NOT_NAIL: %d · REVIEW: %d · Source errors: %d"
        % (
            int(decisions.get("LIKELY_NAIL", 0)),
            int(decisions.get("LIKELY_NOT_NAIL", 0)),
            int(decisions.get("REVIEW", 0)),
            source_errors,
        )
    )

    if source_errors:
        st.error("Có source error. Không dùng các row lỗi nguồn để đánh giá rule.")

    gated = int((result["Policy_Status"] == "CANDIDATE_NEEDS_BENCHMARK").sum())
    st.info(
        "Shadow candidates đang bị policy gate chặn: %d. Local rule chưa được phép auto KEEP/REMOVE." % gated
    )

    important = [
        col
        for col in [
            "State", "Company", "Street", "City", "ZIP", "Phone", "Status",
            "Business_Exists", "Nail_Service", "Decision", "Confidence",
            "Rule_ID", "Candidate_Action", "Auto_Action", "Policy_Status",
            "Local_Signal", "Local_Score", "Risk_Flags", "Shared_Address_Count",
            "Exact_Record_Duplicate_Count", "Evidence_Tier", "Official_Matched_Name",
            "Official_Matched_Address", "Official_License_Type", "Reason",
            "Source_Errors", "Cache_Hit",
        ]
        if col in result.columns
    ]
    st.dataframe(result[important], use_container_width=True, hide_index=True)

    source_name = st.session_state.get("v33_source", "nail-map.csv")
    base_name = source_name.rsplit(".", 1)[0]

    st.download_button(
        "Tải CSV Precision v3.3 Shadow",
        data=result.to_csv(index=False).encode("utf-8-sig"),
        file_name=base_name + "-precision-v33-shadow.csv",
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
            file_name=base_name + "-validation-sample-v33.csv",
            mime="text/csv",
            use_container_width=True,
        )
        st.caption("Sample tiếp theo dùng để mở rộng calibration; không tự bật rule.")
