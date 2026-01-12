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

// 页面初始化：隐藏错误消息并绑定重置表单提交处理
document.addEventListener('DOMContentLoaded', function() {
    const errorDiv = document.querySelector('.error-message');
    if (errorDiv) {
        setTimeout(function() {
            errorDiv.style.display = 'none';
        }, 5000);
    }

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
            if (new_password.length < 4) {
                alertDiv.innerHTML = '<div class="alert alert-warning">密码太短（至少4位）</div>';
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
                    alertDiv.innerHTML = '<div class="alert alert-danger">' + (data.message || '重置失败') + '</div>';
                }
            } catch (err) {
                alertDiv.innerHTML = '<div class="alert alert-danger">请求失败: ' + err + '</div>';
            }
        });
    }
});