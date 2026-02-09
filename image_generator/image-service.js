/**
 * 图片生成服务
 * 独立的 Node.js HTTP 服务，通过 API 提供图片生成功能
 */
const express = require('express');
const puppeteer = require('puppeteer');
const fs = require('fs');
const path = require('path');

const app = express();
const PORT = process.env.PORT || 3001;

// 中间件
app.use(express.json({ limit: '10mb' }));

// 浏览器实例（单例模式，避免重复启动）
let browserInstance = null;

/**
 * 获取浏览器实例
 */
async function getBrowser() {
  if (!browserInstance) {
    browserInstance = await puppeteer.launch({
      headless: 'new',
      executablePath: 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
      args: ['--no-sandbox', '--disable-setuid-sandbox']
    });
  }
  return browserInstance;
}

/**
 * 读取 CSS 文件内容
 */
function readCSS(filename) {
  const cssPath = path.join(__dirname, filename);
  return fs.readFileSync(cssPath, 'utf-8');
}

/**
 * 生成 HTML 内容
 */
function generateHTML(type, data) {
  const timestamp = new Date().toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit'
  });

  if (type === 'status') {
    return generateStatusHTML(data, timestamp);
  } else if (type === 'help') {
    return generateHelpHTML(timestamp);
  }
  return '';
}

/**
 * 生成状态页面 HTML
 */
function generateStatusHTML(data, timestamp) {
  const {
    llbot = {},
    yunzai = {},
    redis = {},
    http = {},
    autoRestart = {}
  } = data;

  const getStatusItem = (label, running, pid) => `
    <div class="status-item ${running ? 'running' : 'stopped'}">
      <div class="status-indicator">
        <span class="icon">${running ? '✓' : '✗'}</span>
      </div>
      <div class="status-info">
        <div class="service-name">${label}</div>
        <div class="service-status">${running ? '运行中' : '已停止'}</div>
      </div>
      ${pid ? `<div class="service-pid">PID: ${pid}</div>` : ''}
    </div>
  `;

  const statusItems = [
    getStatusItem('llbot', llbot.running, llbot.pid),
    getStatusItem('Yunzai', yunzai.running, yunzai.pid),
    getStatusItem('Redis', redis.running, redis.pid),
    getStatusItem('HTTP服务', http.accessible, null),
    getStatusItem('自动重启', autoRestart.enabled === true, null)
  ].join('');

  const commonCSS = readCSS('common.css');
  const statusCSS = readCSS('status.css');

  return `
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <style>
    ${commonCSS}
    ${statusCSS}
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <div class="title">📊 监控系统状态</div>
    </div>
    <div class="status-list">
      ${statusItems}
    </div>
    <div class="footer">
      更新时间: ${timestamp}
    </div>
  </div>
</body>
</html>
  `;
}

/**
 * 生成帮助页面 HTML
 */
function generateHelpHTML(timestamp) {
  const commonCSS = readCSS('common.css');
  const helpCSS = readCSS('help.css');

  return `
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <style>
    ${commonCSS}
    ${helpCSS}
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <div class="title">📖 指令帮助</div>
      <div class="subtitle">llbot & Yunzai 监控系统</div>
    </div>
    
    <div class="section">
      <div class="section-title">📊 状态查询</div>
      <div class="command-list">
        <div class="command-item">
          <div class="command">/st /status</div>
          <div class="description">查看所有服务状态</div>
        </div>
      </div>
    </div>
    
    <div class="section">
      <div class="section-title">🔧 服务控制</div>
      <div class="command-list">
        <div class="command-item">
          <div class="command">/s /start [服务]</div>
          <div class="description">启动服务 (llbot|yunzai|redis|all)</div>
        </div>
        <div class="command-item">
          <div class="command">/t /stop [服务]</div>
          <div class="description">停止服务 (llbot|yunzai|redis|all)</div>
        </div>
        <div class="command-item">
          <div class="command">/r /restart [服务]</div>
          <div class="description">重启服务 (llbot|yunzai|redis|all)</div>
        </div>
      </div>
    </div>
    
    <div class="section">
      <div class="section-title">🔄 更新管理</div>
      <div class="command-list">
        <div class="command-item">
          <div class="command">/cu /check_update</div>
          <div class="description">检查更新 (frontend|git|all)</div>
        </div>
        <div class="command-item">
          <div class="command">/up /update [类型]</div>
          <div class="description">执行更新 (frontend|git)</div>
        </div>
      </div>
    </div>
    
    <div class="footer">
      生成时间: ${timestamp}
    </div>
  </div>
</body>
</html>
  `;
}

/**
 * API: 生成状态图片
 */
app.post('/api/generate-status', async (req, res) => {
  const startTime = Date.now();
  
  try {
    const data = req.body || {};
    const browser = await getBrowser();
    const page = await browser.newPage();

    const html = generateHTML('status', data);
    
    await page.setViewport({ width: 700, height: 700 });
    await page.setContent(html, { waitUntil: 'networkidle0' });

    const screenshot = await page.screenshot({
      type: 'png',
      encoding: 'base64'
    });

    await page.close();

    const duration = Date.now() - startTime;
    console.log(`[INFO] 状态图片生成成功，耗时: ${duration}ms`);

    res.json({
      success: true,
      data: screenshot,
      duration: duration
    });

  } catch (error) {
    console.error('[ERROR] 生成状态图片失败:', error.message);
    res.status(500).json({
      success: false,
      error: error.message
    });
  }
});

/**
 * API: 生成帮助图片
 */
app.post('/api/generate-help', async (req, res) => {
  const startTime = Date.now();
  
  try {
    const browser = await getBrowser();
    const page = await browser.newPage();

    const html = generateHTML('help', {});
    
    await page.setViewport({ width: 700, height: 900 });
    await page.setContent(html, { waitUntil: 'networkidle0' });

    const screenshot = await page.screenshot({
      type: 'png',
      encoding: 'base64'
    });

    await page.close();

    const duration = Date.now() - startTime;
    console.log(`[INFO] 帮助图片生成成功，耗时: ${duration}ms`);

    res.json({
      success: true,
      data: screenshot,
      duration: duration
    });

  } catch (error) {
    console.error('[ERROR] 生成帮助图片失败:', error.message);
    res.status(500).json({
      success: false,
      error: error.message
    });
  }
});

/**
 * 健康检查
 */
app.get('/health', (req, res) => {
  res.json({
    status: 'ok',
    service: 'image-generator',
    version: '2.0.0'
  });
});

/**
 * 优雅关闭
 */
async function gracefulShutdown() {
  console.log('[INFO] 正在关闭服务...');
  
  if (browserInstance) {
    await browserInstance.close();
    console.log('[INFO] 浏览器已关闭');
  }
  
  process.exit(0);
}

process.on('SIGINT', gracefulShutdown);
process.on('SIGTERM', gracefulShutdown);

// 启动服务
app.listen(PORT, () => {
  console.log(`[INFO] 图片生成服务已启动`);
  console.log(`[INFO] 监听地址: http://localhost:${PORT}`);
  console.log(`[INFO] API 端点:`);
  console.log(`  - POST /api/generate-status`);
  console.log(`  - POST /api/generate-help`);
  console.log(`  - GET  /health`);
});