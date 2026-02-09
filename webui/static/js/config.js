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

// 保存配置
async function saveConfig() {
    console.log('saveConfig 函数被调用');
    const configData = {
        llbot: {
            path: document.getElementById('llbot-path').value,
            directory: document.getElementById('llbot-directory').value,
            wait_seconds: parseInt(document.getElementById('llbot-wait-seconds').value)
        },
        yunzai: {
            git_bash_path: document.getElementById('yunzai-git-bash-path').value,
            bash_directory: document.getElementById('yunzai-bash-directory').value,
            wait_seconds: parseInt(document.getElementById('yunzai-wait-seconds').value)
        },
        redis: {
            path: document.getElementById('redis-path').value
        },
        http_check: {
            url: document.getElementById('http-check-url').value,
            timeout: parseInt(document.getElementById('http-check-timeout').value)
        },
        auto_restart: {
            enabled: document.getElementById('auto-restart-enabled').checked,
            respect_manual_stop: document.getElementById('auto-restart-respect-manual-stop').checked
        },
        auto_login: {
            enabled: document.getElementById('auto-login-enabled').checked,
            username: document.getElementById('auto-login-username').value,
            password: document.getElementById('auto-login-password').value
        },
        web_auth: {
            username: document.getElementById('auth-username').value,
            password: document.getElementById('auth-password').value
        },
        git_update: {
            enabled: document.getElementById('git-update-enabled').checked,
            check_interval: parseInt(document.getElementById('git-update-check-interval').value),
            auto_pull: document.getElementById('git-update-auto-pull').checked,
            auto_restart: document.getElementById('git-update-auto-restart').checked
        },
        onebot: {
            enabled: document.getElementById('onebot-enabled').checked,
            ws_url: document.getElementById('onebot-ws-url').value,
            access_token: document.getElementById('onebot-access-token').value,
            reconnect_interval: parseInt(document.getElementById('onebot-reconnect-interval').value),
            authorized_users: document.getElementById('onebot-authorized-users').value
                .split(',')
                .map(id => id.trim())
                .filter(id => id !== '')
        },
        image_service: {
            enabled: document.getElementById('image-service-enabled').checked,
            port: parseInt(document.getElementById('image-service-port').value),
            url: document.getElementById('image-service-url').value
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
            for (let userId of configData.onebot.authorized_users) {
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
    console.log('准备发送保存请求:', configData);
    const response = await fetch('/api/config/update', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(configData)
    });

    console.log('收到响应:', response);
    const result = await response.json();
    console.log('响应内容:', result);

    if (response.ok) {
        showAlert('配置保存成功！配置已热重载生效。', 'success');
        // 更新密码字段显示
        document.getElementById('auth-password').value = '***';
        document.getElementById('auto-login-password').value = '***';
    } else {
        showAlert('保存失败：' + (result.error || '未知错误'), 'danger');
    }
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

// 检查更新
async function checkUpdates() {
    const updateProgress = document.getElementById('updateProgress');
    const updateResult = document.getElementById('updateResult');
    const updateResultAlert = document.getElementById('updateResultAlert');
    const updateAlert = document.getElementById('updateAlert');

    // 显示进度，隐藏结果
    updateProgress.style.display = 'block';
    updateResult.style.display = 'none';
    updateAlert.innerHTML = '';

    try {
        const response = await fetch('/api/check-updates', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            }
        });

        const data = await response.json();

        // 隐藏进度，显示结果
        updateProgress.style.display = 'none';
        updateResult.style.display = 'block';

        if (response.ok) {
            const result = data.result;
            let message = `<strong>${data.message}</strong><br><br>`;
            message += `<ul>`;
            if (result.updated > 0) {
                message += `<li class="text-success">✓ 已更新 ${result.updated} 个文件</li>`;
            }
            if (result.skipped > 0) {
                message += `<li class="text-info">ℹ 跳过 ${result.skipped} 个文件（已是最新）</li>`;
            }
            if (result.failed > 0) {
                message += `<li class="text-danger">✗ 失败 ${result.failed} 个文件</li>`;
            }
            message += `</ul>`;
            message += `<small class="text-muted">检查时间: ${result.timestamp}</small>`;

            updateResultAlert.className = 'alert alert-info';
            updateResultAlert.innerHTML = message;
        } else {
            updateResultAlert.className = 'alert alert-danger';
            updateResultAlert.innerHTML = `<strong>更新检查失败</strong><br>${data.error}`;
        }
    } catch (error) {
        updateProgress.style.display = 'none';
        updateResult.style.display = 'block';
        updateResultAlert.className = 'alert alert-danger';
        updateResultAlert.innerHTML = `<strong>更新检查失败</strong><br>${error}`;
    }
}

// 强制更新
async function forceUpdates() {
    const updateProgress = document.getElementById('updateProgress');
    const updateResult = document.getElementById('updateResult');
    const updateResultAlert = document.getElementById('updateResultAlert');
    const updateAlert = document.getElementById('updateAlert');

    // 显示进度，隐藏结果
    updateProgress.style.display = 'block';
    updateResult.style.display = 'none';
    updateAlert.innerHTML = '';

    try {
        const response = await fetch('/api/force-updates', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            }
        });

        const data = await response.json();

        // 隐藏进度，显示结果
        updateProgress.style.display = 'none';
        updateResult.style.display = 'block';

        if (response.ok) {
            const result = data.result;
            let message = `<strong>${data.message}</strong><br><br>`;
            message += `<ul>`;
            if (result.updated > 0) {
                message += `<li class="text-success">✓ 成功更新 ${result.updated} 个文件</li>`;
            }
            if (result.failed > 0) {
                message += `<li class="text-danger">✗ 失败 ${result.failed} 个文件</li>`;
            }
            message += `</ul>`;
            message += `<small class="text-muted">更新时间: ${result.timestamp}</small>`;

            updateResultAlert.className = 'alert alert-warning';
            updateResultAlert.innerHTML = message;
        } else {
            updateResultAlert.className = 'alert alert-danger';
            updateResultAlert.innerHTML = `<strong>强制更新失败</strong><br>${data.error}`;
        }
    } catch (error) {
        updateProgress.style.display = 'none';
        updateResult.style.display = 'block';
        updateResultAlert.className = 'alert alert-danger';
        updateResultAlert.innerHTML = `<strong>强制更新失败</strong><br>${error}`;
    }
}

