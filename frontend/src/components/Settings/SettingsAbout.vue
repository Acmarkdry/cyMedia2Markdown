<template>
    <div class="about-settings">
        <div class="about-highlight-tip">
            本地优先的视频学习资料提取工作台
        </div>
        <h2>cyMedia2Markdown</h2>
        <p>
            当前版本面向课程视频、技术演讲和会议录屏整理：后端负责本地媒体处理、ASR、Codex CLI 生成和截图，前端负责任务入口、结果 review 和分布式队列看板。
        </p>
        <dl class="about-list">
            <div>
                <dt>运行规范</dt>
                <dd>Python 固定 3.12.x，CPU/GPU 使用角色化虚拟环境。</dd>
            </div>
            <div>
                <dt>分布式入口</dt>
                <dd><code>tools\start_worker.ps1 -Role cpu|gpu</code></dd>
            </div>
            <div>
                <dt>队列规范</dt>
                <dd>队列目录独立于项目目录，只保存任务状态、日志和产物。</dd>
            </div>
            <div>
                <dt>测试规范</dt>
                <dd><code>docs\testing.md</code> 维护测试用例、验收标准和提交流程。</dd>
            </div>
        </dl>
        <p class="about-note">
            请只处理你拥有权利、已获授权，或依法可进行个人学习、研究、引用和整理的音视频内容。
        </p>
    </div>
</template>

<style scoped>
.about-settings {
    width: 100%;
    max-width: 760px;
    margin: 0;
    color: #1e293b;
    font-size: 15px;
    line-height: 1.7;
    background: #ffffff;
    border-radius: 8px;
    padding: 24px 32px;
    text-align: left;
    border: 1px solid #e2e8f0;
}

.about-highlight-tip {
    background: #eff6ff;
    color: #1d4ed8;
    font-size: 15px;
    font-weight: 700;
    border-left: 4px solid #2563eb;
    border-radius: 8px;
    padding: 12px 16px;
    margin-bottom: 20px;
    text-align: left;
}

.about-settings h2 {
    margin: 0 0 12px;
    color: #0f172a;
    font-size: 22px;
}

.about-settings p {
    margin: 0 0 18px;
}

.about-list {
    display: grid;
    gap: 12px;
    margin: 0 0 18px;
}

.about-list div {
    display: grid;
    gap: 2px;
}

.about-list dt {
    color: #475569;
    font-size: 13px;
    font-weight: 700;
}

.about-list dd {
    margin: 0;
    color: #0f172a;
}

.about-list code {
    background: #f1f5f9;
    border-radius: 6px;
    padding: 2px 6px;
    overflow-wrap: anywhere;
}

.about-note {
    color: #64748b;
    font-size: 14px;
}
</style>
