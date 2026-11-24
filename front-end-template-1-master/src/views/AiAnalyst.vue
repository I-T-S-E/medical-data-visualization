<template>
  <div class="ai-analyst">
    <!-- 顶部标题 -->
    <div class="aa-toolbar">
      <div class="aa-title">
        <span class="aa-title-bar"></span>
        <div>
          <h2>AI 数据分析助手</h2>
          <p>基于平台实时病例数据的智能分析问答，支持携带筛选条件与数据上下文</p>
        </div>
      </div>
      <div class="aa-actions">
        <span :class="['conn-badge', connected ? 'online' : 'offline']">
          <i class="dot"></i>
          {{ connected ? "AI 服务已连接" : "AI 服务未连接" }}
        </span>
        <el-button size="mini" @click="clearChat">清空对话</el-button>
      </div>
    </div>

    <div class="aa-layout">
      <!-- 对话区 -->
      <dv-border-box-10 class="chat-panel">
        <div class="chat-inner">
          <div class="context-bar">
            <span class="context-label">分析条件</span>
            <label class="context-item">
              疾病
              <select v-model="context.disease">
                <option value="">全部疾病</option>
                <option v-for="name in diseaseOptions" :key="name" :value="name">
                  {{ name }}
                </option>
              </select>
            </label>
            <label class="context-item">
              性别
              <select v-model="context.gender">
                <option value="">全部</option>
                <option value="男">男</option>
                <option value="女">女</option>
              </select>
            </label>
            <label class="context-item">
              时间范围
              <select v-model="context.range">
                <option value="all">全部时间</option>
                <option value="recent30">最近 30 天</option>
                <option value="recent90">最近 90 天</option>
              </select>
            </label>
            <span class="context-hint">条件会随问题一起发送给分析助手</span>
          </div>

          <div ref="messageList" class="message-list">
            <div v-if="!messages.length" class="welcome">
              <div class="welcome-icon">AI</div>
              <h3>您好，我是 AI 数据分析助手</h3>
              <p>
                我可以结合当前平台 {{ totalCases }} 条病例数据，回答疾病分布、医院排名、年龄性别特征等问题。
              </p>
              <div class="prompt-grid">
                <div
                  v-for="(prompt, index) in quickPrompts"
                  :key="index"
                  class="prompt-card"
                  @click="ask(prompt)"
                >
                  <span class="prompt-title">{{ prompt.title }}</span>
                  <span class="prompt-desc">{{ prompt.desc }}</span>
                </div>
              </div>
            </div>

            <div
              v-for="(message, index) in messages"
              :key="index"
              :class="['message-row', message.role]"
            >
              <div class="avatar">{{ message.role === 'assistant' ? 'AI' : '我' }}</div>
              <div class="message-body">
                <div class="message-meta">
                  {{ message.role === 'assistant' ? 'AI 数据分析助手' : '您' }}
                  <span>{{ message.time }}</span>
                </div>
                <div
                  class="message-content"
                  v-html="formatMessage(message.content)"
                ></div>
              </div>
            </div>

            <div v-if="loading" class="message-row assistant">
              <div class="avatar">AI</div>
              <div class="message-body">
                <div class="message-meta">AI 数据分析助手<span>正在分析…</span></div>
                <div class="typing"><i></i><i></i><i></i></div>
              </div>
            </div>
          </div>

          <div class="composer">
            <textarea
              ref="input"
              v-model="input"
              rows="2"
              placeholder="例如：当前病例中哪些疾病最多？肺炎病例主要集中在哪里？"
              @keydown.enter.exact.prevent="send"
            ></textarea>
            <div class="composer-actions">
              <span class="composer-tip">Enter 发送 · Shift + Enter 换行</span>
              <el-button
                size="mini"
                type="primary"
                :loading="loading"
                :disabled="!input.trim() || loading"
                @click="send"
              >
                发送
              </el-button>
            </div>
          </div>
        </div>
      </dv-border-box-10>

      <!-- 数据速览 -->
      <div class="side-column">
        <dv-border-box-12 class="side-panel snapshot-panel">
          <div class="side-inner">
            <div class="side-head">
              <span class="side-title">当前数据速览</span>
              <span class="side-tip">{{ snapshot.freshness.human || "同步中" }}</span>
            </div>
            <div class="snapshot-kpis">
              <div class="snapshot-kpi">
                <div class="kpi-label">病例总量</div>
                <div class="kpi-value">{{ formatNumber(totalCases) }}</div>
              </div>
              <div class="snapshot-kpi">
                <div class="kpi-label">今日新增</div>
                <div class="kpi-value">{{ formatNumber(snapshot.summary.todayNew || 0) }}</div>
              </div>
              <div class="snapshot-kpi">
                <div class="kpi-label">疾病种类</div>
                <div class="kpi-value">{{ snapshot.summary.diseaseKinds || 0 }}</div>
              </div>
              <div class="snapshot-kpi">
                <div class="kpi-label">医院数量</div>
                <div class="kpi-value">{{ snapshot.summary.hospitalKinds || 0 }}</div>
              </div>
            </div>

            <div class="side-block">
              <div class="side-block-title">疾病分布 Top 5</div>
              <div
                v-for="item in topDiseases"
                :key="item.name"
                class="bar-item"
              >
                <div class="bar-top">
                  <span>{{ item.name }}</span>
                  <span>{{ item.value }}</span>
                </div>
                <div class="bar-track">
                  <div class="bar-fill" :style="{ width: item.percent + '%' }"></div>
                </div>
              </div>
            </div>

            <div class="side-block">
              <div class="side-block-title">医院病例数 Top 5</div>
              <div
                v-for="(item, index) in topHospitals"
                :key="item.name"
                class="rank-item"
              >
                <span :class="['rank-index', index < 3 ? 'hot' : '']">
                  {{ index + 1 }}
                </span>
                <span class="rank-name">{{ item.name }}</span>
                <span class="rank-value">{{ item.value }}</span>
              </div>
              <div v-if="!topHospitals.length" class="side-empty">暂无医院数据</div>
            </div>

            <div class="side-block sync-info">
              <div class="side-block-title">最近同步</div>
              <div class="sync-line">
                <span>批次</span>
                <span>#{{ snapshot.freshness.batchId || "-" }}</span>
              </div>
              <div class="sync-line">
                <span>时间</span>
                <span>{{ snapshot.freshness.lastSyncAt || "-" }}</span>
              </div>
              <div class="sync-line">
                <span>结果</span>
                <span>{{ snapshot.freshness.statusLabel || "-" }}</span>
              </div>
            </div>
          </div>
        </dv-border-box-12>

        <div class="disclaimer">
          分析结果由大模型基于平台数据生成，仅供参考，不替代医生诊断。
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import io from "socket.io-client";
import { marked } from "marked";
import { fetchMonitorOverview } from "@/api/monitor";

