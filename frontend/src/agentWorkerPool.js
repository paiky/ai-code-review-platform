const workerStates = new Set(['IDLE', 'BUSY', 'DRAINING']);
export const AGENT_QUEUE_BACKLOG_COUNT_WARNING = 3;
export const AGENT_QUEUE_OLDEST_WARNING_SECONDS = 120;

export function normalizeAgentWorkerPool(settings) {
  const source = settings?.workerPool && typeof settings.workerPool === 'object'
    ? settings.workerPool
    : null;
  const nodes = Array.isArray(source?.nodes)
    ? source.nodes.map(normalizeWorkerNode).filter(Boolean)
    : [];
  if (nodes.length === 0 && settings?.workerId) {
    const online = settings?.workerStatus === 'ONLINE';
    nodes.push({
      workerId: String(settings.workerId).slice(0, 128),
      workerVersion: safeText(settings.workerVersion, 64),
      cliVersion: safeText(settings.cliVersion, 64),
      state: 'IDLE',
      capacity: 1,
      activeJobId: null,
      activeRunId: null,
      startedAt: null,
      lastHeartbeatAt: settings.lastWorkerHeartbeatAt || null,
      online,
      legacy: true
    });
  }
  const onlineNodes = nodes.filter(node => node.online);
  const fallbackCounts = {
    onlineCount: onlineNodes.length,
    busyCount: onlineNodes.filter(node => node.state === 'BUSY').length,
    idleCount: onlineNodes.filter(node => node.state === 'IDLE').length,
    drainingCount: onlineNodes.filter(node => node.state === 'DRAINING').length,
    totalCapacity: onlineNodes.reduce((total, node) => total + node.capacity, 0),
    onlineCapacity: onlineNodes
      .filter(node => node.state !== 'DRAINING')
      .reduce((total, node) => total + node.capacity, 0),
    busyCapacity: onlineNodes
      .filter(node => node.state === 'BUSY')
      .reduce((total, node) => total + node.capacity, 0),
    totalCount: nodes.length
  };
  const hasRegisteredPool = source
    && (safeCount(source.totalCount, 0) > 0 || (source.nodes || []).length > 0);
  const counts = hasRegisteredPool
    ? Object.fromEntries(
        Object.keys(fallbackCounts).map(key => [key, safeCount(source[key], fallbackCounts[key])])
      )
    : fallbackCounts;
  counts.busyCapacity = Math.min(counts.busyCapacity, counts.onlineCapacity);
  const utilizationPercent = safePercent(
    source?.utilizationPercent,
    calculateUtilization(counts.busyCapacity, counts.onlineCapacity)
  );
  return {
    status: counts.onlineCount > 0 ? 'ONLINE' : 'OFFLINE',
    ...counts,
    utilizationPercent,
    lastHeartbeatAt: safeText(source?.lastHeartbeatAt, 64)
      || nodes.find(node => node.lastHeartbeatAt)?.lastHeartbeatAt
      || safeText(settings?.lastWorkerHeartbeatAt, 64),
    nodes
  };
}

export function normalizeAgentQueueMetrics(settings, normalizedPool = null) {
  const pool = normalizedPool || normalizeAgentWorkerPool(settings);
  const source = settings?.queueMetrics && typeof settings.queueMetrics === 'object'
    ? settings.queueMetrics
    : null;
  const onlineCapacity = safeCount(source?.onlineCapacity, pool.onlineCapacity);
  const busyCapacity = Math.min(
    safeCount(source?.busyCapacity, pool.busyCapacity),
    onlineCapacity
  );
  return {
    queued: safeCount(source?.queued, 0),
    running: safeCount(source?.running, 0),
    expiredLease: safeCount(source?.expiredLease, 0),
    oldestQueuedSeconds: safeCount(source?.oldestQueuedSeconds, 0),
    onlineCapacity,
    busyCapacity,
    utilizationPercent: safePercent(
      source?.utilizationPercent,
      calculateUtilization(busyCapacity, onlineCapacity)
    ),
    drainingWorkers: safeCount(source?.drainingWorkers, pool.drainingCount),
    lastWorkerHeartbeatAt: safeText(source?.lastWorkerHeartbeatAt, 64)
      || pool.lastHeartbeatAt
      || null
  };
}

export function formatAgentQueueSummary(metrics) {
  const value = metrics && typeof metrics === 'object' ? metrics : {};
  return [
    `排队 ${safeCount(value.queued, 0)}`,
    `运行 ${safeCount(value.running, 0)}`,
    `过期租约 ${safeCount(value.expiredLease, 0)}`,
    `最老等待 ${formatQueueAge(value.oldestQueuedSeconds)}`
  ].join(' · ');
}

