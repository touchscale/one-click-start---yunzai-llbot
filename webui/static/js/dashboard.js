// 切换侧边栏显示/隐藏
function toggleSidebar() {
    const sidebar = document.querySelector('.sidebar');
    const mainContent = document.querySelector('.main-content');
    const toggleIcon = document.getElementById('sidebar-toggle-icon');

    sidebar.classList.toggle('collapsed');
    mainContent.classList.toggle('expanded');

    // 切换图标旋转效果
    if (sidebar.classList.contains('collapsed')) {
        toggleIcon.style.transform = 'rotate(180deg)';
    } else {
        toggleIcon.style.transform = 'rotate(0deg)';
    }
}

// 切换密码显示/隐藏
function togglePassword(fieldId, button) {
    const passwordField = document.getElementById(fieldId);
    const icon = button.querySelector('i');

    if (passwordField.type === 'password') {
        passwordField.type = 'text';
        icon.classList.remove('fa-eye');
        icon.classList.add('fa-eye-slash');
    } else {
        passwordField.type = 'password';
        icon.classList.remove('fa-eye-slash');
        icon.classList.add('fa-eye');
    }
}

// 密码强度验证
function validatePasswordStrength(password) {
    const errors = [];
    const MIN_LENGTH = 8;
    const MAX_LENGTH = 64;

    if (password.length < MIN_LENGTH) {
        errors.push(`密码长度不能少于${MIN_LENGTH}位`);
    }
    if (password.length > MAX_LENGTH) {
        errors.push(`密码长度不能超过${MAX_LENGTH}位`);
    }
    if (!/[A-Z]/.test(password)) {
        errors.push('密码必须包含至少一个大写字母');
    }
    if (!/[a-z]/.test(password)) {
        errors.push('密码必须包含至少一个小写字母');
    }
    if (!/\d/.test(password)) {
        errors.push('密码必须包含至少一个数字');
    }

    // 检查常见弱密码
    const commonWeakPasswords = ['password', '12345678', 'qwerty', 'abc123', 'password1', '123456789', '11111111', 'admin', 'admin123', 'root', 'welcome', 'monkey', 'dragon', 'master', 'letmein', 'login', 'passw0rd', 'qwerty123', '123abc', 'test123', 'admin1234', 'password123', '1234567890', 'qwertyuiop', 'asdfghjkl', 'zxcvbnm', '1q2w3e4r', 'a1b2c3d4'];
    if (commonWeakPasswords.includes(password.toLowerCase())) {
        errors.push('密码过于简单，请使用更复杂的密码');
    }

    // 检查连续重复字符
    if (/(.)\1{2,}/.test(password)) {
        errors.push('密码不应包含连续重复的字符');
    }

    // 检查连续序列
    if (/(012|123|234|345|456|567|678|789|890|abc|bcd|cde|def|efg|fgh|ghi|hij|ijk|jkl|klm|lmn|mno|nop|opq|pqr|qrs|rst|stu|tuv|uvw|vwx|wxy|xyz)/i.test(password)) {
        errors.push('密码不应包含连续的数字或字母序列');
    }

    return errors;
}

// 检查认证状态的辅助函数
function handleAuthError() {
    // 如果认证失败，重定向到登录页面
    window.location.href = '/login';
}

// 检查监控脚本运行状态
let lastMonitorStatus = null; // 记录上一次的监控状态
let monitorCheckFailCount = 0; // 监控检查失败计数

function checkMonitorStatus() {
    fetch('/api/monitor-status', {
        method: 'GET',
        timeout: 5000
    })
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            const currentStatus = data.monitor_running;

            // 重置失败计数
            monitorCheckFailCount = 0;

            // 如果状态从运行变为停止，显示提示
            if (lastMonitorStatus === true && currentStatus === false) {
                // 停止所有定时器
                stopTimers();
                // 显示监控停止提示页面
                showMonitorStoppedMessage();
            }

            // 更新上一次状态
            lastMonitorStatus = currentStatus;
        })
        .catch(error => {
            console.error('检查监控状态失败:', error);
            monitorCheckFailCount++;

            // 如果连续3次检查失败，假设监控脚本可能已停止
            if (monitorCheckFailCount >= 3 && lastMonitorStatus === true) {
                lastMonitorStatus = false;
                monitorCheckFailCount = 0;
                // 停止所有定时器
                stopTimers();
                // 显示监控停止提示页面
                showMonitorStoppedMessage();
            }
        });
}

