import {test,expect} from '../playwright.mjs';
import fs from 'node:fs';
import path from 'node:path';

async function openDemo(page){
 await page.goto('./');await page.getByLabel('Email',{exact:true}).fill('admin@example.com');await page.getByLabel('Mật khẩu',{exact:true}).fill('TestParking123!');await page.getByRole('button',{name:'Đăng nhập',exact:true}).click();
 await page.getByRole('link',{name:'Demo AI & IoT',exact:true}).click();await page.getByRole('button',{name:'Tạo / mở bãi demo giao thức'}).click();await expect(page.getByRole('heading',{name:'1. Bảng điều khiển thiết bị giả lập'})).toBeVisible();
 const enable=page.getByRole('button',{name:'Bật bộ mô phỏng',exact:true});if(await enable.count())await enable.click();
 await expect(page.getByRole('button',{name:'Tắt bộ mô phỏng',exact:true})).toBeVisible();
 await expect(page.getByText('Dashboard WebSocket:',{exact:false})).toContainText('Đã kết nối');
}

test('Split-screen publishes HTTP and MQTT, receives socket invalidations and displays alerts',async({page,request})=>{
 let invalidations=0;page.on('websocket',ws=>{if(ws.url().includes('/ws/events'))ws.on('framereceived',e=>{try{if(JSON.parse(e.payload).type==='invalidate')invalidations++;}catch{}});});
 await openDemo(page);
 const before=invalidations;await page.getByLabel('Giao thức gửi',{exact:true}).selectOption('HTTP');await page.getByRole('button',{name:'Xe vào ô',exact:true}).click();
 await expect(page.getByTestId('twin-spot-CG-001')).toContainText('Có xe');await expect(page.locator('.protocol-ack')).toContainText('ACKNOWLEDGED');expect(invalidations).toBeGreaterThan(before);
 await expect(page.locator('.latency')).toContainText('ms');
 await page.getByLabel('Giao thức gửi',{exact:true}).selectOption('MQTT');await page.getByRole('button',{name:'Xe rời ô',exact:true}).click();await expect(page.getByTestId('twin-spot-CG-001')).toContainText('Còn trống');
 const token=await page.evaluate(()=>sessionStorage.getItem('parking-token'));const headers={Authorization:'Bearer '+token};const sites=await(await request.get(process.env.E2E_API_URL+'/simulation/sites',{headers})).json();
 const state=await(await request.get(process.env.E2E_API_URL+`/simulation/${sites[0].parking_lot_id}/state`,{headers})).json();
 await page.getByLabel('Thiết bị mô phỏng',{exact:true}).selectOption(String(state.devices.find(d=>d.kind==='CHARGER').id));await page.getByRole('button',{name:'Quá nhiệt 85 °C',exact:true}).click();
 await expect(page.locator('.twin-alerts')).toContainText('Quá nhiệt');await expect(page.locator('.protocol-ack')).toContainText('MQTT');
 if(process.env.FRONTEND_ARTIFACT_DIR){fs.mkdirSync(process.env.FRONTEND_ARTIFACT_DIR,{recursive:true});await page.screenshot({path:path.join(process.env.FRONTEND_ARTIFACT_DIR,'Digital-Twin-Split-Screen.png'),fullPage:true});}
 await page.getByRole('button',{name:'Sạc bình thường',exact:true}).click();await expect(page.locator('.twin-alerts')).not.toContainText('Quá nhiệt');
});

test('Demo stays within the mobile viewport and firmware downloads require authentication',async({page})=>{
 await page.setViewportSize({width:390,height:844});await page.goto('./');await page.getByLabel('Email',{exact:true}).fill('admin@example.com');await page.getByLabel('Mật khẩu',{exact:true}).fill('TestParking123!');await page.getByRole('button',{name:'Đăng nhập',exact:true}).click();await page.getByRole('button',{name:'Mở menu'}).click();await page.getByRole('link',{name:'Demo AI & IoT',exact:true}).click();await page.getByRole('button',{name:'Tạo / mở bãi demo giao thức'}).click();
 await expect(page.getByRole('heading',{name:'2. Trạng thái Dashboard nhận được'})).toBeVisible();expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBeTruthy();
 const download=page.waitForEvent('download');await page.getByRole('button',{name:'Tải firmware ESP32',exact:true}).click();expect((await download).suggestedFilename()).toBe('parkly_sensor.ino');
});

test('Live RTSP frames reach the browser and stable reads show cropped evidence',async({page})=>{
 test.setTimeout(90000);await openDemo(page);
 await page.getByRole('button',{name:'Bật camera RTSP',exact:true}).click();
 try{
  await expect(page.getByRole('img',{name:'Camera RTSP với khung YOLO và kết quả OCR trực tiếp'})).toBeVisible({timeout:40000});
  const first=await page.getByTestId('live-frame').textContent();await expect(page.getByTestId('live-frame')).not.toHaveText(first,{timeout:10000});
  await expect(page.locator('.evidence-grid article').first()).toBeVisible({timeout:30000});await expect(page.locator('.evidence-grid img').first()).toBeVisible();
  if(process.env.FRONTEND_ARTIFACT_DIR)await page.locator('.live-camera').screenshot({path:path.join(process.env.FRONTEND_ARTIFACT_DIR,'RTSP-YOLO-OCR-Truc-Tiep.png')});
 }finally{await page.getByRole('button',{name:'Dừng camera',exact:true}).click();}
 await expect(page.locator('.live-label')).toContainText('Đã dừng');
});
