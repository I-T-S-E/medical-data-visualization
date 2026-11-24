# 医疗疾病数据分析大屏可视化系统 —— 概要设计说明书

> 文档版本：v1.0
> 编写日期：2026-11-24
> 配套文档：`docs/SRS.md`、`docs/uml/*.puml`

---

## 1. 设计目标

1. **功能可扩展**：在保留现有 21 个接口的前提下，新增实时同步、数据监控、多模型预测与大模型分析能力。
2. **职责可分离**：Controller 只做参数校验与响应，Service 负责业务编排，Repository 隔离 SQL，ML 负责模型推理。
3. **算法可切换**：通过 Strategy + Factory 支持 BERT / TextCNN / Ensemble 动态选择。
4. **数据可观测**：同步批次、日志、健康度、模型指标均可查询与回溯。
5. **旧系统可兼容**：旧路径与旧字段保持不变，前端无需大规模返工。

---

## 2. 现状分析

| 现状 | 问题 |
|---|---|
| `app.py` 单文件约 2200 行，路由、SQL、业务、报告渲染混在一起 | 高耦合、难维护、难测试 |
| `spiders/data_sync_manager.py` 全量 upsert | 无增量识别、无唯一键导致重复插入 |
| `cases` 表仅有主键，无业务唯一键 | `ON DUPLICATE KEY UPDATE` 实际不生效 |
| `websocket_chat.py` 非流式、会话仅存内存 | 无持久化、无工具调用、无图表 |
| 单一 BERT 模型 | 无对比评估、无版本管理 |
| 前端手动刷新 | 数据更新不可感知 |

> 改造原则：**增量演进，不重写**。`app.py` 保留为启动入口，内部逐步调用新分层；旧路由保留并转发。

---

## 3. 总体架构

### 3.1 目标分层

```text
backend/
├── factory.py               # create_app() 应用工厂
├── extensions.py            # socketio / db / cors 单例
├── config.py                # 从 .env 读取配置
├── api/                     # Controller 层：参数校验 + 响应
│   ├── home_api.py          # 兼容 /getHomeData
│   ├── data_api.py          # /api/v1/data/*
│   ├── prediction_api.py    # /api/v1/predict
│   ├── model_api.py         # /api/v1/models/*
│   ├── report_api.py        # 报告模板/生成
│   └── realtime_api.py      # /internal/publish 事件入口
├── services/                # 业务编排层：无 SQL、无 Flask 细节
│   ├── data_service.py
│   ├── sync_service.py
│   ├── prediction_service.py
│   ├── model_service.py
│   └── llm_service.py
├── repositories/            # 数据访问层：参数化 SQL
│   ├── case_repository.py
│   ├── sync_repository.py
│   ├── chat_repository.py
│   └── model_repository.py
├── ml/                      # 模型层
│   ├── base.py              # Predictor 抽象类
│   ├── bert_predictor.py
│   ├── textcnn_predictor.py
│   ├── baseline_predictor.py
│   └── registry.py          # 模型工厂 + 注册表
└── realtime/
    ├── event_bus.py         # 进程内发布订阅
    └── socket_gateway.py    # /ws/chat + /ws/data
```

### 3.2 分层调用关系

```text
前端 Vue ──HTTP──> Controller(api) ──> Service ──> Repository ──> MySQL
   │                                     │
   │                                     └──> ML Registry ──> Predictor(BERT/TextCNN/Ensemble)
   └──Socket.IO──> Socket Gateway ──> EventBus ──> 前端订阅
```

约束：

- Controller 不得直接执行 SQL；
- Service 不得依赖 `flask.request`、`flask.jsonify`；
- Repository 只暴露领域方法，不暴露游标；
- 模型文件懒加载、单例复用，避免内存重复占用。

---

## 4. 模块职责

