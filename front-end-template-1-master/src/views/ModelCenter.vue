<template>
  <div class="model-center">
    <div class="mc-toolbar">
      <div class="mc-title">
        <span class="mc-title-bar"></span>
        <div>
          <h2>模型评估与对比中心</h2>
          <p>查看模型版本、离线评估指标、混淆矩阵与各类别表现</p>
        </div>
      </div>
      <div class="mc-actions">
        <span :class="['artifact-badge', artifactReady ? 'ready' : 'missing']">
          <i class="dot"></i>
          {{ artifactReady ? "模型产物就绪" : "模型产物缺失" }}
        </span>
        <el-button
          size="mini"
          type="primary"
          :loading="evaluating"
          @click="evaluate"
        >
          重新评估
        </el-button>
        <el-button size="mini" :loading="loading" @click="loadOverview">
          刷新
        </el-button>
      </div>
    </div>

    <!-- KPI -->
    <div class="kpi-row">
      <dv-border-box-8
        v-for="(item, index) in kpis"
        :key="index"
        class="kpi-box"
        :color="['#1c4f86', '#3f8ed6']"
      >
        <div class="kpi-inner">
          <div class="kpi-label">{{ item.label }}</div>
          <div class="kpi-value" :class="{ highlight: item.highlight }">
            {{ item.value }}
          </div>
          <div class="kpi-sub">{{ item.sub }}</div>
        </div>
      </dv-border-box-8>
    </div>

    <div class="mc-grid main">
      <dv-border-box-10 class="panel confusion-panel">
        <div class="panel-inner">
          <div class="panel-head">
            <div>
              <span class="panel-title">混淆矩阵</span>
              <span class="panel-sub">
                行为真实类别，列为预测类别
              </span>
            </div>
            <span class="panel-tip">{{ selectedVersionLabel }}</span>
          </div>
          <div ref="confusionChart" class="chart-body"></div>
        </div>
      </dv-border-box-10>

      <dv-border-box-10 class="panel perclass-panel">
        <div class="panel-inner">
          <div class="panel-head">
            <div>
              <span class="panel-title">各类别指标</span>
              <span class="panel-sub">Precision / Recall / F1</span>
            </div>
          </div>
          <div ref="perClassChart" class="chart-body"></div>
        </div>
      </dv-border-box-10>
    </div>

    <div class="mc-grid">
      <dv-border-box-12 class="panel trend-panel">
        <div class="panel-inner">
          <div class="panel-head">
            <span class="panel-title">评估指标趋势</span>
            <span class="panel-tip">按评估版本先后排序</span>
          </div>
          <div ref="trendChart" class="chart-body"></div>
        </div>
      </dv-border-box-12>

      <dv-border-box-12 class="panel version-panel">
        <div class="panel-inner">
          <div class="panel-head">
            <div>
              <span class="panel-title">模型版本</span>
              <span class="panel-sub">
                线上 {{ onlineVersionLabel }}
              </span>
            </div>
            <span class="panel-tip">点击行查看详情</span>
          </div>
          <div class="table-scroll">
            <table class="mc-table">
              <thead>
                <tr>
                  <th style="width: 40%">版本</th>
                  <th style="width: 12%">状态</th>
                  <th style="width: 14%">准确率</th>
                  <th style="width: 14%">Macro-F1</th>
                  <th style="width: 20%">操作</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="version in overview.versions"
                  :key="version.id"
                  :class="['version-row', { active: selected && selected.id === version.id }]"
                  @click="selectVersion(version)"
                >
                  <td>
                    <div class="version-name" :title="version.version">
                      {{ version.version }}
                    </div>
                    <div class="version-meta">{{ version.trainedAt || "未知时间" }}</div>
                  </td>
                  <td>
                    <span
                      :class="['status-pill', version.isOnline ? 'online' : 'candidate']"
                    >
                      {{ version.isOnline ? "线上" : "候选" }}
                    </span>
                  </td>
                  <td class="num">{{ percent(version.accuracy) }}</td>
                  <td class="num">{{ percent(version.macroF1) }}</td>
                  <td>
                    <button
                      class="mini-btn ghost"
                      @click.stop="selectVersion(version)"
                    >
                      查看
                    </button>
                    <button
                      class="mini-btn primary"
                      :disabled="version.isOnline || switchingId === version.id"
                      @click.stop="setOnline(version)"
                    >
                      {{ switchingId === version.id ? "切换中..." : "设为线上" }}
                    </button>
                  </td>
                </tr>
                <tr v-if="!overview.versions.length">
                  <td colspan="5" class="empty-cell">
                    暂无模型版本，请点击“重新评估”生成第一条记录
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          <div class="model-status">
            <span>训练版本 {{ modelStatus.version || "-" }}</span>
            <span>训练准确率 {{ percent(modelStatus.accuracy) }}</span>
            <span>训练时间 {{ modelStatus.trainedAt || "-" }}</span>
            <span>样本 {{ modelStatus.samples || 0 }}</span>
          </div>
        </div>
      </dv-border-box-12>
    </div>
  </div>
