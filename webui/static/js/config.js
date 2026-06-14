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

// 显示警告消息
function showAlert(message, type) {
    const alertDiv = document.createElement('div');
    alertDiv.className = 'alert alert-' + type + ' alert-dismissible fade show position-fixed';
    alertDiv.style.top = '20px';
    alertDiv.style.right = '20px';
    alertDiv.style.zIndex = '9999';
    alertDiv.style.minWidth = '300px';
    alertDiv.innerHTML = message + '<button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>';

    document.body.appendChild(alertDiv);

    setTimeout(() => {
        alertDiv.remove();
    }, 3000);
}

// 保存配置 - 添加加载状态和防御性代码
async function saveConfig() {
    // 获取保存按钮并禁用，防止重复点击
    const saveButton = document.querySelector('.btn-save');
    if (!saveButton) return;

    const originalHTML = saveButton.innerHTML;
    saveButton.disabled = true;
    saveButton.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 保存中...';

    try {
        // 安全地获取字段值，使用默认值防止 undefined
        const getFieldValue = function(id) {
            const el = document.getElementById(id);
            return el ? el.value : '';
        };

        const getFieldChecked = function(id) {
            const el = document.getElementById(id);
            return el ? el.checked : false;
        };

        const parseFieldInt = function(id, defaultValue) {
            const el = document.getElementById(id);
            if (!el) return defaultValue;
            const val = parseInt(el.value, 10);
            return isNaN(val) ? defaultValue : val;
        };

        const configData = {
            llbot: {
                path: getFieldValue('llbot-path'),
                directory: getFieldValue('llbot-directory'),
                wait_seconds: parseFieldInt('llbot-wait-seconds', 30)
            },
            yunzai: {
                git_bash_path: getFieldValue('yunzai-git-bash-path'),
                bash_directory: getFieldValue('yunzai-bash-directory'),
                wait_seconds: parseFieldInt('yunzai-wait-seconds', 30),
                crash_detection: {
                    crash_threshold_seconds: parseFieldInt('yunzai-crash-threshold-seconds', 30),
                    max_crash_count: parseFieldInt('yunzai-max-crash-count', 3),
                    reset_timeout_hours: parseFieldInt('yunzai-reset-timeout-hours', 24)
                }
            },
            redis: {
                path: getFieldValue('redis-path')
            },
            http_check: {
                url: getFieldValue('http-check-url'),
                timeout: parseFieldInt('http-check-timeout', 10)
            },
            auto_restart: {
                enabled: getFieldChecked('auto-restart-enabled'),
                respect_manual_stop: getFieldChecked('auto-restart-respect-manual-stop')
            },
            auto_login: {
                enabled: getFieldChecked('auto-login-enabled'),
                username: getFieldValue('auto-login-username'),
                password: getFieldValue('auto-login-password')
            },
            web_auth: {
                username: getFieldValue('auth-username'),
                password: getFieldValue('auth-password')
            },
            git_update: {
                enabled: getFieldChecked('git-update-enabled'),
                check_interval: parseFieldInt('git-update-check-interval', 900),
                auto_pull: getFieldChecked('git-update-auto-pull'),
                auto_restart: getFieldChecked('git-update-auto-restart')
            },
            onebot: {
                enabled: getFieldChecked('onebot-enabled'),
                ws_url: getFieldValue('onebot-ws-url'),
                access_token: getFieldValue('onebot-access-token'),
                reconnect_interval: parseFieldInt('onebot-reconnect-interval', 5),
                authorized_users: getFieldValue('onebot-authorized-users')
                    .split(',')
                    .map(function(s) { return s.trim(); })
                    .filter(function(s) { return s !== ''; })
            },
            image_service: {
                enabled: getFieldChecked('image-service-enabled'),
                port: parseFieldInt('image-service-port', 3001),
                url: getFieldValue('image-service-url')
            }
        };

        // 验证配置
        if (!configData.llbot.path) {
            showAlert('llbot路径不能为空', 'warning');
            return;
        }
        if (!configData.llbot.directory) {
            showAlert('llbot目录不能为空', 'warning');
            return;
        }
        if (configData.llbot.wait_seconds < 1 || configData.llbot.wait_seconds > 60) {
            showAlert('llbot等待时间必须在 1-60 秒之间', 'warning');
            return;
        }

        if (!configData.yunzai.git_bash_path) {
            showAlert('Git Bash路径不能为空', 'warning');
            return;
        }
        if (!configData.yunzai.bash_directory) {
            showAlert('Yunzai目录不能为空', 'warning');
            return;
        }
        if (configData.yunzai.wait_seconds < 1 || configData.yunzai.wait_seconds > 60) {
            showAlert('Yunzai等待时间必须在 1-60 秒之间', 'warning');
            return;
        }
        if (configData.yunzai.crash_detection.crash_threshold_seconds < 5 || configData.yunzai.crash_detection.crash_threshold_seconds > 300) {
            showAlert('闪退阈值必须在 5-300 秒之间', 'warning');
            return;
        }
        if (configData.yunzai.crash_detection.max_crash_count < 1 || configData.yunzai.crash_detection.max_crash_count > 10) {
            showAlert('最大闪退次数必须在 1-10 之间', 'warning');
            return;
        }
        if (configData.yunzai.crash_detection.reset_timeout_hours < 1 || configData.yunzai.crash_detection.reset_timeout_hours > 168) {
            showAlert('重置超时必须在 1-168 小时之间', 'warning');
            return;
        }

        if (!configData.redis.path) {
            showAlert('Redis路径不能为空', 'warning');
            return;
        }

        if (configData.http_check.url && !configData.http_check.url.startsWith('http://') && !configData.http_check.url.startsWith('https://')) {
            showAlert('HTTP 检查 URL 应以 http:// 或 https:// 开头', 'warning');
            return;
        }
        if (configData.http_check.timeout < 1 || configData.http_check.timeout > 30) {
            showAlert('HTTP 超时时间必须在 1-30 秒之间', 'warning');
            return;
        }

        if (!configData.web_auth.username) {
            showAlert('用户名不能为空', 'warning');
            return;
        }

        // 验证 OneBot 配置
        if (configData.onebot.enabled) {
            if (!configData.onebot.ws_url) {
                showAlert('启用 OneBot 时 WebSocket URL 不能为空', 'warning');
                return;
            }
            if (!configData.onebot.ws_url.startsWith('ws://') && !configData.onebot.ws_url.startsWith('wss://')) {
                showAlert('WebSocket URL 应以 ws:// 或 wss:// 开头', 'warning');
                return;
            }
            if (configData.onebot.reconnect_interval < 1 || configData.onebot.reconnect_interval > 300) {
                showAlert('OneBot 重连间隔必须在 1-300 秒之间', 'warning');
                return;
            }
            // 验证授权用户列表格式
            if (configData.onebot.authorized_users.length > 0) {
                for (let i = 0; i < configData.onebot.authorized_users.length; i++) {
                    const userId = configData.onebot.authorized_users[i];
                    if (!/^\d+$/.test(userId)) {
                        showAlert('授权用户列表中包含无效的 QQ 号码: ' + userId, 'warning');
                        return;
                    }
                }
            }
        }

        // 验证图片服务配置
        if (configData.image_service.enabled) {
            if (configData.image_service.port < 1024 || configData.image_service.port > 65535) {
                showAlert('图片服务端口必须在 1024-65535 之间', 'warning');
                return;
            }
            if (!configData.image_service.url) {
                showAlert('启用图片服务时 URL 不能为空', 'warning');
                return;
            }
            if (!configData.image_service.url.startsWith('http://') && !configData.image_service.url.startsWith('https://')) {
                showAlert('图片服务 URL 应以 http:// 或 https:// 开头', 'warning');
                return;
            }
        }
        // 验证密码字段 - only check if the user provided a new password
        if (configData.web_auth.password && configData.web_auth.password !== '***') {
            // User entered a new password, validate it
            if (configData.web_auth.password.length < 4) {
                showAlert('密码长度至少为4位', 'warning');
                return;
            }
        } else {
            // Password field shows '***' (unchanged), so we'll remove it from the payload to indicate "keep existing"
            delete configData.web_auth.password;
        }

        // 验证自动登录配置
        if (configData.auto_login.enabled) {
            // 如果密码字段为空或显示为 ***，说明用户没有修改密码
            // 此时应该保留现有密码，不需要重新输入
            if (!configData.auto_login.password || configData.auto_login.password === '***') {
                // 删除密码字段，告诉后端保持现有密码不变
                delete configData.auto_login.password;
            }
        } else {
            // 如果未启用自动登录，删除密码字段以保持现有密码不变
            delete configData.auto_login.password;
        }

        // 发送保存请求
        var response;
        try {
            response = await safeFetch('/api/config/update', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(configData)
            });
        } catch (fetchError) {
            showAlert('请求失败: ' + fetchError.message, 'danger');
            return;
        }

        var result = await response.json();

        if (response.ok) {
            showAlert('配置保存成功！配置已热重载生效。', 'success');
            // 更新密码字段显示
            var authPasswordField = document.getElementById('auth-password');
            if (authPasswordField) authPasswordField.value = '***';
            var autoLoginPasswordField = document.getElementById('auto-login-password');
            if (autoLoginPasswordField) autoLoginPasswordField.value = '***';
        } else if (response.status === 429) {
            showAlert(result.error || '配置正在更新中，请稍后再试', 'warning');
        } else {
            showAlert('保存失败：' + (result.error || '未知错误'), 'danger');
        }
    } catch (error) {
        console.error('saveConfig error:', error);
        showAlert('操作失败: ' + (error.message || String(error)), 'danger');
    } finally {
        // 恢复按钮状态
        if (saveButton) {
            saveButton.disabled = false;
            saveButton.innerHTML = originalHTML;
        }
    }
}

