import {useEffect,useState} from 'react';
import {AlertTriangle,CheckCircle2} from 'lucide-react';
import {api,date,vehicleName} from './api';
import {Button,Field,Table} from './ui';

const types={OVERHEAT:'Quá nhiệt',CHARGER_FAULT:'Lỗi điểm sạc',CONNECTION_LOST:'Mất kết nối / thiếu số đo',WRONG_PARKING:'Đỗ sai vị trí'};
const states={OPEN:'Chưa xác nhận',ACKNOWLEDGED:'Đã xác nhận',RESOLVED:'Đã kết thúc'};

function Evidence({item}){
 const d=item.details||{};
 if(item.kind==='OVERHEAT')return <small>{d.temperature_c} °C · Ngưỡng mô phỏng {d.trigger_c} °C</small>;
 if(item.kind==='WRONG_PARKING')return <small>Quan sát: {vehicleName({vehicle_type:d.observed_vehicle_type,energy_type:d.observed_energy_type})}<br/>Ô dành cho: {vehicleName({vehicle_type:d.expected_vehicle_type,energy_type:d.expected_energy_type})}</small>;
 if(item.kind==='CONNECTION_LOST')return <small>Quá hạn {d.timeout_seconds} giây · Số đo cuối: {date(d.last_telemetry_at)}</small>;
 return <small>Thiết bị báo: {d.charger_status}</small>;
}

export function IncidentBanner({summary}){
 if(!summary?.open_count)return null;
 return <a className="incident-banner" href="#alerts"><AlertTriangle size={20}/><span><b>{summary.open_count} sự cố đang mở</b><small>{summary.unacknowledged_count} chưa được nhân viên xác nhận · Xem cảnh báo và nhật ký</small></span></a>;
}

export function AlertsPage({ctx}){
 const [status,setStatus]=useState('OPEN'),[kind,setKind]=useState('ALL'),[page,setPage]=useState(0),[revision,setRevision]=useState(0);
 const [data,setData]=useState(null),[error,setError]=useState(''),[busy,setBusy]=useState(null),[loading,setLoading]=useState(false);
 useEffect(()=>{
  const controller=new AbortController();setLoading(true);
  api(`/alerts?parking_lot_id=${ctx.lotId}&status=${status}&kind=${kind}&limit=25&offset=${page*25}`,{signal:controller.signal})
   .then(rows=>{setData(rows);setError('');}).catch(e=>{if(e.name!=='AbortError')setError(e.message);}).finally(()=>{if(!controller.signal.aborted)setLoading(false);});
  return()=>controller.abort();
 },[ctx.lotId,status,kind,page,revision,ctx.data.alerts]);
 async function acknowledge(row){setBusy(row.id);setError('');try{await api(`/alerts/${row.id}/acknowledge`,{method:'PATCH'});setRevision(v=>v+1);ctx.notify('Đã xác nhận tiếp nhận sự cố.');}catch(e){setError(e.message);}finally{setBusy(null);}}
 return <section className="panel incident-panel"><div className="panel-head"><div><h2>Cảnh báo & nhật ký sự cố</h2><p>{data?`${data.open_count} đang mở · ${data.unacknowledged_count} chưa xác nhận`:'Đang tải nhật ký…'}</p></div><AlertTriangle size={22}/></div>
  <div className="incident-filters"><Field label="Trạng thái sự cố"><select value={status} onChange={e=>{setStatus(e.target.value);setPage(0);}}><option value="OPEN">Đang mở (gồm đã xác nhận)</option><option value="ACKNOWLEDGED">Đã xác nhận</option><option value="RESOLVED">Đã kết thúc</option><option value="ALL">Tất cả lịch sử</option></select></Field>
  <Field label="Loại sự cố"><select value={kind} onChange={e=>{setKind(e.target.value);setPage(0);}}><option value="ALL">Tất cả loại</option>{Object.entries(types).map(([value,label])=><option value={value} key={value}>{label}</option>)}</select></Field></div>
  <p className="incident-explanation">Xác nhận là đã tiếp nhận xử lý. Sự cố chỉ tự kết thúc khi có dữ liệu khôi phục phù hợp. Đỗ sai nhóm xe dựa trên dữ liệu quan sát IoT/mô phỏng; cảm biến có/trống không tự nhận dạng loại xe.</p>
  {error&&<div role="alert" className="error-box">{error}</div>}
  {data&&<Table headers={['Sự cố / mức độ','Vị trí / thiết bị','Phát hiện / cập nhật','Xử lý / kết thúc','Thao tác']} empty={!data.items.length}>{data.items.map(row=><tr key={row.id}>
   <td><span className={'incident-severity '+row.severity.toLowerCase()}>{row.severity==='CRITICAL'?'Khẩn cấp':'Cảnh báo'}</span><b>{types[row.kind]}</b><small>{row.message}</small><Evidence item={row}/><small>Mã sự cố #{row.id}</small></td>
   <td><b>{row.spot_code}</b><small>{row.device_code}</small></td><td>{date(row.opened_at)}<small>Lần ghi nhận cuối: {date(row.last_seen_at)}</small></td>
   <td><span className={'incident-state '+row.status.toLowerCase()}>{row.status==='RESOLVED'&&<CheckCircle2 size={13}/>} {states[row.status]}</span>{row.acknowledged_at&&<small>Tiếp nhận: {date(row.acknowledged_at)} · Tài khoản #{row.acknowledged_by??'đã xóa'}</small>}{row.resolved_at&&<><small>Kết thúc: {date(row.resolved_at)}</small><small>{row.resolution}</small></>}</td>
   <td>{row.status==='OPEN'&&<Button kind="small secondary" busy={busy===row.id} disabled={busy!==null} onClick={()=>acknowledge(row)}>Xác nhận tiếp nhận</Button>}</td>
  </tr>)}</Table>}
  <div className="pagination"><span>{loading?'Đang tải…':`${data?.total??0} sự cố · Trang ${page+1}`}</span><Button kind="ghost" disabled={page===0||loading} onClick={()=>setPage(v=>v-1)}>Trước</Button><Button kind="ghost" disabled={loading||!data||(page+1)*25>=data.total} onClick={()=>setPage(v=>v+1)}>Sau</Button></div>
 </section>;
}