// 检查Git仓库更新
async function checkGitUpdates() {
    const updateProgress = document.getElementById('updateProgress');
    const updateResult = document.getElementById('updateResult');
    const updateResultAlert = document.getElementById('updateResultAlert');
    const updateAlert = document.getElementById('updateAlert');

    // 显示进度，隐藏结果
    updateProgress.style.display = 'block';
    updateResult.style.display = 'none';
    updateAlert.innerHTML = '';

    try {
        const response = await fetch('/api/check-git-updates', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            }
        });

        const data = await response.json();

        // 隐藏进度，显示结果
        updateProgress.style.display = 'none';
        updateResult.style.display = 'block';

        if (response.ok) {
            const result = data;
            let message = `<strong>${data.message}</strong><br><br>`;
            message += `<div style="font-size: 14px; margin: 10px 0;">`;
            message += `<div><strong>当前分支:</strong> <code>${result.branch || '未知'}</code></div>`;
            if (result.local_commit) {
                message += `<div><strong>本地提交:</strong> <code>${result.local_commit.substring(0, 8)}</code></div>`;
            }
            if (result.remote_commit) {
                message += `<div><strong>远程提交:</strong> <code>${result.remote_commit.substring(0, 8)}</code></div>`;
            }
            message += `</div>`;

            if (result.has_update) {
                message += `<div class="alert alert-warning mt-3" style="margin: 10px 0 0 0;">`;
                message += `<i class="fas fa-exclamation-triangle me-2"></i>`;
                message += `<strong>发现新版本！</strong><br>`;
                message += `建议执行 <code>git pull</code> 拉取最新代码。`;
                message += `</div>`;
            } else {
                message += `<div class="alert alert-success mt-3" style="margin: 10px 0 0 0;">`;
                message += `<i class="fas fa-check-circle me-2"></i>`;
                message += `<strong>当前已是最新版本</strong>`;
                message += `</div>`;
            }

            updateResultAlert.className = result.has_update ? 'alert alert-warning' : 'alert alert-success';
            updateResultAlert.innerHTML = message;
        } else {
            updateResultAlert.className = 'alert alert-danger';
            updateResultAlert.innerHTML = `<strong>检查Git仓库更新失败</strong><br>${data.error}`;
        }
    } catch (error) {
        updateProgress.style.display = 'none';
        updateResult.style.display = 'block';
        updateResultAlert.className = 'alert alert-danger';
        updateResultAlert.innerHTML = `<strong>检查Git仓库更新失败</strong><br>${error}`;
    }
}

