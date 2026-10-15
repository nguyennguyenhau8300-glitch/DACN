const BASE = import.meta.env.VITE_API_BASE_URL ?? (import.meta.env.DEV ? '/api' : '');
export async function api(path, options={}) {
  const {body, signal, timeout=20000, ...rest}=options;
  const token=sessionStorage.getItem('parking-token');
  const headers={...(token ? {Authorization:`Bearer ${token}`} : {}),...rest.headers};
  if(body && !(body instanceof FormData)) headers['Content-Type']='application/json';
  let response;
  try { response=await fetch(BASE+path,{...rest,headers,body:body instanceof FormData ? body : body ? JSON.stringify(body) : undefined,
    signal:signal ? AbortSignal.any([signal,AbortSignal.timeout(timeout)]) : AbortSignal.timeout(timeout)}); }
  catch(e) { if(e.name==='AbortError') throw e; throw new Error('Không kết nối được máy chủ. Kiểm tra backend rồi thử lại.'); }
  const data=await response.json().catch(()=>null);
  if(!response.ok) {
    if(response.status===401 && token) window.dispatchEvent(new Event('parking-auth-expired'));
    const detail=data?.detail;
    throw new Error(Array.isArray(detail) ? detail.map(e=>`${e.loc?.slice(1).join('.')}: ${e.msg}`).join('; ') : typeof detail==='string' ? detail : `Yêu cầu thất bại (${response.status}).`);
  }
  return data;
}
export const money=value=>new Intl.NumberFormat('vi-VN',{style:'currency',currency:'VND',maximumFractionDigits:0}).format(Number(value||0));
export const date=value=>value ? new Intl.DateTimeFormat('vi-VN',{dateStyle:'short',timeStyle:'short',timeZone:'Asia/Ho_Chi_Minh'}).format(new Date(/[Zz]|[+-]\d\d:\d\d$/.test(value)?value:value+'+07:00')) : '—';
export const localTime=(minutes=0)=>new Date(Date.now()+7*3600000+minutes*60000).toISOString().slice(0,16);
export const roleName={ADMIN:'Quản trị viên',MANAGER:'Quản lý',SECURITY:'Nhân viên',CUSTOMER:'Khách hàng'};
export const vehicleName=v=>`${v.vehicle_type==='CAR' || v.spot_type==='CAR' || v.spot_type==='DISABLED' ? 'Ô tô':'Xe máy'} ${v.energy_type==='ELECTRIC'?'điện':'xăng'}`;
export const statusName={AVAILABLE:'Còn trống',OCCUPIED:'Có xe',RESERVED:'Đã giữ chỗ',MAINTENANCE:'Bảo trì',PLANNED:'Chưa vận hành',READY:'Sẵn sàng',OFFLINE:'Mất kết nối',ONLINE:'Trực tuyến',NEVER_SEEN:'Chưa kết nối',DISABLED:'Đã tắt',CHARGING:'Đang sạc',FAULT:'Báo lỗi',ACTIVE:'Đang gửi',COMPLETED:'Hoàn tất',CONFIRMED:'Đã xác nhận',PENDING:'Chờ xác nhận',CANCELLED:'Đã hủy',EXPIRED:'Hết hạn',SUCCESS:'Đã thanh toán'};

// UI booking window: two hours after the chosen start, serialized as Vietnam local time.
export const bookingExpiry=start=>{
 const timestamp=new Date(start+'+07:00').getTime();
 return Number.isFinite(timestamp)?new Date(timestamp+9*3600000).toISOString().slice(0,16):'';
};
export const plateKey=value=>(value||'').toUpperCase().replace(/[ .-]/g,'');

export const plateExample=vehicleType=>vehicleType==='CAR'?'VD: 30F-222.22':'VD: 29-B1 555.55';
