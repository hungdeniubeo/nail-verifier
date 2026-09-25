# Nail Verifier

Tool có đúng **2 phase**:

1. **Phase 1 — Export CSV từ NailMap**
2. **Phase 2 — Precision verification**

---

## Phase 1 — Export CSV

Dùng `export_visible_table.js` trên trang NailMap.

Exporter:
- cuộn hết virtual table;
- chống duplicate;
- kiểm tra total rows;
- chỉ export khi số dòng lấy được khớp total NailMap.

---

# Phase 2 — Precision v3

V3 là bản **precision-first** dành cho dataset lớn và nhiều bang.

Mục tiêu không phải ép mọi dòng thành YES/NO. Mục tiêu là:

> Những dòng tool tự KEEP/REMOVE phải có bằng chứng rất mạnh. Dòng không chắc → REVIEW.

## Vì sao rebuild v3

V2 fuzzy-match quá dễ. Ví dụ trước đây:

```text
Audra Day Spa & Salon
```

có thể match nhầm với:

```text
Revive Day Spa - Apprentice Salon
```

chỉ vì cùng ZIP và cùng có các từ generic như `day / spa / salon`.

V3 sửa hẳn lớp lỗi này:

- các từ generic như `spa / salon / beauty / nail / LLC` không được dùng làm identity mạnh;
- official match bắt buộc tên + location khớp chặt;
- khác street number là reject;
- broad beauty license không tự động biến thành nail salon;
- NailMap rating/reviews chỉ có thể tạo `LIKELY_NAIL`, không thể tạo `VERIFIED_NAIL`;
- name heuristic một mình không bao giờ được auto-remove;
- source lỗi → REVIEW, không đoán.

## Decision

| Decision | Ý nghĩa | Auto action |
|---|---|---|
| `VERIFIED_NAIL` | Official state identity/location match + nail-specific license | KEEP |
| `LIKELY_NAIL` | Khả năng nail cao nhưng chưa đạt VERIFIED | REVIEW / giữ tùy policy |
| `VERIFIED_NOT_NAIL` | Nguồn độc lập khớp đúng business và xác nhận category không phải beauty/nail | REMOVE |
| `VERIFIED_BEAUTY_REVIEW_NAIL` | Business beauty thật, chưa chứng minh nail service | REVIEW |
| `CLOSED_PERMANENTLY` | Đóng vĩnh viễn | REMOVE |
| `TEMPORARILY_CLOSED` | Đóng tạm thời | REVIEW |
| `LIKELY_NOT_NAIL` | Chỉ có heuristic tên | REVIEW |
| `REVIEW` | Chưa đủ bằng chứng | REVIEW |
| `UNSUPPORTED_STATE_REVIEW` | Bang chưa có official adapter | REVIEW |

## Official state adapters

Kiến trúc state adapter đã tách riêng để mở rộng nhiều bang.

Hiện có:

- **South Dakota (SD)** — South Dakota Cosmetology Commission current business roster + license detail.

CA, TX và các bang khác sẽ được thêm bằng adapter riêng thay vì dùng một matcher chung cho mọi bang.

## Cache / resume cho dataset lớn

V3 dùng SQLite:

```text
.cache/nail_verifier_v3.sqlite3
```

Nếu chạy 50,000 dòng rồi dừng giữa chừng, lần sau các business đã xác minh với cùng engine version sẽ lấy từ cache.

Business trùng nhau giữa nhiều CSV cũng không cần gọi nguồn ngoài lại.

Rows gặp source error **không được cache**, để lần sau có thể retry.

---

## Chạy trên macOS

Nếu repo đã clone:

```bash
cd ~/nail-verifier
git pull
bash run_mac.sh
```

Mở:

```text
http://localhost:8501
```

Bạn phải thấy:

```text
Nail Verifier — Precision v3
```

### Cách test

1. Upload CSV gốc từ Phase 1.
2. Chọn **Test 20 dòng**.
3. Giữ tick OpenStreetMap.
4. Bấm **Chạy Precision Verification**.
5. Kiểm tra cột `Decision`, `Auto_Action`, evidence và source errors.
6. Chưa chạy production hàng loạt cho một bang cho đến khi benchmark của bang đó đạt gate.

---

# Benchmark độ chính xác

Repo có starter gold set:

```text
benchmarks/sd_gold.csv
```

Chạy:

```bash
python benchmark_v3.py
```

Nó tính:

- **coverage**: bao nhiêu dòng tool dám tự phân loại;
- **precision**: trong những dòng tool phân loại, bao nhiêu dòng đúng.

Production target:

```text
precision >= 98%
gold set >= 20 manually verified rows
```

Starter SD gold set hiện còn nhỏ nên benchmark sẽ cố ý báo `NOT READY` cho production gating cho tới khi đủ mẫu.

---

# Unit tests

```bash
python -m pytest -q
```

V3 có regression test bắt buộc:

```text
Audra Day Spa & Salon
!=
Revive Day Spa - Apprentice Salon
```

Ngoài ra test:
- strict official nail match;
- broad beauty license không thành VERIFIED_NAIL;
- name-only non-nail không được auto-remove;
- NailMap-only không được thành VERIFIED;
- address bị lệch sang City vẫn được normalize.

---

## Lưu ý về độ chính xác

Không có verifier public-data nào bảo đảm 100%.

V3 tối ưu theo hướng **precision > coverage**:

- ít auto-decision hơn;
- nhưng auto KEEP/REMOVE phải có evidence mạnh;
- những trường hợp mơ hồ bị đẩy sang REVIEW.

Đây là behavior có chủ đích cho việc lọc dataset lớn.
