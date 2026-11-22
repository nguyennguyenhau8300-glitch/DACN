import {date, money, vehicleName} from './api';
import {Table} from './ui';

function clock(minute) {
 return [Math.floor(minute/60),minute%60].map(value=>String(value).padStart(2,'0')).join(':');
}

function duration(seconds) {
 const n = Math.ceil(Number(seconds));
 return `${Math.floor(n/3600)} giờ ${Math.floor(n/60)%60} phút ${n%60} giây`;
}

export function FeeDetail({session}) {
 const fee = session.fee_breakdown;
 return <div className="fee-detail">
  <div className="summary-box">
   <span>Lượt gửi</span><b>#{session.id}</b>
   <span>Giờ vào</span><b>{date(session.entry_time,true)}</b>
   <span>Giờ ra</span><b>{date(session.exit_time,true)}</b>
   {fee&&<>
    <span>Bảng giá đã áp dụng</span><b>{vehicleName(fee)} · #{fee.pricing_rule_id}</b>
    <span>Thời lượng (làm tròn lên theo giây)</span><b>{duration(fee.elapsed_seconds)}</b>
    <span>Số giờ tính phí</span><b>{fee.billed_hours} giờ</b>
   </>}
  </div>
  {fee?<Table headers={['Mức giá','Số giờ','Đơn giá','Thành tiền']}>
   {fee.lines.map(line=><tr key={line.start_minute??line.kind}>
    <td>{line.kind==='TIME_BAND'?clock(line.start_minute)+'–'+clock(line.end_minute):line.kind==='FIRST_HOUR'?'Giờ đầu':'Giờ tiếp theo'}</td>
    <td>{line.hours}</td><td>{money(line.unit_price)}</td><td>{money(line.amount)}</td>
   </tr>)}
  </Table>:<p className="info-note">Lượt gửi cũ chỉ lưu tổng phí. Đối soát theo số tiền đã lưu.</p>}
  <div className="summary-box">
   {fee&&<>
    <span>Phí gửi xe</span><b>{money(fee.parking_fee)}</b>
    {fee.energy_type==='ELECTRIC'&&<><span>Phụ phí sạc điện</span><b>{money(fee.charging_fee)}</b></>}
   </>}
   <span>Tổng phải trả</span><b data-testid="fee-total">{money(session.total_amount)}</b>
  </div>
  {fee?.energy_type==='ELECTRIC'&&<p className="info-note">Dữ liệu IoT dùng để theo dõi vận hành điểm sạc. Phiên bản hiện tại áp dụng bảng giá gửi xe điện theo giờ.</p>}
 </div>;
}
