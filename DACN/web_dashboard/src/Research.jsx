import {useEffect,useMemo,useState,useRef} from 'react';
import {api,money,date,vehicleName,BASE} from './api';
import {Button,Field,Empty,Table,Pagination} from './ui';

export function Routing({ctx}){
 const [map,setMap]=useState(null),[vehicle,setVehicle]=useState(String(ctx.data.vehicles[0]?.id||'')),[result,setResult]=useState(null);
 const [error,setError]=useState(''),[busy,setBusy]=useState(false),[editing,setEditing]=useState(false),[source,setSource]=useState(''),[entrance,setEntrance]=useState(''),[destination,setDestination]=useState(''),[weight,setWeight]=useState('1');
 const [point,setPoint]=useState('gate'),[edgeIndex,setEdgeIndex]=useState(0);
 const draft=editing&&source?JSON.parse(source):map;
 const selected=draft?.nodes.find(n=>n.id===point);
 const selectedEdge=draft?.edges[edgeIndex];
 function updatePoint(field,value){const next=JSON.parse(source);next.nodes=next.nodes.map(n=>n.id===point?{...n,[field]:value}:n);setSource(JSON.stringify(next));}
 function updateEdge(field,value){const next=JSON.parse(source);next.edges[edgeIndex]={...next.edges[edgeIndex],[field]:value};setSource(JSON.stringify(next));}
 function addPoint(kind){const next=JSON.parse(source);const id=kind.toLowerCase()+'-'+Date.now();next.nodes.push({id,kind,label:kind==='ENTRANCE'?'Cổng mới':kind==='DESTINATION'?'Điểm đến mới':'Lối đi mới',x:0,y:0});setPoint(id);setSource(JSON.stringify(next));}
 useEffect(()=>{const abort=new AbortController();api(`/parking-lots/${ctx.lotId}/map`,{signal:abort.signal}).then(setMap).catch(e=>{if(e.name!=='AbortError')setError(e.message);});return()=>abort.abort();},[ctx.lotId]);
 async function suggest(e){e.preventDefault();setBusy(true);setError('');try{setResult(await api(`/parking-lots/${ctx.lotId}/recommendation?`+new URLSearchParams({vehicle_id:vehicle,walk_weight:weight,...(entrance?{entrance}:{}),...(destination?{destination}:{})})));}catch(e){setError(e.message);}finally{setBusy(false);}}
 async function save(){setBusy(true);setError('');try{const value=JSON.parse(source);const payload={name:value.name,units:value.units,nodes:value.nodes,edges:value.edges,revision:map.revision};setMap(await api(`/parking-lots/${ctx.lotId}/map`,{method:'PUT',body:payload}));setResult(null);setEditing(false);ctx.notify('Đã lưu sơ đồ và lối đi.');}catch(e){setError(e.message);}finally{setBusy(false);}}
 return <><section className="panel research-panel"><div className="panel-head"><div><h2>Gợi ý ô đỗ & chỉ đường</h2><p>Tính đường từ cổng vào, kết hợp khoảng cách đi bộ đến điểm đến.</p></div>{ctx.manager&&<Button kind="secondary" disabled={!map} onClick={()=>{setEditing(!editing);setSource(JSON.stringify(map,null,2));}}>Cấu hình mặt bằng</Button>}</div>{error&&<div role="alert" className="error-box">{error}</div>}
 <form onSubmit={suggest} className="research-form"><Field label="Phương tiện"><select value={vehicle} onChange={e=>{setVehicle(e.target.value);setResult(null);}} disabled={busy} required><option value="">Chọn xe</option>{ctx.data.vehicles.map(v=><option key={v.id} value={v.id}>{v.license_plate} · {vehicleName(v)}</option>)}</select></Field><Field label="Cổng vào"><select value={entrance} onChange={e=>{setEntrance(e.target.value);setResult(null);}} disabled={busy}><option value="">Cổng mặc định</option>{map?.nodes.filter(n=>n.kind==='ENTRANCE').map(n=><option key={n.id} value={n.id}>{n.label||n.id}</option>)}</select></Field><Field label="Điểm đến"><select value={destination} onChange={e=>{setDestination(e.target.value);setResult(null);}} disabled={busy}><option value="">Lối đi bộ / thang máy</option>{map?.nodes.filter(n=>n.kind==='DESTINATION').map(n=><option key={n.id} value={n.id}>{n.label||n.id}</option>)}</select></Field><Field label="Ưu tiên gần điểm đến"><select value={weight} onChange={e=>{setWeight(e.target.value);setResult(null);}} disabled={busy}><option value="0">Đường xe ngắn nhất</option><option value="1">Cân bằng</option><option value="3">Ưu tiên đi bộ gần</option></select></Field><Button type="submit" busy={busy} disabled={!vehicle||editing}>Tìm ô phù hợp</Button></form>
 {editing&&draft&&<div><p>Chọn điểm để đổi vị trí hoặc chọn lối đi để điều chỉnh độ dài, đóng/mở lối. Tọa độ bản vẽ và độ dài lối đi được chỉnh riêng.</p><div className="research-form"><Field label="Điểm trên sơ đồ"><select value={point} onChange={e=>setPoint(e.target.value)}>{draft.nodes.map(n=><option key={n.id} value={n.id}>{n.label||n.id} ({n.id})</option>)}</select></Field>{selected&&<><Field label="Tên điểm"><input value={selected.label} onChange={e=>updatePoint('label',e.target.value)}/></Field><Field label="Tọa độ ngang"><input type="number" value={selected.x} onChange={e=>updatePoint('x',Number(e.target.value))}/></Field><Field label="Tọa độ dọc"><input type="number" value={selected.y} onChange={e=>updatePoint('y',Number(e.target.value))}/></Field></>}</div><div className="research-form"><Field label="Lối di chuyển"><select value={edgeIndex} onChange={e=>setEdgeIndex(Number(e.target.value))}>{draft.edges.map((e,i)=><option key={i} value={i}>{e.source} → {e.target}</option>)}</select></Field>{selectedEdge&&<><Field label="Độ dài lối đi"><input type="number" min="0.01" step="0.01" value={selectedEdge.distance} onChange={e=>updateEdge('distance',Number(e.target.value))}/></Field><label><input type="checkbox" checked={selectedEdge.blocked} onChange={e=>updateEdge('blocked',e.target.checked)}/> Tạm đóng lối đi</label></>}</div><div className="research-form"><Button kind="secondary" onClick={()=>addPoint('ENTRANCE')}>Thêm cổng</Button><Button kind="secondary" onClick={()=>addPoint('DESTINATION')}>Thêm điểm đến</Button><Button kind="secondary" onClick={()=>addPoint('LANE')}>Thêm điểm lối đi</Button><Button kind="secondary" onClick={()=>{const next=JSON.parse(source);if(next.nodes.length>1){next.edges.push({source:point,target:next.nodes.find(n=>n.id!==point).id,distance:1,directed:false,blocked:false});setEdgeIndex(next.edges.length-1);setSource(JSON.stringify(next));}}}>Thêm lối nối</Button></div>{selectedEdge&&<div className="research-form"><Field label="Nối từ"><select value={selectedEdge.source} onChange={e=>updateEdge('source',e.target.value)}>{draft.nodes.map(n=><option key={n.id} value={n.id}>{n.label||n.id} ({n.id})</option>)}</select></Field><Field label="Nối đến"><select value={selectedEdge.target} onChange={e=>updateEdge('target',e.target.value)}>{draft.nodes.map(n=><option key={n.id} value={n.id}>{n.label||n.id} ({n.id})</option>)}</select></Field></div>}<Button busy={busy} onClick={save}>Lưu mặt bằng</Button></div>}
 {result&&<><p>{result.notice}</p>{!result.candidates.length?<Empty title="Không có ô phù hợp">Ô có thể đang được giữ, thiết bị chưa sẵn sàng hoặc không có đường đi.</Empty>:<div className="recommendations">{result.candidates.map((r,i)=><article key={r.spot_id}><b>{i===0?'Đề xuất: ':''}{r.spot_code}</b><p>Xe đi {r.driving_distance} · Đi bộ {r.walking_distance} {result.units}</p><Button kind="secondary" onClick={()=>ctx.open('reservation',{vehicle_id:Number(vehicle),spot:ctx.data.spots.find(s=>s.id===r.spot_id)})}>Đặt ô này</Button></article>)}</div>}</>}
 </section>{draft&&<section className="panel research-panel"><h2>{draft.name}</h2><p>{draft.units} · Đường cam: xe di chuyển · Đường xanh nét đứt: đi bộ · Đỏ nét đứt: lối bị chặn</p><RouteCanvas map={draft} route={editing?null:result?.candidates[0]} spots={ctx.data.spots} onPick={editing?setPoint:null}/></section>}</>;
}

