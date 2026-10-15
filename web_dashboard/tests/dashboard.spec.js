import {test,expect} from '@playwright/test';
import path from 'node:path';
import fs from 'node:fs';
const artifacts=process.env.FRONTEND_ARTIFACT_DIR;

test('Customer registers a complete profile and vehicle, then updates profile after login',async({page})=>{
 await page.goto('');await page.getByRole('button',{name:'Đăng ký',exact:true}).click();
 await page.getByLabel('Họ và tên',{exact:true}).fill('Nguyễn Hoàng Mai');
 await page.getByLabel('Ngày tháng năm sinh',{exact:true}).fill('2002-04-23');
 await page.getByLabel('Quê quán',{exact:true}).fill('Đà Nẵng');
 await page.getByLabel('Email',{exact:true}).fill('profile-ui@example.com');
 await page.getByLabel('Mật khẩu',{exact:true}).fill('TestProfile123!');
 await expect(page.getByLabel('Biển số xe',{exact:true})).toHaveAttribute('placeholder','VD: 29-B1 555.55');
 await page.getByLabel('Loại xe',{exact:true}).selectOption('CAR');
 await expect(page.getByLabel('Biển số xe',{exact:true})).toHaveAttribute('placeholder','VD: 30F-222.22');
 await page.getByLabel('Biển số xe',{exact:true}).fill('30F-543.21');
 await page.getByLabel('Nguồn năng lượng',{exact:true}).selectOption('ELECTRIC');
 if(artifacts)await page.screenshot({path:path.join(artifacts,'Dang-ky-thong-tin-khach-hang.png'),fullPage:true});
 await page.getByRole('button',{name:'Tạo tài khoản',exact:true}).click();
 await expect(page.getByRole('heading',{name:'Tổng quan',exact:true})).toBeVisible();
 await nav(page,'Thông tin của tôi');
 await expect(page.getByLabel('Ngày tháng năm sinh',{exact:true})).toHaveValue('2002-04-23');
 await expect(page.getByLabel('Quê quán',{exact:true})).toHaveValue('Đà Nẵng');
 await expect(page.getByRole('row').filter({hasText:'30F-543.21'})).toContainText('Ô tô điện');
 await page.getByLabel('Quê quán',{exact:true}).fill('Huế');
 await page.getByRole('button',{name:'Lưu thông tin',exact:true}).click();
 await expect(page.getByRole('status')).toHaveText('Đã lưu thông tin cá nhân.');
 await page.reload();await expect(page.getByLabel('Quê quán',{exact:true})).toHaveValue('Huế');
 await page.getByRole('button',{name:'Chỉnh sửa xe',exact:true}).click();
 await page.getByLabel('Biển số',{exact:true}).fill('30F-543.22');
 await page.getByRole('button',{name:'Lưu / xác nhận',exact:true}).click();await saved(page);
 await expect(page.getByText('30F-543.22',{exact:true})).toBeVisible();
 if(artifacts)await page.screenshot({path:path.join(artifacts,'Thong-tin-khach-hang.png'),fullPage:true});
 await page.getByRole('button',{name:'Đăng xuất',exact:true}).click();
 await login(page);await nav(page,'Tài khoản');
 const row=page.getByRole('row').filter({hasText:'profile-ui@example.com'});
 await expect(row).toContainText('23/04/2002');await expect(row).toContainText('Huế');await expect(row).toContainText('30F-543.22');
});

