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

// 计算密码强度分数
function getPasswordStrengthScore(password) {
    let score = 0;

    // 基础分数：长度贡献
    const lengthScore = Math.min(password.length * 4, 40);
    score += lengthScore;

    // 字符类型多样性加分
    if (/[a-z]/.test(password)) score += 10;
    if (/[A-Z]/.test(password)) score += 10;
    if (/\d/.test(password)) score += 10;
    if (/[!@#$%^&*(),.?":{}|<>]/.test(password)) score += 15;

    // 字符种类数量加分
    let charTypes = 0;
    if (/[a-z]/.test(password)) charTypes++;
    if (/[A-Z]/.test(password)) charTypes++;
    if (/\d/.test(password)) charTypes++;
    if (/[!@#$%^&*(),.?":{}|<>]/.test(password)) charTypes++;

    if (charTypes === 4) score += 15;
    else if (charTypes === 3) score += 10;

    // 惩罚项
    const commonWeakPasswords = ['password', '12345678', 'qwerty', 'abc123', 'password1', '123456789', '11111111', 'admin', 'admin123', 'root', 'welcome', 'monkey', 'dragon', 'master', 'letmein', 'login', 'passw0rd', 'qwerty123', '123abc', 'test123', 'admin1234', 'password123', '1234567890', 'qwertyuiop', 'asdfghjkl', 'zxcvbnm', '1q2w3e4r', 'a1b2c3d4'];
    if (commonWeakPasswords.includes(password.toLowerCase())) score -= 30;
    if (/(.)\1{2,}/.test(password)) score -= 10;
    if (/(012|123|234|345|456|567|678|789|890|abc|bcd|cde|def|efg|fgh|ghi|hij|ijk|jkl|klm|lmn|mno|nop|opq|pqr|qrs|rst|stu|tuv|uvw|vwx|wxy|xyz)/i.test(password)) score -= 10;

    return Math.max(0, Math.min(100, score));
}

// 获取密码强度级别
function getPasswordStrengthLevel(score) {
    if (score < 30) return { level: 0, label: '非常弱', color: '#dc3545' };
    if (score < 50) return { level: 1, label: '弱', color: '#fd7e14' };
    if (score < 70) return { level: 2, label: '中等', color: '#ffc107' };
    if (score < 90) return { level: 3, label: '强', color: '#20c997' };
    return { level: 4, label: '非常强', color: '#28a745' };
}

// 显示密码强度指示器
function updatePasswordStrengthIndicator(passwordFieldId, strengthIndicatorId) {
    const passwordField = document.getElementById(passwordFieldId);
    const strengthIndicator = document.getElementById(strengthIndicatorId);

    if (!passwordField || !strengthIndicator) return;

    const password = passwordField.value;
    const score = getPasswordStrengthScore(password);
    const strength = getPasswordStrengthLevel(score);

    // 更新强度条宽度
    const strengthBar = strengthIndicator.querySelector('.password-strength-bar');
    if (strengthBar) {
        strengthBar.style.width = `${score}%`;
        strengthBar.style.backgroundColor = strength.color;
    }

    // 更新强度文本
    const strengthText = strengthIndicator.querySelector('.password-strength-text');
    if (strengthText) {
        strengthText.textContent = strength.label;
        strengthText.style.color = strength.color;
    }
}

// 页面初始化：隐藏错误消息并绑定重置表单提交处理
document.addEventListener('DOMContentLoaded', function() {
    const errorDiv = document.querySelector('.error-message');
    if (errorDiv) {
        setTimeout(function() {
            errorDiv.style.display = 'none';
        }, 5000);
    }

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

    const form = document.getElementById('resetPasswordForm');
    if (form) {
        form.addEventListener('submit', async function(event) {
            event.preventDefault();
            const new_password = document.getElementById('new_password').value.trim();
            const confirm_password = document.getElementById('confirm_password').value.trim();
            const confirmEdit = document.getElementById('confirmEdit').checked;
            const alertDiv = document.getElementById('resetAlert');
            alertDiv.innerHTML = '';

            if (!new_password || !confirm_password) {
                alertDiv.innerHTML = '<div class="alert alert-warning">请输入新密码并确认</div>';
                return;
            }
            if (new_password !== confirm_password) {
                alertDiv.innerHTML = '<div class="alert alert-warning">两次密码输入不一致</div>';
                return;
            }

            // 验证密码强度
            const errors = validatePasswordStrength(new_password);
            if (errors.length > 0) {
                alertDiv.innerHTML = '<div class="alert alert-warning">' + errors.join('；') + '</div>';
                return;
            }

            if (!confirmEdit) {
                alertDiv.innerHTML = '<div class="alert alert-warning">请确认将更新配置文件</div>';
                return;
            }

            try {
                const resp = await fetch('/api/reset-password', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ new_password, confirm_password, confirm_edit: confirmEdit })
                });
                const data = await resp.json();
                if (resp.ok) {
                    alertDiv.innerHTML = '<div class="alert alert-success">' + (data.message || '密码重置成功') + '</div>';
                    setTimeout(function() {
                        const modalEl = document.getElementById('forgotPasswordModal');
                        const modal = bootstrap.Modal.getInstance(modalEl) || new bootstrap.Modal(modalEl);
                        modal.hide();
                    }, 1200);
                } else {
                    let errorMessage = data.message || '重置失败';
                    if (data.errors && data.errors.length > 0) {
                        errorMessage += '：' + data.errors.join('；');
                    }
                    alertDiv.innerHTML = '<div class="alert alert-danger">' + errorMessage + '</div>';
                }
            } catch (err) {
                alertDiv.innerHTML = '<div class="alert alert-danger">请求失败: ' + err + '</div>';
            }
        });
    }
});