import {test,expect} from '../playwright.mjs';
import fs from 'node:fs';
import path from 'node:path';

const output=process.env.FRONTEND_ARTIFACT_DIR;
async function login(page,role='admin',url='./'){
 await page.goto(url);await page.getByLabel('Email',{exact:true}).fill(role+'@example.com');await page.getByLabel('Mật khẩu',{exact:true}).fill('TestParking123!');await page.getByRole('button',{name:'Đăng nhập',exact:true}).click();await expect(page.getByRole('heading',{name:'Tổng quan',exact:true})).toBeVisible();
}
async function nav(page,label){await page.getByRole('link',{name:label,exact:true}).click();}
async function photo(page,name){if(output){fs.mkdirSync(output,{recursive:true});const panel=page.locator('.research-panel').first();if(await panel.count()){await panel.scrollIntoViewIfNeeded();const box=await panel.boundingBox();await page.screenshot({path:path.join(output,name+'.png'),clip:{x:box.x,y:box.y,width:box.width,height:Math.min(box.height,700)}});}else await page.screenshot({path:path.join(output,name+'.png'),fullPage:false});}}
async function headers(page){return {Authorization:'Bearer '+await page.evaluate(()=>sessionStorage.getItem('parking-token'))};}
const base=process.env.E2E_API_URL;

test('Recommendation map preselects the vehicle and spot, admin edits routes visually',async({page,request})=>{
 await login(page,'customer');const auth=await headers(page);
 const vehicle=await(await request.post(base+'/vehicles',{headers:auth,data:{license_plate:'62B1-98543',vehicle_type:'MOTORBIKE',energy_type:'GASOLINE'}})).json();
 await page.getByRole('button',{name:'Làm mới',exact:true}).click();
 await nav(page,'Gợi ý & đường đi');await page.getByLabel('Phương tiện',{exact:true}).selectOption(String(vehicle.id));await page.getByRole('button',{name:'Tìm ô phù hợp',exact:true}).click();
 await expect(page.locator('.recommendations article').first()).toContainText('Đề xuất');await expect(page.getByRole('img',{name:'Sơ đồ đường đi đến ô đỗ'})).toBeVisible();
 await photo(page,'De-xuat-o-do-va-duong-di');await page.getByRole('button',{name:'Đặt ô này',exact:true}).first().click();
 await expect(page.getByLabel('Phương tiện',{exact:true}).last()).toHaveValue(String(vehicle.id));await expect(page.getByLabel('Ô đỗ phù hợp',{exact:true})).not.toHaveValue('');
 await page.getByRole('button',{name:'Đóng',exact:true}).last().click();await page.getByRole('button',{name:'Đăng xuất',exact:true}).click();await login(page);
 await nav(page,'Gợi ý & đường đi');await page.getByRole('button',{name:'Cấu hình mặt bằng',exact:true}).click();await page.getByLabel('Tên điểm',{exact:true}).fill('Cổng vào chính');await page.getByRole('button',{name:'Lưu mặt bằng',exact:true}).click();await expect(page.getByRole('status')).toContainText('Đã lưu sơ đồ');await photo(page,'Cau-hinh-mat-bang');
});

