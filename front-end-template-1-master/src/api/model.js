import http from "@/api/axios";

// 任务(3)：模型评估与版本中心
// 后端为根路径 /models/*，经 /api rewrite 代理到 5000。

export function fetchModelOverview() {
  return http.get("/models/overview");
}

export function evaluateModel(payload = {}) {
  return http.post("/models/evaluate", payload);
}

export function fetchModelVersion(versionId) {
  return http.get(`/models/versions/${versionId}`);
}

export function setOnlineModel(versionId) {
  return http.post(`/models/versions/${versionId}/online`, {});
}