// 自动更新状态
function updateStatus() {
    // 检查是否在 dashboard 页面
    const llbotStatus = document.getElementById('llbot-status');
    if (!llbotStatus) {
        return;
    }

    fetch('/api/status')
        .then(response => {
            if (response.status === 401) {
                handleAuthError();
                return;
            }
            return response.json();
        })
        .then(data => {
            // 再次检查元素是否仍然存在
            if (!document.getElementById('llbot-status')) {
                return;
            }

            if (data && typeof data === 'object') {
                updateProcessStatus('llbot', data.llbot);
                updateProcessStatus('yunzai', data.yunzai);
                updateProcessStatus('redis', data.redis);

                const httpStatus = document.getElementById('http-status');
                const httpIndicator = document.getElementById('http-status-indicator');

                // HTTP检查卡片总是显示，不需要额外的显示控制
                // 更新HTTP检查状态
                if (httpStatus && httpIndicator &&
                    httpStatus instanceof HTMLElement &&
                    httpIndicator instanceof HTMLElement) {
                    try {
                        if (data.http_check && data.http_check.configured) {
                            if (data.http_check.accessible) {
                                httpStatus.textContent = '可访问';
                                httpIndicator.className = 'status-running';
                            } else {
                                httpStatus.textContent = '不可访问';
                                httpIndicator.className = 'status-stopped';
                            }
                        } else {
                            httpStatus.textContent = '未配置';
                            httpIndicator.className = 'status-unknown';
                        }
                    } catch (error) {
                        console.warn('更新HTTP状态失败:', error);
                    }
                }

                // 更新统计信息
                updateStats(data);

                // 确保HTTP检查卡片始终可见
                ensureHttpCardVisibility();
            }
        })
        .catch(error => {
            console.error('获取状态失败:', error);
            // 即使获取状态失败，也要确保HTTP检查卡片显示
            const httpCard = document.getElementById('http-check-card');
            const httpContainer = document.getElementById('http-check-container');

            if (httpCard && httpCard instanceof HTMLElement) {
                try {
                    httpCard.style.display = 'block';
                    httpCard.style.visibility = 'visible';
                    httpCard.style.opacity = '1';
                    httpCard.classList.remove('d-none', 'd-hidden', 'hidden', 'invisible');
                } catch (e) {
                    console.warn('显示HTTP卡片失败:', e);
                }
            }

            if (httpContainer && httpContainer instanceof HTMLElement) {
                try {
                    httpContainer.style.display = 'block';
                    httpContainer.style.visibility = 'visible';
                    httpContainer.style.opacity = '1';
                    httpContainer.classList.remove('d-none', 'd-hidden', 'hidden', 'invisible');
                } catch (e) {
                    console.warn('显示HTTP容器失败:', e);
                }
            }

            // 检查是否是认证错误
            if (error.message && error.message.includes('401')) {
                handleAuthError();
            }
        });
}

