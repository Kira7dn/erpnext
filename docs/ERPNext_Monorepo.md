# ERPNext trong monorepo

ERPNext được quản lý trực tiếp tại `apps/erpnext/` bằng Git subtree. Workspace
chỉ có một repository chính; remote `erpnext-fork` là nguồn đồng bộ tùy chọn,
không phải một checkout thứ hai.

## Kiểm tra remote

```powershell
git remote -v
git remote add erpnext-fork https://github.com/Kira7dn/erpnext.git
git fetch erpnext-fork version-16
```

Nếu remote đã tồn tại thì không chạy lại `git remote add`.

## Đồng bộ phiên bản ERPNext

```powershell
git fetch erpnext-fork version-16
git subtree pull --prefix=apps/erpnext erpnext-fork version-16
uv run python -m lib.api_generator generate
uv run pytest -q
.\docker-start.ps1 -Action verify
```

Không sửa trực tiếp source ERPNext khi xử lý contract hoặc integration app.
Mọi thay đổi custom ERPNext cần được review như một phần của monorepo và giữ
đúng prefix `apps/erpnext/`.
