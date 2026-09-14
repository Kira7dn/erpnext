# Holding Finance — Native-first Account, Cost Center và Consolidation Design theo VAS

## 1. Mục tiêu và nguyên tắc

Tài liệu này chốt phương án triển khai cho holding nhiều pháp nhân trên một
Frappe site: dùng khả năng native của ERPNext, dùng Shared COA/Function catalog
đã khai báo trong policy và bắt buộc mọi Company tuân thủ cùng một bộ mã Account
và Cost Center.

Mỗi pháp nhân có một Company, sổ kế toán và báo cáo statutory riêng. `Letron
Holding` là một trong bảy Company giao dịch và là nơi ghi consolidation
adjustment. `LETRON GROUP` chỉ là Company Group tổ chức cây Holding, không ghi
nhận giao dịch và không phải pháp nhân thứ tám.

Quy ước lớp xử lý trong bảng:

```text
Shared COA template
        → Company-specific Account trees
        → Native statement engine + Holding consolidation package
        → Policy-generated native consolidation adjustments
```

Trong phạm vi hiện tại, tất cả Company lập sổ kế toán và báo cáo tài chính pháp
định theo Luật Kế toán, Chuẩn mực kế toán Việt Nam (VAS) và chế độ kế toán doanh
nghiệp hiện hành. Với năm tài chính bắt đầu từ hoặc sau 01/01/2026, chế độ kế
toán doanh nghiệp tham chiếu là Thông tư 99/2025/TT-BTC; báo cáo tài chính hợp
nhất tham chiếu Thông tư 202/2014/TT-BTC và các văn bản sửa đổi, bổ sung hiện
hành. IFRS không phải baseline vận hành của Letron và chỉ được xem xét như một
reporting layer tương lai nếu có yêu cầu pháp lý, nhà đầu tư hoặc công ty mẹ.

Tài liệu này chỉ đặc tả hành vi kỹ thuật của hệ thống. Không có task hoặc điều
kiện đóng nào yêu cầu phê duyệt, xin cấp phép, ký duyệt, lobby, hồ sơ giấy hoặc
tác nhân bên ngoài. Mọi quyết định trong phạm vi thiết kế được biểu diễn bằng
policy/config, code và test; phần ngoài phạm vi không trở thành blocker của dev.

Mã Account của Letron dùng trực tiếp mã tài khoản VAS theo Thông tư
99/2025/TT-BTC. Các mã quản trị cũ `1000–5950` không còn là COA vận hành.

### Trạng thái triển khai

`[x]` = đã có trong code/config và đã được runtime verify. `[ ]` = chưa có trong
code/config hoặc chưa có acceptance kỹ thuật.

```text
Frappe site = một Holding và các Company thuộc Holding
Company     = pháp nhân sở hữu bộ sổ
Account     = bản chất kinh tế của khoản tiền
Cost Center = bộ phận chịu trách nhiệm về chi phí/doanh thu
Project     = chương trình hoặc hoạt động có thời hạn
Asset       = tài sản cụ thể
```

## 2. Quan hệ giữa Company, Cost Center và Account

```text
Frappe site = một Holding, dùng chung các master data phù hợp
Company     = pháp nhân sở hữu bộ sổ và Account tree riêng
Account     = loại và bản chất kinh tế của khoản tiền
Cost Center = bộ phận chịu trách nhiệm về chi phí/doanh thu
```

Một dòng hạch toán kết hợp Account với Cost Center:

```text
Company:     LeDB Company
Account:     Salary and Employee Benefits
Cost Center: LEDB-ENG
Amount:      100,000,000 VND
```

## 3. Shared Chart of Accounts template — core code chốt

ERPNext tạo Account thuộc từng Company; không có một ledger Account dùng chung
cho nhiều Company. Vì vậy `Shared COA template` là chuẩn quản trị và bộ dữ liệu
được nhân bản cho từng Company, không phải một Account tree dùng chung vật lý.

Mọi Company phải giữ cùng mã, tên, Root Type, cấu trúc cha/con và ý nghĩa của
Account. Account đặc thù chỉ được thêm khi có lý do pháp lý hoặc nghiệp vụ và
phải được khai báo trong policy trước khi materialize.

### 3.1. Root Type

```text
Asset       = tài sản
Liability   = nợ phải trả
Equity      = vốn chủ sở hữu
Income      = doanh thu và thu nhập
Expense     = chi phí
```

### 3.2. Cây Account TT99 chốt

```text
[x] Asset: 111–244 theo Phụ lục II TT99, gồm tài khoản cấp 1, cấp 2 và cấp 3
[x] Liability: 331–357 theo Phụ lục II TT99, gồm tài khoản cấp 1, cấp 2 và cấp 3
[x] Equity: 411–421 theo Phụ lục II TT99, gồm tài khoản cấp 1, cấp 2 và cấp 3
[x] Income/Expense/Result: 511–911 theo Phụ lục II TT99, gồm tài khoản cấp 1,
    cấp 2 và cấp 3
[x] Policy catalog đã đối chiếu đủ 184 mã; native bootstrap tạo group/leaf theo
    quan hệ cha–con.
```

`Account Type` đặc biệt của ERPNext gồm Bank, Cash, Receivable, Payable, Stock,
Fixed Asset, Accumulated Depreciation, Capital Work in Progress, Cost of Goods
Sold, Depreciation, Tax, Stock Adjustment và Round Off.

`Root Type` xác định nhóm báo cáo; `Account Type` mô tả mục đích đặc biệt.

### 3.3. VAS/local statutory extension

Catalog TT99 đầy đủ là bộ nền chung. Việc bật sử dụng từng tài khoản do policy
của LeTRON quyết định; không tạo Account theo tên IFRS nếu VAS không yêu cầu:

```text
[x] Tài sản cố định hữu hình/vô hình, hao mòn/khấu hao và chi phí xây dựng cơ bản dở dang có trong catalog TT99.
[x] Đầu tư vào công ty con, công ty liên kết, góp vốn và dự phòng tổn thất đầu tư có trong catalog TT99.
[x] Thuế GTGT, thuế TNDN hiện hành/hoãn lại, phải trả người lao động, dự phòng và doanh thu chưa thực hiện có trong catalog TT99.
[x] Ngoại tệ, chênh lệch tỷ giá và chuyển đổi báo cáo nằm ngoài phạm vi policy hiện tại vì Holding đang dùng VND.
[x] Account đặc thù ngành hoặc pháp định được mở rộng bằng version mới của policy khi phạm vi kỹ thuật yêu cầu.
```

### 3.4. Account reporting convention

Trong phương án native-first, chưa tạo Group Account master riêng. Báo cáo hợp
nhất native của ERPNext dựa trên mã/tên Account tương thích giữa các Company.
Do đó bộ mã Account dưới đây là reporting convention bắt buộc toàn Holding.

Các thuộc tính sau là quy ước nghiệp vụ để chuẩn hóa Account và báo cáo VAS.
Chúng được thể hiện trước hết bằng mã quản trị, tên, Root Type, Account Type và
cấu trúc COA; không tạo custom metadata ngoài các field đã có trong policy:

[x] account_code và account_name theo danh mục VAS
[x] vas_account_code và vas_account_name theo Thông tư 99/2025/TT-BTC
[x] bctc_statement, bctc_section và chỉ tiêu báo cáo VAS — mapping core và mở rộng theo nhóm tài khoản TT99
[x] current_non_current theo nhóm chỉ tiêu trong policy; backend trả classification
[x] cash_flow_category theo VAS 24 và mẫu BCTC áp dụng — native Cash Flow nhận Finance Book và policy categories
[x] vas_reference và disclosure_note ở mức policy/template; report chỉ trả dữ liệu và template từ nguồn native
[x] template_version trong shared COA metadata
[x] effective_from: `2026-01-01` và effective_to: `null`; thay đổi framework/COA
    sau này phải tạo version policy mới và được kiểm soát theo kỳ khóa sổ.

Lưu chuyển tiền tệ phải được phân loại theo quy định VAS 24 và mẫu báo cáo áp
dụng; không suy ra đầy đủ chỉ từ Root Type.

## 4. Shared template và phạm vi Company

### 4.1. Dùng chung toàn site

Trong site hiện tại, các master sau luôn dùng chung theo policy:

[x] User, Role, Customer, Supplier, Item, Item Group, UOM, Currency, Finance Book,
Payment Term và Payment Terms Template
và Exchange Rate dùng chung trong site theo native ERPNext; riêng
`Consolidation Adjustment` là book dùng cho bút toán hợp nhất tại Holding.
[x] Shared COA template metadata và Function code catalog đã có trong policy.
[x] Fiscal Year là policy riêng tại `shared.fiscal_year`, tách khỏi `shared.coa_template`,
    có `calendar_year: true` và dùng năm dương lịch `01/01`–`31/12` cho toàn bộ 7 pháp nhân giao dịch.
[x] `shared.comparative_fiscal_years` materialize Fiscal Year 2025 cùng 7 pháp nhân
    để BCTC 2026 có kỳ so sánh native hợp lệ; các kỳ này không thay thế Fiscal Year hiện hành.
[x] Naming Convention và Consolidation Adjustment Policy: draft trước,
    submit/cancel bằng native ERPNext endpoint theo guard kỹ thuật.

Tax Rule, Price List và các master bổ sung phải được khai báo rõ phạm vi trong
policy; không có quy tắc suy đoán hoặc lựa chọn thủ công ngoài policy.

### 4.2. Tách theo Company

Các đối tượng sau phải thuộc đúng pháp nhân:

[x] Company, Account ledger, Cost Center và Warehouse được tách theo Company;
    không dùng Accounting Period để định nghĩa năm hay làm điều kiện cấu hình.
[x] Tax templates và native Company defaults đã được materialize theo Company.
[x] Fiscal Year 2026 (`01/01/2026`–`31/12/2026`) và Fiscal Year comparative 2025
    (`01/01/2025`–`31/12/2025`) đã được policy gán cho toàn bộ 7 Company giao dịch;
    acceptance probe runtime kiểm tra trực tiếp cả hai native Fiscal Year và xác nhận
    `Accounting Period` placeholder không tồn tại; policy không dùng Accounting Period
    để định nghĩa năm.
[x] `shared.fiscal_year`, `shared.comparative_fiscal_years` và native Fiscal Year
    documents bị ràng buộc cùng tên, ngày và danh sách Company; policy validator
    reject nếu các nguồn lệch nhau.
[x] `health`/`runtime_snapshot` đối chiếu native Fiscal Year với policy và đưa
    trạng thái `fiscal_year.ok` vào điều kiện runtime readiness.
[x] `Bank: TP Bank` dùng chung và bảy `Bank Account` placeholder theo từng
    Company đã được khai báo trong policy; mỗi tài khoản liên kết với Account
    `account://112`, chưa điền số tài khoản thật.
[x] Asset Category, Asset và statutory reporting settings được bao phủ bởi
    native object contract và synthetic readback.

### 4.3. Quy tắc đồng bộ COA

- [x] Company mới được tạo từ native ERPNext prerequisite, sau đó áp dụng VAS COA controller.
- [x] Account code VAS, name và cấu trúc đã được triển khai bằng native Account tree tại Company gốc và đồng bộ xuống các Company con.
- [x] Account địa phương chỉ được thêm bằng policy version mới với mã, tên,
  parent, Root Type và mapping report xác định.
- [x] Account đặc thù không dùng chung được xử lý bằng mapping policy; không tạo
  mapping engine riêng ngoài phạm vi hiện tại.