// 更新统计信息
function updateStats(data) {
    const llbotStat = document.getElementById('llbot-stat');
    const yunzaiStat = document.getElementById('yunzai-stat');
    const redisStat = document.getElementById('redis-stat');
    const httpStat = document.getElementById('http-stat');

    // 更新 llbot 统计
    if (llbotStat && llbotStat instanceof HTMLElement) {
        try {
            if(data.llbot && data.llbot.running) {
                llbotStat.textContent = '运行';
                llbotStat.style.color = '#28a745';
            } else {
                llbotStat.textContent = '停止';
                llbotStat.style.color = '#dc3545';
            }
        } catch (error) {
            console.warn('更新llbot统计失败:', error);
        }
    }

    // 更新 yunzai 统计
    if (yunzaiStat && yunzaiStat instanceof HTMLElement) {
        try {
            if(data.yunzai && data.yunzai.running) {
                yunzaiStat.textContent = '运行';
                yunzaiStat.style.color = '#28a745';
            } else {
                yunzaiStat.textContent = '停止';
                yunzaiStat.style.color = '#dc3545';
            }
        } catch (error) {
            console.warn('更新yunzai统计失败:', error);
        }
    }

    // 更新 redis 统计
    if (redisStat && redisStat instanceof HTMLElement) {
        try {
            if(data.redis && data.redis.running) {
                redisStat.textContent = '运行';
                redisStat.style.color = '#28a745';
            } else {
                redisStat.textContent = '停止';
                redisStat.style.color = '#dc3545';
            }
        } catch (error) {
            console.warn('更新redis统计失败:', error);
        }
    }

    // 更新 http 统计
    if (httpStat && httpStat instanceof HTMLElement) {
        try {
            // 确保HTTP检查状态总是更新，不管是否有配置
            if(data.http_check && data.http_check.configured) {
                if(data.http_check.accessible) {
                    httpStat.textContent = '正常';
                    httpStat.style.color = '#28a745';
                } else {
                    httpStat.textContent = '异常';
                    httpStat.style.color = '#dc3545';
                }
            } else {
                httpStat.textContent = '未配置';
                httpStat.style.color = '#6c757d';
            }
        } catch (error) {
            console.warn('更新http统计失败:', error);
        }
    }
}

function updateProcessStatus(process, status) {
    const statusElement = document.getElementById(process + '-status');
    const indicatorElement = document.getElementById(process + '-status-indicator');

    // 增强检查：确保元素存在且是有效的 DOM 元素
    if (!statusElement || !indicatorElement ||
        !(statusElement instanceof HTMLElement) ||
        !(indicatorElement instanceof HTMLElement)) {
        return;
    }

    try {
        if (status && status.running) {
            statusElement.textContent = '运行中 (PID: ' + status.pid + ')';
            indicatorElement.className = 'status-running';
        } else {
            statusElement.textContent = '已停止';
            indicatorElement.className = 'status-stopped';
        }
    } catch (error) {
        console.warn(`更新 ${process} 状态失败:`, error);
    }
}

// 更新日志
function updateLogs() {
    // 检查是否在 dashboard 页面
    const logsDiv = document.getElementById('logs');
    const logCountElement = document.getElementById('log-count');
    const lastUpdateElement = document.getElementById('last-update');

    if (!logsDiv || !logCountElement || !lastUpdateElement) {
        return;
    }

    // 获取选中的日志等级
    const filterButtons = document.querySelectorAll('.log-filter-btn');
    const selectedLevels = Array.from(filterButtons)
        .filter(btn => btn.classList.contains('active'))
        .map(btn => btn.dataset.level);

    // 获取搜索关键词
    const searchInput = document.getElementById('log-search-input');
    const searchKeyword = searchInput ? searchInput.value.trim().toLowerCase() : '';

    fetch('/api/logs')
        .then(response => {
            if (response.status === 401) {
                handleAuthError();
                return;
            }
            return response.json();
        })
        .then(data => {
            // 再次检查元素是否仍然存在（防止在请求期间页面被卸载）
            if (!document.getElementById('logs')) {
                return;
            }

            if (data && data.logs) {
                logsDiv.innerHTML = '';

                // 根据选择的等级过滤日志
                let filteredLogs = data.logs;
                if (!selectedLevels.includes('all') && selectedLevels.length > 0) {
                    filteredLogs = data.logs.filter(log => {
                        const logLevel = log.level.toLowerCase();
                        return selectedLevels.includes(logLevel);
                    });
                }

                // 根据搜索关键词过滤日志
                if (searchKeyword) {
                    filteredLogs = filteredLogs.filter(log => {
                        const logText = (log.timestamp + ' [' + log.level + '] ' + log.module + ':' + log.function + ' - ' + log.message).toLowerCase();
                        return logText.includes(searchKeyword);
                    });
                }

                // 更新日志计数
                logCountElement.textContent = filteredLogs.length;

                // 如果没有日志，显示等待提示
                if (filteredLogs.length === 0) {
                    const emptyMessage = document.createElement('div');
                    emptyMessage.className = 'log-empty-message';
                    emptyMessage.innerHTML = '<i class="fas fa-hourglass-half"></i><span>等待日志...</span>';
                    logsDiv.appendChild(emptyMessage);
                } else {
                    filteredLogs.forEach(log => {
                        const logElement = document.createElement('div');
                        logElement.className = 'log-entry log-' + log.level.toLowerCase();
                        logElement.textContent = log.timestamp + ' [' + log.level + '] ' + log.module + ':' + log.function + ' - ' + log.message;
                        logsDiv.appendChild(logElement);
                    });
                }

                // 根据自动滚动状态决定是否滚动到最新日志
                if (autoScrollEnabled) {
                    logsDiv.scrollTop = logsDiv.scrollHeight;
                }

                // 更新最后更新时间
                lastUpdateElement.textContent = new Date().toLocaleString('zh-CN');
            }
        })
        .catch(error => {
            console.error('获取日志失败:', error);
            // 检查是否是认证错误
            if (error.message && error.message.includes('401')) {
                handleAuthError();
            }
        });
}

