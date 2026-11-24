"""模型评估与版本中心 API（任务(3)）。

接口（根路径，兼容前端 /api rewrite）：

* ``GET  /models/overview``                 模型总览、版本列表、趋势、当前指标
* ``POST /models/evaluate``                 用当前 cases 做离线评估并写库
* ``GET  /models/versions/<id>``            版本详情（混淆矩阵、各类别指标）
* ``POST /models/versions/<id>/online``     设为线上模型
"""

import logging

from flask import Blueprint, jsonify, request

from backend.services.model_service import model_service

logger = logging.getLogger("model_api")

model_bp = Blueprint("model", __name__)


def _ok(data):
    return jsonify({"message": "success", "code": 200, "data": data})


def _err(message, status=500):
    return (
        jsonify({"message": "error", "code": status, "data": {"error": str(message)}}),
        status,
    )


@model_bp.route("/models/overview", methods=["GET"])
def models_overview():
    try:
        return _ok(model_service.overview())
    except Exception as exc:  # noqa: BLE001
        logger.exception("查询模型总览失败")
        return _err("模型总览查询失败：{err}".format(err=exc))


@model_bp.route("/models/evaluate", methods=["POST"])
def models_evaluate():
    """对当前病例数据执行一次离线评估，结果写入 model_versions / model_metrics。"""
    try:
        body = request.get_json(force=True, silent=True) or {}
        sample_limit = int(body.get("sampleLimit") or body.get("sample_limit") or 10000)
    except (TypeError, ValueError):
        sample_limit = 10000
    sample_limit = max(1, min(sample_limit, 50000))

    try:
        detail = model_service.evaluate(sample_limit=sample_limit)
        return _ok(detail)
    except RuntimeError as exc:
        logger.warning("模型评估失败: %s", exc)
        return _err(str(exc), status=400)
    except Exception as exc:  # noqa: BLE001
        logger.exception("模型评估失败")
        return _err("模型评估失败：{err}".format(err=exc))


@model_bp.route("/models/versions/<int:version_id>", methods=["GET"])
def model_version_detail(version_id):
    try:
        detail = model_service.version_detail(version_id)
        if detail is None:
            return _err("模型版本不存在: {id}".format(id=version_id), status=404)
        return _ok(detail)
    except Exception as exc:  # noqa: BLE001
        logger.exception("查询模型版本失败")
        return _err("模型版本查询失败：{err}".format(err=exc))


@model_bp.route("/models/versions/<int:version_id>/online", methods=["POST"])
def model_version_online(version_id):
    try:
        result = model_service.activate(version_id)
        return _ok(result)
    except ValueError as exc:
        return _err(str(exc), status=404)
    except Exception as exc:  # noqa: BLE001
        logger.exception("切换线上模型失败")
        return _err("切换线上模型失败：{err}".format(err=exc))
