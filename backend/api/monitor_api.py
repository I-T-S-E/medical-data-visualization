"""数据监控中心 API（任务(3)）。

统一响应结构沿用项目约定：``{"message", "code", "data"}``。

说明：为兼容前端 ``/api`` 的 rewrite 规则，后端实际路径为根路径
``/data/monitor``；前端通过 ``this.$http.get('/data/monitor')`` 访问，
经 vue devServer 代理后命中本蓝图。
"""

import logging

from flask import Blueprint, jsonify, request

from backend.services.monitor_service import monitor_service

logger = logging.getLogger("monitor_api")

monitor_bp = Blueprint("monitor", __name__)


def _ok(data):
    return jsonify({"message": "success", "code": 200, "data": data})


def _err(message, status=500):
    return (
        jsonify({"message": "error", "code": status, "data": {"error": str(message)}}),
        status,
    )


def _int_arg(name, default, minimum=1, maximum=200):
    raw = request.args.get(name, default)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(value, maximum))


@monitor_bp.route("/data/monitor", methods=["GET"])
def data_monitor():
    """数据监控中心总览：新鲜度、数据源、完整度、分布、批次、日志、版本。"""
    try:
        payload = monitor_service.overview(
            batch_limit=_int_arg("batch_limit", 20, 1, 100),
            log_limit=_int_arg("log_limit", 50, 1, 200),
            version_limit=_int_arg("version_limit", 20, 1, 100),
        )
        return _ok(payload)
    except Exception as exc:  # noqa: BLE001 - 统一转换为可读错误
        logger.exception("查询监控中心数据失败")
        return _err("监控数据查询失败：{err}".format(err=exc))
