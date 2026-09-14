# Tax Matrix — Letron Holding

**Trạng thái:** DRAFT — chờ kế toán trưởng phê duyệt và chốt VAT Account  
**Company:** Letron Holding
**Currency:** VND  
**Nguồn cấu hình sau phê duyệt:** `config/policy.yaml`

## 1. Mục đích

Tài liệu này xác định cách chọn Tax Category, Tax Rule, Tax Template và VAT
Account trước khi đưa cấu hình vào ERP. ERP chỉ thực thi matrix đã được phê
duyệt; không tự suy đoán mức thuế từ tên Item hoặc mô tả giao dịch.

## 2. Dữ liệu hiện có trong policy

### Căn cứ pháp lý cần đối chiếu

Luật Thuế giá trị gia tăng số 48/2024/QH15 có hiệu lực từ 2025-07-01. Điều 5
khoản 21 liệt kê sản phẩm phần mềm và dịch vụ phần mềm là đối tượng không chịu
VAT; Điều 9 khoản 3 quy định mức 10% cho hàng hóa, dịch vụ không thuộc nhóm
0% hoặc 5%. Đây là căn cứ phân loại ban đầu, không thay thế việc đối chiếu
hợp đồng và hồ sơ chứng minh sản phẩm/dịch vụ cụ thể.

### Trạng thái audit kỹ thuật

Policy đã tách đúng tài khoản theo bản chất: VAT đầu vào dùng TK `1331`
(`root_type: Asset`), còn VAT đầu ra dùng TK `33311`
(`root_type: Liability`). Đây là trạng thái đã có trong policy và controller
native; vẫn chưa phải là phê duyệt Tax Matrix hay nghiệm thu hóa đơn thực tế.

COA Account được materialize từ shared policy bằng native Account controller.
Tax templates chỉ được tham chiếu các Account đã có trong COA; controller không
tự suy đoán hoặc tạo một tax account mới khi Tax Matrix chưa được phê duyệt.

| Luồng | Template | Tax Category | Rate | Tax Account | Cost Center | Trạng thái |
|---|---|---:|---:|---|---|---|
| Sales | `Vietnam Tax - LTVN` | Không giới hạn (`null`) | 10% | `33311 - Thuế GTGT đầu ra` | `Main - LTVN` | Đã có trong policy |
| Purchase | `Vietnam Tax - LTVN` | Không giới hạn (`null`) | 10% | `1331 - Thuế GTGT được khấu trừ của hàng hóa, dịch vụ` | `Main - LTVN` | Có cấu hình kỹ thuật; chưa đạt accounting acceptance |
| Item (sales-oriented) | `Vietnam Tax - LTVN` | Không giới hạn (`null`) | 10% | `33311 - Thuế GTGT đầu ra` | `Main - LTVN` | Đã có trong policy |

## 3. Hoạt động kinh doanh đã xác định

| Nhóm hoạt động | ERP cần phân biệt | Baseline suy luận | Trạng thái |
|---|---|---|---|
| Bán hàng hóa | Hàng hóa bán trong nước; hàng xuất khẩu nếu có | 10% cho hàng hóa thông thường trong nước | Provisional |
| Dịch vụ giải pháp công nghệ | Khách hàng chỉ được license sử dụng; không chuyển giao source code/quyền sở hữu | Phân loại là sản phẩm/dịch vụ phần mềm; không chịu VAT nếu đáp ứng định nghĩa pháp lý | Classified, non-VAT candidate |
| Tư vấn/triển khai/bảo trì | Được gộp trong một hợp đồng công nghệ; nếu là software service | Theo nhóm software service không chịu VAT nếu đáp ứng định nghĩa pháp lý | Classified, non-VAT candidate |
| Hosting | Được gộp trong một hợp đồng công nghệ nhưng phải tách component | Baseline 10% tạm thời | Classified, rate pending |
| Outsourcing | Gia công trực tiếp sản phẩm/dịch vụ phần mềm; IP thuộc khách hàng | Không chịu VAT nếu đáp ứng định nghĩa software service; không phải cung ứng nhân sự | Classified, non-VAT candidate |
| Vận tải | Vận tải nội địa hay vận tải quốc tế | 10% tạm thời cho vận tải nội địa thông thường | Provisional |
| Sản xuất | Nguyên vật liệu đầu vào, thành phẩm đầu ra, phế liệu nếu có | Mỗi dòng theo loại hàng hóa/dịch vụ thực tế | Pending classification |
| Mua hàng/dịch vụ | Mua nguyên liệu, hàng hóa, thuê ngoài, vận tải | VAT đầu vào theo hóa đơn hợp lệ và loại mua vào | Provisional |