test('Sandbox checkout, separate revenue report, CSV and virtual relay use real APIs',async({page,request})=>{
 await login(page);const auth=await headers(page);
 const vehicle=await(await request.post(base+'/vehicles',{headers:auth,data:{license_plate:'63B1-98654',vehicle_type:'MOTORBIKE',energy_type:'GASOLINE'}})).json();
 const spots=await(await request.get(base+'/parking-spots?parking_lot_id=1',{headers:auth})).json();const spot=spots.find(s=>s.available_for_booking&&s.spot_type==='MOTORBIKE'&&s.energy_type==='GASOLINE');
 const entered=await request.post(base+'/parking-sessions/check-in',{headers:auth,data:{vehicle_id:vehicle.id,parking_spot_id:spot.id}});expect(entered.status()).toBe(201);const session=await entered.json();
 expect((await request.post(base+`/parking-sessions/${session.id}/check-out`,{headers:auth,data:{}})).status()).toBe(200);
 await page.getByRole('button',{name:'Làm mới',exact:true}).click();await nav(page,'Thanh toán thử');await page.getByLabel('Lượt gửi đã trả xe',{exact:true}).selectOption(String(session.id));await page.getByRole('button',{name:'Tạo giao dịch thử',exact:true}).click();await expect(page.getByAltText('QR mở trang thanh toán mô phỏng nội bộ')).toBeVisible();await photo(page,'QR-thanh-toan-noi-bo');
 const popupPromise=page.waitForEvent('popup');await page.getByRole('link',{name:'Mở trang thanh toán thử',exact:true}).click();const popup=await popupPromise;await expect(popup.getByRole('heading',{name:'Thanh toán mô phỏng nội bộ',exact:true})).toBeVisible();await popup.getByRole('button',{name:'Mô phỏng thành công',exact:true}).click();await expect(popup.locator('body')).toContainText('SUCCESS');await popup.close();
 await page.getByRole('button',{name:'Kiểm tra kết quả',exact:true}).click();await expect(page.locator('.checkout-card')).toContainText('SUCCESS');await photo(page,'Thanh-toan-thanh-cong');
 await nav(page,'Báo cáo');await expect(page.locator('.report-totals')).toContainText('thử nghiệm');await photo(page,'Bao-cao-doanh-thu-luu-luong');const download=page.waitForEvent('download');await page.getByRole('button',{name:'Xuất CSV / mở bằng Excel',exact:true}).click();expect((await download).suggestedFilename()).toMatch(/parkly.*\.csv/);
 await nav(page,'Camera & cổng');await expect(page.getByRole('heading',{name:'Barie cổng A · mô phỏng',exact:true})).toBeVisible();await expect(page.locator('.barrier-panel')).toContainText('Lượt #'+session.id);await photo(page,'Camera-YOLO-va-barrier-mo-phong');
});

test('Time-band pricing is configurable and report screens fit mobile',async({page})=>{
 await login(page);await nav(page,'Giá ngày / đêm');const select=page.getByLabel('Nhóm xe',{exact:true});await select.selectOption({index:4});await page.getByLabel('Ngày 07:00–19:00 (VND/giờ)',{exact:true}).fill('10000');await page.getByLabel('Đêm 19:00–07:00 (VND/giờ)',{exact:true}).fill('15000');await page.getByRole('button',{name:'Áp dụng lịch ngày / đêm',exact:true}).click();await expect(page.getByRole('status')).toContainText('Đã cập nhật khung giờ');await photo(page,'Bang-gia-ngay-dem');
 await page.setViewportSize({width:390,height:844});await page.getByRole('button',{name:'Mở menu',exact:true}).click();await nav(page,'Báo cáo');await expect(page.getByRole('heading',{name:'Doanh thu & lưu lượng theo ngày'})).toBeVisible();expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();await photo(page,'Bao-cao-tren-dien-thoai');
});