test('Mobile registration shows all profile fields and rejects a duplicate plate before creating an account',async({page})=>{
 await page.setViewportSize({width:390,height:844});await page.goto('');await page.getByRole('button',{name:'Đăng ký',exact:true}).click();
 await page.getByLabel('Họ và tên',{exact:true}).fill('Khách Trùng Biển');
 await page.getByLabel('Ngày tháng năm sinh',{exact:true}).fill('2000-02-29');
 await page.getByLabel('Quê quán',{exact:true}).fill('Hà Nội');
 await page.getByLabel('Email',{exact:true}).fill('profile-retry@example.com');
 await page.getByLabel('Mật khẩu',{exact:true}).fill('TestProfile123!');
 await page.getByLabel('Biển số xe',{exact:true}).fill('51A 111.11');
 await page.getByRole('button',{name:'Tạo tài khoản',exact:true}).click();
 await expect(page.getByRole('alert')).toContainText('Biển số xe đã được đăng ký');
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
 if(artifacts)await page.screenshot({path:path.join(artifacts,'Dang-ky-khach-hang-dien-thoai.png'),fullPage:true});
 await page.getByLabel('Biển số xe',{exact:true}).fill('29-B1 334.45');
 await page.getByRole('button',{name:'Tạo tài khoản',exact:true}).click();
 await expect(page.getByRole('heading',{name:'Tổng quan',exact:true})).toBeVisible();
});
async function login(page,role='admin'){
 await page.goto('');await page.getByLabel('Email',{exact:true}).fill(role+'@example.com');await page.getByLabel('Mật khẩu',{exact:true}).fill('TestParking123!');await page.getByRole('button',{name:'Đăng nhập',exact:true}).click();await expect(page.getByRole('heading',{name:'Tổng quan',exact:true})).toBeVisible();await expect(page.getByText('Không gian bãi xe',{exact:true})).toBeVisible();
}
async function nav(page,label){await page.getByRole('link',{name:label,exact:true}).click();}
async function saved(page){await expect(page.getByRole('dialog')).toHaveCount(0);}

test('Admin completes vehicle, check-in, checkout and payment through real APIs',async({page})=>{
 const errors=[];page.on('pageerror',e=>errors.push(e.message));await login(page);
 if(artifacts){fs.mkdirSync(artifacts,{recursive:true});await page.screenshot({path:path.join(artifacts,'Frontend-Tong-quan.png'),fullPage:true});}
 await nav(page,'Phương tiện');await page.getByRole('button',{name:'Thêm xe của tôi'}).click();await page.getByLabel('Biển số',{exact:true}).fill('51A-98765');await page.getByLabel('Loại phương tiện',{exact:true}).selectOption('CAR');await page.getByRole('button',{name:'Lưu / xác nhận',exact:true}).click();await saved(page);await expect(page.getByText('51A-98765',{exact:true})).toBeVisible();
 await nav(page,'Xe vào / ra');await page.getByRole('button',{name:'Xe vào',exact:true}).click();await page.getByLabel('Phương tiện',{exact:true}).selectOption({label:'51A-98765 · Ô tô xăng'});await page.getByLabel('Ô đỗ phù hợp',{exact:true}).selectOption({label:'CG-001 · Ô tô xăng'});await page.getByRole('button',{name:'Ghi nhận xe vào',exact:true}).click();await saved(page);
 let row=page.getByRole('row').filter({hasText:'51A-98765'});await expect(row.getByText('Đang gửi',{exact:true})).toBeVisible();await row.getByRole('button',{name:'Xe ra',exact:true}).click();await page.getByRole('button',{name:'Xác nhận xe ra',exact:true}).click();await saved(page);await expect(row.getByText('Hoàn tất',{exact:true})).toBeVisible();await row.getByRole('button',{name:'Thu tiền',exact:true}).click();await expect(page.getByRole('dialog').getByText('10.000 ₫',{exact:true})).toBeVisible();await page.getByRole('button',{name:'Đã nhận tiền',exact:true}).click();await saved(page);
 await row.getByRole('button',{name:'Thu tiền',exact:true}).click();await page.getByRole('button',{name:'Đã nhận tiền',exact:true}).click();await expect(page.getByRole('alert')).toContainText('đã thanh toán');await page.getByRole('button',{name:'Đóng',exact:true}).last().click();
 await nav(page,'Thanh toán');await expect(page.getByText('Đã thanh toán',{exact:true})).toBeVisible();expect(errors).toEqual([]);
});

