# System Architecture — OpenAPI Interaction Boundary

## 1. Mục đích

Tài liệu này mô tả kiến trúc tổng quan của lớp tương tác OpenAPI trong hệ sinh
thái Letron ERP.

OpenAPI là contract chung để các ứng dụng và hệ thống bên ngoài tương tác với
ERPNext/Frappe. Tài liệu chốt các boundary và source of truth, nhưng không mô
tả source code, field implementation hoặc runbook vận hành chi tiết.

## 2. Phạm vi

Kiến trúc tập trung vào:

- các nhóm consumer sử dụng API;
- OpenAPI contract và cách tổ chức theo module nghiệp vụ;
- integration boundary giữa consumer và ERPNext/Frappe;
- sự khác nhau giữa curated contract và runtime catalog.

Chi tiết triển khai Identity, Data, Event Delivery và hạ tầng không thuộc phạm
vi; tài liệu chỉ ghi ranh giới sở hữu cần thiết để các lớp không chồng lấn.

## 3. System context

```mermaid
flowchart LR
    Frontend[Frontend Applications]
    Lark[Lark Applications]
    AI[Lele AI]
    LeOS[LeOS Systems]
    OpenAPI[Letron OpenAPI Contract]
    Integration[OpenAPI Integration Boundary]
    ERP[ERPNext / Frappe]

    Frontend --> OpenAPI
    Lark --> OpenAPI
    AI --> OpenAPI
    LeOS --> OpenAPI
    OpenAPI --> Integration
    Integration --> ERP
```

OpenAPI là điểm tương tác công khai giữa các consumer và ERPNext/Frappe.
Consumer không phụ thuộc vào chi tiết nội bộ của ERPNext hoặc DocType runtime.

## 4. Các thành phần

| Thành phần | Trách nhiệm kiến trúc |
|---|---|
| Frontend Applications | Sử dụng contract để hiển thị và thao tác dữ liệu ERP |
| Lark Applications | Sử dụng contract cho các tương tác được cấp phép |
| Lele AI | Gọi các capability được công bố qua contract |
| LeOS Systems | Trao đổi dữ liệu với ERP qua contract |
| OpenAPI Contract | Công bố operation, schema, module và capability được hỗ trợ |
| Integration Boundary | Chuẩn hóa tương tác giữa consumer và ERPNext/Frappe |
| ERPNext/Frappe | Thực thi metadata, validation, transaction và lifecycle của ERP |

`OpenAPI Integration Boundary` là boundary logic của contract; không mặc định
là một service độc lập.

## 5. Tổ chức OpenAPI theo module

OpenAPI public hiện được tổ chức đúng theo năm module nghiệp vụ:

- Accounts;
- Buying;
- Contacts;
- Selling;
- Stock;

Các module khác chỉ có thể xuất hiện trong runtime catalog để discovery; chúng
không phải public module và không tự sinh route. Public contract hiện có đúng
23 resource và 137 operation. Manufacturing không thuộc roadmap public hiện
tại.

Mỗi module có contract riêng cho các capability được chọn. Một operation chỉ
được đưa vào OpenAPI module khi đã có contract rõ ràng về:

- mục đích operation;
- HTTP method và URL;
- request và response schema;
- resource hoặc action được tác động;
- lỗi có thể trả về.

Tên module và URL public không nhất thiết phải trùng tên DocType nội bộ của
ERPNext. DocType có khoảng trắng hoặc tên kỹ thuật chỉ được dùng bên trong
integration boundary, không trở thành URL public mặc định.

## 6. Hai loại artifact

### 6.1. Curated OpenAPI contract

Đây là contract public chính, chỉ chứa các module, resource và RPC đã được
chọn và mô tả đầy đủ. Đây là artifact dùng cho consumer, tài liệu API và SDK.

### 6.2. Runtime catalog

Catalog ghi nhận toàn bộ DocType và method được phát hiện từ ERPNext/Frappe,
kể cả những API chưa được đưa vào public contract.

Catalog phục vụ discovery và mở rộng contract, không tự động biến mọi runtime
method thành public OpenAPI operation.

```text
ERPNext/Frappe runtime
        |
        +--> Runtime catalog: đầy đủ những gì được phát hiện
        |
        +--> Curated OpenAPI: chỉ những capability đã được công bố
```

## 7. Nguyên tắc interaction boundary

1. Consumer chỉ phụ thuộc vào OpenAPI contract.
2. Contract được chia theo module để consumer dễ khám phá và sử dụng.
3. Capability nghiệp vụ phải có operation và schema cụ thể.
4. Public contract không công bố resource hoặc RPC fallback động.
5. Runtime discovery không tự động mở rộng public contract.
6. ERPNext/Frappe vẫn là nơi thực thi validation và lifecycle của dữ liệu.
7. Thay đổi nội bộ ERPNext không được làm thay đổi public contract nếu chưa có
   quyết định cập nhật contract.

## 8. Configuration và policy boundary

OpenAPI business contract và control plane cấu hình là hai boundary tách biệt:

```text
config/config.yaml  -> system/runtime reconcile
config/policy.yaml  -> Company bootstrap + native business policy reconcile
.env                -> secret resolution only
ERPNext MariaDB     -> entity, master, transaction, ledger và runtime state
```

Một Docker project/Frappe site tương ứng một tenant và đúng một Company.
`letron_api` chỉ điều phối native controller/DocType; không tạo business
DocType, policy language hoặc workflow engine song song. System Manager có thể
sửa đúng hai YAML bind-mounted qua fixed-path control API. Production deploy
chỉ chạy `.\docker-start.ps1` trên Windows hoặc `./erpctl` trên Ubuntu, không
truyền action.

## 9. Trạng thái kiến trúc

- OpenAPI curated gồm 5 module, 23 resource và 137 operation đã qua Docker
  acceptance.
- Runtime catalog là discovery artifact đầy đủ.
- Các module được công bố tăng dần theo nhu cầu tích hợp.
- Webhook, realtime hoặc consumer cụ thể chỉ thuộc OpenAPI contract khi
  capability delivery tương ứng đã được xác định và công bố rõ.
- Phase 5 dùng `Letron Event Outbox` làm durable boundary: business transaction
  chỉ ghi queued state; worker gửi webhook/realtime sau commit, retry có giới hạn,
  và consumer deduplicate theo event ID. REST tiếp tục là source of truth.

Business boundary và production implementation đã đóng các gap về artifact
OpenAPI bền vững, control-plane typed contract, error contract, rollback
YAML/DB, invariant liên file và production runtime profile. Ubuntu clean-host
evidence còn được theo dõi trong mục
[Audit bàn giao API, config và policy](ERP_PRD.md#audit-bàn-giao-api-config-và-policy)
của PRD.

Evidence 2026-08-12: host `52 passed, 5 deselected`, Docker integration
`5 passed, 49 deselected`, public contract 137/137 operation `passed`, control
plane 2 operation, backup/restore drill và Windows no-flag readiness đều pass.
Policy runtime zero drift chỉ chứng minh 15 native document đã khai báo; không
được suy diễn thành bao phủ toàn bộ setting ERPNext. Ubuntu clean-checkout vẫn
là gate chưa có evidence.

Các quyết định về business workflow, identity provider, data storage và cơ chế
triển khai phải được ghi ở tài liệu chuyên biệt, không đưa vào kiến trúc
OpenAPI interaction boundary này.
