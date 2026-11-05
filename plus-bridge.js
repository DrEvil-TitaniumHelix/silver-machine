"use strict";
if(window.parent!==window&&window.parent.smTransport){
  window.smTransport=window.parent.smTransport;
  document.addEventListener('click',event=>{
    const link=event.target.closest('a');if(!link)return;
    const path=link.getAttribute('href');
    if(path==='/'||path==='/setup'){
      event.preventDefault();
      if(path==='/setup')window.parent.location.reload();
      else window.parent.smDemo.closePlus();
    }
  });
}
