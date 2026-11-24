<template>
  <div class="data-center">
    <!-- 顶部工具栏 -->
    <div class="dc-toolbar">
      <div class="dc-title">
        <span class="dc-title-bar"></span>
        <div>
          <h2>数据源与同步监控中心</h2>
          <p>实时查看数据新鲜度、同步批次、字段完整度与数据分布</p>
        </div>
      </div>
      <div class="dc-actions">
        <span :class="['conn-badge', socketConnected ? 'online' : 'offline']">
          <i class="dot"></i>
          {{ socketConnected ? "实时推送已连接" : "推送离线 · 轮询中" }}
        </span>
        <el-button
          size="mini"
          type="primary"
          :loading="syncing"
          @click="manualSync"
        >
          立即同步
        </el-button>
        <el-button size="mini" :loading="reconciling" @click="reconcile">
          全量对账
        </el-button>
        <el-button size="mini" :loading="loading" @click="loadAll(true)">
          刷新
        </el-button>
      </div>
    </div>

    <!-- KPI 卡片 -->
    <div class="kpi-row">
      <dv-border-box-8
        v-for="(item, index) in kpis"
        :key="index"
        class="kpi-box"
        :color="['#1c4f86', '#3f8ed6']"
      >
        <div class="kpi-inner">
          <div class="kpi-label">{{ item.label }}</div>
          <div class="kpi-value">{{ item.value }}</div>
          <div class="kpi-sub">{{ item.sub }}</div>
        </div>
      </dv-border-box-8>
    </div>

    <!-- 数据源 + 同步批次 -->
    <div class="main-grid">
      <dv-border-box-10 class="panel panel-sources">
        <div class="panel-inner">
          <div class="panel-head">
            <div>
              <span class="panel-title">数据源健康度</span>
              <span class="panel-sub">
                共 {{ overview.sources.length }} 个爬虫数据源
              </span>
            </div>
            <span class="panel-tip">启停后由后台调度统一生效</span>
          </div>

          <div class="table-scroll source-scroll">
            <table class="dc-table">
              <thead>
                <tr>
                  <th style="width: 24%">数据源</th>
                  <th style="width: 12%">状态</th>
                  <th style="width: 18%">最近成功</th>
                  <th style="width: 10%">本次增量</th>
                  <th style="width: 10%">累计</th>
                  <th style="width: 26%">操作</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="source in overview.sources" :key="source.id">
                  <td>
                    <div class="source-name">{{ source.name }}</div>
                    <div class="source-meta">{{ source.disease }}</div>
                  </td>
                  <td>
                    <span
                      :class="[
                        'status-pill',
                        !source.enabled
                          ? 'disabled'
                          : source.status === 'running'
                          ? 'running'
                          : source.status === 'error'
                          ? 'error'
                          : 'ok',
                      ]"
                    >
                      {{ source.enabled ? source.statusLabel : "已停用" }}
                    </span>
                  </td>
                  <td>
                    <div class="time-main">
                      {{ source.lastSuccessAt || "从未成功" }}
                    </div>
                    <div class="time-sub">
                      {{ source.freshnessHuman }}
                    </div>
                  </td>
                  <td class="num">{{ source.lastDelta }}</td>
                  <td class="num">{{ source.totalRecords }}</td>
                  <td>
                    <button
                      class="mini-btn"
                      :class="source.enabled ? 'danger' : 'primary'"
                      @click="toggleSource(source)"
                    >
                      {{ source.enabled ? "停用" : "启用" }}
                    </button>
                    <button
                      class="mini-btn ghost"
                      :disabled="!source.enabled || runningCode === source.code"
                      @click="runSource(source)"
                    >
                      {{ runningCode === source.code ? "采集中..." : "立即采集" }}
                    </button>
                  </td>
                </tr>
                <tr v-if="!overview.sources.length">
                  <td colspan="6" class="empty-cell">暂无数据源配置</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </dv-border-box-10>

      <dv-border-box-10 class="panel panel-batches">
        <div class="panel-inner">
          <div class="panel-head">
            <div>
              <span class="panel-title">同步批次</span>
              <span class="panel-sub">
                成功率 {{ overview.health.successRate || 0 }}%
              </span>
            </div>
            <span class="panel-tip">点击批次查看日志</span>
          </div>

          <div class="table-scroll batch-scroll">
            <table class="dc-table batch-table">
              <thead>
                <tr>
                  <th style="width: 12%">批次</th>
                  <th style="width: 14%">状态</th>
                  <th style="width: 12%">新增</th>
                  <th style="width: 12%">更新</th>
                  <th style="width: 12%">跳过</th>
                  <th style="width: 38%">开始时间</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="batch in overview.batches"
                  :key="batch.id"
                  class="clickable"
                  @click="openLogs(batch)"
                >
                  <td>#{{ batch.id }}</td>
                  <td>
                    <span :class="['status-pill', batch.status]">
                      {{ batch.statusLabel }}
                    </span>
                  </td>
                  <td class="num">{{ batch.inserted }}</td>
                  <td class="num">{{ batch.updated }}</td>
                  <td class="num">{{ batch.skipped }}</td>
                  <td>
                    <div class="time-main">{{ batch.startedAt }}</div>
                    <div class="time-sub">
                      耗时 {{ batch.durationSeconds === null ? "-" : batch.durationSeconds + "s" }}
                    </div>
                  </td>
                </tr>
                <tr v-if="!overview.batches.length">
                  <td colspan="6" class="empty-cell">暂无同步批次记录</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </dv-border-box-10>
    </div>

    <!-- 分布与完整度 -->
    <div class="chart-grid">
      <dv-border-box-12 class="panel panel-chart">
        <div class="panel-inner">
          <div class="panel-head">
            <span class="panel-title">疾病类型分布 Top 10</span>
            <span class="panel-tip">按病例数排序</span>
          </div>
          <div ref="diseaseChart" class="chart-body"></div>
        </div>
      </dv-border-box-12>

      <dv-border-box-12 class="panel panel-fields">
        <div class="panel-inner">
          <div class="panel-head">
            <span class="panel-title">字段完整度</span>
            <span class="panel-tip">非空字段占比</span>
          </div>
          <div class="field-list">
            <div
              v-for="field in overview.fields"
              :key="field.field"
              class="field-item"
            >
              <div class="field-top">
                <span class="field-label">{{ field.label }}</span>
                <span class="field-value">
                  {{ field.filled }} / {{ field.total }}（{{ field.rate }}%）
                </span>
              </div>
              <div class="field-track">
                <div
                  class="field-fill"
                  :style="{ width: field.rate + '%' }"
                  :class="{ warn: field.rate < 60 }"
                ></div>
              </div>
            </div>
          </div>
        </div>
      </dv-border-box-12>
    </div>

    <div class="mini-chart-grid">
      <dv-border-box-13 class="panel panel-small">
        <div class="panel-inner">
          <div class="panel-head"><span class="panel-title">性别构成</span></div>
          <div ref="genderChart" class="chart-body small"></div>
        </div>
      </dv-border-box-13>

      <dv-border-box-13 class="panel panel-small">
        <div class="panel-inner">
          <div class="panel-head"><span class="panel-title">年龄分布</span></div>
          <div ref="ageChart" class="chart-body small"></div>
        </div>
      </dv-border-box-13>

      <dv-border-box-13 class="panel panel-small month-panel">
        <div class="panel-inner">
          <div class="panel-head">
            <span class="panel-title">月度病例趋势</span>
            <span class="panel-tip">按就诊月份统计</span>
          </div>
          <div ref="monthChart" class="chart-body small"></div>
        </div>
      </dv-border-box-13>
    </div>

    <!-- 日志抽屉 -->
    <el-drawer
      title="同步日志"
      :visible.sync="logDrawer"
      size="46%"
      :append-to-body="true"
      custom-class="dc-log-drawer"
    >
      <div class="log-header" v-if="activeBatch">
        <span>批次 #{{ activeBatch.id }}</span>
        <span :class="['status-pill', activeBatch.status]">
          {{ activeBatch.statusLabel }}
        </span>
        <span class="log-meta">
          新增 {{ activeBatch.inserted }} / 更新 {{ activeBatch.updated }} / 跳过
          {{ activeBatch.skipped }}
        </span>
        <span class="log-meta">{{ activeBatch.startedAt }}</span>
        <el-button
          v-if="activeBatch.status === 'failed'"
          size="mini"
          type="warning"
          :loading="syncing"
          @click="manualSync"
        >
          重试同步
        </el-button>
      </div>
      <div v-if="activeBatch && activeBatch.errorMessage" class="log-error">
        错误信息：{{ activeBatch.errorMessage }}
      </div>
      <div v-loading="logLoading" class="log-list">
        <div v-for="log in batchLogs" :key="log.id" class="log-item">
          <span class="log-time">{{ log.createdAt }}</span>
          <span :class="['log-level', log.level.toLowerCase()]">
            {{ log.level }}
          </span>
          <span class="log-message">{{ log.message }}</span>
        </div>
        <div v-if="!batchLogs.length && !logLoading" class="log-empty">
          该批次暂无日志
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<script>
import { io } from "socket.io-client";
import {
  fetchMonitorOverview,
  toggleDataSource,
  runDataSource,
} from "@/api/monitor";
import {
  triggerSync,
  triggerReconcile,
  fetchSyncLogs,
} from "@/api/data";

