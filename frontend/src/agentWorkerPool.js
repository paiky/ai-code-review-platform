const workerStates = new Set(['IDLE', 'BUSY', 'DRAINING']);

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
    totalCount: nodes.length
  };
  const hasRegisteredPool = source
    && (safeCount(source.totalCount, 0) > 0 || (source.nodes || []).length > 0);
  const counts = hasRegisteredPool
    ? Object.fromEntries(
        Object.keys(fallbackCounts).map(key => [key, safeCount(source[key], fallbackCounts[key])])
      )
    : fallbackCounts;
  return {
    status: counts.onlineCount > 0 ? 'ONLINE' : 'OFFLINE',
    ...counts,
    nodes
  };
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
  if (!node || node.state !== 'BUSY') return '-';
  const parts = [];
  if (node.activeJobId) parts.push(`Job #${node.activeJobId}`);
  if (node.activeRunId) parts.push(`Run #${node.activeRunId}`);
  return parts.join(' / ') || '配置测试或任务启动中';
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

function safeText(value, maximum) {
  const text = String(value || '').trim();
  return text ? text.slice(0, maximum) : null;
}
