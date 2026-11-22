import {test,expect} from '../playwright.mjs';
import path from 'node:path';
import fs from 'node:fs';
const artifacts=process.env.FRONTEND_ARTIFACT_DIR;

test('Staff sees heat and wrong-parking incidents, acknowledges and retains recovered history',async({page,request})=>{
 await login(page);const token=await page.evaluate(()=>sessionStorage.getItem('parking-token'));const headers={Authorization:'Bearer '+token};
 const base=process.env.E2E_API_URL;
 const spots=await(await request.get(base+'/parking-spots',{headers})).json();
 const electric=spots.find(s=>s.spot_code==='CE-020'),car=spots.find(s=>s.spot_code==='CG-030');
 const charger=await(await request.post(base+'/iot/devices',{headers,data:{device_code:'ALERT-CHARGER',parking_spot_id:electric.id,kind:'CHARGER'}})).json();
 const sensor=await(await request.post(base+'/iot/devices',{headers,data:{device_code:'ALERT-SENSOR',parking_spot_id:car.id,kind:'SENSOR'}})).json();
 const send=async(d,data)=>{const response=await request.post(base+`/iot/devices/${d.device_code}/telemetry`,{headers:{'X-API-Key':d.api_key},data});expect(response.status()).toBe(200);};
 await send(charger,{sequence:1,charger_status:'READY',temperature_c:75});
 await send(sensor,{sequence:1,sensor_status:'OCCUPIED',observed_vehicle_type:'MOTORBIKE',observed_energy_type:'GASOLINE'});
 await page.getByRole('button',{name:'Làm mới',exact:true}).click();
 await expect(page.locator('.incident-banner')).toContainText('sự cố đang mở');
 await nav(page,'Cảnh báo & sự cố');
 const heat=page.getByRole('row').filter({hasText:'ALERT-CHARGER'}),wrong=page.getByRole('row').filter({hasText:'ALERT-SENSOR'});
 await expect(heat).toContainText('Quá nhiệt');await expect(heat).toContainText('75 °C');
 await expect(wrong).toContainText('Đỗ sai vị trí');await expect(wrong).toContainText('Quan sát: Xe máy xăng');await expect(wrong).toContainText('Ô dành cho: Ô tô xăng');
 await heat.getByRole('button',{name:'Xác nhận tiếp nhận',exact:true}).click();await expect(heat).toContainText('Đã xác nhận');
 if(artifacts)await page.screenshot({path:path.join(artifacts,'Canh-bao-qua-nhiet-sai-vi-tri.png'),fullPage:true});
 await page.reload();await expect(heat).toContainText('Đã xác nhận');
 await send(charger,{sequence:2,charger_status:'READY',temperature_c:30});await send(sensor,{sequence:2,sensor_status:'AVAILABLE'});
 await page.getByRole('button',{name:'Làm mới',exact:true}).click();await page.getByLabel('Trạng thái sự cố',{exact:true}).selectOption('RESOLVED');
 await expect(heat).toContainText('Đã kết thúc');await expect(wrong).toContainText('Ô đã trống');
 await page.getByLabel('Loại sự cố',{exact:true}).selectOption('OVERHEAT');await expect(heat).toBeVisible();await expect(wrong).toHaveCount(0);
 if(artifacts)await page.screenshot({path:path.join(artifacts,'Nhat-ky-su-co-da-khac-phuc.png'),fullPage:true});
 await page.getByRole('button',{name:'Đăng xuất',exact:true}).click();await login(page,'customer');await expect(page.getByRole('link',{name:'Cảnh báo & sự cố',exact:true})).toHaveCount(0);
});