- [x] Không tự đổi nghĩa mã legacy; các mã legacy được retire an toàn, còn mã TT99
  được materialize theo catalog policy (ví dụ 141 là Tạm ứng, tồn kho dùng 152/156).

## 5. VAS accounting semantics

### 5.1. Nghiên cứu và phát triển

Tách rõ:

```text
621 Chi phí nhân công trực tiếp cho hoạt động nghiên cứu/phát triển
642 Chi phí quản lý doanh nghiệp cho hoạt động nghiên cứu/phát triển
213 Tài sản cố định vô hình khi đủ điều kiện ghi nhận theo VAS
214 Hao mòn tài sản cố định vô hình
```

Chi phí nghiên cứu và phát triển phải được phân loại, tập hợp và xử lý theo VAS
04, VAS 16 và hướng dẫn của Thông tư 99/2025/TT-BTC. Cost Center hoặc Project
chỉ cung cấp chiều quản trị, không tự quyết định việc vốn hóa; việc vốn hóa
phải đi qua Asset workflow và rule vốn hóa được khai báo trong policy; Cost Center
và Project không tự biến chi phí thành tài sản.

### 5.2. Tài sản cố định và thuê tài sản

```text
Asset
→ Asset Category
→ Fixed Asset Account
→ Accumulated Depreciation
→ Depreciation Expense
→ Cost Center
→ Project nếu có
```

Tài sản cố định phải theo dõi nguyên giá, giá trị còn lại, khấu hao và hồ sơ
kiểm kê theo VAS 03, VAS 04, Thông tư 99/2025/TT-BTC và quy định hiện hành về
quản lý, trích khấu hao tài sản cố định. Không tự động áp dụng mô hình
Right-of-use Asset/Lease Liability của IFRS; hợp đồng thuê phải được phân loại
và hạch toán theo VAS/chế độ kế toán Việt Nam.

### 5.3. Doanh thu và khoản nhận trước

Doanh thu và khoản nhận trước dùng Account/Cost Center/Project native theo policy.
Các metadata hợp đồng dưới đây không thuộc schema bắt buộc hiện tại; không tạo
custom field nếu chưa có task kỹ thuật riêng:

```text
contract
performance_obligation
recognition_pattern: point_in_time | over_time
contract_asset
contract_liability
principal_or_agent
```

Không dùng các trường `performance_obligation`, `principal_or_agent` hoặc
`contract_asset` như yêu cầu IFRS bắt buộc. Nếu cần dùng cho quản trị hợp đồng,
chúng phải được đánh dấu là metadata nội bộ và không thay thế quy định ghi nhận
doanh thu theo VAS.

### 5.4. Thuế, tổn thất và ngoại tệ

Phải phân biệt:

```text
Current Tax Asset/Liability
Deferred Tax Asset/Liability
Impairment Loss
Allowance for Impairment
Foreign Exchange Gain/Loss
Foreign Currency Translation Reserve
```

Mỗi Company phải khai báo đơn vị tiền tệ kế toán theo Luật Kế toán và Thông tư
99; báo cáo hợp nhất phải tuân thủ quy định về đơn vị tiền tệ kế toán, tỷ giá và
chuyển đổi báo cáo theo chế độ kế toán Việt Nam. Không dùng `functional_currency`
và `presentation_currency` như một yêu cầu IFRS độc lập.

## 6. Cost Center taxonomy — mã chốt

### 6.1. Bộ mã Company/segment

```text
HLD   Holding Corporate
LESC  LeSC - Smart City
LESM  LeSM - Smart Mobility
LEDB  LeDB - Digital Brain
LESE  LeSE - Smart Energy
LESB  LeSB - Smart Building
LEGM  LeGM - Green Materials
```

```text
FIN | TRE | HR | LEG | SAL | MKT | ENG | OPS
PRJ | PRD | QLT | SCM | IT | EXE | ADM
```

### 6.1.1. Bảng Function code chính thức — [x] catalog đã triển khai

| Code | Function | Ý nghĩa | Nhóm áp dụng chính |
|---|---|---|---|
| `FIN` | Finance | Kế toán, báo cáo, thuế, kiểm soát tài chính | Mọi Company |
| `TRE` | Treasury | Ngân hàng, tiền mặt, vốn, khoản vay | Holding và Company có dòng tiền riêng |
| `HR` | Human Resources | Nhân sự, tuyển dụng, phúc lợi, payroll | Mọi Company có nhân sự |
| `LEG` | Legal & Compliance | Pháp lý, hợp đồng, compliance, audit coordination | Holding và Company cần chức năng riêng |
| `SAL` | Sales | Bán hàng, account management, commission | Company kinh doanh |
| `MKT` | Marketing | Marketing, thương hiệu, truyền thông | Company có hoạt động thị trường |
| `ENG` | Engineering | Kỹ thuật, sản phẩm, R&D, triển khai kỹ thuật | Technology, Energy, Building |
| `OPS` | Operations | Vận hành dịch vụ, delivery, support | Company vận hành dịch vụ |
| `PRJ` | Projects | Quản lý chi phí và delivery theo dự án | Company chạy dự án |
| `PRD` | Production | Sản xuất, nhà máy, dây chuyền | Green Materials và manufacturing |
| `QLT` | Quality | QA/QC, kiểm định và chất lượng | Manufacturing và delivery cần kiểm soát |
| `SCM` | Supply Chain | Mua hàng, kho, logistics, cung ứng | Trading và manufacturing |
| `IT` | Information Technology | Hạ tầng, phần mềm và hỗ trợ IT nội bộ | Holding hoặc Shared Services |
| `EXE` | Executive | Ban điều hành và quản trị cấp cao | Holding hoặc Company có bộ máy riêng |
| `ADM` | Administration | Hành chính, văn phòng, tài sản dùng chung | Mọi Company cần tách hành chính |

Function code không phải Account và không mô tả loại tiền. Ví dụ `ENG` là bộ
phận; loại tiền vẫn do Account xác định:

```text
LEDB-ENG + 5300 Salary and Employee Benefits
LEDB-ENG + 5400 Research and Development
LEDB-ENG + 5700 Information Technology
```

Cost Center có dạng:

```text
{COMPANY_CODE}-{FUNCTION_CODE}
```

Ví dụ mã hợp lệ:

```text
HLD-FIN  HLD-TRE  HLD-LEG  HLD-EXE
LESC-FIN LESC-SAL LESC-ENG LESC-OPS LESC-PRJ
LESM-FIN LESM-SAL LESM-OPS LESM-PRJ
LEDB-FIN LEDB-ENG LEDB-OPS LEDB-PRJ
LESE-FIN LESE-ENG LESE-OPS LESE-PRJ
LESB-FIN LESB-ENG LESB-OPS LESB-PRJ
LEGM-FIN LEGM-SAL LEGM-PRD LEGM-QLT LEGM-SCM
```

Mã `HLD`, `LESC`, `LESM`, `LEDB`, `LESE`, `LESB` và `LEGM` là node group; các
node chức năng bên dưới là Cost Center ledger để gắn vào giao dịch.

### 6.2. Cost Center theo Company

```text
Letron Holding legal Company (1/7)
└── HLD
    ├── HLD-FIN
    ├── HLD-TRE
    ├── HLD-LEG
    └── HLD-EXE

LeDB legal Company
└── LEDB
    ├── LEDB-FIN
    ├── LEDB-ENG
    ├── LEDB-OPS
    └── LEDB-PRJ

LeGM Company
└── LEGM
    ├── LEGM-FIN
    ├── LEGM-SAL
    ├── LEGM-PRD
    ├── LEGM-QLT
    └── LEGM-SCM
```

Mọi Company dùng cùng bộ mã chức năng nhưng chỉ kích hoạt Cost Center thực sự
có hoạt động. Cost Center không được tạo theo cá nhân, Account, sản phẩm hoặc
hóa đơn. Nếu một Function chưa có owner hoặc chưa phát sinh hoạt động độc lập,
không tạo mã chỉ để làm đẹp cây.

## 7. Ví dụ kết hợp Account và Cost Center

| Company | Account | Cost Center | Ý nghĩa |
|---|---|---|---|
| LeDB | 642 Chi phí quản lý doanh nghiệp | LEDB-ENG | Lương/R&D nội bộ theo chính sách phân loại VAS |
| LeDB | 621 Chi phí nguyên liệu, vật liệu trực tiếp | LEDB-ENG | Chi phí trực tiếp cho hoạt động kỹ thuật |
| LeDB | 627 Chi phí sản xuất chung | LEDB-ENG | Chi phí vận hành kỹ thuật/phân bổ |
| LeGM | 641 Chi phí bán hàng | LEGM-SAL | Chi phí bán hàng |
| Holding | 642 Chi phí quản lý doanh nghiệp | HLD-LEG | Chi phí pháp lý Holding |
| Holding | 635 Chi phí tài chính | HLD-TRE | Chi phí ngân hàng/treasury |

Không tạo các Account như `LEDB-SALARY` hoặc `LEGM-SALES-COMMISSION`. Account và
Cost Center là hai trục độc lập.

## 8. Project, Asset và chiều bổ sung

```text
Account     = bản chất tiền
Cost Center = bộ phận chịu trách nhiệm
Project     = chương trình hoặc hợp đồng có thời hạn
Asset       = tài sản cụ thể
Employee    = đối tượng nhân sự
Party       = khách hàng, nhà cung cấp hoặc công ty đối ứng
```

Ví dụ R&D:

```text
Account:     5400 Research and Development
Cost Center: LEDB-ENG
Project:     Battery Research 2026
```

Ví dụ tài sản:

```text
Asset:                AI Server 001
Asset Category:       IT Equipment
Fixed Asset Account:  211 Tài sản cố định hữu hình
Cost Center:          LEDB-ENG
Accumulated Depreciation: 214 Hao mòn tài sản cố định
Depreciation Expense: 642 Chi phí quản lý doanh nghiệp
```

## 9. Intercompany và hợp nhất

```text
Holding Company
├── Investment in Subsidiaries
├── Intercompany Receivable - LEDB
└── Management Fee Income - LEDB

LeDB Company
├── Intercompany Payable - HLD
└── Management Fee Expense - HLD
```

Mỗi dòng intercompany phải xác định rõ pháp nhân đối ứng bằng Company,
Customer/Supplier nội bộ hoặc tài khoản Due to/Due from. Các trường sau là
metadata quản trị tùy chọn cho quy trình closing, không phải một ledger mới:

[x] source_company và counterparty_company được truyền trong intercompany marker và
  kiểm tra khớp với Company của GL khi matching
[x] intercompany_partner và transaction_type được truyền trong marker
[x] currency native theo từng Company
[x] matching_id bắt buộc cho auto-matching; match không đủ hai Company không được tạo schedule

Không tạo một Account riêng cho mọi đối tác nếu generic Account kết hợp với
`intercompany_partner` đã đủ để đối chiếu.

Quy trình vận hành hiện tại:

```text
Separate Company GL
→ Match marked intercompany balances
→ Generate policy elimination schedule
→ Aggregate consolidated statements before/after elimination (không ghi GL trực tiếp)
→ Create draft native Journal Entry in Letron Holding / Consolidation Adjustment / HLD-FIN
  → Submit native Journal Entry through ERPNext's built-in document workflow
 → Chỉ xử lý intercompany elimination theo rule hiện tại; NCI, thuế hoãn lại và FX
   không thuộc phạm vi triển khai này
 → Lập BCTC hợp nhất theo VAS và Thông tư 202/2014/TT-BTC, đã được sửa đổi/bổ sung
```

Không dùng Cost Center chung để che giao dịch nội bộ. Cost Center là chiều
quản trị; intercompany là quan hệ giữa các pháp nhân.