// 清空日志
function clearLogs() {
    fetch('/api/clear-logs', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        }
    })
    .then(response => {
        if (response.status === 401) {
            handleAuthError();
            return;
        }
        return response.json();
    })
    .then(data => {
        if (data) {
            const logsDiv = document.getElementById('logs');
            logsDiv.innerHTML = '';
            document.getElementById('log-count').textContent = '0';
            document.getElementById('last-update').textContent = '已清空';

            // 显示等待日志提示
            const emptyMessage = document.createElement('div');
            emptyMessage.className = 'log-empty-message';
            emptyMessage.innerHTML = '<i class="fas fa-hourglass-half"></i><span>等待日志...</span>';
            logsDiv.appendChild(emptyMessage);

            showAlert('日志已清空', 'info');
        }
    })
    .catch(error => {
        console.error('清空日志失败:', error);
        if (error.message && error.message.includes('401')) {
            handleAuthError();
        } else {
            showAlert('清空日志失败', 'danger');
        }
    });
}

// 自动滚动状态
let autoScrollEnabled = true;

// 切换自动滚动
function toggleAutoScroll() {
    autoScrollEnabled = !autoScrollEnabled;
    const btn = document.getElementById('auto-scroll-btn');

    if (autoScrollEnabled) {
        btn.classList.remove('btn-outline-primary');
        btn.classList.add('btn-primary');
        showAlert('自动滚动已开启', 'success');
    } else {
        btn.classList.remove('btn-primary');
        btn.classList.add('btn-outline-primary');
        showAlert('自动滚动已关闭', 'info');
    }
}

// 控制进程（已移除确认框，点击立即执行）
function controlProcess(process, action) {
    const actionText = action === 'start' ? '启动' : '停止';

    // 获取该进程的所有相关按钮
    const buttons = document.querySelectorAll(`button[onclick*="controlProcess('${process}'"]`);

    // 保存原始内容并禁用按钮
    buttons.forEach(btn => {
        // 保存原始内容到 data 属性
        btn.setAttribute('data-original-content', btn.innerHTML);
        btn.disabled = true;
        // 显示加载状态
        btn.innerHTML = `<i class="fas fa-spinner fa-spin"></i> ${actionText}中...`;
    });

    // 设置超时，5秒后自动恢复按钮状态
    const timeoutId = setTimeout(() => {
        buttons.forEach(btn => {
            btn.disabled = false;
            // 恢复原始内容
            const originalContent = btn.getAttribute('data-original-content');
            if (originalContent) {
                btn.innerHTML = originalContent;
            } else {
                btn.innerHTML = btn.innerHTML.replace('<i class="fas fa-spinner fa-spin"></i> ', '');
            }
        });
    }, 5000);

    fetch('/api/control', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            process: process,
            action: action
        })
    })
    .then(response => {
        if (response.status === 401) {
            clearTimeout(timeoutId);
            handleAuthError();
            return;
        }
        if (response.status === 429) {
            clearTimeout(timeoutId);
            // 操作正在进行中，恢复按钮并显示提示
            buttons.forEach(btn => {
                btn.disabled = false;
                const originalContent = btn.getAttribute('data-original-content');
                if (originalContent) {
                    btn.innerHTML = originalContent;
                }
            });
            return response.json().then(data => {
                showAlert(data.message || '操作正在进行中，请稍后再试', 'warning');
            });
        }
        return response.json();
    })
    .then(data => {
        clearTimeout(timeoutId);
        if (data) {
            // 使用Bootstrap的alert显示消息
            showAlert(data.message, 'success');
            // 立即恢复按钮状态
            buttons.forEach(btn => {
                btn.disabled = false;
                const originalContent = btn.getAttribute('data-original-content');
                if (originalContent) {
                    btn.innerHTML = originalContent;
                }
            });
            // 触发状态更新
            updateStatus();
        }
    })
    .catch(error => {
        clearTimeout(timeoutId);
        console.error('控制进程失败:', error);
        // 恢复按钮状态
        buttons.forEach(btn => {
            btn.disabled = false;
            const originalContent = btn.getAttribute('data-original-content');
            if (originalContent) {
                btn.innerHTML = originalContent;
            }
        });

        // 检查是否是认证错误
        if (error.message && error.message.includes('401')) {
            handleAuthError();
        } else {
            showAlert('操作失败: ' + error, 'danger');
        }
    });
}



