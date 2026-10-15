import {useEffect,useState} from 'react';
import {api,localTime,plateExample,vehicleName} from './api';
import {Button,Field,Table} from './ui';

export function PersonalFields({values={},disabled=false}) {
 return <fieldset disabled={disabled} className="personal-fields">
  <Field label="Họ và tên"><input name="full_name" defaultValue={values.full_name||''} required minLength={2} maxLength={100} autoComplete="name"/></Field>
  <div className="form-grid"><Field label="Ngày tháng năm sinh"><input name="date_of_birth" type="date" defaultValue={values.date_of_birth||''} required max={localTime().slice(0,10)} autoComplete="bday"/></Field>
  <Field label="Quê quán"><input name="hometown" defaultValue={values.hometown||''} required maxLength={200} placeholder="Xã/phường, tỉnh/thành phố"/></Field></div>
 </fieldset>;
}

export function RegistrationVehicleFields() {
 const [type,setType]=useState('MOTORBIKE');
 return <section className="registration-vehicle"><h3>Xe đăng ký</h3>
  <div className="form-grid"><Field label="Biển số xe"><input name="license_plate" required minLength={5} maxLength={20} placeholder={plateExample(type)} autoComplete="off"/></Field>
  <Field label="Loại xe"><select name="vehicle_type" value={type} onChange={e=>setType(e.target.value)}><option value="MOTORBIKE">Xe máy</option><option value="CAR">Ô tô</option></select></Field></div>
  <Field label="Nguồn năng lượng"><select name="energy_type" defaultValue="GASOLINE"><option value="GASOLINE">Xăng</option><option value="ELECTRIC">Điện</option></select></Field>
  <p className="vehicle-picker-help">Xe được lưu vào tài khoản của bạn để đặt chỗ. Bạn có thể thêm xe khác sau khi đăng ký.</p>
 </section>;
}

export function CustomerProfile({ctx}) {
 const [busy,setBusy]=useState(false),[error,setError]=useState(''),[vehicles,setVehicles]=useState([]),[vehicleError,setVehicleError]=useState('');
 useEffect(()=>{const controller=new AbortController();api('/vehicles',{signal:controller.signal}).then(rows=>{setVehicles(rows);setVehicleError('');}).catch(e=>{if(e.name!=='AbortError')setVehicleError(e.message);});return()=>controller.abort();},[ctx.revision]);
 async function save(e){e.preventDefault();setBusy(true);setError('');const form=Object.fromEntries(new FormData(e.currentTarget));try{const user=await api('/auth/me',{method:'PATCH',body:form});ctx.setUser(user);ctx.notify('Đã lưu thông tin cá nhân.');}catch(e){setError(e.message);}finally{setBusy(false);}}
 return <div className="customer-profile">
  <section className="panel"><div className="panel-head"><div><h2>Thông tin cá nhân</h2><p>Tài khoản: {ctx.user.email}</p></div></div>
   <form onSubmit={save} className="profile-form"><PersonalFields values={ctx.user} disabled={busy}/>{error&&<div role="alert" className="error-box">{error}</div>}<Button type="submit" busy={busy}>Lưu thông tin</Button></form>
  </section>
  <section className="panel"><div className="panel-head"><div><h2>Xe đã đăng ký</h2><p>Biển số và loại xe thuộc tài khoản của bạn.</p></div><Button onClick={()=>ctx.open('vehicle')}>Thêm xe của tôi</Button></div>
   {vehicleError&&<p role="alert" className="error-box">{vehicleError}</p>}
   <Table headers={['Biển số xe','Loại xe','Thao tác']} empty={!vehicles.length}>{vehicles.map(v=><tr key={v.id}><td><b>{v.license_plate}</b></td><td>{vehicleName(v)}</td><td><Button kind="small secondary" onClick={()=>ctx.open('vehicle',v)}>Chỉnh sửa xe</Button></td></tr>)}</Table>
  </section>
 </div>;
}
