# Policy Configuration Questionnaire

## 1. Mục đích

Tài liệu này là checklist nghiệp vụ để xác định các giá trị cần cấu hình trong
[`config/policy.yaml`](../config/policy.yaml). Người trả lời không cần biết ERP;
chỉ cần trả lời theo chính sách kế toán, mua hàng, bán hàng, kho và phân quyền
của doanh nghiệp.

Thuật ngữ ERPNext/ERP và kế toán chuyên ngành được giữ nguyên bằng English để
đối chiếu trực tiếp với field trong policy. Không tự chọn giá trị khi chưa có
xác nhận của người phụ trách nghiệp vụ.

Mục tiêu của policy là giúp kế toán đọc file và biết ngay: giá trị nào đang
được áp dụng, field đó nhận lựa chọn nào, và phần nào còn phải quyết định.
Vì vậy, `null` không được xem là câu trả lời hoàn tất. Khi policy không có
field để biểu diễn một chính sách (ví dụ ngày bắt đầu năm tài chính hoặc quy
trình phê duyệt nội bộ), câu hỏi phải được đánh dấu `Need evidence` hoặc
`To decide`, không được suy đoán từ các field khác.

## 2. Cách trả lời

Mỗi câu nên có một trong các trạng thái:

- `Confirmed`: đã được chủ doanh nghiệp/kế toán trưởng xác nhận;
- `To decide`: chưa có quyết định nghiệp vụ;
- `Not applicable`: không áp dụng;
- `Need evidence`: cần kiểm tra hợp đồng, quy định thuế hoặc chứng từ mẫu.

| Câu hỏi | Trạng thái | Câu trả lời | Người xác nhận | Ngày |
|---|---|---|---|---|
| ... | ... | ... | ... | ... |

Các giá trị `null` trong policy không có nghĩa là `0` hoặc “tắt”; chúng thường
nghĩa là chưa chọn một linked record như Role, Warehouse, Price List hoặc Group.
Giá trị `''` là empty string và khác với `null`.

## 3. Câu hỏi bắt buộc để kế toán nhập được policy

Đây là câu hỏi thao tác, không phải yêu cầu kế toán tự xây dựng chính sách.
Kế toán chỉ cần mở ERPNext hoặc hồ sơ cấu hình hiện có, lấy đúng tên/giá trị,
chọn một lựa chọn được liệt kê và điền vào field tương ứng.

1. Trong ERPNext, tên `Company` cần áp dụng policy chính xác là gì? Nhập đúng
   `Company.name`, kể cả dấu cách và ký tự tiếng Việt.
2. `Company abbreviation` đang dùng trong ERPNext là gì? Nhập vào
   `bootstrap.company.abbreviation`.
3. `Company` đang dùng base currency nào? Chọn `VND` hoặc currency hiện có;
   không tự đổi sang currency khác.
4. `Company` đang dùng `Financial Year` nào? Nếu file policy chưa có field này,
   ghi lại để cấu hình ở bước Company/Accounting Period, không đoán từ ngày hiện tại.
5. Khi tạo Company, chọn `Standard` hay tên Chart of Accounts template đã có
   trong ERPNext? Nếu chọn custom, cung cấp chính xác tên template.
6. Policy này áp dụng cho Company nào? Chỉ chọn Company đã tồn tại hoặc được
   bootstrap; không tự tạo thêm Company từ questionnaire.
7. Trong form Company, chọn domain nào trong các giá trị ERPNext cho phép? Giá
   trị hiện tại là `Distribution`; chỉ đổi nếu ERPNext cung cấp lựa chọn khác.
8. Trong Chart of Accounts, tên Account Head dùng cho VAT là gì? Cung cấp đúng
   tên Account Head đã tồn tại cho Sales và Purchase Tax Template.
9. Trong hồ sơ thuế của công ty, cần tạo những Tax Rate/Tax Template nào? Ghi
   từng rate và Account Head; không chỉ ghi “có thuế khác”.
10. Khi tạo Sales Order, Delivery Note hoặc Sales Invoice, `Sales Order` có bắt
    buộc trước không? Chọn `Yes` hoặc `No` cho `so_required`.
11. Khi tạo Sales Invoice, `Delivery Note` có bắt buộc trước không? Chọn `Yes`
    hoặc `No` cho `dn_required`.
