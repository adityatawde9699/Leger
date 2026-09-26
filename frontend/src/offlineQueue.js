// Explicit, per-profile IndexedDB queue for quick capture. No tokens are stored.
const DATABASE = "ledger-quick-capture-v1";
const STORE = "drafts";

function requestResult(request) {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error || new Error("Offline storage failed"));
  });
}

function openQueue() {
  return new Promise((resolve, reject) => {
    if (!window.indexedDB) return reject(new Error("Offline storage is unavailable in this browser"));
    const request = window.indexedDB.open(DATABASE, 1);
    request.onupgradeneeded = () => {
      const store = request.result.createObjectStore(STORE, { keyPath: "id" });
      store.createIndex("ownerId", "ownerId");
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error || new Error("Could not open offline storage"));
  });
}

async function withStore(mode, operation) {
  const database = await openQueue();
  try {
    return await new Promise((resolve, reject) => {
      const transaction = database.transaction(STORE, mode);
      const store = transaction.objectStore(STORE);
      let result;
      transaction.oncomplete = () => resolve(result);
      transaction.onerror = () => reject(transaction.error || new Error("Offline storage failed"));
      transaction.onabort = () => reject(transaction.error || new Error("Offline storage was interrupted"));
      Promise.resolve(operation(store)).then((value) => { result = value; }).catch(reject);
    });
  } finally {
    database.close();
  }
}

export async function listQueued(ownerId) {
  if (!ownerId) return [];
  const drafts = await withStore("readonly", (store) => requestResult(store.index("ownerId").getAll(ownerId)));
  return drafts.sort((a, b) => a.createdAt.localeCompare(b.createdAt));
}

export async function queueCapture(ownerId, submission) {
  if (!ownerId) throw new Error("Open your profile online once before capturing offline");
  const draft = { ...submission, id: crypto.randomUUID(), ownerId, createdAt: new Date().toISOString(), status: "queued" };
  await withStore("readwrite", (store) => requestResult(store.put(draft)));
  return draft;
}

export async function updateQueued(draft) {
  await withStore("readwrite", (store) => requestResult(store.put(draft)));
}

export async function removeQueued(id) {
  await withStore("readwrite", (store) => requestResult(store.delete(id)));
}
