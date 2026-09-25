from __future__ import annotations

import io
import os

import pandas as pd
import streamlit as st

from verifier import detect_columns, validate_mapping, verify_dataframe

st.set_page_config(page_title="Nail Salon Verifier", page_icon="💅", layout="wide")

st.title("Nail Salon Verifier")
st.caption("Upload CSV từ NailMap → kiểm tra business ngoài đời bằng Google Places → tải CSV kết quả.")

with st.expander("Tool sẽ kết luận như thế nào?", expanded=False):
    st.markdown(
        """
- **YES / REAL_NAIL_SALON**: khớp business và Google phân loại là `nail_salon`, đang hoạt động.
- **YES / LIKELY_REAL_NAIL_SALON**: business beauty/spa đang hoạt động và có dấu hiệu rõ về nail.
- **NO / WRONG_BUSINESS**: business tồn tại nhưng là loại khác (ví dụ hardware store, restaurant...).
- **CLOSED**: business khớp nhưng Google báo đóng cửa.
- **REVIEW**: chưa đủ bằng chứng, không tự ý gọi là fake.

Tool giữ lại toàn bộ cột CSV gốc và thêm bằng chứng Google ở phía bên phải.
"""
    )

api_key = st.text_input(
    "Google Maps API key",
    value=os.getenv("GOOGLE_MAPS_API_KEY", ""),
    type="password",
    help="Cần bật Places API (New). Key chỉ dùng trong phiên chạy local và không được ghi vào CSV.",
)

uploaded = st.file_uploader("1. Chọn file CSV", type=["csv"])

if uploaded is not None:
    try:
        raw = uploaded.getvalue()
        df = pd.read_csv(io.BytesIO(raw), dtype=str, keep_default_na=False)
        mapping = detect_columns(df.columns)
        validate_mapping(mapping)
    except Exception as exc:
        st.error(f"Không đọc được CSV: {exc}")
        st.stop()

    c1, c2, c3 = st.columns(3)
    c1.metric("Số dòng", f"{len(df):,}")
    c2.metric("Số cột", len(df.columns))
    c3.metric("Cột tên tiệm", mapping.get("company") or "Không tìm thấy")

    st.dataframe(df.head(10), use_container_width=True, hide_index=True)

    mode = st.radio(
        "2. Chọn phạm vi kiểm tra",
        ["Test 20 dòng đầu", "Test 50 dòng đầu", "Kiểm tra toàn bộ CSV"],
        horizontal=True,
    )
    limit = 20 if mode.startswith("Test 20") else 50 if mode.startswith("Test 50") else None

    st.info(
        "Nên chạy 20 dòng trước để xem kết quả có hợp lý rồi mới chạy toàn bộ. "
        "Mỗi dòng sẽ gọi Google Places API; một số dòng yếu có thể cần thêm 1 lần tìm bằng số điện thoại."
    )

    if st.button("3. Bắt đầu kiểm tra", type="primary", use_container_width=True):
        if not api_key.strip():
            st.error("Bạn chưa nhập Google Maps API key.")
            st.stop()

        progress_bar = st.progress(0)
        progress_text = st.empty()

        def update_progress(done: int, total: int, name: str) -> None:
            progress_bar.progress(done / max(total, 1))
            progress_text.caption(f"Đang kiểm tra {done}/{total}: {name}")

        with st.spinner("Đang kiểm tra business ngoài đời..."):
            result = verify_dataframe(
                df,
                api_key=api_key,
                limit=limit,
                progress=update_progress,
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
    cols[4].metric("Review / lỗi", int(sum(v for k, v in counts.items() if k not in {"REAL_NAIL_SALON", "LIKELY_REAL_NAIL_SALON", "WRONG_BUSINESS"})))

    important = [
        col
        for col in [
            "Company",
            "Street",
            "City",
            "State",
            "ZIP",
            "Phone",
            "Is_Real_Nail_Salon",
            "Verdict",
            "Confidence",
            "Matched_Name",
            "Matched_Address",
            "Google_Primary_Type",
            "Google_Business_Status",
            "Reason",
        ]
        if col in result.columns
    ]
    st.dataframe(result[important], use_container_width=True, hide_index=True)

    source_name = st.session_state.get("source_name", "nail-map.csv")
    output_name = source_name.rsplit(".", 1)[0] + "-verified.csv"
    csv_bytes = result.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        "Tải CSV kết quả",
        data=csv_bytes,
        file_name=output_name,
        mime="text/csv",
        type="primary",
        use_container_width=True,
    )