function RouteCanvas({map,route,spots,onPick}){
 const container=useRef(null);
 useEffect(()=>{if(route&&container.current){const node=map.nodes.find(n=>n.spot_id===route.spot_id);if(node)container.current.scrollTop=Math.max(0,node.y*10-200);}},[route,map]);
 const nodes=useMemo(()=>Object.fromEntries(map.nodes.map(n=>[n.id,n])),[map]);
 const x=map.nodes.map(n=>n.x),y=map.nodes.map(n=>n.y),left=Math.min(...x)-5,top=Math.min(...y)-5,width=Math.max(...x)-left+6,height=Math.max(...y)-top+6;
 const points=ids=>ids?.map(id=>nodes[id]).filter(Boolean).map(n=>`${n.x},${n.y}`).join(' ');
 const fills={AVAILABLE:'#d8edc4',RESERVED:'#f6dc95',OCCUPIED:'#f1b0a0',MAINTENANCE:'#b5bec4'};
 return <div className="route-canvas" ref={container}><svg role="img" aria-label="Sơ đồ đường đi đến ô đỗ" viewBox={`${left} ${top} ${width} ${height}`} style={{width:Math.max(600,width*10),height:Math.max(420,height*10)}}>
 {map.edges.map((e,i)=><line key={i} x1={nodes[e.source]?.x} y1={nodes[e.source]?.y} x2={nodes[e.target]?.x} y2={nodes[e.target]?.y} stroke={e.blocked?'#cf4d39':'#c4cec8'} strokeWidth=".6" strokeDasharray={e.blocked?'1,1':undefined}/>)}
 {route&&<><polyline points={points(route.route)} fill="none" stroke="#d87a27" strokeWidth="1.1"/><polyline points={points(route.walking_route)} fill="none" stroke="#287fa9" strokeWidth=".7" strokeDasharray="1,1"/></>}
 {map.nodes.filter(n=>n.kind!=='LANE'||onPick).map(n=>{const spot=spots.find(s=>s.id===n.spot_id);return <g key={n.id} onClick={()=>onPick?.(n.id)} style={{cursor:onPick?'pointer':'default'}}><title>{n.label}</title><rect x={n.x-2.6} y={n.y-1.6} width="5.2" height="3.2" rx=".5" fill={spot?fills[spot.status]:'#155b49'} stroke={route?.spot_id===n.spot_id?'#d87a27':'#7b9888'} strokeWidth=".2"/><text x={n.x} y={n.y+.4} textAnchor="middle" fill={spot?'#173f32':'white'} fontSize={spot?'1.15':'1.0'}>{n.kind==='ENTRANCE'?'VÀO':n.kind==='DESTINATION'?'ĐÍCH':n.label}</text></g>;})}
 </svg></div>;
}