export default {
  name: "DataCenter",
  data() {
    return {
      loading: false,
      syncing: false,
      reconciling: false,
      runningCode: "",
      overview: {
        freshness: {},
        summary: {},
        health: {},
        sources: [],
        fields: [],
        distributions: { disease: [], gender: [], age: [], month: [], hospital: [] },
        batches: [],
        logs: [],
        versions: [],
      },
      socket: null,
      socketConnected: false,
      pollTimer: null,
      logDrawer: false,
      logLoading: false,
      activeBatch: null,
      batchLogs: [],
      charts: {
        disease: null,
        gender: null,
        age: null,
        month: null,
      },
      palette: ["#4fa3ff", "#37e2c4", "#f7b84b", "#ff7a8a", "#9b8cff", "#41d1ff"],
    };
  },
  computed: {
    kpis() {
      const summary = this.overview.summary || {};
      const freshness = this.overview.freshness || {};
      const health = this.overview.health || {};
      return [
        {
          label: "病例总量",
          value: this.formatNumber(summary.totalCases || 0),
          sub: `${summary.diseaseKinds || 0} 类疾病 · ${summary.hospitalKinds || 0} 家医院`,
        },
        {
          label: "今日新增",
          value: this.formatNumber(summary.todayNew || 0),
          sub: `最近批次新增 ${freshness.inserted || 0} · 更新 ${freshness.updated || 0}`,
        },
        {
          label: "最近同步",
          value: freshness.human || "未知",
          sub: freshness.lastSyncAt || "暂无同步记录",
        },
        {
          label: "同步成功率",
          value: `${health.successRate || 0}%`,
          sub: `成功 ${health.successBatches || 0} · 失败 ${health.failedBatches || 0}`,
        },
        {
          label: "活跃数据源",
          value: `${summary.activeSources || 0} / ${summary.sourceCount || 0}`,
          sub: "最近 24 小时成功采集",
        },
      ];
    },
  },
  async mounted() {
    await this.loadAll(false);
    this.connectSocket();
    this.pollTimer = setInterval(() => this.loadAll(false), 15000);
    window.addEventListener("resize", this.resizeCharts);
  },
  beforeDestroy() {
    if (this.pollTimer) {
      clearInterval(this.pollTimer);
      this.pollTimer = null;
    }
    if (this.socket) {
      this.socket.disconnect();
      this.socket = null;
    }
    window.removeEventListener("resize", this.resizeCharts);
    Object.keys(this.charts).forEach((key) => {
      if (this.charts[key]) {
        this.charts[key].dispose();
        this.charts[key] = null;
      }
    });
  },
  methods: {
    formatNumber(value) {
      const n = Number(value || 0);
      return n.toLocaleString("zh-CN");
    },
    async loadAll(showLoading) {
      if (showLoading) this.loading = true;
      try {
        const res = await fetchMonitorOverview();
        if (res.code === 200 && res.data) {
          this.overview = res.data;
          this.$nextTick(() => this.renderCharts());
        } else {
          this.$message.error(res.message || "监控数据加载失败");
        }
      } catch (err) {
        this.$message.error(this.errorText(err, "监控数据加载失败"));
      } finally {
        this.loading = false;
      }
    },
    connectSocket() {
      try {
        this.socket = io("http://localhost:5001/ws/data", {
          transports: ["websocket", "polling"],
          reconnection: true,
          reconnectionDelay: 2000,
          reconnectionAttempts: Infinity,
        });
        this.socket.on("connect", () => {
          this.socketConnected = true;
        });
        this.socket.on("disconnect", () => {
          this.socketConnected = false;
        });
        this.socket.on("connect_error", () => {
          this.socketConnected = false;
        });
        this.socket.on("data.updated", (payload) => {
          const data = payload || {};
          this.$message.success(
            `数据已更新：新增 ${data.inserted || 0} 条，更新 ${data.updated || 0} 条`
          );
          this.loadAll(false);
        });
      } catch (err) {
        this.socketConnected = false;
      }
    },
    async manualSync() {
      this.syncing = true;
      try {
        const res = await triggerSync({});
        if (res.code === 200 && res.data) {
          this.$message.success(
            `同步完成：新增 ${res.data.inserted} 条，更新 ${res.data.updated} 条，跳过 ${res.data.skipped} 条`
          );
          await this.loadAll(false);
        } else {
          this.$message.error(this.errorText(res, "同步失败"));
        }
      } catch (err) {
        this.$message.error(this.errorText(err, "同步失败"));
      } finally {
        this.syncing = false;
      }
    },
    async reconcile() {
      this.reconciling = true;
      try {
        const res = await triggerReconcile();
        if (res.code === 200 && res.data) {
          const d = res.data;
          this.$message({
            type: d.consistent ? "success" : "warning",
            message: `对账完成：CSV ${d.csvCount} 条 / 库内 ${d.dbCount} 条，缺失 ${d.missing} 条，历史多出 ${d.extra} 条`,
          });
        } else {
          this.$message.error(this.errorText(res, "对账失败"));
        }
      } catch (err) {
        this.$message.error(this.errorText(err, "对账失败"));
      } finally {
        this.reconciling = false;
      }
    },
    async toggleSource(source) {
      try {
        const res = await toggleDataSource(source.code, !source.enabled);
        if (res.code === 200) {
          this.$message.success(
            `${source.name} 已${source.enabled ? "停用" : "启用"}`
          );
          await this.loadAll(false);
        } else {
          this.$message.error(this.errorText(res, "操作失败"));
        }
      } catch (err) {
        this.$message.error(this.errorText(err, "操作失败"));
      }
    },
    async runSource(source) {
      try {
        await this.$confirm(
          `确认立即采集「${source.name}」？采集过程可能需要数分钟。`,
          "手动采集",
          { confirmButtonText: "开始采集", cancelButtonText: "取消", type: "warning" }
        );
      } catch (err) {
        return;
      }
      this.runningCode = source.code;
      try {
        const res = await runDataSource(source.code, 3);
        if (res.code === 200 && res.data) {
          if (res.data.success) {
            this.$message.success(
              `采集完成：新增 ${res.data.delta} 条病例`
            );
          } else {
            this.$message.warning(
              `采集结束但未成功：${res.data.error || "请检查爬虫环境"}`
            );
          }
          await this.loadAll(false);
        } else {
          this.$message.error(this.errorText(res, "采集失败"));
        }
      } catch (err) {
        this.$message.error(this.errorText(err, "采集失败"));
      } finally {
        this.runningCode = "";
      }
    },
    async openLogs(batch) {
      this.activeBatch = batch;
      this.batchLogs = [];
      this.logDrawer = true;
      this.logLoading = true;
      try {
        const res = await fetchSyncLogs(batch.id);
        if (res.code === 200) {
          this.batchLogs = res.data || [];
        }
      } catch (err) {
        this.$message.error(this.errorText(err, "日志加载失败"));
      } finally {
        this.logLoading = false;
      }
    },
    errorText(err, fallback) {
      if (typeof err === "string") return err;
      if (err && err.data && err.data.error) return err.data.error;
      if (err && err.response && err.response.data) {
        const body = err.response.data;
        if (body.data && body.data.error) return body.data.error;
        if (body.message) return body.message;
      }
      return (err && err.message) || fallback;
    },
    resizeCharts() {
      Object.keys(this.charts).forEach((key) => {
        if (this.charts[key]) this.charts[key].resize();
      });
    },
    renderCharts() {
      const distributions = this.overview.distributions || {};
      this.renderDisease(distributions.disease || []);
      this.renderGender(distributions.gender || []);
      this.renderAge(distributions.age || []);
      this.renderMonth(distributions.month || []);
    },
    baseGrid() {
      return {
        left: 10,
        right: 18,
        top: 18,
        bottom: 10,
        containLabel: true,
      };
    },
    axisStyle() {
      return {
        axisLine: { lineStyle: { color: "#2b4a70" } },
        axisLabel: { color: "#8fb6dd", fontSize: 11 },
        splitLine: { lineStyle: { color: "rgba(80, 140, 220, 0.10)" } },
      };
    },
    ensureChart(key, refName) {
      const el = this.$refs[refName];
      if (!el) return null;
      if (!this.charts[key]) {
        this.charts[key] = this.$echarts.init(el);
      }
      return this.charts[key];
    },
    renderDisease(data) {
      const chart = this.ensureChart("disease", "diseaseChart");
      if (!chart) return;
      const names = data.map((item) => item.name).reverse();
      const values = data.map((item) => item.value).reverse();
      chart.setOption(
        {
          backgroundColor: "transparent",
          tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
          grid: { left: 8, right: 48, top: 12, bottom: 8, containLabel: true },
          xAxis: Object.assign({ type: "value" }, this.axisStyle()),
          yAxis: Object.assign(
            { type: "category", data: names },
            this.axisStyle(),
            { axisLabel: { color: "#c7ddf5", fontSize: 11 } }
          ),
          series: [
            {
              type: "bar",
              data: values,
              barWidth: 12,
              itemStyle: {
                borderRadius: [0, 8, 8, 0],
                color: new this.$echarts.graphic.LinearGradient(0, 0, 1, 0, [
                  { offset: 0, color: "#1f66c9" },
                  { offset: 1, color: "#4fd1ff" },
                ]),
              },
              label: {
                show: true,
                position: "right",
                color: "#d6e9ff",
                fontSize: 11,
              },
            },
          ],
        },
        true
      );
    },
    renderGender(data) {
      const chart = this.ensureChart("gender", "genderChart");
      if (!chart) return;
      chart.setOption(
        {
          backgroundColor: "transparent",
          tooltip: { trigger: "item", formatter: "{b}: {c} ({d}%)" },
          color: this.palette,
          series: [
            {
              type: "pie",
              radius: ["42%", "66%"],
              center: ["50%", "54%"],
              itemStyle: { borderColor: "#071a33", borderWidth: 2 },
              label: { color: "#bcd9f5", fontSize: 11, formatter: "{b}\n{c} 例" },
              data,
            },
          ],
        },
        true
      );
    },
    renderAge(data) {
      const chart = this.ensureChart("age", "ageChart");
      if (!chart) return;
      chart.setOption(
        {
          backgroundColor: "transparent",
          tooltip: { trigger: "axis" },
          grid: this.baseGrid(),
          xAxis: Object.assign(
            { type: "category", data: data.map((item) => item.name) },
            this.axisStyle()
          ),
          yAxis: Object.assign({ type: "value" }, this.axisStyle()),
          series: [
            {
              type: "bar",
              barWidth: 18,
              data: data.map((item) => item.value),
              itemStyle: {
                borderRadius: [6, 6, 0, 0],
                color: new this.$echarts.graphic.LinearGradient(0, 0, 0, 1, [
                  { offset: 0, color: "#37e2c4" },
                  { offset: 1, color: "#1f66c9" },
                ]),
              },
            },
          ],
        },
        true
      );
    },
    renderMonth(data) {
      const chart = this.ensureChart("month", "monthChart");
      if (!chart) return;
      chart.setOption(
        {
          backgroundColor: "transparent",
          tooltip: { trigger: "axis" },
          grid: this.baseGrid(),
          xAxis: Object.assign(
            { type: "category", boundaryGap: false, data: data.map((item) => item.name) },
            this.axisStyle()
          ),
          yAxis: Object.assign({ type: "value" }, this.axisStyle()),
          series: [
            {
              type: "line",
              smooth: true,
              symbolSize: 7,
              data: data.map((item) => item.value),
              lineStyle: { width: 3, color: "#4fa3ff" },
              itemStyle: { color: "#4fd1ff" },
              areaStyle: {
                color: new this.$echarts.graphic.LinearGradient(0, 0, 0, 1, [
                  { offset: 0, color: "rgba(79, 163, 255, 0.45)" },
                  { offset: 1, color: "rgba(79, 163, 255, 0.02)" },
                ]),
              },
            },
          ],
        },
        true
      );
    },
  },
};
</script>

