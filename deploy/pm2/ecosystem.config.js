// =============================================================================
// TradeDojo pm2 配置
// 启动: pm2 start deploy/pm2/ecosystem.config.js
// 重启: pm2 restart tradedojo
// 开机自启: pm2 startup + pm2 save
// =============================================================================
module.exports = {
  apps: [{
    name: 'tradedojo',
    // ---- 进程定位 ----
    cwd: '/opt/tradedojo/backend',
    script: '/root/.local/bin/uv',
    args: 'run main.py',
    // interpreter 留空(script 直接当解释器;arg 为 uv run main.py)
    interpreter: 'none',

    // ---- 实例 ----
    instances: 1,           // uvicorn 自己多 worker,这里 1 个进程足够
    exec_mode: 'fork',      // 单实例 fork 模式;若要 cluster 改 cluster

    // ---- 资源限制 ----
    max_memory_restart: '800M',
    max_restarts: 10,
    restart_delay: 5000,
    min_uptime: '30s',

    // ---- 环境注入 ----
    // 直接从 .env 读 key=value,赋给 process.env
    // pm2 不支持 EnvironmentFile,所以手动把 .env 拍平注入
    env: {
      PYTHONUNBUFFERED: '1',
      PYTHONIOENCODING: 'utf-8',
      // 下面这些由脚本自动从 /opt/tradedojo/.env 注入,这里只是样例
    },
    // pm2 --env 可以指定不同组,这里用 default

    // ---- 日志(走 pm2 自带轮转) ----
    out_file: '/opt/tradedojo/backend/logs/pm2-out.log',
    error_file: '/opt/tradedojo/backend/logs/pm2-error.log',
    merge_logs: true,
    log_date_format: 'YYYY-MM-DD HH:mm:ss Z',
    log_rotation: {
      max_size: '20M',
      compress: true,
      dateFormat: 'YYYY-MM-DD',
      maxFiles: 14,
    },

    // ---- 监控 ----
    listen_timeout: 60000,
    kill_timeout: 5000,
    shutdown_with_message: true,

    // ---- 部署钩子(可选) ----
    // pre_start: 'echo "[pm2] starting tradedojo"',
    // post_start: 'echo "[pm2] started"',
  }],
};
