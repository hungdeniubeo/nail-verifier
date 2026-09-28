# Nail Verifier

Tool có 2 phase:

1. Phase 1 — Export CSV từ NailMap
2. Phase 2 — Precision verification

## Phase 1

Dùng `export_visible_table.js` trên NailMap.

Exporter cuộn virtual table, chống duplicate, đọc total rows và chỉ export khi số dòng thu được khớp total.

---

# Phase 2 — Precision v3.3 Shadow Calibration

Nguyên tắc:

> precision > coverage

Nếu chưa đủ chắc chắn thì REVIEW, không đoán.

## Decision / Candidate / Auto

V3.3 tách riêng:

- `Decision`: tool đánh giá record thuộc nhóm nào.
- `Candidate_Action`: rule đề xuất KEEP / REMOVE / REVIEW.
- `Auto_Action`: hành động thật sự được phép chạy tự động.

Local rule hiện vẫn **shadow-only**. Candidate KEEP/REMOVE không tự động trở thành Auto_Action.

Official nail-specific current state license vẫn có thể Auto KEEP vì evidence tier mạnh hơn heuristic local.

## Vì sao chưa bật auto local rules

Một sample nhỏ có thể cho kết quả 20/20 hoặc 30/30 nhưng vẫn chưa đủ để khẳng định rule sẽ giữ precision rất cao ở hàng chục nghìn record.

Benchmark v3.3 vì vậy đo thêm **Wilson 95% lower confidence bound**.

Báo cáo cho mỗi rule gồm:

- số gold labels;
- empirical precision;
- Wilson 95% lower bound;
- false-remove count;
- trạng thái cần thêm validation hay đủ điều kiện.

`UNKNOWN` gold label không bị tính như đúng hoặc sai.

## Calibration South Dakota

Repo có:

- `benchmarks/sd_gold.csv`
- `benchmarks/sd_rule_calibration_v33.csv`

`sd_rule_calibration_v33.csv` chứa các business đã được đối chiếu bằng website chính thức / business directory / map listing / nguồn độc lập khác.

Hiện local rules **chưa được auto-enable**.

## Local rule engine

Các rule quan trọng:

- `R_NAIL_EXPLICIT_STRONG`
  - explicit nail name;
  - OPERATIONAL;
  - location + phone;
  - >= 3 reviews;
  - Candidate KEEP.

- `R_NAIL_EXPLICIT_ADDRESS_STRONG`
  - explicit nail name;
  - location;
  - >= 5 reviews;
  - Candidate KEEP nhưng benchmark riêng.

- `R_NAIL_NON_SERVICE_CONFLICT`
  - tên có nail nhưng đồng thời có các từ như Supply / Wholesale / Academy / School / Products / Equipment...;
  - REVIEW để tránh nhầm nail-product/training business với nail salon.

- `R_NAIL_EXPLICIT_WEAK`
  - explicit nail name nhưng identity/review yếu;
  - REVIEW.

- `R_NAIL_STYLING_HINT`
  - polish / polished / pinky / tips / toes / claws / lacquer / gloss;
  - REVIEW.

- `R_NON_NAIL_CATEGORY_STRONG`
  - hardware / restaurant / grocery / fuel / hotel...;
  - structured identity;
  - Candidate REMOVE.

- `R_BEAUTY_AMBIGUOUS`
  - hair / salon / spa / beauty / lash...;
  - REVIEW vì beauty business không đồng nghĩa nail salon.

## Official South Dakota adapter

- tải roster một lần;
- index local theo ZIP / City;
- shortlist candidate;
- chỉ mở detail cho candidate hợp lý;
- distinctive business-name + address guard chống false match.

Regression quan trọng:

```text
Audra Day Spa & Salon
!=
Revive Day Spa - Apprentice Salon
```

Trong khi Revive DBA/legal-name variant chỉ được match khi distinctive token và location cùng khớp.

## Public OpenStreetMap

- Test 20 / Test 50 có thể bật Nominatim.
- Full/bulk pilot tự tắt Nominatim.
- Không dùng public Nominatim như bulk backend.

## Cache

SQLite:

```text
.cache/nail_verifier_v3.sqlite3
```

Cache có safety invalidation để không tái sử dụng local auto-actions từ build calibration cũ.

## Benchmark

```bash
python benchmark_v3.py --file benchmarks/sd_rule_calibration_v33.csv
```

Benchmark sẽ báo riêng từng Rule_ID.

## Chạy trên macOS

```bash
cd ~/nail-verifier
git pull
bash run_mac.sh
```

Mở:

```text
http://localhost:8501
```

Phải thấy:

```text
Nail Verifier — Precision v3.3 Shadow Calibration
```

## Flow hiện tại

1. Export CSV NailMap.
2. Chạy full pilot shadow calibration.
3. Lấy validation sample cân bằng.
4. Xác minh gold labels bằng nguồn độc lập.
5. Chạy benchmark per-rule.
6. Chỉ bật auto-rule khi empirical precision + statistical confidence + false-remove gate đều đạt.
7. Sau SD mới làm adapter / calibration cho bang tiếp theo.

---

Không có public-data verifier nào đảm bảo 100%.

Mục tiêu của v3.3 là giảm false KEEP và đặc biệt false REMOVE trước khi tăng coverage.