// 手动HTTP检查
function manualHttpCheck() {
    // 获取按钮
    const button = document.querySelector('button[onclick="manualHttpCheck()"]');
    if (!button) return;

    // 保存原始内容并禁用按钮
    const originalHTML = button.innerHTML;
    button.setAttribute('data-original-content', originalHTML);
    button.disabled = true;
    button.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 检查中...';

    // 设置超时，5秒后自动恢复
    const timeoutId = setTimeout(() => {
        button.disabled = false;
        button.innerHTML = originalHTML;
    }, 5000);

    fetch('/api/manual-check', {
        method: 'POST',
    })
    .then(response => {
        clearTimeout(timeoutId);
        if (response.status === 401) {
            handleAuthError();
            return;
        }
        return response.json();
    })
    .then(data => {
        if (data) {
            // 恢复按钮状态
            button.disabled = false;
            button.innerHTML = originalHTML;

            showAlert(data.message, 'info');
            updateStatus();
        }
    })
    .catch(error => {
        clearTimeout(timeoutId);
        console.error('手动检查失败:', error);
        // 恢复按钮状态
        button.disabled = false;
        button.innerHTML = originalHTML;

        // 检查是否是认证错误
        if (error.message && error.message.includes('401')) {
            handleAuthError();
        } else {
            showAlert('检查失败: ' + error, 'danger');
        }
    });
}

