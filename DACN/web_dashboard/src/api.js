const BASE = import.meta.env.VITE_API_BASE_URL ?? (import.meta.env.DEV ? '/api' : '');
export {BASE};
export async function api(path, options={}) {
  const {body, signal, timeout=20000, ...rest}=options;
  const token=sessionStorage.getItem('parking-token');
  const headers={...(token ? {Authorization:`Bearer ${token}`} : {}),...rest.headers};
  if(body && !(body instanceof FormData)) headers['Content-Type']='application/json';
  let response;
  try { response=await fetch(BASE+path,{...rest,headers,body:body instanceof FormData ? body : body ? JSON.stringify(body) : undefined,
    signal:signal ? AbortSignal.any([signal,AbortSignal.timeout(timeout)]) : AbortSignal.timeout(timeout)}); }
  catch(e) { if(e.name==='AbortError') throw e; throw new Error('Không kết nối được máy chủ. Kiểm tra backend rồi thử lại.'); }
  const data=await response.json().catch(e=>{if(e.name==='AbortError')throw e;return null;});
  if(!response.ok) {
    if(response.status===401 && token && sessionStorage.getItem('parking-token')===token) {
      window.dispatchEvent(new Event('parking-auth-expired'));
    }
    const detail=data?.detail;
    const error=new Error(Array.isArray(detail) ? detail.map(e=>`${e.loc?.slice(1).join('.')}: ${e.msg}`).join('; ') : typeof detail==='string' ? detail : `Yêu cầu thất bại (${response.status}).`);
    error.status=response.status;
    throw error;
  }
  return data;
}

export async function parkingSnapshot(lotId, options) {
  try {
    return await api(`/parking-lots/${lotId}/snapshot`, options);
  } catch (error) {
    if (error.status !== 404) throw error;
    const [spots, capacity] = await Promise.all([
      api(`/parking-spots?parking_lot_id=${lotId}`, options),
      api(`/parking-lots/${lotId}/capacity`, options),
    ]);
    return {spots, capacity};
  }
}

const currencyFormat = new Intl.NumberFormat('vi-VN', {style:'currency', currency:'VND', maximumFractionDigits:2});
const dateOptions = {dateStyle:'short', timeZone:'Asia/Ho_Chi_Minh'};
const shortDate = new Intl.DateTimeFormat('vi-VN', {...dateOptions, timeStyle:'short'});
const fullDate = new Intl.DateTimeFormat('vi-VN', {...dateOptions, timeStyle:'medium'});
export const money=value=>currencyFormat.format(Number(value||0));
export const date=(value,withSeconds=false)=>value ? (withSeconds ? fullDate : shortDate).format(new Date(/[Zz]|[+-]\d\d:\d\d$/.test(value)?value:value+'+07:00')) : '—';
export const localTime=(minutes=0)=>new Date(Date.now()+7*3600000+minutes*60000).toISOString().slice(0,16);
export const roleName={ADMIN:'Quản trị viên',MANAGER:'Quản lý',SECURITY:'Bảo vệ',CUSTOMER:'Khách hàng'};
export const vehicleName=v=>`${v.vehicle_type==='CAR' || v.spot_type==='CAR' || v.spot_type==='DISABLED' ? 'Ô tô':'Xe máy'} ${v.energy_type==='ELECTRIC'?'điện':'xăng'}`;
export const statusName={AVAILABLE:'Còn trống',OCCUPIED:'Có xe',RESERVED:'Đã giữ chỗ',MAINTENANCE:'Bảo trì',PLANNED:'Chưa vận hành',READY:'Sẵn sàng',OFFLINE:'Mất kết nối',ONLINE:'Trực tuyến',NEVER_SEEN:'Chưa kết nối',DISABLED:'Đã tắt',CHARGING:'Đang sạc',FAULT:'Báo lỗi',ACTIVE:'Đang gửi',COMPLETED:'Hoàn tất',CONFIRMED:'Đã xác nhận',PENDING:'Chờ xác nhận',CANCELLED:'Đã hủy',EXPIRED:'Hết hạn',SUCCESS:'Đã thanh toán'};

export const defaultBookingPolicy={max_advance_minutes:120,checkin_window_minutes:120,clockOffset:0};
const minute=60000;
const bookingWallTime=epoch=>new Date(epoch+7*3600000).toISOString().slice(0,16);
export const bookingLimits=policy=>{
 const now=Date.now()+policy.clockOffset;
 return {min:bookingWallTime(Math.ceil(now/minute)*minute),max:bookingWallTime(now+policy.max_advance_minutes*minute)};
};
export const bookingExpiry=(start,minutes=defaultBookingPolicy.checkin_window_minutes)=>{
 const timestamp=new Date(start+'+07:00').getTime();
 return Number.isFinite(timestamp)?bookingWallTime(timestamp+minutes*minute):'';
};
export const plateKey=value=>(value||'').toUpperCase().replace(/[ .-]/g,'');

export const plateExample=vehicleType=>vehicleType==='CAR'?'VD: 30F-222.22':'VD: 29-B1 555.55';