| 模块 | 职责 | 关键类/函数 |
|---|---|---|
| `api` | 路由注册、参数校验、统一响应、异常转换 | `data_api`, `prediction_api` |
| `services` | 业务编排、事务边界、事件发布 | `SyncService`, `PredictionService`, `LLMService` |
| `repositories` | 参数化 SQL、结果映射为 DTO | `CaseRepository`, `SyncRepository` |
| `ml` | 模型加载、推理、评估、版本注册 | `Predictor`, `ModelRegistry` |
| `realtime` | 事件发布订阅、Socket.IO 命名空间 | `EventBus`, `socket_gateway` |
| `spiders` | 采集、CSV 生成、调度 | `spiderMain`, `crawler_scheduler` |
| `utils` | 配置、查询工具 | `db_config`, `query` |

---

## 5. 接口约定

### 5.1 统一响应

```json
{
  "message": "success",
  "code": 200,
  "data": {}
}
```

错误：

```json
{
  "message": "error",
  "code": 500,
  "data": { "error": "具体错误信息" }
}
```

### 5.2 旧接口兼容策略

| 旧接口 | 兼容方式 |
|---|---|
| `/getHomeData` | 保留原返回结构，内部改为 `HomeService` 组装 |
| `/submitModel` | 保留 `resultData/confidence/advice/similarCases`，追加 `probabilities/model` |
| `/tableData` | 保留 `resultData` 与 `ids` |
| `/data/*` | 路径不变，逐步迁移到 `DataService` |
| `/templates/*`、`/reports/*` | 路径不变，迁移到 `ReportService` |

### 5.3 新增接口约定

| 方法 | 路径 | 入参 | 出参 `data` |
|---|---|---|---|
| GET | `/api/v1/data/batches` | `limit=20` | `[{id, sourceCode, status, inserted, updated, skipped, startedAt, finishedAt, errorMessage}]` |
| GET | `/api/v1/data/logs` | `batch_id` | `[{id, batchId, level, message, createdAt}]` |
| POST | `/api/v1/data/sync` | `{source?}` | `{batchId, inserted, updated, skipped, total}` |
| POST | `/api/v1/data/reconcile` | `{}` | `{csvCount, dbCount, missing, extra, consistent}` |
| GET | `/api/v1/data/health` | - | `[{sourceCode, lastSyncAt, successRate, freshnessSeconds}]` |
| POST | `/api/v1/predict` | `{content, model}` | `{disease, confidence, probabilities, model}` |
| GET | `/api/v1/models` | - | `[{id, modelName, version, isOnline, macroF1, accuracy, trainedAt}]` |
| POST | `/api/v1/models/{id}/online` | `{}` | `{id, isOnline}` |

### 5.4 内部回调

`POST /internal/data-changed`，Header `X-Internal-Token: <INTERNAL_TOKEN>`：

```json
{ "batchId": 12, "inserted": 30, "updated": 5, "total": 1035, "updatedAt": "2026-11-24 12:00:00" }
```

服务端校验 Token 后，转发至 WebSocket 服务 `POST http://127.0.0.1:5001/internal/publish`，向 `/ws/data` 房间广播 `data.updated`。

> 实现说明：`SyncService` 在同步成功后默认**直接** POST 到 WS 的 `/internal/publish`，避免同进程内自调用造成阻塞；`/internal/data-changed` 作为独立调度器/外部系统的统一入口，校验 Token 后同样转发到 WS，两条路径最终都由 Socket.IO 广播。

---

## 6. 数据库设计

### 6.1 `cases`（扩展）

| 字段 | 类型 | 说明 |
|---|---|---|
| id | int PK AI | 主键 |
| type / gender / age / time | varchar | 现有业务字段 |
| content | TEXT | 原有 `varchar(255)` 不足以容纳爬虫内容，`002` 迁移放宽 |
| docName / docHospital / department / detailUrl | varchar | 现有业务字段 |
| height / weight / illDuration / allergy | varchar | 现有业务字段 |
| content_hash | char(64) | SHA-256 去重哈希，唯一索引 |
| source_code | varchar(32) | 来源标识，默认 `crawler` |
| batch_id | bigint | 首次写入批次（内容不变不重复更新） |
| updated_at | datetime | 更新时间 |