// 修改密码 - 添加按钮状态管理和防御性代码
function changePassword() {
    const currentPasswordEl = document.getElementById('currentPassword');
    const newUsernameEl = document.getElementById('newUsername');
    const newPasswordEl = document.getElementById('newPassword');

    if (!currentPasswordEl || !newPasswordEl) {
        showAlert('表单元素不完整', 'danger');
        return;
    }

    const currentPassword = currentPasswordEl.value;
    const newUsername = newUsernameEl ? newUsernameEl.value : '';
    const newPassword = newPasswordEl.value;

    if (!currentPassword || !newPassword) {
        showAlert('请填写当前密码和新密码', 'warning');
        return;
    }

    // 查找密码模态框内的"保存更改"按钮
    const passwordModal = document.getElementById('passwordModal');
    let passwordSaveBtn = null;
    if (passwordModal) {
        passwordSaveBtn = passwordModal.querySelector('button[onclick="changePassword()"]');
    }

    const originalBtnHTML = passwordSaveBtn ? passwordSaveBtn.innerHTML : null;
    if (passwordSaveBtn) {
        passwordSaveBtn.disabled = true;
        passwordSaveBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 处理中...';
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
    .then(function(response) { return response.json(); })
    .then(function(data) {
        if (data.message) {
            showAlert(data.message, 'success');
            // 关闭模态框
            const modalEl = document.getElementById('passwordModal');
            const modal = modalEl && (typeof bootstrap !== 'undefined') ? bootstrap.Modal.getInstance(modalEl) : null;
            if (modal) {
                modal.hide();
            }
        } else if (data.error) {
            showAlert(data.error, 'danger');
        }
    })
    .catch(function(error) {
        showAlert('修改密码失败: ' + error, 'danger');
    })
    .finally(function() {
        if (passwordSaveBtn && originalBtnHTML) {
            passwordSaveBtn.disabled = false;
            passwordSaveBtn.innerHTML = originalBtnHTML;
        }
    });
}

// 辅助函数：显示更新进度
function showUpdateProgress() {
    var updateProgress = document.getElementById('updateProgress');
    var updateResult = document.getElementById('updateResult');
    if (updateProgress) updateProgress.style.display = 'block';
    if (updateResult) {
        updateResult.style.display = 'none';
        updateResult.innerHTML = '';  // 清空之前的结果
    }
}

// 辅助函数：隐藏更新进度
function hideUpdateProgress() {
    var updateProgress = document.getElementById('updateProgress');
    if (updateProgress) updateProgress.style.display = 'none';
}

// 辅助函数：显示更新结果 alert
function showUpdateResultAlert(alertHTML, alertClass) {
    hideUpdateProgress();  // 确保进度条被隐藏
    var updateResult = document.getElementById('updateResult');
    var updateResultAlert = document.getElementById('updateResultAlert');
    if (updateResult) {
        updateResult.style.display = 'block';
    }
    if (updateResultAlert) {
        updateResultAlert.className = 'alert ' + (alertClass || 'alert-info');
        updateResultAlert.innerHTML = alertHTML;
    }
}

// 通用 fetch 包装函数 - 简化版：2xx 一律返回，非 2xx 且非 JSON 才抛错
async function safeFetch(url, options) {
    var response = await fetch(url, options);

    // 2xx 成功响应 - 直接返回
    if (response.ok) {
        return response;
    }

    // 非 2xx 响应 - 检查是否是 JSON 格式
    var contentType = response.headers.get('content-type') || '';

    // 如果是 JSON 格式的错误响应（如 429），返回给调用者处理
    if (contentType.indexOf('application/json') !== -1) {
        return response;
    }

    // 非 JSON 错误响应 - 可能是 HTML 登录页或其他错误页
    if (response.status === 401) {
        throw new Error('登录已过期，请刷新页面重新登录');
    } else if (response.status === 403) {
        throw new Error('没有权限执行此操作');
    } else if (response.status >= 500) {
        throw new Error('服务器错误 (HTTP ' + response.status + ')');
    } else {
        throw new Error('请求失败 (HTTP ' + response.status + ')');
    }
}

// 安全解析 JSON - 带 fallback 的响应解析
async function parseJsonResponse(response) {
    try {
        return await response.json();
    } catch (e) {
        try {
            var text = await response.text();
            return { message: text, _raw_text: true };
        } catch (e2) {
            return { message: '（无响应内容）' };
        }
    }
}

// 检查更新
async function checkUpdates() {
    try {
        showUpdateProgress();

        var response = await safeFetch('/api/check-updates', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });

        var data = await parseJsonResponse(response);

        if (response.ok) {
            if (data.result) {
                var result = data.result;
                var message = '<strong>' + (data.message || '更新检查完成') + '</strong><br><br>';
                message += '<ul>';
                if (typeof result.updated === 'number' && result.updated > 0) {
                    message += '<li class="text-success">✓ 已更新 ' + result.updated + ' 个文件</li>';
                }
                if (typeof result.skipped === 'number' && result.skipped > 0) {
                    message += '<li class="text-info">ℹ 跳过 ' + result.skipped + ' 个文件（已是最新）</li>';
                }
                if (typeof result.failed === 'number' && result.failed > 0) {
                    message += '<li class="text-danger">✗ 失败 ' + result.failed + ' 个文件</li>';
                }
                if (message.indexOf('<li>') === -1 && message.indexOf('class="text-') === -1) {
                    message += '<li class="text-muted">无需更新</li>';
                }
                message += '</ul>';
                if (result.timestamp) {
                    message += '<small class="text-muted">检查时间: ' + result.timestamp + '</small>';
                }
                showUpdateResultAlert(message, 'alert-info');
            } else {
                // 没有 result 字段，直接显示 message
                showUpdateResultAlert('<strong>' + (data.message || '更新检查完成') + '</strong>', 'alert-info');
            }
        } else if (response.status === 429) {
            showUpdateResultAlert('<strong>操作进行中</strong><br>' + (data.error || '请稍后再试'), 'alert-warning');
        } else {
            showUpdateResultAlert('<strong>更新检查失败</strong><br>' + (data.error || 'HTTP ' + response.status), 'alert-danger');
        }
    } catch (error) {
        showUpdateResultAlert('<strong>更新检查失败</strong><br>' + (error.message || String(error)), 'alert-danger');
    }
}

