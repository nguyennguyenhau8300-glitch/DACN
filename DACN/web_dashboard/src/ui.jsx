import { useEffect, useRef, useId, cloneElement } from 'react';
import { X, Search, Inbox, ArrowLeft, ArrowRight, LoaderCircle } from 'lucide-react';
import {statusName} from './api';
export function Badge({status,children}) { return <span className={'badge '+String(status).toLowerCase()}><i/>{children||statusName[status]||status}</span>; }
export function Button({children,kind='',busy=false,...props}) {return <button className={'button '+kind} {...props} disabled={props.disabled||busy}>{busy&&<LoaderCircle size={16} className="spin"/>}{children}</button>;}
export function Empty({title='Chưa có dữ liệu',children}) {return <div className="empty"><Inbox size={32}/><h3>{title}</h3>{children&&<p>{children}</p>}</div>;}
export function Field({label,children,help}) {const id=useId();return <div className="field"><label htmlFor={id}>{label}</label>{cloneElement(children,{id,"aria-describedby":help?id+"-help":undefined})}{help&&<small id={id+"-help"}>{help}</small>}</div>;}
export function SearchBox({value,onChange,placeholder='Tìm kiếm…'}) {return <div className="search"><Search size={17}/><input aria-label={placeholder} placeholder={placeholder} value={value} onChange={e=>onChange(e.target.value)}/></div>;}
export function Table({headers,children,empty=false}) {return empty?<Empty/>:<div className="table-scroll"><table><thead><tr>{headers.map(h=><th key={h}>{h}</th>)}</tr></thead><tbody>{children}</tbody></table></div>;}
export function Pagination({page,setPage,count,limit=25,hasMore=count>=limit}) {return <div className="pagination"><span>Trang {page+1} · {count} kết quả</span><Button kind="ghost" disabled={!page} onClick={()=>setPage(page-1)}><ArrowLeft size={15}/>Trước</Button><Button kind="ghost" disabled={!hasMore} onClick={()=>setPage(page+1)}>Sau<ArrowRight size={15}/></Button></div>;}
export function Modal({title,children,onClose,busy}) {
 const ref=useRef(); const previous=useRef(document.activeElement);
 useEffect(()=>{const d=ref.current;d.showModal();const before=previous.current;return()=>{d.close();before?.focus();};},[]);
 return <dialog ref={ref} onCancel={e=>{e.preventDefault();if(!busy)onClose();}} className="modal"><div className="modal-head"><h2>{title}</h2><button className="icon-button" aria-label="Đóng" disabled={busy} onClick={onClose}><X size={20}/></button></div>{children}</dialog>;
}