## 10. Quy tắc quản trị và ERPNext

- [x] Account đã có lịch sử không bị xóa; chỉ disable hoặc thay thế có kiểm soát.
- [x] Account mới phải tuân thủ Shared COA template hoặc được khai báo như policy exception.
- [x] Cost Center phải thuộc đúng Company.
- [x] Không đổi nghĩa của mã Account đã dùng ở kỳ trước.
- [x] Không tạo duplicate Account chỉ để xem báo cáo theo bộ phận.
- [x] Intercompany được nhận diện bằng marker bắt buộc trong `remarks` của GL:
  `LETRON-IC|id=...|counterparty=...|type=...`; giao dịch không có marker không
  bị engine tự đoán.
- [x] Elimination schedule có rule, matching id, source companies, account code,
  amount và cặp tài khoản điều chỉnh; policy dùng `mirror_actual_accounts` để
  ghi đúng Account lá thực tế (ví dụ `1368/3368`, `515/635`), không ghi vào
  Account nhóm hoặc ép mọi nghiệp vụ về `511/632`.
- [x] `require_closed_period` được enforce: chỉ tạo adjustment khi cả 7 Company
  có Period Closing Voucher native đã submit đến hết ngày báo cáo.
- [x] Consolidation package trả Balance Sheet, P&L và B03-DN cash-flow package
  hợp nhất pro-forma trước elimination cho kỳ hiện hành; khi truyền kỳ so sánh,
  trả thêm package và elimination schedule riêng cho kỳ đó. Các metric thiếu
  nguồn native vẫn fail-closed, phần elimination preview không ghi GL.
- [x] Consolidation adjustment luôn tạo native Journal Entry ở trạng thái Draft,
  dùng Cost Center lá `HLD-FIN - LTVN`; submit/cancel là thao tác riêng có kiểm quyền.
- [x] Mỗi Company phải khai báo đơn vị tiền tệ kế toán; BCTC hợp nhất phải tuân
  thủ quy định Việt Nam về đơn vị tiền tệ và tỷ giá chuyển đổi.
- [x] Shared COA template phải có version và không được thay đổi âm thầm các kỳ đã
  khóa.
- [x] Policy có mapping core chỉ tiêu BCTC riêng theo Thông tư 99/2025/TT-BTC.
- [x] Policy có catalog đầy đủ mã dòng statutory B01-DN/B02-DN/B03-DN theo Phụ lục IV
  TT99, gồm mã chính thức, công thức subtotal và Account/metric nguồn; các dòng
  cần tách ngắn hạn/dài hạn hoặc chi tiết sổ phụ vẫn fail-closed.
- [x] Report endpoint có Balance Sheet, Profit and Loss, B01-DN, B02-DN, B03-DN
  và native Cash Flow.
- [x] Backend trả classification ngắn hạn/dài hạn/vốn chủ sở hữu, cash-flow
  categories, disclosure-note templates và unmapped-account exceptions từ policy.
- [x] B01-DN/B02-DN/B03-DN đọc dữ liệu native theo đúng source của policy:
  B01 phân loại ngắn hạn/dài hạn bằng `GL Entry.due_date`, B01/B02 subledger
  bằng marker máy `LETRON-STAT` trong native Journal Entry, B02 basic EPS từ
  native Shareholder; diluted EPS không có nguồn native thì `not_applicable`.
  Nếu nguồn bắt buộc có số dư nhưng thiếu chi tiết, report vẫn fail-closed.
- [x] Cash Flow adapter giữ nguyên native ERPNext payload và bổ sung contract VAS 24
  indirect method, ba nhóm operating/investing/financing và account-type policy.
- [x] Native Cash Flow account-type adapter truyền đầy đủ `company` vào đúng
  signature ERPNext `get_account_type_based_gl_data`, tránh lỗi SQL runtime khi
  chạy package nhiều Company.
- [x] Notes adapter tạo quantitative snapshot từ số liệu Balance Sheet/P&L native;
  không tự sinh diễn giải hoặc số liệu không có trong sổ.
- [x] Currency guard chỉ cho phép các đơn vị tiền tệ nằm trong allowlist của policy;
  translation đa tiền tệ là capability chưa thuộc phạm vi hiện tại.
- [x] BCTC mẫu và nội dung thuyết minh được kiểm thử bằng synthetic fixture; report
  không tự sinh số liệu hoặc diễn giải ngoài nguồn native.

Các native objects chính được sử dụng trong workflow hiện tại:

```text
Company | Account | Cost Center | Project | Asset Category | Asset
Accounting Dimension | Finance Book | Journal Entry | Consolidated Financial Statements
```

ERPNext tạo Chart of Accounts riêng cho từng Company. Shared COA template là
điểm bắt đầu; mô hình holding dùng mã Account quản trị thống nhất và cần thêm
mapping sang tài khoản/chỉ tiêu VAS để lập BCTC pháp định. Intercompany
elimination được kiểm soát bằng quy trình closing và Journal Entry trong giai
đoạn đầu. Phần elimination được ghi vào chính `Letron Holding` (một trong bảy
pháp nhân), dùng `Finance Book: Consolidation Adjustment`; không tạo pháp nhân
hay database thứ tám. `LETRON GROUP` chỉ là Company group native phục vụ cây
Company/report, không phải nơi ghi adjustment.

Trạng thái tích hợp hiện tại của codebase:

```text
[x] Có native/contract foundation:
[x] Company tree và nhiều Company trong cùng site
[x] Account tree riêng theo Company từ cùng Shared COA template
[x] Cost Center riêng theo Company từ cùng Function catalog
[x] Project, Asset, Cost Center Allocation native foundation
[x] Journal Entry, Inter Company Invoice/Journal Entry và báo cáo accounting native
[x] Shared COA policy có đủ 184 mã TT99 và kiểm tra quan hệ Account cha–con
[x] API adapters cho Balance Sheet, Profit and Loss, Cash Flow, Notes, Unmapped Accounts và Consolidation Package

[x] Quy trình backend native có kiểm soát:
[x] Đối chiếu intercompany tự động cho các GL line có marker hợp lệ; marker được
  compile từ `shared.consolidation.intercompany_marker` trong policy; truy vấn
  GL dùng native `frappe.get_list()` để tôn trọng User Permission/Company isolation
[x] Lập elimination schedule tự động theo rule trong policy
[x] Trả consolidated statement lines trước/sau elimination để đối chiếu và preview
[x] Tạo draft consolidation adjustment Journal Entry idempotent tại Letron Holding
[x] Không cho create endpoint submit trực tiếp; submit phải qua command endpoint riêng
[x] Submit/cancel adjustment chỉ khi Journal Entry do policy tạo và đúng Finance Book
[x] Report VAS đọc qua native financial-statement engine; test fixture chạy trên stack chính
[x] Consolidation package native-first; hỗ trợ kỳ hiện hành và kỳ comparative;
  adjustment dùng native Journal Entry
[x] Public consolidation payload/response có schema generated chặt; report route
  truyền đúng `report_key` và `filters` vào Frappe handler
[x] Rà soát reporting-line, phân loại, thuyết minh template và Finance Book filter
[x] Acceptance kỹ thuật của reporting contract, currency guard, note snapshot và
  native transaction path đã có unit test/synthetic fixture; không phụ thuộc dữ
  liệu bên ngoài hoặc quy trình bên ngoài hệ thống

[x] Không cần triển khai thêm Group Account Mapping/ledger riêng ở giai đoạn này:
[x] Mã Account VAS dùng trực tiếp giữa các Company
[x] Matching/elimination engine nằm trong `letron_api`
[x] Adjustment model dùng native Journal Entry + Finance Book, không tạo custom ledger

API hợp nhất đã triển khai:

```text
GET  /api/v1/accounts/consolidation/package
POST /api/v1/accounts/consolidation/adjustments
POST /api/v1/accounts/consolidation/adjustments/submit
POST /api/v1/accounts/consolidation/adjustments/cancel
```

Package hợp nhất có thể nhận thêm `comparative_from_date` và
`comparative_to_date`. Khi có đủ hai ngày, backend đọc thêm GL native của kỳ
so sánh cho từng Company, lập `comparative_elimination_schedule` riêng và trả
`consolidated_before_elimination_comparative` cùng
`consolidated_after_elimination_comparative`; B03-DN cũng giữ đủ hai cột kỳ.
Kỳ so sánh không bị trộn vào kỳ hiện hành.

Ví dụ:

```text
GET /api/v1/accounts/consolidation/package?filters={
  "companies": ["Letron Holding", "LeSC", "LeSM", "LeDB", "LeSE", "LeSB", "LeGM"],
  "from_date": "2026-01-01",
  "to_date": "2026-12-31",
  "comparative_from_date": "2025-01-01",
  "comparative_to_date": "2025-12-31"
}
```

API báo cáo statutory dùng chung report handler:

```text
GET /api/v1/accounts/reports/report?report_key=vas-b01-dn&filters=...
GET /api/v1/accounts/reports/report?report_key=vas-b02-dn&filters=...
GET /api/v1/accounts/reports/report?report_key=vas-b03-dn&filters=...
```

Ba report đọc GL/native Cash Flow, không tạo Journal Entry. B01-DN trả cả
`closing_balance` và `opening_balance` (số đầu kỳ lấy từ `opening_balance` của
native financial-statement engine). B02-DN nhận thêm
`comparative_from_date`/`comparative_to_date` trong `filters` để lấy số so sánh;
nếu không truyền đủ hai ngày, cột so sánh được trả `null` với trạng thái
`requires_comparative_period`. B03-DN là mẫu lưu chuyển tiền tệ gián tiếp theo
TT99; adapter dùng các bucket native `Depreciation`, `Receivable`, `Stock` và
cash balance native, còn chỉ tiêu không thể truy nguyên từ native GL sẽ trả
`requires_metric`. B01/B02 chỉ dùng các detail source native: `due_date`, GL
remark marker và Shareholder; không suy diễn từ số dư Account tổng hợp. Nếu
thiếu detail source bắt buộc, response trả `ok: false` cùng
`unresolved_line_codes`; hệ thống không tự phát sinh hoặc ghi thêm GL.

Package hợp nhất mặc định trả preview trước/sau elimination của kỳ hiện hành. Khi adjustment đã
được submit qua native endpoint ở `Letron Holding`, truyền `include_adjustments: true` trong
`filters` để đọc lại native GL gồm default Finance Book và
`Consolidation Adjustment`; kết quả nằm ở `consolidated_after_native_adjustment`.
Chế độ này chỉ đọc lại bút toán đã ghi, không áp dụng elimination schedule lần
thứ hai. Nếu Company đã có một default Finance Book khác, backend đọc native
financial-statement engine theo ba scope `default`, `Consolidation Adjustment`
và `blank`, sau đó tính `default + adjustment - blank` để loại phần giao nhau;
Cash Flow cũng truyền `include_default_book_entries` để không bỏ sót B03-DN của
Holding; khi có kỳ comparative, readback cũng trả B03-DN comparative theo
Finance Book đó và dùng tỷ giá native tại ngày cuối kỳ comparative. Điều này
tuân theo guard native của ERPNext và không làm thay đổi sổ cái.

Luồng chuẩn là: GL của bảy pháp nhân → package/matching → elimination schedule →
draft Journal Entry tại `Letron Holding`/`Consolidation Adjustment` → submit theo
native ERPNext workflow → native GL Entry → consolidated report. Adjustment JE
đặt `party_not_required=1` theo đúng native Journal Entry contract để loại trừ
các cặp Receivable/Payable cấp tập đoàn không có một Customer/Supplier party
riêng; đây không phải là sửa ERPNext core. Không ghi trực tiếp vào GL Entry.
```