<style lang="less" scoped>
.data-center {
  color: #cfe4ff;
  padding: 2px 6px 18px;
}

.dc-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
  .dc-title {
    display: flex;
    align-items: center;
    .dc-title-bar {
      width: 4px;
      height: 38px;
      border-radius: 4px;
      margin-right: 12px;
      background: linear-gradient(180deg, #4fd1ff, #1f66c9);
      box-shadow: 0 0 12px rgba(79, 209, 255, 0.6);
    }
    h2 {
      font-size: 20px;
      color: #eaf4ff;
      letter-spacing: 1px;
    }
    p {
      margin-top: 4px;
      font-size: 12px;
      color: #7fa8d4;
    }
  }
  .dc-actions {
    display: flex;
    align-items: center;
    gap: 10px;
  }
}

.conn-badge {
  display: inline-flex;
  align-items: center;
  font-size: 12px;
  padding: 5px 12px;
  border-radius: 14px;
  border: 1px solid rgba(79, 163, 255, 0.35);
  color: #8fb6dd;
  background: rgba(20, 46, 80, 0.55);
  .dot {
    display: inline-block;
    width: 7px;
    height: 7px;
    border-radius: 50%;
    margin-right: 6px;
    background: #6b7f98;
  }
  &.online {
    color: #37e2c4;
    border-color: rgba(55, 226, 196, 0.4);
    .dot {
      background: #37e2c4;
      box-shadow: 0 0 8px #37e2c4;
    }
  }
}