test('Connection monitor raises an incident without telemetry and fresh data closes it',async({page,request})=>{
 test.setTimeout(60000);
 await login(page,'security');const token=await page.evaluate(()=>sessionStorage.getItem('parking-token'));
 const admin=await(await request.post(process.env.E2E_API_URL+'/auth/login',{data:{email:'admin@example.com',password:'TestParking123!'}})).json();
 const headers={Authorization:'Bearer '+admin.access_token},base=process.env.E2E_API_URL;
 const spots=await(await request.get(base+'/parking-spots',{headers})).json();const spot=spots.find(s=>s.spot_code==='CG-029');
 const device=await(await request.post(base+'/iot/devices',{headers,data:{device_code:'OFFLINE-ALERT',parking_spot_id:spot.id,kind:'SENSOR',offline_after_seconds:10}})).json();
 const pollHeaders={Authorization:'Bearer '+token};
 await expect.poll(async()=>{const rows=await(await request.get(base+'/alerts?status=OPEN',{headers:pollHeaders})).json();return rows.items.some(r=>r.device_code==='OFFLINE-ALERT');},{timeout:25000,intervals:[1000]}).toBeTruthy();
 await nav(page,'Cảnh báo & sự cố');const row=page.getByRole('row').filter({hasText:'OFFLINE-ALERT'});await expect(row).toContainText('Mất kết nối / thiếu số đo');
 await row.getByRole('button',{name:'Xác nhận tiếp nhận',exact:true}).click();await expect(row).toContainText('Đã xác nhận');
 const response=await request.post(base+'/iot/devices/OFFLINE-ALERT/telemetry',{headers:{'X-API-Key':device.api_key},data:{sequence:1,sensor_status:'AVAILABLE'}});expect(response.status()).toBe(200);
 await page.getByRole('button',{name:'Làm mới',exact:true}).click();await page.getByLabel('Trạng thái sự cố',{exact:true}).selectOption('RESOLVED');await expect(row).toContainText('Đã nhận bản tin đo mới');
});

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
 let row=page.getByRole('row').filter({hasText:'51A-98765'});await expect(row.getByText('Đang gửi',{exact:true})).toBeVisible();await row.getByRole('button',{name:'Xe ra',exact:true}).click();await page.getByRole('button',{name:'Xác nhận xe ra',exact:true}).click();await saved(page);await expect(row.getByText('Hoàn tất',{exact:true})).toBeVisible();await row.getByRole('button',{name:'Thu tiền',exact:true}).click();await expect(page.getByRole('dialog').getByTestId('fee-total')).toHaveText('10.000 ₫');await page.getByRole('button',{name:'Đã nhận tiền',exact:true}).click();await saved(page);
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
 await page.setViewportSize({width:390,height:844});await login(page,'security');await page.getByRole('button',{name:'Mở menu'}).click();await expect(page.getByRole('link',{name:'Bảng giá & bãi xe'})).toHaveCount(0);await nav(page,'Sạc & thiết bị IoT');await expect(page.getByRole('button',{name:'Cập nhật',exact:true})).toHaveCount(0);await page.getByRole('button',{name:'Thiết bị IoT',exact:true}).click();await expect(page.getByRole('button',{name:'Thiết bị IoT',exact:true})).toHaveClass('selected');await expect(page.getByRole('button',{name:'Tắt',exact:true})).toHaveCount(0);await expect(page.getByRole('button',{name:'Bật',exact:true})).toHaveCount(0);
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
 await page.getByLabel('Ảnh biển số').setInputFiles(path.resolve('../../kiem_thu/fixtures/ai_engine/single.png'));
 await page.getByRole('button',{name:'Nhận diện ảnh',exact:true}).click();await expect(page.getByRole('dialog').getByText(/độ tin cậy/)).toBeVisible({timeout:90000});const after=await (await request.get(process.env.E2E_API_URL+'/parking-sessions',options)).json();expect(after.length).toBe(before.length);
});

test('Network failure keeps stale data visible and expired session returns to login',async({page})=>{
 await login(page);await page.route('**/api/parking-lots/*/snapshot',route=>route.abort());await page.getByRole('button',{name:'Làm mới',exact:true}).click();await expect(page.getByRole('alert')).toContainText('Không kết nối');await page.unroute('**/api/parking-lots/*/snapshot');await page.evaluate(()=>sessionStorage.setItem('parking-token','invalid'));await page.reload();await expect(page.getByRole('heading',{name:'Chào mừng trở lại'})).toBeVisible();
});

