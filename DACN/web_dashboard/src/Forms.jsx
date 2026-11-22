import {useState,useEffect} from 'react';
import {ScanLine,Upload,PlugZap,Car,Info} from 'lucide-react';
import {api,money,date,localTime,vehicleName,roleName,defaultBookingPolicy,bookingLimits,bookingExpiry,plateKey,plateExample} from './api';
import {Modal,Button,Field,Badge,Table,Empty} from './ui';
import {SamplePicker} from './InternalSimulation';
import {FeeDetail} from './FeeDetail';
const titles={customerVehicle:'Đăng ký xe khách hàng',vehicle:'Phương tiện của tôi',checkin:'Ghi nhận xe vào',checkout:'Xác nhận xe ra',reservation:'Đặt chỗ mới',cancel:'Hủy đặt chỗ',payment:'Thu tiền gửi xe',charging:'Trạng thái điểm sạc',device:'Trạng thái thiết bị',price:'Thiết lập bảng giá',user:'Quyền truy cập',lot:'Cấu hình bãi xe',layout:'Tạo sơ đồ bãi',spot:'Chi tiết ô đỗ',ai:'Nhận diện biển số · Xe vào',aiout:'Nhận diện biển số · Xe ra',events:'Lịch sử thiết bị'};
export function ActionModal({descriptor,ctx,onClose}){
 const {type,item}=descriptor;const [busy,setBusy]=useState(false),[error,setError]=useState(''),[result,setResult]=useState(null),[image,setImage]=useState(null),[preview,setPreview]=useState(''),[events,setEvents]=useState(null);
 const reservation=item.reservation;
 const [bookingPolicy,setBookingPolicy]=useState(defaultBookingPolicy);
 const [bookingMode,setBookingMode]=useState('immediate');
 const [slotOptions,setSlotOptions]=useState(null);
 const scheduled=type==='reservation'&&bookingMode==='scheduled';
 const [customerMode,setCustomerMode]=useState('guest'),[customerEmail,setCustomerEmail]=useState('');
 const [vehicleSearch,setVehicleSearch]=useState(''),[addingVehicle,setAddingVehicle]=useState(false),[addedVehicles,setAddedVehicles]=useState([]),[vehicleNotice,setVehicleNotice]=useState('');
 const [newVehicle,setNewVehicle]=useState({license_plate:'',vehicle_type:item.spot?(item.spot.spot_type==='DISABLED'?'CAR':item.spot.spot_type):'MOTORBIKE',energy_type:item.spot?.energy_type||'GASOLINE'});
 const [form,setForm]=useState(()=>({...item,vehicle_id:String(reservation?.vehicle_id||item.vehicle_id||''),parking_spot_id:String(reservation?.parking_spot_id||(type==='reservation'||type==='checkin'?item.spot?.id:'')||''),start_time:localTime(5),expiry_time:localTime(125),vehicle_type:item.vehicle_type||'MOTORBIKE',energy_type:item.energy_type??'GASOLINE',is_active:item.is_active??true,car_capacity:item.car_capacity??30,motorbike_capacity:item.motorbike_capacity??65,electric_car_capacity:item.electric_car_capacity??10,electric_motorbike_capacity:item.electric_motorbike_capacity??25}));
 const change=(key,value)=>setForm(f=>({...f,[key]:value}));
 useEffect(()=>{if(!image){setPreview('');return;}const url=URL.createObjectURL(image);setPreview(url);return()=>URL.revokeObjectURL(url);},[image]);
 useEffect(()=>{if(type!=='events')return;const abort=new AbortController();api('/iot/events?limit=100&device_code='+encodeURIComponent(item.device_code),{signal:abort.signal}).then(setEvents).catch(e=>{if(e.name!=='AbortError')setError(e.message);});return()=>abort.abort();},[type,item.device_code]);
 const vehicles=[...ctx.data.vehicles,...addedVehicles.filter(v=>!ctx.data.vehicles.some(row=>row.id===v.id))].filter(v=>type!=='reservation'||ctx.staff||v.user_id===ctx.user.id);
 const matchingVehicles=type==='checkin'?vehicles.filter(v=>plateKey(v.license_plate).includes(plateKey(vehicleSearch))):vehicles;
 useEffect(()=>{
  if(type!=='reservation')return;
  const abort=new AbortController();
  api('/reservations/policy',{signal:abort.signal}).then(policy=>{
   const at=Date.parse(policy.server_time+'+07:00');
   if(!abort.signal.aborted&&Number.isFinite(at))setBookingPolicy({...policy,clockOffset:at-Date.now()});
  }).catch(()=>{}); // The server also validates submissions when the policy lookup fails.
  return ()=>abort.abort();
 },[type]);
 const limits=bookingLimits(bookingPolicy);
 const deadline=bookingExpiry(form.start_time,bookingPolicy.checkin_window_minutes);
 const validWindow=Boolean(form.start_time&&form.end_time&&form.start_time<form.end_time&&form.start_time>=limits.min);
 const expiresAt=scheduled?(validWindow?(deadline<form.end_time?deadline:form.end_time):''):deadline;
 const selectedVehicle=vehicles.find(v=>v.id===Number(form.vehicle_id));
 const slotQuery=scheduled&&validWindow&&selectedVehicle?new URLSearchParams({
  parking_lot_id:ctx.lotId, vehicle_type:selectedVehicle.vehicle_type, energy_type:selectedVehicle.energy_type,
  start_time:form.start_time, end_time:form.end_time,
 }).toString():'';
 const slotResult=slotOptions?.query===slotQuery?slotOptions:null;
 useEffect(()=>{
  if(!slotQuery)return;
  const abort=new AbortController();
  api('/reservations/available-spots?'+slotQuery,{signal:abort.signal}).then(rows=>{
   if(!abort.signal.aborted)setSlotOptions({query:slotQuery,rows});
  }).catch(e=>{
   if(!abort.signal.aborted)setSlotOptions({query:slotQuery,rows:[],error:e.message});
  });
  return ()=>abort.abort();
 },[slotQuery,ctx.revision]);
 const imageVehicle=result?.vehicle_detection;
 const imageVehicleLabel=imageVehicle?.type==='CAR'?'Ô tô':imageVehicle?.type==='MOTORBIKE'?'Xe máy':null;
 const recognizedVehicle=result?.plate?vehicles.find(v=>plateKey(v.license_plate)===plateKey(result.plate)):null;
 const spots=scheduled?(slotResult?.rows??[]):ctx.data.spots.filter(s=>(s.available_for_booking||s.id===reservation?.parking_spot_id)&&(!selectedVehicle||((s.spot_type==='DISABLED'?'CAR':s.spot_type)===selectedVehicle.vehicle_type&&s.energy_type===selectedVehicle.energy_type)));
 const input=(key,kind='text',extra={})=><input name={key} type={kind} value={form[key]??''} onChange={e=>change(key,e.target.value)} {...extra}/>;
 function fileSelected(e){const file=e.target.files[0];setResult(null);if(file&&!['image/jpeg','image/png','image/webp'].includes(file.type)){setError('Chỉ nhận ảnh JPEG, PNG hoặc WebP.');setImage(null);return;}if(file?.size>8*1024*1024){setError('Ảnh tối đa 8 MB.');setImage(null);return;}setError('');setImage(file||null);}
 function photoForm(){const data=new FormData();if(image)data.append('file',image);if(form.parking_spot_id)data.append('parking_spot_id',form.parking_spot_id);if(form.roi?.trim())data.append('roi',form.roi.trim());if(form.reservation_id)data.append('reservation_id',form.reservation_id);return data;}
 async function recognize(selected){const photo=selected instanceof Blob?selected:image;if(!photo){setError('Chọn ảnh biển số trước.');return;}setBusy(true);setError('');try{const body=photoForm();body.set('file',photo);const r=await api('/ai/recognize',{method:'POST',body,timeout:120000});setResult(r);const vehicle=vehicles.find(v=>plateKey(v.license_plate)===plateKey(r.plate||''));if(vehicle&&!r.needs_review){const candidates=ctx.data.spots.filter(s=>s.available_for_booking&&(s.spot_type==='DISABLED'?'CAR':s.spot_type)===vehicle.vehicle_type&&s.energy_type===vehicle.energy_type);setForm(f=>({...f,vehicle_id:String(vehicle.id),parking_spot_id:candidates.some(s=>s.id===Number(f.parking_spot_id))?f.parking_spot_id:String(candidates[0]?.id||'')}));}}catch(e){setError(e.message);}finally{setBusy(false);}}
 function chooseVehicle(vehicle){
  setForm(current=>{
   const spot=ctx.data.spots.find(s=>s.id===Number(current.parking_spot_id));
   const matches=spot&&vehicle&&(spot.spot_type==='DISABLED'?'CAR':spot.spot_type)===vehicle.vehicle_type&&spot.energy_type===vehicle.energy_type;
   return {...current,vehicle_id:vehicle?String(vehicle.id):'',parking_spot_id:matches||!vehicle?current.parking_spot_id:''};
  });
 }
 function searchVehicle(value){
  setVehicleSearch(value);setVehicleNotice('');
  chooseVehicle(vehicles.find(v=>plateKey(v.license_plate)===plateKey(value)));
 }
 async function saveNewVehicle(){
  setError('');setVehicleNotice('');
  const plate=newVehicle.license_plate.trim().toUpperCase();
  if(plate.length>20||plateKey(plate).length<5||!/^[A-Z0-9 .-]+$/.test(plate)){setError('Nhập biển số hợp lệ, gồm chữ Latin, số, dấu cách, chấm hoặc gạch ngang (5–20 ký tự).');return;}
  const existing=vehicles.find(v=>plateKey(v.license_plate)===plateKey(plate));
  if(existing){chooseVehicle(existing);setVehicleSearch('');setAddingVehicle(false);setVehicleNotice('Biển số đã có trong danh sách. Đã chọn xe với nhóm xe đã đăng ký.');return;}
  setBusy(true);
  try{
   if(ctx.staff&&customerMode==='account'&&!customerEmail.trim())throw new Error('Nhập email tài khoản khách hàng.');
   const vehicle=await api(ctx.staff?'/dashboard-data/vehicles':'/vehicles',{method:'POST',body:{...newVehicle,license_plate:plate,...(ctx.staff?{customer_email:customerMode==='account'?customerEmail.trim():null}:{})}});
   setAddedVehicles(rows=>[...rows,vehicle]);chooseVehicle(vehicle);setVehicleSearch('');setAddingVehicle(false);
   setVehicleNotice('Đã lưu và chọn xe '+vehicle.license_plate+'. Bạn có thể tiếp tục xác nhận.');ctx.refresh();
  }catch(e){setError(e.message);}finally{setBusy(false);}
 }
 async function submit(e){e.preventDefault();setBusy(true);setError('');try{
  let path,body,method='POST',message='Đã lưu thay đổi.';
  if(type==='customerVehicle'){path='/dashboard-data/vehicles';body={license_plate:form.license_plate?.trim(),vehicle_type:form.vehicle_type,energy_type:form.energy_type,brand:form.brand?.trim()||null,color:form.color?.trim()||null,customer_email:customerMode==='account'?customerEmail.trim():null};message='Đã đăng ký xe khách hàng.';}
  if(type==='vehicle'){path='/vehicles'+(item.id?'/'+item.id:'');method=item.id?'PUT':'POST';body={license_plate:form.license_plate?.trim(),vehicle_type:form.vehicle_type,energy_type:form.energy_type,brand:form.brand?.trim()||null,color:form.color?.trim()||null};message=item.id?'Đã cập nhật phương tiện.':'Đã thêm phương tiện của bạn.';}
  if(type==='checkin'){path='/parking-sessions/check-in';body={vehicle_id:Number(form.vehicle_id),parking_spot_id:Number(form.parking_spot_id),reservation_id:reservation?.id||null};message='Đã ghi nhận xe vào bãi.';}
  if(type==='checkout'){path=`/parking-sessions/${item.id}/check-out`;body={};message='Đã hoàn tất lượt gửi. Bạn có thể thu tiền.';}
  if((type==='reservation'||type==='checkin')&&addingVehicle)throw new Error('Lưu xe mới hoặc quay lại chọn xe đã đăng ký trước khi xác nhận.');
  if(type==='reservation'){
   const {min,max}=bookingLimits(bookingPolicy);
   if(!expiresAt||form.start_time<min||(!scheduled&&form.start_time>max))throw new Error('Hãy chọn giờ đến và khung giờ hợp lệ.');
   if(scheduled&&!spots.some(s=>s.id===Number(form.parking_spot_id)))throw new Error('Hãy chọn ô còn trống trong khung giờ.');
   path='/reservations';
   body={vehicle_id:Number(form.vehicle_id),parking_spot_id:Number(form.parking_spot_id),start_time:form.start_time};
   if(scheduled)body.end_time=form.end_time;
   message=scheduled?'Đã đặt ô theo khung giờ.':'Đã đặt và giữ chỗ thành công.';
  }
  if(type==='cancel'){path=`/reservations/${item.id}/cancel`;method='PATCH';message='Đã hủy đặt chỗ.';}
  if(type==='payment'){path='/payments';body={parking_session_id:item.id,payment_method:'CASH'};message='Đã ghi nhận thanh toán tiền mặt.';}
  if(type==='charging'){path=`/parking-spots/${item.id}/charging-status`;method='PATCH';body={charger_status:form.charger_status};}
  if(type==='device'){path=`/iot/devices/${item.device_code}/access`;method='PATCH';body={enabled:!item.enabled};}
  if(type==='price'){path='/pricing-rules'+(item.id?'/'+item.id:'');method=item.id?'PUT':'POST';body={parking_lot_id:ctx.lotId,vehicle_type:form.vehicle_type,energy_type:form.energy_type,first_hour_price:form.first_hour_price,additional_hour_price:form.additional_hour_price,is_active:true};message='Đã cập nhật bảng giá.';}
  if(type==='user'){path=`/users/${item.id}/access`;method='PATCH';body={role:form.role,is_active:form.is_active};}
  if(type==='lot'){path='/parking-lots'+(item.id?'/'+item.id:'');method=item.id?'PUT':'POST';body={name:form.name?.trim(),address:form.address?.trim(),car_capacity:Number(form.car_capacity),motorbike_capacity:Number(form.motorbike_capacity),electric_car_capacity:Number(form.electric_car_capacity),electric_motorbike_capacity:Number(form.electric_motorbike_capacity)};if(item.id)body.is_active=form.is_active;}
  if(type==='layout'){path=`/parking-lots/${ctx.lotId}/initialize-layout`;message='Đã tạo hoặc bổ sung sơ đồ bãi xe.';}
  if(type==='spot'){path=`/parking-spots/${item.id}`;method='PUT';body={status:item.status==='MAINTENANCE'?'AVAILABLE':'MAINTENANCE'};}
  if(type==='ai'||type==='aiout'){if(!image)throw new Error('Chọn ảnh trước.');if(!result||result.needs_review)throw new Error('Cần nhận diện được một biển số rõ ràng trước khi tiếp tục.');path=type==='ai'?'/ai/check-in':`/ai/check-out/${item.id}`;body=photoForm();message=type==='ai'?'Đã nhận diện và ghi nhận xe vào.':'Đã đối chiếu ảnh và ghi nhận xe ra.';}
  const response=await api(path,{method,body,timeout:type.startsWith('ai')?120000:20000});
  if(type==='checkout')message=`Xe đã ra bãi. Phí gửi xe: ${money(response.total_amount)}.`;
  if(type==='lot')await ctx.reloadLots();ctx.notify(message);onClose();
 }catch(e){
  setError(e.message);
  if(e.status===409&&['reservation','cancel','checkin','ai'].includes(type))ctx.refresh();
 }finally{setBusy(false);}}
 const customerFields=<div className="customer-vehicle-fields"><Field label="Khách hàng"><select value={customerMode} onChange={e=>setCustomerMode(e.target.value)}><option value="guest">Khách vãng lai (chưa có tài khoản)</option><option value="account">Khách đã có tài khoản</option></select></Field>{customerMode==='account'&&<Field label="Email tài khoản khách hàng" help="Dùng email khách đã đăng ký. Xe sẽ thuộc tài khoản đó."><input type="email" required value={customerEmail} onChange={e=>setCustomerEmail(e.target.value)} placeholder="khach@example.com"/></Field>}</div>;
 const spotPicker=<Field label="Ô đỗ phù hợp"><select value={scheduled&&!spots.some(s=>s.id===Number(form.parking_spot_id))?'':form.parking_spot_id} required disabled={!!reservation||addingVehicle||(scheduled&&!slotResult)} onChange={e=>change('parking_spot_id',e.target.value)}><option value="">Chọn ô đỗ</option>{spots.map(s=><option key={s.id} value={s.id}>{s.spot_code} · {vehicleName(s)}</option>)}</select></Field>;
 const picker=<>
 {!reservation&&<div className="vehicle-entry">
  <div className="vehicle-entry-tabs"><Button type="button" kind={!addingVehicle?'small':'small secondary'} onClick={()=>{setAddingVehicle(false);setError('');}}>Xe đã lưu trong hệ thống</Button><Button type="button" kind={addingVehicle?'small':'small secondary'} onClick={()=>{setAddingVehicle(true);setVehicleNotice('');setError('');setNewVehicle(v=>({...v,license_plate:vehicleSearch}));}}>Nhập biển số mới</Button></div>
  <p className="vehicle-picker-help">Chọn xe đã lưu để đặt lại; nếu biển số chưa có, chọn “Nhập biển số mới” để đăng ký ngay.</p>
  {addingVehicle?<div className="new-vehicle-fields">{ctx.staff&&customerFields}
   <Field label="Biển số mới"><input value={newVehicle.license_plate} maxLength={20} placeholder={plateExample(newVehicle.vehicle_type)} autoComplete="off" onChange={e=>setNewVehicle(v=>({...v,license_plate:e.target.value.toUpperCase()}))} onKeyDown={e=>{if(e.key==='Enter'){e.preventDefault();saveNewVehicle();}}}/></Field>
   <div className="form-grid"><Field label="Loại xe mới"><select value={newVehicle.vehicle_type} onChange={e=>setNewVehicle(v=>({...v,vehicle_type:e.target.value}))}><option value="MOTORBIKE">Xe máy</option><option value="CAR">Ô tô</option></select></Field><Field label="Nguồn năng lượng xe mới"><select value={newVehicle.energy_type} onChange={e=>setNewVehicle(v=>({...v,energy_type:e.target.value}))}><option value="GASOLINE">Xăng</option><option value="ELECTRIC">Điện</option></select></Field></div>
   <p className="info-note">{ctx.staff?(customerMode==='guest'?'Xe được đăng ký cho khách vãng lai, không gắn vào tài khoản nhân viên.':'Xe được lưu vào tài khoản khách hàng đã chọn.'):'Xe mới được lưu vào tài khoản của bạn.'} Lưu xe xong, tiếp tục xác nhận {type==='reservation'?'đặt chỗ':'xe vào'} bên dưới.</p><Button type="button" kind="secondary wide" onClick={saveNewVehicle}>Lưu xe và chọn</Button>
  </div>:type==='checkin'?<Field label="Tìm biển số" help="Nhập biển số để tìm xe. Biển số trùng chính xác sẽ được tự chọn."><input type="search" value={vehicleSearch} placeholder="Nhập biển số xe…" onChange={e=>searchVehicle(e.target.value)} autoComplete="off"/></Field>:null}
 </div>}
 {(!addingVehicle||reservation)&&<Field label="Phương tiện"><select value={form.vehicle_id} required disabled={!!reservation} onChange={e=>chooseVehicle(vehicles.find(v=>v.id===Number(e.target.value)))}><option value="">Chọn biển số đã đăng ký</option>{(reservation?vehicles:matchingVehicles).map(v=><option key={v.id} value={v.id}>{v.license_plate} · {vehicleName(v)}</option>)}</select></Field>}
 {!addingVehicle&&!reservation&&!matchingVehicles.length&&<p className="info-note">Không có biển số phù hợp. Chọn “Nhập biển số mới” để thêm xe ngay tại đây.</p>}
 {vehicleNotice&&<p className="vehicle-notice" role="status">{vehicleNotice}</p>}
 {!scheduled&&spotPicker}
 {!scheduled&&!spots.length&&<p className="info-note">Chưa có ô phù hợp và sẵn sàng. Kiểm tra loại xe, điểm sạc và kết nối IoT.</p>}</>;

 if(type==='fee')return <Modal title="Chi tiết phí gửi xe" onClose={onClose}><div className="modal-body"><FeeDetail session={item}/><div className="modal-actions"><Button type="button" kind="secondary" onClick={onClose}>Đóng</Button></div></div></Modal>;
 return <Modal title={titles[type]} busy={busy} onClose={onClose}><form onSubmit={submit} className="modal-body"><fieldset disabled={busy}>
 {(type==='vehicle'||type==='customerVehicle')&&<>{type==='customerVehicle'&&customerFields}<Field label="Biển số">{input('license_plate','text',{required:true,minLength:5,maxLength:20,placeholder:plateExample(form.vehicle_type)})}</Field><div className="form-grid"><Field label="Loại phương tiện"><select value={form.vehicle_type} onChange={e=>change('vehicle_type',e.target.value)}><option value="MOTORBIKE">Xe máy</option><option value="CAR">Ô tô</option></select></Field><Field label="Nguồn năng lượng"><select value={form.energy_type} required onChange={e=>change('energy_type',e.target.value)}><option value="" disabled>Chọn nguồn năng lượng</option><option value="GASOLINE">Xăng</option><option value="ELECTRIC">Điện</option></select></Field><Field label="Hãng xe">{input('brand','text',{maxLength:50})}</Field><Field label="Màu sắc">{input('color','text',{maxLength:50})}</Field></div><p className="info-note">{type==='customerVehicle'?(customerMode==='guest'?'Đăng ký cho khách vãng lai; không gắn xe vào tài khoản nhân viên.':'Đăng ký xe vào tài khoản khách hàng theo email. Khách chưa có tài khoản có thể tự đăng ký ở màn hình đăng nhập.'):'Xe được đăng ký vào tài khoản của bạn.'} Biển số và nhóm xe không đổi được khi đã có lịch sử gửi xe.</p></>}
 {(type==='checkin'||type==='reservation')&&<>
  {reservation&&<p className="info-note">Đặt chỗ #{reservation.id} nhận xe từ {date(reservation.start_time)} đến trước {date(reservation.expiry_time)}.</p>}
  {picker}
  {type==='reservation'&&<>
   <Field label="Cách đặt chỗ"><select value={bookingMode} onChange={e=>{
    const mode=e.target.value;
    setBookingMode(mode);setSlotOptions(null);setError('');
    if(mode==='scheduled')change('end_time',bookingExpiry(form.start_time,60));
    if(mode==='immediate'&&(form.start_time<limits.min||form.start_time>limits.max))change('start_time',localTime(5));
   }}><option value="immediate">Giữ ô ngay</option><option value="scheduled">Đặt theo khung giờ</option></select></Field>
   <Field label="Giờ bắt đầu (Việt Nam)" help={scheduled?'Ô bắt đầu được giữ từ giờ đã chọn.':`Chọn giờ đến trong ${bookingPolicy.max_advance_minutes/60} giờ tới. Ô được giữ ngay khi xác nhận.`}>
    {input('start_time','datetime-local',{required:true,...(scheduled?{min:limits.min}:limits),onChange:e=>{
     const start=e.target.value;
     setForm(f=>({...f,start_time:start,end_time:scheduled&&(!f.end_time||f.end_time<=start)?bookingExpiry(start,60):f.end_time}));
    }})}
   </Field>
   {scheduled&&<Field label="Giờ rời bãi dự kiến (Việt Nam)">{input('end_time','datetime-local',{required:true,min:form.start_time})}</Field>}
   <div className="booking-deadline" role="status">
    <span>Tự hủy nếu chưa nhận xe</span>
    <strong>{expiresAt?date(expiresAt):'Chọn giờ bắt đầu ở trên'}</strong>
    <small>{scheduled?'Hạn nhận xe đến trước giờ rời dự kiến và tối đa '+bookingPolicy.checkin_window_minutes/60+' giờ sau giờ bắt đầu.':'Nhận xe từ giờ bắt đầu. Hạn nhận xe là '+bookingPolicy.checkin_window_minutes/60+' giờ sau giờ bắt đầu.'}</small>
   </div>
   {scheduled&&<>
    {spotPicker}
    <p className="info-note" role="status">{slotResult?.error||(!slotQuery?'Chọn phương tiện và khung giờ để tìm ô.':!slotResult?'Đang tìm ô trong khung giờ…':!spots.length?'Không còn ô phù hợp trong khung giờ.':'Nhân viên kiểm tra lại ô khi nhận xe nếu lượt trước chưa rời.')}</p>
   </>}
  </>}
  {type==='checkin'&&<p className="info-note">Nhóm xe cần có bảng giá hoạt động. Hệ thống kiểm tra lại ô đỗ khi ghi nhận xe vào.</p>}
 </>}
 {type==='checkout'&&<><div className="summary-box"><span>Lượt gửi</span><b>#{item.id}</b><span>Thời gian vào</span><b>{date(item.entry_time)}</b></div><p>Xác nhận xe đã rời bãi. Phí gửi xe được tính theo thời gian ra thực tế và bảng giá của nhóm xe.</p></>}
 {type==='payment'&&<><FeeDetail session={item}/><p>Chỉ xác nhận sau khi đã nhận tiền. Hệ thống chỉ ghi một lần thanh toán thành công cho mỗi lượt gửi.</p></>}
 {type==='cancel'&&<p>Hủy đặt chỗ #{item.id}? Chỗ được giải phóng theo trạng thái cảm biến mới nhất. Không thể hủy khi xe đã check-in.</p>}
 {type==='charging'&&<><p className="info-note">Điểm sạc {item.spot_code} · {item.charger_type==='SOCKET'?'Ổ cắm xe máy điện':'Trạm sạc ô tô điện'}</p><Field label="Trạng thái vận hành"><select value={form.charger_status} onChange={e=>change('charger_status',e.target.value)}><option value="PLANNED">Chưa vận hành</option><option value="READY">Sẵn sàng</option><option value="OFFLINE">Mất kết nối</option><option value="MAINTENANCE">Bảo trì</option></select></Field><p>Dữ liệu IoT vẫn được kiểm tra riêng. Trạng thái sẵn sàng không bỏ qua thiết bị đang báo lỗi hoặc mất kết nối.</p></>}
 {type==='device'&&<p>{item.enabled?'Tắt':'Bật lại'} thiết bị <b>{item.device_code}</b>? Ô đỗ sẽ cần dữ liệu mới từ thiết bị trước khi nhận lượt đặt chỗ tiếp theo.</p>}
 {type==='price'&&<><p className="info-note">{vehicleName(form)} · {ctx.lot?.name}</p><Field label="Giá giờ đầu (đồng)">{input('first_hour_price','number',{required:true,min:0,max:9999999999.99,step:0.01})}</Field><Field label="Giá mỗi giờ tiếp theo (đồng)">{input('additional_hour_price','number',{required:true,min:0,max:9999999999.99,step:0.01})}</Field><p>Không thay đổi được giá khi có xe thuộc nhóm này đang gửi tại bãi.</p></>}
 {type==='user'&&<><p>{item.full_name} · {item.email}</p><Field label="Vai trò"><select value={form.role} onChange={e=>change('role',e.target.value)}>{Object.entries(roleName).map(([key,value])=><option key={key} value={key}>{value}</option>)}</select></Field><label className="checkbox"><input type="checkbox" checked={form.is_active} onChange={e=>change('is_active',e.target.checked)}/>Tài khoản được hoạt động</label></>}
 {type==='lot'&&<><Field label="Tên bãi xe">{input('name','text',{required:true,minLength:2,maxLength:150})}</Field><Field label="Địa chỉ">{input('address','text',{required:true,minLength:2,maxLength:255})}</Field><div className="form-grid"><Field label="Tổng chỗ ô tô (1–50)">{input('car_capacity','number',{required:true,min:1,max:50})}</Field><Field label="Trong đó: ô tô điện">{input('electric_car_capacity','number',{required:true,min:0,max:form.car_capacity})}</Field><Field label="Tổng chỗ xe máy (1–120)">{input('motorbike_capacity','number',{required:true,min:1,max:120})}</Field><Field label="Trong đó: xe máy điện">{input('electric_motorbike_capacity','number',{required:true,min:0,max:form.motorbike_capacity})}</Field></div>{item.id&&<label className="checkbox"><input type="checkbox" checked={form.is_active} onChange={e=>change('is_active',e.target.checked)}/>Bãi đang hoạt động</label>}<p className="info-note">Sau khi lưu, dùng “Tạo / bổ sung sơ đồ” để thêm các ô còn thiếu theo sức chứa.</p></>}
 {type==='layout'&&<p>Tạo các ô còn thiếu cho bãi <b>{ctx.lot?.name}</b> theo cấu hình hiện tại: {ctx.lot?.car_capacity} ô tô và {ctx.lot?.motorbike_capacity} xe máy. Các điểm sạc mới ở trạng thái chưa vận hành.</p>}
 {type==='spot'&&<><div className="spot-detail"><span className="vehicle-icon"><Car size={30}/></span><div><h3>{item.spot_code}</h3><p>{vehicleName(item)}</p></div><Badge status={item.status}/></div><div className="summary-box"><span>Nhận đặt chỗ</span><b>{item.available_for_booking?'Có thể đặt':'Chưa sẵn sàng'}</b><span>Khu vực</span><b>{ctx.data.areas.find(a=>a.id===item.parking_area_id)?.name||'—'}</b>{item.energy_type==='ELECTRIC'&&<><span>Điểm sạc</span><Badge status={item.charger_status}/><span>Mã trạm / cổng</span><b>{item.charging_station_code} / {item.charging_port_code}</b></>}</div><div className="row-actions">{item.available_for_booking&&<><Button type="button" onClick={()=>ctx.open('reservation',{spot:item})}>Đặt chỗ này</Button>{ctx.staff&&<Button type="button" kind="secondary" onClick={()=>ctx.open('checkin',{spot:item})}>Ghi nhận xe vào</Button>}</>}</div>{ctx.admin&&['AVAILABLE','MAINTENANCE'].includes(item.status)&&<p className="info-note">Bạn có thể {item.status==='MAINTENANCE'?'mở lại ô đỗ':'đưa ô đỗ vào bảo trì'} bằng nút bên dưới.</p>}</>}
 {(type==='ai'||type==='aiout')&&<>
 {ctx.manager&&<Button type="button" kind="secondary wide" onClick={async()=>{setBusy(true);setError('');try{const r=await api('/internal-simulation/prepare',{method:'POST'});ctx.notify(r.notice);}catch(e){setError(e.message);}finally{setBusy(false);}}}>Chuẩn bị xe mẫu nếu chưa đăng ký</Button>}
 <SamplePicker busy={busy} onCapture={async file=>{setImage(file);setResult(null);await recognize(file);}}/>
 <details className="camera-options"><summary>Hoặc tải ảnh xe riêng</summary><label className="upload"><Upload size={26}/><b>Chọn ảnh thấy rõ xe và biển số</b><span>JPEG, PNG, WebP · tối đa 8 MB</span><input aria-label="Ảnh biển số" type="file" accept="image/jpeg,image/png,image/webp" onChange={fileSelected}/></label></details>
 {preview&&<img className="plate-preview" src={result?.annotated_image||preview} alt={result?.annotated_image?'Khung nhận diện biển số do AI tính':'Ảnh biển số đã chọn'}/>}
 {result&&<><Field label="Biển số nhận diện"><input value={result.plate||''} readOnly placeholder="AI chưa đọc được biển số"/></Field>{result.cropped_image&&<img className="plate-crop" src={result.cropped_image} alt="Ảnh crop biển số từ mô hình AI"/>}<div className={result.needs_review?'error-box':'recognition-result'}><b>{result.plate||'Cần kiểm tra ảnh'}</b><span>{Math.round(result.confidence*100)}% độ tin cậy</span>{result.needs_review&&<small>Không tự ghi nhận xe. Chọn ảnh rõ hơn, cắt vùng biển số hoặc dùng thao tác thủ công.</small>}</div></>}
 {imageVehicle&&<div className="info-note">
  <b>Loại xe từ ảnh </b>
  {imageVehicleLabel? <>{imageVehicleLabel} · {Math.round(imageVehicle.confidence*100)}% độ tin cậy</> :
   imageVehicle.reason==='ambiguous'?'Ảnh có nhiều xe hoặc biển số. Hãy chụp riêng xe cần xử lý.' :
   imageVehicle.reason==='inconsistent_vehicle_type'?'Hai mô hình cho kết quả khác nhau. Hãy kiểm tra loại xe.' :
   imageVehicle.reason==='unavailable'?'Mô hình loại xe đang không sẵn sàng.' :
   'Chưa xác định được loại xe. Cần thấy thân xe trong ảnh.'}
  {imageVehicleLabel&&recognizedVehicle&&imageVehicle.type!==recognizedVehicle.vehicle_type&&
   <p>Loại xe trong ảnh khác hồ sơ. Hãy đối chiếu xe và biển số trước khi xác nhận.</p>}
 </div>}
 {type==='ai'&&result?.plate&&!result.needs_review&&!recognizedVehicle&&imageVehicleLabel&&
  <Button type="button" kind="secondary" onClick={()=>ctx.open('customerVehicle',{license_plate:result.plate,vehicle_type:imageVehicle.type,energy_type:''})}>
   Đăng ký xe vừa nhận diện
  </Button>}
 <details className="camera-options"><summary>Chọn vùng ảnh cần đọc (tùy chọn)</summary><Field label="Vùng ảnh cần đọc (tùy chọn)" help="Để trống để AI tìm biển số. Khi cần, nhập x,y,rộng,cao theo pixel.">{input('roi','text',{placeholder:'100,100,400,160',onChange:e=>{change('roi',e.target.value);setResult(null);}})}</Field></details>
 <Button type="button" kind="secondary wide" disabled={!image} onClick={recognize}><ScanLine size={17}/>Nhận diện ảnh</Button>
 {type==='ai'&&<><Field label="Ô đỗ cho xe vào"><select value={form.parking_spot_id} required onChange={e=>change('parking_spot_id',e.target.value)}><option value="">Chọn ô phù hợp loại xe đã đăng ký</option>{ctx.data.spots.filter(s=>(s.available_for_booking||s.status==='RESERVED')&&(!selectedVehicle||(s.spot_type==='DISABLED'?'CAR':s.spot_type)===selectedVehicle.vehicle_type&&s.energy_type===selectedVehicle.energy_type)).map(s=><option key={s.id} value={s.id}>{s.spot_code} · {vehicleName(s)}</option>)}</select></Field><Field label="Mã đặt chỗ (nếu có)">{input('reservation_id','number',{min:1})}</Field></>}
 <p className="info-note">{type==='aiout'?`Đối chiếu biển số với lượt gửi #${item.id}.`:'Biển số phải thuộc phương tiện đã đăng ký. Backend kiểm tra nhóm xe và chỗ đỗ.'} Nhận diện ảnh chưa tạo lượt gửi; bấm xác nhận bên dưới để ghi nhận.</p></>}
 {type==='events'&&<>{events?<><Table headers={['Sequence','Thời gian','Dữ liệu']} empty={!events.length}>{events.map(e=><tr key={e.id}><td>{e.sequence}</td><td>{date(e.received_at)}</td><td><Badge status={e.payload.sensor_status||e.payload.charger_status}/>{e.payload.energy_kwh!=null&&<small>{e.payload.power_kw??0} kW · {e.payload.energy_kwh} kWh</small>}</td></tr>)}</Table><p className="info-note">100 sự kiện mới nhất của thiết bị này.</p></>:<p>Đang tải lịch sử…</p>}</>}
 </fieldset>{error&&<div className="error-box" role="alert">{error}</div>}<div className="modal-actions"><Button type="button" kind="secondary" disabled={busy} onClick={onClose}>Đóng</Button>{type!=='events'&&(type!=='spot'||ctx.admin&&['AVAILABLE','MAINTENANCE'].includes(item.status))&&<Button type="submit" busy={busy} disabled={((type==='reservation'||type==='checkin')&&addingVehicle)||((type==='ai'||type==='aiout')&&(!result||result.needs_review))}>{type==='payment'?'Đã nhận tiền':type==='checkout'?'Xác nhận xe ra':type==='checkin'?'Ghi nhận xe vào':type==='reservation'?'Xác nhận đặt chỗ':type==='spot'?(item.status==='MAINTENANCE'?'Mở lại ô đỗ':'Đưa vào bảo trì'):type==='ai'?'Xác nhận xe vào':type==='aiout'?'Xác nhận xe ra':'Lưu / xác nhận'}</Button>}</div></form></Modal>;
}
