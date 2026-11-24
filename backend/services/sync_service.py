"""数据增量同步服务。

职责：
- 读取爬虫 CSV
- 计算业务字段 SHA-256 去重哈希
- 幂等 upsert 到 cases（依赖 uk_cases_hash 唯一索引）
- 记录 sync_batches / sync_logs
- 同步成功后向 WebSocket 服务发布 data.updated 事件

说明：本模块不依赖 Flask 上下文，可被 API、定时任务或其他脚本复用。
"""

import csv
import hashlib
import logging
import os
import time
from datetime import datetime

import pymysql
import requests

from utils.db_config import get_db_config

logger = logging.getLogger("sync_service")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_CSV_PATH = os.path.join(BASE_DIR, "spiders", "temp2.csv")

FIELDS = [
    "type",
    "gender",
    "age",
    "time",
    "content",
    "docName",
    "docHospital",
    "department",
    "detailUrl",
    "height",
    "weight",
    "illDuration",
    "allergy",
]

# 与数据库迁移脚本 001_realtime.sql 的字段拼接顺序保持一致
QUOTED_COLUMNS = ",".join("`{}`".format(f) for f in FIELDS)
PLACEHOLDERS = ",".join(["%s"] * len(FIELDS))

WS_PUBLISH_URL = os.getenv("WS_PUBLISH_URL", "http://127.0.0.1:5001/internal/publish")
INTERNAL_TOKEN = os.getenv("INTERNAL_TOKEN", "dev-internal-token")


def compute_content_hash(row):
    """计算病例内容的 SHA-256 哈希，必须与 001_realtime.sql 的回填逻辑一致。"""
    parts = []
    for field in FIELDS:
        value = row.get(field)
        parts.append("" if value is None else str(value))
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


