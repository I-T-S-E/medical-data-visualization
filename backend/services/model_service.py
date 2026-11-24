"""模型评估与版本中心业务编排层。

核心能力：
- 懒加载 ``spiders/models`` 下的 RandomForest + TF-IDF 产物（单例缓存）；
- 对当前 ``cases`` 做离线评估，输出 accuracy / macro-F1 / 各类别 P/R/F1 /
  混淆矩阵 / 单条推理延迟；
- 评估结果写入 ``model_versions`` + ``model_metrics``；
- 支持把指定版本切换为线上模型（同模型其他版本自动下线）。

设计模式：Strategy（不同模型产物可替换）+ Registry（按名称加载）+ Facade（对 API 暴露统一入口）。
本模块不依赖 Flask 上下文。
"""

import json
import logging
import os
import pickle
import re
import time
import warnings
from datetime import datetime

import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)

from backend.repositories.model_repository import (
    ARTIFACT_FILES,
    MODEL_DIR,
    model_repository,
)

logger = logging.getLogger("model_service")

MODEL_NAME = "random_forest"
MODEL_PATH = "spiders/models/classifier_model.pkl"

DURATION_MAPPING = {
    "未知": 0,
    "1天内": 1,
    "1-3天": 2,
    "3-7天": 3,
    "1-2周": 4,
    "2-4周": 5,
    "1-3个月": 6,
    "3个月以上": 7,
}


