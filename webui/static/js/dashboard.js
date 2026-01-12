// 检查认证状态的辅助函数
function handleAuthError() {
    // 如果认证失败，重定向到登录页面
    window.location.href = '/login';
}

// 自动更新状态
function updateStatus() {
    fetch('/api/status')
        .then(response => {
            if (response.status === 401) {
                handleAuthError();
                return;
            }
            return response.json();
        })
        .then(data => {
            if (data && typeof data === 'object') {
                updateProcessStatus('llbot', data.llbot);
                updateProcessStatus('yunzai', data.yunzai);
                updateProcessStatus('redis', data.redis);

                const httpStatus = document.getElementById('http-status');
                const httpIndicator = document.getElementById('http-status-indicator');

                // HTTP检查卡片总是显示，不需要额外的显示控制
                // 更新HTTP检查状态
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

            if (httpCard) {
                httpCard.style.display = 'block';
                httpCard.style.visibility = 'visible';
                httpCard.style.opacity = '1';
                httpCard.classList.remove('d-none', 'd-hidden', 'hidden', 'invisible');
            }

            if (httpContainer) {
                httpContainer.style.display = 'block';
                httpContainer.style.visibility = 'visible';
                httpContainer.style.opacity = '1';
                httpContainer.classList.remove('d-none', 'd-hidden', 'hidden', 'invisible');
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

    if(data.llbot && data.llbot.running) {
        llbotStat.textContent = '运行';
        llbotStat.style.color = '#28a745';
    } else {
        llbotStat.textContent = '停止';
        llbotStat.style.color = '#dc3545';
    }

    if(data.yunzai && data.yunzai.running) {
        yunzaiStat.textContent = '运行';
        yunzaiStat.style.color = '#28a745';
    } else {
        yunzaiStat.textContent = '停止';
        yunzaiStat.style.color = '#dc3545';
    }

    if(data.redis && data.redis.running) {
        redisStat.textContent = '运行';
        redisStat.style.color = '#28a745';
    } else {
        redisStat.textContent = '停止';
        redisStat.style.color = '#dc3545';
    }

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
}

function updateProcessStatus(process, status) {
    const statusElement = document.getElementById(process + '-status');
    const indicatorElement = document.getElementById(process + '-status-indicator');

    if (status && status.running) {
        statusElement.textContent = '运行中 (PID: ' + status.pid + ')';
        indicatorElement.className = 'status-running';
    } else {
        statusElement.textContent = '已停止';
        indicatorElement.className = 'status-stopped';
    }
}

// 更新日志
function updateLogs() {
    fetch('/api/logs')
        .then(response => {
            if (response.status === 401) {
                handleAuthError();
                return;
            }
            return response.json();
        })
        .then(data => {
            if (data && data.logs) {
                const logsDiv = document.getElementById('logs');
                logsDiv.innerHTML = '';

                // 更新日志计数
                document.getElementById('log-count').textContent = data.logs.length;

                data.logs.forEach(log => {
                    const logElement = document.createElement('div');
                    logElement.className = 'log-entry log-' + log.level.toLowerCase();
                    logElement.textContent = log.timestamp + ' [' + log.level + '] ' + log.module + ':' + log.function + ' - ' + log.message;
                    logsDiv.appendChild(logElement);
                });

                // 滚动到最新日志
                logsDiv.scrollTop = logsDiv.scrollHeight;

                // 更新最后更新时间
                document.getElementById('last-update').textContent = new Date().toLocaleString('zh-CN');
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
    const logsDiv = document.getElementById('logs');
    logsDiv.innerHTML = '';
    document.getElementById('log-count').textContent = '0';
    document.getElementById('last-update').textContent = '已清空';
    showAlert('日志已清空', 'info');
}

// 控制进程（已移除确认框，点击立即执行）
function controlProcess(process, action) {
    const actionText = action === 'start' ? '启动' : '停止';
    // 不再弹出确认框，直接执行操作以提高体验。

    // 禁用按钮并显示加载状态
    const buttons = document.querySelectorAll(`button[onclick*="controlProcess('${process}'"]`);
    buttons.forEach(btn => {
        btn.disabled = true;
        const originalHTML = btn.innerHTML;
        btn.innerHTML = `<i class="fas fa-spinner fa-spin"></i> ${actionText}中...`;

        // 恢复原始内容的函数
        setTimeout(() => {
            btn.innerHTML = originalHTML;
            btn.disabled = false;
        }, 5000); // 5秒后恢复，即使没有收到响应
    });

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
            handleAuthError();
            return;
        }
        return response.json();
    })
    .then(data => {
        if (data) {
            // 重置按钮状态
            buttons.forEach(btn => {
                btn.disabled = false;
                btn.innerHTML = btn.getAttribute('data-original-content') || btn.innerHTML.replace('<i class="fas fa-spinner fa-spin"></i> ', '');
            });

            // 使用Bootstrap的alert显示消息
            showAlert(data.message, 'success');
            updateStatus();
        }
    })
    .catch(error => {
        console.error('控制进程失败:', error);
        // 重置按钮状态
        buttons.forEach(btn => {
            btn.disabled = false;
            btn.innerHTML = btn.getAttribute('data-original-content') || btn.innerHTML.replace('<i class="fas fa-spinner fa-spin"></i> ', '');
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
    // 禁用按钮并显示加载状态
    const button = document.querySelector('button[onclick="manualHttpCheck()"]');
    const originalHTML = button.innerHTML;
    button.disabled = true;
    button.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 检查中...';

    fetch('/api/manual-check', {
        method: 'POST',
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
            // 重置按钮状态
            button.disabled = false;
            button.innerHTML = originalHTML;

            showAlert(data.message, 'info');
            updateStatus();
        }
    })
    .catch(error => {
        console.error('手动检查失败:', error);
        // 重置按钮状态
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

    if (newPassword.length < 4) {
        showAlert('新密码长度至少为4位', 'warning');
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

    if (httpCard) {
        httpCard.style.display = 'block';
        httpCard.style.visibility = 'visible';
        httpCard.style.opacity = '1';
        httpCard.classList.remove('d-none', 'd-hidden', 'hidden', 'invisible');
    }

    if (httpContainer) {
        httpContainer.style.display = 'block';
        httpContainer.style.visibility = 'visible';
        httpContainer.style.opacity = '1';
        httpContainer.classList.remove('d-none', 'd-hidden', 'hidden', 'invisible');
    }

    if (httpButton) {
        httpButton.style.display = 'inline-flex';
        httpButton.style.visibility = 'visible';
        httpButton.style.opacity = '1';
    }
}

// 页面加载完成后启动自动更新
document.addEventListener('DOMContentLoaded', function() {
    updateStatus();
    updateLogs();

    // 每5秒更新一次状态
    setInterval(updateStatus, 5000);

    // 每5秒更新一次日志
    setInterval(updateLogs, 5000);

    // 确保HTTP检查卡片始终可见
    ensureHttpCardVisibility();
});