"""数据监控中心业务编排层。

职责：
- 调用 ``MonitorRepository`` 获取原始数据；
- 计算数据新鲜度、成功率、批次耗时等派生指标；
- 输出前端可直接渲染的 DTO（统一 camelCase 字段）。

本模块不依赖 Flask 上下文，可被 API、定时任务或测试脚本复用。
"""

import logging
from datetime import datetime

from backend.repositories.monitor_repository import monitor_repository

logger = logging.getLogger("monitor_service")

SOURCE_STATUS_LABELS = {
    "success": "运行中",
    "running": "采集中",
    "error": "异常",
    "idle": "空闲",
}

BATCH_STATUS_LABELS = {
    "running": "同步中",
    "success": "成功",
    "failed": "失败",
}


def _fmt(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    return str(value)


def _humanize_seconds(seconds):
    if seconds is None:
        return "未知"
    seconds = max(0, int(seconds))
    if seconds < 60:
        return "刚刚"
    if seconds < 3600:
        return "{n} 分钟前".format(n=seconds // 60)
    if seconds < 86400:
        return "{n} 小时前".format(n=seconds // 3600)
    return "{n} 天前".format(n=seconds // 86400)


class MonitorService:
    def __init__(self, repository=None):
        self.repository = repository or monitor_repository

    # ------------------------------------------------------------------ #
    # 对外主入口
    # ------------------------------------------------------------------ #
    def overview(self, batch_limit=20, log_limit=50, version_limit=20):
        now = datetime.now()
        payload = {
            "generatedAt": _fmt(now),
            "freshness": {},
            "summary": {},
            "health": {},
            "sources": [],
            "fields": [],
            "distributions": {
                "disease": [],
                "gender": [],
                "age": [],
                "month": [],
                "hospital": [],
            },
            "batches": [],
            "logs": [],
            "versions": [],
        }

        conn = self.repository.open()
        try:
            cur = conn.cursor()

            summary = self.repository.case_summary(cur)
            batches = self.repository.list_batches(cur, limit=batch_limit)
            stats = self.repository.batch_stats(cur)

            payload["summary"] = {
                "totalCases": int(summary.get("total") or 0),
                "todayNew": int(summary.get("today_new") or 0),
                "diseaseKinds": int(summary.get("disease_kinds") or 0),
                "hospitalKinds": int(summary.get("hospital_kinds") or 0),
                "lastUpdated": _fmt(summary.get("last_updated")),
            }

            payload["freshness"] = self._build_freshness(batches, summary, now)
            payload["health"] = self._build_health(stats)
            payload["sources"] = self._build_sources(
                self.repository.list_sources(cur), now
            )

            payload["fields"] = self.repository.field_completeness(cur)
            payload["distributions"]["disease"] = [
                {"name": r["name"], "value": int(r["value"])}
                for r in self.repository.disease_top(cur)
            ]
            payload["distributions"]["gender"] = [
                {"name": r["name"], "value": int(r["value"])}
                for r in self.repository.gender_distribution(cur)
            ]
            payload["distributions"]["age"] = [
                {"name": r["name"], "value": int(r["value"])}
                for r in self.repository.age_distribution(cur)
            ]
            payload["distributions"]["month"] = [
                {"name": "{m}月".format(m=int(r["name"])), "value": int(r["value"])}
                for r in self.repository.month_distribution(cur)
            ]
            payload["distributions"]["hospital"] = [
                {"name": r["name"], "value": int(r["value"])}
                for r in self.repository.hospital_top(cur)
            ]

            payload["batches"] = [self._batch_dto(r) for r in batches]
            payload["logs"] = [self._log_dto(r) for r in self.repository.list_logs(cur, limit=log_limit)]
            payload["versions"] = [
                self._version_dto(r) for r in self.repository.list_versions(cur, limit=version_limit)
            ]
        finally:
            try:
                conn.close()
            except Exception:
                pass

        payload["summary"]["activeSources"] = sum(
            1 for s in payload["sources"] if s["enabled"] and s["freshnessSeconds"] is not None
            and s["freshnessSeconds"] <= 86400
        )
        payload["summary"]["sourceCount"] = len(payload["sources"])
        return payload

    # ------------------------------------------------------------------ #
    # 派生指标
    # ------------------------------------------------------------------ #
    def _build_freshness(self, batches, summary, now):
        latest = batches[0] if batches else None
        last_sync = latest.get("finished_at") or latest.get("started_at") if latest else None
        last_updated = summary.get("last_updated")
        reference = last_sync or last_updated

        if isinstance(reference, datetime):
            seconds = int((now - reference).total_seconds())
        elif isinstance(last_updated, datetime):
            seconds = int((now - last_updated).total_seconds())
        else:
            seconds = None

        return {
            "lastSyncAt": _fmt(last_sync),
            "lastUpdatedAt": _fmt(last_updated),
            "freshnessSeconds": seconds,
            "human": _humanize_seconds(seconds),
            "status": (latest or {}).get("status"),
            "statusLabel": BATCH_STATUS_LABELS.get((latest or {}).get("status"), "未知"),
            "batchId": (latest or {}).get("id"),
            "inserted": int((latest or {}).get("inserted") or 0),
            "updated": int((latest or {}).get("updated") or 0),
            "skipped": int((latest or {}).get("skipped") or 0),
        }

    def _build_health(self, stats):
        total = int(stats.get("total") or 0)
        success = int(stats.get("success_cnt") or 0)
        failed = int(stats.get("failed_cnt") or 0)
        return {
            "batches": total,
            "successBatches": success,
            "failedBatches": failed,
            "successRate": round(success / total * 100, 2) if total else 0.0,
        }

    def _build_sources(self, rows, now):
        sources = []
        for r in rows:
            last_success = r.get("last_success_at")
            freshness = (
                int((now - last_success).total_seconds())
                if isinstance(last_success, datetime)
                else None
            )
            sources.append(
                {
                    "id": r.get("id"),
                    "code": r.get("code"),
                    "name": r.get("name"),
                    "disease": r.get("disease"),
                    "type": r.get("type"),
                    "enabled": bool(r.get("enabled")),
                    "status": r.get("status") or "idle",
                    "statusLabel": SOURCE_STATUS_LABELS.get(
                        r.get("status") or "idle", "未知"
                    ),
                    "lastRunAt": _fmt(r.get("last_run_at")),
                    "lastSuccessAt": _fmt(last_success),
                    "freshnessSeconds": freshness,
                    "freshnessHuman": _humanize_seconds(freshness),
                    "lastDelta": int(r.get("last_delta") or 0),
                    "totalRecords": int(r.get("total_records") or 0),
                    "lastMessage": r.get("last_message"),
                }
            )
        return sources

    # ------------------------------------------------------------------ #
    # DTO
    # ------------------------------------------------------------------ #
    def _batch_dto(self, r):
        started = r.get("started_at")
        finished = r.get("finished_at")
        duration = None
        if isinstance(started, datetime) and isinstance(finished, datetime):
            duration = int((finished - started).total_seconds())
        elif isinstance(started, datetime) and r.get("status") == "running":
            duration = int((datetime.now() - started).total_seconds())

        return {
            "id": r.get("id"),
            "sourceCode": r.get("source_code"),
            "status": r.get("status"),
            "statusLabel": BATCH_STATUS_LABELS.get(r.get("status"), r.get("status")),
            "inserted": int(r.get("inserted") or 0),
            "updated": int(r.get("updated") or 0),
            "skipped": int(r.get("skipped") or 0),
            "total": int(r.get("inserted") or 0) + int(r.get("updated") or 0) + int(r.get("skipped") or 0),
            "errorMessage": r.get("error_message"),
            "startedAt": _fmt(started),
            "finishedAt": _fmt(finished),
            "durationSeconds": duration,
        }

    def _log_dto(self, r):
        return {
            "id": r.get("id"),
            "batchId": r.get("batch_id"),
            "level": (r.get("level") or "INFO").upper(),
            "message": r.get("message"),
            "createdAt": _fmt(r.get("created_at")),
        }

    def _version_dto(self, r):
        return {
            "id": r.get("id"),
            "name": r.get("name"),
            "version": r.get("version_code"),
            "operator": r.get("operator"),
            "action": r.get("action"),
            "description": r.get("description") or "",
            "createdAt": _fmt(r.get("created_at")),
            "totalRecords": int(r.get("total_records") or 0),
            "deltaRecords": int(r.get("delta_records") or 0),
        }


monitor_service = MonitorService()