// 显示监控停止消息
function showMonitorStoppedMessage() {
    // 防止重复显示
    if (document.getElementById('monitor-stopped-overlay')) {
        return;
    }

    const overlay = document.createElement('div');
    overlay.id = 'monitor-stopped-overlay';
    overlay.style.cssText = `
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        display: flex;
        justify-content: center;
        align-items: center;
        z-index: 999999;
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif;
    `;

    const container = document.createElement('div');
    container.style.cssText = `
        text-align: center;
        padding: 60px 40px;
        background: rgba(255, 255, 255, 0.1);
        border-radius: 20px;
        box-shadow: 0 8px 32px 0 rgba(31, 38, 135, 0.37);
        backdrop-filter: blur(4px);
        border: 1px solid rgba(255, 255, 255, 0.18);
        max-width: 600px;
        width: 90%;
        animation: fadeIn 0.5s ease-in;
        color: white;
    `;

    const iconHtml = `
        <div style="margin-bottom: 30px;">
            <svg width="100" height="100" viewBox="0 0 24 24" fill="none" style="animation: pulse 2s infinite;">
                <circle cx="12" cy="12" r="10" stroke="white" stroke-width="2" fill="rgba(255,255,255,0.1)"/>
                <path d="M12 8V12M12 16H12.01" stroke="white" stroke-width="2" stroke-linecap="round"/>
            </svg>
        </div>
    `;

    const contentHtml = `
        <h1 style="font-size: 2.5em; margin-bottom: 20px; font-weight: 600; text-shadow: 2px 2px 4px rgba(0, 0, 0, 0.2);">监控脚本已停止</h1>
        <p style="font-size: 1.2em; margin-bottom: 15px; line-height: 1.6; text-shadow: 1px 1px 2px rgba(0, 0, 0, 0.2);">检测到监控脚本已停止运行</p>
        <p style="font-size: 1.2em; margin-bottom: 30px; text-shadow: 1px 1px 2px rgba(0, 0, 0, 0.2);">系统正在等待监控脚本恢复...</p>
        <div style="margin-top: 30px; padding: 20px; background: rgba(0, 0, 0, 0.2); border-radius: 10px; font-size: 1.1em;">
            <div style="display: inline-block; width: 20px; height: 20px; border: 3px solid rgba(255, 255, 255, 0.3); border-top: 3px solid white; border-radius: 50%; animation: spin 1s linear infinite; margin-right: 10px; vertical-align: middle;"></div>
            <span id="connection-status">正在检查监控脚本状态...</span>
        </div>
        <div style="margin-top: 20px; padding: 15px; background: rgba(255, 255, 255, 0.1); border-radius: 10px; font-size: 0.95em; line-height: 1.5;">
            <strong style="display: block; margin-bottom: 8px; color: #ffd700;">提示：</strong>
            监控脚本恢复运行后，系统将自动跳转到登录界面
        </div>
        <button id="refresh-btn" style="margin-top: 30px; padding: 12px 30px; background: rgba(255, 255, 255, 0.2); border: 2px solid white; border-radius: 25px; color: white; font-size: 1em; cursor: pointer; transition: all 0.3s ease;">立即刷新</button>
    `;

    const styleHtml = `
        <style>
            @keyframes fadeIn {
                from { opacity: 0; transform: translateY(-20px); }
                to { opacity: 1; transform: translateY(0); }
            }
            @keyframes pulse {
                0%, 100% { transform: scale(1); }
                50% { transform: scale(1.1); }
            }
            @keyframes spin {
                0% { transform: rotate(0deg); }
                100% { transform: rotate(360deg); }
            }
            #refresh-btn:hover {
                background: rgba(255, 255, 255, 0.3);
                transform: scale(1.05);
            }
            #refresh-btn:active {
                transform: scale(0.95);
            }
        </style>
    `;

    container.innerHTML = styleHtml + iconHtml + contentHtml;
    overlay.appendChild(container);
    document.body.appendChild(overlay);

    // 点击刷新按钮刷新页面
    document.getElementById('refresh-btn').addEventListener('click', function() {
        window.location.reload();
    });

    // 智能监控恢复检测
    let checkCount = 0;
    const maxCheckCount = 60; // 最多检查60次（约3分钟）

    function checkMonitorRecovery() {
        checkCount++;
        const statusEl = document.getElementById('connection-status');

        // 首先尝试通过 API 检查（如果 Web 服务器已恢复）
        fetch('/api/monitor-status-file', {
            method: 'GET',
            timeout: 5000
        })
            .then(response => {
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                return response.json();
            })
            .then(data => {
                if (data.monitor_recovered) {
                    // 监控脚本已恢复
                    statusEl.textContent = '监控脚本已恢复，正在跳转到登录页面...';
                    setTimeout(() => {
                        window.location.href = '/login';
                    }, 1500);
                } else {
                    // 监控脚本仍未恢复
                    if (checkCount < maxCheckCount) {
                        statusEl.textContent = `监控脚本仍未运行，3秒后再次检查... (${checkCount}/${maxCheckCount})`;
                        setTimeout(checkMonitorRecovery, 3000);
                    } else {
                        statusEl.textContent = '监控脚本长时间未恢复，请点击按钮手动刷新页面';
                    }
                }
            })
            .catch(error => {
                // API 检查失败，说明 Web 服务器可能还未恢复
                if (checkCount < maxCheckCount) {
                    statusEl.textContent = `Web 服务器未响应，3秒后再次尝试... (${checkCount}/${maxCheckCount})`;
                    setTimeout(checkMonitorRecovery, 3000);
                } else {
                    statusEl.textContent = 'Web 服务器长时间未响应，请点击按钮手动刷新页面';
                }
            });
    }

    // 延迟1秒开始检查
    setTimeout(checkMonitorRecovery, 1000);
}