// 强制更新
async function forceUpdates() {
    try {
        showUpdateProgress();

        var response = await safeFetch('/api/force-updates', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });

        var data = await parseJsonResponse(response);

        if (response.ok) {
            if (data.result) {
                var result = data.result;
                var message = '<strong>' + (data.message || '强制更新完成') + '</strong><br><br>';
                message += '<ul>';
                if (typeof result.updated === 'number' && result.updated > 0) {
                    message += '<li class="text-success">✓ 成功更新 ' + result.updated + ' 个文件</li>';
                }
                if (typeof result.failed === 'number' && result.failed > 0) {
                    message += '<li class="text-danger">✗ 失败 ' + result.failed + ' 个文件</li>';
                }
                if (message.indexOf('<li>') === -1 && message.indexOf('class="text-') === -1) {
                    message += '<li class="text-muted">无需更新</li>';
                }
                message += '</ul>';
                if (result.timestamp) {
                    message += '<small class="text-muted">更新时间: ' + result.timestamp + '</small>';
                }
                showUpdateResultAlert(message, 'alert-warning');
            } else {
                showUpdateResultAlert('<strong>' + (data.message || '强制更新完成') + '</strong>', 'alert-warning');
            }
        } else if (response.status === 429) {
            showUpdateResultAlert('<strong>操作进行中</strong><br>' + (data.error || '请稍后再试'), 'alert-warning');
        } else {
            showUpdateResultAlert('<strong>强制更新失败</strong><br>' + (data.error || 'HTTP ' + response.status), 'alert-danger');
        }
    } catch (error) {
        showUpdateResultAlert('<strong>强制更新失败</strong><br>' + (error.message || String(error)), 'alert-danger');
    }
}