test('Realtime coalesces refreshes during a slow dashboard read', async ({page, request}) => {
  const frames = [];
  page.on('websocket', socket => {
    if (new URL(socket.url()).pathname !== '/ws/events') return;
    socket.on('framereceived', frame => frames.push(JSON.parse(frame.payload.toString()).type));
  });
  await login(page);
  await nav(page, 'Sơ đồ bãi xe');
  await expect(page.getByRole('button', {name: 'Ô CG-001 — Còn trống', exact: true})).toBeVisible();
  await expect.poll(() => frames.includes('ready')).toBe(true);
  const base = process.env.E2E_API_URL;
  const token = await page.evaluate(() => sessionStorage.getItem('parking-token'));
  const headers = {Authorization: 'Bearer ' + token};
  const spots = await (await request.get(base + '/parking-spots?parking_lot_id=1', {headers})).json();
  const spotId = spots.find(spot => spot.spot_code === 'CG-001').id;

  let reads = 0;
  let firstReadReady = false;
  let release;
  const heldRead = new Promise(resolve => { release = resolve; });
  await page.route(url => url.pathname === '/api/parking-spots' || /^\/api\/parking-lots\/\d+\/snapshot$/.test(url.pathname), async route => {
    reads++;
    if (reads > 1) return route.continue();
    const snapshot = await route.fetch();
    firstReadReady = true;
    await heldRead;
    await route.fulfill({response: snapshot}).catch(() => {});
  });

  let readsWhileHeld;
  try {
    await page.getByRole('button', {name: 'Làm mới', exact: true}).click();
    await expect.poll(() => firstReadReady).toBe(true);
    for (const sensorStatus of ['OCCUPIED', 'AVAILABLE', 'OCCUPIED']) {
      const sent = frames.filter(type => type === 'invalidate').length;
      const response = await request.post(base + '/api/v1/iot/simulate-sensor', {
        headers, data: {parking_spot_id: spotId, sensor_status: sensorStatus},
      });
      expect(response.status()).toBe(200);
      await expect.poll(() => frames.filter(type => type === 'invalidate').length).toBeGreaterThan(sent);
      await page.waitForTimeout(350); // Each notification gets past the 250 ms window.
    }
    readsWhileHeld = reads;
  } finally {
    release();
  }
  await expect(page.getByRole('button', {name: 'Ô CG-001 — Có xe', exact: true})).toBeVisible();
  expect(readsWhileHeld).toBe(1);
  expect(reads).toBe(2);
});