// 显示警告消息
function showAlert(message, type) {
    // 创建alert元素
    const alertDiv = document.createElement('div');
    alertDiv.className = 'alert alert-' + type + ' alert-dismissible fade show position-fixed';
    alertDiv.style.top = '20px';
    alertDiv.style.right = '20px';
    alertDiv.style.zIndex = '9999';
    alertDiv.style.minWidth = '300px';
    alertDiv.innerHTML = message + '<button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>';

    document.body.appendChild(alertDiv);

    // 3秒后自动关闭
    setTimeout(() => {
        alertDiv.remove();
    }, 3000);
}

// 修改密码
function changePassword() {
    const currentPassword = document.getElementById('currentPassword').value;
    const newUsername = document.getElementById('newUsername').value;
    const newPassword = document.getElementById('newPassword').value;
    const confirmPassword = document.getElementById('confirmPassword').value;

    if (!currentPassword || !newPassword) {
        showAlert('请填写当前密码和新密码', 'warning');
        return;
    }

    if (newPassword !== confirmPassword) {
        showAlert('两次输入的新密码不一致', 'warning');
        return;
    }

    // 验证密码强度
    const errors = validatePasswordStrength(newPassword);
    if (errors.length > 0) {
        showAlert(errors.join('；'), 'warning');
        return;
    }

    fetch('/api/change-password', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            old_password: currentPassword,
            new_username: newUsername,
            new_password: newPassword
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.message) {
            showAlert(data.message, 'success');
            // 关闭模态框
            const modalEl = document.getElementById('passwordModal');
            const modal = bootstrap.Modal.getInstance(modalEl);
            if (modal) {
                modal.hide();
            }
        }
    })
    .catch(error => {
        showAlert('修改密码失败: ' + error, 'danger');
    });
}

// 确保HTTP检查卡片始终可见
function ensureHttpCardVisibility() {
    const httpCard = document.getElementById('http-check-card');
    const httpContainer = document.getElementById('http-check-container');
    const httpButton = document.getElementById('http-check-button');

    if (httpCard && httpCard instanceof HTMLElement) {
        try {
            httpCard.style.display = 'block';
            httpCard.style.visibility = 'visible';
            httpCard.style.opacity = '1';
            httpCard.classList.remove('d-none', 'd-hidden', 'hidden', 'invisible');
        } catch (error) {
            console.warn('显示HTTP卡片失败:', error);
        }
    }

    if (httpContainer && httpContainer instanceof HTMLElement) {
        try {
            httpContainer.style.display = 'block';
            httpContainer.style.visibility = 'visible';
            httpContainer.style.opacity = '1';
            httpContainer.classList.remove('d-none', 'd-hidden', 'hidden', 'invisible');
        } catch (error) {
            console.warn('显示HTTP容器失败:', error);
        }
    }

    if (httpButton && httpButton instanceof HTMLElement) {
        try {
            httpButton.style.display = 'inline-flex';
            httpButton.style.visibility = 'visible';
            httpButton.style.opacity = '1';
        } catch (error) {
            console.warn('显示HTTP按钮失败:', error);
        }
    }
}

// 定时器ID存储
let statusIntervalId = null;
let logsIntervalId = null;
let monitorStatusIntervalId = null;

// 启动定时器
function startTimers() {
    // 清除旧的定时器
    stopTimers();

    // 每5秒更新一次状态
    statusIntervalId = setInterval(updateStatus, 5000);

    // 每5秒更新一次日志
    logsIntervalId = setInterval(updateLogs, 5000);
    
    // 每3秒检查一次监控脚本运行状态
    monitorStatusIntervalId = setInterval(checkMonitorStatus, 3000);
}

// 停止定时器
function stopTimers() {
    if (statusIntervalId) {
        clearInterval(statusIntervalId);
        statusIntervalId = null;
    }
    if (logsIntervalId) {
        clearInterval(logsIntervalId);
        logsIntervalId = null;
    }
    if (monitorStatusIntervalId) {
        clearInterval(monitorStatusIntervalId);
        monitorStatusIntervalId = null;
    }
}