## 4. Các dòng cần kế toán xác nhận

| Mã dòng | Loại giao dịch | Mô tả hàng hóa/dịch vụ | VAT rate | Tax Category | Sales template | Purchase template | VAT Account | Effective from | Effective to | Căn cứ nghiệp vụ | Phê duyệt |
|---|---|---|---:|---|---|---|---|---|---|---|---|
| TM-00 | Sales/Purchase | Không chịu thuế | Chưa xác nhận | Chưa xác nhận | Chưa xác nhận | Chưa xác nhận | Chưa xác nhận | Chưa xác nhận | Chưa xác nhận | Chưa xác nhận | Pending |
| TM-01 | Sales/Purchase | Thuế suất 0% | Chưa xác nhận | Chưa xác nhận | Chưa xác nhận | Chưa xác nhận | Chưa xác nhận | Chưa xác nhận | Chưa xác nhận | Chưa xác nhận | Pending |
| TM-02 | Sales/Purchase | Thuế suất 5% | Chưa xác nhận | Chưa xác nhận | Chưa xác nhận | Chưa xác nhận | Chưa xác nhận | Chưa xác nhận | Chưa xác nhận | Chưa xác nhận | Pending |
| TM-03 | Sales/Purchase | Thuế suất 8% nếu thuộc diện áp dụng | Chưa xác nhận | Chưa xác nhận | Chưa xác nhận | Chưa xác nhận | Chưa xác nhận | Chưa xác nhận | Chưa xác nhận | Chưa xác nhận | Pending |
| TM-04 | Sales/Purchase | Thuế suất 10% | 10% | Chưa xác nhận | `Vietnam Tax - LTVN` hoặc template mới | `Vietnam Tax - LTVN` hoặc template mới | `VAT - LTVN` hoặc tài khoản mới | Chưa xác nhận | Chưa xác nhận | Chưa xác nhận | Pending |
| TM-05 | Item-specific | Mức thuế theo từng nhóm Item | Chưa xác nhận | Chưa xác nhận | Chưa xác nhận | Chưa xác nhận | Chưa xác nhận | Chưa xác nhận | Chưa xác nhận | Chưa xác nhận | Pending |
| TM-06 | Technology license | License sử dụng phần mềm; không chuyển giao source code/quyền sở hữu | Không chịu VAT nếu đáp ứng định nghĩa software product/service | Domestic Software - Non-VAT | Template non-VAT | Template mua non-VAT | Không phát sinh VAT output | Chưa xác nhận | Chưa xác nhận | Phải đối chiếu quyền sử dụng, sản phẩm và dịch vụ đi kèm | Classified, non-VAT candidate |
| TM-07 | Software service bundle | Tư vấn/triển khai/bảo trì phần mềm trong hợp đồng gói chung | Không chịu VAT nếu đáp ứng định nghĩa software service | Domestic Software - Non-VAT | Template non-VAT | Template mua non-VAT | Không phát sinh VAT output | Chưa xác nhận | Chưa xác nhận | Invoice phải có component rõ ràng dù hợp đồng là một gói | Classified, non-VAT candidate |
| TM-08 | Hosting | Hosting trong hợp đồng gói chung | Tạm 10% | Domestic Hosting | `Vietnam Tax - LTVN` | `Vietnam Tax - LTVN` | `VAT - LTVN` hiện có | Chưa xác nhận | Chưa xác nhận | Phải tách khỏi software service | Provisional |
| TM-09 | Software outsourcing | Gia công trực tiếp; sản phẩm/IP thuộc khách hàng | Không chịu VAT nếu đáp ứng định nghĩa software service | Domestic Software - Non-VAT | Template non-VAT | Template mua non-VAT | Không phát sinh VAT output | Chưa xác nhận | Chưa xác nhận | Không phải cung ứng nhân sự; phải lưu ownership trong hồ sơ hợp đồng | Classified, non-VAT candidate |
| TM-10 | Transport | Vận tải nội địa | Tạm 10% | Domestic Transport | `Vietnam Tax - LTVN` | `Vietnam Tax - LTVN` | `VAT - LTVN` hiện có | Chưa xác nhận | Chưa xác nhận | Hợp đồng/chặng vận tải nội địa | Provisional |

