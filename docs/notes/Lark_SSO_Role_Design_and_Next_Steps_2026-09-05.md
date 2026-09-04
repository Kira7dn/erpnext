# Thiết kế Lark User Group và các bước triển khai ERP Role

- Ngày chốt: 2026-09-05
- Trạng thái: thiết kế mục tiêu; chưa phải bằng chứng production acceptance
- Liên quan: [Báo cáo audit bảo mật](Lark_SSO_Role_Sync_Security_Audit_2026-09-04.md)
- Ứng dụng kế tiếp: [Action plan tích hợp Driver Amplify](Driver_Amplify_Lark_SSO_Action_Plan_2026-09-05.md)

## Quyết định kiến trúc

Lark là Source of Truth cho trạng thái nhân viên và membership User Group. Một
người dùng có thể và thường sẽ thuộc nhiều User Group. ERPNext hợp các role được
ánh xạ từ tất cả group hiện tại của người dùng.

```text
Lark user
  + ERP - Access
  + ERP - Finance Manager
  + ERP - Purchasing User
          |
          v
ERP roles
  + Desk User
  + Accounts User
  + Accounts Manager
  + Purchase User
```

Không tạo Lark User Group cho từng cá nhân và không sao chép toàn bộ role lẻ của
ERPNext sang Lark. Group phải đại diện cho chức năng công việc ổn định. Một group
có thể ánh xạ sang một bundle gồm nhiều ERP Role.

## Ranh giới Source of Truth

| Dữ liệu | Nơi quản lý |
|---|---|
| Người nào còn hoạt động và thuộc chức năng nào | Lark User Group |
| Group ID nào ánh xạ sang ERP Role nào | Environment của SSO |
| Role có quyền đọc/tạo/sửa/submit DocType nào | ERPNext |
| Company, Branch, Warehouse và giới hạn bản ghi | ERPNext User Permission |
| Workflow, cấp duyệt và hạn mức duyệt | ERPNext |
| Quyền đặc biệt và break-glass | ERPNext/operator |

Lark không định nghĩa chi tiết permission của ERP. Lark chỉ quyết định entitlement
nghiệp vụ nào được cấp cho một danh tính.

## Mô hình group mục tiêu

`ERP - Access` là group cổng bắt buộc. Có group nghiệp vụ nhưng không có
`ERP - Access` thì vẫn bị từ chối đăng nhập.

| Lark User Group | ERP Role bundle | Ghi chú |
|---|---|---|
| `ERP - Access` | `Desk User` | Bắt buộc với mọi System User |
| `ERP - Finance User` | `Accounts User` | Nghiệp vụ kế toán thông thường |
| `ERP - Finance Manager` | `Accounts User`, `Accounts Manager` | Manager đã bao gồm quyền user |
| `ERP - Purchasing User` | `Purchase User` | Nghiệp vụ mua hàng |
| `ERP - Purchasing Manager` | `Purchase User`, `Purchase Manager` | Manager đã bao gồm quyền user |
| `ERP - Warehouse User` | `Stock User` | Nghiệp vụ kho |
| `ERP - Warehouse Manager` | `Stock User`, `Stock Manager` | Manager đã bao gồm quyền user |
| `ERP - Sales User` | `Sales User` | Nghiệp vụ bán hàng |
| `ERP - Sales Manager` | `Sales User`, `Sales Manager` | Manager đã bao gồm quyền user |

Đây là catalog khởi đầu, không phải yêu cầu phải tạo tất cả ngay. Chỉ tạo group
khi đã có owner nghiệp vụ, thành viên thực tế và ERP permission đã được duyệt.
HR, Manufacturing, Asset và các phân hệ khác được bổ sung theo cùng nguyên tắc.

## Quy tắc membership

1. Mọi người dùng ERP phải thuộc `ERP - Access`.
2. Mỗi người có thể thuộc nhiều group nghiệp vụ; role cuối cùng là phép hợp của
   các bundle tương ứng.
3. Người quản lý chỉ cần group `... Manager`; bundle Manager phải chứa cả role
   User cần thiết, không bắt buộc thêm đồng thời hai group cùng phân hệ.
4. Nếu hai group cùng cấp một role, việc rời một group không gỡ role khi group
   còn lại vẫn cấp role đó.
5. Gỡ `ERP - Access` hoặc disable Auth User phải ưu tiên hơn mọi group nghiệp vụ:
   ERP User bị disable, managed roles bị gỡ và session bị thu hồi.
6. Không ánh xạ `Administrator`, `System Manager`, `All` hoặc `Guest` từ Lark.
7. Không dùng Messenger group chat thay cho Contact User Group. Auth Server đọc
   membership bằng API `contact/v3/group/member_belong`.

## Quản trị enterprise

Mỗi group phải có:

- business owner chịu trách nhiệm xác nhận nhu cầu quyền;
- người được phép thêm/xóa thành viên;
- ticket hoặc dấu vết phê duyệt cho thay đổi membership;
- access review định kỳ;
- nguyên tắc least privilege và kiểm tra Separation of Duties.

App availability chỉ quyết định ai nhìn thấy/mở được Web App trong Lark; nó
không thay thế `ERP - Access` và không phải authorization boundary. Permission &
Scopes chỉ cấp khả năng gọi API cho app; nó không cấp ERP Role cho người dùng.

## Hiển thị tính năng trên Global Portal

Global Portal dùng cùng `LETRON_SSO_LARK_ROLE_MAPPING` để suy ra role từ snapshot
group của phiên đăng nhập. Không duy trì một mapping visibility thứ hai.

