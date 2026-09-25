# Nail Verifier

Tool có 2 phase:

1. Phase 1 — Export CSV từ NailMap
2. Phase 2 — Precision verification

## Phase 1

Dùng export_visible_table.js trên NailMap.

Exporter sẽ cuộn hết virtual table, chống duplicate, đọc total rows và chỉ export khi số dòng thu được khớp total.

---

# Phase 2 — Precision v3.1

V3.1 được thiết kế theo hướng precision-first cho dataset lớn.

Mục tiêu:

- không ép mọi dòng thành YES/NO;
- auto KEEP/REMOVE chỉ khi evidence đủ mạnh;
- case mơ hồ -> REVIEW;
- dữ liệu lớn dùng official roster theo batch và cache local.

## Thay đổi chính ở v3.1

### 1. South Dakota chạy theo batch index

South Dakota official business roster được tải một lần rồi index local theo:

- ZIP
- City

Mỗi business chỉ shortlist vài candidate hợp lý trước khi mở license detail.

Không scan toàn bộ roster cho từng row.

### 2. DBA / legal-name matching an toàn hơn

Các từ generic như:

spa / salon / beauty / nail / nails / LLC / PLLC / day

không được dùng làm business identity mạnh.

Ví dụ regression bắt buộc:

Audra Day Spa & Salon
!=
Revive Day Spa - Apprentice Salon

Nhưng:

Revive Salon & Day Spa
~=
Revive Day Spa - Apprentice Salon

có thể được match nếu distinctive token REVIVE và street/city/ZIP cùng khớp.

Khác street number -> reject.

### 3. Tách business existence và nail service

CSV v3.1 có thêm:

- Business_Exists
- Nail_Service

Ví dụ một hair salon có official license có thể là:

Business_Exists = VERIFIED_EXISTS
Nail_Service = UNKNOWN_NAIL_SERVICE

Thay vì tự động gọi nó là nail salon.

### 4. Không dùng public Nominatim cho bulk run

Trong UI:

- Test 20 / Test 50: có thể dùng OpenStreetMap/Nominatim.
- Pilot toàn bộ CSV: Nominatim bị tắt tự động.

Public Nominatim không được dùng làm backend cho hàng chục nghìn dòng.

### 5. SQLite cache/resume

Cache:

.cache/nail_verifier_v3.sqlite3

Nếu dừng giữa chừng thì lần sau các business đã xử lý với cùng engine version được lấy từ cache.

Engine v3.1 dùng version mới nên kết quả v3.0 cũ không bị tái sử dụng nhầm.

---

# Decision / action

| Decision | Ý nghĩa | Auto action |
|---|---|---|
| VERIFIED_NAIL | Official identity/location match + nail-specific license | KEEP |
| LIKELY_NAIL | Có tín hiệu nail mạnh nhưng chưa đủ VERIFIED | REVIEW hoặc keep có kiểm soát |
| VERIFIED_NOT_NAIL | Independent identity/location match + definite non-beauty category | REMOVE |
| VERIFIED_BEAUTY_REVIEW_NAIL | Business beauty thật nhưng nail service chưa chứng minh | REVIEW |
| CLOSED_PERMANENTLY | Source ghi đóng vĩnh viễn | REMOVE |
| TEMPORARILY_CLOSED | Đóng tạm thời | REVIEW |
| LIKELY_NOT_NAIL | Chỉ heuristic tên | REVIEW |
| REVIEW | Chưa đủ evidence | REVIEW |

---

# Benchmark gate

Gold set SD hiện có 20 business đã kiểm tra thủ công:

benchmarks/sd_gold.csv

Chạy:

python benchmark_v3.py

Benchmark v3.1 chỉ tính các dòng thật sự auto:

- Auto_Action = KEEP
- Auto_Action = REMOVE

LIKELY_NAIL và LIKELY_NOT_NAIL không còn được tính là auto decision.

Production gate:

- gold set >= 20
- ít nhất 10 NAIL
- ít nhất 5 NOT_NAIL
- ít nhất 5 auto KEEP
- ít nhất 3 auto REMOVE
- KEEP precision >= 99%
- REMOVE precision >= 99.5%
- false removals = 0

Nếu chưa đạt thì script báo:

GATE: FAIL / NOT PRODUCTION READY

Coverage được báo riêng nhưng không được phép đổi precision lấy coverage.

---

# Chạy trên macOS

cd ~/nail-verifier
git pull
bash run_mac.sh

Mở:

http://localhost:8501

Phải thấy:

Nail Verifier — Precision v3.1

## Test nhỏ

1. Upload CSV gốc.
2. Chọn Test 20 dòng.
3. Có thể bật OpenStreetMap/Nominatim.
4. Chạy Precision v3.1.
5. Kiểm tra Official matches và Source errors.

## Pilot toàn bộ 536 dòng SD

Sau khi Test 20 không lỗi:

1. Upload file gốc 536 rows.
2. Chọn Pilot toàn bộ CSV — official batch only.
3. Không bật OSM; UI tự tắt.
4. Chạy.
5. Tải file precision-v31.csv.
6. Pilot này dùng để đo official coverage/evidence trước khi production.

Không dùng file pilot để xóa hàng loạt cho tới khi benchmark gate PASS.

---

# Official adapters

Hiện có:

- SD — South Dakota Cosmetology Commission business roster + license detail

Các bang khác sẽ được thêm thành adapter riêng.

Không dùng một parser chung cho toàn nước Mỹ vì mỗi state board có schema và rule khác nhau.

---

# Tests

python -m pytest -q

Regression tests bao gồm:

- Audra không match nhầm Revive.
- Revive DBA variant có thể match Revive khi address khớp.
- khác street number bị reject.
- official Nail Salon -> VERIFIED_NAIL.
- broad beauty license không tự thành VERIFIED_NAIL.
- name-only non-nail không auto-remove.
- NailMap-only không thành VERIFIED.
- roster chỉ tải một lần và index local.

---

## Nguyên tắc

Không có public-data verifier nào đảm bảo 100%.

V3.1 ưu tiên:

precision > coverage

Nếu chưa chắc -> REVIEW.

Đây là behavior có chủ đích để bảo vệ dataset lớn khỏi false KEEP và đặc biệt là false REMOVE.
