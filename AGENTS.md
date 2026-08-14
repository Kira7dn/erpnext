# Hướng dẫn vận hành Letron ERP

## Encoding

- Khi đọc hoặc xử lý file có tiếng Việt, luôn đọc nội dung bằng UTF-8.
- Không dùng encoding mặc định của PowerShell cho file tiếng Việt.

## Docker hot reload

Khi thay đổi source code, `config.yaml`, `policy.yaml` hoặc entrypoint Docker,
nhưng không muốn build lại image, dùng:

```powershell
.\docker-start.ps1 -Action reload
```

`reload` sẽ:

- dùng image hiện có với `--no-build`;
- chạy lại `config-sync`, `policy-bootstrap` và `policy-sync`;
- recreate các service dài hạn để nạp source/config mới;
- không recreate `create-site`;
- không chạy lại site migration;
- kiểm tra config/policy drift, Setup Wizard completion, landing route `/desk`
  và HTTP readiness.

Không dùng raw `docker compose up` để thay thế launcher, vì launcher chịu trách
nhiệm nạp environment từ `config/config.yaml`, validate bundle và chạy readiness.

## Phân biệt các action

- `.\docker-start.ps1 -Action reload`: hot reload hằng ngày, không build image.
- `.\docker-start.ps1 -Action build`: build image một cách tường minh trước
  production; không dùng action này trong vòng lặp phát triển hằng ngày.
- `.\docker-start.ps1 -Action up`: khởi động theo flow đầy đủ của launcher.
- `.\docker-start.ps1 -Action restart`: dừng và khởi động lại toàn bộ stack;
  chỉ dùng khi cần restart toàn hệ thống.
- `.\docker-start.ps1 -Action verify`: kiểm tra health và zero drift.
- `.\docker-start.ps1 -Action config`: chỉ validate Compose, config và policy.

Sau khi `reload` hoặc thay đổi landing route, đóng tab ERPNext cũ và mở lại
`/login` để browser nhận lại `frappe.boot` và session defaults mới.
