"""数据监控中心的数据访问层。

负责所有只读 SQL：
- 病例总量、今日新增、字段完整度、疾病/性别/年龄/月份/医院分布；
- 数据源状态、同步批次、同步日志、数据版本。

Controller 与 Service 不直接写 SQL，符合 SRS NFR-12 的分层约束。
"""

import pymysql

from utils.db_config import get_db_config

# 字段完整度统计的字段与中文标签
COMPLETENESS_FIELDS = [
    ("type", "疾病类型"),
    ("gender", "性别"),
    ("age", "年龄"),
    ("time", "就诊时间"),
    ("content", "病情描述"),
    ("docName", "医生"),
    ("docHospital", "医院"),
    ("department", "科室"),
    ("detailUrl", "详情链接"),
    ("height", "身高"),
    ("weight", "体重"),
    ("illDuration", "病程"),
    ("allergy", "过敏史"),
]


def _connect():
    return pymysql.connect(
        **get_db_config(),
        autocommit=True,
        cursorclass=pymysql.cursors.DictCursor,
    )


class MonitorRepository:
    """监控中心 Repository。所有方法接收已打开的游标，便于一次请求复用连接。"""

    # ------------------------------------------------------------------ #
    # 病例概览
    # ------------------------------------------------------------------ #
    def case_summary(self, cur):
        cur.execute(
            """
            SELECT COUNT(*) AS total,
                   SUM(updated_at >= CURDATE()) AS today_new,
                   MAX(updated_at) AS last_updated,
                   COUNT(DISTINCT `type`) AS disease_kinds,
                   COUNT(DISTINCT docHospital) AS hospital_kinds
            FROM cases
            """
        )
        return cur.fetchone() or {}

    def field_completeness(self, cur):
        """一次扫描统计各字段的非空率。"""
        selects = []
        for field, _label in COMPLETENESS_FIELDS:
            selects.append(
                "SUM(`{f}` IS NOT NULL AND `{f}` <> '') AS `{f}_filled`".format(f=field)
            )
        cur.execute("SELECT COUNT(*) AS total, " + ", ".join(selects) + " FROM cases")
        row = cur.fetchone() or {}
        total = int(row.get("total") or 0)

        result = []
        for field, label in COMPLETENESS_FIELDS:
            filled = int(row.get("{f}_filled".format(f=field)) or 0)
            result.append(
                {
                    "field": field,
                    "label": label,
                    "filled": filled,
                    "total": total,
                    "rate": round(filled / total * 100, 2) if total else 0.0,
                }
            )
        return result

    # ------------------------------------------------------------------ #
    # 分布统计
    # ------------------------------------------------------------------ #
    def disease_top(self, cur, limit=10):
        cur.execute(
            "SELECT `type` AS name, COUNT(*) AS value FROM cases "
            "WHERE `type` IS NOT NULL AND `type` <> '' "
            "GROUP BY `type` ORDER BY value DESC LIMIT %s",
            (limit,),
        )
        return cur.fetchall()

    def gender_distribution(self, cur):
        cur.execute(
            "SELECT gender AS name, COUNT(*) AS value FROM cases "
            "WHERE gender IS NOT NULL AND gender <> '' "
            "GROUP BY gender ORDER BY value DESC"
        )
        return cur.fetchall()

    def age_distribution(self, cur):
        cur.execute(
            """
            SELECT bucket AS name, COUNT(*) AS value FROM (
              SELECT CASE
                WHEN age REGEXP '^[[:space:]]*[0-9]+[[:space:]]*$' THEN
                  CASE
                    WHEN CAST(age AS UNSIGNED) < 18 THEN '0-17'
                    WHEN CAST(age AS UNSIGNED) < 35 THEN '18-34'
                    WHEN CAST(age AS UNSIGNED) < 50 THEN '35-49'
                    WHEN CAST(age AS UNSIGNED) < 65 THEN '50-64'
                    ELSE '65+'
                  END
                ELSE '未知'
              END AS bucket
              FROM cases
            ) AS t
            GROUP BY bucket
            ORDER BY FIELD(bucket, '0-17', '18-34', '35-49', '50-64', '65+', '未知')
            """
        )
        return cur.fetchall()

    def month_distribution(self, cur):
        cur.execute(
            """
            SELECT month_no AS name, COUNT(*) AS value FROM (
              SELECT CASE
                WHEN `time` REGEXP '^[0-9]{1,2}[.][0-9]{1,2}$'
                  THEN CAST(SUBSTRING_INDEX(`time`, '.', 1) AS UNSIGNED)
                WHEN `time` REGEXP '^[0-9]{4}-[0-9]{2}-[0-9]{2}'
                  THEN CAST(SUBSTRING(`time`, 6, 2) AS UNSIGNED)
                ELSE NULL
              END AS month_no
              FROM cases
            ) AS t
            WHERE month_no BETWEEN 1 AND 12
            GROUP BY month_no
            ORDER BY month_no
            """
        )
        return cur.fetchall()

    def hospital_top(self, cur, limit=10):
        cur.execute(
            "SELECT docHospital AS name, COUNT(*) AS value FROM cases "
            "WHERE docHospital IS NOT NULL AND docHospital <> '' "
            "GROUP BY docHospital ORDER BY value DESC LIMIT %s",
            (limit,),
        )
        return cur.fetchall()

    # ------------------------------------------------------------------ #
    # 数据源 / 批次 / 日志 / 版本
    # ------------------------------------------------------------------ #
    def list_sources(self, cur):
        cur.execute(
            "SELECT id, code, name, disease, `type`, enabled, status, last_run_at, "
            "last_success_at, last_delta, total_records, last_message "
            "FROM data_sources ORDER BY id ASC"
        )
        return cur.fetchall()

    def list_batches(self, cur, limit=20):
        cur.execute(
            "SELECT id, source_code, status, inserted, updated, skipped, "
            "error_message, started_at, finished_at "
            "FROM sync_batches ORDER BY id DESC LIMIT %s",
            (limit,),
        )
        return cur.fetchall()

    def batch_stats(self, cur):
        cur.execute(
            "SELECT COUNT(*) AS total, "
            "SUM(status = 'success') AS success_cnt, "
            "SUM(status = 'failed') AS failed_cnt, "
            "MIN(started_at) AS first_started "
            "FROM sync_batches"
        )
        return cur.fetchone() or {}

    def list_logs(self, cur, limit=50, batch_id=None):
        if batch_id:
            cur.execute(
                "SELECT id, batch_id, level, message, created_at FROM sync_logs "
                "WHERE batch_id = %s ORDER BY id DESC LIMIT %s",
                (batch_id, limit),
            )
        else:
            cur.execute(
                "SELECT id, batch_id, level, message, created_at FROM sync_logs "
                "ORDER BY id DESC LIMIT %s",
                (limit,),
            )
        return cur.fetchall()

    def list_versions(self, cur, limit=20):
        cur.execute(
            "SELECT id, name, version_code, operator, action, description, "
            "created_at, total_records, delta_records "
            "FROM data_versions ORDER BY created_at DESC, id DESC LIMIT %s",
            (limit,),
        )
        return cur.fetchall()

    # ------------------------------------------------------------------ #
    # 连接管理
    # ------------------------------------------------------------------ #
    def open(self):
        return _connect()


monitor_repository = MonitorRepository()