export function Analytics({ctx}){
 const today=new Date(Date.now()+7*3600000).toISOString().slice(0,10);
 const [start,setStart]=useState(today.slice(0,8)+'01'),[end,setEnd]=useState(today),[report,setReport]=useState(null),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 const [selectedDay,setSelectedDay]=useState(null);
 const query=(from,to)=>new URLSearchParams({parking_lot_id:ctx.lotId,from_date:from,to_date:to});
 async function load(e){
  e?.preventDefault();
  setBusy(true);setError('');setSelectedDay(null);
  try{setReport(await api('/reports/daily?'+query(start,end)));}
  catch(e){setError(e.message);}
  finally{setBusy(false);}
 }
 useEffect(()=>{load();},[ctx.lotId]);
 async function download(){
  setError('');
  try{
   const {from_date,to_date}=report;
   const response=await fetch(BASE+'/reports/daily?'+query(from_date,to_date)+'&format=csv',{headers:{Authorization:`Bearer ${sessionStorage.getItem('parking-token')}`}});
   if(!response.ok)throw new Error('Không xuất được báo cáo');
   const url=URL.createObjectURL(await response.blob()),a=document.createElement('a');
   a.href=url;a.download=`parkly-${from_date}-${to_date}.csv`;a.click();
   setTimeout(()=>URL.revokeObjectURL(url),1000);
  }catch(e){setError(e.message);}
 }
 const max=Math.max(1,...(report?.items||[]).map(r=>Number(r.revenue)));
 return <section className="panel research-panel">
  <h2>Doanh thu & lưu lượng theo ngày</h2>
  <form className="research-form" onSubmit={load}>
   <Field label="Từ ngày"><input type="date" value={start} onChange={e=>setStart(e.target.value)} required/></Field>
   <Field label="Đến ngày"><input type="date" value={end} onChange={e=>setEnd(e.target.value)} required/></Field>
   <Button busy={busy}>Xem báo cáo</Button>
   <Button type="button" kind="secondary" disabled={!report||busy} onClick={download}>Xuất CSV / mở bằng Excel</Button>
  </form>
  {error&&<p role="alert" className="error-box">{error}</p>}
  {report&&<>
   <div className="report-totals"><b>{money(report.totals.revenue)} thực thu</b><span>{report.totals.entries} xe vào · {report.totals.exits} xe ra</span><span>{money(report.totals.sandbox_revenue)} thử nghiệm</span></div>
   <p>Doanh thu tính theo ngày thanh toán thành công (giờ Việt Nam). Khoản mô phỏng nằm ở cột Thử nghiệm.</p>
   <div className="daily-chart" aria-label="Biểu đồ doanh thu ngày">
    {report.items.map(r=><div key={r.date} title={`${r.date}: ${money(r.revenue)}`}><span style={{height:`${Math.max(1,Number(r.revenue)/max*170)}px`}}/><small>{r.date.slice(8)}</small></div>)}
   </div>
   <Table headers={['Ngày','Xe vào','Xe ra','Thực thu','Thử nghiệm','Giao dịch']}>
    {report.items.map(r=><tr key={r.date}>
     <td>{r.date}</td><td>{r.entries}</td><td>{r.exits}</td><td>{money(r.revenue)}</td><td>{money(r.sandbox_revenue)}</td>
     <td><Button kind="small secondary" aria-label={`Đối soát ngày ${r.date}`} aria-pressed={selectedDay===r.date} disabled={busy} onClick={()=>setSelectedDay(r.date)}>Đối soát</Button></td>
    </tr>)}
   </Table>
   {selectedDay&&<DailyReceipts key={selectedDay} ctx={ctx} day={selectedDay}/>}
  </>}
 </section>;
}