唯一索引：`uk_cases_hash(content_hash)`。

> 迁移注意：现有表无业务唯一键，需先回填 `content_hash`（对已有行计算 SHA-256）并去重，再建唯一索引，否则索引创建失败。
>
> `002_widen_cases_content.sql`：将 `cases.content` 与 `cases_snapshot.content` 放宽为 `TEXT`（当前 CSV 内容最长 276 字符，`varchar(255)` 会报 1406 错误）。迁移按 `001` → `002` 顺序执行。
>
> 对账口径：`consistent = (missing == 0)`，即“当前 CSV 的病例是否已全部入库”；`extra` 表示库中存在但当前 CSV 没有的历史数据，仅作提示。

### 6.2 `sync_batches`

| 字段 | 类型 | 说明 |
|---|---|---|
| id | bigint PK AI | 批次号 |
| source_code | varchar(32) | 数据源 |
| status | varchar(20) | running/success/failed |
| inserted / updated / skipped | int | 统计 |
| error_message | text | 错误信息 |
| started_at | datetime | 开始时间 |
| finished_at | datetime | 结束时间 |

### 6.3 `sync_logs`

| 字段 | 类型 | 说明 |
|---|---|---|
| id | bigint PK AI | 日志号 |
| batch_id | bigint | 关联批次（可空） |
| level | varchar(16) | INFO/WARN/ERROR |
| message | text | 日志内容 |
| created_at | datetime | 创建时间 |

### 6.4 `chat_sessions` / `chat_messages`

| 表 | 字段 |
|---|---|
| chat_sessions | id(varchar64 PK)、title、context_json(JSON)、created_at、updated_at |
| chat_messages | id(bigint PK)、session_id、role、content(MEDIUMTEXT)、tokens、model、created_at |

### 6.5 `model_versions` / `model_metrics`

| 表 | 字段 |
|---|---|
| model_versions | id、model_name、version、path、is_online、macro_f1、accuracy、trained_at |
| model_metrics | id、model_version_id、metric_key、metric_value、detail_json(JSON) |

### 6.6 实体关系

详见 `docs/uml/er.puml`。核心关系：

- `sync_batches` 1 — N `sync_logs`
- `sync_batches` 1 — N `cases`（`cases.batch_id`）
- `chat_sessions` 1 — N `chat_messages`
- `model_versions` 1 — N `model_metrics`

---

## 7. 设计模式与体系结构

| 模式 | 使用位置 | 解决问题 |
|---|---|---|
| 分层架构 + 应用工厂 | `backend/factory.py` + `api/services/repositories` | 展示、业务、数据分离 |
| Strategy + Factory | `ml/registry.py`：Bert / TextCNN / Baseline / Ensemble | 算法可切换、可扩展 |
| Repository | `repositories/*` | 隔离 SQL，业务层不依赖数据库细节 |
| Facade | `services/*` | 对 Controller 暴露简单统一接口 |
| Observer / Pub-Sub | `realtime/event_bus.py` + SocketIO | 数据变更主动推送前端 |
| Adapter | `llm_service.py` 中 `LLMProvider` 适配 DeepSeek/OpenAI | 大模型可替换 |
| Template Method | `report_service.py`：收集→校验→渲染→导出 | 固定流程，替换步骤 |
| Chain of Responsibility | 数据导入校验：格式→必填→业务规则 | 校验规则可插拔 |
| State | 报告模板 `draft/published/offline` | 状态流转受控 |
| Singleton | 配置、调度器、模型注册表 | 全局唯一资源 |
| DTO / Serializer | 各 API 的 `to_dict()` | 统一响应结构 |

---

## 8. 关键流程设计

### 8.1 增量同步 + 事件推送

