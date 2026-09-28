from __future__ import annotations

import io

import pandas as pd
import streamlit as st

from nailverifier_v3.engine import ENGINE_VERSION, OFFICIAL_ADAPTERS, verify_dataframe
from nailverifier_v3.normalize import detect_columns, validate_mapping
from nailverifier_v3.sampling import make_validation_sample

st.set_page_config(page_title="Nail Verifier — Precision v3.6", page_icon="💅", layout="wide")

st.title("Nail Verifier — Precision v3.6 NOT-NAIL Candidate")
st.caption(
    "Mục tiêu chính: tìm business trong NailMap nhưng thực tế KHÔNG phải tiệm nail. "
    "South Dakota hiện chỉ Auto REMOVE khi exact identity khớp business NOT_NAIL đã được xác minh độc lập."
)
st.caption(
    "Generic non-nail rule vẫn bị khóa. Identity collision guard có quyền ép mọi Auto KEEP/REMOVE về REVIEW; bulk mode tắt public Nominatim."
)

with st.expander("V3.6 thêm gì?", expanded=False):
    st.markdown(
        """
**Verified NOT_NAIL → Auto REMOVE**
- 35 business thuộc `R_NON_NAIL_CATEGORY_STRONG` trong cohort South Dakota hiện tại đã được kiểm tra độc lập là hardware / retail / grocery / restaurant / fuel stop / hotel-gaming, không phải nail salon.
- V3.6 chỉ cho phép REMOVE khi **exact normalized name + full street + city + ZIP + phone** khớp allowlist đã xác minh.
- Business mới có cùng pattern (`Ace Hardware`, `Dollar General`, `Restaurant`...) nhưng chưa nằm allowlist vẫn `CANDIDATE_NEEDS_BENCHMARK` → REVIEW.
- Đây **không phải** bật generic `R_NON_NAIL_CATEGORY_STRONG`.

**Auto KEEP vẫn giữ nguyên**
- `R_NAIL_EXPLICIT_STRONG` → Auto KEEP theo calibrated strong rule.
- 7 exact address-strong nail identities đã xác minh → Auto KEEP khi exact identity khớp.
- `K & E Nail Studio LLC` vẫn REVIEW vì chưa đủ independent evidence cho exact identity.

**Safety guards**
- Cùng normalized phone + cùng base address nhưng khác business name → `Identity_Collision = YES`.
- Nếu một row đang Auto KEEP/REMOVE, collision guard ép về `REVIEW` với `Policy_Status = IDENTITY_COLLISION_REVIEW`.
- `Nail Supply / Nail Academy / Nail Products / Nail Wholesale...` luôn REVIEW.
- Các bang ngoài SD không dùng exact allowlist của SD.

Calibration là evidence cho các identity đã kiểm tra, không phải bảo đảm cho business chưa từng thấy.
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
    c3.metric("Auto-policy", "SD exact KEEP + REMOVE")
    c4.metric("Engine", ENGINE_VERSION)

    if unsupported:
        st.warning(
            "Bang chưa calibrated: %s. SD exact auto-policy sẽ không áp dụng cho các bang này."
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
            "Bulk run: Nominatim public đã tắt. Exact verified NOT_NAIL identities có thể Auto REMOVE; business chưa xác minh vẫn REVIEW."
        )

    force_refresh = st.checkbox(
        "Bỏ qua verification cache",
        value=False,
        help="V3.6 có engine version mới nên verification cache v3.5 không bị dùng nhầm.",
    )

    if st.button("3. Chạy Precision v3.6", type="primary", use_container_width=True):
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

        st.session_state["v36_result"] = result
        st.session_state["v36_source"] = uploaded.name
        st.session_state["v36_mode"] = mode
        progress_text.success("Xong")

if "v36_result" in st.session_state:
    result = st.session_state["v36_result"]
    st.divider()
    st.subheader("Kết quả Precision v3.6")

    decisions = result["Decision"].value_counts(dropna=False).to_dict()
    candidate_keep = int((result["Candidate_Action"] == "KEEP").sum())
    candidate_remove = int((result["Candidate_Action"] == "REMOVE").sum())
    auto_keep = int((result["Auto_Action"] == "KEEP").sum())
    auto_remove = int((result["Auto_Action"] == "REMOVE").sum())
    official_matches = int(result["Official_Source"].astype(str).str.strip().ne("").sum())
    source_errors = int(result["Source_Errors"].astype(str).str.strip().ne("").sum())
    collisions = int((result["Identity_Collision"] == "YES").sum())
    collision_blocks = int((result["Policy_Status"] == "IDENTITY_COLLISION_REVIEW").sum())
    exact_keep = int(
        ((result["Policy_Status"] == "VERIFIED_IDENTITY_ALLOWLIST") & (result["Auto_Action"] == "KEEP")).sum()
    )
    exact_remove = int(
        ((result["Policy_Status"] == "VERIFIED_IDENTITY_ALLOWLIST") & (result["Auto_Action"] == "REMOVE")).sum()
    )
    unexpected_remove = int(
        ((result["Auto_Action"] == "REMOVE") & (result["Policy_Status"] != "VERIFIED_IDENTITY_ALLOWLIST")).sum()
    )

    cols = st.columns(8)
    cols[0].metric("Checked", len(result))
    cols[1].metric("Candidate KEEP", candidate_keep)
    cols[2].metric("Candidate REMOVE", candidate_remove)
    cols[3].metric("Auto KEEP", auto_keep)
    cols[4].metric("Auto REMOVE", auto_remove)
    cols[5].metric("Exact NOT_NAIL REMOVE", exact_remove)
    cols[6].metric("Collision rows", collisions)
    cols[7].metric("Collision blocks", collision_blocks)

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

    enabled_keep = int(
        ((result["Policy_Status"] == "BENCHMARK_VALIDATED_RULE") & (result["Auto_Action"] == "KEEP")).sum()
    )
    gated = int((result["Policy_Status"] == "CANDIDATE_NEEDS_BENCHMARK").sum())
    st.info(
        "Strong-rule Auto KEEP: %d · Exact verified Auto KEEP: %d · Exact verified Auto REMOVE: %d · Candidate vẫn bị gate: %d · Collision blocks: %d."
        % (enabled_keep, exact_keep, exact_remove, gated, collision_blocks)
    )

    if unexpected_remove:
        st.error(
            "%d Auto REMOVE không đến từ exact verified identity allowlist. Không dùng các row này cho production filtering."
            % unexpected_remove
        )
    elif auto_remove:
        st.success(
            "%d business được Auto REMOVE vì exact identity khớp NOT_NAIL đã xác minh."
            % auto_remove
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

    source_name = st.session_state.get("v36_source", "nail-map.csv")
    base_name = source_name.rsplit(".", 1)[0]

    st.download_button(
        "Tải CSV Precision v3.6",
        data=result.to_csv(index=False).encode("utf-8-sig"),
        file_name=base_name + "-precision-v36.csv",
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
            file_name=base_name + "-validation-sample-v36.csv",
            mime="text/csv",
            use_container_width=True,
        )
        st.caption("Sample tiếp theo ưu tiên beauty/hair/spa ambiguous để tìm thêm business NOT_NAIL.")
