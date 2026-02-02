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

    // 发送保存请求
    const response = await fetch('/api/config/update', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(configData)
    });

    const result = await response.json();

    if (response.ok) {
        showAlert('配置保存成功！配置已热重载生效。', 'success');
        // 更新密码字段显示
        document.getElementById('auth-password').value = '***';
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

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', function() {
    // 激活第一个选项卡
    const firstTab = document.querySelector('#configTabs .nav-link');
    if (firstTab) {
        firstTab.click();
    }

    // 修复模态框的 aria-hidden 警告
    const modals = document.querySelectorAll('.modal');
    modals.forEach(modal => {
        // 移除初始的 aria-hidden 属性，让 Bootstrap 动态管理
        modal.removeAttribute('aria-hidden');

        // 监听显示事件
        modal.addEventListener('show.bs.modal', function() {
            modal.removeAttribute('aria-hidden');
        });

        // 监听隐藏事件
        modal.addEventListener('hidden.bs.modal', function() {
            modal.setAttribute('aria-hidden', 'true');
        });
    });
});