def _fmt(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    return str(value)


def _to_float(value):
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_json(value):
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except Exception:
        return None


def _clean_age(value):
    match = re.search(r"\d+", str(value or ""))
    return int(match.group()) if match else 0


class ModelService:
    def __init__(self, repository=None):
        self.repository = repository or model_repository
        self._cache = None
        self._cache_mtime = None

    # ------------------------------------------------------------------ #
    # 模型产物（懒加载 + 单例缓存）
    # ------------------------------------------------------------------ #
    def _artifacts(self):
        paths = {name: os.path.join(MODEL_DIR, name) for name in ARTIFACT_FILES}
        missing = [name for name, path in paths.items() if not os.path.exists(path)]
        if missing:
            raise RuntimeError(
                "模型产物缺失：{files}，请先运行 spiders/model_trainer.py 训练模型".format(
                    files=", ".join(missing)
                )
            )

        mtime = os.path.getmtime(paths["classifier_model.pkl"])
        if self._cache is not None and self._cache_mtime == mtime:
            return self._cache

        loaded = {}
        with warnings.catch_warnings():
            # 训练环境 sklearn 版本与当前环境不同，忽略版本告警
            warnings.simplefilter("ignore")
            for name, path in paths.items():
                with open(path, "rb") as fp:
                    loaded[name] = pickle.load(fp)
        self._cache = loaded
        self._cache_mtime = mtime
        return loaded

    def _build_features(self, artifacts, rows):
        """把病例记录转换为与训练时一致的特征矩阵。"""
        df = pd.DataFrame(rows)
        df["gender"] = df["gender"].fillna("未知").astype(str)
        df["age"] = df["age"].fillna("0").astype(str)
        df["illDuration"] = df["illDuration"].fillna("未知").astype(str)
        df["content"] = df["content"].fillna("").astype(str)

        gender_encoder = artifacts["label_encoder.pkl"]
        known_genders = set(gender_encoder.classes_)
        df["gender_norm"] = df["gender"].apply(
            lambda g: g if g in known_genders else "未知"
        )

        df["gender_encoded"] = gender_encoder.transform(df["gender_norm"])
        df["age_numeric"] = df["age"].apply(_clean_age)
        df["duration_encoded"] = df["illDuration"].map(
            lambda x: DURATION_MAPPING.get(str(x), 0)
        )

        tfidf = artifacts["tfidf_vectorizer.pkl"]
        matrix = tfidf.transform(df["content"])
        tfidf_df = pd.DataFrame(
            matrix.toarray(),
            columns=["tfidf_{i}".format(i=i) for i in range(matrix.shape[1])],
        )

        features = pd.concat(
            [
                df[["gender_encoded", "age_numeric", "duration_encoded"]].reset_index(
                    drop=True
                ),
                tfidf_df.reset_index(drop=True),
            ],
            axis=1,
        )
        return df, features

    # ------------------------------------------------------------------ #
    # 离线评估
    # ------------------------------------------------------------------ #
    def evaluate(self, sample_limit=10000):
        rows = self.repository.load_eval_samples(limit=sample_limit)
        if not rows:
            raise RuntimeError("cases 表中没有可用于评估的病例数据")

        artifacts = self._artifacts()
        target_encoder = artifacts["target_encoder.pkl"]
        classes = [str(c) for c in target_encoder.classes_]

        df = pd.DataFrame(rows)
        evaluable = df[df["type"].astype(str).isin(classes)].copy()
        skipped = len(df) - len(evaluable)
        if evaluable.empty:
            raise RuntimeError("当前病例的疾病类型均不在模型类别中，无法评估")

        evaluable, features = self._build_features(artifacts, evaluable.to_dict("records"))
        y_true = target_encoder.transform(evaluable["type"].astype(str))

        scaler = artifacts["scaler.pkl"]
        model = artifacts["classifier_model.pkl"]

        started = time.perf_counter()
        scaled = scaler.transform(features)
        y_pred = model.predict(scaled)
        elapsed_ms = (time.perf_counter() - started) * 1000
        latency_ms = round(elapsed_ms / max(len(features), 1), 3)

        accuracy = accuracy_score(y_true, y_pred)
        macro_f1 = f1_score(y_true, y_pred, average="macro", zero_division=0)
        precision_w = precision_score(y_true, y_pred, average="weighted", zero_division=0)
        recall_w = recall_score(y_true, y_pred, average="weighted", zero_division=0)
        f1_w = f1_score(y_true, y_pred, average="weighted", zero_division=0)

        labels = list(range(len(classes)))
        report = classification_report(
            y_true,
            y_pred,
            labels=labels,
            target_names=classes,
            output_dict=True,
            zero_division=0,
        )
        cm = confusion_matrix(y_true, y_pred, labels=labels)

        per_class = []
        for name in classes:
            item = report.get(name, {})
            per_class.append(
                {
                    "name": name,
                    "precision": round(float(item.get("precision", 0.0)), 4),
                    "recall": round(float(item.get("recall", 0.0)), 4),
                    "f1": round(float(item.get("f1-score", 0.0)), 4),
                    "support": int(item.get("support", 0)),
                }
            )

        status = self.repository.load_model_status()
        base_version = str(status.get("model_version") or "0.0.0")
        now = datetime.now()
        version = "{base}-eval-{stamp}".format(
            base=base_version, stamp=now.strftime("%Y%m%d%H%M%S%f")
        )

        trained_at = now
        raw_trained = status.get("last_train_time")
        if raw_trained:
            try:
                trained_at = datetime.strptime(raw_trained, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                trained_at = now

        online = self.repository.online_version(MODEL_NAME)
        metrics = [
            ("accuracy", round(float(accuracy), 4), None),
            ("precision_weighted", round(float(precision_w), 4), None),
            ("recall_weighted", round(float(recall_w), 4), None),
            ("f1_weighted", round(float(f1_w), 4), None),
            ("macro_f1", round(float(macro_f1), 4), None),
            ("eval_samples", int(len(evaluable)), None),
            ("skipped_samples", int(skipped), None),
            ("latency_ms", latency_ms, None),
            ("confusion_matrix", None, {"classes": classes, "matrix": cm.tolist()}),
            ("per_class_report", None, per_class),
        ]

        version_id = self.repository.insert_evaluation(
            model_name=MODEL_NAME,
            version=version,
            path=MODEL_PATH,
            accuracy=round(float(accuracy), 4),
            macro_f1=round(float(macro_f1), 4),
            trained_at=trained_at,
            metrics=metrics,
            is_online=online is None,
        )
        logger.info(
            "模型评估完成 version=%s accuracy=%.4f macro_f1=%.4f samples=%s",
            version,
            accuracy,
            macro_f1,
            len(evaluable),
        )
        return self.version_detail(version_id)

    # ------------------------------------------------------------------ #
    # 查询
    # ------------------------------------------------------------------ #
    def _version_dto(self, row):
        return {
            "id": row.get("id"),
            "modelName": row.get("model_name"),
            "version": row.get("version"),
            "path": row.get("path"),
            "isOnline": bool(row.get("is_online")),
            "accuracy": _to_float(row.get("accuracy")),
            "macroF1": _to_float(row.get("macro_f1")),
            "trainedAt": _fmt(row.get("trained_at")),
        }

    def _metrics_dto(self, version_id):
        rows = self.repository.load_metrics(version_id)
        values = {}
        details = {}
        for r in rows:
            key = r.get("metric_key")
            if r.get("metric_value") is not None:
                values[key] = _to_float(r.get("metric_value"))
            detail = _parse_json(r.get("detail_json"))
            if detail is not None:
                details[key] = detail

        confusion = details.get("confusion_matrix") or {}
        return {
            "accuracy": values.get("accuracy"),
            "macroF1": values.get("macro_f1"),
            "precisionWeighted": values.get("precision_weighted"),
            "recallWeighted": values.get("recall_weighted"),
            "f1Weighted": values.get("f1_weighted"),
            "evalSamples": int(values.get("eval_samples") or 0),
            "skippedSamples": int(values.get("skipped_samples") or 0),
            "latencyMs": values.get("latency_ms"),
            "labels": confusion.get("classes") or [],
            "confusionMatrix": confusion.get("matrix") or [],
            "perClass": details.get("per_class_report") or [],
        }

    def version_detail(self, version_id):
        row = self.repository.get_version(version_id)
        if not row:
            return None
        detail = self._version_dto(row)
        detail["metrics"] = self._metrics_dto(version_id)
        return detail

    def overview(self, limit=30):
        versions = self.repository.list_versions(MODEL_NAME, limit=limit)
        online = next((v for v in versions if v.get("is_online")), None)
        active = online or (versions[0] if versions else None)

        active_detail = self.version_detail(active["id"]) if active else None
        status = self.repository.load_model_status()

        return {
            "modelName": MODEL_NAME,
            "modelStatus": {
                "version": status.get("model_version"),
                "accuracy": _to_float(status.get("accuracy")),
                "trainedAt": status.get("last_train_time"),
                "status": status.get("last_train_status"),
                "samples": status.get("data_samples"),
                "trainCount": status.get("train_count"),
            },
            "onlineId": online["id"] if online else None,
            "activeId": active["id"] if active else None,
            "active": active_detail,
            "versions": [self._version_dto(v) for v in versions],
            "trend": [self._version_dto(v) for v in reversed(versions)],
            "artifacts": self.repository.artifact_info(),
        }

    # ------------------------------------------------------------------ #
    # 上线切换
    # ------------------------------------------------------------------ #
    def activate(self, version_id):
        result = self.repository.set_online(version_id)
        if result is None:
            raise ValueError("模型版本不存在: {id}".format(id=version_id))
        return result


model_service = ModelService()
