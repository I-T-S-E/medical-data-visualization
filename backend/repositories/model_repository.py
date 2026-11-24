"""模型评估与版本中心的数据访问层。

负责：
- 读取 ``spiders/models`` 下的模型状态（model_status.json）；
- 读取当前 ``cases`` 作为离线评估样本；
- ``model_versions`` / ``model_metrics`` 的读写与上线切换。

Controller / Service 不直接写 SQL。
"""

import json
import os

import pymysql

from utils.db_config import get_db_config

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MODEL_DIR = os.path.join(BASE_DIR, "spiders", "models")
MODEL_STATUS_FILE = os.path.join(MODEL_DIR, "model_status.json")
ARTIFACT_FILES = [
    "classifier_model.pkl",
    "tfidf_vectorizer.pkl",
    "scaler.pkl",
    "label_encoder.pkl",
    "target_encoder.pkl",
]


def _connect():
    return pymysql.connect(
        **get_db_config(),
        autocommit=False,
        cursorclass=pymysql.cursors.DictCursor,
    )


class ModelRepository:
    # ------------------------------------------------------------------ #
    # 模型产物 / 状态
    # ------------------------------------------------------------------ #
    def load_model_status(self):
        try:
            with open(MODEL_STATUS_FILE, "r", encoding="utf-8") as fp:
                return json.load(fp)
        except Exception:
            return {}

    def artifact_info(self):
        files = []
        for name in ARTIFACT_FILES:
            path = os.path.join(MODEL_DIR, name)
            files.append(
                {
                    "name": name,
                    "exists": os.path.exists(path),
                    "size": os.path.getsize(path) if os.path.exists(path) else 0,
                }
            )
        return {
            "dir": "spiders/models",
            "files": files,
            "ready": all(f["exists"] for f in files),
        }

    # ------------------------------------------------------------------ #
    # 评估样本
    # ------------------------------------------------------------------ #
    def load_eval_samples(self, limit=10000):
        conn = _connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT `type`, gender, age, content, illDuration
                    FROM cases
                    WHERE content IS NOT NULL AND content <> ''
                      AND `type` IS NOT NULL AND `type` <> ''
                      AND `type` <> '类型'
                    ORDER BY id ASC
                    LIMIT %s
                    """,
                    (limit,),
                )
                return cur.fetchall()
        finally:
            conn.close()

    # ------------------------------------------------------------------ #
    # 版本
    # ------------------------------------------------------------------ #
    def list_versions(self, model_name=None, limit=50):
        conn = _connect()
        try:
            with conn.cursor() as cur:
                if model_name:
                    cur.execute(
                        "SELECT id, model_name, version, path, is_online, macro_f1, "
                        "accuracy, trained_at FROM model_versions "
                        "WHERE model_name = %s ORDER BY id DESC LIMIT %s",
                        (model_name, limit),
                    )
                else:
                    cur.execute(
                        "SELECT id, model_name, version, path, is_online, macro_f1, "
                        "accuracy, trained_at FROM model_versions "
                        "ORDER BY id DESC LIMIT %s",
                        (limit,),
                    )
                return cur.fetchall()
        finally:
            conn.close()

    def get_version(self, version_id):
        conn = _connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, model_name, version, path, is_online, macro_f1, "
                    "accuracy, trained_at FROM model_versions WHERE id = %s",
                    (version_id,),
                )
                return cur.fetchone()
        finally:
            conn.close()

    def online_version(self, model_name):
        conn = _connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, model_name, version, path, is_online, macro_f1, "
                    "accuracy, trained_at FROM model_versions "
                    "WHERE model_name = %s AND is_online = 1 ORDER BY id DESC LIMIT 1",
                    (model_name,),
                )
                return cur.fetchone()
        finally:
            conn.close()

    def load_metrics(self, version_id):
        conn = _connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, model_version_id, metric_key, metric_value, detail_json "
                    "FROM model_metrics WHERE model_version_id = %s ORDER BY id ASC",
                    (version_id,),
                )
                return cur.fetchall()
        finally:
            conn.close()

    # ------------------------------------------------------------------ #
    # 写入
    # ------------------------------------------------------------------ #
    def insert_evaluation(
        self,
        model_name,
        version,
        path,
        accuracy,
        macro_f1,
        trained_at,
        metrics,
        is_online=False,
    ):
        """写入一次评估结果，返回新的 model_versions.id。"""
        conn = _connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO model_versions "
                    "(model_name, version, path, is_online, macro_f1, accuracy, trained_at) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                    (
                        model_name,
                        version,
                        path,
                        1 if is_online else 0,
                        macro_f1,
                        accuracy,
                        trained_at,
                    ),
                )
                version_id = cur.lastrowid

                rows = []
                for key, value, detail in metrics:
                    rows.append(
                        (
                            version_id,
                            key,
                            value,
                            json.dumps(detail, ensure_ascii=False) if detail is not None else None,
                        )
                    )
                if rows:
                    cur.executemany(
                        "INSERT INTO model_metrics "
                        "(model_version_id, metric_key, metric_value, detail_json) "
                        "VALUES (%s, %s, %s, %s)",
                        rows,
                    )
            conn.commit()
            return version_id
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def set_online(self, version_id):
        """把指定版本设为线上，同时把同模型的其他版本置为离线。"""
        conn = _connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT model_name FROM model_versions WHERE id = %s", (version_id,)
                )
                row = cur.fetchone()
                if not row:
                    return None
                model_name = row["model_name"]
                cur.execute(
                    "UPDATE model_versions SET is_online = 0 WHERE model_name = %s",
                    (model_name,),
                )
                cur.execute(
                    "UPDATE model_versions SET is_online = 1 WHERE id = %s", (version_id,)
                )
            conn.commit()
            return {"id": version_id, "modelName": model_name, "isOnline": True}
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


model_repository = ModelRepository()