// 检查Git仓库更新
async function checkGitUpdates() {
    try {
        showUpdateProgress();

        var response = await safeFetch('/api/check-git-updates', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });

        var data = await parseJsonResponse(response);

        if (response.ok) {
            var message = '<strong>' + (data.message || 'Git仓库检查完成') + '</strong><br><br>';
            message += '<div style="font-size: 14px; margin: 10px 0;">';
            if (data.branch) {
                message += '<div><strong>当前分支:</strong> <code>' + data.branch + '</code></div>';
            }
            if (data.local_commit) {
                message += '<div><strong>本地提交:</strong> <code>' + String(data.local_commit).substring(0, 8) + '</code></div>';
            }
            if (data.remote_commit) {
                message += '<div><strong>远程提交:</strong> <code>' + String(data.remote_commit).substring(0, 8) + '</code></div>';
            }
            message += '</div>';

            if (data.has_update) {
                message += '<div class="alert alert-warning mt-3" style="margin: 10px 0 0 0;">';
                message += '<i class="fas fa-exclamation-triangle me-2"></i>';
                message += '<strong>发现新版本！</strong><br>';
                message += '建议执行 <code>git pull</code> 拉取最新代码。';
                message += '</div>';
            } else {
                message += '<div class="alert alert-success mt-3" style="margin: 10px 0 0 0;">';
                message += '<i class="fas fa-check-circle me-2"></i>';
                message += '<strong>当前已是最新版本</strong>';
                message += '</div>';
            }

            showUpdateResultAlert(message, data.has_update ? 'alert-warning' : 'alert-success');
        } else if (response.status === 429) {
            showUpdateResultAlert('<strong>操作进行中</strong><br>' + (data.error || '请稍后再试'), 'alert-warning');
        } else {
            showUpdateResultAlert('<strong>检查Git仓库更新失败</strong><br>' + (data.error || 'HTTP ' + response.status), 'alert-danger');
        }
    } catch (error) {
        showUpdateResultAlert('<strong>检查Git仓库更新失败</strong><br>' + (error.message || String(error)), 'alert-danger');
    }
}

