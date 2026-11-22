import {test, expect} from '../playwright.mjs';

const base = process.env.E2E_API_URL;

test('Booking controls follow the server from early arrival to checked in', async ({page, request})=>{
 await page.goto(base+'/dashboard/');
 await page.getByLabel('Email',{exact:true}).fill('admin@example.com');
 await page.getByLabel('Mật khẩu',{exact:true}).fill('TestParking123!');
 await page.getByRole('button',{name:'Đăng nhập',exact:true}).click();
 await expect(page.getByRole('heading',{name:'Tổng quan',exact:true})).toBeVisible();
 const headers={Authorization:'Bearer '+await page.evaluate(()=>sessionStorage.getItem('parking-token'))};
 const registered=await request.post(base+'/vehicles',{headers,data:{license_plate:'62B1-47852',vehicle_type:'MOTORBIKE',energy_type:'GASOLINE'}});
 expect(registered.status()).toBe(201);
 const vehicle=await registered.json();
 const spots=await (await request.get(base+'/parking-spots?parking_lot_id=1',{headers})).json();
 const spot=spots.find(s=>s.available_for_booking&&s.spot_type==='MOTORBIKE'&&s.energy_type==='GASOLINE'&&Number(s.spot_code.slice(3))>30);
 expect(spot).toBeTruthy();
 await page.getByRole('link',{name:'Đặt chỗ',exact:true}).click();
 const policy=await (await request.get(base+'/reservations/policy',{headers})).json();
 const localStart=Date.parse(policy.server_time+'+07:00')+7*3600000+12000;
 const start=new Date(localStart).toISOString().slice(0,23);
 const created=await request.post(base+'/reservations',{headers,data:{vehicle_id:vehicle.id,parking_spot_id:spot.id,start_time:start}});
 expect(created.status()).toBe(201);
 const booking=await created.json();
 expect(booking.arrival_status).toBe('UPCOMING');
 const bookingUrl=base+'/reservations/'+booking.id;
 const row=page.getByRole('row').filter({hasText:vehicle.license_plate});
 const refresh=page.getByRole('button',{name:'Làm mới',exact:true});
 let session;
 try{
  await refresh.click();
  await expect(row.getByText('Chưa tới giờ nhận xe',{exact:true})).toBeVisible();
  await expect(row.getByRole('button',{name:'Xe vào',exact:true})).toHaveCount(0);
  await expect(row.getByRole('button',{name:'Hủy',exact:true})).toBeVisible();
  await expect.poll(async()=>{
   const reply=await request.get(bookingUrl,{headers});
   return (await reply.json()).arrival_status;
  },{timeout:22000}).toBe('READY');
  await refresh.click();
  await expect(row.getByText('Có thể nhận xe',{exact:true})).toBeVisible();
  await row.getByRole('button',{name:'Xe vào',exact:true}).click();
  const reply=page.waitForResponse(r=>new URL(r.url()).pathname==='/parking-sessions/check-in'&&r.request().method()==='POST');
  await page.getByRole('button',{name:'Ghi nhận xe vào',exact:true}).click();
  const entered=await reply;
  expect(entered.status()).toBe(201);
  session=await entered.json();
  await expect(row.getByText('Đã nhận xe',{exact:true})).toBeVisible();
  await expect(row.getByRole('button',{name:'Hủy',exact:true})).toHaveCount(0);
  await expect(row.getByRole('button',{name:'Xe vào',exact:true})).toHaveCount(0);
 }finally{
  if(session) await request.post(base+'/parking-sessions/'+session.id+'/check-out',{headers,data:{}});
  else await request.patch(bookingUrl+'/cancel',{headers});
 }
});

test('Dashboard books adjacent time slots without occupying the spot in advance', async ({page, request}) => {
  await page.goto(base + '/dashboard/');
  await page.getByLabel('Email', {exact: true}).fill('admin@example.com');
  await page.getByLabel('Mật khẩu', {exact: true}).fill('TestParking123!');
  await page.getByRole('button', {name: 'Đăng nhập', exact: true}).click();
  await expect(page.getByRole('heading', {name: 'Tổng quan', exact: true})).toBeVisible();
  const headers = {Authorization: 'Bearer ' + await page.evaluate(() => sessionStorage.getItem('parking-token'))};
  const registered = await request.post(base + '/vehicles', {headers, data: {
    license_plate: '62B1-47853', vehicle_type: 'MOTORBIKE', energy_type: 'GASOLINE',
  }});
  expect(registered.status()).toBe(201);
  const vehicle = await registered.json();
  const policy = await (await request.get(base + '/reservations/policy', {headers})).json();
  const bookingDay = Date.parse(policy.server_time + 'Z') + 86400000;
  const wallTime = hours => new Date(bookingDay + hours * 3600000).toISOString().slice(0, 16);
  await page.getByRole('link', {name: 'Đặt chỗ', exact: true}).click();
  await page.getByRole('button', {name: 'Làm mới', exact: true}).click();
  const booked = [];
  let spotId;
  try {
    for (let hour = 0; hour < 2; hour++) {
      await page.getByRole('button', {name: 'Đặt chỗ mới', exact: true}).click();
      const dialog = page.getByRole('dialog');
      await dialog.getByLabel('Phương tiện', {exact: true}).selectOption(String(vehicle.id));
      await dialog.getByLabel('Cách đặt chỗ', {exact: true}).selectOption('scheduled');
      await dialog.getByLabel('Giờ bắt đầu (Việt Nam)', {exact: true}).fill(wallTime(hour));
      await dialog.getByLabel('Giờ rời bãi dự kiến (Việt Nam)', {exact: true}).fill(wallTime(hour + 1));
      const selector = dialog.getByLabel('Ô đỗ phù hợp', {exact: true});
      await expect.poll(() => selector.locator('option').count()).toBeGreaterThan(1);
      spotId ??= Number(await selector.locator('option').nth(1).getAttribute('value'));
      await selector.selectOption(String(spotId));
      const saved = page.waitForResponse(response => new URL(response.url()).pathname === '/reservations' && response.request().method() === 'POST');
      await dialog.getByRole('button', {name: 'Xác nhận đặt chỗ', exact: true}).click();
      const response = await saved;
      expect(response.status()).toBe(201);
      booked.push(await response.json());
      expect(booked.at(-1).end_time.slice(0, 16)).toBe(wallTime(hour + 1));
      await expect(dialog).toBeHidden();
    }
    expect(booked.map(row => row.parking_spot_id)).toEqual([spotId, spotId]);
    await expect(page.getByText(/Rời dự kiến/)).toHaveCount(2);
    const spot = await (await request.get(base + '/parking-spots/' + spotId, {headers})).json();
    expect(spot.status).toBe('AVAILABLE');
    const immediateStart = new Date(Date.parse(policy.server_time + 'Z') + 300000).toISOString().slice(0, 19);
    const immediate = await request.post(base + '/reservations', {headers, data: {
      parking_spot_id: spotId, vehicle_id: vehicle.id, start_time: immediateStart,
    }});
    expect(immediate.status()).toBe(201);
    const activeHold = await immediate.json();
    booked.push(activeHold);
    await page.getByRole('link', {name: 'Sơ đồ bãi xe', exact: true}).click();
    const tile = page.getByRole('button', {name: `Ô ${spot.spot_code} — Đã giữ chỗ`, exact: true});
    await expect(tile).toContainText('Hủy lúc ' + activeHold.expiry_time.slice(11, 16));
  } finally {
    for (const booking of booked) await request.patch(base + '/reservations/' + booking.id + '/cancel', {headers});
  }
});