export function formatQueueAge(value) {
  const seconds = safeCount(value, 0);
  if (seconds === 0) return '暂无';
  if (seconds < 60) return `${seconds} 秒`;
  if (seconds < 3600) {
    const minutes = Math.floor(seconds / 60);
    const remainder = seconds % 60;
    return remainder ? `${minutes} 分 ${remainder} 秒` : `${minutes} 分`;
  }
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  return minutes ? `${hours} 小时 ${minutes} 分` : `${hours} 小时`;
}

export function buildAgentQueueAlerts(settings) {
  const pool = normalizeAgentWorkerPool(settings);
  const metrics = normalizeAgentQueueMetrics(settings, pool);
  const alerts = [];
  if (pool.onlineCount === 0) {
    alerts.push({
      key: 'offline',
      type: 'error',
      message: 'Agent Worker Pool 离线',
      description: '当前没有 60 秒心跳窗口内的 Worker；排队任务可能在既有离线宽限后进入 Standard fallback。'
    });
  }
  if (metrics.drainingWorkers > 0) {
    alerts.push({
      key: 'draining',
      type: 'warning',
      message: `${metrics.drainingWorkers} 个 Worker 正在排空`,
      description: '排空节点不会领取新任务。缩容前请确认其当前任务已完成，并先补足其余在线容量。'
    });
  }
  if (metrics.expiredLease > 0) {
    alerts.push({
      key: 'expired-lease',
      type: 'warning',
      message: `${metrics.expiredLease} 个运行任务租约已过期`,
      description: '任务正在等待现有租约接管与 claimAttempt fencing，详情页只展示脱敏接管事件。'
    });
  }
  if (
    metrics.queued > 0
    && metrics.onlineCapacity > 0
    && metrics.busyCapacity >= metrics.onlineCapacity
  ) {
    alerts.push({
      key: 'saturated',
      type: 'info',
      message: '全部在线容量正在忙碌',
      description: '新 Agent 任务会继续排队，不会仅因 Worker 忙碌触发 Standard fallback。'
    });
  }
  if (
    metrics.queued >= AGENT_QUEUE_BACKLOG_COUNT_WARNING
    || metrics.oldestQueuedSeconds >= AGENT_QUEUE_OLDEST_WARNING_SECONDS
  ) {
    alerts.push({
      key: 'backlog',
      type: 'warning',
      message: 'Agent 队列出现积压',
      description: '请检查 Worker 状态；需要扩容时使用 docker compose up -d --scale agent-worker=N。'
    });
  }
  return alerts;
}

export function workerStateLabel(state) {
  return {
    IDLE: '空闲',
    BUSY: '忙碌',
    DRAINING: '排空中'
  }[state] || '未知';
}

export function workerStateColor(state, online = true) {
  if (!online) return 'default';
  return {
    IDLE: 'green',
    BUSY: 'blue',
    DRAINING: 'orange'
  }[state] || 'default';
}

export function formatWorkerActivity(node) {
  if (!node || !['BUSY', 'DRAINING'].includes(node.state)) return '-';
  const parts = [];
  if (node.activeJobId) parts.push(`Job #${node.activeJobId}`);
  if (node.activeRunId) parts.push(`Run #${node.activeRunId}`);
  if (parts.length > 0) return parts.join(' / ');
  return node.state === 'DRAINING' ? '排空中' : '配置测试或任务启动中';
}

function normalizeWorkerNode(value) {
  if (!value || typeof value !== 'object') return null;
  const workerId = safeText(value.workerId, 128);
  if (!workerId) return null;
  const state = workerStates.has(value.state) ? value.state : 'IDLE';
  return {
    workerId,
    workerVersion: safeText(value.workerVersion, 64),
    cliVersion: safeText(value.cliVersion, 64),
    state,
    capacity: value.capacity === 1 ? 1 : 0,
    activeJobId: safePositiveInteger(value.activeJobId),
    activeRunId: safePositiveInteger(value.activeRunId),
    capabilities: Array.from(new Set(
      (Array.isArray(value.capabilities) ? value.capabilities : [])
        .map(item => safeText(item, 64))
        .filter(Boolean)
    )),
    startedAt: safeText(value.startedAt, 64),
    lastHeartbeatAt: safeText(value.lastHeartbeatAt, 64),
    online: value.online === true,
    legacy: false
  };
}

function safePositiveInteger(value) {
  const number = Number(value);
  return Number.isSafeInteger(number) && number > 0 ? number : null;
}

function safeCount(value, fallback) {
  const number = Number(value);
  return Number.isSafeInteger(number) && number >= 0 ? number : fallback;
}

function safePercent(value, fallback) {
  const number = Number(value);
  if (!Number.isFinite(number) || number < 0) return fallback;
  return Math.min(Math.round(number), 100);
}

function calculateUtilization(busyCapacity, onlineCapacity) {
  if (onlineCapacity <= 0) return 0;
  return Math.min(Math.round((busyCapacity / onlineCapacity) * 100), 100);
}

function safeText(value, maximum) {
  const text = String(value || '').trim();
  return text ? text.slice(0, maximum) : null;
}