Các mục `[ ]` chỉ là gap kỹ thuật trong code/config/policy/test. Không có mục
nào là yêu cầu phê duyệt, xin cấp phép, lobby hoặc điều phối bên ngoài hệ thống.

## 10.0. Nhật ký sự cố triển khai và trạng thái runtime

Ngày 13/09/2026, lần apply COA đầu tiên đã phát sinh transaction lớn do logic
cũ cập nhật hàng loạt cây `Account` trong khi ERPNext đang dùng nested-set
(`lft/rgt`). Lệnh apply thủ công còn chạy chồng với startup migration/bootstrap,
dẫn đến MariaDB lock wait timeout và phải rollback hàng trăm nghìn undo-row.

Đây là lỗi thứ tự và cơ chế materialization của triển khai, không phải mô hình
`Cost Center + Account` hay lỗi của dữ liệu COA trong policy.

Biện pháp đã áp dụng:

```text
[x] Loại bỏ bulk-update/reparent toàn bộ Account tree.
[x] Chỉ tạo Account còn thiếu; Account đã tồn tại không save lại không cần thiết.
[x] Thêm Redis distributed lock cho toàn bộ policy sync.
[x] Launcher policy-apply chờ backend readiness trước khi chạy.
[x] Đổi thứ tự sync: native finance masters trước, policy Link validation sau.
[x] Reset volume db-data và sites của site frontend theo yêu cầu; giữ Redis,
    backup, source và policy.
[x] Runtime acceptance sau reset: backend readiness, policy/config drift = 0,
    setup hoàn tất và đủ 184 Account template cho mỗi 8 Company (1.472 Account).
[x] Tối ưu hot path: bundle validation được cache theo source signature; `reload`
    chỉ sync khi hash config/policy thay đổi và không gọi runtime snapshot sâu.
[x] Sửa lifecycle `tenant_bootstrap`: không serialize lại `policy.yaml` khi 77
    native documents đã được khai báo đầy đủ; source policy giữ nguyên UTF-8,
    comment, thứ tự và SHA-256 qua restart. Chỉ ghi lại khi native export thực sự
    bổ sung dữ liệu chưa có trong policy.
[x] Health bootstrap được cache 60 giây theo policy hash; `runtime_snapshot` vẫn
    refresh đầy đủ để không làm yếu kiểm chứng drift.
[x] Runtime read-only consolidation probe: đủ 7 Company, `Letron Holding`,
    `Consolidation Adjustment`, `match_count=0`, `schedule_count=0`.
[x] Probe package ngày 14/09/2026 chạy qua toàn bộ 7 Company và trả đúng
    `holding_company`, Finance Book, `company_count=7`, không tạo native
    adjustment; `ok=false` chỉ vì database chưa có giao dịch để suy ra các
    metric B03-DN còn thiếu — đây không phải acceptance số liệu kế toán.
[x] Acceptance lifecycle sau sửa: gọi lại `tenant_bootstrap` trên site cô lập,
    trả `created=false`, `policy_documents=77`, đủ 184 Account template cho mỗi
    Company và policy source không đổi byte/hash.
[x] Synthetic VAS acceptance trên stack ERPNext chính: native Journal Entry tạo GL
    cho Holding ở kỳ 2026 và comparative 2025; B03-DN đủ 37 dòng và hai cột,
    Notes đủ 7 template, Bank Account/Asset Category/Warehouse native readback,
    matcher/elimination chạy trên đủ 7 pháp nhân. Probe chỉ dùng native
    document lifecycle và rollback toàn bộ; tuyệt đối không insert trực tiếp
    `GL Entry`.
[x] B03-DN đã có `metric_sources` trong policy. Các metric chi tiết được đọc từ
    activity của Account/GL Entry native theo mã policy; thiếu mapping hoặc
    thiếu dữ liệu vẫn trả `requires_metric`, không mặc định bằng zero.
[x] Synthetic acceptance xác nhận adjustment boundary: adjustment chỉ đặt tại
    `Letron Holding/Consolidation Adjustment` và bị native close guard chặn khi
    bảy Company chưa có Period Closing Voucher đã submit.
[x] B01/B02 detail derivation đã hoàn tất: maturity đọc `GL Entry.due_date` theo
    cutoff một năm tại ngày báo cáo; subledger đọc marker
    `LETRON-STAT|form=...|line=...` từ native GL remarks; B02 basic EPS đọc tổng
    cổ phần từ native Shareholder và diluted EPS được đánh dấu
    `not_applicable` khi ERPNext không có diluted-instrument source.
[x] Synthetic VAS acceptance nạp các marker detail và `due_date` qua native
    Journal Entry lifecycle; B01-DN và B02-DN đều không còn unresolved line.
[x] Elimination schedule runtime/unit path giữ nguyên Account lá source và
    counterparty khi `posting_mode: mirror_actual_accounts`.
[x] Đo runtime sau tối ưu: `reload` 58,78 giây (trước 78,81 giây),
    `policy-apply` 33,33 giây (trước 63,92 giây), cả hai exit code 0.
```

Số row rollback trong log MariaDB là undo-row cần hoàn tác, không phải số
Account được tạo. Sau khi reset volume, transaction rollback cũ đã bị loại bỏ;
runtime mới đang materialize Account native qua cơ chế nested-set của ERPNext.
Chỉ đánh dấu runtime acceptance `[x]` sau khi backend lên Gunicorn, health trả
`ok=true`, policy không drift và đối chiếu đủ COA/Cost Center theo từng Company.

## 10.1. Gap register kỹ thuật — lý do và mức độ

Danh sách này chỉ ghi nhận phần chưa hoàn thiện về code, policy, config, test
hoặc Docker runtime. Chỉ các thành phần có thể kiểm tra trong source và runtime
của hệ thống mới thuộc phạm vi gap.