test('Parking filters, charging commissioning and pricing',async({page})=>{
 await login(page);await nav(page,'Sơ đồ bãi xe');await expect(page.getByRole('button',{name:/^Ô [A-Z]/})).toHaveCount(170);
 await page.getByRole('button',{name:'Ô tô điện',exact:true}).click();await expect(page.getByRole('button',{name:/^Ô [A-Z]/})).toHaveCount(20);
 if(artifacts)await page.screenshot({path:path.join(artifacts,'Frontend-So-do-xe-dien.png'),fullPage:true});
 await page.getByRole('button',{name:'Ô CE-011 — Còn trống',exact:true}).click();await expect(page.getByRole('dialog').getByText('Chưa sẵn sàng',{exact:true})).toBeVisible();await expect(page.getByRole('button',{name:'Đặt chỗ này'})).toHaveCount(0);await page.getByRole('button',{name:'Đóng',exact:true}).last().click();
 await nav(page,'Sạc & thiết bị IoT');const charging=page.getByRole('row').filter({hasText:'CE-011'});await charging.getByRole('button',{name:'Cập nhật'}).click();await page.getByLabel('Trạng thái vận hành').selectOption('READY');await page.getByRole('button',{name:'Lưu / xác nhận'}).click();await saved(page);await expect(charging.getByText('Sẵn sàng',{exact:true})).toBeVisible();
 await nav(page,'Bảng giá & bãi xe');await page.getByRole('article').filter({has:page.getByRole('heading',{name:'Ô tô điện',exact:true})}).getByRole('button',{name:'Chỉnh sửa giá'}).click();await page.getByLabel('Giá giờ đầu (đồng)',{exact:true}).fill('12000');await page.getByRole('button',{name:'Lưu / xác nhận'}).click();await saved(page);await expect(page.getByText('12.000 ₫',{exact:true})).toBeVisible();
});

test('Customer booking and cancellation respect role permissions',async({page})=>{
 await login(page,'customer');await expect(page.getByRole('link',{name:'Tài khoản',exact:true})).toHaveCount(0);await expect(page.getByRole('link',{name:'Xe vào / ra',exact:true})).toHaveCount(0);
 await nav(page,'Đặt chỗ');await page.getByRole('button',{name:'Đặt chỗ mới'}).click();await page.getByLabel('Phương tiện',{exact:true}).selectOption({label:'59A1-22222 · Xe máy xăng'});await page.getByLabel('Ô đỗ phù hợp',{exact:true}).selectOption({label:'MG-001 · Xe máy xăng'});await page.getByRole('button',{name:'Xác nhận đặt chỗ'}).click();await saved(page);const row=page.getByRole('row').filter({hasText:'59A1-22222'});await expect(row.getByText('Đã xác nhận')).toBeVisible();await row.getByRole('button',{name:'Hủy',exact:true}).click();await page.getByRole('button',{name:'Lưu / xác nhận'}).click();await saved(page);await expect(row.getByText('Đã hủy')).toBeVisible();
 await page.evaluate(()=>location.hash='users');await expect(page.getByRole('heading',{name:'Tổng quan',exact:true})).toBeVisible();
});

