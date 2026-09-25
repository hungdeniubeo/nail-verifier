# Nail Verifier

Tool có đúng **2 phase**:

1. **Phase 1 — Export CSV từ NailMap**
2. **Phase 2 — Upload CSV và kiểm tra tiệm nail có thật ngoài đời hay không**

---

## Phase 1 — Export CSV từ NailMap

File: `export_visible_table.js`

1. Đăng nhập NailMap bằng Chrome.
2. Mở report theo bang và chờ bảng load xong.
3. Mở DevTools Console.
4. Copy toàn bộ `export_visible_table.js` và paste vào Console.
5. Nhấn Enter và chờ tool chạy hết.

Tool chỉ export khi số dòng thu được khớp total NailMap hiển thị.

---

# Phase 2 — Nail Salon Verifier

Flow:

```text
CSV từ NailMap
   ↓
Upload vào Nail Salon Verifier
   ↓
Google Places kiểm tra business ngoài đời
   ↓
So khớp tên + địa chỉ + ZIP + phone + business type + business status
   ↓
Tải CSV kết quả
```

Tool **không gọi một business là fake chỉ vì không tìm thấy**. Nếu bằng chứng chưa đủ, nó trả về `REVIEW` để tránh loại nhầm tiệm thật.

## Kết quả

| Kết quả | Ý nghĩa |
|---|---|
| `REAL_NAIL_SALON` | Business khớp và Google phân loại là `nail_salon`, đang hoạt động |
| `LIKELY_REAL_NAIL_SALON` | Business beauty/spa đang hoạt động và có dấu hiệu rõ là làm nail |
| `WRONG_BUSINESS` | Business có thật nhưng không phải nail/beauty salon |
| `CLOSED_PERMANENTLY` | Business khớp nhưng đã đóng vĩnh viễn |
| `CLOSED_TEMPORARILY` | Business khớp nhưng đang đóng tạm thời |
| `REVIEW_BEAUTY_BUSINESS` | Có business beauty/spa nhưng chưa đủ bằng chứng để khẳng định là nail salon |
| `REVIEW` | Chưa đủ bằng chứng |
| `BAD_DATA` | CSV thiếu dữ liệu quan trọng |
| `API_ERROR` | Google Places API trả lỗi |

## Chuẩn bị Google Maps API key

Phase 2 dùng **Google Places API (New)**. Bạn cần một Google Maps API key có bật **Places API (New)**.

API key được nhập trực tiếp trong giao diện local và không được ghi vào CSV.

> Nên dùng **Test 20 dòng đầu** trước khi chạy toàn bộ file vì mỗi dòng sẽ dùng Google Places API.

## Chạy trên macOS

Lần đầu:

```bash
git clone https://github.com/hungdeniubeo/nail-verifier.git
cd nail-verifier
bash run_mac.sh
```

Sau này:

```bash
cd nail-verifier
git pull
bash run_mac.sh
```

## Chạy trên Windows

```powershell
git clone https://github.com/hungdeniubeo/nail-verifier.git
cd nail-verifier
.\run_windows.bat
```

## Cách dùng

1. Nhập Google Maps API key.
2. Upload CSV từ Phase 1.
3. Chọn `Test 20 dòng đầu`.
4. Bấm **Bắt đầu kiểm tra**.
5. Xem kết quả.
6. Nếu ổn, chọn `Kiểm tra toàn bộ CSV`.
7. Bấm **Tải CSV kết quả**.

CSV kết quả giữ nguyên dữ liệu gốc và thêm các cột bằng chứng như matched business, Google type/status, score và lý do.

## Test code

```bash
python -m pytest -q
```

Hiện có test cho:
- nhận diện cột NailMap;
- tự sửa case địa chỉ nằm nhầm ở cột City;
- nail salon thật;
- business thật nhưng sai loại;
- salon đã đóng;
- không tìm thấy thì `REVIEW`, không tự gắn `FAKE`.
