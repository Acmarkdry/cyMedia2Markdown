<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import {
  CircleCheckFilled,
  Clock,
  DataLine,
  Document,
  Loading,
  Operation,
  Refresh,
  Tickets,
  VideoPlay,
  WarningFilled
} from '@element-plus/icons-vue'
import { getQueueStatus } from '../apis/queueService'

const dashboard = ref(null)
const loading = ref(false)
const errorMessage = ref('')
const selectedState = ref('all')
const selectedJobId = ref('')
const autoRefresh = ref(true)
let refreshTimer = null

const stateMeta = {
  queued: { label: '待准备', type: 'info' },
  prepare_running: { label: '准备中', type: 'warning' },
  prepared: { label: '待生成', type: 'success' },
  opencode_running: { label: '生成中', type: 'primary' },
  done: { label: '完成', type: 'success' },
  prepare_failed: { label: '准备失败', type: 'danger' },
  opencode_failed: { label: '生成失败', type: 'danger' }
}

const stageMeta = {
  success: { label: '完成', icon: CircleCheckFilled },
  running: { label: '运行中', icon: Loading },
  failed: { label: '失败', icon: WarningFilled },
  blocked: { label: '未到达', icon: Clock },
  waiting: { label: '等待', icon: Clock }
}

const loadStatus = async (silent = false) => {
  if (loading.value) return
  loading.value = true
  errorMessage.value = ''
  try {
    dashboard.value = await getQueueStatus()
    ensureSelectedJob()
  } catch (error) {
    errorMessage.value = error.message || '读取队列状态失败'
    if (!silent) ElMessage.error(errorMessage.value)
  } finally {
    loading.value = false
  }
}

const startAutoRefresh = () => {
  stopAutoRefresh()
  if (!autoRefresh.value) return
  refreshTimer = window.setInterval(() => loadStatus(true), 10000)
}

const stopAutoRefresh = () => {
  if (refreshTimer) {
    window.clearInterval(refreshTimer)
    refreshTimer = null
  }
}

const jobs = computed(() => dashboard.value?.jobs || [])
const summary = computed(() => dashboard.value?.summary || {})
const contract = computed(() => dashboard.value?.contract || {})
const storageContract = computed(() => contract.value.storage_contract || {})
const storageHealth = computed(() => dashboard.value?.storage_health || {})
const stateCounts = computed(() => dashboard.value?.counts || {})
const runningJobs = computed(() => dashboard.value?.running_jobs || [])
const todoJobs = computed(() => dashboard.value?.todo_jobs || [])
const failedJobs = computed(() => dashboard.value?.failed_jobs || [])

const visibleJobs = computed(() => {
  if (selectedState.value === 'all') return jobs.value
  return jobs.value.filter(job => job.state === selectedState.value)
})

const selectedJob = computed(() => {
  if (!jobs.value.length) return null
  return jobs.value.find(job => job.job_id === selectedJobId.value) || jobs.value[0]
})

const pipeline = computed(() => [
  {
    key: 'queued',
    title: '等待 GPU 准备',
    subtitle: '按任务顺序领取',
    count: stateCounts.value.queued || 0,
    icon: Tickets
  },
  {
    key: 'prepare',
    title: 'GPU 准备 / ASR',
    subtitle: '下载、抽音频、转写',
    count: stateCounts.value.prepare_running || 0,
    extra: `${stateCounts.value.prepared || 0} 个已准备`,
    icon: VideoPlay
  },
  {
    key: 'opencode',
    title: 'OpenCode 生成',
    subtitle: '导入 artifact 后生成笔记',
    count: stateCounts.value.opencode_running || 0,
    extra: `${stateCounts.value.opencode_failed || 0} 个失败`,
    icon: Operation
  },
  {
    key: 'done',
    title: '产物完成',
    subtitle: 'notes / screenshots / quality',
    count: stateCounts.value.done || 0,
    icon: CircleCheckFilled
  }
])

const stateOptions = computed(() => [
  { value: 'all', state: 'all', label: '全部', count: jobs.value.length },
  ...Object.entries(stateMeta).map(([state, meta]) => ({
    value: state,
    state,
    label: meta.label,
    count: stateCounts.value[state] || 0
  }))
])

