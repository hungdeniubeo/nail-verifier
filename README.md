# Nail Verifier

Tool có đúng **2 phase**:

1. **Phase 1 — Export CSV từ NailMap**
2. **Phase 2 — Upload CSV và kiểm tra tiệm nail có thật ngoài đời hay không**

## Phase 1

Dùng `export_visible_table.js` trên trang NailMap. Tool chỉ export khi số dòng thu được khớp total NailMap hiển thị.

## Phase 2 FREE

Bản hiện tại **không cần Google Maps API key, không cần Billing và không cần thẻ**.

Nguồn kiểm tra:

- South Dakota Cosmetology Commission — roster license hiện hành.
- OpenStreetMap/Nominatim — nguồn phụ cho những dòng chưa xác minh được từ license.
- Signal có sẵn trong CSV NailMap chỉ dùng để hỗ trợ, không dùng một mình để kết luận.

Bản FREE hiện tối ưu cho **South Dakota (SD)**.

### Kết quả

| Verdict | Ý nghĩa |
|---|---|
| `REAL_NAIL_SALON` | Có bằng chứng mạnh từ license hiện hành rằng đây là nail salon |
| `LIKELY_REAL_NAIL_SALON` | Nguồn phụ khớp khá tốt với nail/beauty business |
| `WRONG_BUSINESS` | Business rõ ràng là loại khác |
| `CLOSED_FROM_SOURCE` | CSV nguồn ghi business đã đóng |
| `REAL_BEAUTY_BUSINESS_REVIEW_NAIL` | Có license beauty/salon thật nhưng chưa đủ chắc để nói riêng nail |
| `REVIEW` | Chưa đủ bằng chứng, không tự ý gọi fake |

### Chạy trên macOS

Nếu repo đang chạy bản cũ:

```bash
cd ~/nail-verifier
git pull
bash run_mac.sh
```

Sau đó mở:

```text
http://localhost:8501
```

Không còn ô Google Maps API key.

1. Upload CSV.
2. Chọn **Test 20 dòng đầu**.
3. Giữ tick **Dùng OpenStreetMap làm nguồn phụ**.
4. Bấm **Bắt đầu kiểm tra FREE**.
5. Xem kết quả.
6. Nếu ổn mới chạy toàn bộ CSV.

OpenStreetMap public service được gọi tuần tự và có cache local để tránh gọi lại cùng truy vấn. Vì vậy chạy toàn bộ có thể mất vài phút.

### Test code

```bash
python -m pytest -q
```

Hiện có test cho:

- nhận diện cột NailMap;
- sửa trường hợp Street bị lệch sang City;
- parse bảng license;
- nail salon khớp license hiện hành;
- business rõ ràng sai loại;
- business đóng cửa;
- xác minh phụ qua OpenStreetMap;
- không đủ bằng chứng thì giữ `REVIEW`.
