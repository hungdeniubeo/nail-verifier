from __future__ import annotations

import io

import pandas as pd
import streamlit as st

from nailverifier_v3.engine import ENGINE_VERSION, OFFICIAL_ADAPTERS, verify_dataframe
from nailverifier_v3.normalize import detect_columns, validate_mapping

st.set_page_config(page_title="Nail Verifier — Precision v3", page_icon="💅", layout="wide")

st.title("Nail Verifier — Precision v3")
st.caption(
    "Precision-first: chỉ tự động KEEP/REMOVE khi bằng chứng đủ mạnh. Case không chắc sẽ vào REVIEW thay vì đoán."
)
st.caption("Không cần Google API key. Có SQLite cache/resume để chạy dataset lớn.")

with st.expander("Cách v3 phân loại", expanded=False):
    st.markdown(
        """
- **VERIFIED_NAIL** → nguồn official của bang khớp chặt tên + vị trí và license type xác nhận nail salon. Có thể **KEEP** tự động.
- **LIKELY_NAIL** → bằng chứng khá mạnh nhưng chưa đủ chuẩn VERIFIED. Nên giữ, có thể review tùy nhu cầu.
- **VERIFIED_NOT_NAIL** → nguồn độc lập khớp đúng business nhưng category rõ ràng không phải nail/beauty. Có thể **REMOVE** tự động.
- **VERIFIED_BEAUTY_REVIEW_NAIL** → business beauty/salon là thật nhưng chưa chứng minh có dịch vụ nail.
- **CLOSED_PERMANENTLY** → nguồn dữ liệu ghi đóng vĩnh viễn.
- **REVIEW / UNSUPPORTED_STATE_REVIEW** → chưa đủ bằng chứng. Tool **không tự đoán**.

**Official adapters hiện có:** South Dakota (`SD`). Kiến trúc v3 đã tách adapter theo bang để thêm CA/TX/... mà không làm matcher lẫn nhau.
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
    official_states = set(OFFICIAL_ADAPTERS.keys())
    unsupported = [state for state in states if state not in official_states]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Rows", f"{len(df):,}")
    c2.metric("States", len(states) if states else 1)
    c3.metric("Official supported", ", ".join(sorted(official_states)))
    c4.metric("Engine", ENGINE_VERSION)

    if unsupported:
        st.warning(
            "Các bang chưa có official adapter: %s. V3 vẫn có thể dùng nguồn phụ, nhưng sẽ không gọi là VERIFIED nếu thiếu bằng chứng đủ mạnh."
            % ", ".join(unsupported)
        )

    st.dataframe(df.head(10), use_container_width=True, hide_index=True)

    mode = st.radio(
        "2. Phạm vi",
        ["Test 20 dòng", "Test 50 dòng", "Chạy toàn bộ"],
        horizontal=True,
    )
    limit = 20 if mode.startswith("Test 20") else 50 if mode.startswith("Test 50") else None

    use_osm = st.checkbox(
        "Dùng OpenStreetMap làm nguồn độc lập phụ",
        value=True,
        help="Miễn phí, có cache và rate limit. Official state source vẫn được ưu tiên hơn.",
    )
    force_refresh = st.checkbox(
        "Bỏ qua cache và kiểm tra lại từ đầu",
        value=False,
        help="Không nên bật khi chạy dataset lớn trừ khi bạn muốn refresh bằng chứng.",
    )

    st.info(
        "V3 có resume/cache: cùng business đã kiểm tra với cùng engine version sẽ lấy lại kết quả từ SQLite thay vì gọi nguồn bên ngoài lại."
    )

    if st.button("3. Chạy Precision Verification", type="primary", use_container_width=True):
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
        st.session_state["v3_result"] = result
        st.session_state["v3_source"] = uploaded.name
        progress_text.success("Xong")

if "v3_result" in st.session_state:
    result = st.session_state["v3_result"]
    st.divider()
    st.subheader("Kết quả Precision v3")

    counts = result["Decision"].value_counts(dropna=False).to_dict()
    cols = st.columns(6)
    cols[0].metric("Checked", len(result))
    cols[1].metric("VERIFIED NAIL", int(counts.get("VERIFIED_NAIL", 0)))
    cols[2].metric("LIKELY NAIL", int(counts.get("LIKELY_NAIL", 0)))
    cols[3].metric("VERIFIED NOT NAIL", int(counts.get("VERIFIED_NOT_NAIL", 0)))
    cols[4].metric("Beauty / review", int(counts.get("VERIFIED_BEAUTY_REVIEW_NAIL", 0)))
    review_count = sum(v for k, v in counts.items() if k in {"REVIEW", "UNSUPPORTED_STATE_REVIEW", "ERROR_REVIEW", "LIKELY_NOT_NAIL", "TEMPORARILY_CLOSED"})
    cols[5].metric("Needs review", int(review_count))

    keep_count = int((result["Auto_Action"] == "KEEP").sum())
    remove_count = int((result["Auto_Action"] == "REMOVE").sum())
    cache_hits = int((result["Cache_Hit"] == "YES").sum())
    source_error_rows = int(result["Source_Errors"].astype(str).str.len().gt(0).sum())

    st.markdown(
        f"**Safe auto-actions:** KEEP `{keep_count}` · REMOVE `{remove_count}` · Cache hits `{cache_hits}` · Source-error rows `{source_error_rows}`"
    )
    if source_error_rows:
        st.error("Có source error. Những dòng này không được auto-classify; hãy xem cột Source_Errors trước khi dùng kết quả production.")

    important = [
        col
        for col in [
            "State",
            "Company",
            "Street",
            "City",
            "ZIP",
            "Phone",
            "Decision",
            "Confidence",
            "Auto_Action",
            "Evidence_Tier",
            "Official_Matched_Name",
            "Official_Matched_Address",
            "Official_License_Type",
            "Official_License",
            "Official_Name_Score",
            "Official_Address_Score",
            "OSM_Matched_Name",
            "OSM_Category",
            "Reason",
            "Source_Errors",
            "Cache_Hit",
        ]
        if col in result.columns
    ]
    st.dataframe(result[important], use_container_width=True, hide_index=True)

    source_name = st.session_state.get("v3_source", "nail-map.csv")
    output_name = source_name.rsplit(".", 1)[0] + "-precision-v3.csv"
    st.download_button(
        "Tải CSV Precision v3",
        data=result.to_csv(index=False).encode("utf-8-sig"),
        file_name=output_name,
        mime="text/csv",
        type="primary",
        use_container_width=True,
    )
