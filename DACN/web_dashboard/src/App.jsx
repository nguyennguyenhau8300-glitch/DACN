import {useState,useEffect,useCallback,useRef} from 'react';
import {Bell,LayoutDashboard,Grid2X2,ArrowLeftRight,CalendarDays,Car,PlugZap,Receipt,Settings,Users,LogOut,RefreshCw,Menu,AlertCircle,CheckCircle2,Leaf,ArrowRight,ShieldCheck} from 'lucide-react';
import {api,parkingSnapshot,roleName} from './api';
import {Button,Field,Empty} from './ui';
import {PageContent} from './Pages';
import {ActionModal} from './Forms';
import {IncidentBanner} from './Alerts';
import {PersonalFields,RegistrationVehicleFields,CustomerProfile} from './CustomerProfile';
import {useRealtime} from './realtime';

const NAV=[['overview','Tổng quan',LayoutDashboard],['parking','Sơ đồ bãi xe',Grid2X2],['routing','Gợi ý & đường đi',Grid2X2],['operations','Xe vào / ra',ArrowLeftRight,'staff'],['reservations','Đặt chỗ',CalendarDays],['vehicles','Phương tiện',Car],['profile','Thông tin của tôi',Users],['charging','Sạc & thiết bị IoT',PlugZap,'staff'],['alerts','Cảnh báo & sự cố',Bell,'staff'],['payments','Thanh toán',Receipt],['checkout','Thanh toán thử',Receipt],['analytics','Báo cáo',LayoutDashboard,'manager'],['pricing','Bảng giá & bãi xe',Settings,'manager'],['schedules','Giá ngày / đêm',Settings,'manager'],['users','Tài khoản',Users,'admin']];
const emptyData={spots:[],areas:[],vehicles:[],sessions:[],reservations:[],payments:[],devices:[],prices:[],users:[],alerts:{items:[],open_count:0,unacknowledged_count:0},capacity:null,report:null};
NAV.splice(3,0,['camera','Camera & cổng',Car,'staff']);
NAV.splice(4,0,['pos','POS · Quét vé',Receipt,'staff']);
NAV.splice(5,0,['simulation','Giả lập vận hành',PlugZap,'manager']);
function Auth({onLogin}) {
 const [register,setRegister]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState('');
 async function submit(e){e.preventDefault();setBusy(true);setError('');const f=Object.fromEntries(new FormData(e.currentTarget));try{
   if(register)await api('/auth/register',{method:'POST',body:{full_name:f.full_name,date_of_birth:f.date_of_birth,hometown:f.hometown,email:f.email,password:f.password,vehicle:{license_plate:f.license_plate,vehicle_type:f.vehicle_type,energy_type:f.energy_type}}});
   const response=await api('/auth/login',{method:'POST',body:{email:f.email,password:f.password}});onLogin(response);
 }catch(e){setError(e.message);}finally{setBusy(false);}}
 return <main className="auth"><section className="auth-story"><div className="brand"><span className="brand-icon">P</span>parkly<span className="brand-tag">SMART PARKING</span></div><div><span className="eyebrow">MỖI CHỖ ĐỖ. MỘT KẾT NỐI.</span><h1>Bãi xe thông minh.<br/>Vận hành nhẹ nhàng.</h1><p>Theo dõi ô đỗ, đón xe và quản lý điểm sạc trong một không gian làm việc.</p><div className="auth-map" aria-hidden="true">{Array.from({length:15},(_,i)=><div key={i} className={i%4===0?'electric':i%3===0?'filled':''}>{i%4===0?<PlugZap/>:<Car/>}<small>{String(i+1).padStart(2,'0')}</small></div>)}</div></div><span className="auth-foot"><Leaf size={17}/> Kết nối bãi xe · Đồng hành cùng xe điện</span></section><section className="auth-form"><div className="mobile-brand">P / parkly</div><div className={"auth-card "+(register?"is-register":"")}><div className="auth-mark"><ShieldCheck size={26}/></div><h2>{register?'Tạo tài khoản':'Chào mừng trở lại'}</h2><p>{register?'Đăng ký để quản lý xe và đặt chỗ của bạn.':'Đăng nhập để bắt đầu quản lý bãi xe.'}</p><form onSubmit={submit}>{register&&<PersonalFields/>}<Field label="Email"><input name="email" type="email" placeholder="ban@example.com" autoComplete="username" required/></Field><Field label="Mật khẩu"><input name="password" type="password" autoComplete={register?'new-password':'current-password'} minLength={6} required/></Field>{register&&<RegistrationVehicleFields/>}{error&&<div role="alert" className="error-box">{error}</div>}<Button busy={busy} type="submit" kind="wide">{register?'Tạo tài khoản':'Đăng nhập'}<ArrowRight size={18}/></Button></form><p className="auth-switch">{register?'Đã có tài khoản?':'Chưa có tài khoản?'} <button onClick={()=>{setRegister(!register);setError('');}}>{register?'Đăng nhập':'Đăng ký'}</button></p></div><small className="auth-caption">Smart Parking · Đồ án chuyên ngành</small></section></main>;
}
export default function App(){
 const [user,setUser]=useState(null),[boot,setBoot]=useState(true),[lots,setLots]=useState([]),[lotId,setLotId]=useState(''),[lotsError,setLotsError]=useState('');
 const [requestedPage,setRequestedPage]=useState(location.hash.slice(1)||'overview'),[mobile,setMobile]=useState(false),[data,setData]=useState(null),[error,setError]=useState(''),[updated,setUpdated]=useState(null),[revision,setRevision]=useState(0),[loading,setLoading]=useState(false),[modal,setModal]=useState(null),[toast,setToast]=useState('');
 const [sessionPage,setSessionPage]=useState(0),[paymentPage,setPaymentPage]=useState(0),[userPage,setUserPage]=useState(0);
 const loadedScope=useRef('');
 const requestRefresh=useRef(null);
 const refresh=useCallback(()=>{
  setRevision(v=>v+1);
  requestRefresh.current?.();
 },[]);
 const socketStatus=useRealtime(user,refresh);
 const staff=['ADMIN','MANAGER','SECURITY'].includes(user?.role),manager=['ADMIN','MANAGER'].includes(user?.role),admin=user?.role==='ADMIN';
 const logout=useCallback(()=>{sessionStorage.removeItem('parking-token');setUser(null);setLots([]);setLotId('');setData(null);setModal(null);setBoot(false);},[]);
 useEffect(()=>{const abort=new AbortController();if(sessionStorage.getItem('parking-token'))api('/auth/me',{signal:abort.signal}).then(setUser).catch(e=>{if(e.name!=='AbortError')logout();}).finally(()=>{if(!abort.signal.aborted)setBoot(false);});else setBoot(false);window.addEventListener('parking-auth-expired',logout);return()=>{abort.abort();window.removeEventListener('parking-auth-expired',logout);};},[logout]);
 useEffect(()=>{const f=()=>{setRequestedPage(location.hash.slice(1)||'overview');setMobile(false);};window.addEventListener('hashchange',f);return()=>window.removeEventListener('hashchange',f);},[]);
 const navigation=NAV.filter(n=>!n[3]||(n[3]==='staff'?staff:n[3]==='manager'?manager:admin));
 const current=navigation.find(n=>n[0]===requestedPage)||navigation[0];
 const page=current[0];
 useEffect(()=>{if(user&&page!==requestedPage)location.hash=page;},[user,page,requestedPage]);
 const reloadLots=useCallback(async()=>{
  const token=sessionStorage.getItem('parking-token');
  if(!token)return;
  try{
   const rows=await api('/parking-lots');
   if(sessionStorage.getItem('parking-token')!==token)return;
   setLots(rows);
   setLotsError('');
   setLotId(id=>rows.some(r=>String(r.id)===String(id))?id:String(rows[0]?.id||''));
  }catch(e){
   if(sessionStorage.getItem('parking-token')===token)setLotsError(e.message);
  }
 },[]);
 useEffect(()=>{if(user)reloadLots();},[user,reloadLots]);
 useEffect(()=>{setSessionPage(0);setPaymentPage(0);setUserPage(0);},[lotId]);
 useEffect(()=>{
  if(!user){setData(null);return;}
  const controller=new AbortController();
  const token=sessionStorage.getItem('parking-token');
  let working=false, queued=false;
  const scope=`${user.id}:${user.role}:${lotId}:${sessionPage}:${paymentPage}:${userPage}`;
  if(loadedScope.current!==scope){
   setData(null);
   setUpdated(null);
   loadedScope.current=scope;
  }
  setError('');

  const isCurrent=()=>!controller.signal.aborted&&sessionStorage.getItem('parking-token')===token;

  function schedule(){
   if(!isCurrent())return;
   if(working){queued=true;return;}
   void load();
  }

  async function load(){
   working=true;
   setLoading(true);
   const batch=new AbortController();
   const options={signal:AbortSignal.any([controller.signal,batch.signal])};
   const q=`parking_lot_id=${lotId}`;
   let checkingAccount=true;
   try{
    const account=await api('/auth/me',options);
    if(!isCurrent())return;
    checkingAccount=false;
    if(account.id!==user.id||account.role!==user.role){
     controller.abort();
     setData(null);setUpdated(null);setModal(null);setUser(account);
     return;
    }
    if(!lotId)return;
    const endpoints={
     areas:`/parking-areas?${q}`,
     vehicles:staff?'/dashboard-data/vehicles':'/vehicles',
     sessions:`/parking-sessions?${q}&limit=25&offset=${sessionPage*25}`,
     reservations:staff?`/dashboard-data/reservations?${q}`:'/reservations',
     payments:`/payments?${q}&limit=25&offset=${paymentPage*25}`,
     prices:`/pricing-rules?${q}`,
     devices:staff?`/iot/devices?${q}`:null,
     report:manager?`/reports/summary?${q}`:null,
     users:admin?`/users?limit=25&offset=${userPage*25}`:null,
     alerts:staff?`/alerts?${q}&status=OPEN&limit=5`:null,
    };
    const [parking,...rows]=await Promise.all([
     parkingSnapshot(lotId,options),
     ...Object.entries(endpoints).map(async ([key,path])=>[
      key,path?(await api(path,options)??emptyData[key]):emptyData[key],
     ]),
    ]);
    if(isCurrent()){
     setData({...Object.fromEntries(rows),spots:parking?.spots??emptyData.spots,capacity:parking?.capacity??emptyData.capacity});
     setUpdated(new Date());
     setError('');
    }
   }catch(e){
    if(!isCurrent())return;
    if(checkingAccount&&(e.status===401||e.status===403)){controller.abort();logout();return;}
    if(e.status===403){setData(null);setUpdated(null);setModal(null);}
    setError(e.message);
   }finally{
    batch.abort();
    working=false;
    if(isCurrent()){
     if(queued){queued=false;schedule();}
     else setLoading(false);
    }
   }
  }
  requestRefresh.current=schedule;
  schedule();
  const timer=setInterval(()=>{if(!document.hidden)schedule();},15000);
  return()=>{requestRefresh.current=null;controller.abort();clearInterval(timer);};
 },[user,lotId,sessionPage,paymentPage,userPage,staff,manager,admin,logout]);
 useEffect(()=>{if(!toast)return;const t=setTimeout(()=>setToast(''),5000);return()=>clearTimeout(t);},[toast]);
 const notify=message=>{setToast(message);refresh();};
 const open=(type,item={})=>setModal({type,item});
 const ctx={user,setUser,setLotId,socketStatus,revision,staff,manager,admin,lotId:Number(lotId),lot:lots.find(l=>String(l.id)===String(lotId)),lots,data:data||emptyData,open,notify,refresh,reloadLots,sessionPage,setSessionPage,paymentPage,setPaymentPage,userPage,setUserPage};
 if(boot)return <div className="splash"><span className="brand-icon">P</span><p>Đang mở bãi xe…</p></div>;
 if(!user)return <Auth onLogin={r=>{sessionStorage.setItem('parking-token',r.access_token);setUser(r.user);location.hash='overview';}}/>;
 return <div className="app"><aside className={'sidebar '+(mobile?'is-open':'')}><a href="#overview" className="brand"><span className="brand-icon">P</span><span>parkly<small>SMART PARKING</small></span></a><div className="nav-caption">KHÔNG GIAN LÀM VIỆC</div><nav>{navigation.map(([key,label,Icon])=><a key={key} href={'#'+key} className={page===key?'active':''}><Icon size={19}/>{label}{page===key&&<i/>}</a>)}</nav><div className="sidebar-bottom"><div className="eco-note"><PlugZap size={19}/><span>Sẵn sàng cho<br/><strong>hành trình xanh</strong></span></div><div className="profile"><span className="avatar">{user.full_name.slice(0,1).toUpperCase()}</span><div><b>{user.full_name}</b><small>{roleName[user.role]}</small></div><button aria-label="Đăng xuất" className="icon-button" onClick={logout}><LogOut size={18}/></button></div></div></aside>{mobile&&<button aria-label="Đóng menu" className="sidebar-scrim" onClick={()=>setMobile(false)}/>}
 <div className="workspace"><header className="topbar"><button className="icon-button mobile-menu" aria-label="Mở menu" onClick={()=>setMobile(!mobile)}><Menu size={23}/></button><nav className="topbar-location" aria-label="Vị trí trang"><a className="topbar-home" href="#overview" aria-label="Parkly — Về trang chủ" onClick={()=>setMobile(false)}><span className="brand-icon" aria-hidden="true">P</span></a><div className="topbar-page-path"><a href="#overview" onClick={()=>setMobile(false)}>parkly</a><span className="topbar-separator" aria-hidden="true">/</span><span className="topbar-page-name" aria-current="page">{current[1]}</span></div></nav><div className="topbar-right"><span className="connection"><i className={error||lotsError?'bad':''}/>{error||lotsError?'Chưa đồng bộ':loading?'Đang đồng bộ':'Kết nối hệ thống'}</span><label className="lot-select"><span className="sr-only">Bãi xe đang xem</span><select value={lotId} onChange={e=>{setLotId(e.target.value);setModal(null);}}>{lots.map(l=><option key={l.id} value={l.id}>{l.name}</option>)}{!lots.length&&<option value="">Chưa có bãi xe</option>}</select></label></div></header>
 <main className="main-content"><div className="page-heading"><div><h1>{current[1]}</h1><p>{page==='overview'?'Một góc nhìn rõ ràng cho mọi hoạt động trong bãi.':page==='parking'?'Chọn một ô đỗ để xem chi tiết và thực hiện thao tác.':page==='charging'?'Theo dõi điểm sạc, kết nối và dữ liệu mới nhất.':page==='simulation'?'Theo dõi tín hiệu, giao dịch và bằng chứng trong bãi mô phỏng.':'Quản lý và tra cứu thông tin trong bãi xe của bạn.'}</p></div><Button kind="secondary" busy={loading} onClick={()=>{reloadLots();refresh();}}><RefreshCw size={16}/>Làm mới</Button></div>
 {staff&&data&&<IncidentBanner summary={data.alerts}/>}
 {(error||lotsError)&&<div role="alert" className="error-box"><AlertCircle size={18}/>{error||lotsError}{data&&' Dữ liệu bên dưới là lần cập nhật trước.'}</div>}
 {page==='profile'?<CustomerProfile ctx={ctx}/>:!lotId&&!lotsError?<section className="panel"><Empty title="Chưa có bãi xe">{admin?'Tạo bãi đầu tiên để bắt đầu cấu hình sơ đồ.':'Bãi xe chưa được quản trị viên cấu hình.'}</Empty>{admin&&<div className="center"><Button onClick={()=>open('lot')}>Tạo bãi xe</Button></div>}</section>:!data&&!error?<div className="skeleton-grid">{[1,2,3,4].map(i=><div key={i} className="skeleton"/>)}<div className="skeleton large"/></div>:data?<PageContent page={page} ctx={ctx}/>:null}
 <footer className="footer"><span>Parkly · Smart Parking</span><span>{updated?'Cập nhật '+updated.toLocaleTimeString('vi-VN'):'Chưa có dữ liệu'} · Tự làm mới mỗi 15 giây</span></footer></main></div>
 {toast&&<div role="status" className="toast"><CheckCircle2 size={19}/>{toast}</div>}{modal&&<ActionModal key={modal.type+String(modal.item.id||'')} descriptor={modal} ctx={ctx} onClose={()=>setModal(null)}/>}</div>;
}