test('Security can inspect IoT, cannot manage settings; mobile has no overflow',async({page})=>{
 await page.setViewportSize({width:390,height:844});await login(page,'security');await page.getByRole('button',{name:'Mở menu'}).click();await expect(page.getByRole('link',{name:'Bảng giá & bãi xe'})).toHaveCount(0);await nav(page,'Sạc & thiết bị IoT');await expect(page.getByRole('button',{name:'Cập nhật',exact:true})).toHaveCount(0);await page.getByRole('button',{name:'Thiết bị IoT',exact:true}).click();await expect(page.getByRole('heading',{name:'Chưa có dữ liệu'})).toBeVisible();
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 await page.getByRole('button',{name:'Mở menu'}).click();await nav(page,'Tổng quan');if(artifacts)await page.screenshot({path:path.join(artifacts,'Frontend-Dien-thoai.png'),fullPage:true,animations:'disabled'});
 await page.getByRole('button',{name:'Mở menu'}).click();await nav(page,'Thông tin của tôi');
 const home=page.getByRole('link',{name:'Parkly — Về trang chủ',exact:true});await expect(page.getByRole('navigation',{name:'Vị trí trang'})).toContainText('parkly/Thông tin của tôi');
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 if(artifacts)await page.screenshot({path:path.join(artifacts,'Parkly-logo-ten-trang.png'),fullPage:true,animations:'disabled'});
 await home.click();await expect(page.getByRole('heading',{name:'Tổng quan',exact:true})).toBeVisible();

});

test('AI image validation and recognition preview do not create parking sessions',async({page,request})=>{
 await login(page);const token=await page.evaluate(()=>sessionStorage.getItem('parking-token'));const options={headers:{Authorization:'Bearer '+token}};const before=await (await request.get(process.env.E2E_API_URL+'/parking-sessions',options)).json();await nav(page,'Xe vào / ra');await page.getByRole('button',{name:'Nhận diện AI',exact:true}).click();await expect(page.getByRole('button',{name:'Xác nhận xe vào'})).toBeDisabled();await page.getByLabel('Ảnh biển số').setInputFiles({name:'invalid.txt',mimeType:'text/plain',buffer:Buffer.from('not an image')});await expect(page.getByRole('alert')).toContainText('JPEG');
 await page.getByLabel('Ảnh biển số').setInputFiles(path.resolve('../ai_engine/examples/single.png'));
 await page.getByRole('button',{name:'Nhận diện ảnh',exact:true}).click();await expect(page.getByRole('dialog').getByText(/độ tin cậy/)).toBeVisible({timeout:90000});const after=await (await request.get(process.env.E2E_API_URL+'/parking-sessions',options)).json();expect(after.length).toBe(before.length);
});

test('Network failure keeps stale data visible and expired session returns to login',async({page})=>{
 await login(page);await page.route('**/api/parking-spots?*',route=>route.abort());await page.getByRole('button',{name:'Làm mới',exact:true}).click();await expect(page.getByRole('alert')).toContainText('Không kết nối');await page.unroute('**/api/parking-spots?*');await page.evaluate(()=>sessionStorage.setItem('parking-token','invalid'));await page.reload();await expect(page.getByRole('heading',{name:'Chào mừng trở lại'})).toBeVisible();
});



test('IoT history and device access controls use real telemetry',async({page,request})=>{
 await login(page);const token=await page.evaluate(()=>sessionStorage.getItem('parking-token'));const headers={Authorization:'Bearer '+token};
 const spots=await (await request.get(process.env.E2E_API_URL+'/parking-spots',{headers})).json();const spot=spots.find(s=>s.spot_code==='CG-002');
 const device=await (await request.post(process.env.E2E_API_URL+'/iot/devices',{headers,data:{device_code:'WEB-SENSOR',parking_spot_id:spot.id,kind:'SENSOR'}})).json();
 const telemetry=await request.post(process.env.E2E_API_URL+'/iot/devices/WEB-SENSOR/telemetry',{headers:{'X-API-Key':device.api_key},data:{sequence:1,sensor_status:'AVAILABLE'}});expect(telemetry.status()).toBe(200);
 await page.getByRole('button',{name:'Làm mới',exact:true}).click();await nav(page,'Sạc & thiết bị IoT');await page.getByRole('button',{name:'Thiết bị IoT',exact:true}).click();const row=page.getByRole('row').filter({hasText:'WEB-SENSOR'});await expect(row.getByText('Trực tuyến',{exact:true})).toBeVisible();await row.getByRole('button',{name:'Lịch sử',exact:true}).click();await expect(page.getByRole('dialog').getByText('Còn trống',{exact:true})).toBeVisible();await page.getByRole('button',{name:'Đóng',exact:true}).last().click();await row.getByRole('button',{name:'Tắt',exact:true}).click();await page.getByRole('button',{name:'Lưu / xác nhận'}).click();await saved(page);await expect(row.getByText('Đã tắt',{exact:true})).toBeVisible();
});

