"use strict";
self.saveStore = {
  async open() {
    return new Promise((resolve,reject) => {
      const request = indexedDB.open('silvermachine-web-v1',1);
      request.onupgradeneeded = () => request.result.createObjectStore('state');
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
  },
  async read(key) {
    const db = await this.open();
    try { return await new Promise((resolve,reject) => {
      const request = db.transaction('state').objectStore('state').get(key);
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    }); } finally { db.close(); }
  },
  async write(key,value) {
    const db = await this.open();
    try { await new Promise((resolve,reject) => {
      const transaction = db.transaction('state','readwrite',{durability:'strict'});
      transaction.objectStore('state').put(value,key);
      transaction.oncomplete = resolve;
      transaction.onerror = transaction.onabort = () => reject(transaction.error || Error('Save commit aborted'));
    }); } finally { db.close(); }
  },
  get() { return this.read('save'); },
  put(bytes) { return this.write('save',{format:1,updated:Date.now(),archive:bytes}); }
};