// 手动绑定模态框按钮 - 不依赖 Bootstrap data-api，确保动态 DOM 加载后能正常工作
function setupModalButtons() {
    if (typeof bootstrap === 'undefined' || !bootstrap.Modal) {
        return;
    }

    // 为所有 modal 触发器按钮手动绑定事件
    // 移除 data-bs-toggle 属性，并用自己的逻辑处理
    var modalTriggers = document.querySelectorAll('[data-bs-toggle="modal"]');
    modalTriggers.forEach(function(trigger) {
        if (trigger.hasAttribute('data-modal-bound')) {
            return;
        }
        trigger.setAttribute('data-modal-bound', 'true');

        // 获取目标 modal 的 ID
        var targetSelector = trigger.getAttribute('data-bs-target');
        if (!targetSelector) {
            targetSelector = trigger.getAttribute('href');
            if (targetSelector && targetSelector.indexOf('#') !== 0) {
                return;
            }
        }
        if (!targetSelector) {
            return;
        }

        // 移除 data-bs-toggle 属性（我们自己控制）
        trigger.removeAttribute('data-bs-toggle');

        trigger.addEventListener('click', function(e) {
            e.preventDefault();
            e.stopPropagation();

            var modalElement = document.querySelector(targetSelector);
            if (!modalElement) {
                return;
            }

            // 关键修复：每次点击时先销毁旧实例再创建新实例
            // 这解决了动态 DOM 加载时 Bootstrap 无法正确初始化的问题
            try {
                var existingInstance = bootstrap.Modal.getInstance(modalElement);
                if (existingInstance) {
                    existingInstance.dispose();
                }
            } catch (err) {
                // 忽略销毁失败，继续创建新实例
            }

            // 清除 Bootstrap 在元素上可能残留的数据
            try {
                for (var key in modalElement) {
                    if (key.indexOf('bs') === 0 || key.indexOf('data') === 0) {
                        try {
                            delete modalElement[key];
                        } catch (innerErr) {
                            // 忽略
                        }
                    }
                }
            } catch (err2) {
                // 忽略
            }

            // 创建新的 Modal 实例并显示
            var modal = new bootstrap.Modal(modalElement, {
                backdrop: true,
                keyboard: true,
                focus: true
            });
            modal.show();
        });
    });

    // 额外处理：为 modal 内的关闭按钮也手动绑定
    var modalCloseButtons = document.querySelectorAll('[data-bs-dismiss="modal"]');
    modalCloseButtons.forEach(function(btn) {
        if (btn.hasAttribute('data-modal-close-bound')) {
            return;
        }
        btn.setAttribute('data-modal-close-bound', 'true');

        // 找最近的 modal 元素
        btn.addEventListener('click', function(e) {
            var parentModal = btn.closest('.modal');
            if (parentModal) {
                e.preventDefault();
                try {
                    var modalInstance = bootstrap.Modal.getInstance(parentModal);
                    if (modalInstance) {
                        modalInstance.hide();
                    }
                } catch (err) {
                    // 忽略
                }
            }
        });
    });
}

