# 医疗疾病数据分析大屏可视化系统 —— 需求规格说明书（SRS）

> 项目名称：基于开源医疗数据可视化平台的实时智能分析系统扩展
> 文档版本：v1.0
> 编写日期：2026-11-24
> 适用范围：软件工程课程实践 / 开源软件项目赋能

---

## 1. 引言

### 1.1 编写目的

本文档定义“医疗疾病数据分析大屏可视化系统”的功能需求、非功能需求与验收标准，作为设计、开发、测试和验收的依据。读者包括开发人员、测试人员、课程指导教师与项目验收方。

### 1.2 项目背景

现有开源项目已具备医疗病例数据的采集、存储、统计大屏、在线预测、数据管理与 AI 问答能力，但存在以下不足：

- 数据同步为全量覆盖式写入，无增量识别、无去重、无同步批次与日志；
- 数据更新后前端只能手动刷新，缺乏实时推送；
- AI 助手为非流式单轮问答，无会话持久化与业务工具调用；
- 只有单一 BERT 模型，无多模型对比、评估与版本管理；
- 后端为单文件 `app.py`（约 2200 行），展示、业务、数据访问耦合。

本项目在**不推翻原有功能**的前提下，以“增加功能为主、工程化改造为辅”的方式扩展实时同步、数据监控、模型评估与大模型分析能力。

### 1.3 术语与缩写

| 术语 | 说明 |
|---|---|
| 大屏 | 首页数据可视化看板（`Index.vue`） |
| CSV | 爬虫落盘的病例数据文件（`spiders/temp2.csv`） |
| 增量同步 | 仅写入新增或内容变化的病例，幂等去重 |
| 对账（Reconcile） | 定时全量校验 CSV 与数据库一致性 |
| 批次（Batch） | 一次同步任务的执行记录，含插入/更新/跳过统计 |
| 事件推送 | 后端数据变更后通过 Socket.IO 主动通知前端 |
| LLM | 大语言模型，本文指 DeepSeek Chat |
| 工具调用 | LLM Function Calling，调用后端只读查询接口 |
| Champion/Challenger | 线上模型（冠军）与候选模型（挑战者）对比上线机制 |

### 1.4 参考资料

- `扩展方案.md`：系统扩展总体方案
- `app.py`：Flask 主服务（现有接口实现）
- `websocket_chat.py`：Socket.IO AI 助手服务（端口 5001）
- `machine/tree.py`：BERT 疾病文本分类与相似病例检索
- `spiders/data_sync_manager.py`：现有 CSV→MySQL 同步逻辑
- `utils/db_config.py`：数据库配置统一入口
- `medicalinfo.sql`：`cases` 表结构与初始数据

---

## 2. 系统概述

### 2.1 系统定位

面向医生、医学研究者与数据管理人员的医疗病例数据可视化与智能分析平台，提供：

1. 病例数据采集、增量同步与数据质量管理；
2. 多维度统计大屏与条件检索；
3. 基于深度学习的疾病预测与相似病例推荐；
4. 多模型评估、对比与版本管理；
5. 基于大模型的流式数据分析助手。

### 2.2 现有系统基础

| 模块 | 现状 |
|---|---|
| 前端 | Vue2 + Element UI + ECharts + DataV，页面：首页、在线预测、数据管理、报告生成、AI 医疗助手 |
| 后端 API | Flask，`app.py` 提供首页统计、预测、数据管理、导入导出、版本回滚、报告模板与生成等 21 个接口 |
| WebSocket | `websocket_chat.py`，Socket.IO `/ws/chat`，端口 5001，DeepSeek 非流式问答 |
| 模型 | `machine/tree.py`，bert-base-chinese 疾病分类 + 相似病例检索 |
| 采集与调度 | `spiders/`：爬虫、CSV→MySQL 同步、APScheduler 定时任务、sklearn 模型训练 |
| 数据库 | MySQL `medicalinfo`，核心表 `cases`（13 个业务字段） |

### 2.3 用户角色

