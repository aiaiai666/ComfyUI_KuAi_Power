/**
 * 实时批量处理监控 - 前端扩展
 * 监听 WebSocket 消息并显示浮动面板
 */

import { app } from "../../scripts/app.js";

// 全局状态
let monitorPanel = null;
let isMonitoring = false;

/**
 * 创建浮动监控面板
 */
function createMonitorPanel() {
    if (monitorPanel) {
        return monitorPanel;
    }

    // 创建面板容器
    const panel = document.createElement("div");
    panel.id = "kuai-realtime-monitor";
    panel.style.cssText = `
        position: fixed;
        top: 80px;
        right: 20px;
        width: 450px;
        max-height: 600px;
        background: rgba(0, 0, 0, 0.9);
        border: 1px solid #444;
        border-radius: 8px;
        color: #fff;
        font-family: 'Courier New', monospace;
        font-size: 12px;
        z-index: 9999;
        display: none;
        overflow: hidden;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.5);
    `;

    // 创建标题栏
    const header = document.createElement("div");
    header.style.cssText = `
        padding: 10px 15px;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        font-weight: bold;
        font-size: 14px;
        display: flex;
        justify-content: space-between;
        align-items: center;
        cursor: move;
    `;
    header.innerHTML = `
        <span>📊 批量处理实时监控</span>
        <span id="kuai-monitor-close" style="cursor: pointer; font-size: 18px;">&times;</span>
    `;
    panel.appendChild(header);

    // 创建内容区域
    const content = document.createElement("div");
    content.id = "kuai-monitor-content";
    content.style.cssText = `
        padding: 15px;
        max-height: 550px;
        overflow-y: auto;
    `;
    panel.appendChild(content);

    // 添加到页面
    document.body.appendChild(panel);

    // 关闭按钮事件
    document.getElementById("kuai-monitor-close").addEventListener("click", () => {
        panel.style.display = "none";
        isMonitoring = false;
    });

    // 拖动功能
    makeDraggable(panel, header);

    monitorPanel = panel;
    return panel;
}

/**
 * 使元素可拖动
 */
function makeDraggable(element, handle) {
    let pos1 = 0, pos2 = 0, pos3 = 0, pos4 = 0;

    handle.onmousedown = dragMouseDown;

    function dragMouseDown(e) {
        e.preventDefault();
        pos3 = e.clientX;
        pos4 = e.clientY;
        document.onmouseup = closeDragElement;
        document.onmousemove = elementDrag;
    }

    function elementDrag(e) {
        e.preventDefault();
        pos1 = pos3 - e.clientX;
        pos2 = pos4 - e.clientY;
        pos3 = e.clientX;
        pos4 = e.clientY;
        element.style.top = (element.offsetTop - pos2) + "px";
        element.style.right = "auto";
        element.style.left = (element.offsetLeft - pos1) + "px";
    }

    function closeDragElement() {
        document.onmouseup = null;
        document.onmousemove = null;
    }
}

/**
 * 更新监控面板内容
 */
