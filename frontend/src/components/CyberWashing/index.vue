<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Delete, FolderOpened, Document, RefreshRight, CopyDocument, Download } from '@element-plus/icons-vue'
import { washArticles } from '../../apis/washingService'
import { WASHING_PROMPT_PRESETS } from '../../constants'
// Types are imported from types.ts but used as plain JS here
import MarkdownIt from 'markdown-it'

const md = new MarkdownIt()

// ─── Prompt Presets ───
const promptPresets = WASHING_PROMPT_PRESETS
const selectedPreset = ref(promptPresets[0].label)

const applyPreset = (label) => {
  const preset = promptPresets.find(p => p.label === label)
  if (preset) {
    contextPrompt.value = preset.context_prompt
    refinementPrompt.value = preset.refinement_prompt
    selectedPreset.value = label
  }
}

// ─── Article URLs ───
const urls = ref([{ value: '' }])

const addUrl = () => {
  urls.value.push({ value: '' })
}

const removeUrl = (index) => {
  if (urls.value.length <= 1) {
    ElMessage.warning('至少保留一个URL输入框')
    return
  }
  urls.value.splice(index, 1)
}

// ─── Code Projects ───
const codeProjects = ref([])
const showProjectDialog = ref(false)
const newProjectLabel = ref('')
const newProjectPath = ref('')
const newProjectPatterns = ref('')

const openProjectDialog = () => {
  newProjectLabel.value = ''
  newProjectPath.value = ''
  newProjectPatterns.value = ''
  showProjectDialog.value = true
}

const addProject = () => {
  if (!newProjectLabel.value.trim()) {
    ElMessage.warning('请输入工程名称')
    return
  }
  if (!newProjectPath.value.trim()) {
    ElMessage.warning('请输入工程路径')
    return
  }
  const project = {
    label: newProjectLabel.value.trim(),
    path: newProjectPath.value.trim()
  }
  if (newProjectPatterns.value.trim()) {
    project.file_patterns = newProjectPatterns.value.split(',').map(p => p.trim()).filter(p => p)
  }
  codeProjects.value.push(project)
  showProjectDialog.value = false
  ElMessage.success(`已添加工程: ${project.label}`)
}

const removeProject = (index) => {
  codeProjects.value.splice(index, 1)
}

// ─── Prompts ───
const contextPrompt = ref('')
const refinementPrompt = ref('')

// ─── Options ───
const styleOptions = [
  { value: 'deep', label: '深度学习' },
  { value: 'concise', label: '精简' },
  { value: 'comprehensive', label: '全面' }
]
const selectedStyle = ref('deep')
const timeoutValue = ref(600)
const maxTokensValue = ref(16384)

// ─── Processing State ───
const isProcessing = ref(false)
const progressPercent = ref(0)
const progressText = ref('')

// ─── Results ───
const extractedArticles = ref([])
const codeFiles = ref([])
const domainSummary = ref('')
const refinedMarkdown = ref('')
const activeResultTab = ref('final')

// ─── Computed ───
const canStart = computed(() => {
  const hasValidUrl = urls.value.some(u => u.value.trim().length > 0)
  return hasValidUrl && contextPrompt.value.trim().length > 0 && refinementPrompt.value.trim().length > 0 && !isProcessing.value
})

const domainSummaryHtml = computed(() => md.render(domainSummary.value))
const refinedHtml = computed(() => md.render(refinedMarkdown.value))