| 角色 | 职责 | 主要关注 |
|---|---|---|
| 医生 / 研究者 | 查看大屏、检索病例、模型预测、模型评估 | 数据准确性、预测置信度、相似病例 |
| 数据管理员 | 配置数据源、触发同步、查看日志、版本回滚 | 同步成功率、数据新鲜度、可回滚性 |
| 系统管理员 | 模型重训练与上线切换、调度状态、审计日志 | 系统稳定性、可观测性、权限与安全 |
| AI 助手（内部服务） | 多轮问诊、基于筛选条件分析、生成图表 | 上下文准确、响应及时、可追溯 |

### 2.4 运行环境

- 后端：Python 3.8–3.10，Flask 2.3，PyMySQL，APScheduler，PyTorch/Transformers
- 前端：Node.js 16/18，Vue 2.6，Vue CLI 4.5
- 数据库：MySQL 8.x
- 端口：前端 8080，Flask API 5000，WebSocket 5001，MySQL 3306

---

## 3. 用例需求

### 3.1 用例清单

| 编号 | 用例名称 | 参与者 | 前置条件 | 基本流程 | 后置条件 |
|---|---|---|---|---|---|
| UC-01 | 查看实时大屏 | 医生/研究者 | 服务可用 | 打开首页 → 拉取 `/getHomeData` → 渲染统计图 → 订阅数据变更事件 → 自动刷新 | 展示最新统计数据 |
| UC-02 | 按条件检索病例 | 医生/研究者 | 已加载病例 | 选择疾病/时间/性别 → 前端过滤 → 展示列表 | 展示筛选结果 |
| UC-03 | 相似病例推荐 | 医生/研究者 | 模型已加载 | 输入症状 → `/submitModel` → 返回疾病、置信度、相似病例 | 展示预测与相似病例 |
| UC-04 | 模型预测与置信度 | 医生/研究者 | 模型已加载 | 输入文本 → 选择模型 → `/api/v1/predict` | 返回多模型概率与置信度 |
| UC-05 | 模型对比评估 | 医生/研究者 | 存在评估指标 | 打开模型中心 → 查看准确率/F1/混淆矩阵 | 展示模型对比结果 |
| UC-06 | 配置数据源 | 数据管理员 | 已登录 | 打开数据监控中心 → 启用/停用数据源 | 数据源状态更新 |
| UC-07 | 手动触发同步 | 数据管理员 | 数据源已启用 | 点击“立即同步” → `POST /api/v1/data/sync` | 生成同步批次 |
| UC-08 | 查看同步日志 | 数据管理员 | 存在批次 | 查看批次列表 → 打开日志抽屉 → `GET /api/v1/data/logs` | 展示批次日志明细 |
| UC-09 | 失败重试 | 数据管理员 | 存在失败批次 | 点击重试 → 重新执行同步 | 生成新批次 |
| UC-10 | 数据版本回滚 | 数据管理员 | 存在版本快照 | `GET /data/versions` → `POST /data/versions/{id}/rollback` | 恢复指定版本数据 |
| UC-11 | 模型重训练/上线切换 | 系统管理员 | 训练数据充足 | 触发重训练 → 写评估指标 → 达到阈值后切换线上模型 | 线上模型更新 |
| UC-12 | 查看任务调度状态 | 系统管理员 | 调度器运行 | 查看任务列表 → 暂停/恢复/立即执行 | 任务状态变更 |
| UC-13 | 查看审计日志 | 系统管理员 | 存在操作记录 | 按时间/操作人筛选审计日志 | 展示审计记录 |
| UC-14 | 多轮问诊 | 医生/研究者 | LLM 可用 | 连接 `/ws/chat` → 发送消息 → 流式接收回复 | 会话持久化 |
| UC-15 | 基于筛选条件提问 | 医生/研究者 | 已选择大屏筛选条件 | 携带 context 提问 → 后端工具查库 | 返回基于数据的回答 |
| UC-16 | 自动生成统计图表 | 医生/研究者 | 查询有结果 | 工具调用返回数据 → 生成 ECharts spec → 前端渲染 | 展示图表 |

### 3.2 用例关系

- UC-03 与 UC-04 为同一预测能力的不同入口：`/submitModel`（旧接口，BERT 单模型）与 `/api/v1/predict`（新接口，支持多模型与集成）。
- UC-05 依赖 UC-11：模型中心展示的指标由训练/评估任务写入 `model_versions`、`model_metrics`。
- UC-16 被 UC-15 包含：数据分析助手的图表能力建立在工具查库结果之上。

