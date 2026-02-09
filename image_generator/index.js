/**
 * Puppeteer 图片生成器
 * 用于生成状态图片和帮助图片
 */
const puppeteer = require('puppeteer');
const fs = require('fs');
const path = require('path');

/**
 * 生成图片
 * @param {string} type - 图片类型 (status|help)
 * @param {Object} data - 数据对象
 * @returns {Promise<string>} Base64 编码的图片数据
 */
async function generateImage(type, data = {}) {
  let browser;
  try {
    // 启动浏览器（使用系统已安装的 Microsoft Edge）
    browser = await puppeteer.launch({
      headless: 'new',
      executablePath: 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
      args: ['--no-sandbox', '--disable-setuid-sandbox']
    });

    const page = await browser.newPage();

    // 根据类型生成不同的 HTML
    const html = generateHTML(type, data);

    // 设置视口
    await page.setViewport({ width: 700, height: type === 'help' ? 900 : 700 });

    // 设置页面内容
    await page.setContent(html, { waitUntil: 'networkidle0' });

    // 截图
    const screenshot = await page.screenshot({
      type: 'png',
      encoding: 'base64'
    });

    return screenshot;
  } catch (error) {
    console.error('生成图片失败:', error.message);
    throw error;
  } finally {
    if (browser) {
      await browser.close();
    }
  }
}

/**
 * 生成 HTML 内容
 * @param {string} type - 图片类型
 * @param {Object} data - 数据对象
 * @returns {string} HTML 字符串
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
 * 读取 CSS 文件内容
 * @param {string} filename - CSS 文件名
 * @returns {string} CSS 内容
 */
function readCSS(filename) {
  const cssPath = path.join(__dirname, filename);
  return fs.readFileSync(cssPath, 'utf-8');
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

// 命令行调用接口
if (require.main === module) {
  const args = process.argv.slice(2);
  if (args.length < 1) {
    console.error('Usage: node index.js <type> [data_json]');
    console.error('  type: status | help');
    console.error('  data_json: JSON string with data (for status type)');
    process.exit(1);
  }

  const type = args[0];
  const data = args.length > 1 ? JSON.parse(args[1]) : {};

  generateImage(type, data)
    .then(base64 => {
      console.log(base64);
    })
    .catch(error => {
      console.error(error.message);
      process.exit(1);
    });
}

module.exports = { generateImage };