const STORAGE_KEY = "ai_analyst_messages_v1";
const RANGE_LABELS = {
  all: "全部时间",
  recent30: "最近 30 天",
  recent90: "最近 90 天",
};

export default {
  name: "AiAnalyst",
  data() {
    return {
      messages: [],
      input: "",
      lastQuestion: "",
      loading: false,
      socket: null,
      connected: false,
      responseTimer: null,
      context: {
        disease: "",
        gender: "",
        range: "all",
      },
      snapshot: {
        summary: {},
        freshness: {},
        distributions: { disease: [], gender: [], age: [], hospital: [] },
      },
      pollTimer: null,
      quickPrompts: [
        {
          title: "疾病分布",
          desc: "当前病例中哪些疾病最多？",
          question: "当前病例中哪些疾病最多？请列出前 5 名，并结合数量做简要分析。",
        },
        {
          title: "医院排名",
          desc: "哪些医院病例最多？",
          question: "按病例数统计，当前数据中病例最多的医院有哪些？请给出前 5 名。",
        },
        {
          title: "人群特征",
          desc: "年龄与性别有什么特点？",
          question: "结合当前数据，总结病例在年龄和性别上的分布特征。",
        },
      ],
    };
  },
  computed: {
    totalCases() {
      return this.snapshot.summary.totalCases || 0;
    },
    diseaseOptions() {
      return (this.snapshot.distributions.disease || []).map((item) => item.name);
    },
    topDiseases() {
      const list = this.snapshot.distributions.disease || [];
      const max = list.length ? list[0].value : 1;
      return list.slice(0, 5).map((item) => ({
        name: item.name,
        value: item.value,
        percent: Math.round((item.value / Math.max(max, 1)) * 100),
      }));
    },
    topHospitals() {
      return (this.snapshot.distributions.hospital || []).slice(0, 5);
    },
    contextText() {
      const parts = [];
      parts.push("疾病=" + (this.context.disease || "全部"));
      parts.push("性别=" + (this.context.gender || "全部"));
      parts.push("时间=" + (RANGE_LABELS[this.context.range] || "全部时间"));
      return parts.join("；");
    },
  },
  async mounted() {
    this.loadMessages();
    await this.loadSnapshot();
    this.connectSocket();
    this.pollTimer = setInterval(this.loadSnapshot, 30000);
    this.$nextTick(this.scrollToBottom);
  },
  beforeDestroy() {
    if (this.pollTimer) {
      clearInterval(this.pollTimer);
      this.pollTimer = null;
    }
    if (this.responseTimer) {
      clearTimeout(this.responseTimer);
      this.responseTimer = null;
    }
    if (this.socket) {
      this.socket.disconnect();
      this.socket = null;
    }
  },
  methods: {
    formatNumber(value) {
      return Number(value || 0).toLocaleString("zh-CN");
    },
    async loadSnapshot() {
      try {
        const res = await fetchMonitorOverview();
        if (res.code === 200 && res.data) {
          this.snapshot = res.data;
        }
      } catch (err) {
        // 数据概览失败不影响对话
      }
    },
    connectSocket() {
      try {
        const socketUrl = `http://${window.location.hostname}:5001/ws/chat`;
        this.socket = io(socketUrl, {
          transports: ["websocket", "polling"],
          reconnection: true,
          reconnectionDelay: 2000,
        });
        this.socket.on("connect", () => {
          this.connected = true;
        });
        this.socket.on("disconnect", () => {
          this.connected = false;
        });
        this.socket.on("connect_error", () => {
          this.connected = false;
        });
        this.socket.on("response", (data) => {
          this.clearResponseTimer();
          this.loading = false;
          if (!data) return;
          if (data.type === "response") {
            this.addMessage("assistant", data.content || "");
          } else if (data.type === "error") {
            this.$message.warning("AI 服务暂不可用，已返回本地实时统计结果");
            this.addMessage("assistant", this.buildLocalAnswer(this.lastQuestion));
          }
        });
      } catch (err) {
        this.connected = false;
      }
    },
    ask(prompt) {
      this.input = prompt.question;
      this.$nextTick(() => this.send());
    },
    send() {
      const text = this.input.trim();
      if (!text || this.loading) return;

      this.addMessage("user", text);
      this.input = "";
      this.lastQuestion = text;
      this.loading = true;

      if (!this.connected || !this.socket) {
        this.loading = false;
        this.addMessage("assistant", this.buildLocalAnswer(text));
        return;
      }

      this.socket.emit(
        "message",
        JSON.stringify({
          type: "message",
          content: this.buildPrompt(text),
        })
      );
      this.startResponseTimer();
    },
    buildPrompt(question) {
      const summary = this.dataSummaryText();
      return [
        "你是医疗数据分析助手。请严格依据下面提供的平台实时数据回答问题，不要编造数据；",
        "回答使用中文 Markdown，先给结论，再列依据，必要时给出简洁的表格或列表。",
        "",
        "【平台实时数据摘要】",
        summary,
        "",
        "【分析条件】",
        this.contextText,
        "",
        "【用户问题】",
        question,
      ].join("\n");
    },
    dataSummaryText() {
      const lines = [];
      lines.push(
        `病例总量 ${this.totalCases} 条，今日新增 ${this.snapshot.summary.todayNew || 0} 条。`
      );
      lines.push(
        "疾病 Top5：" +
          this.topDiseases.map((item) => `${item.name} ${item.value} 例`).join("、")
      );
      lines.push(
        "医院 Top5：" +
          this.topHospitals.map((item) => `${item.name} ${item.value} 例`).join("、")
      );
      const genders = this.snapshot.distributions.gender || [];
      if (genders.length) {
        lines.push(
          "性别构成：" +
            genders.map((item) => `${item.name} ${item.value} 例`).join("、")
        );
      }
      const ages = this.snapshot.distributions.age || [];
      if (ages.length) {
        lines.push(
          "年龄分布：" + ages.map((item) => `${item.name} ${item.value} 例`).join("、")
        );
      }
      const freshness = this.snapshot.freshness || {};
      lines.push(
        `最近同步：${freshness.lastSyncAt || "未知"}（${freshness.statusLabel || "未知"}）。`
      );
      return lines.join("\n");
    },
    buildLocalAnswer(question) {
      const q = String(question || "");
      const total = this.totalCases || 1;
      const lines = [];

      if (this.context.disease || this.context.gender || this.context.range !== "all") {
        lines.push("> 分析条件：" + this.contextText);
        lines.push("");
      }

      if (/医院/.test(q)) {
        lines.push("### 医院病例数 Top5");
        lines.push("");
        this.topHospitals.forEach((item, index) => {
          lines.push(`${index + 1}. ${item.name}：${item.value} 例`);
        });
      } else if (/年龄/.test(q)) {
        lines.push("### 年龄分布");
        lines.push("");
        (this.snapshot.distributions.age || []).forEach((item) => {
          lines.push(
            `- ${item.name} 岁：${item.value} 例（${((item.value / total) * 100).toFixed(1)}%）`
          );
        });
      } else if (/性别/.test(q)) {
        lines.push("### 性别构成");
        lines.push("");
        (this.snapshot.distributions.gender || []).forEach((item) => {
          lines.push(
            `- ${item.name}：${item.value} 例（${((item.value / total) * 100).toFixed(1)}%）`
          );
        });
      } else if (/趋势|月份|月度|时间/.test(q)) {
        lines.push("### 月度病例趋势");
        lines.push("");
        (this.snapshot.distributions.month || []).forEach((item) => {
          lines.push(`- ${item.name}：${item.value} 例`);
        });
      } else if (/疾病|病种|哪些病/.test(q)) {
        lines.push("### 疾病分布 Top5");
        lines.push("");
        this.topDiseases.forEach((item, index) => {
          lines.push(
            `${index + 1}. ${item.name}：${item.value} 例（${((item.value / total) * 100).toFixed(1)}%）`
          );
        });
      } else {
        lines.push("### 当前数据速览");
        lines.push("");
        lines.push(this.dataSummaryText().replace(/\n/g, "  \n"));
      }

      lines.push("");
      lines.push(
        "> 说明：AI 服务当前不可用，以上为平台本地实时统计结果；配置 DeepSeek API Key 后可获得自然语言分析与解读。"
      );
      return lines.join("\n");
    },
    startResponseTimer() {
      this.clearResponseTimer();
      this.responseTimer = setTimeout(() => {
        if (!this.loading) return;
        this.loading = false;
        this.$message.warning("AI 响应超时，已返回本地数据摘要");
        this.addMessage("assistant", this.buildLocalAnswer(this.lastQuestion));
      }, 60000);
    },
    clearResponseTimer() {
      if (this.responseTimer) {
        clearTimeout(this.responseTimer);
        this.responseTimer = null;
      }
    },
    addMessage(role, content) {
      this.messages.push({
        role,
        content,
        time: this.currentTime(),
      });
      if (this.messages.length > 100) {
        this.messages = this.messages.slice(-100);
      }
      this.saveMessages();
      this.$nextTick(this.scrollToBottom);
    },
    formatMessage(content) {
      try {
        marked.setOptions({
          breaks: true,
          gfm: true,
          headerIds: false,
          mangle: false,
        });
        let html = marked.parse(content || "");
        html = html.replace(/<a /g, '<a target="_blank" ');
        return html;
      } catch (err) {
        return String(content || "").replace(/\n/g, "<br>");
      }
    },
    scrollToBottom() {
      const container = this.$refs.messageList;
      if (container) container.scrollTop = container.scrollHeight;
    },
    currentTime() {
      const now = new Date();
      return `${now.getHours().toString().padStart(2, "0")}:${now
        .getMinutes()
        .toString()
        .padStart(2, "0")}`;
    },
    saveMessages() {
      try {
        localStorage.setItem(
          STORAGE_KEY,
          JSON.stringify({ messages: this.messages, updatedAt: new Date().toISOString() })
        );
      } catch (err) {
        // 本地存储不可用时忽略
      }
    },
    loadMessages() {
      try {
        const raw = localStorage.getItem(STORAGE_KEY);
        if (!raw) return;
        const data = JSON.parse(raw);
        const updated = data.updatedAt ? new Date(data.updatedAt) : null;
        const thirtyDaysAgo = new Date();
        thirtyDaysAgo.setDate(thirtyDaysAgo.getDate() - 30);
        if (updated && updated < thirtyDaysAgo) return;
        this.messages = Array.isArray(data.messages) ? data.messages.slice(-100) : [];
      } catch (err) {
        this.messages = [];
      }
    },
    clearChat() {
      this.$confirm("确认清空当前对话记录？", "清空对话", {
        confirmButtonText: "清空",
        cancelButtonText: "取消",
        type: "warning",
      })
        .then(() => {
          this.messages = [];
          this.loading = false;
          this.clearResponseTimer();
          try {
            localStorage.removeItem(STORAGE_KEY);
          } catch (err) {
            // ignore
          }
          this.$message.success("对话已清空");
        })
        .catch(() => {});
    },
  },
};
</script>

