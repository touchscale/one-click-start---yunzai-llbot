// 主题管理
const THEME_STORAGE_KEY = 'app-theme';

// 获取保存的主题
function getSavedTheme() {
    return localStorage.getItem(THEME_STORAGE_KEY) || 'system';
}

// 保存主题设置
function saveTheme(theme) {
    localStorage.setItem(THEME_STORAGE_KEY, theme);
}

// 检测系统主题
function getSystemTheme() {
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

// 获取主题图标
function getThemeIcon(theme) {
    switch (theme) {
        case 'light':
            return 'fa-sun';
        case 'dark':
            return 'fa-moon';
        case 'system':
            return 'fa-desktop';
        default:
            return 'fa-desktop';
    }
}

// 设置主题
function setTheme(theme, event) {
    // 阻止默认行为（防止链接跳转或页面刷新）
    if (event) {
        event.preventDefault();
        event.stopPropagation();
    }
    applyTheme(theme);
}

// 应用主题
function applyTheme(theme) {
    const body = document.body;
    const themeIcon = document.getElementById('current-theme-icon');

    // 移除所有主题类
    body.classList.remove('light-theme', 'dark-theme');

    let actualTheme = theme;

    // 如果是跟随系统，检测系统主题
    if (theme === 'system') {
        actualTheme = getSystemTheme();
    }

    // 应用主题类
    body.classList.add(actualTheme + '-theme');

    // 立即设置背景色，避免闪烁
    if (actualTheme === 'dark') {
        body.style.background = 'linear-gradient(135deg, #1a1a2e 0%, #16213e 100%)';
    } else {
        body.style.background = 'linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%)';
    }

    // 更新图标
    if (themeIcon) {
        themeIcon.className = 'fas ' + getThemeIcon(theme);
    }

    // 保存主题设置
    saveTheme(theme);
}

// 初始化主题
function initTheme() {
    const savedTheme = getSavedTheme();
    applyTheme(savedTheme);

    // 监听系统主题变化
    if (savedTheme === 'system') {
        window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
            applyTheme('system');
        });
    }
}

// 切换侧边栏显示/隐藏
function toggleSidebar() {
    const sidebar = document.querySelector('.sidebar');
    const mainContent = document.querySelector('.main-content');
    const toggleIcon = document.getElementById('sidebar-toggle-icon');

    if (sidebar && mainContent) {
        sidebar.classList.toggle('collapsed');
        mainContent.classList.toggle('expanded');

        // 切换图标旋转效果
        if (toggleIcon) {
            if (sidebar.classList.contains('collapsed')) {
                toggleIcon.style.transform = 'rotate(180deg)';
            } else {
                toggleIcon.style.transform = 'rotate(0deg)';
            }
        }
    }
}

// 立即执行主题初始化，在页面渲染前
(function() {
    const savedTheme = getSavedTheme();
    const body = document.body;

    // 移除所有主题类
    body.classList.remove('light-theme', 'dark-theme');

    let actualTheme = savedTheme;

    // 如果是跟随系统，检测系统主题
    if (savedTheme === 'system') {
        actualTheme = getSystemTheme();
    }

    // 立即应用主题类
    body.classList.add(actualTheme + '-theme');

    // 立即设置body的背景色，避免闪烁
    if (actualTheme === 'dark') {
        body.style.background = 'linear-gradient(135deg, #1a1a2e 0%, #16213e 100%)';
    } else {
        body.style.background = 'linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%)';
    }
})();

// 页面加载时初始化主题（处理图标更新）
document.addEventListener('DOMContentLoaded', function() {
    initTheme();

    // 拦截侧边栏导航，实现平滑切换
    const sidebarLinks = document.querySelectorAll('.sidebar-link');
    sidebarLinks.forEach(link => {
        link.addEventListener('click', function(e) {
            const href = this.getAttribute('href');

            // 只拦截内部页面导航
            if (href && (href === '/' || href === '/config')) {
                e.preventDefault();

                // 显示加载提示
                const mainContent = document.querySelector('.main-content .container-fluid');
                if (mainContent) {
                    mainContent.style.opacity = '0.5';
                }

                // 使用fetch加载新页面
                fetch(href, {
                    headers: {
                        'X-Requested-With': 'XMLHttpRequest'
                    }
                })
                .then(response => {
                    if (!response.ok) throw new Error('Network response was not ok');
                    return response.text();
                })
                .then(html => {
                    // 创建临时DOM解析HTML
                    const parser = new DOMParser();
                    const doc = parser.parseFromString(html, 'text/html');

                    // 替换主内容区域
                    const newMainContent = doc.querySelector('.main-content');
                    const currentMainContent = document.querySelector('.main-content');

                    if (newMainContent && currentMainContent) {
                        currentMainContent.innerHTML = newMainContent.innerHTML;

                        // 更新页面标题
                        document.title = doc.title;

                        // 更新激活的侧边栏链接
                        document.querySelectorAll('.sidebar-link').forEach(l => l.classList.remove('active'));
                        this.classList.add('active');

                        // 重新初始化主题图标
                        const newThemeIcon = document.getElementById('current-theme-icon');
                        if (newThemeIcon) {
                            const savedTheme = getSavedTheme();
                            newThemeIcon.className = 'fas ' + getThemeIcon(savedTheme);
                        }

                        // 恢复透明度
                        if (mainContent) {
                            mainContent.style.opacity = '1';
                        }

                        // 如果是 dashboard 页面，重新初始化日志筛选功能
                        if (href === '/') {
                            // 延迟一点时间确保DOM完全更新
                            setTimeout(function() {
                                if (typeof initLogFilters === 'function') {
                                    initLogFilters();
                                }
                                if (typeof updateStatus === 'function') {
                                    updateStatus();
                                }
                                if (typeof updateLogs === 'function') {
                                    updateLogs();
                                }
                            }, 100);
                        }

                        // 更新URL但不刷新页面
                        history.pushState({}, '', href);
                    }
                })
                .catch(error => {
                    console.error('Error loading page:', error);
                    // 如果出错，回退到普通导航
                    window.location.href = href;
                });
            }
        });
    });

    // 监听浏览器后退/前进按钮
    window.addEventListener('popstate', function(e) {
        location.reload();
    });
});