---

## 4. 功能需求

### 4.1 首页统计与实时大屏

| 编号 | 需求 | 说明 |
|---|---|---|
| FR-01 | 首页统计接口 | `GET/POST /getHomeData` 返回饼图、词云、病例列表、性别比例、年龄分布、体重分布、医院/科室/疾病 Top 等 |
| FR-02 | 病例列表展示 | `GET/POST /tableData` 返回业务字段与对应自增 id |
| FR-03 | 数据新鲜度展示 | 首页展示“最近同步时间”“数据新鲜度”指标 |
| FR-04 | 实时自动刷新 | 收到 `data.updated` 事件后节流 3s 重新拉取 `/getHomeData`，并 Toast 提示新增条数 |
| FR-05 | 断线降级 | WebSocket 断开时降级为 30s 轮询 |

### 4.2 在线预测

| 编号 | 需求 | 说明 |
|---|---|---|
| FR-06 | BERT 疾病预测 | `POST /submitModel` 入参 `content`，返回 `resultData`、`confidence`、`advice`、`similarCases` |
| FR-07 | 多模型预测 | `POST /api/v1/predict` 支持 `model=bert|textcnn|ensemble`，默认 `ensemble` |
| FR-08 | 预测结果结构 | 统一返回 `{disease, confidence, probabilities, model}` |
| FR-09 | 旧接口兼容 | `/submitModel` 保留原有字段并追加新字段，不破坏前端 |

### 4.3 数据管理

| 编号 | 需求 | 说明 |
|---|---|---|
| FR-10 | 数据统计 | `GET /data/summary` 返回总量、今日更新、活跃数据源 |
| FR-11 | 数据源管理 | `GET /data/sources`、`POST /data/sources/{code}/toggle`、`POST /data/sources/{code}/run` |
| FR-12 | 导入模板 | `GET /data/import/template?type=excel|csv` |
| FR-13 | 数据导入 | `POST /data/import`，校验列结构与必填字段 |
| FR-14 | 数据导出 | `GET /data/export` |
| FR-15 | 版本列表 | `GET /data/versions` 返回最近 50 条版本记录 |
| FR-16 | 版本回滚 | `POST /data/versions/{id}/rollback` 使用快照恢复 `cases` |

### 4.4 数据实时同步（新增）

| 编号 | 需求 | 说明 |
|---|---|---|
| FR-17 | 增量去重 | 使用 SHA-256 对业务字段计算 `content_hash`，唯一索引保证幂等 |
| FR-18 | 增量写入 | `INSERT ... ON DUPLICATE KEY UPDATE` 实现 upsert |
| FR-19 | 批次记录 | 每次同步写入 `sync_batches`（插入/更新/跳过/状态/耗时/错误） |
| FR-20 | 同步日志 | 关键步骤写入 `sync_logs`（级别、消息、批次号） |
| FR-21 | 定时策略 | 每 5 分钟增量同步，每日 2:00 全量对账 |
| FR-22 | 失败重试 | 失败按 1/5/15 分钟指数退避重试，最多 3 次 |
| FR-23 | 批次查询 | `GET /api/v1/data/batches?limit=20` |
| FR-24 | 日志查询 | `GET /api/v1/data/logs?batch_id=` |
| FR-25 | 手动同步 | `POST /api/v1/data/sync` |
| FR-26 | 全量对账 | `POST /api/v1/data/reconcile` |
| FR-27 | 健康检查 | `GET /api/v1/data/health` 返回各数据源新鲜度与成功率 |
| FR-28 | 事件发布 | 同步成功后服务端广播 `data.updated {batchId, inserted, updated, total, updatedAt}` |
| FR-29 | 调度管理 | 支持查看、暂停、恢复、立即执行调度任务 |

### 4.5 报告模板与生成

| 编号 | 需求 | 说明 |
|---|---|---|
| FR-30 | 模板列表 | `GET /templates` |
| FR-31 | 模板保存 | `POST /templates/save` |
| FR-32 | 模板状态流转 | `POST /templates/{id}/publish`、`POST /templates/{id}/offline`、`DELETE /templates/{id}` |
| FR-33 | 报告生成 | `POST /reports/generate` |
| FR-34 | 报告导出 | `POST /reports/export`（Word/PDF） |
| FR-35 | AI 摘要 | `POST /ai/report` 生成报告摘要，LLM 不可用时降级 |