// ─── Actions ───
const startWashing = async () => {
  const validUrls = urls.value
    .map(u => u.value.trim())
    .filter(u => u.length > 0)

  if (validUrls.length === 0) {
    ElMessage.warning('请至少输入一个文章URL')
    return
  }

  for (const url of validUrls) {
    if (!/^https?:\/\//.test(url)) {
      ElMessage.error(`无效的URL格式: ${url}`)
      return
    }
  }

  if (!contextPrompt.value.trim()) {
    ElMessage.warning('请填写上下文提示')
    return
  }

  if (!refinementPrompt.value.trim()) {
    ElMessage.warning('请填写深化提示')
    return
  }

  isProcessing.value = true
  progressPercent.value = 5
  progressText.value = '正在提取文章...'
  extractedArticles.value = []
  codeFiles.value = []
  domainSummary.value = ''
  refinedMarkdown.value = ''

  try {
    progressPercent.value = 15
    progressText.value = '正在分析要点...'

    const request = {
      articles: validUrls.map(u => ({ url: u })),
      context_prompt: contextPrompt.value.trim(),
      refinement_prompt: refinementPrompt.value.trim(),
      style: selectedStyle.value,
      timeout: timeoutValue.value,
      max_tokens: maxTokensValue.value
    }

    if (codeProjects.value.length > 0) {
      request.code_projects = codeProjects.value
    }

    progressPercent.value = 30
    progressText.value = 'Stage 1: 理解领域知识...'

    const response = await washArticles(request)

    progressPercent.value = 85
    progressText.value = 'Stage 2: 深度知识融合...'

    if (response.success && response.data) {
      extractedArticles.value = response.data.extracted_articles || []
      codeFiles.value = response.data.code_files || []
      domainSummary.value = response.data.domain_summary || ''
      refinedMarkdown.value = response.data.refined_output || ''

      progressPercent.value = 95
      progressText.value = '正在整理结果...'

      setTimeout(() => {
        progressPercent.value = 100
        progressText.value = '洗稿完成'
        isProcessing.value = false
        ElMessage.success('洗稿完成')
      }, 300)
    } else {
      throw new Error(response.error?.message || '洗稿请求失败')
    }
  } catch (error) {
    console.error('洗稿失败:', error)
    ElMessage.error(error.message || '洗稿失败，请重试')
    isProcessing.value = false
    progressPercent.value = 0
    progressText.value = ''
  }
}

const resetAll = () => {
  urls.value = [{ value: '' }]
  codeProjects.value = []
  selectedStyle.value = 'deep'
  timeoutValue.value = 600
  maxTokensValue.value = 16384
  isProcessing.value = false
  progressPercent.value = 0
  progressText.value = ''
  extractedArticles.value = []
  codeFiles.value = []
  domainSummary.value = ''
  refinedMarkdown.value = ''
  activeResultTab.value = 'final'
  applyPreset(promptPresets[0].label)
}

const copyMarkdown = async () => {
  try {
    await navigator.clipboard.writeText(refinedMarkdown.value)
    ElMessage.success('已复制到剪贴板')
  } catch {
    ElMessage.error('复制失败')
  }
}

