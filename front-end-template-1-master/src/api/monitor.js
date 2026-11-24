import http from "@/api/axios";

// 任务(3)：数据监控中心
// axios baseURL 为 http://localhost:8080/api，因此这里用根路径，
// 经 vue devServer 的 /api rewrite 后命中后端 /data/monitor。

export function fetchMonitorOverview(params = {}) {
  return http.get("/data/monitor", { params });
}

export function toggleDataSource(code, enabled) {
  return http.post(
    `/data/sources/${encodeURIComponent(code)}/toggle`,
    { enabled }
  );
}

export function runDataSource(code, pages = 3) {
  return http.post(`/data/sources/${encodeURIComponent(code)}/run`, { pages });
}