### 4.6 大模型分析助手（新增）

| 编号 | 需求 | 说明 |
|---|---|---|
| FR-36 | 流式对话 | Socket.IO `/ws/chat`，服务端 `delta` 流式片段 |
| FR-37 | 会话持久化 | `chat_sessions`、`chat_messages` 表，保留 30 天 |
| FR-38 | 上下文携带 | 发送 `join` 时携带 `{dateRange, disease, gender}` |
| FR-39 | 工具调用 | `query_cases_stats`、`top_hospitals`、`trend_by_month`、`find_similar_cases` |
| FR-40 | 图表返回 | 服务端返回 `chart {spec}`，前端渲染 ECharts |
| FR-41 | 停止生成 | 客户端 `stop` 取消当前流式输出 |
| FR-42 | 安全限制 | 只读 SQL、表白名单、`LIMIT 200`、5s 超时、按 IP/session 限流 |

### 4.7 模型评估与对比（新增）

| 编号 | 需求 | 说明 |
|---|---|---|
| FR-43 | 多模型矩阵 | Baseline（TF-IDF+LinearSVC/RF）、TextCNN、BERT、Ensemble |
| FR-44 | 评估指标 | 5 折交叉验证，accuracy、macro-F1、各类别 P/R/F1、混淆矩阵、推理延迟 |
| FR-45 | 模型版本 | 指标写入 `model_versions`、`model_metrics`，文件存 `machine/registry/<name>/<version>/` |
| FR-46 | 自动上线 | 新模型 macro-F1 超过线上模型 1% 才上线 |
| FR-47 | 定时重训练 | 每周日 3:00 重训练并推送 `model.trained` 事件 |

### 4.8 接口清单

| 方法 | 路径 | 类型 | 说明 |
|---|---|---|---|
| GET | `/` | 现有 | 健康探测 |
| GET/POST | `/getHomeData` | 现有 | 首页统计 |
| GET/POST | `/submitModel` | 现有 | BERT 预测 |
| GET/POST | `/tableData` | 现有 | 病例表格 |
| GET | `/data/summary` | 现有 | 数据统计 |
| GET | `/data/sources` | 现有 | 数据源列表 |
| POST | `/data/sources/{code}/toggle` | 现有 | 启停数据源 |
| POST | `/data/sources/{code}/run` | 现有 | 手动爬取 |
| GET | `/data/import/template` | 现有 | 导入模板 |
| POST | `/data/import` | 现有 | 数据导入 |
| GET | `/data/export` | 现有 | 数据导出 |
| GET | `/data/versions` | 现有 | 版本列表 |
| POST | `/data/versions/{id}/rollback` | 现有 | 版本回滚 |
| GET | `/templates` | 现有 | 模板列表 |
| POST | `/templates/save` | 现有 | 保存模板 |
| POST | `/templates/{id}/publish` | 现有 | 发布模板 |
| POST | `/templates/{id}/offline` | 现有 | 下线模板 |
| DELETE | `/templates/{id}` | 现有 | 删除模板 |
| POST | `/reports/generate` | 现有 | 生成报告 |
| POST | `/reports/export` | 现有 | 导出报告 |
| POST | `/ai/report` | 现有 | AI 报告摘要 |
| GET | `/api/v1/data/batches` | 新增 | 同步批次 |
| GET | `/api/v1/data/logs` | 新增 | 同步日志 |
| POST | `/api/v1/data/sync` | 新增 | 手动增量同步 |
| POST | `/api/v1/data/reconcile` | 新增 | 全量对账 |
| GET | `/api/v1/data/health` | 新增 | 数据健康度 |
| POST | `/api/v1/predict` | 新增 | 多模型预测 |
| GET | `/api/v1/models` | 新增 | 模型版本列表 |
| POST | `/api/v1/models/{id}/online` | 新增 | 设为线上模型 |
| POST | `/internal/data-changed` | 新增 | 同步完成内部回调（Token） |