.kpi-row {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 12px;
}

.kpi-box {
  height: 104px;
  .kpi-inner {
    height: 100%;
    padding: 12px 18px;
    box-sizing: border-box;
    display: flex;
    flex-direction: column;
    justify-content: center;
  }
  .kpi-label {
    font-size: 12px;
    color: #7fa8d4;
    letter-spacing: 1px;
  }
  .kpi-value {
    margin: 6px 0 4px;
    font-size: 24px;
    font-weight: 600;
    color: #4fd1ff;
    text-shadow: 0 0 12px rgba(79, 209, 255, 0.35);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .kpi-sub {
    font-size: 11px;
    color: #6f90b5;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
}

.main-grid {
  display: grid;
  grid-template-columns: 1.15fr 1fr;
  gap: 12px;
  margin-top: 12px;
}

.chart-grid {
  display: grid;
  grid-template-columns: 1.1fr 1fr;
  gap: 12px;
  margin-top: 12px;
}

.mini-chart-grid {
  display: grid;
  grid-template-columns: 0.9fr 1fr 1.6fr;
  gap: 12px;
  margin-top: 12px;
}

.panel {
  height: 340px;
  &.panel-small {
    height: 250px;
  }
  .panel-inner {
    height: 100%;
    padding: 14px 18px;
    box-sizing: border-box;
    display: flex;
    flex-direction: column;
  }
}

.panel-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  margin-bottom: 10px;
  .panel-title {
    font-size: 15px;
    color: #e3f1ff;
    letter-spacing: 0.5px;
    &::before {
      content: "";
      display: inline-block;
      width: 3px;
      height: 13px;
      margin-right: 8px;
      background: #4fd1ff;
      vertical-align: -2px;
    }
  }
  .panel-sub {
    margin-left: 10px;
    font-size: 12px;
    color: #7fa8d4;
  }
  .panel-tip {
    font-size: 12px;
    color: #6f90b5;
  }
}

.table-scroll {
  flex: 1;
  overflow: auto;
  &::-webkit-scrollbar {
    width: 6px;
  }
  &::-webkit-scrollbar-thumb {
    background: rgba(79, 163, 255, 0.35);
    border-radius: 3px;
  }
}

.dc-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
  th {
    text-align: left;
    color: #7fa8d4;
    font-weight: 500;
    padding: 8px 6px;
    border-bottom: 1px solid rgba(79, 163, 255, 0.2);
    position: sticky;
    top: 0;
    background: #071a33;
    z-index: 2;
  }
  td {
    padding: 8px 6px;
    border-bottom: 1px dashed rgba(79, 163, 255, 0.12);
    color: #c7ddf5;
    vertical-align: middle;
  }
  tr.clickable {
    cursor: pointer;
    &:hover td {
      background: rgba(79, 163, 255, 0.08);
    }
  }
  .num {
    color: #4fd1ff;
    font-weight: 600;
  }
  .time-main {
    color: #bcd9f5;
    white-space: nowrap;
  }
  .time-sub {
    color: #6f90b5;
    font-size: 11px;
    margin-top: 2px;
  }
  .source-name {
    color: #e3f1ff;
  }
  .source-meta {
    color: #6f90b5;
    font-size: 11px;
    margin-top: 2px;
  }
  .empty-cell {
    text-align: center;
    color: #6f90b5;
    padding: 26px 0;
  }
}