const ensureSelectedJob = () => {
  if (!jobs.value.length) {
    selectedJobId.value = ''
    return
  }
  const exists = jobs.value.some(job => job.job_id === selectedJobId.value)
  if (exists) return
  const preferred = runningJobs.value[0] || todoJobs.value[0] || failedJobs.value[0] || jobs.value[0]
  selectedJobId.value = preferred.job_id
}

const stateLabel = state => stateMeta[state]?.label || state || '未知'
const stateType = state => stateMeta[state]?.type || 'info'

const formatTime = value => {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString()
}

const shortTime = value => {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

const heartbeatAge = job => {
  if (!job?.last_heartbeat_iso) return '无心跳'
  const date = new Date(job.last_heartbeat_iso)
  if (Number.isNaN(date.getTime())) return job.last_heartbeat_iso
  const seconds = Math.max(0, Math.round((Date.now() - date.getTime()) / 1000))
  if (seconds < 60) return `${seconds}s 前`
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}m 前`
  return `${Math.floor(minutes / 60)}h ${minutes % 60}m 前`
}

const leaseText = job => {
  if (!job?.lease_until_iso) return '未持有租约'
  return job.lease_expired ? `租约已过期：${formatTime(job.lease_until_iso)}` : `租约至：${formatTime(job.lease_until_iso)}`
}

const attemptsText = job => `prepare ${job.prepare_attempts || 0} / opencode ${job.opencode_attempts || 0}`

const eventText = event => {
  const parts = [event.event, event.stage].filter(Boolean)
  if (event.owner) parts.push(event.owner)
  if (event.success === true) parts.push('success')
  if (event.success === false) parts.push('failed')
  return parts.join(' · ')
}

const rowClassName = ({ row }) => (row.job_id === selectedJobId.value ? 'selected-row' : '')

const selectJob = row => {
  selectedJobId.value = row.job_id
}

watch(autoRefresh, startAutoRefresh)

onMounted(() => {
  loadStatus()
  startAutoRefresh()
})

onBeforeUnmount(() => {
  stopAutoRefresh()
})
</script>

<template>
  <div class="queue-dashboard">
    <header class="queue-header">
      <div>
        <div class="eyebrow">
          <el-icon><DataLine /></el-icon>
          Distributed Queue
        </div>
        <h1>分布式任务流程看板</h1>
        <p>实时读取共享队列目录，跟踪 GPU 准备、OpenCode 生成、租约心跳和待办顺序。</p>
      </div>
      <div class="queue-actions">
        <el-switch v-model="autoRefresh" active-text="自动刷新" />
        <el-button :icon="Refresh" :loading="loading" @click="loadStatus()">刷新</el-button>
      </div>
    </header>

    <el-alert
      v-if="errorMessage"
      :title="errorMessage"
      type="error"
      show-icon
      :closable="false"
      class="status-alert"
    />

    <el-alert
      v-else-if="storageHealth.error_count"
      :title="`存储契约错误：${storageHealth.error_count} 项结构错误，需要先修目录。`"
      type="error"
      show-icon
      :closable="false"
      class="status-alert"
    />

    <el-alert
      v-else-if="storageHealth.warning_count"
      :title="`存储契约警告：${storageHealth.warning_count} 个任务存在旧路径元数据；非运行任务可用 check_storage_layout.py --fix 修复。`"
      type="warning"
      show-icon
      :closable="false"
      class="status-alert"
    />

    <section class="contract-strip">
      <div class="contract-item">
        <span>Python 规范</span>
        <strong>{{ contract.required_python || '3.12.x' }}</strong>
      </div>
      <div class="contract-item wide">
        <span>项目根目录</span>
        <strong>{{ contract.project_root || '-' }}</strong>
      </div>
      <div class="contract-item wide">
        <span>队列根目录</span>
        <strong>{{ contract.queue_root || dashboard?.queue_root || '-' }}</strong>
      </div>
      <div class="contract-item wide">
        <span>最终输出</span>
        <strong>{{ storageContract.final_output_root || '-' }}</strong>
      </div>
      <div class="contract-item wide">
        <span>媒体缓存</span>
        <strong>{{ storageContract.backend_storage?.media || contract.local_media_dir || '-' }}</strong>
      </div>
      <div class="contract-item">
        <span>CPU 环境</span>
        <strong>{{ contract.cpu_venv ? '.venv-cpu' : '-' }}</strong>
      </div>
      <div class="contract-item">
        <span>GPU 环境</span>
        <strong>{{ contract.gpu_venv ? '.venv-gpu' : '-' }}</strong>
      </div>
    </section>

    <section class="command-strip" v-if="contract.commands">
      <div>
        <span>统一入口</span>
        <code>tools\start_worker.ps1 -Role cpu|gpu</code>
      </div>
      <div>
        <span>CPU 启动</span>
        <code>{{ contract.commands.start_cpu }}</code>
      </div>
      <div>
        <span>GPU 启动</span>
        <code>{{ contract.commands.start_gpu }}</code>
      </div>
    </section>

    <section class="summary-strip" v-loading="loading && !dashboard">
      <div class="summary-item">
        <span>总任务</span>
        <strong>{{ summary.total || 0 }}</strong>
      </div>
      <div class="summary-item">
        <span>已完成</span>
        <strong>{{ summary.done || 0 }}</strong>
      </div>
      <div class="summary-item">
        <span>运行中</span>
        <strong>{{ summary.running || 0 }}</strong>
      </div>
      <div class="summary-item">
        <span>待办</span>
        <strong>{{ summary.todo || 0 }}</strong>
      </div>
      <div class="summary-item danger">
        <span>失败</span>
        <strong>{{ summary.failed || 0 }}</strong>
      </div>
      <div class="summary-progress">
        <span>整体进度</span>
        <el-progress :percentage="summary.progress_percent || 0" :stroke-width="10" />
      </div>
    </section>

    <section class="pipeline">
      <div v-for="stage in pipeline" :key="stage.key" class="pipeline-step">
        <div class="pipeline-icon">
          <el-icon><component :is="stage.icon" /></el-icon>
        </div>
        <div class="pipeline-body">
          <span>{{ stage.title }}</span>
          <strong>{{ stage.count }}</strong>
          <small>{{ stage.extra || stage.subtitle }}</small>
        </div>
      </div>
    </section>

    <section class="queue-grid">
      <div class="work-panel">
        <div class="panel-header">
          <div>
            <h2>当前运行</h2>
            <p>来自 worker 的 owner、lease 和 heartbeat。</p>
          </div>
          <el-tag type="primary" effect="plain">{{ runningJobs.length }}</el-tag>
        </div>

        <div v-if="runningJobs.length" class="running-list">
          <button
            v-for="job in runningJobs"
            :key="job.job_id"
            class="running-job"
            :class="{ active: job.job_id === selectedJobId }"
            @click="selectJob(job)"
          >
            <div>
              <span class="job-id">{{ job.job_id }}</span>
              <strong>{{ job.slug }}</strong>
            </div>
            <el-tag :type="stateType(job.state)" effect="dark">{{ stateLabel(job.state) }}</el-tag>
            <dl>
              <div>
                <dt>owner</dt>
                <dd>{{ job.owner || '-' }}</dd>
              </div>
              <div>
                <dt>heartbeat</dt>
                <dd>{{ heartbeatAge(job) }}</dd>
              </div>
              <div>
                <dt>lease</dt>
                <dd :class="{ expired: job.lease_expired }">{{ leaseText(job) }}</dd>
              </div>
            </dl>
          </button>
        </div>

        <el-empty v-else description="当前没有运行中的 worker 任务" :image-size="84" />
      </div>

      <div class="work-panel">
        <div class="panel-header">
          <div>
            <h2>后续待办</h2>
            <p>按课程 p 序和 job id 排列，prepared 会优先等待 OpenCode 消费。</p>
          </div>
          <el-tag type="success" effect="plain">{{ todoJobs.length }}</el-tag>
        </div>

        <div class="todo-list">
          <button
            v-for="job in todoJobs.slice(0, 8)"
            :key="job.job_id"
            class="todo-item"
            :class="{ active: job.job_id === selectedJobId }"
            @click="selectJob(job)"
          >
            <span>{{ job.sort_index < 999999 ? `p${String(job.sort_index).padStart(2, '0')}` : job.job_id }}</span>
            <strong>{{ job.slug }}</strong>
            <el-tag :type="stateType(job.state)" effect="plain">{{ stateLabel(job.state) }}</el-tag>
          </button>
          <el-empty v-if="!todoJobs.length" description="待办队列为空" :image-size="84" />
        </div>
      </div>
    </section>

    <section class="detail-layout">
      <div class="jobs-panel">
        <div class="panel-header">
          <div>
            <h2>任务顺序</h2>
            <p>{{ dashboard?.queue_root || '队列目录未加载' }}</p>
          </div>
          <el-segmented v-model="selectedState" :options="stateOptions" class="state-filter">
            <template #default="{ item }">
              <span>{{ item.label }}</span>
              <b>{{ item.count }}</b>
            </template>
          </el-segmented>
        </div>

        <el-table
          :data="visibleJobs"
          height="520"
          class="jobs-table"
          :row-class-name="rowClassName"
          @row-click="selectJob"
        >
          <el-table-column label="顺序" width="72">
            <template #default="{ row }">
              <span class="order-pill">{{ row.sort_index < 999999 ? `p${String(row.sort_index).padStart(2, '0')}` : '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="任务" min-width="260">
            <template #default="{ row }">
              <div class="job-cell">
                <strong>{{ row.slug || row.job_id }}</strong>
                <span>{{ row.job_id }}</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="120">
            <template #default="{ row }">
              <el-tag :type="stateType(row.state)" effect="plain">{{ stateLabel(row.state) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="尝试" width="150">
            <template #default="{ row }">{{ attemptsText(row) }}</template>
          </el-table-column>
          <el-table-column label="更新时间" width="190">
            <template #default="{ row }">{{ formatTime(row.updated_at_iso) }}</template>
          </el-table-column>
          <el-table-column label="owner" min-width="210">
            <template #default="{ row }">{{ row.owner || '-' }}</template>
          </el-table-column>
        </el-table>
      </div>

      <aside class="detail-panel">
        <template v-if="selectedJob">
          <div class="selected-title">
            <span class="job-id">{{ selectedJob.job_id }}</span>
            <h2>{{ selectedJob.slug }}</h2>
            <el-tag :type="stateType(selectedJob.state)" effect="dark">{{ stateLabel(selectedJob.state) }}</el-tag>
          </div>

          <div class="stage-track">
            <div
              v-for="step in selectedJob.steps"
              :key="step.key"
              class="stage-node"
              :class="step.status"
            >
              <div class="stage-dot">
                <el-icon><component :is="stageMeta[step.status]?.icon || Clock" /></el-icon>
              </div>
              <div>
                <strong>{{ step.label }}</strong>
                <span>{{ stageMeta[step.status]?.label || step.status }}</span>
                <small>{{ formatTime(step.time) }}</small>
              </div>
            </div>
          </div>

          <dl class="detail-list">
            <div>
              <dt>标题</dt>
              <dd>{{ selectedJob.title }}</dd>
            </div>
            <div>
              <dt>worker</dt>
              <dd>{{ selectedJob.owner || '-' }}</dd>
            </div>
            <div>
              <dt>心跳</dt>
              <dd>{{ heartbeatAge(selectedJob) }}</dd>
            </div>
            <div>
              <dt>租约</dt>
              <dd :class="{ expired: selectedJob.lease_expired }">{{ leaseText(selectedJob) }}</dd>
            </div>
            <div>
              <dt>artifact</dt>
              <dd>{{ selectedJob.paths?.artifact_output || '-' }}</dd>
            </div>
            <div v-if="selectedJob.last_error">
              <dt>错误</dt>
              <dd class="error-text">{{ selectedJob.last_error.message }}</dd>
            </div>
          </dl>

          <div class="events">
            <div class="events-title">
              <el-icon><Document /></el-icon>
              最近事件
            </div>
            <div v-if="selectedJob.recent_events?.length" class="event-list">
              <div v-for="event in selectedJob.recent_events" :key="`${event.epoch}-${event.event}-${event.stage}`" class="event-item">
                <span>{{ shortTime(event.time) }}</span>
                <strong>{{ eventText(event) }}</strong>
              </div>
            </div>
            <el-empty v-else description="暂无事件日志" :image-size="72" />
          </div>
        </template>
        <el-empty v-else description="暂无队列任务" />
      </aside>
    </section>
  </div>
</template>

<style scoped>
.queue-dashboard {
  width: 100%;
  min-height: 100vh;
  padding: 6px 0 28px;
  color: #1f2937;
}

.queue-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 24px;
  padding: 18px 4px 20px;
}

.eyebrow {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #2563eb;
  font-size: 13px;
  font-weight: 700;
  letter-spacing: 0;
  text-transform: uppercase;
}

.queue-header h1 {
  margin: 6px 0 8px;
  font-size: 28px;
  line-height: 1.25;
  color: #111827;
}

.queue-header p,
.panel-header p {
  margin: 0;
  color: #6b7280;
  font-size: 14px;
}

.queue-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.status-alert {
  margin-bottom: 14px;
}

.contract-strip {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 10px;
  margin-bottom: 10px;
}

.contract-item.wide {
  grid-column: span 2;
}

.contract-item,
.command-strip > div {
  min-width: 0;
  background: #ffffff;
  border: 1px solid #dbe3ef;
  border-radius: 8px;
  padding: 12px 14px;
  display: grid;
  gap: 4px;
}

.contract-item span,
.command-strip span {
  color: #64748b;
  font-size: 12px;
  font-weight: 700;
}

.contract-item strong {
  color: #0f172a;
  font-size: 13px;
  line-height: 1.4;
  overflow-wrap: anywhere;
}

.command-strip {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 14px;
}

.command-strip code {
  color: #0f172a;
  background: #f1f5f9;
  border-radius: 6px;
  padding: 6px 8px;
  font-size: 12px;
  white-space: normal;
  overflow-wrap: anywhere;
}

.summary-strip {
  display: grid;
  grid-template-columns: repeat(5, minmax(96px, 1fr)) minmax(220px, 1.5fr);
  gap: 10px;
  margin-bottom: 14px;
}

.summary-item,
.summary-progress,
.work-panel,
.jobs-panel,
.detail-panel,
.pipeline-step {
  background: #ffffff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
}

.summary-item,
.summary-progress {
  min-height: 82px;
  padding: 14px 16px;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 4px;
}

.summary-item span,
.summary-progress span {
  color: #6b7280;
  font-size: 13px;
}

.summary-item strong {
  color: #111827;
  font-size: 28px;
  line-height: 1;
}

.summary-item.danger strong {
  color: #dc2626;
}

.pipeline {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 14px;
}

.pipeline-step {
  min-height: 110px;
  padding: 16px;
  display: flex;
  gap: 12px;
  align-items: center;
}

.pipeline-icon {
  width: 42px;
  height: 42px;
  flex: 0 0 42px;
  border-radius: 8px;
  background: #eef2ff;
  color: #2563eb;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 22px;
}

.pipeline-body {
  min-width: 0;
  display: grid;
  gap: 2px;
  text-align: left;
}

.pipeline-body span {
  color: #111827;
  font-size: 15px;
  font-weight: 700;
}

.pipeline-body strong {
  color: #111827;
  font-size: 26px;
  line-height: 1.1;
}

.pipeline-body small {
  color: #6b7280;
  font-size: 12px;
}

.queue-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 14px;
  margin-bottom: 14px;
}

.work-panel,
.jobs-panel,
.detail-panel {
  padding: 16px;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  margin-bottom: 14px;
}

.panel-header h2,
.selected-title h2 {
  margin: 0;
  color: #111827;
  font-size: 18px;
  line-height: 1.35;
}

.running-list,
.todo-list {
  display: grid;
  gap: 10px;
}

.running-job,
.todo-item {
  width: 100%;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  background: #f9fafb;
  color: #1f2937;
  text-align: left;
  cursor: pointer;
  transition: border-color 0.18s, background 0.18s;
}

.running-job {
  padding: 14px;
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 12px;
}

.running-job:hover,
.todo-item:hover,
.running-job.active,
.todo-item.active {
  border-color: #2563eb;
  background: #eff6ff;
}

.job-id {
  color: #2563eb;
  font-size: 12px;
  font-weight: 700;
}

.running-job strong,
.todo-item strong {
  display: block;
  margin-top: 2px;
  color: #111827;
  font-size: 14px;
  line-height: 1.35;
  overflow-wrap: anywhere;
}

.running-job dl {
  grid-column: 1 / -1;
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
  margin: 0;
}

.running-job dt,
.detail-list dt {
  color: #6b7280;
  font-size: 12px;
}

.running-job dd,
.detail-list dd {
  margin: 0;
  color: #1f2937;
  font-size: 13px;
  overflow-wrap: anywhere;
}

.todo-item {
  min-height: 54px;
  padding: 10px 12px;
  display: grid;
  grid-template-columns: 50px minmax(0, 1fr) auto;
  align-items: center;
  gap: 10px;
}

.todo-item > span,
.order-pill {
  color: #475569;
  font-size: 12px;
  font-weight: 700;
  background: #e2e8f0;
  border-radius: 999px;
  padding: 3px 8px;
  width: fit-content;
}

.detail-layout {
  display: grid;
  grid-template-columns: minmax(0, 1.6fr) minmax(340px, 0.8fr);
  gap: 14px;
}

.state-filter {
  max-width: 100%;
  overflow-x: auto;
}

.state-filter :deep(.el-segmented__item-label) {
  display: flex;
  align-items: center;
  gap: 6px;
  white-space: nowrap;
}

.state-filter b {
  font-size: 12px;
  color: #6b7280;
}

.jobs-table {
  width: 100%;
}

.jobs-table :deep(.selected-row) {
  --el-table-tr-bg-color: #eff6ff;
}

.job-cell {
  display: grid;
  gap: 2px;
  text-align: left;
}

.job-cell strong {
  color: #111827;
  font-size: 14px;
  overflow-wrap: anywhere;
}

.job-cell span {
  color: #64748b;
  font-size: 12px;
}

.selected-title {
  display: grid;
  gap: 8px;
  margin-bottom: 18px;
}

.stage-track {
  display: grid;
  gap: 12px;
  margin-bottom: 18px;
  position: relative;
}

.stage-node {
  display: grid;
  grid-template-columns: 34px minmax(0, 1fr);
  gap: 10px;
  align-items: start;
}

.stage-dot {
  width: 34px;
  height: 34px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #e5e7eb;
  color: #6b7280;
}

.stage-node.success .stage-dot {
  background: #dcfce7;
  color: #16a34a;
}

.stage-node.running .stage-dot {
  background: #dbeafe;
  color: #2563eb;
}

.stage-node.failed .stage-dot {
  background: #fee2e2;
  color: #dc2626;
}

.stage-node strong {
  display: block;
  color: #111827;
  font-size: 14px;
}

.stage-node span,
.stage-node small {
  display: block;
  color: #6b7280;
  font-size: 12px;
}

.stage-node.running .el-icon {
  animation: spin 1.2s linear infinite;
}

.detail-list {
  display: grid;
  gap: 10px;
  margin: 0 0 18px;
}

.detail-list div {
  display: grid;
  gap: 2px;
}

.expired,
.error-text {
  color: #dc2626 !important;
}

.events-title {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 10px;
  color: #111827;
  font-weight: 700;
}

.event-list {
  display: grid;
  gap: 8px;
}

.event-item {
  display: grid;
  grid-template-columns: 72px minmax(0, 1fr);
  gap: 8px;
  padding: 9px 10px;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  background: #f9fafb;
}

.event-item span {
  color: #64748b;
  font-size: 12px;
}

.event-item strong {
  color: #1f2937;
  font-size: 12px;
  overflow-wrap: anywhere;
}

@keyframes spin {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}

@media screen and (max-width: 1180px) {
  .summary-strip,
  .contract-strip,
  .command-strip,
  .pipeline,
  .queue-grid,
  .detail-layout {
    grid-template-columns: 1fr;
  }

  .summary-strip {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .contract-item.wide {
    grid-column: auto;
  }
}

@media screen and (max-width: 720px) {
  .queue-header,
  .panel-header {
    flex-direction: column;
  }

  .queue-actions {
    justify-content: flex-start;
  }

  .queue-header h1 {
    font-size: 24px;
  }

  .summary-strip {
    grid-template-columns: 1fr;
  }

  .running-job dl {
    grid-template-columns: 1fr;
  }

  .todo-item {
    grid-template-columns: 44px minmax(0, 1fr);
  }

  .todo-item .el-tag {
    grid-column: 2;
    width: fit-content;
  }
}
</style>