test('A changed heartbeat refreshes the map if an invalidation was missed', async ({page, request}) => {
  let dropInvalidations = false;
  let missedRevision;
  let routedSocket;
  await page.routeWebSocket('**/ws/events', socket => {
    routedSocket = socket;
    const server = socket.connectToServer();
    server.onMessage(message => {
      const frame = JSON.parse(message.toString());
      if (dropInvalidations && frame.type === 'invalidate') {
        missedRevision = frame.revision;
      } else {
        socket.send(message);
      }
    });
  });
  await login(page);
  await nav(page, 'Sơ đồ bãi xe');
  const base = process.env.E2E_API_URL;
  const headers = {Authorization: 'Bearer ' + await page.evaluate(() => sessionStorage.getItem('parking-token'))};
  const spots = await (await request.get(base + '/parking-spots?parking_lot_id=1', {headers})).json();
  const spot = spots.find(candidate => candidate.spot_code === 'CG-004' && candidate.available_for_booking);
  expect(spot).toBeTruthy();
  const available = page.getByRole('button', {name: `Ô ${spot.spot_code} — Còn trống`, exact: true});
  await expect(available).toBeVisible();
  dropInvalidations = true;
  const update = sensor_status => request.post(base + '/api/v1/iot/simulate-sensor', {
    headers, data: {parking_spot_id: spot.id, sensor_status},
  });
  try {
    expect((await update('OCCUPIED')).status()).toBe(200);
    await expect.poll(() => missedRevision).toBeTruthy();
    await expect(available).toBeVisible();
    routedSocket.send(JSON.stringify({type: 'ping', revision: missedRevision}));
    await expect(page.getByRole('button', {name: `Ô ${spot.spot_code} — Có xe`, exact: true})).toBeVisible({timeout: 8000});
  } finally {
    dropInvalidations = false;
    await update('AVAILABLE');
  }
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
 const startField=page.getByLabel('Giờ bắt đầu (Việt Nam)',{exact:true});
 await startField.fill(new Date(Date.now()+10*3600000).toISOString().slice(0,16));
 expect(await startField.evaluate(input=>input.validity.rangeOverflow)).toBe(true);
 const start=new Date(Date.now()+7*3600000+30*60000).toISOString().slice(0,16);
 await startField.fill(start);
 const expected=new Date(new Date(start+'+07:00').getTime()+9*3600000).toISOString().slice(0,16);
 await expect(page.getByRole('dialog').locator('.booking-deadline')).toContainText(expected.slice(11,16));
 if(artifacts)await page.getByRole('dialog').screenshot({path:path.join(artifacts,'Dat-cho-nhap-bien-so.png'),animations:'disabled'});
 const posted=page.waitForResponse(r=>r.request().method()==='POST'&&new URL(r.url()).pathname==='/api/reservations');await page.getByRole('button',{name:'Xác nhận đặt chỗ',exact:true}).click();const response=await posted;expect(response.status()).toBe(201);expect(response.request().postDataJSON()).not.toHaveProperty('expiry_time');const record=await response.json();expect(record.expiry_time.slice(0,16)).toBe(expected);await saved(page);
 const tile=page.getByRole('button',{name:'Ô CG-003 — Đã giữ chỗ',exact:true});await expect(tile).toContainText('Hủy lúc '+expected.slice(11,16));
 const token=await page.evaluate(()=>sessionStorage.getItem('parking-token'));const vehicles=await(await request.get(process.env.E2E_API_URL+'/vehicles',{headers:{Authorization:'Bearer '+token}})).json();expect(vehicles.filter(v=>v.license_plate==='51A-67890')).toHaveLength(1);
});

test('Selecting a registered vehicle keeps compatible selected spot without a plate search field',async({page})=>{
 await login(page,'customer');await nav(page,'Sơ đồ bãi xe');await page.getByRole('button',{name:'Ô MG-002 — Còn trống',exact:true}).click();await page.getByRole('button',{name:'Đặt chỗ này',exact:true}).click();await expect(page.getByLabel('Tìm biển số',{exact:true})).toHaveCount(0);await page.getByLabel('Phương tiện',{exact:true}).selectOption({label:'59A1-22222 · Xe máy xăng'});await expect(page.getByLabel('Phương tiện',{exact:true}).locator('option:checked')).toContainText('59A1-22222');await expect(page.getByLabel('Ô đỗ phù hợp',{exact:true}).locator('option:checked')).toContainText('MG-002');
 if(artifacts)await page.getByRole('dialog').screenshot({path:path.join(artifacts,'Dat-cho-bo-tim-bien-so.png'),animations:'disabled'});
});

test('Inline registration rejects another owner plate and reuses the current owner plate',async({page,request})=>{
 await login(page,'customer');await nav(page,'Đặt chỗ');await page.getByRole('button',{name:'Đặt chỗ mới',exact:true}).click();await page.getByRole('button',{name:'Nhập biển số mới',exact:true}).click();await page.getByLabel('Biển số mới',{exact:true}).fill('51A-11111');await page.getByRole('button',{name:'Lưu xe và chọn',exact:true}).click();await expect(page.getByRole('alert')).toContainText('đã tồn tại');await expect(page.getByRole('button',{name:'Xác nhận đặt chỗ',exact:true})).toBeDisabled();
 await page.getByLabel('Biển số mới',{exact:true}).fill('59a1 22222');await page.getByRole('button',{name:'Lưu xe và chọn',exact:true}).click();await expect(page.getByLabel('Phương tiện',{exact:true}).locator('option:checked')).toContainText('59A1-22222');await expect(page.getByText(/Biển số đã có trong danh sách/)).toBeVisible();
});