</template>

<script>
import { fetchModelOverview, evaluateModel, fetchModelVersion, setOnlineModel } from "@/api/model";

export default {
  name: "ModelCenter",
  data() {
    return {
      loading: false,
      evaluating: false,
      switchingId: null,
      overview: {
        modelName: "random_forest",
        modelStatus: {},
        onlineId: null,
        activeId: null,
        active: null,
        versions: [],
        trend: [],
        artifacts: { ready: false, files: [] },
      },
      selected: null,
      charts: {
        confusion: null,
        perClass: null,
        trend: null,
      },
      palette: ["#4fa3ff", "#37e2c4", "#f7b84b", "#ff7a8a", "#9b8cff"],
    };
  },
  computed: {
    artifactReady() {
      return !!(this.overview.artifacts && this.overview.artifacts.ready);
    },
    modelStatus() {
      return this.overview.modelStatus || {};
    },
    onlineVersion() {
      return (this.overview.versions || []).find((v) => v.isOnline) || null;
    },
    onlineVersionLabel() {
      if (!this.onlineVersion) return "未设置";
      return `#${this.onlineVersion.id}`;
    },
    selectedVersionLabel() {
      if (!this.selected) return "暂无版本";
      return `版本 #${this.selected.id} · ${this.selected.isOnline ? "线上" : "候选"}`;
    },
    kpis() {
      const metrics = (this.selected && this.selected.metrics) || {};
      const evalSamples = metrics.evalSamples || 0;
      const skipped = metrics.skippedSamples || 0;
      const latency =
        metrics.latencyMs === null || metrics.latencyMs === undefined
          ? "-"
          : `${Number(metrics.latencyMs).toFixed(2)} ms`;
      return [
        {
          label: "当前查看版本",
          value: this.selected ? `#${this.selected.id}` : "-",
          sub: this.selected
            ? this.selected.isOnline
              ? "线上模型"
              : "候选版本"
            : "暂无评估记录",
        },
        {
          label: "准确率",
          value: this.percent(metrics.accuracy),
          sub: `加权 F1 ${this.percent(metrics.f1Weighted)}`,
          highlight: true,
        },
        {
          label: "Macro-F1",
          value: this.percent(metrics.macroF1),
          sub: `加权精确率 ${this.percent(metrics.precisionWeighted)}`,
        },
        {
          label: "评估样本",
          value: String(evalSamples),
          sub: `跳过 ${skipped} 条（类别未知）`,
        },
        {
          label: "单条推理",
          value: latency,
          sub: "CPU 离线评估",
        },
      ];
    },
  },
  async mounted() {
    await this.loadOverview();
    window.addEventListener("resize", this.resizeCharts);
  },
  beforeDestroy() {
    window.removeEventListener("resize", this.resizeCharts);
    Object.keys(this.charts).forEach((key) => {
      if (this.charts[key]) {
        this.charts[key].dispose();
        this.charts[key] = null;
      }
    });
  },
  methods: {
    percent(value) {
      if (value === null || value === undefined) return "-";
      return `${(Number(value) * 100).toFixed(2)}%`;
    },
    async loadOverview() {
      this.loading = true;
      try {
        const res = await fetchModelOverview();
        if (res.code !== 200 || !res.data) {
          this.$message.error(res.message || "模型总览加载失败");
          return;
        }
        this.overview = res.data;
        this.selected = res.data.active || null;
        this.$nextTick(() => this.renderCharts());
      } catch (err) {
        this.$message.error(this.errorText(err, "模型总览加载失败"));
      } finally {
        this.loading = false;
      }
    },
    async selectVersion(version) {
      if (!version) return;
      if (this.selected && this.selected.id === version.id && this.selected.metrics) {
        return;
      }
      try {
        const res = await fetchModelVersion(version.id);
        if (res.code === 200 && res.data) {
          this.selected = res.data;
          this.$nextTick(() => this.renderCharts());
        } else {
          this.$message.error(res.message || "版本详情加载失败");
        }
      } catch (err) {
        this.$message.error(this.errorText(err, "版本详情加载失败"));
      }
    },
    async evaluate() {
      try {
        await this.$confirm(
          "将使用当前 cases 数据重新评估线上模型，并写入一个新的模型版本，是否继续？",
          "重新评估",
          { confirmButtonText: "开始评估", cancelButtonText: "取消", type: "warning" }
        );
      } catch (err) {
        return;
      }
      this.evaluating = true;
      try {
        const res = await evaluateModel({});
        if (res.code === 200 && res.data) {
          this.$message.success(
            `评估完成：准确率 ${this.percent(res.data.metrics.accuracy)}，Macro-F1 ${this.percent(
              res.data.metrics.macroF1
            )}`
          );
          this.overview = Object.assign({}, this.overview);
          await this.loadOverview();
          await this.selectVersion(res.data);
        } else {
          this.$message.error(this.errorText(res, "评估失败"));
        }
      } catch (err) {
        this.$message.error(this.errorText(err, "评估失败"));
      } finally {
        this.evaluating = false;
      }
    },
    async setOnline(version) {
      try {
        await this.$confirm(
          `确认将版本 #${version.id} 设为线上模型？同模型的其他版本会自动下线。`,
          "切换线上模型",
          { confirmButtonText: "确认切换", cancelButtonText: "取消", type: "warning" }
        );
      } catch (err) {
        return;
      }
      this.switchingId = version.id;
      try {
        const res = await setOnlineModel(version.id);
        if (res.code === 200) {
          this.$message.success(`版本 #${version.id} 已设为线上模型`);
          await this.loadOverview();
        } else {
          this.$message.error(this.errorText(res, "切换失败"));
        }
      } catch (err) {
        this.$message.error(this.errorText(err, "切换失败"));
      } finally {
        this.switchingId = null;
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
    ensureChart(key, refName) {
      const el = this.$refs[refName];
      if (!el) return null;
      if (!this.charts[key]) {
        this.charts[key] = this.$echarts.init(el);
      }
      return this.charts[key];
    },
    renderCharts() {
      const metrics = (this.selected && this.selected.metrics) || {};
      this.renderConfusion(metrics);
      this.renderPerClass(metrics);
      this.renderTrend(this.overview.trend || []);
    },
    emptyOption(text) {
      return {
        title: {
          text: text,
          left: "center",
          top: "middle",
          textStyle: { color: "#6f90b5", fontSize: 13, fontWeight: "normal" },
        },
      };
    },
    renderConfusion(metrics) {
      const chart = this.ensureChart("confusion", "confusionChart");
      if (!chart) return;
      const labels = metrics.labels || [];
      const matrix = metrics.confusionMatrix || [];
      if (!labels.length || !matrix.length) {
        chart.clear();
        chart.setOption(this.emptyOption("暂无混淆矩阵数据"), true);
        return;
      }
      const data = [];
      let maxValue = 0;
      matrix.forEach((row, y) => {
        row.forEach((value, x) => {
          data.push([x, y, value]);
          if (value > maxValue) maxValue = value;
        });
      });
      chart.setOption(
        {
          backgroundColor: "transparent",
          tooltip: {
            formatter: (params) => {
              const [x, y, value] = params.data;
              return `真实：${labels[y]}<br/>预测：${labels[x]}<br/>数量：${value}`;
            },
          },
          grid: { left: 8, right: 24, top: 24, bottom: 8, containLabel: true },
          xAxis: {
            type: "category",
            data: labels,
            splitArea: { show: true, areaStyle: { color: ["rgba(10,30,60,0.25)", "transparent"] } },
            axisLabel: { color: "#8fb6dd", fontSize: 10, rotate: 35 },
            axisLine: { lineStyle: { color: "#2b4a70" } },
          },
          yAxis: {
            type: "category",
            data: labels,
            inverse: true,
            splitArea: { show: true, areaStyle: { color: ["rgba(10,30,60,0.25)", "transparent"] } },
            axisLabel: { color: "#8fb6dd", fontSize: 10 },
            axisLine: { lineStyle: { color: "#2b4a70" } },
          },
          visualMap: {
            min: 0,
            max: Math.max(maxValue, 1),
            calculable: false,
            orient: "horizontal",
            left: "center",
            bottom: 0,
            itemWidth: 10,
            itemHeight: 70,
            textStyle: { color: "#7fa8d4", fontSize: 10 },
            inRange: { color: ["#0b2545", "#1f66c9", "#4fd1ff"] },
          },
          series: [
            {
              type: "heatmap",
              data,
              label: {
                show: true,
                color: "#eaf4ff",
                fontSize: 9,
                formatter: (params) => (params.data[2] ? params.data[2] : ""),
              },
              emphasis: { itemStyle: { shadowBlur: 8, shadowColor: "rgba(79,209,255,0.6)" } },
              itemStyle: { borderColor: "#071a33", borderWidth: 1 },
            },
          ],
        },
        true
      );
    },
    renderPerClass(metrics) {
      const chart = this.ensureChart("perClass", "perClassChart");
      if (!chart) return;
      const perClass = metrics.perClass || [];
      if (!perClass.length) {
        chart.clear();
        chart.setOption(this.emptyOption("暂无各类别指标"), true);
        return;
      }
      const names = perClass.map((item) => item.name);
      const series = [
        { key: "precision", label: "Precision", color: "#4fa3ff" },
        { key: "recall", label: "Recall", color: "#37e2c4" },
        { key: "f1", label: "F1", color: "#f7b84b" },
      ].map((item) => ({
        name: item.label,
        type: "bar",
        barWidth: 8,
        data: perClass.map((row) => Number(row[item.key] || 0)),
        itemStyle: { color: item.color, borderRadius: [3, 3, 0, 0] },
      }));

      chart.setOption(
        {
          backgroundColor: "transparent",
          tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
          legend: {
            top: 0,
            right: 0,
            textStyle: { color: "#8fb6dd", fontSize: 11 },
            itemWidth: 10,
            itemHeight: 8,
          },
          grid: { left: 10, right: 16, top: 34, bottom: 8, containLabel: true },
          xAxis: {
            type: "category",
            data: names,
            axisLabel: { color: "#8fb6dd", fontSize: 10, rotate: 30 },
            axisLine: { lineStyle: { color: "#2b4a70" } },
          },
          yAxis: {
            type: "value",
            max: 1,
            axisLabel: { color: "#8fb6dd", fontSize: 10, formatter: (v) => `${Math.round(v * 100)}%` },
            splitLine: { lineStyle: { color: "rgba(80,140,220,0.10)" } },
            axisLine: { lineStyle: { color: "#2b4a70" } },
          },
          series,
        },
        true
      );
    },
    renderTrend(trend) {
      const chart = this.ensureChart("trend", "trendChart");
      if (!chart) return;
      if (!trend.length) {
        chart.clear();
        chart.setOption(this.emptyOption("暂无评估版本"), true);
        return;
      }
      const labels = trend.map((item) => `#${item.id}`);
      chart.setOption(
        {
          backgroundColor: "transparent",
          tooltip: {
            trigger: "axis",
            formatter: (params) => {
              const index = params[0].dataIndex;
              const version = trend[index];
              const lines = [`版本 #${version.id}`];
              params.forEach((p) => {
                lines.push(`${p.marker}${p.seriesName}：${(p.value * 100).toFixed(2)}%`);
              });
              return lines.join("<br/>");
            },
          },
          legend: {
            top: 0,
            right: 0,
            textStyle: { color: "#8fb6dd", fontSize: 11 },
            itemWidth: 12,
            itemHeight: 8,
          },
          grid: { left: 10, right: 20, top: 34, bottom: 8, containLabel: true },
          xAxis: {
            type: "category",
            data: labels,
            axisLabel: { color: "#8fb6dd", fontSize: 11 },
            axisLine: { lineStyle: { color: "#2b4a70" } },
          },
          yAxis: {
            type: "value",
            max: 1,
            axisLabel: { color: "#8fb6dd", fontSize: 10, formatter: (v) => `${Math.round(v * 100)}%` },
            splitLine: { lineStyle: { color: "rgba(80,140,220,0.10)" } },
            axisLine: { lineStyle: { color: "#2b4a70" } },
          },
          series: [
            {
              name: "准确率",
              type: "line",
              smooth: true,
              symbolSize: 7,
              data: trend.map((item) => Number(item.accuracy || 0)),
              lineStyle: { width: 3, color: "#4fa3ff" },
              itemStyle: { color: "#4fa3ff" },
            },
            {
              name: "Macro-F1",
              type: "line",
              smooth: true,
              symbolSize: 7,
              data: trend.map((item) => Number(item.macroF1 || 0)),
              lineStyle: { width: 3, color: "#37e2c4", type: "dashed" },
              itemStyle: { color: "#37e2c4" },
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
.model-center {
  color: #cfe4ff;
  padding: 2px 6px 18px;
}

.mc-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
  .mc-title {
    display: flex;
    align-items: center;
    .mc-title-bar {
      width: 4px;
      height: 38px;
      border-radius: 4px;
      margin-right: 12px;
      background: linear-gradient(180deg, #37e2c4, #1f66c9);
      box-shadow: 0 0 12px rgba(55, 226, 196, 0.55);
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
  .mc-actions {
    display: flex;
    align-items: center;
    gap: 10px;
  }
}

.artifact-badge {
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
  &.ready {
    color: #37e2c4;
    border-color: rgba(55, 226, 196, 0.4);
    .dot {
      background: #37e2c4;
      box-shadow: 0 0 8px #37e2c4;
    }
  }
  &.missing {
    color: #ff9aa6;
    border-color: rgba(255, 122, 138, 0.35);
    .dot {
      background: #ff7a8a;
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
    &.highlight {
      color: #37e2c4;
      text-shadow: 0 0 12px rgba(55, 226, 196, 0.35);
    }
  }
  .kpi-sub {
    font-size: 11px;
    color: #6f90b5;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
}

.mc-grid {
  display: grid;
  grid-template-columns: 1.35fr 1fr;
  gap: 12px;
  margin-top: 12px;
  &.main {
    grid-template-columns: 1.2fr 1fr;
  }
}

.panel {
  height: 350px;
  &.trend-panel,
  &.version-panel {
    height: 320px;
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
      background: #37e2c4;
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

.chart-body {
  flex: 1;
  width: 100%;
  min-height: 0;
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

.mc-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
  th {
    text-align: left;
    color: #7fa8d4;
    font-weight: 500;
    padding: 7px 6px;
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
  }
  tr.version-row {
    cursor: pointer;
    &:hover td {
      background: rgba(79, 163, 255, 0.08);
    }
    &.active td {
      background: rgba(55, 226, 196, 0.08);
    }
  }
  .num {
    color: #4fd1ff;
    font-weight: 600;
  }
  .version-name {
    color: #e3f1ff;
    font-family: Consolas, Monaco, monospace;
    font-size: 11px;
    max-width: 260px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .version-meta {
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
  &.online {
    color: #37e2c4;
    border-color: rgba(55, 226, 196, 0.4);
    background: rgba(55, 226, 196, 0.08);
  }
  &.candidate {
    color: #8fb6dd;
    border-color: rgba(143, 182, 221, 0.35);
    background: rgba(143, 182, 221, 0.06);
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
  &.primary {
    border-color: rgba(55, 226, 196, 0.45);
    color: #37e2c4;
  }
  &.ghost {
    border-color: rgba(140, 170, 200, 0.35);
    color: #a9c3de;
  }
}

.model-status {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  padding-top: 8px;
  margin-top: 6px;
  border-top: 1px dashed rgba(79, 163, 255, 0.18);
  font-size: 11px;
  color: #6f90b5;
}

@media (max-width: 1500px) {
  .kpi-value {
    font-size: 20px !important;
  }
  .mc-grid,
  .mc-grid.main {
    grid-template-columns: 1fr;
  }
}
</style>