12. Khi tạo Purchase Receipt hoặc Purchase Invoice, `Purchase Order` có bắt
    buộc trước không? Chọn `Yes` hoặc `No` cho `po_required`.
13. Khi tạo Purchase Invoice, `Purchase Receipt` có bắt buộc trước không? Chọn
    `Yes` hoặc `No` cho `pr_required`.
14. `allow_negative_stock` chọn `0` (không cho phép) hay `1` (cho phép)? Chọn
    đúng theo trạng thái kiểm soát kho đang được sử dụng, không nhập chữ.
15. `valuation_method` chọn enum nào: `FIFO`, `Moving Average` hay `LIFO`?
16. Item có dùng Serial No/Batch No không? Nếu có, kiểm tra và cấu hình đồng
    nhất `enable_serial_and_batch_no_for_item`, Bundle và selector; không để các
    field này thể hiện hai cách vận hành khác nhau.
17. Có cần Accounting Dimensions không? Chọn `0` hoặc `1`; nếu chọn `1`, cung
    cấp tên các dimension đã tạo trong ERPNext.
18. Khi ERPNext gặp hành động `Stop`, Role nào được phép override? Nhập đúng
    tên `Role` đã tồn tại; nếu không có Role được cấp quyền thì giữ `null`.
19. Role nào được phép tạo hoặc sửa back-dated Stock Transaction? Nhập đúng tên
    Role; nếu không cấp quyền thì giữ `null`.
20. Khi chứng từ đã submit bị sai, người dùng sẽ xử lý bằng `Cancel`/reversal
    theo lifecycle ERPNext nào? Chọn quy trình đã được hướng dẫn trong hệ thống;
    không sửa/xóa ledger trực tiếp khi `enable_immutable_ledger: 1`.

## 3A. Câu hỏi policy hiện chưa thể tự trả lời

Các câu dưới đây là thông tin nghiệp vụ hoặc master data nằm ngoài các field
hiện có trong `policy.yaml`. Không được coi giá trị hiện tại trong policy là
câu trả lời cho chúng:

- ngày bắt đầu và kết thúc Financial Year;
- địa chỉ pháp lý, mã số thuế, thông tin đăng ký VAT và hồ sơ pháp nhân;
- danh sách thực tế của Company, Account, Cost Center, Warehouse, Price List,
  Customer Group, Supplier Group, Territory và Role;
- cơ cấu phê duyệt, người ký, phân nhiệm Accountant/Buyer/Sales/Stock/Auditor;
- chính sách chứng từ thay thế, reversal và xử lý sai sót sau khi khóa sổ;
- hợp đồng, quy định thuế hoặc bằng chứng xác nhận các tỷ lệ/ngoại lệ;
- việc doanh nghiệp có thực sự sử dụng Asset, Subscription, Loyalty,
  Manufacturing hoặc các capability ngoài scope hay không.

Đây là các câu hỏi cần trả lời bằng hồ sơ nghiệp vụ hoặc linked entity trước khi
điền policy. Nếu muốn `policy.yaml` tự trả lời cả nhóm này, phải mở rộng schema
policy có kiểm soát; không nhồi các dữ liệu entity, identity hoặc secret vào
file policy hiện tại.

## 4. Company, kỳ kế toán và audit trail

21. Có được phép sửa chứng từ đã ghi sổ không?
22. Khi chứng từ sai, quy trình cancel/reversal là gì?
23. Có giữ `enable_immutable_ledger: 1` ở production không?
24. Ai được quyền thực hiện Period Closing?
25. Sau khi khóa sổ, ai được quyền tạo back-dated transaction?
26. Có cần giới hạn số ngày được back-date không?
27. Có cho phép xóa linked ledger entries không? Khuyến nghị nghiệp vụ là không.
28. Có cần bảo toàn đầy đủ audit trail cho mọi Payment, Invoice và Journal Entry không?
29. Có cần phê duyệt hai cấp cho Invoice, Payment và Journal Entry không?
30. Có tự động submit Journal Entry không, hay phải giữ ở Draft để kiểm tra?

## 5. Accounts Receivable, Accounts Payable và Payment