test('Staff registers guest and account vehicles; customers see only their assigned vehicle',async({page,request})=>{
 await login(page,'security');await nav(page,'Phương tiện');await page.getByRole('button',{name:'Đăng ký xe khách hàng',exact:true}).click();await expect(page.getByLabel('Khách hàng',{exact:true})).toHaveValue('guest');await page.getByLabel('Biển số',{exact:true}).fill('59B1-88888');await page.getByRole('button',{name:'Lưu / xác nhận',exact:true}).click();await saved(page);await expect(page.getByRole('row').filter({hasText:'59B1-88888'}).getByText('Khách vãng lai',{exact:true})).toBeVisible();
 await page.getByRole('button',{name:'Đăng ký xe khách hàng',exact:true}).click();await page.getByLabel('Khách hàng',{exact:true}).selectOption('account');await page.getByLabel('Email tài khoản khách hàng',{exact:true}).fill('customer@example.com');await page.getByLabel('Biển số',{exact:true}).fill('59B1-77777');await page.getByRole('button',{name:'Lưu / xác nhận',exact:true}).click();await saved(page);
 const token=await page.evaluate(()=>sessionStorage.getItem('parking-token'));const vehicles=await(await request.get(process.env.E2E_API_URL+'/dashboard-data/vehicles',{headers:{Authorization:'Bearer '+token}})).json();expect(vehicles.find(v=>v.license_plate==='59B1-88888').user_id).toBeNull();expect(vehicles.find(v=>v.license_plate==='59B1-77777').user_id).not.toBeNull();
 await nav(page,'Đặt chỗ');await page.getByRole('button',{name:'Đặt chỗ mới',exact:true}).click();await page.getByLabel('Phương tiện',{exact:true}).selectOption({label:'59B1-77777 · Xe máy xăng'});await page.getByLabel('Ô đỗ phù hợp',{exact:true}).selectOption({label:'MG-004 · Xe máy xăng'});await page.getByRole('button',{name:'Xác nhận đặt chỗ',exact:true}).click();await saved(page);
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

test('New lot form and API use the reduced 95-space defaults',async({page,request})=>{
 await login(page);await nav(page,'Bảng giá & bãi xe');
 await page.getByRole('button',{name:'Thêm bãi xe',exact:true}).click();
 await expect(page.getByLabel('Tổng chỗ ô tô (1–50)',{exact:true})).toHaveValue('30');
 await expect(page.getByLabel('Trong đó: ô tô điện',{exact:true})).toHaveValue('10');
 await expect(page.getByLabel('Tổng chỗ xe máy (1–120)',{exact:true})).toHaveValue('65');
 await expect(page.getByLabel('Trong đó: xe máy điện',{exact:true})).toHaveValue('25');
 const token=await page.evaluate(()=>sessionStorage.getItem('parking-token'));
 const headers={Authorization:'Bearer '+token},base=process.env.E2E_API_URL;
 const created=await request.post(base+'/parking-lots',{headers,data:{name:'Bãi mới 95 chỗ',address:'Kiểm thử cấu hình mới'}});
 expect(created.status()).toBe(201);const lot=await created.json();
 expect([lot.car_capacity,lot.motorbike_capacity,lot.electric_car_capacity,lot.electric_motorbike_capacity]).toEqual([30,65,10,25]);
 const layout=await request.post(base+`/parking-lots/${lot.id}/initialize-layout`,{headers});expect(layout.status()).toBe(200);
 const capacity=await layout.json();expect(capacity.total_configured_spots).toBe(95);
 expect(capacity.groups.map(g=>g.configured_spots)).toEqual([20,10,40,25]);
 await request.delete(base+`/parking-lots/${lot.id}`,{headers});
});

