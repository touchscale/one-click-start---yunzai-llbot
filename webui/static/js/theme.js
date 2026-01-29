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

    // 更新图标
    if (themeIcon) {
        themeIcon.className = 'fas ' + getThemeIcon(theme);
    }

    // 保存主题设置
    saveTheme(theme);
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
function setTheme(theme) {
    applyTheme(theme);
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

// 页面加载时初始化主题
document.addEventListener('DOMContentLoaded', function() {
    initTheme();
});