test('Built dashboard itemizes an electric checkout and reconciles the cash receipt',async({page,request})=>{
 await login(page,'admin',base+'/dashboard/');
 const auth=await headers(page);
 const registered=await request.post(base+'/vehicles',{headers:auth,data:{license_plate:'56F-98123',vehicle_type:'CAR',energy_type:'ELECTRIC'}});
 expect(registered.status()).toBe(201);
 const vehicle=await registered.json();
 const spots=await (await request.get(base+'/parking-spots?parking_lot_id=1',{headers:auth})).json();
 const spot=spots.find(item=>item.available_for_booking&&item.spot_type==='CAR'&&item.energy_type==='ELECTRIC');
 expect(spot).toBeTruthy();
 const entered=await request.post(base+'/parking-sessions/check-in',{headers:auth,data:{vehicle_id:vehicle.id,parking_spot_id:spot.id}});
 expect(entered.status()).toBe(201);
 const session=await entered.json();
 await page.getByRole('button',{name:'Làm mới',exact:true}).click();
 await nav(page,'Xe vào / ra');
 const row=page.getByRole('row').filter({hasText:vehicle.license_plate});
 await row.getByRole('button',{name:'Xe ra',exact:true}).click();
 const departure=page.waitForResponse(r=>new URL(r.url()).pathname===`/parking-sessions/${session.id}/check-out`);
 await page.getByRole('button',{name:'Xác nhận xe ra',exact:true}).click();
 const checkedOut=await departure;
 expect(checkedOut.status()).toBe(200);
 const checked=await checkedOut.json();
 expect(checked.fee_breakdown.billed_hours).toBe(1);
 expect(Number(checked.fee_breakdown.charging_fee)).toBe(0);
 const dialog=page.getByRole('dialog');
 const feeLabel='Chi tiết phí lượt '+session.id;
 await row.getByRole('button',{name:feeLabel,exact:true}).click();
 await expect(dialog.getByRole('heading',{name:'Chi tiết phí gửi xe'})).toBeVisible();
 await expect(dialog).toContainText('Phụ phí sạc điện');
 await expect(dialog).toContainText('Số giờ tính phí');
 await expect(dialog.getByRole('table')).toContainText('Đơn giá');
 await dialog.getByRole('button',{name:'Đóng',exact:true}).last().click();

 await row.getByRole('button',{name:'Thu tiền',exact:true}).click();
 await expect(dialog).toContainText('Tổng phải trả');
 const paymentResponse=page.waitForResponse(r=>new URL(r.url()).pathname==='/payments'&&r.request().method()==='POST');
 await dialog.getByRole('button',{name:'Đã nhận tiền',exact:true}).click();
 const paid=await paymentResponse;
 expect(paid.status()).toBe(201);
 const payment=await paid.json();
 expect(Number(payment.amount)).toBe(Number(checked.total_amount));
 await expect(dialog).not.toBeVisible();
 await nav(page,'Báo cáo');
 const day=payment.paid_at.slice(0,10);
 await page.getByRole('button',{name:'Đối soát ngày '+day,exact:true}).click();
 const receipts=page.getByRole('region',{name:'Đối soát ngày '+day,exact:true});
 await expect(receipts.getByRole('heading')).toBeFocused();
 const receipt=receipts.getByRole('row').filter({hasText:payment.transaction_code});
 await expect(receipt).toContainText('Thực thu');
 await expect(receipt).toContainText('Khớp');
 await receipt.getByRole('button',{name:feeLabel,exact:true}).click();
 await expect(dialog).toContainText('Ô tô điện');
 await page.setViewportSize({width:390,height:844});
 await expect(dialog).toBeVisible();
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
 if(output){
  fs.mkdirSync(output,{recursive:true});
  await dialog.screenshot({path:path.join(output,'Chi-tiet-phi-gui-xe-dien.png')});
  await page.setViewportSize({width:1280,height:900});
  await dialog.getByRole('button',{name:'Đóng',exact:true}).last().click();
  await expect(page.locator('.toast')).toBeHidden();
  await receipts.screenshot({path:path.join(output,'Doi-soat-doanh-thu.png')});
 }
});

test('POS issues a signed QR ticket and looks up a session without changing it',async({page,request})=>{
 await login(page);const auth=await headers(page);const rows=await(await request.get(base+'/parking-sessions',{headers:auth})).json();expect(rows.length).toBeGreaterThan(0);
 const ticket=await(await request.get(base+`/parking-sessions/${rows[0].id}/ticket`,{headers:auth})).json();
 await nav(page,'POS · Quét vé');await page.getByLabel('Mã vé Parkly',{exact:true}).fill(ticket.code);await page.getByRole('button',{name:'Tra cứu vé',exact:true}).click();await expect(page.locator('.checkout-card').first()).toContainText('Lượt #'+rows[0].id);await photo(page,'POS-quet-ve-co-chu-ky');
 await page.getByLabel('Mã vé Parkly',{exact:true}).fill('not-a-parkly-ticket');await page.getByRole('button',{name:'Tra cứu vé',exact:true}).click();await expect(page.getByRole('alert')).toContainText('không phải vé gửi xe');
 const after=await(await request.get(base+`/parking-sessions/${rows[0].id}`,{headers:auth})).json();expect(after.status).toBe(rows[0].status);
});
