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
    await page.setViewport({ width: 650, height: type === 'help' ? 600 : 500 });

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
      font-family: 'Microsoft YaHei', 'PingFang SC', sans-serif;
      background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
      color: #fff;
      padding: 20px;
      width: 650px;
    }
    .container {
      background: rgba(255, 255, 255, 0.05);
      border-radius: 12px;
      padding: 20px;
      backdrop-filter: blur(10px);
      border: 1px solid rgba(255, 255, 255, 0.1);
    }
    .header {
      text-align: center;
      margin-bottom: 20px;
      padding-bottom: 15px;
      border-bottom: 2px solid rgba(15, 52, 96, 0.5);
    }
    .title {
      font-size: 28px;
      font-weight: bold;
      color: #e94560;
      text-shadow: 0 0 10px rgba(233, 69, 96, 0.3);
    }
    .status-list {
      display: flex;
      flex-direction: column;
      gap: 10px;
    }
    .status-item {
      display: flex;
      align-items: center;
      gap: 15px;
      padding: 12px 15px;
      background: rgba(255, 255, 255, 0.05);
      border-radius: 8px;
      border-left: 4px solid;
      transition: all 0.3s ease;
    }
    .status-item.running {
      border-left-color: #00b894;
      background: rgba(0, 184, 148, 0.1);
    }
    .status-item.stopped {
      border-left-color: #d63031;
      background: rgba(214, 48, 49, 0.1);
    }
    .status-indicator {
      width: 40px;
      height: 40px;
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 20px;
      font-weight: bold;
    }
    .status-item.running .status-indicator {
      background: #00b894;
      box-shadow: 0 0 10px rgba(0, 184, 148, 0.5);
    }
    .status-item.stopped .status-indicator {
      background: #d63031;
      box-shadow: 0 0 10px rgba(214, 48, 49, 0.5);
    }
    .status-info {
      flex: 1;
    }
    .service-name {
      font-size: 18px;
      font-weight: 600;
      color: #dfe6e9;
    }
    .service-status {
      font-size: 14px;
      opacity: 0.8;
    }
    .service-pid {
      font-size: 13px;
      color: #636e72;
      background: rgba(0, 0, 0, 0.2);
      padding: 4px 10px;
      border-radius: 4px;
    }
    .footer {
      text-align: center;
      margin-top: 20px;
      padding-top: 15px;
      border-top: 1px solid rgba(15, 52, 96, 0.5);
      font-size: 12px;
      color: #636e72;
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
      font-family: 'Microsoft YaHei', 'PingFang SC', sans-serif;
      background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
      color: #fff;
      padding: 20px;
      width: 650px;
    }
    .container {
      background: rgba(255, 255, 255, 0.05);
      border-radius: 12px;
      padding: 25px;
      backdrop-filter: blur(10px);
      border: 1px solid rgba(255, 255, 255, 0.1);
    }
    .header {
      text-align: center;
      margin-bottom: 25px;
      padding-bottom: 15px;
      border-bottom: 2px solid rgba(233, 69, 96, 0.5);
    }
    .title {
      font-size: 28px;
      font-weight: bold;
      color: #e94560;
      text-shadow: 0 0 10px rgba(233, 69, 96, 0.3);
    }
    .subtitle {
      font-size: 14px;
      color: #636e72;
      margin-top: 8px;
    }
    .section {
      margin-bottom: 20px;
    }
    .section-title {
      font-size: 16px;
      font-weight: 600;
      color: #74b9ff;
      margin-bottom: 10px;
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .command-list {
      display: flex;
      flex-direction: column;
      gap: 8px;
    }
    .command-item {
      background: rgba(255, 255, 255, 0.05);
      padding: 12px 15px;
      border-radius: 8px;
      border-left: 3px solid #74b9ff;
    }
    .command {
      font-family: 'Consolas', 'Monaco', monospace;
      font-size: 14px;
      color: #00cec9;
      margin-bottom: 4px;
    }
    .description {
      font-size: 13px;
      color: #b2bec3;
    }
    .footer {
      text-align: center;
      margin-top: 20px;
      padding-top: 15px;
      border-top: 1px solid rgba(15, 52, 96, 0.5);
      font-size: 12px;
      color: #636e72;
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