class SyncService:
    def __init__(self, csv_path=None, source_code="crawler", batch_size=200):
        self.csv_path = csv_path or DEFAULT_CSV_PATH
        self.source_code = source_code
        self.batch_size = batch_size

    # ------------------------------------------------------------------ #
    # 连接与基础操作
    # ------------------------------------------------------------------ #
    def _connect(self):
        return pymysql.connect(
            **get_db_config(),
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=False,
        )

    def _create_batch(self, conn):
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO sync_batches (source_code, status, started_at) "
                "VALUES (%s, %s, %s)",
                (self.source_code, "running", datetime.now()),
            )
            batch_id = cursor.lastrowid
        conn.commit()
        return batch_id

    def _finish_batch(
        self, conn, batch_id, status, inserted=0, updated=0, skipped=0, error_message=None
    ):
        with conn.cursor() as cursor:
            cursor.execute(
                "UPDATE sync_batches SET status=%s, inserted=%s, updated=%s, "
                "skipped=%s, error_message=%s, finished_at=%s WHERE id=%s",
                (
                    status,
                    inserted,
                    updated,
                    skipped,
                    error_message,
                    datetime.now(),
                    batch_id,
                ),
            )
        conn.commit()

    def _write_log(self, conn, batch_id, level, message):
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO sync_logs (batch_id, level, message) VALUES (%s, %s, %s)",
                    (batch_id, level, message),
                )
            conn.commit()
        except Exception as exc:  # 日志失败不应影响主流程
            logger.warning("写入同步日志失败: %s", exc)

    # ------------------------------------------------------------------ #
    # CSV 读取
    # ------------------------------------------------------------------ #
    def _read_csv(self):
        if not os.path.exists(self.csv_path):
            raise FileNotFoundError("CSV 文件不存在: {}".format(self.csv_path))

        rows = []
        with open(self.csv_path, "r", encoding="utf-8-sig", newline="") as fp:
            reader = csv.DictReader(fp)
            for raw in reader:
                row = {}
                for field in FIELDS:
                    value = raw.get(field, "")
                    row[field] = "" if value is None else str(value)
                rows.append(row)
        return rows

    # ------------------------------------------------------------------ #
    # 增量写入
    # ------------------------------------------------------------------ #
    def _upsert(self, conn, rows, batch_id):
        insert_sql = (
            "INSERT INTO cases ({cols}, content_hash, source_code, batch_id) "
            "VALUES ({ph}, %s, %s, %s) "
            "ON DUPLICATE KEY UPDATE "
            "content=VALUES(content), docName=VALUES(docName), "
            "docHospital=VALUES(docHospital), department=VALUES(department), "
            "height=VALUES(height), weight=VALUES(weight), "
            "illDuration=VALUES(illDuration), allergy=VALUES(allergy)"
        ).format(cols=QUOTED_COLUMNS, ph=PLACEHOLDERS)

        inserted = updated = skipped = 0
        try:
            with conn.cursor() as cursor:
                for row in rows:
                    content_hash = compute_content_hash(row)
                    values = [row.get(field, "") or "" for field in FIELDS]
                    values.extend([content_hash, self.source_code, batch_id])
                    cursor.execute(insert_sql, values)
                    affected = cursor.rowcount
                    if affected == 1:
                        inserted += 1
                    elif affected == 2:
                        updated += 1
                    else:
                        skipped += 1
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        return inserted, updated, skipped

    # ------------------------------------------------------------------ #
    # 事件发布
    # ------------------------------------------------------------------ #
    def _publish(self, payload):
        try:
            requests.post(
                WS_PUBLISH_URL,
                json=payload,
                headers={"X-Internal-Token": INTERNAL_TOKEN},
                timeout=3,
            )
        except Exception as exc:
            # WS 服务未启动不影响同步结果
            logger.warning("发布 data.updated 事件失败（WS 可能未启动）: %s", exc)

    # ------------------------------------------------------------------ #
    # 对外主流程
    # ------------------------------------------------------------------ #
    def run_incremental(self, max_retries=0, retry_delays=(60, 300, 900)):
        """执行一次增量同步。

        返回 dict：
          {success, batchId, inserted, updated, skipped, total, error}
        """
        try:
            rows = self._read_csv()
        except Exception as exc:
            logger.error("读取 CSV 失败: %s", exc)
            return {
                "success": False,
                "batchId": None,
                "inserted": 0,
                "updated": 0,
                "skipped": 0,
                "total": 0,
                "error": str(exc),
            }

        conn = self._connect()
        batch_id = None
        try:
            batch_id = self._create_batch(conn)
            self._write_log(conn, batch_id, "INFO", "开始同步 CSV，共 {} 条".format(len(rows)))

            attempt = 0
            while True:
                try:
                    inserted, updated, skipped = self._upsert(conn, rows, batch_id)
                    break
                except Exception as exc:
                    if attempt >= max_retries:
                        raise
                    delay = retry_delays[min(attempt, len(retry_delays) - 1)]
                    attempt += 1
                    self._write_log(
                        conn,
                        batch_id,
                        "WARN",
                        "同步失败，第 {} 次重试，{} 秒后执行: {}".format(attempt, delay, exc),
                    )
                    time.sleep(delay)

            self._finish_batch(conn, batch_id, "success", inserted, updated, skipped)
            self._write_log(
                conn,
                batch_id,
                "INFO",
                "同步完成：新增 {}，更新 {}，跳过 {}".format(inserted, updated, skipped),
            )

            result = {
                "success": True,
                "batchId": batch_id,
                "inserted": inserted,
                "updated": updated,
                "skipped": skipped,
                "total": len(rows),
                "error": None,
            }
            self._publish(
                {
                    "batchId": batch_id,
                    "inserted": inserted,
                    "updated": updated,
                    "total": len(rows),
                    "updatedAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                }
            )
            return result
        except Exception as exc:
            logger.error("增量同步失败: %s", exc)
            if batch_id is not None:
                try:
                    self._finish_batch(conn, batch_id, "failed", error_message=str(exc))
                    self._write_log(conn, batch_id, "ERROR", "同步失败: {}".format(exc))
                except Exception as inner:
                    logger.error("更新失败批次状态出错: %s", inner)
            return {
                "success": False,
                "batchId": batch_id,
                "inserted": 0,
                "updated": 0,
                "skipped": 0,
                "total": len(rows),
                "error": str(exc),
            }
        finally:
            try:
                conn.close()
            except Exception:
                pass

    # ------------------------------------------------------------------ #
    # 查询接口
    # ------------------------------------------------------------------ #
    def list_batches(self, limit=20):
        limit = max(1, min(int(limit or 20), 200))
        conn = self._connect()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT id, source_code, status, inserted, updated, skipped, "
                    "error_message, started_at, finished_at "
                    "FROM sync_batches ORDER BY id DESC LIMIT %s",
                    (limit,),
                )
                rows = cursor.fetchall()
        finally:
            conn.close()
        return [self._batch_to_dict(r) for r in rows]

    def list_logs(self, batch_id=None, limit=200):
        limit = max(1, min(int(limit or 200), 500))
        conn = self._connect()
        try:
            with conn.cursor() as cursor:
                if batch_id:
                    cursor.execute(
                        "SELECT id, batch_id, level, message, created_at "
                        "FROM sync_logs WHERE batch_id=%s ORDER BY id DESC LIMIT %s",
                        (batch_id, limit),
                    )
                else:
                    cursor.execute(
                        "SELECT id, batch_id, level, message, created_at "
                        "FROM sync_logs ORDER BY id DESC LIMIT %s",
                        (limit,),
                    )
                rows = cursor.fetchall()
        finally:
            conn.close()
        return [
            {
                "id": r["id"],
                "batchId": r["batch_id"],
                "level": r["level"],
                "message": r["message"],
                "createdAt": self._fmt(r["created_at"]),
            }
            for r in rows
        ]

    def health(self):
        conn = self._connect()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT source_code, COUNT(*) AS total, "
                    "SUM(status='success') AS success_cnt, "
                    "MAX(finished_at) AS last_finished, MAX(started_at) AS last_started "
                    "FROM sync_batches GROUP BY source_code"
                )
                rows = cursor.fetchall()
        finally:
            conn.close()

        now = datetime.now()
        result = []
        for r in rows:
            total = int(r["total"] or 0)
            success_cnt = int(r["success_cnt"] or 0)
            last = r["last_finished"] or r["last_started"]
            freshness = int((now - last).total_seconds()) if isinstance(last, datetime) else None
            result.append(
                {
                    "sourceCode": r["source_code"],
                    "lastSyncAt": self._fmt(last),
                    "successRate": round(success_cnt / total * 100, 2) if total else 0.0,
                    "freshnessSeconds": freshness,
                    "batches": total,
                }
            )
        return result

    def reconcile(self):
        """全量对账：以“当前 CSV 的病例是否都已入库”为准。

        返回 missing（CSV 有、库中没有）、extra（库中有、当前 CSV 没有，
        通常为历史数据）。consistent 表示源数据是否已全部覆盖。
        """
        rows = self._read_csv()
        csv_hashes = {compute_content_hash(r) for r in rows}

        conn = self._connect()
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT content_hash FROM cases WHERE content_hash IS NOT NULL")
                db_hashes = {r["content_hash"] for r in cursor.fetchall()}
        finally:
            conn.close()

        missing = csv_hashes - db_hashes
        extra = db_hashes - csv_hashes
        return {
            "csvCount": len(csv_hashes),
            "dbCount": len(db_hashes),
            "missing": len(missing),
            "extra": len(extra),
            "consistent": len(missing) == 0,
        }

    # ------------------------------------------------------------------ #
    # 工具方法
    # ------------------------------------------------------------------ #
    @staticmethod
    def _fmt(value):
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.strftime("%Y-%m-%d %H:%M:%S")
        return str(value)

    def _batch_to_dict(self, r):
        return {
            "id": r["id"],
            "sourceCode": r["source_code"],
            "status": r["status"],
            "inserted": r["inserted"],
            "updated": r["updated"],
            "skipped": r["skipped"],
            "errorMessage": r["error_message"],
            "startedAt": self._fmt(r["started_at"]),
            "finishedAt": self._fmt(r["finished_at"]),
        }


# 默认单例，供 API / 定时任务复用
sync_service = SyncService()