ERPNext đã có GL Entry, financial statements, Fiscal Year, Period Closing
Voucher và các dimension native. Phần cần tiếp tục xử lý nằm ở localization
TT99, mapping báo cáo và các guard kỹ thuật của LeTRON.

Mức độ:

```text
P0 = chặn phát hành BCTC hoặc có rủi ro sai số liệu trọng yếu
P1 = cần hoàn thiện trước vận hành chính thức ổn định
P2 = nâng cao cho quản trị Holding, chưa chặn vận hành từng pháp nhân
```

| Gap kỹ thuật | Mức độ | Lớp xử lý | Trạng thái | Lý do | Next action kỹ thuật |
|---|---:|---|---|---|---|
| COA TT99 và Shared COA materialization | P0 | Policy + BE | `[x]` | Catalog 184 mã, quan hệ cha–con và native Account tree đã có; policy là nguồn duy nhất | Không còn action kỹ thuật |
| Mapping Account → B01/B02/B03 | P0 | Policy + BE + Test | `[x]` B01/B02 đã có maturity, subledger và EPS derivation; B03 đủ 37 dòng | Maturity và subledger không nằm trong số dư Account tổng hợp nên phải đọc detail native; diluted EPS không có native instrument source được đánh dấu `not_applicable` | Không còn action kỹ thuật trong phạm vi COA VAS/VND hiện tại |
| Thuyết minh BCTC | P1 | Policy + BE | `[x]` | Notes adapter, template và quantitative snapshot đã có; không tự sinh dữ liệu ngoài native GL | Không còn action kỹ thuật |
| Cash Flow theo VAS | P1 | Policy + BE | `[x]` | Native Cash Flow, `metric_sources` và synthetic B03 acceptance đã có | Không còn action kỹ thuật trong phạm vi VND |
| TSCĐ, khấu hao, thuế, ngân hàng và tồn kho | P1 | Config + Policy + BE + Test | `[x]` | Native objects, policy rules và synthetic readback đã được kiểm tra | Không còn action kỹ thuật; chỉ bổ sung test khi mở thêm capability |
| Fiscal Year và close guard | P1 | Config + BE + Test | `[x]` | Native Fiscal Year và guard chặn consolidation adjustment ngoài kỳ đã khóa đã có | Không còn action kỹ thuật |
| Báo cáo hợp nhất Holding | P1 | Policy + BE | `[x]` | Engine BS/P&L/B03-DN, current/comparative, matcher/elimination trên 7 Company và adjustment boundary đã có | Không còn action kỹ thuật trong phạm vi hiện tại |
| Intercompany matching và elimination | P2 | Policy + BE | `[x]` | Marker contract, matching engine và idempotent native Journal Entry workflow đã có | Không còn action kỹ thuật |

### Kết luận về gap

Không có gap nào buộc phải thay thế ERPNext hoặc xây dựng ledger riêng. Mapping
và derivation B01/B02 đã hoàn tất trên native GL detail; chỉ những trường hợp
thiếu detail bắt buộc mới trả fail-closed. Test runtime dùng cùng stack chính;
không có acceptance Compose project riêng. Không cần frontend riêng trong phạm
vi hiện tại.

Quy ước lớp xử lý được ghi ngay trong cột `Lớp xử lý` của bảng trên:

```text
[x] Config: chỉ dùng cho runtime/hạ tầng, không phải nơi giải quyết BCTC
[x] Policy: nơi khai báo COA, mapping, chuẩn và rule dùng chung
[x] Backend: nơi bắt buộc triển khai report, validation, materialization và API
[x] Test: synthetic fixture và native runtime acceptance
[x] Frontend: không cần sửa trong phạm vi hiện tại; dùng native ERPNext Desk/API
```

Do đó, hiện không còn gap P0 kỹ thuật trong phạm vi mapping B01/B02 trên
COA VAS/VND hiện tại. Không có gap P0 nào bắt buộc phải xây frontend riêng.

`GL Entry` là ledger dẫn xuất. Người dùng submit chứng từ nghiệp vụ hoặc
Journal Entry; không tạo GL Entry độc lập để thay thế source document.

## 11. Tham khảo

- [ERPNext Chart of Accounts](https://docs.frappe.io/erpnext/chart-of-accounts)
- [ERPNext Accounting Dimensions](https://docs.frappe.io/erpnext/v14/user/manual/en/accounts/accounting-dimensions)
- [ERPNext Accounting Reports](https://docs.frappe.io/erpnext/accounting-reports)
- [ERPNext Cost Center](https://docs.frappe.io/erpnext/v14/user/manual/en/accounts/cost-center)
- [ERPNext Regional Chart of Accounts](https://docs.frappe.io/erpnext/regional/chart-of-accounts)
- [Thông tư 99/2025/TT-BTC — Bộ Tài chính](https://www.mof.gov.vn/tin-tuc-tai-chinh/tin-chinh-sach-tai-chinh/quy-dinh-moi-ve-che-do-ke-toan-doanh-nghiep)
- [Công báo Thông tư 99/2025/TT-BTC — Phụ lục IV mẫu B01-DN](https://congbao.chinhphu.vn/van-ban/thong-tu-so-99-2025-tt-btc-46529/59652.htm)
- [Công báo Thông tư 99/2025/TT-BTC — mẫu B03-DN](https://congbao.chinhphu.vn/van-ban/thong-tu-so-99-2025-tt-btc-46529/59658.htm)
- [Thông tư 43/2026/TT-BTC và BCTC hợp nhất — Bộ Tài chính](https://www.mof.gov.vn/tin-tuc-tai-chinh/tin-chinh-sach-tai-chinh/quy-dinh-moi-ve-phuong-phap-lap-va-trinh-bay-bao-cao-tai-chinh-hop-nhat)