// 初始化配置页面的函数
function initConfigPage() {
    // 初始化密码字段显示为 ***
    var authPasswordField = document.getElementById('auth-password');
    var autoLoginPasswordField = document.getElementById('auto-login-password');
    if (authPasswordField && authPasswordField.value !== '***') {
        authPasswordField.value = '***';
    }
    if (autoLoginPasswordField && autoLoginPasswordField.value !== '***') {
        autoLoginPasswordField.value = '***';
    }

    // 侧边栏子菜单切换逻辑
    var sidebarItemHasChildren = document.querySelector('.sidebar-item-has-children');
    var sidebarChildLinks = document.querySelectorAll('.sidebar-child-link');

    // 从 URL hash 中获取要激活的配置项
    var hash = window.location.hash.replace('#', '');
    var targetConfig = hash || (typeof sessionStorage !== 'undefined' ? sessionStorage.getItem('targetConfig') : null);
    try {
        if (typeof sessionStorage !== 'undefined') sessionStorage.removeItem('targetConfig');
    } catch (e) {
        // 忽略 sessionStorage 错误
    }

    // 默认展开配置管理子菜单
    if (sidebarItemHasChildren) {
        sidebarItemHasChildren.classList.add('expanded');

        // 激活配置项和对应的页面
        var targetLink = null;
        var targetPage = null;

        if (targetConfig) {
            // 如果有指定的配置项，激活它
            targetLink = sidebarItemHasChildren.querySelector('.sidebar-child-link[data-config="' + targetConfig + '"]');
            targetPage = document.getElementById('config-' + targetConfig);
        }

        // 如果没有指定配置项或找不到对应的配置项，激活第一个
        if (!targetLink || !targetPage) {
            targetLink = sidebarItemHasChildren.querySelector('.sidebar-child-link');
            targetPage = document.getElementById('config-llbot');
        }

        if (targetLink && targetPage) {
            showConfigPage(targetLink, targetPage);
        }
    }

    // 点击子菜单项切换配置页面
    sidebarChildLinks.forEach(function(link) {
        // 防止重复绑定事件
        if (!link.hasAttribute('data-initialized')) {
            link.addEventListener('click', function(e) {
                e.preventDefault();
                e.stopPropagation();

                var configType = this.getAttribute('data-config');
                var targetPageEl = document.getElementById('config-' + configType);

                if (targetPageEl) {
                    // 先切换到目标页面
                    showConfigPage(this, targetPageEl);
                    // 然后使用 pushState 更新 URL hash (不会触发 hashchange 事件)
                    var currentUrl = window.location.pathname;
                    if (typeof history !== 'undefined' && history.pushState) {
                        history.pushState({}, '', currentUrl + '#' + configType);
                    }
                }
            });
            link.setAttribute('data-initialized', 'true');
        }
    });

    // 监听 hash 变化
    if (!window.hasHashChangeListener) {
        window.addEventListener('hashchange', function() {
            // 如果是用户点击导致的 hash 变化,跳过处理
            if (window.isHashChangeFromClick) {
                return;
            }

            var changedHash = window.location.hash.replace('#', '');
            if (changedHash) {
                var targetLinkEl = document.querySelector('.sidebar-child-link[data-config="' + changedHash + '"]');
                var targetPageEl = document.getElementById('config-' + changedHash);
                if (targetLinkEl && targetPageEl) {
                    showConfigPage(targetLinkEl, targetPageEl);
                }
            }
        });
        window.hasHashChangeListener = true;
    }

    // 关键修复：手动绑定模态框按钮
    setupModalButtons();
}

// 显示指定的配置页面 - 添加防御性检查
function showConfigPage(link, page) {
    if (!link || !page) {
        return;
    }

    // 获取所有子菜单链接和配置页面
    var allChildLinks = document.querySelectorAll('.sidebar-child-link');
    var allConfigPages = document.querySelectorAll('.config-page');

    // 移除所有子菜单的激活状态
    allChildLinks.forEach(function(l) { l.classList.remove('active'); });
    allConfigPages.forEach(function(p) {
        p.classList.remove('show', 'active');
        // 清除行内样式
        p.style.opacity = '';
        p.style.transform = '';
    });

    // 激活当前选中的子菜单项
    link.classList.add('active');

    // 显示对应的配置页面
    page.classList.add('show', 'active');
}

// 页面加载完成后初始化
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initConfigPage);
} else {
    // DOM 已经加载完成，直接初始化
    initConfigPage();
}