| Điều kiện role | Thành phần được hiển thị |
|---|---|
| `Desk User` | Thẻ Letron ERP và `Không gian ERP` |
| `Accounts User` hoặc `Accounts Manager` | `Tài chính` |
| `Purchase User` hoặc `Purchase Manager` | `Mua hàng` |
| `Stock User` hoặc `Stock Manager` | `Kho` |
| `Sales User` hoặc `Sales Manager` | `Bán hàng` |

Nếu không suy ra được `Desk User`, portal vẫn hiển thị danh tính đã đăng nhập
nhưng không hiển thị thẻ ERP. Việc ẩn ứng dụng/phân hệ chỉ là presentation
filter, không phải security boundary. ERPNext vẫn bắt buộc kiểm tra Role,
Permission, Workflow và User Permission trên mọi request.

## Ví dụ cấu hình

Chỉ group ID thật được ghi trong `.env` bị Git ignore. Tài liệu và file example
luôn dùng placeholder.

```env
LETRON_SSO_LARK_ROLE_MAPPING={"replace-access-group-id":["Desk User"],"replace-finance-user-group-id":["Accounts User"],"replace-finance-manager-group-id":["Accounts User","Accounts Manager"]}
LETRON_SSO_LARK_MANAGED_ROLES=["Desk User","Accounts User","Accounts Manager"]
LETRON_SSO_REQUIRED_LARK_GROUP_ID=replace-access-group-id
```

`LETRON_SSO_LARK_MANAGED_ROLES` phải là hợp của toàn bộ role xuất hiện trong
mapping. Role ngoài allowlist không được bộ đồng bộ thêm hoặc xóa.

## Trạng thái hiện tại

- Đã có User Group `ERP - Access` trên Lark.
- Mapping hiện tại chỉ có `ERP - Access` sang `Desk User`.
- Đồng bộ group phía Auth Server và đồng bộ role phía ERP đang được bật trong
  cấu hình local.
- Chưa có catalog group nghiệp vụ và mapping production hoàn chỉnh.
- Audit ngày 2026-09-04 còn hai lỗi High phải xử lý trước khi tuyên bố cơ chế
  thu hồi quyền sẵn sàng production: enforcement request dùng cookie `sid` và
  refresh group khi tái sử dụng Auth Server session.

## Bước tiếp theo

### Bước 1 — Chốt ma trận nghiệp vụ

Business owner xác nhận những group thực sự cần trong đợt đầu và danh sách thành
viên của từng group. Không tạo toàn bộ catalog chỉ để dự phòng.

Deliverable:

```text
Lark group name | Business owner | Members | ERP role bundle | Approval
```

### Bước 2 — Tạo User Group trên Lark

Trong Lark Admin Console, tạo các Contact User Group đã được duyệt, chỉ định
owner và thêm thành viên. Mọi thành viên phải có `ERP - Access` cùng với group
nghiệp vụ của họ.

Deliverable: tên group và `group_id` thật. Không đưa group ID thật vào Git.

### Bước 3 — Xác nhận ERP Role bundle

Kiểm tra các ERP Role đích đã tồn tại và permission của từng role đúng nhu cầu.
Thiết lập Company/User Permission và Workflow trong ERP; không cố biểu diễn các
giới hạn này bằng Lark group.

### Bước 4 — Vá security P0

Thực hiện SSO-01 và SSO-02 trong báo cáo audit trước khi mở rộng người dùng:

1. enforcement phải chạy cho cả cookie `sid` và API token;
2. mọi lần phát hành OIDC claim phải dùng snapshot group đủ mới.

### Bước 5 — Cập nhật mapping

Cập nhật `.env` thật với các group ID đã xác nhận, bảo đảm managed-role allowlist
khớp mapping. Auth Server và ERP runtime phải nhận cùng một giá trị
`LETRON_SSO_LARK_ROLE_MAPPING`; không thay đổi secret khi chỉ cập nhật role
mapping.

### Bước 6 — Nạp cấu hình và kiểm thử

Sau thay đổi cấu hình ERP, dùng launcher của repository:

```powershell
.\docker-start.ps1 -Action reload
```

Kiểm thử ít nhất các trường hợp:

1. chỉ có `ERP - Access` nhận đúng `Desk User`;
2. một user thuộc nhiều group nhận đúng hợp role;
3. chuyển từ User sang Manager gỡ/cấp đúng managed roles;
4. rời một group chỉ gỡ role không còn được group khác cấp;
5. rời `ERP - Access` bị disable và thu hồi session;
6. role ngoài managed allowlist không bị thay đổi;
7. mở Web App thật trong Lark và vào được ERP Desk.

### Bước 7 — Hoàn thiện vận hành production

Trước production cần thêm owner/review workflow, rate limit và retention cho
Auth Server, readiness xuyên suốt, metrics/audit alert, và cơ chế event hoặc
reconciliation để xử lý membership của user không phát sinh request.

## Điều kiện hoàn thành đợt phân quyền đầu tiên

- Ma trận group, owner, member và role bundle được phê duyệt.
- Group ID thật chỉ nằm trong secret environment.
- Hai lỗi P0 đã được vá và có regression test.
- Test add, move và remove membership đều cho kết quả đúng trong ERP.
- App availability, `ERP - Access` và backend authorization thống nhất.
- Có bằng chứng người dùng mở App thật trong Lark và chỉ thực hiện được nghiệp vụ
  theo role đã cấp.
