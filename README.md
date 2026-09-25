# Nail Verifier

Tool này được làm theo **2 phase**:

1. **Phase 1 — Export CSV từ NailMap**
2. **Phase 2 — Kiểm tra các salon trong CSV có thật hay không**

Hiện tại repo đang ở **Phase 1**.

## Phase 1 — Export CSV từ NailMap

File chính:

`export_visible_table.js`

### Mục tiêu

Lấy dữ liệu từ report NailMap ra CSV **đúng và đủ dòng**, đặc biệt với bảng dùng virtual/infinite scroll.

### Cách chạy

1. Đăng nhập NailMap bằng Chrome.
2. Mở report, ví dụ South Dakota:

   `https://nailmap.lexorit.com/v2026/reports/by-state/sheet/?state=SD`

3. Chờ bảng tải xong.
4. Mở Chrome DevTools:
   - macOS: `Command + Option + J`
   - Windows: `Ctrl + Shift + J`
5. Mở file `export_visible_table.js` trong repo.
6. Copy toàn bộ nội dung file.
7. Paste vào tab **Console** rồi nhấn Enter.
8. Không đóng tab và không thao tác vào bảng trong lúc script đang chạy.

### Phase 1 đã được nâng cấp

- Tự đưa bảng về đầu rồi cuộn hết virtual/infinite-scroll.
- Thu thập row trong nhiều lượt thay vì chỉ lấy row đang nhìn thấy.
- Ưu tiên `row id`, `aria-rowindex`, `data-*` và record URL để chống duplicate.
- Chỉ fallback sang nội dung row khi trang không có ID ổn định.
- Cố đọc các counter dạng:
  - `X of Y loaded`
  - `Showing X-Y of Z`
  - `N results`
  - `Total: N`
- Nếu NailMap báo tổng số dòng nhưng tool lấy thiếu thì **không tự tải CSV thiếu**.
- Lưu kết quả debug tại:

  `window.__NAILMAP_EXPORT_RESULT__`

- Tự thêm cột `State` từ query `?state=SD` nếu bảng không có sẵn.

### Kết quả thành công

Ví dụ:

```text
State: SD
Expected rows: 412
Exported rows: 412
Count match: YES
```

Browser sẽ tải file:

```text
nail-map-SD-YYYY-MM-DD.csv
```

### Nếu bị báo thiếu dòng

Ví dụ:

```text
NailMap expected: 412
Tool collected: 409
```

Tool sẽ **không tải CSV**.

Hãy:

1. chờ bảng NailMap load xong;
2. chạy lại script;
3. nếu vẫn lỗi, chạy trong Console:

```js
window.__NAILMAP_EXPORT_RESULT__
```

rồi gửi output để debug.

## Test syntax local

Nếu máy đã có Node.js:

```bash
node --check export_visible_table.js
```

Nếu không có lỗi gì hiện ra thì JavaScript syntax hợp lệ.

---

## Phase 2 — Salon verification

Sau khi Phase 1 lấy được CSV ổn định, Phase 2 sẽ đọc chính CSV đó và phân loại salon theo bằng chứng thực tế, dự kiến:

- `REAL`
- `LIKELY_REAL`
- `REVIEW`
- `CLOSED`
- `INVALID`

Phase 2 chưa được đưa vào bản hiện tại để tránh trộn logic xác minh salon với logic export CSV.