.status-pill {
  display: inline-block;
  padding: 1px 9px;
  border-radius: 10px;
  font-size: 11px;
  line-height: 18px;
  border: 1px solid transparent;
  white-space: nowrap;
  &.ok,
  &.success {
    color: #37e2c4;
    border-color: rgba(55, 226, 196, 0.4);
    background: rgba(55, 226, 196, 0.08);
  }
  &.running {
    color: #f7b84b;
    border-color: rgba(247, 184, 75, 0.4);
    background: rgba(247, 184, 75, 0.08);
  }
  &.error,
  &.failed {
    color: #ff7a8a;
    border-color: rgba(255, 122, 138, 0.4);
    background: rgba(255, 122, 138, 0.08);
  }
  &.disabled {
    color: #8b9bb0;
    border-color: rgba(139, 155, 176, 0.35);
    background: rgba(139, 155, 176, 0.08);
  }
}

.mini-btn {
  padding: 2px 10px;
  margin-right: 6px;
  font-size: 11px;
  border-radius: 10px;
  border: 1px solid rgba(79, 163, 255, 0.4);
  background: transparent;
  color: #8fc6ff;
  cursor: pointer;
  transition: all 0.2s;
  &:hover:not(:disabled) {
    background: rgba(79, 163, 255, 0.15);
  }
  &:disabled {
    opacity: 0.45;
    cursor: not-allowed;
  }
  &.danger {
    border-color: rgba(255, 122, 138, 0.45);
    color: #ff9aa6;
  }
  &.primary {
    border-color: rgba(55, 226, 196, 0.45);
    color: #37e2c4;
  }
  &.ghost {
    border-color: rgba(140, 170, 200, 0.35);
    color: #a9c3de;
  }
}