function updateMonitorPanel(data) {
    const panel = createMonitorPanel();
    const content = document.getElementById("kuai-monitor-content");

    if (!data || !data.session_id) {
        content.innerHTML = `
            <div style="text-align: center; padding: 20px; color: #888;">
                暂无批量处理任务运行
            </div>
        `;
        return;
    }

    // 显示面板
    panel.style.display = "block";
    isMonitoring = true;

    // 计算进度
    const progress = data.progress || 0;
    const total = data.total || 0;
    const completed = data.completed || 0;
    const failed = data.failed || 0;
    const processing = data.processing || 0;
    const pending = total - completed - failed - processing;

    // 统计信息
    const stats = data.statistics || {};
    const avgDuration = stats.avg_duration || 0;
    const successRate = stats.success_rate || 0;
    const estimatedRemaining = stats.estimated_remaining || 0;

    // 格式化时间
    const formatTime = (seconds) => {
        if (seconds < 60) return `${Math.round(seconds)}秒`;
        const minutes = Math.floor(seconds / 60);
        const secs = Math.round(seconds % 60);
        return `${minutes}分${secs}秒`;
    };

    // 生成进度条
    const progressBar = `
        <div style="background: #333; border-radius: 4px; overflow: hidden; margin: 10px 0;">
            <div style="
                width: ${progress}%;
                height: 20px;
                background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
                transition: width 0.3s ease;
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 11px;
                font-weight: bold;
            ">${progress.toFixed(1)}%</div>
        </div>
    `;

    // 生成统计信息
    const statsHtml = `
        <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; margin: 10px 0;">
            <div style="background: #1a1a1a; padding: 8px; border-radius: 4px;">
                <div style="color: #888; font-size: 10px;">总进度</div>
                <div style="font-size: 16px; font-weight: bold;">${completed + failed}/${total}</div>
            </div>
            <div style="background: #1a1a1a; padding: 8px; border-radius: 4px;">
                <div style="color: #888; font-size: 10px;">成功率</div>
                <div style="font-size: 16px; font-weight: bold; color: ${successRate >= 80 ? '#4ade80' : '#fbbf24'};">${successRate.toFixed(1)}%</div>
            </div>
            <div style="background: #1a1a1a; padding: 8px; border-radius: 4px;">
                <div style="color: #888; font-size: 10px;">平均耗时</div>
                <div style="font-size: 16px; font-weight: bold;">${formatTime(avgDuration)}</div>
            </div>
            <div style="background: #1a1a1a; padding: 8px; border-radius: 4px;">
                <div style="color: #888; font-size: 10px;">预计剩余</div>
                <div style="font-size: 16px; font-weight: bold;">${formatTime(estimatedRemaining)}</div>
            </div>
        </div>
    `;

    // 生成状态统计
    const statusHtml = `
        <div style="display: flex; justify-content: space-around; margin: 10px 0; padding: 10px; background: #1a1a1a; border-radius: 4px;">
            <div style="text-align: center;">
                <div style="font-size: 18px; color: #4ade80;">✓ ${completed}</div>
                <div style="font-size: 10px; color: #888;">已完成</div>
            </div>
            <div style="text-align: center;">
                <div style="font-size: 18px; color: #f87171;">✗ ${failed}</div>
                <div style="font-size: 10px; color: #888;">已失败</div>
            </div>
            <div style="text-align: center;">
                <div style="font-size: 18px; color: #60a5fa;">⟳ ${processing}</div>
                <div style="font-size: 10px; color: #888;">处理中</div>
            </div>
            <div style="text-align: center;">
                <div style="font-size: 18px; color: #9ca3af;">○ ${pending}</div>
                <div style="font-size: 10px; color: #888;">等待中</div>
            </div>
        </div>
    `;

    // 生成最新任务列表
    let tasksHtml = '<div style="margin-top: 15px;"><div style="color: #888; margin-bottom: 8px; font-weight: bold;">最新任务:</div>';
    const tasks = data.tasks || [];
    if (tasks.length > 0) {
        tasks.slice(0, 5).forEach(task => {
            const statusIcon = {
                'completed': '<span style="color: #4ade80;">✓</span>',
                'failed': '<span style="color: #f87171;">✗</span>',
                'processing': '<span style="color: #60a5fa;">⟳</span>',
                'pending': '<span style="color: #9ca3af;">○</span>'
            }[task.status] || '?';

            const prompt = task.prompt || '';
            const promptShort = prompt.length > 30 ? prompt.substring(0, 30) + '...' : prompt;

            let detailHtml = '';
            if (task.status === 'completed' && task.local_path) {
                detailHtml = `<div style="color: #4ade80; font-size: 10px; margin-left: 20px;">└─ ${task.local_path}</div>`;
            } else if (task.status === 'failed' && task.error) {
                detailHtml = `<div style="color: #f87171; font-size: 10px; margin-left: 20px;">└─ ${task.error}</div>`;
            } else if (task.status === 'processing' && task.task_id) {
                detailHtml = `<div style="color: #60a5fa; font-size: 10px; margin-left: 20px;">└─ ${task.task_id}</div>`;
            }

            tasksHtml += `
                <div style="margin-bottom: 8px; padding: 6px; background: #1a1a1a; border-radius: 4px;">
                    <div>[${task.update_time}] [${task.idx}] ${statusIcon} ${task.status.toUpperCase()}</div>
                    ${promptShort ? `<div style="color: #888; font-size: 10px; margin-left: 20px;">${promptShort}</div>` : ''}
                    ${detailHtml}
                </div>
            `;
        });
    } else {
        tasksHtml += '<div style="color: #888; text-align: center; padding: 10px;">暂无任务</div>';
    }
    tasksHtml += '</div>';

    // 生成详细日志
    let logsHtml = '<div style="margin-top: 15px;"><div style="color: #888; margin-bottom: 8px; font-weight: bold;">详细日志:</div>';
    logsHtml += '<div id="kuai-monitor-logs" style="background: #1a1a1a; padding: 10px; border-radius: 4px; max-height: 150px; overflow-y: auto; font-size: 10px;">';

    const logs = data.logs || [];
    if (logs.length > 0) {
        logs.slice(-20).reverse().forEach(log => {
            const levelColor = {
                'ERROR': '#f87171',
                'WARNING': '#fbbf24',
                'INFO': '#60a5fa',
                'DEBUG': '#9ca3af'
            }[log.level] || '#fff';

            logsHtml += `
                <div style="margin-bottom: 4px; color: ${levelColor};">
                    [${log.timestamp}] [${log.task_idx}] ${log.message}
                </div>
            `;
        });
    } else {
        logsHtml += '<div style="color: #888; text-align: center;">暂无日志</div>';
    }
    logsHtml += '</div></div>';

    // 组合所有内容
    content.innerHTML = `
        <div style="color: #888; font-size: 10px; margin-bottom: 10px;">
            会话: ${data.session_id}<br>
            开始: ${data.start_time} | 更新: ${data.last_update}
        </div>
        ${progressBar}
        ${statusHtml}
        ${statsHtml}
        ${tasksHtml}
        ${logsHtml}
    `;

    // 自动滚动日志到底部
    const logsContainer = document.getElementById("kuai-monitor-logs");
    if (logsContainer) {
        logsContainer.scrollTop = logsContainer.scrollHeight;
    }

    // 如果会话完成，3秒后自动隐藏
    if (data.completed) {
        setTimeout(() => {
            if (panel.style.display !== "none") {
                panel.style.display = "none";
                isMonitoring = false;
            }
        }, 3000);
    }
}

/**
 * 注册 ComfyUI 扩展
 */
app.registerExtension({
    name: "KuAi.RealtimeMonitor",

    async setup() {
        console.log("[KuAi.RealtimeMonitor] 扩展已加载");

        // 监听 WebSocket 消息
        const originalOnMessage = app.socket.onmessage;

        app.socket.onmessage = function(event) {
            // 调用原始处理器
            if (originalOnMessage) {
                originalOnMessage.call(this, event);
            }

            // 处理我们的消息
            try {
                const msg = JSON.parse(event.data);

                // 监听批量处理进度消息
                if (msg.type === 'kuai.batch.progress') {
                    console.log("[KuAi.RealtimeMonitor] 收到进度更新", msg.data);
                    updateMonitorPanel(msg.data);
                }
            } catch (e) {
                // 忽略解析错误
            }
        };

        console.log("[KuAi.RealtimeMonitor] WebSocket 监听已设置");
    }
});