const paymentNames={CASH:'Tiền mặt',VIETQR:'VietQR',VNPAY:'VNPAY',MOMO:'MoMo'};
const receiptLimit=25;

function DailyReceipts({ctx,day}){
 const [page,setPage]=useState(0),[receipts,setReceipts]=useState(null),[error,setError]=useState('');
 const heading=useRef(null);
 useEffect(()=>{
  heading.current?.focus();
  const abort=new AbortController();
  const params=new URLSearchParams({parking_lot_id:ctx.lotId,payment_date:day,limit:receiptLimit,offset:page*receiptLimit});
  api('/reports/daily/payments?'+params,{signal:abort.signal})
   .then(value=>{if(!abort.signal.aborted)setReceipts(value);})
   .catch(e=>{if(!abort.signal.aborted)setError(e.message);});
  return ()=>abort.abort();
 },[ctx.lotId,day,page]);
 function changePage(next){
  setReceipts(null);setError('');setPage(next);
 }
 return <section className="revenue-receipts" aria-label={`Đối soát ngày ${day}`}>
  <h3 ref={heading} tabIndex={-1}>Biên nhận ngày {day}</h3>
  {error?<p role="alert" className="error-box">{error}</p>:!receipts?<p role="status">Đang tải biên nhận…</p>:<>
   <Table headers={['Biên nhận / Lượt','Giờ thu','Hình thức','Phí đã chốt','Đã thu','Đối chiếu','Chi tiết']} empty={!receipts.items.length}>
    {receipts.items.map(({payment,session,sandbox})=>{
     const matched=Number(payment.amount)===Number(session.total_amount);
     return <tr key={payment.id}>
      <td><b>Biên nhận #{payment.id}</b><small>Lượt #{session.id}</small>{payment.transaction_code&&<small className="transaction">{payment.transaction_code}</small>}</td>
      <td>{date(payment.paid_at,true)}</td>
      <td>{paymentNames[payment.payment_method]||payment.payment_method}<small>{sandbox?'Thử nghiệm':'Thực thu'}</small></td>
      <td>{money(session.total_amount)}</td><td><b>{money(payment.amount)}</b></td>
      <td>{matched?'Khớp':'Chênh lệch'}</td>
      <td><Button kind="small ghost" aria-label={`Chi tiết phí lượt ${session.id}`} onClick={()=>ctx.open('fee',session)}>Chi tiết phí</Button></td>
     </tr>;
    })}
   </Table>
   {(page>0||receipts.has_more)&&<Pagination page={page} count={receipts.items.length} hasMore={receipts.has_more} setPage={changePage}/>}
  </>}
 </section>;
}