// 初始化日志筛选和搜索功能
function initLogFilters() {
    // 移除旧的事件监听器（避免重复绑定）
    const filterButtons = document.querySelectorAll('.log-filter-btn');
    filterButtons.forEach(button => {
        const newButton = button.cloneNode(true);
        button.parentNode.replaceChild(newButton, button);
    });

    const searchInput = document.getElementById('log-search-input');
    if (searchInput) {
        const newSearchInput = searchInput.cloneNode(true);
        searchInput.parentNode.replaceChild(newSearchInput, searchInput);
    }

    // 重新获取元素并绑定事件
    const newFilterButtons = document.querySelectorAll('.log-filter-btn');
    newFilterButtons.forEach(button => {
        button.addEventListener('click', function() {
            const level = this.dataset.level;

            if (level === 'all') {
                // 点击"全部"按钮，只选中全部，取消其他选择
                newFilterButtons.forEach(btn => btn.classList.remove('active'));
                this.classList.add('active');
            } else {
                // 点击具体等级按钮
                const allButton = document.querySelector('.log-filter-btn[data-level="all"]');

                // 如果"全部"按钮被选中，先取消它
                if (allButton.classList.contains('active')) {
                    allButton.classList.remove('active');
                    this.classList.add('active');
                } else {
                    // 切换当前按钮的选中状态
                    this.classList.toggle('active');

                    // 如果没有任何按钮被选中，默认选中"全部"
                    const anySelected = Array.from(newFilterButtons).some(btn => btn.classList.contains('active'));
                    if (!anySelected) {
                        allButton.classList.add('active');
                    }
                }
            }

            // 当用户改变选择时，立即更新日志显示
            updateLogs();
        });
    });

    // 日志搜索框事件监听
    const newSearchInput = document.getElementById('log-search-input');
    if (newSearchInput) {
        // 使用防抖函数，避免频繁搜索
        let searchTimeout;
        newSearchInput.addEventListener('input', function() {
            clearTimeout(searchTimeout);
            searchTimeout = setTimeout(function() {
                updateLogs();
            }, 300); // 300ms 延迟后执行搜索
        });
    }
}

// 页面加载完成后启动自动更新
document.addEventListener('DOMContentLoaded', function() {
    // 立即显示加载状态
    const loadingStates = [
        { id: 'llbot-status', text: '加载中...', class: 'status-unknown' },
        { id: 'yunzai-status', text: '加载中...', class: 'status-unknown' },
        { id: 'redis-status', text: '加载中...', class: 'status-unknown' },
        { id: 'http-status', text: '加载中...', class: 'status-unknown' }
    ];

    loadingStates.forEach(item => {
        const statusEl = document.getElementById(item.id);
        if (statusEl) {
            statusEl.textContent = item.text;
            const indicatorEl = document.getElementById(item.id + '-indicator');
            if (indicatorEl) {
                indicatorEl.className = item.class;
            }
        }
    });

    // 立即获取真实状态
    updateStatus();
    updateLogs();

    // 初始化自动滚动按钮状态
    const autoScrollBtn = document.getElementById('auto-scroll-btn');
    if (autoScrollEnabled) {
        autoScrollBtn.classList.remove('btn-outline-primary');
        autoScrollBtn.classList.add('btn-primary');
    }

    // 初始化日志筛选和搜索功能
    initLogFilters();

    // 启动定时器
    startTimers();

    // 确保HTTP检查卡片始终可见
    ensureHttpCardVisibility();

    // 修复模态框的 aria-hidden 警告
    const modals = document.querySelectorAll('.modal');
    modals.forEach(modal => {
        modal.removeAttribute('aria-hidden');

        modal.addEventListener('show.bs.modal', function() {
            modal.removeAttribute('aria-hidden');
        });

        modal.addEventListener('hidden.bs.modal', function() {
            modal.setAttribute('aria-hidden', 'true');
            // 移除焦点，避免焦点保留在具有 aria-hidden 属性的元素上
            if (document.activeElement && modal.contains(document.activeElement)) {
                document.activeElement.blur();
            }
        });
    });
});