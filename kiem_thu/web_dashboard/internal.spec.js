import {test,expect} from '../playwright.mjs';
import fs from 'node:fs';
import path from 'node:path';

async function login(page,role='admin'){
 await page.goto('./');await page.getByLabel('Email',{exact:true}).fill(role+'@example.com');await page.getByLabel('Mật khẩu',{exact:true}).fill('TestParking123!');await page.getByRole('button',{name:'Đăng nhập',exact:true}).click();await expect(page.getByRole('heading',{name:'Tổng quan',exact:true})).toBeVisible();
}
async function nav(page,name){await page.getByRole('link',{name,exact:true}).click();}
async function auth(page){return {Authorization:'Bearer '+await page.evaluate(()=>sessionStorage.getItem('parking-token'))};}
async function shot(page,name){if(process.env.FRONTEND_ARTIFACT_DIR){fs.mkdirSync(process.env.FRONTEND_ARTIFACT_DIR,{recursive:true});await page.screenshot({path:path.join(process.env.FRONTEND_ARTIFACT_DIR,name+'.png'),fullPage:true});}}

test('Internal one-click flow runs actual AI, holds the spot for QR payment and opens the gate',async({page,request})=>{
 test.setTimeout(90000);await login(page);const headers=await auth(page),base=process.env.E2E_API_URL;
 const revenue=(await(await request.get(base+'/reports/summary',{headers})).json()).revenue;
 await nav(page,'Giả lập vận hành');await expect(page.getByRole('heading',{name:'Giả lập vận hành ngay trong Parkly'})).toBeVisible();
 await page.getByRole('button',{name:'Ô tô điện vào đỗ và sạc',exact:true}).click();
 const result=page.getByTestId('preset-result');await expect(result).toContainText('AI đọc:',{timeout:45000});await expect(result).toContainText('16F27080');await expect(result.getByRole('img',{name:'Ảnh crop biển số do AI phát hiện'})).toBeVisible();
 const state=await(await request.get(base+'/internal-simulation/state?parking_lot_id=1',{headers})).json();const entry=state.runs.find(r=>r.kind==='ENTRY'&&r.status==='DONE');expect(entry).toBeTruthy();
 await expect(page.getByTestId('internal-spot-'+entry.result.spot_code)).toContainText('Có xe');await expect(page.getByTestId('internal-spot-'+entry.result.spot_code)).toContainText('7 kW');
 await expect(page.getByRole('img',{name:'Barie cổng vào đang mở',exact:true})).toBeVisible({timeout:7000});
 await page.getByRole('button',{name:'Xe ra và thanh toán',exact:true}).click();await expect(page.getByAltText('QR thanh toán mô phỏng cho xe mẫu')).toBeVisible();await expect(page.getByTestId('internal-spot-'+entry.result.spot_code)).toContainText('Có xe');
 await shot(page,'Gia-lap-noi-bo-QR-cho-thanh-toan');
 await page.getByRole('button',{name:'Xác nhận thanh toán mô phỏng',exact:true}).click();await expect(result).toContainText('Đã hoàn tất thanh toán thử và trả ô đỗ.');await expect(page.getByTestId('internal-spot-'+entry.result.spot_code)).toContainText('Còn trống');
 expect((await(await request.get(base+'/reports/summary',{headers})).json()).revenue).toBe(revenue);
 const payments=await(await request.get(base+'/payments?parking_session_id='+entry.parking_session_id,{headers})).json();expect(payments).toHaveLength(1);expect(payments[0].transaction_code).toMatch(/^SANDBOX-INTERNAL-/);
});