test('Production build served by FastAPI authenticates and loads map',async({page})=>{
 await page.goto(process.env.E2E_API_URL+'/dashboard/');await page.getByLabel('Email',{exact:true}).fill('admin@example.com');await page.getByLabel('Mật khẩu',{exact:true}).fill('TestParking123!');await page.getByRole('button',{name:'Đăng nhập',exact:true}).click();await expect(page.getByText('Không gian bãi xe',{exact:true})).toBeVisible();await nav(page,'Sơ đồ bãi xe');await expect(page.getByRole('button',{name:/^Ô [A-Z]/})).toHaveCount(170);
});


test('Register a plate inside booking, retain chosen spot and show a two-hour cancellation deadline',async({page,request})=>{
 await login(page,'customer');await nav(page,'Sơ đồ bãi xe');await page.getByRole('button',{name:'Ô CG-003 — Còn trống',exact:true}).click();await page.getByRole('button',{name:'Đặt chỗ này',exact:true}).click();
 await page.getByRole('button',{name:'Nhập biển số mới',exact:true}).click();await expect(page.getByLabel('Loại xe mới',{exact:true})).toHaveValue('CAR');await page.getByLabel('Biển số mới',{exact:true}).fill('51A-67890');await expect(page.getByRole('button',{name:'Xác nhận đặt chỗ'})).toBeDisabled();
 await page.getByRole('button',{name:'Lưu xe và chọn',exact:true}).click();await expect(page.getByRole('dialog').getByText(/Đã lưu và chọn xe 51A-67890/)).toBeVisible();await expect(page.getByLabel('Ô đỗ phù hợp',{exact:true}).locator('option:checked')).toHaveText('CG-003 · Ô tô xăng');
 await expect(page.getByLabel('Giờ hết hạn (Việt Nam)',{exact:true})).toHaveCount(0);
 const tomorrow=new Date(Date.now()+31*3600000).toISOString().slice(0,10);const start=tomorrow+'T23:30';await page.getByLabel('Giờ bắt đầu (Việt Nam)',{exact:true}).fill(start);
 const expected=new Date(new Date(start+'+07:00').getTime()+9*3600000).toISOString().slice(0,16);
 await expect(page.getByRole('dialog').locator('.booking-deadline')).toContainText('01:30');
 if(artifacts)await page.getByRole('dialog').screenshot({path:path.join(artifacts,'Dat-cho-nhap-bien-so.png'),animations:'disabled'});
 const posted=page.waitForResponse(r=>r.request().method()==='POST'&&new URL(r.url()).pathname==='/api/reservations');await page.getByRole('button',{name:'Xác nhận đặt chỗ',exact:true}).click();const response=await posted;expect(response.status()).toBe(201);const record=await response.json();expect(record.expiry_time.slice(0,16)).toBe(expected);await saved(page);
 const tile=page.getByRole('button',{name:'Ô CG-003 — Đã giữ chỗ',exact:true});await expect(tile).toContainText('Hủy lúc 01:30');
 const token=await page.evaluate(()=>sessionStorage.getItem('parking-token'));const vehicles=await(await request.get(process.env.E2E_API_URL+'/vehicles',{headers:{Authorization:'Bearer '+token}})).json();expect(vehicles.filter(v=>v.license_plate==='51A-67890')).toHaveLength(1);
});