> 响应统一结构：`{"message": "success|error", "code": 200, "data": {...}}`。

---

## 5. 非功能需求

| 编号 | 类别 | 指标 |
|---|---|---|
| NFR-01 | 性能 | 接口 P95 响应时间 < 2s |
| NFR-02 | 性能 | 数据更新到前端可见 < 10s |
| NFR-03 | 性能 | WebSocket 首字返回 < 2s |
| NFR-04 | 性能 | CPU 单条模型推理 < 1s |
| NFR-05 | 可靠性 | 同步任务失败自动重试 3 次（1/5/15 分钟退避） |
| NFR-06 | 可靠性 | WebSocket 断线自动重连，降级为 30s 轮询 |
| NFR-07 | 可用性 | DeepSeek 不可用时降级为本地 BERT/规则回复 |
| NFR-08 | 安全 | API Key 仅存 `.env`，不入库不提交 |
| NFR-09 | 安全 | LLM 不生成裸 SQL，后端执行参数化只读查询 |
| NFR-10 | 安全 | 内部回调 Token 校验，LLM 接口按 IP/session 限流 |
| NFR-11 | 数据 | 对话历史保留 30 天，定时清理 |
| NFR-12 | 可维护性 | Controller 不含 SQL，Service 不依赖 Flask 上下文 |
| NFR-13 | 兼容性 | 旧接口路径与字段保持不变 |
| NFR-14 | 可观测性 | 同步批次、日志、健康度可查询；失败可重试 |

---

## 6. 数据需求

核心数据实体：

- `cases`：病例主表，现有 13 个业务字段；扩展 `content_hash`、`source_code`、`batch_id`、`updated_at`。
- `data_sources`：数据源配置（现有）。
- `data_versions`、`cases_snapshot`：数据版本与快照（现有）。
- `sync_batches`、`sync_logs`：同步批次与日志（新增）。
- `chat_sessions`、`chat_messages`：对话会话与消息（新增）。
- `model_versions`、`model_metrics`：模型版本与指标（新增）。

详细字段定义见 `docs/design.md` 第 6 节与 `docs/uml/er.puml`。

---

## 7. 验收标准

| 验收项 | 通过条件 | 对应 UML |
|---|---|---|
| 需求分析与设计 | `docs/SRS.md`、`docs/design.md`、8 张 PlantUML 图齐全且可渲染 | 全部 |
| 数据实时更新 | 触发同步后 10s 内大屏新增数据；批次与日志可查；失败可重试 | sequence-sync、er |
| 新增子界面 | 数据监控中心、模型中心、AI 分析助手 3 个路由可访问 | use-case、component |
| 高内聚松耦合 | 分层目录 + 模式清单；Controller 无 SQL，Service 无 Flask 依赖 | class、component |
| 大模型 WebSocket 子界面 | 流式对话、上下文、持久化、工具查库、图表输出 | sequence-chat |
| 先进 ML 算法 | TextCNN/BiLSTM + BERT 集成；指标对比与模型版本可切换 | class、state-template |
| 非功能指标 | 满足 NFR-01 ~ NFR-14 中可测项 | deployment |

---

## 8. 需求追踪矩阵

| 需求组 | 主要用例 | 主要接口 | 对应 UML |
|---|---|---|---|
| FR-01 ~ FR-05 大屏 | UC-01、UC-02 | `/getHomeData`、`/tableData`、`/ws/data` | component、sequence-sync |
| FR-06 ~ FR-09 预测 | UC-03、UC-04 | `/submitModel`、`/api/v1/predict` | class |
| FR-10 ~ FR-16 数据管理 | UC-06、UC-10 | `/data/*` | use-case |
| FR-17 ~ FR-29 实时同步 | UC-07 ~ UC-09、UC-12 | `/api/v1/data/*`、`/internal/*` | sequence-sync、er |
| FR-30 ~ FR-35 报告 | UC-11 相关 | `/templates/*`、`/reports/*` | state-template |
| FR-36 ~ FR-42 AI 助手 | UC-14 ~ UC-16 | `/ws/chat` | sequence-chat |
| FR-43 ~ FR-47 模型评估 | UC-05、UC-11 | `/api/v1/models/*` | class、state-template |