// 初始化配置页面的函数
function initConfigPage() {
    console.log('initConfigPage called');
    // 初始化密码字段显示为 ***
    const authPasswordField = document.getElementById('auth-password');
    const autoLoginPasswordField = document.getElementById('auto-login-password');
    if (authPasswordField && authPasswordField.value !== '***') {
        authPasswordField.value = '***';
    }
    if (autoLoginPasswordField && autoLoginPasswordField.value !== '***') {
        autoLoginPasswordField.value = '***';
    }

    // 侧边栏子菜单切换逻辑
    const sidebarItemHasChildren = document.querySelector('.sidebar-item-has-children');
    const sidebarChildLinks = document.querySelectorAll('.sidebar-child-link');
    const configPages = document.querySelectorAll('.config-page');

    console.log('sidebarChildLinks count:', sidebarChildLinks.length);
    console.log('configPages count:', configPages.length);
    console.log('sidebarChildLinks:', sidebarChildLinks);

    // 从 URL hash 中获取要激活的配置项
    const hash = window.location.hash.replace('#', '');
    const targetConfig = hash || sessionStorage.getItem('targetConfig');
    sessionStorage.removeItem('targetConfig'); // 清除存储的配置项

    // 默认展开配置管理子菜单
    if (sidebarItemHasChildren) {
        sidebarItemHasChildren.classList.add('expanded');

        // 激活配置项和对应的页面
        let targetLink = null;
        let targetPage = null;

        if (targetConfig) {
            // 如果有指定的配置项，激活它
            targetLink = sidebarItemHasChildren.querySelector(`.sidebar-child-link[data-config="${targetConfig}"]`);
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
    sidebarChildLinks.forEach(link => {
        console.log('Processing sidebar child link:', link, 'href:', link.href, 'getAttribute:', link.getAttribute('href'));
        // 防止重复绑定事件
        if (!link.hasAttribute('data-initialized')) {
            link.addEventListener('click', function(e) {
                console.log('Sidebar child link clicked:', this.getAttribute('data-config'));
                e.preventDefault();
                e.stopPropagation();

                const configType = this.getAttribute('data-config');
                const targetPage = document.getElementById('config-' + configType);

                console.log('Target page:', targetPage, 'configType:', configType);

                if (targetPage) {
                    // 先切换到目标页面
                    showConfigPage(this, targetPage);
                    // 然后使用 pushState 更新 URL hash (不会触发 hashchange 事件)
                    const currentUrl = window.location.pathname;
                    history.pushState({}, '', currentUrl + '#' + configType);
                } else {
                    console.error('Target page not found for config type:', configType);
                }
            });
            link.setAttribute('data-initialized', 'true');
            console.log('Event listener bound to link:', link);
        } else {
            console.log('Link already initialized:', link);
        }
    });

    // 监听 hash 变化
    if (!window.hasHashChangeListener) {
        window.addEventListener('hashchange', function() {
            // 如果是用户点击导致的 hash 变化,跳过处理
            if (window.isHashChangeFromClick) {
                return;
            }

            const hash = window.location.hash.replace('#', '');
            if (hash) {
                const targetLink = document.querySelector(`.sidebar-child-link[data-config="${hash}"]`);
                const targetPage = document.getElementById('config-' + hash);
                if (targetLink && targetPage) {
                    showConfigPage(targetLink, targetPage);
                }
            }
        });
        window.hasHashChangeListener = true;
    }

    // 修复模态框的 aria-hidden 警告
    fixModalAriaWarnings();
}

// 显示指定的配置页面
function showConfigPage(link, page) {
    const isDarkTheme = document.body.classList.contains('dark-theme');

    // 获取所有子菜单链接和配置页面
    const allChildLinks = document.querySelectorAll('.sidebar-child-link');
    const allConfigPages = document.querySelectorAll('.config-page');

    // 移除所有子菜单的激活状态
    allChildLinks.forEach(l => l.classList.remove('active'));
    allConfigPages.forEach(p => {
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

// 修复模态框的 aria-hidden 警告
function fixModalAriaWarnings() {
    const modals = document.querySelectorAll('.modal');
    modals.forEach(modal => {
        if (!modal.hasAttribute('data-modal-initialized')) {
            // 移除初始的 aria-hidden 属性，让 Bootstrap 动态管理
            modal.removeAttribute('aria-hidden');

            // 监听显示事件
            modal.addEventListener('show.bs.modal', function() {
                modal.removeAttribute('aria-hidden');
            });

            // 监听隐藏事件
            modal.addEventListener('hidden.bs.modal', function() {
                modal.setAttribute('aria-hidden', 'true');
                // 移除焦点，避免焦点保留在具有 aria-hidden 属性的元素上
                if (document.activeElement && modal.contains(document.activeElement)) {
                    document.activeElement.blur();
                }
            });
            modal.setAttribute('data-modal-initialized', 'true');
        }
    });
}

// 页面加载完成后初始化
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initConfigPage);
} else {
    // DOM 已经加载完成，直接初始化
    initConfigPage();
}