/**
 * Puppeteer 图片生成器
 * 用于生成状态图片和帮助图片
 */
const puppeteer = require('puppeteer');

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

  return `
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <style>
    * {
      margin: 0;
      padding: 0;
      box-sizing: border-box;
    }
    body {
      font-family: 'Microsoft YaHei', 'PingFang SC', -apple-system, BlinkMacSystemFont, sans-serif;
      background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
      color: #fff;
      padding: 25px;
      width: 650px;
    }
    .container {
      background: rgba(255, 255, 255, 0.1);
      border-radius: 20px;
      padding: 30px;
      backdrop-filter: blur(20px);
      border: 1px solid rgba(255, 255, 255, 0.2);
      box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
    }
    .header {
      text-align: center;
      margin-bottom: 30px;
      padding-bottom: 20px;
      border-bottom: 2px solid rgba(255, 255, 255, 0.15);
    }
    .title {
      font-size: 32px;
      font-weight: 700;
      background: linear-gradient(135deg, #fff 0%, #e0e0e0 100%);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      background-clip: text;
      text-shadow: 0 2px 4px rgba(0, 0, 0, 0.2);
      margin-bottom: 8px;
    }
    .status-list {
      display: flex;
      flex-direction: column;
      gap: 12px;
    }
    .status-item {
      display: flex;
      align-items: center;
      gap: 16px;
      padding: 16px 18px;
      background: rgba(255, 255, 255, 0.08);
      border-radius: 12px;
      border-left: 5px solid;
      transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
      backdrop-filter: blur(5px);
    }
    .status-item.running {
      border-left-color: #10b981;
      background: linear-gradient(135deg, rgba(16, 185, 129, 0.2) 0%, rgba(16, 185, 129, 0.1) 100%);
      box-shadow: 0 4px 15px rgba(16, 185, 129, 0.3);
    }
    .status-item.stopped {
      border-left-color: #ef4444;
      background: linear-gradient(135deg, rgba(239, 68, 68, 0.2) 0%, rgba(239, 68, 68, 0.1) 100%);
      box-shadow: 0 4px 15px rgba(239, 68, 68, 0.3);
    }
    .status-indicator {
      width: 48px;
      height: 48px;
      border-radius: 12px;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 24px;
      font-weight: bold;
      flex-shrink: 0;
    }
    .status-item.running .status-indicator {
      background: linear-gradient(135deg, #10b981 0%, #059669 100%);
      box-shadow: 0 4px 12px rgba(16, 185, 129, 0.5);
    }
    .status-item.stopped .status-indicator {
      background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%);
      box-shadow: 0 4px 12px rgba(239, 68, 68, 0.5);
    }
    .status-info {
      flex: 1;
    }
    .service-name {
      font-size: 18px;
      font-weight: 600;
      color: #fff;
      letter-spacing: 0.5px;
    }
    .service-status {
      font-size: 13px;
      color: rgba(255, 255, 255, 0.75);
      margin-top: 4px;
    }
    .service-pid {
      font-size: 12px;
      color: rgba(255, 255, 255, 0.6);
      background: rgba(0, 0, 0, 0.25);
      padding: 6px 12px;
      border-radius: 6px;
      font-weight: 500;
    }
    .footer {
      text-align: center;
      margin-top: 25px;
      padding-top: 20px;
      border-top: 1px solid rgba(255, 255, 255, 0.1);
      font-size: 12px;
      color: rgba(255, 255, 255, 0.6);
      font-weight: 500;
    }
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <div class="title">📊 监控系统状态</div>
    </div>
    <div class="status-list">
      ${getStatusItem('llbot', llbot.running, llbot.pid)}
      ${getStatusItem('Yunzai', yunzai.running, yunzai.pid)}
      ${getStatusItem('Redis', redis.running, redis.pid)}
      ${getStatusItem('HTTP服务', http.accessible, null)}
      ${getStatusItem('自动重启', autoRestart.enabled === true, null)}
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
  return `
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <style>
    * {
      margin: 0;
      padding: 0;
      box-sizing: border-box;
    }
    body {
      font-family: 'Microsoft YaHei', 'PingFang SC', -apple-system, BlinkMacSystemFont, sans-serif;
      background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
      color: #fff;
      padding: 25px;
      width: 650px;
    }
    .container {
      background: rgba(255, 255, 255, 0.1);
      border-radius: 20px;
      padding: 30px;
      backdrop-filter: blur(20px);
      border: 1px solid rgba(255, 255, 255, 0.2);
      box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
    }
    .header {
      text-align: center;
      margin-bottom: 30px;
      padding-bottom: 20px;
      border-bottom: 2px solid rgba(255, 255, 255, 0.15);
    }
    .title {
      font-size: 32px;
      font-weight: 700;
      background: linear-gradient(135deg, #fff 0%, #e0e0e0 100%);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      background-clip: text;
      text-shadow: 0 2px 4px rgba(0, 0, 0, 0.2);
      margin-bottom: 8px;
    }
    .subtitle {
      font-size: 14px;
      color: rgba(255, 255, 255, 0.7);
      font-weight: 500;
      letter-spacing: 1px;
    }
    .section {
      margin-bottom: 24px;
    }
    .section:last-child {
      margin-bottom: 0;
    }
    .section-title {
      font-size: 18px;
      font-weight: 600;
      color: #fff;
      margin-bottom: 12px;
      display: flex;
      align-items: center;
      gap: 10px;
      padding-bottom: 8px;
      border-bottom: 1px solid rgba(255, 255, 255, 0.1);
    }
    .command-list {
      display: flex;
      flex-direction: column;
      gap: 10px;
    }
    .command-item {
      background: rgba(255, 255, 255, 0.08);
      padding: 14px 18px;
      border-radius: 10px;
      border-left: 4px solid;
      transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
      backdrop-filter: blur(5px);
    }
    .command-item:nth-child(1) {
      border-left-color: #60a5fa;
      box-shadow: 0 4px 12px rgba(96, 165, 250, 0.2);
    }
    .command-item:nth-child(2) {
      border-left-color: #34d399;
      box-shadow: 0 4px 12px rgba(52, 211, 153, 0.2);
    }
    .command-item:nth-child(3) {
      border-left-color: #fbbf24;
      box-shadow: 0 4px 12px rgba(251, 191, 36, 0.2);
    }
    .command {
      font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
      font-size: 14px;
      color: #a5f3fc;
      margin-bottom: 6px;
      font-weight: 600;
      letter-spacing: 0.3px;
    }
    .description {
      font-size: 13px;
      color: rgba(255, 255, 255, 0.7);
      font-weight: 400;
      line-height: 1.5;
    }
    .footer {
      text-align: center;
      margin-top: 25px;
      padding-top: 20px;
      border-top: 1px solid rgba(255, 255, 255, 0.1);
      font-size: 12px;
      color: rgba(255, 255, 255, 0.6);
      font-weight: 500;
    }
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