test('Sample camera reads uploaded bytes, displays crop and rejects a blank image without check-in',async({page,request})=>{
 test.setTimeout(90000);await login(page);await nav(page,'Xe vào / ra');const headers=await auth(page),base=process.env.E2E_API_URL;
 const before=(await(await request.get(base+'/parking-sessions',{headers})).json()).length;
 await page.getByRole('button',{name:'Nhận diện AI',exact:true}).click();await page.getByRole('button',{name:'Chuẩn bị xe mẫu nếu chưa đăng ký'}).click();
 await page.getByLabel('Ảnh camera mẫu',{exact:true}).selectOption('car_gas_tilted');await page.getByRole('button',{name:'Giả lập camera chụp ảnh',exact:true}).click();
 await expect(page.getByLabel('Biển số nhận diện',{exact:true})).toHaveValue('53F17609',{timeout:30000});await expect(page.getByAltText('Khung nhận diện biển số do AI tính')).toBeVisible();await expect(page.getByAltText('Ảnh crop biển số từ mô hình AI')).toBeVisible();
 await shot(page,'Camera-anh-mau-YOLO-OCR');
 await page.getByLabel('Ảnh camera mẫu',{exact:true}).selectOption('blank');await page.getByRole('button',{name:'Giả lập camera chụp ảnh',exact:true}).click();await expect(page.getByLabel('Biển số nhận diện',{exact:true})).toHaveValue('');await expect(page.getByRole('button',{name:'Xác nhận xe vào',exact:true})).toBeDisabled();
 expect((await(await request.get(base+'/parking-sessions',{headers})).json()).length).toBe(before);
});

test('Internal sensor and 70-degree heat update the actual parking and charging pages over sockets',async({page,request})=>{
 await login(page);const headers=await auth(page),base=process.env.E2E_API_URL;
 const devices=await(await request.get(base+'/iot/devices?parking_lot_id=1',{headers})).json();const spots=await(await request.get(base+'/parking-spots?parking_lot_id=1',{headers})).json();
 const gas=spots.find(s=>s.spot_type==='MOTORBIKE'&&s.energy_type==='GASOLINE'&&s.status==='AVAILABLE'&&!devices.some(d=>d.parking_spot_id===s.id));
 const electric=spots.find(s=>s.energy_type==='ELECTRIC'&&s.charger_status==='READY'&&!devices.some(d=>d.parking_spot_id===s.id));expect(gas).toBeTruthy();expect(electric).toBeTruthy();
 await nav(page,'Giả lập vận hành');await page.getByLabel('Tìm ô đỗ mô phỏng',{exact:true}).fill(gas.spot_code);await page.getByTestId('internal-spot-'+gas.spot_code).getByRole('button',{name:'Có xe',exact:true}).click();
 await expect(page.getByTestId('internal-spot-'+gas.spot_code)).toContainText('Có xe');await nav(page,'Sơ đồ bãi xe');await expect(page.getByRole('button',{name:`Ô ${gas.spot_code} — Có xe`,exact:true})).toBeVisible();
 await nav(page,'Giả lập vận hành');await page.getByLabel('Tìm ô đỗ mô phỏng',{exact:true}).fill(gas.spot_code);await page.getByTestId('internal-spot-'+gas.spot_code).getByRole('button',{name:'Trống',exact:true}).click();
 await page.getByLabel('Tìm ô đỗ mô phỏng',{exact:true}).fill(electric.spot_code);await page.getByTestId('internal-spot-'+electric.spot_code).getByRole('button',{name:'Quá nhiệt 70 °C',exact:true}).click();
 await nav(page,'Sạc & thiết bị IoT');await expect(page.getByRole('row').filter({has:page.getByText(electric.spot_code,{exact:true})})).toContainText('70 °C');
 await nav(page,'Cảnh báo & sự cố');await expect(page.getByRole('row').filter({hasText:electric.spot_code}).filter({hasText:'Quá nhiệt'})).toBeVisible();
 await nav(page,'Giả lập vận hành');await page.getByLabel('Tìm ô đỗ mô phỏng',{exact:true}).fill(electric.spot_code);await page.getByTestId('internal-spot-'+electric.spot_code).getByRole('button',{name:'Sạc bình thường',exact:true}).click();
});

test('Management simulator fits a phone and stays hidden from security staff',async({page})=>{
 await page.setViewportSize({width:390,height:844});await login(page);await page.getByRole('button',{name:'Mở menu'}).click();await nav(page,'Giả lập vận hành');await expect(page.getByRole('heading',{name:'Kịch bản một nút'})).toBeVisible();expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBeTruthy();
 await page.getByRole('button',{name:'Mở menu'}).click();await page.getByRole('button',{name:'Đăng xuất',exact:true}).click();await login(page,'security');await page.getByRole('button',{name:'Mở menu'}).click();await expect(page.getByRole('link',{name:'Giả lập vận hành',exact:true})).toHaveCount(0);
});
