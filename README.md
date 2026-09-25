# Nail Verifier

Tool có 2 phase:

1. Phase 1 — Export CSV từ NailMap
2. Phase 2 — Precision verification

## Phase 1

Dùng export_visible_table.js trên NailMap.

Exporter sẽ cuộn hết virtual table, chống duplicate, đọc total rows và chỉ export khi số dòng thu được khớp total.

---

# Phase 2 — Precision v3.2

V3.2 được thiết kế cho dataset lớn theo nguyên tắc:

precision > coverage

Nếu chưa đủ chắc chắn thì REVIEW, không đoán.

## Tư duy mới ở v3.2

V3.2 tách 3 thứ khác nhau:

- Decision: tool nghĩ record thuộc nhóm nào.
- Candidate_Action: rule đề xuất KEEP / REMOVE / REVIEW.
- Auto_Action: hành động thực sự được phép chạy tự động.

Một candidate KEEP/REMOVE không tự động trở thành Auto_Action.

Local rule chỉ được auto khi đã có đủ gold sample và vượt benchmark gate.

## Local rule engine

Các rule hiện có:

- R_NAIL_EXPLICIT_STRONG
  - tên có nail/nails/manicure/pedicure hoặc compact name như NailSpa, NativeNails, Nailery;
  - OPERATIONAL;
  - có location + phone;
  - >= 3 reviews;
  - Candidate KEEP.

- R_NAIL_EXPLICIT_ADDRESS_STRONG
  - explicit nail name;
  - location đầy đủ;
  - >= 5 reviews;
  - có thể thiếu phone;
  - Candidate KEEP nhưng rule riêng để benchmark độc lập.

- R_NAIL_EXPLICIT_WEAK
  - explicit nail name nhưng thiếu identity/reviews;
  - REVIEW.

- R_NAIL_STYLING_HINT
  - từ gợi ý như polished / polish / pinky / tips / toes / claws / lacquer / gloss;
  - REVIEW vì các từ này không đủ chắc.

- R_NON_NAIL_CATEGORY_STRONG
  - category rõ ràng như hardware / restaurant / grocery / fuel / hotel...;
  - có structured identity;
  - Candidate REMOVE.

- R_NON_NAIL_CATEGORY_ADDRESS_STRONG
  - strong non-nail category + location + review activity;
  - Candidate REMOVE nhưng benchmark riêng.

- R_BEAUTY_AMBIGUOUS
  - hair / salon / spa / beauty / lash...
  - REVIEW vì beauty business không đồng nghĩa nail salon.

- R_UNKNOWN
  - không có rule precision cao.

## Official source

South Dakota adapter:

- tải official business roster một lần;
- index local theo ZIP / City;
- shortlist candidate;
- chỉ mở detail cho candidate hợp lý;
- distinctive business-name + address guard chống false match.

Regression quan trọng:

Audra Day Spa & Salon
!=
Revive Day Spa - Apprentice Salon

Trong khi:

Revive Salon & Day Spa
~=
Revive Day Spa - Apprentice Salon

chỉ khi distinctive token REVIVE và address/city/ZIP khớp.

## Public OpenStreetMap

- Test 20 / Test 50 có thể bật Nominatim.
- Bulk pilot tự tắt Nominatim.
- Không dùng public Nominatim như bulk backend.

## Audit columns

V3.2 xuất thêm:

- Rule_ID
- Candidate_Action
- Auto_Action
- Policy_Status
- Local_Signal
- Local_Score
- Risk_Flags
- Business_Exists
- Nail_Service
- Shared_Address_Count
- Exact_Record_Duplicate_Count
- official evidence
- OSM evidence
- Reason
- Source_Errors

## Policy gate

Local candidate rules mặc định chưa được auto-enable.

Rule KEEP cần:

- >= 20 manually verified examples của chính rule đó
- precision >= 99%

Rule REMOVE cần:

- >= 20 manually verified examples
- precision >= 99.5%
- zero false-remove trong benchmark

Official nail-specific current license vẫn có thể Auto KEEP vì evidence tier mạnh hơn local heuristic.

## Validation sample

Sau khi chạy v3.2, UI có nút:

Tải validation sample cân bằng

Sample lấy theo Rule_ID để tránh chỉ kiểm tra các case dễ.

Các cột cần điền:

- Gold_Label = NAIL / NOT_NAIL / UNKNOWN
- Gold_Source_URL
- Gold_Notes

Sau đó dùng sample để calibrate policy.

## Benchmark

Chạy:

python benchmark_v3.py

Benchmark v3.2 báo riêng:

- candidate rule sample count
- precision theo từng Rule_ID
- false remove
- rule nào ELIGIBLE
- actual Auto_Action đang được enable

Candidate_Action và Auto_Action không còn bị trộn với nhau.

---

# Chạy trên macOS

cd ~/nail-verifier
git pull
bash run_mac.sh

Mở:

http://localhost:8501

Phải thấy:

Nail Verifier — Precision v3.2

## Flow khuyến nghị

1. Test 20 dòng.
2. Nếu không có Source_Errors -> chạy Pilot toàn bộ CSV — official batch only.
3. Tải precision-v32.csv.
4. Tải validation-sample-v32.csv.
5. Kiểm tra gold sample.
6. Chạy benchmark.
7. Chỉ enable rule nào vượt precision gate.
8. Sau đó mới mở rộng production / bang tiếp theo.

---

# Cache / resume

SQLite:

.cache/nail_verifier_v3.sqlite3

Engine version nằm trong cache key nên v3.1 và v3.2 không dùng nhầm verification result của nhau.

HTTP cache vẫn được tận dụng để không tải lại official source không cần thiết.

---

# Official adapters

Hiện có:

- SD — South Dakota Cosmetology Commission business roster + detail.

Các bang khác phải có adapter riêng vì board/schema/rule khác nhau.

Local rule engine dùng chung toàn quốc nhưng Auto_Action vẫn được benchmark theo state/dataset trước khi enable.

---

# Tests

Chạy:

python -m pytest -q

Regression tests bao gồm:

- Audra không match nhầm Revive.
- Revive DBA variant match được khi address đúng.
- official Nail Salon -> safe Auto KEEP.
- broad beauty license không tự thành VERIFIED_NAIL.
- structured explicit nail -> Candidate KEEP nhưng policy block.
- structured non-nail -> Candidate REMOVE nhưng policy block.
- low-evidence nail-name -> REVIEW.
- permanently closed từ NailMap không còn auto-remove nếu chưa benchmark.
- shifted address recovery.
- roster tải/index một lần.

---

Không có public-data verifier nào đảm bảo 100%.

Mục tiêu của v3.2 là giảm false KEEP / false REMOVE tối đa, đồng thời dùng benchmark để mở coverage dần thay vì bật rule rộng ngay từ đầu.
