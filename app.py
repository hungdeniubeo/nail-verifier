from __future__ import annotations

import io

import pandas as pd
import streamlit as st

from nailverifier_v3.engine import ENGINE_VERSION, OFFICIAL_ADAPTERS, verify_dataframe
from nailverifier_v3.normalize import detect_columns, validate_mapping

st.set_page_config(page_title="Nail Verifier — Precision v3.1", page_icon="💅", layout="wide")

st.title("Nail Verifier — Precision v3.1")
st.caption(
    "Precision-first cho dataset lớn: official state data được ưu tiên; full-pilot không dùng public Nominatim."
)
st.caption(
    "SQLite cache/resume giúp chạy lại dataset lớn mà không phải kiểm tra lại các business đã hoàn tất."
)

with st.expander("V3.1 khác gì?", expanded=False):
    st.markdown(
        """
- Official roster được tải một lần rồi index local theo ZIP/City.
- Chỉ những candidate name hợp lý mới mở license detail.
- DBA/legal-name variants được phép nếu có distinctive name token + location khớp.
- Các từ generic như spa / salon / beauty / nail / LLC không đủ để match business.
- Audra Day Spa & Salon không thể match với Revive Day Spa chỉ vì cùng ZIP.
- Full-pilot tự động tắt public OpenStreetMap/Nominatim để tránh dùng public service như một bulk backend.
- Kết quả tách thêm Business_Exists và Nail_Service.
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
            "Chưa có official adapter cho: %s. Những bang này chưa sẵn sàng để production auto-filter."
            % ", ".join(unsupported)
        )

    st.dataframe(df.head(10), use_container_width=True, hide_index=True)

    mode = st.radio(
        "2. Chọn kiểu chạy",
        [
            "Test 20 dòng",
            "Test 50 dòng",
            "Pilot toàn bộ CSV — official batch only",
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
            help="Chỉ dùng cho test nhỏ. Không dùng public Nominatim làm backend cho bulk run.",
        )
    else:
        use_osm = False
        st.info(
            "Pilot toàn bộ sẽ chạy official state batch + local rules + cache. "
            "Public OpenStreetMap/Nominatim được tắt tự động."
        )

    force_refresh = st.checkbox(
        "Bỏ qua verification cache",
        value=False,
        help="Chỉ bật khi cần kiểm tra lại bằng engine hiện tại. HTTP source cache vẫn được giữ để tránh tải thừa.",
    )

    if mode.startswith("Pilot"):
        st.warning(
            "Đây là PILOT để đo coverage/evidence trên toàn file, chưa phải production auto-filter. "
            "Không xóa dữ liệu chỉ dựa trên file pilot."
        )

    if st.button("3. Chạy Precision v3.1", type="primary", use_container_width=True):
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
        st.session_state["v31_result"] = result
        st.session_state["v31_source"] = uploaded.name
        st.session_state["v31_mode"] = mode
        progress_text.success("Xong")

if "v31_result" in st.session_state:
    result = st.session_state["v31_result"]
    st.divider()
    st.subheader("Kết quả Precision v3.1")

    counts = result["Decision"].value_counts(dropna=False).to_dict()
    cols = st.columns(6)
    cols[0].metric("Checked", len(result))
    cols[1].metric("VERIFIED NAIL", int(counts.get("VERIFIED_NAIL", 0)))
    cols[2].metric("LIKELY NAIL", int(counts.get("LIKELY_NAIL", 0)))
    cols[3].metric("VERIFIED NOT NAIL", int(counts.get("VERIFIED_NOT_NAIL", 0)))
    cols[4].metric("Beauty review", int(counts.get("VERIFIED_BEAUTY_REVIEW_NAIL", 0)))
    cols[5].metric("Plain REVIEW", int(counts.get("REVIEW", 0)))

    keep_count = int((result["Auto_Action"] == "KEEP").sum())
    remove_count = int((result["Auto_Action"] == "REMOVE").sum())
    cache_hits = int((result["Cache_Hit"] == "YES").sum())
    source_error_rows = int(result["Source_Errors"].astype(str).str.len().gt(0).sum())
    official_matches = int(result["Official_Source"].astype(str).str.len().gt(0).sum()) if "Official_Source" in result else 0

    st.markdown(
        "**Pilot metrics:** "
        f"Official matches {official_matches} · "
        f"Auto KEEP {keep_count} · "
        f"Auto REMOVE {remove_count} · "
        f"Cache hits {cache_hits} · "
        f"Source errors {source_error_rows}"
    )

    if source_error_rows:
        st.error(
            "Có source error. Các dòng lỗi nguồn không được xem là production-safe."
        )

    if st.session_state.get("v31_mode", "").startswith("Pilot"):
        st.info(
            "File này dùng để đánh giá pilot coverage. Auto_Action vẫn phải qua benchmark gate trước khi dùng để lọc production."
        )

    important = [
        col
        for col in [
            "State",
            "Company",
            "Street",
            "City",
            "ZIP",
            "Phone",
            "Business_Exists",
            "Nail_Service",
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

    source_name = st.session_state.get("v31_source", "nail-map.csv")
    output_name = source_name.rsplit(".", 1)[0] + "-precision-v31.csv"
    st.download_button(
        "Tải CSV Precision v3.1",
        data=result.to_csv(index=False).encode("utf-8-sig"),
        file_name=output_name,
        mime="text/csv",
        type="primary",
        use_container_width=True,
    )