test('Plate search ignores separators and keeps compatible selected spot',async({page})=>{
 await login(page,'customer');await nav(page,'Sơ đồ bãi xe');await page.getByRole('button',{name:'Ô MG-002 — Còn trống',exact:true}).click();await page.getByRole('button',{name:'Đặt chỗ này',exact:true}).click();await page.getByLabel('Tìm biển số',{exact:true}).fill('59a122222');await expect(page.getByLabel('Phương tiện',{exact:true}).locator('option:checked')).toContainText('59A1-22222');await expect(page.getByLabel('Ô đỗ phù hợp',{exact:true}).locator('option:checked')).toContainText('MG-002');
 await page.getByLabel('Tìm biển số',{exact:true}).fill('missing');await expect(page.getByLabel('Phương tiện',{exact:true})).toHaveValue('');await expect(page.getByText(/Không có biển số phù hợp/)).toBeVisible();
});

test('Inline registration rejects another owner plate and reuses the current owner plate',async({page,request})=>{
 await login(page,'customer');await nav(page,'Đặt chỗ');await page.getByRole('button',{name:'Đặt chỗ mới',exact:true}).click();await page.getByRole('button',{name:'Nhập biển số mới',exact:true}).click();await page.getByLabel('Biển số mới',{exact:true}).fill('51A-11111');await page.getByRole('button',{name:'Lưu xe và chọn',exact:true}).click();await expect(page.getByRole('alert')).toContainText('đã tồn tại');await expect(page.getByRole('button',{name:'Xác nhận đặt chỗ',exact:true})).toBeDisabled();
 await page.getByLabel('Biển số mới',{exact:true}).fill('59a1 22222');await page.getByRole('button',{name:'Lưu xe và chọn',exact:true}).click();await expect(page.getByLabel('Phương tiện',{exact:true}).locator('option:checked')).toContainText('59A1-22222');await expect(page.getByText(/Biển số đã có trong danh sách/)).toBeVisible();
});


test('Staff registers guest and account vehicles; customers see only their assigned vehicle',async({page,request})=>{
 await login(page,'security');await nav(page,'Phương tiện');await page.getByRole('button',{name:'Đăng ký xe khách hàng',exact:true}).click();await expect(page.getByLabel('Khách hàng',{exact:true})).toHaveValue('guest');await page.getByLabel('Biển số',{exact:true}).fill('59B1-88888');await page.getByRole('button',{name:'Lưu / xác nhận',exact:true}).click();await saved(page);await expect(page.getByRole('row').filter({hasText:'59B1-88888'}).getByText('Khách vãng lai',{exact:true})).toBeVisible();
 await page.getByRole('button',{name:'Đăng ký xe khách hàng',exact:true}).click();await page.getByLabel('Khách hàng',{exact:true}).selectOption('account');await page.getByLabel('Email tài khoản khách hàng',{exact:true}).fill('customer@example.com');await page.getByLabel('Biển số',{exact:true}).fill('59B1-77777');await page.getByRole('button',{name:'Lưu / xác nhận',exact:true}).click();await saved(page);
 const token=await page.evaluate(()=>sessionStorage.getItem('parking-token'));const vehicles=await(await request.get(process.env.E2E_API_URL+'/dashboard-data/vehicles',{headers:{Authorization:'Bearer '+token}})).json();expect(vehicles.find(v=>v.license_plate==='59B1-88888').user_id).toBeNull();expect(vehicles.find(v=>v.license_plate==='59B1-77777').user_id).not.toBeNull();
 await nav(page,'Đặt chỗ');await page.getByRole('button',{name:'Đặt chỗ mới',exact:true}).click();await page.getByLabel('Tìm biển số',{exact:true}).fill('59B177777');await page.getByLabel('Ô đỗ phù hợp',{exact:true}).selectOption({label:'MG-004 · Xe máy xăng'});await page.getByRole('button',{name:'Xác nhận đặt chỗ',exact:true}).click();await saved(page);
 await page.getByRole('button',{name:'Đăng xuất',exact:true}).click();await login(page,'customer');await nav(page,'Phương tiện');await expect(page.getByText('59B1-77777',{exact:true})).toBeVisible();await expect(page.getByText('59B1-88888',{exact:true})).toHaveCount(0);await expect(page.getByRole('button',{name:'Đăng ký xe khách hàng',exact:true})).toHaveCount(0);await nav(page,'Đặt chỗ');await expect(page.getByRole('row').filter({hasText:'59B1-77777'}).getByText('Đã xác nhận',{exact:true})).toBeVisible();
});

