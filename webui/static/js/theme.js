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

    // 防抖变量,防止连续快速点击
    let isNavigating = false;
    let pendingNavigationHref = null;

    // 拦截侧边栏导航，实现平滑切换
    const sidebarLinks = document.querySelectorAll('.sidebar-link');
    sidebarLinks.forEach(link => {
        link.addEventListener('click', function(e) {
            const href = this.getAttribute('href');

            // 只拦截内部页面导航
            if (href && (href === '/' || href === '/config')) {
                e.preventDefault();

                // 如果正在导航中,记录待处理的导航
                if (isNavigating) {
                    pendingNavigationHref = href;
                    return;
                }

                // 设置导航标志
                isNavigating = true;
                pendingNavigationHref = null;

                // 立即禁用所有过渡效果,防止闪烁
                document.body.style.transition = 'none';
                document.body.style.animation = 'none';
                document.body.style.transform = 'none';

                const currentMainContent = document.querySelector('.main-content');
                if (currentMainContent) {
                    currentMainContent.style.transition = 'none';
                    currentMainContent.style.animation = 'none';
                    currentMainContent.style.transform = 'none';
                }

                // 禁用侧边栏的动画效果
                const sidebar = document.querySelector('.sidebar');
                if (sidebar) {
                    sidebar.style.transition = 'none';
                    sidebar.style.animation = 'none';
                }

                document.querySelectorAll('.sidebar-link, .sidebar-child-link').forEach(link => {
                    link.style.transition = 'none';
                    link.style.animation = 'none';
                    link.style.transform = 'none';
                });

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
                        // 更新页面标题
                        document.title = doc.title;

                        // 更新主内容区域 - 直接替换
                        currentMainContent.innerHTML = newMainContent.innerHTML;

                        // 更新激活的侧边栏链接
                        document.querySelectorAll('.sidebar-link').forEach(l => l.classList.remove('active'));
                        this.classList.add('active');

                        // 重新初始化主题图标
                        const newThemeIcon = document.getElementById('current-theme-icon');
                        if (newThemeIcon) {
                            const savedTheme = getSavedTheme();
                            newThemeIcon.className = 'fas ' + getThemeIcon(savedTheme);
                        }

                        // 智能加载CSS - 只加载缺失的CSS文件
                        const newStylesheets = doc.querySelectorAll('head link[rel="stylesheet"]');
                        const currentHead = document.querySelector('head');

                        if (newStylesheets.length > 0 && currentHead) {
                            newStylesheets.forEach(sheet => {
                                const sheetHref = sheet.href;
                                const sheetName = sheetHref.split('/').pop();

                                // 查找是否已经存在这个CSS文件
                                const existingSheet = Array.from(currentHead.querySelectorAll('link[rel="stylesheet"]'))
                                    .find(s => s.href.includes(sheetName));

                                if (!existingSheet) {
                                    // 如果不存在,添加它
                                    const newSheet = document.createElement('link');
                                    newSheet.rel = 'stylesheet';
                                    newSheet.href = sheet.href;
                                    currentHead.appendChild(newSheet);
                                }
                            });
                        }

                        // 如果是 dashboard 页面，重新初始化日志筛选功能
                        if (href === '/') {
                            // 更新侧边栏的子菜单链接为 dashboard 版本
                            const newSidebarChildren = doc.querySelector('.sidebar-children');
                            const currentSidebarChildren = document.querySelector('.sidebar-children');
                            if (newSidebarChildren && currentSidebarChildren) {
                                currentSidebarChildren.innerHTML = newSidebarChildren.innerHTML;
                            }

                            // 延迟一点时间确保DOM完全更新
                            setTimeout(function() {
                                // 检查函数是否存在,如果不存在则加载 dashboard.js
                                if (typeof updateStatus === 'function' && typeof updateLogs === 'function') {
                                    if (typeof initLogFilters === 'function') {
                                        initLogFilters();
                                    }
                                    if (typeof updateStatus === 'function') {
                                        updateStatus();
                                    }
                                    if (typeof updateLogs === 'function') {
                                        updateLogs();
                                    }
                                } else {
                                    // 加载 dashboard.js
                                    const script = document.createElement('script');
                                    script.src = '/static/js/dashboard.js';
                                    script.onload = function() {
                                        console.log('dashboard.js loaded, initializing...');
                                        if (typeof initLogFilters === 'function') {
                                            initLogFilters();
                                        }
                                        if (typeof updateStatus === 'function') {
                                            updateStatus();
                                        }
                                        if (typeof updateLogs === 'function') {
                                            updateLogs();
                                        }
                                    };
                                    document.body.appendChild(script);
                                }
                            }, 100);
                        }

                        // 如果是 config 页面，重新初始化配置页面逻辑
                        if (href === '/config') {
                            console.log('Loading config page...');

                            // 先更新侧边栏的子菜单链接
                            const newSidebarChildren = doc.querySelector('.sidebar-children');
                            const currentSidebarChildren = document.querySelector('.sidebar-children');
                            console.log('newSidebarChildren:', newSidebarChildren);
                            console.log('currentSidebarChildren:', currentSidebarChildren);

                            if (newSidebarChildren && currentSidebarChildren) {
                                currentSidebarChildren.innerHTML = newSidebarChildren.innerHTML;
                                console.log('Sidebar children updated');
                            }

                            // 加载 config.js 文件
                            const script = document.createElement('script');
                            script.src = '/static/js/config.js';
                            script.onload = function() {
                                console.log('config.js loaded, calling initConfigPage...');
                                if (typeof initConfigPage === 'function') {
                                    initConfigPage();
                                    console.log('initConfigPage completed');

                                    // 获取第一个子菜单链接的配置项
                                    const firstChildLink = document.querySelector('.sidebar-child-link');
                                    console.log('firstChildLink:', firstChildLink);

                                    if (firstChildLink) {
                                        const firstConfigType = firstChildLink.getAttribute('data-config');
                                        console.log('firstConfigType:', firstConfigType);
                                        // 只有当当前 URL 没有 hash 时才更新,避免覆盖已有的 hash
                                        if (!window.location.hash) {
                                            history.pushState({}, '', href + '#' + firstConfigType);
                                        } else {
                                            // 如果已经有 hash,保留它
                                            history.pushState({}, '', href + window.location.hash);
                                        }
                                    } else {
                                        // 如果没有找到子菜单链接,只更新基础URL
                                        history.pushState({}, '', href);
                                    }
                                } else {
                                    console.error('initConfigPage is still not a function after loading config.js');
                                }
                            };
                            document.body.appendChild(script);
                        } else {
                            // 如果不是 config 页面,清除 hash
                            history.pushState({}, '', href);
                        }

                        // 恢复导航标志
                        isNavigating = false;

                        // 恢复过渡效果
                        setTimeout(() => {
                            document.body.style.transition = '';
                            document.body.style.animation = '';
                            document.body.style.transform = '';

                            const currentMainContent = document.querySelector('.main-content');
                            if (currentMainContent) {
                                currentMainContent.style.transition = '';
                                currentMainContent.style.animation = '';
                                currentMainContent.style.transform = '';
                            }

                            const sidebar = document.querySelector('.sidebar');
                            if (sidebar) {
                                sidebar.style.transition = '';
                                sidebar.style.animation = '';
                            }

                            document.querySelectorAll('.sidebar-link, .sidebar-child-link').forEach(link => {
                                link.style.transition = '';
                                link.style.animation = '';
                                link.style.transform = '';
                            });
                        }, 100);

                        // 如果有待处理的导航,立即执行
                        if (pendingNavigationHref) {
                            const pendingLink = document.querySelector(`.sidebar-link[href="${pendingNavigationHref}"]`);
                            if (pendingLink) {
                                pendingLink.click();
                            }
                        }
                    }
                })
                .catch(error => {
                    console.error('Error loading page:', error);
                    // 恢复导航标志
                    isNavigating = false;

                    // 恢复过渡效果
                    setTimeout(() => {
                        document.body.style.transition = '';
                        document.body.style.animation = '';
                        document.body.style.transform = '';

                        const currentMainContent = document.querySelector('.main-content');
                        if (currentMainContent) {
                            currentMainContent.style.transition = '';
                            currentMainContent.style.animation = '';
                            currentMainContent.style.transform = '';
                        }

                        const sidebar = document.querySelector('.sidebar');
                        if (sidebar) {
                            sidebar.style.transition = '';
                            sidebar.style.animation = '';
                        }

                        document.querySelectorAll('.sidebar-link, .sidebar-child-link').forEach(link => {
                            link.style.transition = '';
                            link.style.animation = '';
                            link.style.transform = '';
                        });
                    }, 100);

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