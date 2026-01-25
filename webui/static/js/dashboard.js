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
            if (data && data.logs) {
                const logsDiv = document.getElementById('logs');
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
                document.getElementById('log-count').textContent = filteredLogs.length;

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

    // 初始化自动滚动按钮状态
    const autoScrollBtn = document.getElementById('auto-scroll-btn');
    if (autoScrollEnabled) {
        autoScrollBtn.classList.remove('btn-outline-primary');
        autoScrollBtn.classList.add('btn-primary');
    }

    // 每5秒更新一次状态
    setInterval(updateStatus, 5000);

    // 每5秒更新一次日志
    setInterval(updateLogs, 5000);

    // 日志等级筛选按钮组事件监听
    const filterButtons = document.querySelectorAll('.log-filter-btn');
    filterButtons.forEach(button => {
        button.addEventListener('click', function() {
            const level = this.dataset.level;

            if (level === 'all') {
                // 点击"全部"按钮，只选中全部，取消其他选择
                filterButtons.forEach(btn => btn.classList.remove('active'));
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
                    const anySelected = Array.from(filterButtons).some(btn => btn.classList.contains('active'));
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
    const searchInput = document.getElementById('log-search-input');
    if (searchInput) {
        // 使用防抖函数，避免频繁搜索
        let searchTimeout;
        searchInput.addEventListener('input', function() {
            clearTimeout(searchTimeout);
            searchTimeout = setTimeout(function() {
                updateLogs();
            }, 300); // 300ms 延迟后执行搜索
        });
    }

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
        });
    });
});