31. Có cho phép một Party Account dùng nhiều Currency không?
32. Có tự động reconcile Payment với Invoice không?
33. Nếu auto reconciliation sai, ai kiểm tra và điều chỉnh?
34. Có tự động lấy Payment Terms từ Order hoặc Quotation sang Invoice không?
35. Payment sẽ ghi bằng `Payment Entry` hay `Journal Entry`?
36. Có tạo Payment Request từ Draft Invoice không?
37. Có tự động unlink Payment khi cancel Invoice không?
38. Có tự động unlink Advance Payment khi cancel Order không?
39. Role nào được bypass Credit Limit?
40. Role nào được bypass Overdue Billing Threshold?
41. Khi Customer quá hạn, chỉ `Warn` hay phải `Stop` Sales Invoice?
42. Các mốc `default_ageing_range` có phải `30, 60, 90, 120` không?
43. Khoảng chạy auto reconciliation bao nhiêu phút một lần?
44. Số document mỗi lần reconciliation có phù hợp với giới hạn 5–100 không?
45. Có cần giới hạn độ dài Remarks trong GL và AR/AP không?

## 6. Tax và VAT

46. `VAT - LTVN` là tài khoản VAT đầu vào, đầu ra hay tài khoản dùng chung?
47. Có cần tách VAT đầu vào, VAT đầu ra và VAT không được khấu trừ không?
48. Có áp dụng Import Tax, Withholding Tax, Special Consumption Tax hoặc loại khác không?
49. Tax Category được xác định từ `Billing Address` hay `Shipping Address`?
50. Có dùng Tax Category để phân biệt Customer, Supplier hoặc khu vực không?
51. Tax lấy ưu tiên từ `Item Tax Template` hay `Taxes and Charges Template`?
52. Có tính Tax theo `Net Total`, `Previous Row Amount`, `Previous Row Total`,
    `Item Quantity` hay `Actual`?
53. Có tính Tax theo từng Item row không?
54. Có cần `round_row_wise_tax` không?
55. Tax đã bao gồm trong rate hay cộng thêm vào rate?
56. Có hiển thị inclusive tax khi in không?
57. Có hiển thị Taxes dưới dạng table khi in không?
58. Có dùng Tax Withholding không?
59. Purchase và Sales Tax Template có cần đặt `is_default` không?
60. Có nên đặt tên riêng cho Input VAT và Output VAT thay vì cùng tên `Vietnam Tax` không?
61. Các `account_head`, `cost_center`, `company` trong tax template đã được tạo
    và đúng với Company chưa?
62. Có cần thêm Tax Rate 0%, 5% hoặc 8% ngoài 10% không?

## 7. Buying

63. Có cho phép một Item xuất hiện nhiều lần trong một Purchase transaction không?
64. Có cho phép negative rate không?
65. Có cho phép quantity bằng 0 trên Purchase Order, RFQ hoặc Supplier Quotation không?
66. Được phép nhận vượt Purchase Order bao nhiêu phần trăm?
67. Được phép transfer vượt quantity đã order bao nhiêu phần trăm?
68. Được phép order vượt Material Request bao nhiêu phần trăm?
69. Được phép order vượt Blanket Order bao nhiêu phần trăm?
70. Khi rate thay đổi, hệ thống `Warn` hay `Stop`?
71. Role nào được override `Stop` trong Buying?
72. Có tính Rejected Quantity vào Purchase Invoice không?
73. Hàng bị reject có tạo accounting entry không?
74. Có điều chỉnh incoming rate theo Purchase Invoice không?
75. Có tự động tạo Purchase Receipt từ Subcontracting Receipt không?
76. Có tự động tạo Subcontracting Order từ Purchase Order không?
77. Supplier được đặt tên theo `Supplier Name`, `Naming Series` hay `Auto Name`?
78. Price List mua hàng mặc định là gì?
79. Supplier Group mặc định là gì?
80. Email Account nào gửi Request for Quotation?

## 8. Selling