const downloadMarkdown = () => {
  const blob = new Blob([refinedMarkdown.value], { type: 'text/markdown;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = 'cyber-washing-output.md'
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
  ElMessage.success('下载已开始')
}

// Initialize with default preset
onMounted(() => {
  applyPreset(promptPresets[0].label)
})
</script>

<template>
  <div class="cyber-washing-workbench">
    <!-- Header -->
    <div class="workbench-header">
      <div class="header-content">
        <h1 class="workbench-title">赛博洗稿工作台</h1>
        <p class="workbench-subtitle">输入多篇文章URL与本地代码工程，AI将提取内容并融合为深度知识笔记</p>
      </div>
    </div>

    <!-- Main layout: left config + right prompts -->
    <div class="workbench-body" v-if="!isProcessing && !refinedMarkdown">
      <!-- Left panel: Sources -->
      <div class="panel panel-sources">
        <el-card shadow="never" class="source-card">
          <template #header>
            <div class="card-header">
              <span class="card-title">文章管理</span>
              <el-button type="primary" :icon="Plus" size="small" plain @click="addUrl">添加URL</el-button>
            </div>
          </template>

          <div class="url-list">
            <div v-for="(item, index) in urls" :key="index" class="url-row">
              <el-input
                v-model="item.value"
                placeholder="https://example.com/article"
                clearable
                class="url-input"
              >
                <template #prefix>
                  <el-icon><Document /></el-icon>
                </template>
              </el-input>
              <el-button
                v-if="urls.length > 1"
                :icon="Delete"
                type="danger"
                plain
                circle
                size="small"
                @click="removeUrl(index)"
              />
            </div>
          </div>

          <div class="source-divider"></div>

          <div class="projects-section">
            <div class="card-title" style="margin-bottom: 12px;">本地工程</div>
            <div v-if="codeProjects.length === 0" class="projects-empty">
              <el-button type="primary" :icon="FolderOpened" plain @click="openProjectDialog">添加工程</el-button>
            </div>
            <div v-else class="projects-list">
              <div v-for="(proj, idx) in codeProjects" :key="idx" class="project-tag-row">
                <el-tag closable effect="plain" @close="removeProject(idx)" class="project-tag">
                  <span class="project-tag-label">{{ proj.label }}</span>
                  <span class="project-tag-path">{{ proj.path }}</span>
                </el-tag>
              </div>
              <el-button type="primary" :icon="Plus" size="small" plain @click="openProjectDialog" style="margin-top: 8px;">
                添加工程
              </el-button>
            </div>
          </div>
        </el-card>
      </div>

      <!-- Right panel: Prompts & Options -->
      <div class="panel panel-config">
        <el-card shadow="never" class="config-card">
          <template #header>
            <div class="card-header">
              <span class="card-title">Prompt 配置</span>
            </div>
          </template>

          <div class="prompt-section">
            <label class="prompt-label">Prompt 预设模板</label>
            <div class="preset-tabs">
              <button
                v-for="preset in promptPresets"
                :key="preset.label"
                class="preset-tab"
                :class="{ active: selectedPreset === preset.label }"
                @click="applyPreset(preset.label)"
                :title="preset.description"
              >
                {{ preset.label }}
              </button>
            </div>
          </div>

          <div class="prompt-section">
            <label class="prompt-label">上下文提示 (Stage 1)</label>
            <el-input
              v-model="contextPrompt"
              type="textarea"
              :rows="4"
              placeholder="描述这些文章是关于什么的，帮助AI理解背景。例如：这些文章是关于Unreal Lyra游戏框架的技术分析..."
              class="prompt-textarea"
            />
          </div>

          <div class="prompt-section">
            <label class="prompt-label">深化提示 (Stage 2)</label>
            <el-input
              v-model="refinementPrompt"
              type="textarea"
              :rows="4"
              placeholder="用于深化提取的prompt。例如：请从技术原理、应用场景、优缺点等维度深度整理..."
              class="prompt-textarea"
            />
          </div>

          <div class="options-row">
            <div class="option-item">
              <label class="option-label">风格</label>
              <el-select v-model="selectedStyle" size="default" style="width: 140px;">
                <el-option
                  v-for="opt in styleOptions"
                  :key="opt.value"
                  :label="opt.label"
                  :value="opt.value"
                />
              </el-select>
            </div>
            <div class="option-item">
              <label class="option-label">超时(秒)</label>
              <el-input-number v-model="timeoutValue" :min="60" :max="3600" :step="60" size="default" style="width: 120px;" />
            </div>
            <div class="option-item">
              <label class="option-label">Token</label>
              <el-input-number v-model="maxTokensValue" :min="1024" :max="65536" :step="1024" size="default" style="width: 130px;" />
            </div>
          </div>

          <div class="action-row">
            <el-button
              type="primary"
              size="large"
              :disabled="!canStart"
              @click="startWashing"
              class="start-btn"
            >
              开始洗稿
            </el-button>
            <el-button
              size="large"
              :icon="RefreshRight"
              @click="resetAll"
            >
              重置
            </el-button>
          </div>
        </el-card>
      </div>
    </div>

    <!-- Processing progress -->
    <div v-if="isProcessing" class="processing-wrapper">
      <div class="processing-card">
        <div class="processing-icon">
          <svg viewBox="0 0 1024 1024" width="48" height="48" class="spin-icon">
            <path d="M512 64a448 448 0 1 0 448 448A448 448 0 0 0 512 64zm0 820a372 372 0 1 1 372-372A372 372 0 0 1 512 884z" fill="currentColor" opacity="0.3"/>
            <path d="M512 64v76a372 372 0 0 1 0 744v76a448 448 0 0 0 0-896z" fill="currentColor"/>
          </svg>
        </div>
        <h3 class="processing-title">正在处理</h3>
        <p class="processing-text">{{ progressText }}</p>
        <el-progress :percentage="progressPercent" :stroke-width="12" :format="(p) => p + '%'" />
      </div>
    </div>

    <!-- Results -->
    <div v-if="!isProcessing && refinedMarkdown" class="result-wrapper">
      <div class="result-header-bar">
        <h2 class="result-title">洗稿结果</h2>
        <div class="result-actions">
          <el-button type="primary" plain size="small" :icon="CopyDocument" @click="copyMarkdown">复制</el-button>
          <el-button plain size="small" :icon="Download" @click="downloadMarkdown">下载Markdown</el-button>
          <el-button plain size="small" :icon="RefreshRight" @click="resetAll">重新开始</el-button>
        </div>
      </div>

      <el-tabs v-model="activeResultTab" class="result-tabs">
        <!-- Tab: Extracted Articles -->
        <el-tab-pane label="文章原文" name="sources">
          <el-collapse v-if="extractedArticles.length > 0" class="articles-collapse">
            <el-collapse-item
              v-for="(article, idx) in extractedArticles"
              :key="idx"
              :name="String(idx)"
            >
              <template #title>
                <div class="article-collapse-title">
                  <el-tag size="small" type="info" effect="plain">文章 {{ idx + 1 }}</el-tag>
                  <span class="article-title-text">{{ article.title || article.url }}</span>
                </div>
              </template>
              <div class="article-meta-row" v-if="article.metadata">
                <el-tag v-if="article.metadata.author" size="small" effect="plain" type="success">{{ article.metadata.author }}</el-tag>
                <el-tag v-if="article.metadata.date" size="small" effect="plain">{{ article.metadata.date }}</el-tag>
                <el-tag v-if="article.metadata.sitename" size="small" effect="plain" type="warning">{{ article.metadata.sitename }}</el-tag>
              </div>
              <div class="article-url-row">
                <a :href="article.url" target="_blank" rel="noopener">{{ article.url }}</a>
              </div>
              <div class="article-excerpt" v-if="article.key_points">
                <strong>关键要点：</strong>{{ article.key_points }}
              </div>
              <div class="markdown-body" v-html="md.render(article.markdown_content || '')"></div>
            </el-collapse-item>
          </el-collapse>
          <el-empty v-else description="暂无提取的文章" />
        </el-tab-pane>

        <!-- Tab: Domain Summary -->
        <el-tab-pane label="领域脉络" name="domain">
          <div v-if="domainSummary" class="markdown-body" v-html="domainSummaryHtml"></div>
          <el-empty v-else description="暂无领域脉络" />
        </el-tab-pane>

        <!-- Tab: Final Output -->
        <el-tab-pane label="最终笔记" name="final">
          <div class="markdown-body final-output" v-html="refinedHtml"></div>
        </el-tab-pane>

        <!-- Tab: Code Files -->
        <el-tab-pane label="源码参考" name="code">
          <div v-if="codeFiles.length > 0" class="code-files-list">
            <div v-for="(file, idx) in codeFiles" :key="idx" class="code-file-item">
              <div class="code-file-header">
                <el-tag
                  size="small"
                  effect="plain"
                  :color="getLanguageColor(file.language)"
                  style="color: #fff; border: none;"
                >
                  {{ file.language }}
                </el-tag>
                <span class="code-file-project">{{ file.project_label }}</span>
                <span class="code-file-path">{{ file.relative_path }}</span>
              </div>
              <pre class="code-file-content"><code>{{ file.content }}</code></pre>
            </div>
          </div>
          <el-empty v-else description="暂无代码文件" />
        </el-tab-pane>
      </el-tabs>
    </div>

    <!-- Add Project Dialog -->
    <el-dialog v-model="showProjectDialog" title="添加本地工程" width="480px" :close-on-click-modal="false">
      <div class="dialog-form">
        <div class="dialog-form-item">
          <label class="dialog-label">工程名称</label>
          <el-input v-model="newProjectLabel" placeholder="例如: Lyra项目" />
        </div>
        <div class="dialog-form-item">
          <label class="dialog-label">工程路径</label>
          <el-input v-model="newProjectPath" placeholder="例如: D:\Lyra" />
        </div>
        <div class="dialog-form-item">
          <label class="dialog-label">文件模式 <span class="dialog-hint">（逗号分隔，可选）</span></label>
          <el-input v-model="newProjectPatterns" placeholder="例如: *.cpp,*.h,*.cs" />
        </div>
      </div>
      <template #footer>
        <el-button @click="showProjectDialog = false">取消</el-button>
        <el-button type="primary" @click="addProject">添加</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.cyber-washing-workbench {
  width: 100%;
  min-height: calc(100vh - 56px);
  background: #f5f7fa;
  display: flex;
  flex-direction: column;
}

/* ─── Header ─── */
.workbench-header {
  background: linear-gradient(135deg, #1a1a2e 0%, #16213e 60%, #0f3460 100%);
  padding: 32px 40px 28px;
  color: #fff;
}

.header-content {
  max-width: 1400px;
  margin: 0 auto;
  width: 100%;
}

.workbench-title {
  font-size: 26px;
  font-weight: 800;
  margin: 0 0 6px 0;
  letter-spacing: 0.5px;
  color: #fff;
}

.workbench-subtitle {
  font-size: 14px;
  margin: 0;
  color: rgba(255, 255, 255, 0.65);
  font-weight: 400;
}

/* ─── Body Layout ─── */
.workbench-body {
  display: flex;
  gap: 24px;
  padding: 24px 40px;
  max-width: 1400px;
  margin: 0 auto;
  width: 100%;
  box-sizing: border-box;
  flex: 1;
}

.panel-sources {
  flex: 0 0 420px;
  min-width: 0;
}

.panel-config {
  flex: 1;
  min-width: 0;
}

/* ─── Cards ─── */
.source-card :deep(.el-card__header),
.config-card :deep(.el-card__header) {
  padding: 16px 20px;
  border-bottom: 1px solid #f0f0f0;
  background: #fafbfc;
}

.source-card :deep(.el-card__body),
.config-card :deep(.el-card__body) {
  padding: 20px;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.card-title {
  font-size: 15px;
  font-weight: 700;
  color: #1a1a2e;
}

/* ─── URL List ─── */
.url-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.url-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.url-input {
  flex: 1;
}

.source-divider {
  height: 1px;
  background: #f0f0f0;
  margin: 20px 0 16px;
}

/* ─── Projects ─── */
.projects-empty {
  display: flex;
  justify-content: center;
  padding: 16px 0;
}

.projects-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.project-tag-row {
  display: flex;
  align-items: center;
}

.project-tag {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: auto;
  padding: 8px 12px;
}

.project-tag-label {
  font-weight: 600;
  margin-right: 8px;
}

.project-tag-path {
  color: #909399;
  font-size: 12px;
  font-family: 'Consolas', 'Monaco', monospace;
}

/* ─── Prompts ─── */
.prompt-section {
  margin-bottom: 20px;
}

.prompt-label {
  display: block;
  font-size: 13px;
  font-weight: 600;
  color: #1a1a2e;
  margin-bottom: 8px;
}

/* ─── Preset Tabs ─── */
.preset-tabs {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.preset-tab {
  padding: 6px 14px;
  border: 1px solid #dcdfe6;
  border-radius: 6px;
  background: #fff;
  color: #606266;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
  white-space: nowrap;
}

.preset-tab:hover {
  border-color: #409eff;
  color: #409eff;
}

.preset-tab.active {
  background: #409eff;
  border-color: #409eff;
  color: #fff;
  font-weight: 600;
}

.prompt-textarea :deep(.el-textarea__inner) {
  font-size: 13px;
  line-height: 1.6;
}

/* ─── Options ─── */
.options-row {
  display: flex;
  gap: 20px;
  margin-bottom: 24px;
  flex-wrap: wrap;
}

.option-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.option-label {
  font-size: 12px;
  font-weight: 600;
  color: #606266;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

/* ─── Actions ─── */
.action-row {
  display: flex;
  gap: 12px;
  justify-content: center;
  padding-top: 8px;
}

.start-btn {
  min-width: 160px;
  font-weight: 600;
}

/* ─── Processing ─── */
.processing-wrapper {
  display: flex;
  align-items: center;
  justify-content: center;
  flex: 1;
  padding: 80px 40px;
}

.processing-card {
  background: #fff;
  border-radius: 16px;
  padding: 48px 56px;
  box-shadow: 0 4px 24px rgba(0, 0, 0, 0.06);
  text-align: center;
  min-width: 400px;
}

.processing-icon {
  margin-bottom: 16px;
  color: #409EFF;
}

.spin-icon {
  animation: spin 1.5s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.processing-title {
  font-size: 20px;
  font-weight: 700;
  color: #1a1a2e;
  margin: 0 0 8px 0;
}

.processing-text {
  font-size: 14px;
  color: #6b7280;
  margin: 0 0 24px 0;
}

/* ─── Results ─── */
.result-wrapper {
  padding: 24px 40px;
  max-width: 1400px;
  margin: 0 auto;
  width: 100%;
  box-sizing: border-box;
}

.result-header-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
  flex-wrap: wrap;
  gap: 12px;
}

.result-title {
  font-size: 22px;
  font-weight: 800;
  color: #1a1a2e;
  margin: 0;
}

.result-actions {
  display: flex;
  gap: 8px;
}

.result-tabs :deep(.el-tabs__header) {
  margin-bottom: 20px;
}

.result-tabs :deep(.el-tabs__item) {
  font-weight: 600;
  font-size: 14px;
}

/* ─── Article Collapse ─── */
.articles-collapse {
  border: none;
}

.article-collapse-title {
  display: flex;
  align-items: center;
  gap: 8px;
}

.article-title-text {
  font-weight: 600;
  color: #1a1a2e;
  font-size: 14px;
}

.article-meta-row {
  display: flex;
  gap: 6px;
  margin-bottom: 8px;
  flex-wrap: wrap;
}

.article-url-row {
  margin-bottom: 8px;
}

.article-url-row a {
  color: #409EFF;
  text-decoration: none;
  font-size: 13px;
}

.article-url-row a:hover {
  text-decoration: underline;
}

.article-excerpt {
  font-size: 13px;
  color: #606266;
  margin-bottom: 12px;
  padding: 8px 12px;
  background: #f8f9fa;
  border-radius: 6px;
  border-left: 3px solid #409EFF;
}

/* ─── Markdown Rendering ─── */
.markdown-body {
  font-size: 14px;
  line-height: 1.75;
  color: #23272f;
  word-break: break-word;
}

.markdown-body :deep(h1),
.markdown-body :deep(h2),
.markdown-body :deep(h3),
.markdown-body :deep(h4) {
  margin-top: 1.2em;
  margin-bottom: 0.6em;
  font-weight: 700;
  color: #1a1a2e;
}

.markdown-body :deep(p) {
  margin: 0.5em 0;
}

.markdown-body :deep(ul),
.markdown-body :deep(ol) {
  padding-left: 1.5em;
  margin: 0.5em 0;
}

.markdown-body :deep(code) {
  background: #f3f4f6;
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 0.9em;
}

.markdown-body :deep(pre) {
  background: #f8f9fa;
  padding: 1em;
  border-radius: 8px;
  overflow-x: auto;
}

.markdown-body :deep(blockquote) {
  border-left: 4px solid #409EFF;
  padding-left: 1em;
  margin: 0.5em 0;
  color: #6b7280;
}

.final-output {
  background: #fff;
  border-radius: 12px;
  padding: 28px 32px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.04);
  border: 1px solid #f0f0f0;
}

/* ─── Code Files ─── */
.code-files-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.code-file-item {
  background: #fff;
  border-radius: 10px;
  border: 1px solid #f0f0f0;
  overflow: hidden;
}

.code-file-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  background: #fafbfc;
  border-bottom: 1px solid #f0f0f0;
  font-size: 13px;
}

.code-file-project {
  font-weight: 600;
  color: #1a1a2e;
}

.code-file-path {
  color: #909399;
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 12px;
}

.code-file-content {
  margin: 0;
  padding: 16px;
  background: #f8f9fa;
  overflow-x: auto;
  font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
  font-size: 13px;
  line-height: 1.6;
  color: #23272f;
  max-height: 400px;
  overflow-y: auto;
}

/* ─── Dialog ─── */
.dialog-form {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.dialog-form-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.dialog-label {
  font-size: 13px;
  font-weight: 600;
  color: #1a1a2e;
}

.dialog-hint {
  font-weight: 400;
  color: #909399;
  font-size: 12px;
}

/* ─── Responsive ─── */
@media screen and (max-width: 1024px) {
  .workbench-body {
    flex-direction: column;
    padding: 16px;
  }

  .panel-sources {
    flex: none;
    width: 100%;
  }

  .panel-config {
    flex: none;
    width: 100%;
  }

  .workbench-header {
    padding: 24px 16px 20px;
  }

  .result-wrapper {
    padding: 16px;
  }

  .processing-card {
    min-width: auto;
    padding: 32px 24px;
  }
}

@media screen and (max-width: 768px) {
  .workbench-title {
    font-size: 20px;
  }

  .workbench-subtitle {
    font-size: 13px;
  }

  .options-row {
    flex-direction: column;
    gap: 12px;
  }

  .result-header-bar {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>