<style lang="less" scoped>
.ai-analyst {
  color: #cfe4ff;
  padding: 2px 6px 16px;
}

.aa-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
  .aa-title {
    display: flex;
    align-items: center;
    .aa-title-bar {
      width: 4px;
      height: 38px;
      border-radius: 4px;
      margin-right: 12px;
      background: linear-gradient(180deg, #9b8cff, #4fa3ff);
      box-shadow: 0 0 12px rgba(155, 140, 255, 0.5);
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
  .aa-actions {
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

.aa-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 340px;
  gap: 12px;
  align-items: stretch;
}

.chat-panel {
  height: calc(100vh - 170px);
  min-height: 620px;
  .chat-inner {
    height: 100%;
    padding: 14px 18px;
    box-sizing: border-box;
    display: flex;
    flex-direction: column;
  }
}

.context-bar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
  padding-bottom: 10px;
  border-bottom: 1px dashed rgba(79, 163, 255, 0.18);
  font-size: 12px;
  .context-label {
    color: #8fb6dd;
  }
  .context-item {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    color: #7fa8d4;
    select {
      background: rgba(10, 32, 62, 0.9);
      color: #cfe4ff;
      border: 1px solid rgba(79, 163, 255, 0.35);
      border-radius: 6px;
      padding: 4px 8px;
      font-size: 12px;
      outline: none;
      option {
        background: #0a2040;
      }
    }
  }
  .context-hint {
    margin-left: auto;
    color: #5f7f9f;
    font-size: 11px;
  }
}

.message-list {
  flex: 1;
  overflow-y: auto;
  padding: 14px 4px 8px;
  &::-webkit-scrollbar {
    width: 6px;
  }
  &::-webkit-scrollbar-thumb {
    background: rgba(79, 163, 255, 0.35);
    border-radius: 3px;
  }
}

.welcome {
  max-width: 640px;
  margin: 30px auto 0;
  text-align: center;
  .welcome-icon {
    width: 54px;
    height: 54px;
    margin: 0 auto 12px;
    border-radius: 50%;
    line-height: 54px;
    font-weight: 700;
    color: #071a33;
    background: linear-gradient(135deg, #9b8cff, #4fd1ff);
    box-shadow: 0 0 20px rgba(79, 209, 255, 0.35);
  }
  h3 {
    font-size: 18px;
    color: #e3f1ff;
  }
  p {
    margin: 8px 0 18px;
    font-size: 12px;
    color: #7fa8d4;
    line-height: 1.7;
  }
}

.prompt-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px;
}
.prompt-card {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 12px;
  border-radius: 8px;
  border: 1px solid rgba(79, 163, 255, 0.25);
  background: rgba(12, 34, 64, 0.6);
  cursor: pointer;
  transition: all 0.2s;
  text-align: left;
  &:hover {
    border-color: rgba(79, 209, 255, 0.6);
    background: rgba(20, 48, 86, 0.7);
    transform: translateY(-2px);
  }
  .prompt-title {
    color: #4fd1ff;
    font-size: 13px;
  }
  .prompt-desc {
    color: #7fa8d4;
    font-size: 11px;
  }
}

.message-row {
  display: flex;
  gap: 10px;
  margin-bottom: 16px;
  .avatar {
    flex: 0 0 34px;
    height: 34px;
    border-radius: 50%;
    text-align: center;
    line-height: 34px;
    font-size: 12px;
    font-weight: 600;
  }
  .message-body {
    max-width: 78%;
    min-width: 0;
  }
  .message-meta {
    font-size: 11px;
    color: #7fa8d4;
    margin-bottom: 5px;
    span {
      margin-left: 8px;
      color: #5f7f9f;
    }
  }
  .message-content {
    padding: 10px 14px;
    border-radius: 8px;
    font-size: 13px;
    line-height: 1.8;
    color: #d7e9ff;
    word-break: break-word;
  }
  &.user {
    flex-direction: row-reverse;
    .avatar {
      background: linear-gradient(135deg, #1f66c9, #4fa3ff);
      color: #fff;
    }
    .message-body {
      text-align: right;
    }
    .message-content {
      text-align: left;
      background: rgba(31, 102, 201, 0.28);
      border: 1px solid rgba(79, 163, 255, 0.28);
    }
  }
  &.assistant {
    .avatar {
      background: linear-gradient(135deg, #9b8cff, #4fd1ff);
      color: #071a33;
    }
    .message-content {
      background: rgba(12, 34, 64, 0.75);
      border: 1px solid rgba(79, 163, 255, 0.18);
    }
  }
}

.typing {
  display: flex;
  gap: 5px;
  padding: 12px 16px;
  border-radius: 8px;
  background: rgba(12, 34, 64, 0.75);
  width: 70px;
  i {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: #4fd1ff;
    animation: blink 1.2s infinite ease-in-out;
    &:nth-child(2) {
      animation-delay: 0.2s;
    }
    &:nth-child(3) {
      animation-delay: 0.4s;
    }
  }
}
@keyframes blink {
  0%,
  80%,
  100% {
    opacity: 0.25;
    transform: translateY(0);
  }
  40% {
    opacity: 1;
    transform: translateY(-3px);
  }
}

.composer {
  border-top: 1px solid rgba(79, 163, 255, 0.2);
  padding-top: 10px;
  textarea {
    width: 100%;
    resize: none;
    box-sizing: border-box;
    background: rgba(8, 26, 50, 0.9);
    border: 1px solid rgba(79, 163, 255, 0.3);
    border-radius: 8px;
    color: #d7e9ff;
    padding: 10px 12px;
    font-size: 13px;
    line-height: 1.6;
    outline: none;
    font-family: inherit;
    &:focus {
      border-color: rgba(79, 209, 255, 0.65);
      box-shadow: 0 0 10px rgba(79, 209, 255, 0.12);
    }
    &::placeholder {
      color: #5f7f9f;
    }
  }
  .composer-actions {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-top: 8px;
  }
  .composer-tip {
    font-size: 11px;
    color: #5f7f9f;
  }
}

.side-column {
  display: flex;
  flex-direction: column;
  gap: 10px;
  height: calc(100vh - 170px);
  min-height: 620px;
}

.side-panel {
  flex: 1;
  min-height: 0;
  .side-inner {
    height: 100%;
    padding: 14px 16px;
    box-sizing: border-box;
    display: flex;
    flex-direction: column;
    overflow-y: auto;
    &::-webkit-scrollbar {
      width: 5px;
    }
    &::-webkit-scrollbar-thumb {
      background: rgba(79, 163, 255, 0.35);
      border-radius: 3px;
    }
  }
}

.side-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  margin-bottom: 10px;
  .side-title {
    font-size: 14px;
    color: #e3f1ff;
    &::before {
      content: "";
      display: inline-block;
      width: 3px;
      height: 12px;
      margin-right: 8px;
      background: #9b8cff;
      vertical-align: -2px;
    }
  }
  .side-tip {
    font-size: 11px;
    color: #6f90b5;
  }
}

.snapshot-kpis {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  margin-bottom: 12px;
}
.snapshot-kpi {
  padding: 8px 10px;
  border-radius: 6px;
  background: rgba(79, 163, 255, 0.07);
  border: 1px solid rgba(79, 163, 255, 0.14);
  .kpi-label {
    font-size: 11px;
    color: #7fa8d4;
  }
  .kpi-value {
    margin-top: 4px;
    font-size: 17px;
    font-weight: 600;
    color: #4fd1ff;
  }
}

.side-block {
  margin-bottom: 14px;
  .side-block-title {
    font-size: 12px;
    color: #8fb6dd;
    margin-bottom: 8px;
  }
}

.bar-item {
  margin-bottom: 8px;
  .bar-top {
    display: flex;
    justify-content: space-between;
    font-size: 11px;
    color: #bcd9f5;
    margin-bottom: 3px;
  }
  .bar-track {
    height: 5px;
    border-radius: 3px;
    background: rgba(79, 163, 255, 0.12);
    overflow: hidden;
  }
  .bar-fill {
    height: 100%;
    border-radius: 3px;
    background: linear-gradient(90deg, #4fa3ff, #4fd1ff);
  }
}

.rank-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 0;
  font-size: 11px;
  color: #bcd9f5;
  .rank-index {
    flex: 0 0 18px;
    height: 18px;
    line-height: 18px;
    text-align: center;
    border-radius: 50%;
    background: rgba(79, 163, 255, 0.12);
    color: #7fa8d4;
    font-size: 10px;
    &.hot {
      background: rgba(247, 184, 75, 0.16);
      color: #f7b84b;
    }
  }
  .rank-name {
    flex: 1;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .rank-value {
    color: #4fd1ff;
    font-weight: 600;
  }
}

.sync-info {
  margin-top: auto;
  margin-bottom: 0;
  padding-top: 10px;
  border-top: 1px dashed rgba(79, 163, 255, 0.18);
  .sync-line {
    display: flex;
    justify-content: space-between;
    font-size: 11px;
    color: #7fa8d4;
    padding: 2px 0;
  }
}

.side-empty {
  font-size: 11px;
  color: #5f7f9f;
  padding: 6px 0;
}

.disclaimer {
  font-size: 11px;
  color: #5f7f9f;
  line-height: 1.6;
  padding: 0 4px;
}

@media (max-width: 1500px) {
  .aa-layout {
    grid-template-columns: minmax(0, 1fr) 300px;
  }
}

@media (max-width: 1200px) {
  .aa-layout {
    grid-template-columns: 1fr;
  }
  .chat-panel {
    height: 70vh;
  }
  .side-column {
    height: auto;
  }
  .side-panel {
    min-height: 420px;
  }
}
</style>

<style lang="less">
/* v-html 渲染的 Markdown 内容不带 scoped 属性，这里统一补充排版 */
.ai-analyst .message-content {
  > :first-child {
    margin-top: 0;
  }
  > :last-child {
    margin-bottom: 0;
  }
  p {
    margin: 6px 0;
  }
  ul,
  ol {
    padding-left: 20px;
    margin: 6px 0;
  }
  table {
    width: 100%;
    border-collapse: collapse;
    margin: 8px 0;
    font-size: 12px;
  }
  th,
  td {
    border: 1px solid rgba(79, 163, 255, 0.25);
    padding: 5px 8px;
    text-align: left;
  }
  th {
    background: rgba(79, 163, 255, 0.12);
  }
  code {
    background: rgba(79, 163, 255, 0.12);
    padding: 1px 5px;
    border-radius: 4px;
  }
  blockquote {
    margin: 8px 0;
    padding: 6px 12px;
    border-left: 3px solid rgba(79, 209, 255, 0.5);
    background: rgba(79, 209, 255, 0.06);
    color: #9fc0e0;
  }
}
</style>
