import {test, expect} from '../playwright.mjs';

const base = process.env.E2E_API_URL;
const accounts = [
 ['admin', 'Quản trị viên', true, true, true],
 ['manager', 'Quản lý', true, true, false],
 ['security', 'Bảo vệ', true, false, false],
 ['customer', 'Khách hàng', false, false, false],
];

async function login(page, role) {
 await page.goto(base+'/dashboard/');
 await page.getByLabel('Email',{exact:true}).fill(role+'@example.com');
 await page.getByLabel('Mật khẩu',{exact:true}).fill('TestParking123!');
 await page.getByRole('button',{name:'Đăng nhập',exact:true}).click();
 await expect(page.getByRole('heading',{name:'Tổng quan',exact:true})).toBeVisible();
}

test('Published dashboard shows the four roles and rejects restricted direct links',async ({page})=>{
 const restricted = [];
 page.on('request',request=>{
  if(new URL(request.url()).pathname==='/reports/daily')restricted.push(request.url());
 });
 const sidebar = page.locator('.sidebar');
 for(const [role,label,staff,manager,admin] of accounts){
  await login(page,role);
  await expect(sidebar.getByText(label,{exact:true})).toBeVisible();
  await expect(sidebar.getByRole('link',{name:'Sơ đồ bãi xe',exact:true})).toBeVisible();
  await expect(sidebar.getByRole('link',{name:'Xe vào / ra',exact:true})).toHaveCount(Number(staff));
  await expect(sidebar.getByRole('link',{name:'Báo cáo',exact:true})).toHaveCount(Number(manager));
  await expect(sidebar.getByRole('link',{name:'Tài khoản',exact:true})).toHaveCount(Number(admin));
  if(!manager){
   await page.evaluate(()=>location.hash='analytics');
   await expect(page).toHaveURL(/#overview$/);
   await expect(page.getByRole('heading',{name:'Doanh thu & lưu lượng theo ngày'})).toHaveCount(0);
  }
  await sidebar.getByRole('button',{name:'Đăng xuất',exact:true}).click();
 }
 expect(restricted).toHaveLength(0);
});

test('An open dashboard applies a demotion and exits a locked account on refresh',async ({page,request})=>{
 const loginResult = await request.post(base+'/auth/login',{data:{email:'admin@example.com',password:'TestParking123!'}});
 expect(loginResult.status()).toBe(200);
 const headers = {Authorization:'Bearer '+(await loginResult.json()).access_token};
 const list = await request.get(base+'/users',{headers});
 const manager = (await list.json()).find(user=>user.email==='manager@example.com');
 expect(manager).toBeTruthy();
 const access = base+'/users/'+manager.id+'/access';
 try{
  await login(page,'manager');
  await page.getByRole('link',{name:'Báo cáo',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Doanh thu & lưu lượng theo ngày'})).toBeVisible();
  expect((await request.patch(access,{headers,data:{role:'CUSTOMER',is_active:true}})).status()).toBe(200);
  await page.getByRole('button',{name:'Làm mới',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Tổng quan',exact:true})).toBeVisible();
  await expect(page.getByRole('link',{name:'Báo cáo',exact:true})).toHaveCount(0);
  await expect(page.getByRole('link',{name:'Xe vào / ra',exact:true})).toHaveCount(0);
  await expect(page.locator('.sidebar').getByText('Khách hàng',{exact:true})).toBeVisible();

  expect((await request.patch(access,{headers,data:{role:'CUSTOMER',is_active:false}})).status()).toBe(200);
  await page.getByRole('button',{name:'Làm mới',exact:true}).click();
  await expect(page.getByRole('button',{name:'Đăng nhập',exact:true})).toBeVisible();
  expect(await page.evaluate(()=>sessionStorage.getItem('parking-token'))).toBeNull();
 }finally{
  expect((await request.patch(access,{headers,data:{role:'MANAGER',is_active:true}})).status()).toBe(200);
 }
});