export function SandboxCheckout({ctx}){
 const [session,setSession]=useState(''),[provider,setProvider]=useState('INTERNAL'),[order,setOrder]=useState(null),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 async function create(e){e.preventDefault();setError('');setBusy(true);try{setOrder(await api('/checkout/orders',{method:'POST',body:{parking_session_id:Number(session),provider}}));}catch(e){setError(e.message);}finally{setBusy(false);}}
 async function refresh(){try{setOrder(o=>({...o}));const row=await api('/checkout/orders/'+order.id);setOrder(o=>({...o,...row}));ctx.refresh();}catch(e){setError(e.message);}}
 return <section className="panel research-panel"><h2>Thanh toán thử nghiệm</h2><p>Không chuyển tiền thật. QR nội bộ mở trang mô phỏng, không phải mã chuyển khoản ngân hàng.</p><form className="research-form" onSubmit={create}><Field label="Lượt gửi đã trả xe"><select value={session} onChange={e=>{setSession(e.target.value);setOrder(null);}} disabled={busy} required><option value="">Chọn lượt gửi</option>{ctx.data.sessions.filter(s=>s.status==='COMPLETED').map(s=><option key={s.id} value={s.id}>#{s.id} · {money(s.total_amount)} · {date(s.exit_time)}</option>)}</select></Field><Field label="Cổng thử nghiệm"><select value={provider} onChange={e=>{setProvider(e.target.value);setOrder(null);}} disabled={busy}><option value="INTERNAL">Mô phỏng nội bộ</option><option value="VNPAY">VNPAY sandbox (cần cấu hình)</option></select></Field><Button busy={busy}>Tạo giao dịch thử</Button></form><Pagination page={ctx.sessionPage} setPage={ctx.setSessionPage} count={ctx.data.sessions.length}/>{error&&<p role="alert" className="error-box">{error}</p>}{order&&<article className="checkout-card"><b>{money(order.amount)}</b><p>Lượt gửi #{order.parking_session_id} · Trạng thái: {order.status} · Hết hạn: {date(order.expires_at)}</p>{order.qr_url&&<img width="220" height="220" src={order.qr_url} alt="QR mở trang thanh toán mô phỏng nội bộ"/>}<p><a className="button" href={order.checkout_url} target="_blank" rel="noopener noreferrer">Mở trang thanh toán thử</a></p><Button kind="secondary" onClick={refresh}>Kiểm tra kết quả</Button></article>}</section>;
}

export function TimeBands({ctx}){
 const [rule,setRule]=useState(''),[day,setDay]=useState('10000'),[night,setNight]=useState('15000'),[error,setError]=useState(''),[busy,setBusy]=useState(false),[schedule,setSchedule]=useState(null);
 async function choose(id){setRule(id);setError('');try{setSchedule(id?await api(`/pricing-rules/${id}/schedule`):null);}catch(e){setError(e.message);}}
 async function save(clear=false){setBusy(true);setError('');try{const bands=clear?[]:[{start_minute:0,end_minute:420,hourly_price:night},{start_minute:420,end_minute:1140,hourly_price:day},{start_minute:1140,end_minute:1440,hourly_price:night}];setSchedule(await api(`/pricing-rules/${rule}/schedule`,{method:'PUT',body:{bands}}));ctx.notify('Đã cập nhật khung giờ tính phí.');}catch(e){setError(e.message);}finally{setBusy(false);}}
 return <section className="panel research-panel"><h2>Giá theo khung giờ ngày / đêm</h2><p>Mỗi giờ bắt đầu tính theo giá tại thời điểm bắt đầu giờ đó. Khi bật lịch, lịch thay thế cách tính giờ đầu / giờ tiếp theo. Không đổi được khi còn xe trong nhóm đang gửi.</p><div className="research-form"><Field label="Nhóm xe"><select value={rule} onChange={e=>choose(e.target.value)}><option value="">Chọn bảng giá</option>{ctx.data.prices.filter(p=>p.is_active).map(p=><option key={p.id} value={p.id}>{vehicleName(p)}</option>)}</select></Field><Field label="Ngày 07:00–19:00 (VND/giờ)"><input type="number" min="0" value={day} onChange={e=>setDay(e.target.value)}/></Field><Field label="Đêm 19:00–07:00 (VND/giờ)"><input type="number" min="0" value={night} onChange={e=>setNight(e.target.value)}/></Field><Button busy={busy} disabled={!rule} onClick={()=>save()}>Áp dụng lịch ngày / đêm</Button><Button kind="secondary" disabled={!rule||busy} onClick={()=>save(true)}>Dùng giá giờ đầu / tiếp theo</Button></div>{error&&<p className="error-box" role="alert">{error}</p>}{schedule&&<p>Lịch hiện tại: {schedule.bands.length?schedule.bands.map(b=>`${Math.floor(b.start_minute/60)}h–${b.end_minute/60}h: ${money(b.hourly_price)}`).join(' · '):'Giá giờ đầu / giờ tiếp theo'}</p>}</section>;
}

