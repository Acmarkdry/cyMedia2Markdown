<script setup>
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { VideoCameraFilled, EditPen } from '@element-plus/icons-vue'
import AppSidebar from './components/AppSidebar.vue'
import VideoToMarkdown from './components/VideoToMarkdown/index.vue'
import TaskDetail from './components/VideoToMarkdown/TaskDetail.vue'
import QueueDashboard from './components/QueueDashboard.vue'
import CyberWashing from './components/CyberWashing/index.vue'
import { eventBus } from './utils/eventBus'

const activeTab = ref('video')
const activeMenu = ref('new-task')
const isChatOpen = ref(false)
const selectedTask = ref(null)

const isTaskDetailOpen = ref(false)
const currentTask = ref(null)

const previousMenu = ref('new-task')

const handleMenuSelect = (key) => {
  if (key.startsWith('task-')) {
    const taskId = parseInt(key.replace('task-', ''))
    return;
  }

  isTaskDetailOpen.value = false
  currentTask.value = null
  activeMenu.value = key
}

const handleViewTask = (task) => {
  currentTask.value = task
  isTaskDetailOpen.value = true
  previousMenu.value = activeMenu.value
  activeMenu.value = 'task-detail'
}

onMounted(() => {
  eventBus.on('view-task', handleViewTask)
})
onBeforeUnmount(() => {
  eventBus.off('view-task', handleViewTask)
})
</script>

<template>
  <div class="app-root">
    <!-- Top navigation bar -->
    <header class="top-nav">
      <div class="nav-brand">
        <span class="nav-logo">🎬</span>
        <span class="nav-title">Media2Markdown</span>
      </div>
      <div class="nav-tabs">
        <button
          class="nav-tab"
          :class="{ active: activeTab === 'video' }"
          @click="activeTab = 'video'"
        >
          <el-icon style="margin-right: 6px;"><VideoCameraFilled /></el-icon>
          视频工作台
        </button>
        <button
          class="nav-tab"
          :class="{ active: activeTab === 'washing' }"
          @click="activeTab = 'washing'"
        >
          <el-icon style="margin-right: 6px;"><EditPen /></el-icon>
          赛博洗稿
        </button>
      </div>
      <div class="nav-spacer"></div>
    </header>

    <!-- Main content area -->
    <div class="app-body">
      <!-- Video mode: sidebar + content -->
      <template v-if="activeTab === 'video'">
        <AppSidebar :active-menu="activeMenu" @menu-select="handleMenuSelect" @view-task="handleViewTask" />
        <div class="content-area">
          <div class="content-wrapper">
            <template v-if="isTaskDetailOpen && currentTask">
              <TaskDetail :task="currentTask" />
            </template>
            <template v-else-if="activeMenu === 'new-task'">
              <VideoToMarkdown />
            </template>
            <template v-else-if="activeMenu === 'queue-dashboard'">
              <QueueDashboard />
            </template>
            <template v-else>
            </template>
          </div>
        </div>
      </template>

      <!-- Washing mode: full-width -->
      <template v-else-if="activeTab === 'washing'">
        <CyberWashing />
      </template>
    </div>
  </div>
</template>

<style>
/* Reset & base */
body {
  margin: 0;
  padding: 0;
  font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
  background-color: #f5f7fa;
  width: 100%;
  height: auto;
  overflow-y: auto;
  overflow-x: hidden;
}

html {
  width: 100%;
  height: auto;
  background-color: #f5f7fa;
  overflow-y: auto;
  overflow-x: hidden;
}

#app {
  width: 100vw;
  min-height: 100vh;
  position: relative;
  background-color: #f5f7fa;
  margin: 0;
  padding: 0;
  max-width: 100%;
  overflow-y: auto;
  overflow-x: hidden;
}

/* Top navigation */
.top-nav {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  height: 56px;
  background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
  display: flex;
  align-items: center;
  padding: 0 24px;
  z-index: 1000;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.15);
}

.nav-brand {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-right: 40px;
}

.nav-logo {
  font-size: 22px;
}

.nav-title {
  font-size: 17px;
  font-weight: 700;
  color: #e8eaf6;
  letter-spacing: 0.5px;
  white-space: nowrap;
}

.nav-tabs {
  display: flex;
  gap: 4px;
  background: rgba(255, 255, 255, 0.08);
  border-radius: 8px;
  padding: 3px;
}

.nav-tab {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 7px 20px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: rgba(232, 234, 246, 0.65);
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.25s ease;
  white-space: nowrap;
}

.nav-tab:hover {
  color: #e8eaf6;
  background: rgba(255, 255, 255, 0.08);
}

.nav-tab.active {
  background: rgba(255, 255, 255, 0.15);
  color: #ffffff;
  font-weight: 600;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.12);
}

.nav-spacer {
  flex: 1;
}

/* App layout */
.app-root {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
  width: 100vw;
  max-width: 100%;
}

.app-body {
  margin-top: 56px;
  display: flex;
  flex: 1;
  min-height: calc(100vh - 56px);
}

/* Video mode layout */
.content-area {
  flex: 1;
  margin-left: 260px;
  width: calc(100vw - 260px);
  min-height: auto;
  display: flex;
  flex-direction: column;
  padding: 0 20px;
  box-sizing: border-box;
  overflow-y: auto;
  overflow-x: hidden;
}

.content-wrapper {
  flex: 1;
  display: flex;
  flex-direction: column;
  width: 100%;
  max-width: 1800px;
  margin: 0 auto;
  box-sizing: border-box;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 20px 0;
  height: auto;
}

/* Scrollbar */
::-webkit-scrollbar-track {
  background-color: #f5f7fa;
}

::-webkit-scrollbar {
  width: 6px;
}

::-webkit-scrollbar-thumb {
  background-color: #c0c4cc;
  border-radius: 3px;
}

::-webkit-scrollbar-thumb:hover {
  background-color: #909399;
}

/* Responsive */
@media screen and (max-width: 768px) {
  .content-area {
    margin-left: 60px;
    width: calc(100vw - 60px);
    padding: 0 5px;
    overflow-y: auto;
  }

  .content-wrapper {
    padding: 10px 0;
    overflow-y: visible;
  }

  .nav-brand {
    margin-right: 16px;
  }

  .nav-title {
    display: none;
  }

  .nav-tab {
    padding: 7px 12px;
    font-size: 13px;
  }
}

@media screen and (max-width: 480px) {
  .content-area {
    padding: 0 2px;
  }

  .content-wrapper {
    padding: 5px 0;
  }

  .nav-tab {
    padding: 6px 10px;
    font-size: 12px;
  }
}
</style>