from __future__ import annotations

import io

import pandas as pd
import streamlit as st

from verifier import detect_columns, validate_mapping, verify_dataframe

st.set_page_config(page_title="Nail Salon Verifier — FREE", page_icon="💅", layout="wide")

st.title("Nail Salon Verifier — FREE")
st.caption("Upload CSV từ NailMap → tool tự kiểm tra bằng nguồn miễn phí → tải CSV kết quả. Không cần Google API key, không cần thẻ.")

with st.expander("Tool này đang kiểm tra bằng gì?", expanded=False):
    st.markdown(
        """
**Nguồn chính (South Dakota):** roster license hiện hành của South Dakota Cosmetology Commission.  
**Nguồn phụ:** OpenStreetMap/Nominatim cho các dòng chưa xác minh được từ license.

Kết quả:
- `YES / REAL_NAIL_SALON`: có bằng chứng mạnh là tiệm nail thật.
- `YES / LIKELY_REAL_NAIL_SALON`: có bằng chứng khá tốt từ nguồn phụ.
- `NO / WRONG_BUSINESS`: business rõ ràng là loại khác.
- `CLOSED`: nguồn CSV đang cho biết đã đóng.
- `REVIEW`: chưa đủ bằng chứng, tool không tự ý gọi fake.

> Bản FREE hiện tối ưu cho CSV bang **South Dakota (SD)**.
"""
    )

uploaded = st.file_uploader("1. Chọn file CSV", type=["csv"])

if uploaded is not None:
    try:
        df = pd.read_csv(io.BytesIO(uploaded.getvalue()), dtype=str, keep_default_na=False)
        mapping = detect_columns(df.columns)
        validate_mapping(mapping)
    except Exception as exc:
        st.error(f"Không đọc được CSV: {exc}")
        st.stop()

    state_col = mapping.get("state")
    states = sorted({str(x).strip().upper() for x in df[state_col].tolist() if str(x).strip()}) if state_col else []
    if states and states != ["SD"]:
        st.warning(f"Bản FREE hiện tối ưu cho South Dakota. File này có state: {', '.join(states)}")

    c1, c2, c3 = st.columns(3)
    c1.metric("Số dòng", f"{len(df):,}")
    c2.metric("Số cột", len(df.columns))
    c3.metric("Tên business", mapping.get("company") or "Không tìm thấy")

    st.dataframe(df.head(10), use_container_width=True, hide_index=True)

    mode = st.radio(
        "2. Chọn phạm vi kiểm tra",
        ["Test 20 dòng đầu", "Test 50 dòng đầu", "Kiểm tra toàn bộ CSV"],
        horizontal=True,
    )
    limit = 20 if mode.startswith("Test 20") else 50 if mode.startswith("Test 50") else None

    use_osm = st.checkbox(
        "Dùng OpenStreetMap làm nguồn phụ cho các dòng chưa xác minh được",
        value=True,
        help="Miễn phí nhưng giới hạn tốc độ khoảng 1 request/giây, nên chạy toàn bộ có thể mất vài phút.",
    )

    st.info("Lần đầu nên chạy **20 dòng**. Nếu kết quả hợp lý thì mới chạy toàn bộ 536 dòng.")

    if st.button("3. Bắt đầu kiểm tra FREE", type="primary", use_container_width=True):
        progress_bar = st.progress(0)
        progress_text = st.empty()

        def update_progress(done: int, total: int, name: str) -> None:
            progress_bar.progress(done / max(total, 1))
            progress_text.caption(f"Đang kiểm tra {done}/{total}: {name}")

        with st.spinner("Đang kiểm tra license và business ngoài đời..."):
            result = verify_dataframe(
                df,
                limit=limit,
                progress=update_progress,
                use_osm=use_osm,
            )

        st.session_state["verification_result"] = result
        st.session_state["source_name"] = uploaded.name
        progress_text.success("Kiểm tra xong.")

if "verification_result" in st.session_state:
    result = st.session_state["verification_result"]
    st.divider()
    st.subheader("Kết quả")

    counts = result["Verdict"].value_counts(dropna=False).to_dict()
    cols = st.columns(5)
    cols[0].metric("Đã kiểm tra", len(result))
    cols[1].metric("Real nail", int(counts.get("REAL_NAIL_SALON", 0)))
    cols[2].metric("Likely real", int(counts.get("LIKELY_REAL_NAIL_SALON", 0)))
    cols[3].metric("Wrong business", int(counts.get("WRONG_BUSINESS", 0)))
    cols[4].metric(
        "Review / khác",
        len(result)
        - int(counts.get("REAL_NAIL_SALON", 0))
        - int(counts.get("LIKELY_REAL_NAIL_SALON", 0))
        - int(counts.get("WRONG_BUSINESS", 0)),
    )

    important = [
        col
        for col in [
            "Company",
            "Street",
            "City",
            "State",
            "ZIP",
            "Phone",
            "Status",
            "Is_Real_Nail_Salon",
            "Verdict",
            "Confidence",
            "SD_Current_License",
            "SD_License_Match_Score",
            "OSM_Match",
            "OSM_Type",
            "Reason",
        ]
        if col in result.columns
    ]
    st.dataframe(result[important], use_container_width=True, hide_index=True)

    output_name = st.session_state.get("source_name", "nail-map.csv").rsplit(".", 1)[0] + "-verified-free.csv"
    st.download_button(
        "Tải CSV kết quả",
        data=result.to_csv(index=False).encode("utf-8-sig"),
        file_name=output_name,
        mime="text/csv",
        type="primary",
        use_container_width=True,
    )