.field-list {
  flex: 1;
  overflow: auto;
  padding-right: 4px;
  &::-webkit-scrollbar {
    width: 6px;
  }
  &::-webkit-scrollbar-thumb {
    background: rgba(79, 163, 255, 0.35);
    border-radius: 3px;
  }
}
.field-item {
  margin-bottom: 8px;
  .field-top {
    display: flex;
    justify-content: space-between;
    font-size: 11px;
    margin-bottom: 4px;
  }
  .field-label {
    color: #bcd9f5;
  }
  .field-value {
    color: #7fa8d4;
  }
  .field-track {
    height: 6px;
    border-radius: 4px;
    background: rgba(79, 163, 255, 0.12);
    overflow: hidden;
  }
  .field-fill {
    height: 100%;
    border-radius: 4px;
    background: linear-gradient(90deg, #1f66c9, #4fd1ff);
    transition: width 0.4s ease;
    &.warn {
      background: linear-gradient(90deg, #a05a1f, #f7b84b);
    }
  }
}

.chart-body {
  flex: 1;
  min-height: 0;
  width: 100%;
  &.small {
    height: 100%;
  }
}

.log-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 0 4px 12px;
  border-bottom: 1px dashed rgba(79, 163, 255, 0.2);
  font-size: 12px;
  color: #bcd9f5;
  .log-meta {
    color: #7fa8d4;
  }
}
.log-error {
  margin: 12px 4px 0;
  padding: 8px 12px;
  border-radius: 6px;
  font-size: 12px;
  color: #ff9aa6;
  background: rgba(255, 122, 138, 0.08);
  border: 1px solid rgba(255, 122, 138, 0.25);
}
.log-list {
  margin-top: 8px;
  .log-item {
    display: flex;
    align-items: baseline;
    gap: 10px;
    padding: 7px 4px;
    border-bottom: 1px dashed rgba(79, 163, 255, 0.1);
    font-size: 12px;
  }
  .log-time {
    color: #6f90b5;
    white-space: nowrap;
    font-family: Consolas, Monaco, monospace;
  }
  .log-level {
    font-size: 10px;
    padding: 0 6px;
    border-radius: 8px;
    border: 1px solid rgba(79, 163, 255, 0.3);
    color: #8fc6ff;
    &.warn {
      color: #f7b84b;
      border-color: rgba(247, 184, 75, 0.35);
    }
    &.error {
      color: #ff7a8a;
      border-color: rgba(255, 122, 138, 0.35);
    }
  }
  .log-message {
    color: #c7ddf5;
    word-break: break-all;
  }
}
.log-empty {
  padding: 40px 0;
  text-align: center;
  color: #6f90b5;
  font-size: 12px;
}

@media (max-width: 1500px) {
  .kpi-value {
    font-size: 20px !important;
  }
  .main-grid {
    grid-template-columns: 1fr;
  }
  .chart-grid {
    grid-template-columns: 1fr;
  }
  .mini-chart-grid {
    grid-template-columns: 1fr 1fr;
    .month-panel {
      grid-column: span 2;
    }
  }
}
</style>

<style lang="less">
/* 日志抽屉挂载在 body 上，需用非 scoped 样式统一深色主题 */
.dc-log-drawer {
  background: #071a33;
  .el-drawer__header {
    color: #e3f1ff;
    margin-bottom: 10px;
    padding: 20px 20px 0;
  }
  .el-drawer__body {
    padding: 0 20px 20px;
    overflow: auto;
  }
}
</style>