test('Deadline is below start time and staff can register a guest in the booking dialog',async({page,request})=>{
 await login(page,'security');await nav(page,'Đặt chỗ');await page.getByRole('button',{name:'Đặt chỗ mới',exact:true}).click();await page.getByRole('button',{name:'Nhập biển số mới',exact:true}).click();await expect(page.getByLabel('Khách hàng',{exact:true})).toHaveValue('guest');await page.getByLabel('Biển số mới',{exact:true}).fill('59B1-66666');await page.getByRole('button',{name:'Lưu xe và chọn',exact:true}).click();await expect(page.getByLabel('Phương tiện',{exact:true}).locator('option:checked')).toContainText('59B1-66666');await page.getByLabel('Ô đỗ phù hợp',{exact:true}).selectOption({label:'MG-005 · Xe máy xăng'});
 const start=await page.getByLabel('Giờ bắt đầu (Việt Nam)',{exact:true}).boundingBox();const deadline=await page.locator('.booking-deadline').boundingBox();expect(deadline.y).toBeGreaterThan(start.y+start.height);
 if(artifacts)await page.getByRole('dialog').screenshot({path:path.join(artifacts,'Dat-cho-han-huy-duoi-gio-bat-dau.png'),animations:'disabled'});
 await page.getByRole('button',{name:'Xác nhận đặt chỗ',exact:true}).click();await saved(page);
 const token=await page.evaluate(()=>sessionStorage.getItem('parking-token'));const vehicles=await(await request.get(process.env.E2E_API_URL+'/dashboard-data/vehicles',{headers:{Authorization:'Bearer '+token}})).json();expect(vehicles.find(v=>v.license_plate==='59B1-66666').user_id).toBeNull();
});


test('Plate examples follow car or motorbike selection without changing entered text',async({page})=>{
 await login(page,'customer');await nav(page,'Đặt chỗ');await page.getByRole('button',{name:'Đặt chỗ mới',exact:true}).click();await page.getByRole('button',{name:'Nhập biển số mới',exact:true}).click();const plate=page.getByLabel('Biển số mới',{exact:true});await expect(plate).toHaveAttribute('placeholder','VD: 29-B1 555.55');await page.getByLabel('Loại xe mới',{exact:true}).selectOption('CAR');await expect(plate).toHaveAttribute('placeholder','VD: 30F-222.22');await plate.fill('30F-222.22');await page.getByLabel('Loại xe mới',{exact:true}).selectOption('MOTORBIKE');await expect(plate).toHaveAttribute('placeholder','VD: 29-B1 555.55');await expect(plate).toHaveValue('30F-222.22');await plate.clear();
 if(artifacts)await page.getByRole('dialog').screenshot({path:path.join(artifacts,'Dang-ky-xe-may-vi-du-bien-so.png'),animations:'disabled'});
 await page.getByRole('button',{name:'Đóng',exact:true}).last().click();await nav(page,'Phương tiện');await page.getByRole('button',{name:'Thêm xe của tôi',exact:true}).click();await expect(page.getByLabel('Biển số',{exact:true})).toHaveAttribute('placeholder','VD: 29-B1 555.55');await page.getByLabel('Loại phương tiện',{exact:true}).selectOption('CAR');await expect(page.getByLabel('Biển số',{exact:true})).toHaveAttribute('placeholder','VD: 30F-222.22');
});
