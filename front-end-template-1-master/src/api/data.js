import http from "@/api/axios";

// 任务(2)：数据实时同步接口
// axios baseURL 为 http://localhost:8080/api，因此这里用 /v1/... 最终请求 /api/v1/...
const BASE = "/v1/data";

export function fetchSyncBatches(limit = 20) {
  return http.get(`${BASE}/batches`, { params: { limit } });
}

export function fetchSyncLogs(batchId, limit = 200) {
  return http.get(`${BASE}/logs`, {
    params: batchId ? { batch_id: batchId, limit } : { limit },
  });
}

export function triggerSync(payload = {}) {
  return http.post(`${BASE}/sync`, payload);
}

export function triggerReconcile() {
  return http.post(`${BASE}/reconcile`, {});
}

export function fetchDataHealth() {
  return http.get(`${BASE}/health`);
}