```text
Scheduler / 手动触发
  → SyncService.run_incremental()
    → 读取 CSV
    → 规范化字段 + SHA-256 计算 content_hash
    → 写 sync_batches(status=running)
    → 批量 INSERT ... ON DUPLICATE KEY UPDATE
    → 写 sync_logs
    → 更新 sync_batches(status=success, 统计, finished_at)
    → POST /internal/publish（或经 /internal/data-changed 转发）
      → SocketIO emit('data.updated') 到 /ws/data
        → Index.vue 节流 3s 调 /getHomeData + Toast
```

失败处理：按 1/5/15 分钟退避重试，3 次后标记 `failed` 并写 `error_message`。

### 8.2 大模型流式分析

```text
AiAnalyst.vue
  → socket.emit('join', {sessionId, context})
  → socket.emit('message', {sessionId, content})
    → LLMService 组装系统提示 + 历史 + context
    → LLMProvider.stream() 逐 chunk emit('delta')
    → 若需查库：emit('tool') → 执行白名单只读查询
    → 返回图表：emit('chart', {spec})
    → emit('done', {messageId, usage, finishedAt})
  → 消息写入 chat_messages
```

安全：仅执行参数化只读 SQL，表白名单，`LIMIT 200`，5s 超时。

### 8.3 多模型预测

```text
POST /api/v1/predict {content, model}
  → PredictionService
    → ModelRegistry.get(model)
      → BertPredictor / TextCNN / Ensemble
    → predict(content)
  → {disease, confidence, probabilities, model}
```

---

## 9. 兼容与迁移策略

1. **第 1 阶段**：新增 `backend/` 骨架与 `data_api` 蓝图，旧 `app.py` 路由保持不变，仅注册新蓝图。
2. **第 2 阶段**：将 `/getHomeData`、`/submitModel`、`/tableData` 的 SQL/业务迁移到 Service/Repository，旧路由转发，返回结构不变。
3. **第 3 阶段**：`data_sync_manager.py` 的定时函数委托 `SyncService`，旧类保留。
4. **第 4 阶段**：AI 助手升级为流式 + 持久化 + 工具调用，`websocket_chat.py` 保留为启动适配层。
5. **前端兼容**：`axios` baseURL 仍为 `/api`；新增接口通过 `/api/v1` 代理到 5000（不 rewrite）。

---

## 10. 非功能设计

| 指标 | 实现手段 |
|---|---|
| P95 < 2s | 索引优化、分页、只读查询、缓存统计结果 |
| 更新可见 < 10s | 事件驱动 + 前端节流 3s 刷新 |
| 首字 < 2s | LLM 流式输出；本地 BERT 懒加载 |
| 推理 < 1s | 模型单例复用；必要时 CPU 线程数限制 |
| 重试 | 指数退避 1/5/15 分钟 |
| 降级 | WS 断开 30s 轮询；LLM 不可用回退本地规则 |
| 安全 | `.env` 管理密钥；内部 Token；只读 SQL；限流 |
| 可观测 | 批次/日志/健康度/模型指标表 |

---

## 11. UML 索引

| 图 | 文件 | 说明 |
|---|---|---|
| 用例图 | `docs/uml/use-case.puml` | 三类角色 + AI 助手 |
| 类图 | `docs/uml/class.puml` | 分层关键类与模式 |
| 时序图（同步） | `docs/uml/sequence-sync.puml` | 爬虫→CSV→入库→推送→刷新 |
| 时序图（对话） | `docs/uml/sequence-chat.puml` | WS→LLM→工具→流式返回 |
| 组件图 | `docs/uml/component.puml` | 前端/API/WS/调度/DB/模型 |
| 部署图 | `docs/uml/deployment.puml` | 端口与节点 |
| ER 图 | `docs/uml/er.puml` | 核心数据实体 |
| 状态图 | `docs/uml/state-template.puml` | 报告模板状态流转 |