Các dòng trên không có nghĩa mọi mức thuế đều áp dụng cho Letron. Kế toán phải
xóa dòng không sử dụng và điền căn cứ áp dụng cho dòng còn lại.

## 5. Câu hỏi bắt buộc trước khi cấu hình

1. Công ty có thực tế phát sinh giao dịch VAT 0%, 5%, 8% hoặc chỉ 10%?
2. Có hàng hóa/dịch vụ không chịu thuế hoặc miễn thuế không?
3. Sales và Purchase có dùng cùng VAT Account không?
4. Có cần phân biệt Tax Category theo Customer/Supplier, địa chỉ hoặc loại Item không?
5. Tax Rule có thời hạn hiệu lực khác nhau theo năm hoặc theo loại giao dịch không?
6. VAT đã bao gồm trong giá (`included_in_print_rate`) hay cộng thêm trên giá chưa thuế?
7. Có trường hợp Tax là `Actual`, `On Previous Row Amount` hoặc `On Item Quantity` không?
8. Có cần tách VAT đầu vào được khấu trừ và không được khấu trừ bằng các Account khác nhau không?
9. Template nào được phép làm default? Có được phép để nhiều template cùng default không?
10. Ai phê duyệt thay đổi Tax Matrix và từ ngày nào thay đổi có hiệu lực?
11. Hợp đồng bản quyền là cấp quyền sử dụng phần mềm, bán sản phẩm phần mềm hay chuyển giao quyền sở hữu? **Đã trả lời: chỉ cấp license sử dụng.**
12. Phí tư vấn, triển khai, bảo trì và hosting có tách thành từng dòng trên hợp đồng/hóa đơn không? **Đã trả lời: hợp đồng gói chung; ERP vẫn phải tách component khi cần áp dụng khác nhau.**
13. Gia công trực tiếp tạo ra sản phẩm/dịch vụ phần mềm theo yêu cầu của khách hàng hay chỉ thực hiện một phần công đoạn? **Đã trả lời: gia công trực tiếp, IP thuộc khách hàng.**
14. Vận tải chỉ chạy trong Việt Nam hay có chặng quốc tế? **Đã trả lời: chỉ vận tải nội địa.**
15. Sản phẩm sản xuất là sản phẩm gì và có bán kèm dịch vụ triển khai không?

## 6. Quy tắc đưa vào policy

Chỉ đưa một dòng vào `config/policy.yaml` khi đủ các giá trị:

- Company;
- Template name/title;
- Tax Category hoặc xác nhận `null` là có chủ ý;
- Tax Rule và thời hạn hiệu lực nếu có;
- VAT Account;
- Cost Center;
- rate/charge type/category/add-deduct;
- effective date và người phê duyệt trong hồ sơ nghiệp vụ.

Không đưa vào policy:

- certificate/API key/provider credential;
- mã hóa đơn điện tử do provider cấp;
- GL Entry hoặc tax amount đã tính;
- mức thuế chưa được phê duyệt.

## 7. Tiêu chí nghiệm thu sau khi được phê duyệt

Với từng dòng Tax Matrix:

1. Tax Rule chọn đúng Sales/Purchase Template.
2. Sales Invoice tính đúng tax amount.
3. Purchase Invoice tính đúng tax amount.
4. Submit tạo đúng debit/credit trong GL Entry.
5. Currency và rounding đúng theo Company.
6. Cancel/amend tạo reversal đúng.
7. Tax Category không phù hợp không được chọn nhầm template.
8. Cấu hình có thể export/readback và tái tạo trên disposable tenant.

## 8. Quyết định hiện tại

Toàn bộ khách hàng hiện được xác định là khách hàng Việt Nam. Không đưa VAT 0%
theo giao dịch xuất khẩu vào policy. Chưa được phép thay đổi policy ngoài cấu
hình VAT 10% hiện có; các dòng phần mềm còn lại phải được phân loại là chịu
thuế hoặc không chịu thuế theo bản chất pháp lý trước khi cấu hình.