81. Có bắt buộc Sales Order trước Delivery Note không?
82. Có bắt buộc Sales Order trước Sales Invoice không?
83. Có bắt buộc Delivery Note trước Sales Invoice không?
84. Có cho phép quantity bằng 0 trên Quotation hoặc Sales Order không?
85. Có cho phép negative rate không?
86. Được phép bán vượt Blanket Order bao nhiêu phần trăm?
87. Khi selling rate thay đổi, hệ thống `Warn` hay `Stop`?
88. Role nào được override `Stop` trong Selling?
89. Có chặn bán dưới Purchase Rate hoặc Valuation Rate không?
90. Price List bán hàng mặc định là gì?
91. Customer Group mặc định là gì?
92. Territory mặc định là gì?
93. Customer được đặt tên theo `Customer Name`, `Naming Series` hay `Auto Name`?
94. Có cho phép tạo Sales Order từ expired Quotation không?
95. Khi Sales Return, có reserve lại Sales Order quantity không?
96. Có sử dụng Product Bundle không?
97. Có cho phép sửa rate của child Item trong Product Bundle không?
98. Có theo dõi Sales Commission, Sales Partner và Sales Team không?
99. Có bật UTM cho sales/CRM transaction không?
100. Có hiển thị nút Pay trên Sales Order portal không?

## 9. Stock, warehouse và valuation

101. Có cho phép Negative Stock không?
102. Có cho phép Negative Stock for Batch không?
103. Valuation Method chính thức là `FIFO`, `Moving Average` hay `LIFO`?
104. Có bật Serial and Batch tracking cho Item không?
105. Khi xuất kho, chọn Serial/Batch theo `FIFO`, `LIFO` hay `Expiry`?
106. Có cho phép chọn Serial/Batch thủ công không?
107. Có tự động tạo Serial and Batch Bundle khi outward transaction không?
108. Có tự động reserve stock khi submit Sales Order, Work Order hoặc Production Plan không?
109. Có cho phép partial reservation không?
110. Có bật Stock Reservation không?
111. Warehouse mặc định là gì?
112. Stock UOM mặc định là gì?
113. Item Group mặc định là gì?
114. Có cho phép sửa Stock UOM Quantity trên Purchase, Sales và Stock Entry không?
115. Có cho phép receive/deliver vượt Order không? Nếu có, tỷ lệ bao nhiêu?
116. Có bắt buộc source và target Warehouse khác nhau khi Material Transfer không?
117. Có yêu cầu Quality Inspection trước Purchase hoặc Delivery không?
118. Nếu Quality Inspection chưa submit, chọn `Stop` hay `Warn`?
119. Nếu Quality Inspection bị reject, chọn `Stop` hay `Warn`?
120. Có cho phép tạo Quality Inspection sau Purchase hoặc Delivery không?
121. Có sử dụng Barcode trong stock transaction không?
122. Có dùng Sample Retention Warehouse không?
123. Có tự động tạo Material Request khi đạt Reorder Level không?
124. Có tự động tạo Item Price khi thiếu Price List Rate không?
125. Có cập nhật Price List Rate đã tồn tại không?
126. `update_price_list_based_on` là `Rate` hay `Price List Rate`?
127. Có cho phép sửa Stock transaction sau ngày freeze không?
128. Role nào được quyền sửa frozen stock transaction?
129. Stock Frozen Upto là ngày cụ thể hay số ngày lùi lại?

## 10. Stock Reposting và Ledger Health

130. Có bật parallel Stock Reposting không?
131. Có tách riêng reposting cho GL không?
132. Có giới hạn reposting trong time slot không?
133. Nếu có, `start_time` và `end_time` là mấy giờ?
134. Ngày nào được miễn giới hạn time slot? `''` nghĩa là không miễn ngày nào.
135. `no_of_parallel_reposting: 4` có phù hợp với máy chủ không?
136. Role nào nhận Reposting Error Notification?
137. Có tự động repost incorrect valuation entries không?
138. Có bật Ledger Health Monitor không?
139. Có kiểm tra Debit-Credit Mismatch không?
140. Có kiểm tra General Ledger và Payment Ledger mismatch không?
141. Monitor kiểm tra bao nhiêu ngày gần nhất?
142. Các DocType nào được phép repost valuation?

## 11. Currency Exchange

143. Có cần tự động lấy exchange rate từ `frankfurter.dev` không?
144. Có chấp nhận chỉ dùng HTTPS không? Khuyến nghị là giữ `use_http: 0`.
145. `api_endpoint` có giữ nguyên placeholder `{from_currency}` và `{to_currency}` không?
146. Exchange rate cũ tối đa bao nhiêu ngày?
147. Khi không có rate mới, `Warn` hay `Stop` transaction?
148. Exchange Gain/Loss posting date là `Invoice`, `Payment` hay `Reconciliation Date`?
149. Có cần cho phép pegged currency không?
150. Các cặp AED, BHD, JOD, OMR, QAR và SAR có thực sự áp dụng không?
151. Người phụ trách tài chính đã xác nhận các pegged exchange rate chưa?
152. Có cho phép quy đổi qua pegged/intermediate currency không?

