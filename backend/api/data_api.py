"""数据实时同步相关 API（任务(2)）。

统一挂载在 /api/v1/data 下，前端通过 vue devServer 的 /api/v1 代理访问 5000 端口。
"""

import logging

from flask import Blueprint, jsonify, request

from backend.services.sync_service import sync_service

logger = logging.getLogger("data_api")

data_bp = Blueprint("data_v1", __name__, url_prefix="/api/v1/data")


def _ok(data):
    return jsonify({"message": "success", "code": 200, "data": data})


def _err(message, status=500):
    return (
        jsonify(
            {
                "message": "error",
                "code": status,
                "data": {"error": str(message)},
            }
        ),
        status,
    )


@data_bp.route("/batches", methods=["GET"])
def list_batches():
    """同步批次记录。"""
    try:
        limit = request.args.get("limit", 20)
        return _ok(sync_service.list_batches(limit))
    except Exception as exc:
        logger.exception("查询同步批次失败")
        return _err(exc)


@data_bp.route("/logs", methods=["GET"])
def list_logs():
    """同步日志，可按 batch_id 过滤。"""
    try:
        batch_id = request.args.get("batch_id") or request.args.get("batchId")
        limit = request.args.get("limit", 200)
        return _ok(sync_service.list_logs(batch_id, limit))
    except Exception as exc:
        logger.exception("查询同步日志失败")
        return _err(exc)


@data_bp.route("/sync", methods=["POST"])
def trigger_sync():
    """手动触发一次增量同步。"""
    try:
        body = request.get_json(force=True, silent=True) or {}
        source = body.get("source") or body.get("sourceCode")
        service = sync_service
        if source and source != sync_service.source_code:
            from backend.services.sync_service import SyncService

            service = SyncService(source_code=source)
        result = service.run_incremental(max_retries=0)
        if not result.get("success"):
            return (
                jsonify(
                    {
                        "message": "error",
                        "code": 500,
                        "data": result,
                    }
                ),
                500,
            )
        return _ok(result)
    except Exception as exc:
        logger.exception("手动同步失败")
        return _err(exc)


@data_bp.route("/reconcile", methods=["POST"])
def trigger_reconcile():
    """触发全量对账。"""
    try:
        return _ok(sync_service.reconcile())
    except Exception as exc:
        logger.exception("全量对账失败")
        return _err(exc)


@data_bp.route("/health", methods=["GET"])
def data_health():
    """各数据源同步新鲜度与成功率。"""
    try:
        return _ok(sync_service.health())
    except Exception as exc:
        logger.exception("查询数据健康度失败")
        return _err(exc)
