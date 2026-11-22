import {test,expect} from '../playwright.mjs';
import {mkdir,writeFile} from 'node:fs/promises';
import {join} from 'node:path';

const car={id:'demo_car_scene',plate:'53F17609',kind:'Ô tô',key:'CAR'};
const motorbike={id:'demo_motorbike_scene',plate:'24B150935',kind:'Xe máy',key:'MOTORBIKE'};

test('Verified AI samples complete three car and motorbike round trips',async({page,request})=>{
 test.setTimeout(480000);
 const base=process.env.E2E_API_URL;
 const delays=[];
 const transactions=[];
 await page.goto(base+'/dashboard/');
 await page.getByLabel('Email',{exact:true}).fill('admin@example.com');
 await page.getByLabel('Mật khẩu',{exact:true}).fill('TestParking123!');
 await page.getByRole('button',{name:'Đăng nhập',exact:true}).click();
 await page.getByRole('link',{name:'Xe vào / ra',exact:true}).click();
 const token=await page.evaluate(()=>sessionStorage.getItem('parking-token'));
 const headers={Authorization:'Bearer '+token};
 const get=async path=>{
  const response=await request.get(base+path,{headers});
  expect(response.ok(),path).toBeTruthy();
  return response.json();
 };
 const openEntry=async()=>page.getByRole('button',{name:'Nhận diện AI',exact:true}).click();
 const run=async sample=>{
  await page.getByLabel('Ảnh camera mẫu',{exact:true}).selectOption(sample.id);
  const start=Date.now();
  const recognize=page.waitForResponse(r=>new URL(r.url()).pathname==='/ai/recognize'&&r.request().method()==='POST',{timeout:90000});
  await page.getByRole('button',{name:'Giả lập camera chụp ảnh',exact:true}).click();
  const response=await recognize;
  expect(response.status()).toBe(200);
  await expect(page.getByLabel('Vùng ảnh cần đọc (tùy chọn)',{exact:true})).toHaveValue('');
  const result=await response.json();
  delays.push({sample:sample.id,ms:Date.now()-start});
  if(!sample.plate){
   expect(result.plate).toBeNull();
   expect(result.needs_review).toBe(true);
   await expect(page.getByRole('button',{name:'Xác nhận xe vào',exact:true})).toBeDisabled();
   return;
  }
  expect(result.plate).toBe(sample.plate);
  expect(result.needs_review).toBe(false);
  expect(result.vehicle_detection.type).toBe(sample.key);
  await expect(page.getByLabel('Biển số nhận diện',{exact:true})).toHaveValue(sample.plate);
  await expect(page.getByText('Loại xe từ ảnh',{exact:true}).locator('..')).toContainText(sample.kind);
  await expect(page.getByAltText('Ảnh crop biển số từ mô hình AI')).toBeVisible();
 };
 const action=async (button,pattern,expected)=>{
  const response=page.waitForResponse(r=>pattern.test(new URL(r.url()).pathname)&&r.request().method()==='POST',{timeout:90000});
  await page.getByRole('button',{name:button,exact:true}).click();
  const observed=await response;
  expect(observed.status()).toBe(expected);
  return observed.json();
 };
 await openEntry();
 await page.getByRole('button',{name:'Chuẩn bị xe mẫu nếu chưa đăng ký'}).click();
 await expect(page.getByRole('status').filter({hasText:/xe mẫu/i})).toBeVisible();
 const before=(await get('/parking-sessions')).length;
 await run({id:'blank'});
 expect((await get('/parking-sessions')).length).toBe(before);
 await page.getByRole('button',{name:'Đóng',exact:true}).last().click();
 for(let round=1;round<=3;round++){
  for(const sample of [car,motorbike]){
   await openEntry();
   const count=(await get('/parking-sessions')).length;
   await run(sample);
   expect((await get('/parking-sessions')).length).toBe(count);
   const entry=await action('Xác nhận xe vào',/^\/ai\/check-in$/,201);
   await expect(page.getByLabel('Biển số nhận diện',{exact:true})).toHaveCount(0);
   expect(entry.status).toBe('ACTIVE');
   const findSpot=async()=> (await get('/parking-spots?parking_lot_id=1')).find(row=>row.id===entry.parking_spot_id);
   expect((await findSpot()).status).toBe('OCCUPIED');
   expect((await get('/dashboard-data/vehicles')).find(row=>row.id===entry.vehicle_id).vehicle_type).toBe(sample.key);
   const evidence=await request.get(base+entry.entry_plate_image,{headers});
   expect(evidence.ok()).toBeTruthy();
   await page.getByRole('button',{name:'Xe ra bằng AI lượt '+entry.id,exact:true}).click();
   if(round===1&&sample===car){
    await run(motorbike);
    await action('Xác nhận xe ra',/^\/ai\/check-out\/\d+$/,409);
    expect((await get('/parking-sessions?session_status=ACTIVE')).some(row=>row.id===entry.id)).toBe(true);
    expect((await findSpot()).status).toBe('OCCUPIED');
   }
   await run(sample);
   const departure=await action('Xác nhận xe ra',/^\/ai\/check-out\/\d+$/,200);
   await expect(page.getByLabel('Biển số nhận diện',{exact:true})).toHaveCount(0);
   expect(departure.status).toBe('COMPLETED');
   expect((await findSpot()).status).toBe('AVAILABLE');
   expect((await request.get(base+departure.exit_plate_image,{headers})).ok()).toBeTruthy();
   transactions.push({round,sample:sample.id,entry:entry.status,exit:departure.status,spot:'AVAILABLE'});
  }
 }
 if(process.env.FRONTEND_ARTIFACT_DIR){
  await mkdir(process.env.FRONTEND_ARTIFACT_DIR,{recursive:true});
  await writeFile(join(process.env.FRONTEND_ARTIFACT_DIR,'ai-golden-web.json'),JSON.stringify({
   transactions,recognition_attempts:delays,blank_rejected:true,incorrect_exit_rejected:true,
  },null,2));
 }
});