## 12. Asset, deferred accounting, print và delivery

153. Có sử dụng Asset Management trong product scope không?
154. Có tự động book Asset Depreciation Entry không?
155. Role nào nhận thông báo depreciation failure?
156. Deferred Revenue/Expense có được tự động process không?
157. Deferred entry ghi trực tiếp GL hay qua Journal Entry?
158. Deferred allocation tính theo `Days` hay `Months`?
159. Có dùng Global Defaults `disable_in_words` không?
160. Có ẩn `Rounded Total` không?
161. Có ẩn currency symbol không? Nếu có, chọn `Yes`; nếu không, dùng `No` hoặc để `''` theo quy ước đã thống nhất.
162. Có dùng posting datetime thay vì creation datetime khi đặt tên document không?
163. Có hiển thị Payment Schedule khi in không?
164. Có giới hạn độ dài Remarks trên GL và AR/AP không?
165. Có gộp các dòng cùng Account Head trên Ledger không?
166. Dispatch Notification có đính kèm Print Format không?
167. Email Template gửi Dispatch Notification là Template nào?
168. Giữa các Delivery Stop cần delay bao nhiêu phút?

## 13. Phân quyền và trách nhiệm xác nhận

169. Role nào được bypass Credit Limit?
170. Role nào được bypass Overdue Billing Threshold?
171. Role nào được over-bill?
172. Role nào được over-deliver hoặc over-receive?
173. Role nào được override hành động `Stop` trong Accounts, Buying, Selling và Stock?
174. Role nào được sửa back-dated transaction?
175. Role nào được sửa transaction sau khi stock freeze?
176. Role nào nhận depreciation failure?
177. Role nào nhận reposting failure?
178. Các Role đang để `null` là chưa quyết định hay chủ ý không cấp quyền?
179. Có cần tách quyền Accountant, Purchase Manager, Sales Manager, Stock User và Auditor không?
180. Ai ký xác nhận các câu trả lời liên quan đến Tax?
181. Ai ký xác nhận các câu trả lời liên quan đến Stock Valuation?
182. Ai ký xác nhận việc bật `Immutable Ledger` và quy trình correction?

## 14. Điều kiện hoàn tất questionnaire

Questionnaire chỉ được xem là hoàn tất khi policy có thể trả lời hoặc chỉ rõ
trạng thái của từng câu hỏi:

1. 20 câu bắt buộc ở mục 3 có câu trả lời và người xác nhận.
2. Mọi field có giá trị `null` trong policy đã được đánh dấu `Confirmed`,
   `Not applicable` hoặc `To decide`; nếu là `To decide` thì phải nêu rõ người
   chịu trách nhiệm và quyết định còn thiếu.
3. Các enum đã được chọn rõ ràng; không dùng giá trị ngoài enum trong comment
   của policy.
4. Tax Account, Company, Cost Center, Warehouse, Price List, Customer Group,
   Supplier Group và Role đều có linked record hợp lệ.
5. Người phụ trách nghiệp vụ ký xác nhận các giới hạn `allowance`, Credit Limit,
   Overdue, Negative Stock, Valuation Method và Tax.
6. Sau khi cập nhật policy, chạy validate, plan, apply, export và kiểm tra
   canonical round-trip trước khi dùng cho production.

Policy không được dùng comment để giả vờ trả lời một dữ kiện không tồn tại.
Comment phải giải thích ý nghĩa field và cách đọc giá trị; quyết định nghiệp vụ
phải nằm ở giá trị YAML hoặc ở trạng thái xác nhận trong checklist.

## 15. Tài liệu liên quan

- [`config/policy.yaml`](../config/policy.yaml): giá trị cấu hình thực tế.
- [`contracts/scope.yml`](../contracts/scope.yml): scope và classification của
  policy wrapper.
- [`Configuration_Inventory.md`](Configuration_Inventory.md): ownership,
  classification, coverage và acceptance evidence.
- [`ERP_PRD.md`](ERP_PRD.md): product scope, requirements và release gates.
