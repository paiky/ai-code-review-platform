import http from 'node:http';

const host = '127.0.0.1';
const port = parsePort(process.argv);
let scenario = parseScenario(process.argv);
let agentTestPollCount = 0;

const defaultBudgets = {
  maxTurns: 12,
  maxToolCalls: 40,
  maxSourceBytes: 200000,
  timeoutSeconds: 600,
  inlineDiffBytes: 200000,
  maxEvidenceCalls: 10,
  convergeAtCalls: 8,
  submitByTurn: 9
};

let settings = {
  reviewEnabled: true,
  dingtalkNotificationEnabled: true,
  autoFixPreviewEnabled: false,
  autoFixPreviewSeverities: ['CRITICAL', 'MAJOR'],
  defaultProviderCode: 'DEEPSEEK'
};

let agentSettings = {
  enabled: true,
  selectedRuntime: 'CLAUDE_CODE_DEEPSEEK',
  runtimeOptions: [
    { value: 'CLAUDE_CODE_DEEPSEEK', label: 'Claude Code + DeepSeek', isDefault: true },
    { value: 'OPENAI_RESPONSES_CUSTOM', label: '自定义 OpenAI Responses Agent', isDefault: false }
  ],
  defaultRuntime: {
    runtimeType: 'CLAUDE_CODE_DEEPSEEK',
    provider: 'DEEPSEEK',
    endpoint: 'https://safe-mock.invalid/agent',
    model: 'deepseek-v4-pro[1m]',
    apiKeyConfigured: true,
    apiKeyMasked: 'mock...only'
  },
  customRuntime: {
    runtimeType: 'OPENAI_RESPONSES_CUSTOM',
    protocol: 'OPENAI_RESPONSES',
    displayName: 'Safe Mock Relay',
    baseUrl: 'https://safe-mock.invalid/v1',
    model: 'gpt-5.6-sol',
    reasoningEffort: 'high',
    tlsVerify: true,
    reasoningEffortOptions: ['low', 'medium', 'high'],
    apiKeyConfigured: true,
    apiKeyMasked: 'mock...only',
    egressAllowed: true,
    urlSafetyValidated: true,
    configurationComplete: true,
    workerSupported: true
  },
  encryptionAvailable: true,
  workerStatus: 'ONLINE',
  workerPool: {
    onlineCount: 1,
    busyCount: 0,
    idleCount: 1,
    drainingCount: 0,
    totalCapacity: 1,
    onlineCapacity: 1,
    busyCapacity: 0,
    totalCount: 1,
    nodes: []
  },
  queueMetrics: {
    queued: 0,
    running: 0,
    expiredLease: 0,
    oldestQueuedSeconds: 0,
    onlineCapacity: 1,
    busyCapacity: 0,
    utilizationPercent: 0,
    drainingWorkers: 0
  },
  configurationTest: { status: 'NOT_RUN' },
  budgets: { ...defaultBudgets, maxDiffBytes: 500000 },
  budgetDefaults: defaultBudgets,
  budgetLimits: Object.fromEntries(Object.entries(defaultBudgets).map(([key, value]) => [
    key,
    { min: Math.max(1, Math.floor(value / 4)), max: value * 4 }
  ])),
  budgetConfigSource: 'DEFAULT',
  updatedAt: '2026-08-08T08:00:00Z'
};

let providers = [
  provider('DEEPSEEK', 'DeepSeek V4 Pro', 'OPENAI_CHAT_COMPATIBLE', 'deepseek-v4-pro', true, true),
  provider('OPENAI', 'OpenAI', 'OPENAI_CHAT_COMPATIBLE', 'gpt-5.6-sol', true, false),
  provider('ANTHROPIC', 'Claude Sonnet', 'ANTHROPIC_MESSAGES', 'claude-sonnet', false, false)
];

if (scenario === 'AGENT_INCOMPLETE') {
  agentSettings = {
    ...agentSettings,
    selectedRuntime: 'OPENAI_RESPONSES_CUSTOM',
    customRuntime: {
      ...agentSettings.customRuntime,
      apiKeyConfigured: false,
      apiKeyMasked: null,
      configurationComplete: false,
      workerSupported: false
    }
  };
}

const server = http.createServer(async (request, reply) => {
  const url = new URL(request.url, `http://${host}:${port}`);
  reply.setHeader('Content-Type', 'application/json; charset=utf-8');
  reply.setHeader('Cache-Control', 'no-store');

  if (url.pathname === '/api/__docs54__/health') {
    send(reply, 200, { service: 'docs54-settings-safe-mock', scenario });
    return;
  }
  if (request.method === 'POST' && url.pathname === '/api/__docs54__/scenario') {
    setScenario((await readJson(request)).scenario);
    send(reply, 200, { service: 'docs54-settings-safe-mock', scenario });
    return;
  }
  if (request.method === 'GET' && url.pathname === '/api/code-quality-reviews/settings') {
    if (scenario === 'SETTINGS_READ_FAILED') {
      sendError(reply, 503, 'Synthetic Settings read failure');
      return;
    }
    send(reply, 200, settings);
    return;
  }
  if (request.method === 'PUT' && url.pathname === '/api/code-quality-reviews/settings') {
    if (scenario === 'MUTATION_FAILED') {
      sendError(reply, 503, 'Synthetic Settings save failure');
      return;
    }
    settings = { ...settings, ...(await readJson(request)) };
    send(reply, 200, settings);
    return;
  }
  if (request.method === 'GET' && url.pathname === '/api/code-quality-reviews/agent-settings') {
    if (scenario === 'AGENT_READ_FAILED') {
      sendError(reply, 503, 'Synthetic Agent Settings read failure');
      return;
    }
    advanceAgentTestScenario();
    send(reply, 200, agentSettings);
    return;
  }
  if (request.method === 'PUT' && url.pathname === '/api/code-quality-reviews/agent-settings') {
    if (scenario === 'MUTATION_FAILED') {
      sendError(reply, 503, 'Synthetic Agent Settings save failure');
      return;
    }
    updateAgentSettings(await readJson(request));
    send(reply, 200, agentSettings);
    return;
  }
  if (request.method === 'POST' && url.pathname === '/api/code-quality-reviews/agent-settings/test') {
    if (scenario === 'MUTATION_FAILED') {
      sendError(reply, 503, 'Synthetic Agent test submission failure');
      return;
    }
    const asyncScenario = ['AGENT_ASYNC_SUCCESS', 'AGENT_ASYNC_FAILED'].includes(scenario);
    agentSettings = {
      ...agentSettings,
      configurationTest: {
        requestId: 'safe-mock-test',
        status: asyncScenario ? 'QUEUED' : 'SUCCESS',
        message: asyncScenario ? '本地安全 mock 测试已排队' : '本地安全 mock 测试成功',
        durationMs: asyncScenario ? null : 12,
        runtimeType: agentSettings.selectedRuntime
      }
    };
    agentTestPollCount = 0;
    send(reply, 200, agentSettings.configurationTest);
    return;
  }
  if (request.method === 'GET' && url.pathname === '/api/code-quality-review-providers') {
    if (scenario === 'PROVIDERS_READ_FAILED') {
      sendError(reply, 503, 'Synthetic Provider catalog read failure');
      return;
    }
    send(reply, 200, providers);
    return;
  }

  const providerMatch = /^\/api\/code-quality-review-providers\/([^/]+)$/.exec(url.pathname);
  if (request.method === 'PUT' && providerMatch) {
    if (scenario === 'MUTATION_FAILED') {
      sendError(reply, 503, 'Synthetic Provider save failure');
      return;
    }
    updateProvider(providerMatch[1], await readJson(request));
    send(reply, 200, providers);
    return;
  }
  const providerTestMatch = /^\/api\/code-quality-review-providers\/([^/]+)\/test$/.exec(url.pathname);
  if (request.method === 'POST' && providerTestMatch) {
    const body = await readJson(request);
    if (scenario === 'PROVIDER_TEST_FAILED') {
      send(reply, 200, {
        success: false,
        providerCode: providerTestMatch[1],
        endpointUrl: body.endpointUrl,
        modelName: body.modelName,
        errorMessage: 'Synthetic Provider connectivity failure'
      });
      return;
    }
    send(reply, 200, {
      success: true,
      providerCode: providerTestMatch[1],
      endpointUrl: body.endpointUrl,
      modelName: body.modelName,
      latencyMs: 12
    });
    return;
  }
  const defaultMatch = /^\/api\/code-quality-review-providers\/([^/]+)\/set-default$/.exec(url.pathname);
  if (request.method === 'POST' && defaultMatch) {
    if (scenario === 'MUTATION_FAILED') {
      sendError(reply, 503, 'Synthetic default Provider save failure');
      return;
    }
    settings = { ...settings, defaultProviderCode: defaultMatch[1] };
    providers = providers.map(item => ({ ...item, defaultProvider: item.providerCode === defaultMatch[1] }));
    send(reply, 200, settings);
    return;
  }

  if (request.method === 'GET' && url.pathname === '/api/code-quality-review-profiles') {
    send(reply, 200, []);
    return;
  }
  if (request.method === 'GET' && url.pathname === '/api/project-groups') {
    send(reply, 200, { items: [] });
    return;
  }
  if (request.method === 'GET' && url.pathname === '/api/projects') {
    send(reply, 200, { items: [] });
    return;
  }
  if (request.method === 'GET' && url.pathname === '/api/target-type-path-mappings') {
    send(reply, 200, []);
    return;
  }

  sendError(reply, 404, `Synthetic endpoint not found: ${request.method} ${url.pathname}`);
});

server.listen(port, host, () => {
  console.log(`Docs 54 settings safe mock ready at http://${host}:${port}`);
});

for (const signal of ['SIGINT', 'SIGTERM']) {
  process.on(signal, () => server.close(() => process.exit(0)));
}

function provider(code, name, type, model, enabled, isDefault) {
  return {
    providerCode: code,
    providerName: name,
    providerType: type,
    endpointUrl: `https://safe-mock.invalid/${code.toLowerCase()}`,
    modelName: model,
    timeoutSeconds: 1000,
    enabled,
    builtIn: true,
    defaultProvider: isDefault,
    apiKeyConfigured: true,
    apiKeyMasked: 'mock...only',
    updatedAt: '2026-08-08T08:05:00Z'
  };
}

function updateAgentSettings(body) {
  const next = { ...agentSettings };
  if ('enabled' in body) next.enabled = Boolean(body.enabled);
  if (body.selectedRuntime) next.selectedRuntime = body.selectedRuntime;
  if (body.budgets) {
    next.budgets = { ...next.budgets, ...body.budgets };
    next.budgetConfigSource = 'CUSTOM';
  }
  if (body.resetBudgets) {
    next.budgets = { ...defaultBudgets, maxDiffBytes: 500000 };
    next.budgetConfigSource = 'DEFAULT';
  }
  if (body.apiKey) next.defaultRuntime = { ...next.defaultRuntime, apiKeyConfigured: true };
  if (body.clearApiKey) {
    next.defaultRuntime = { ...next.defaultRuntime, apiKeyConfigured: false, apiKeyMasked: null };
    next.enabled = false;
  }
  if (body.customRuntime) {
    const custom = { ...next.customRuntime, ...body.customRuntime };
    if (body.customRuntime.apiKey) custom.apiKeyConfigured = true;
    if (body.customRuntime.clearApiKey) {
      custom.apiKeyConfigured = false;
      custom.apiKeyMasked = null;
      if (next.selectedRuntime === 'OPENAI_RESPONSES_CUSTOM') next.enabled = false;
    }
    custom.configurationComplete = Boolean(custom.baseUrl && custom.model && custom.apiKeyConfigured);
    delete custom.apiKey;
    delete custom.clearApiKey;
    next.customRuntime = custom;
  }
  next.updatedAt = new Date().toISOString();
  agentSettings = next;
}

function updateProvider(code, body) {
  providers = providers.map(item => {
    if (item.providerCode !== code) return item;
    const next = { ...item, ...body, updatedAt: new Date().toISOString() };
    if (body.apiKey) next.apiKeyConfigured = true;
    if (body.clearApiKey) {
      next.apiKeyConfigured = false;
      next.apiKeyMasked = null;
    }
    delete next.apiKey;
    delete next.clearApiKey;
    return next;
  });
}

function advanceAgentTestScenario() {
  if (!['AGENT_ASYNC_SUCCESS', 'AGENT_ASYNC_FAILED'].includes(scenario)) return;
  if (!['QUEUED', 'RUNNING'].includes(agentSettings.configurationTest?.status)) return;
  agentTestPollCount += 1;
  if (agentTestPollCount === 1) {
    agentSettings = {
      ...agentSettings,
      configurationTest: {
        ...agentSettings.configurationTest,
        status: 'RUNNING',
        message: '本地安全 mock Worker 正在执行'
      }
    };
    return;
  }
  const success = scenario === 'AGENT_ASYNC_SUCCESS';
  agentSettings = {
    ...agentSettings,
    configurationTest: {
      ...agentSettings.configurationTest,
      status: success ? 'SUCCESS' : 'FAILED',
      message: success ? '本地安全 mock 异步测试成功' : '本地安全 mock 异步测试失败',
      durationMs: 24
    }
  };
}

async function readJson(request) {
  const chunks = [];
  for await (const chunk of request) chunks.push(chunk);
  const raw = Buffer.concat(chunks).toString('utf8');
  return raw ? JSON.parse(raw) : {};
}

function send(reply, statusCode, data) {
  reply.statusCode = statusCode;
  reply.end(JSON.stringify({ success: true, data }));
}

function sendError(reply, statusCode, message) {
  reply.statusCode = statusCode;
  reply.end(JSON.stringify({ success: false, message }));
}

function parsePort(argv) {
  const index = argv.indexOf('--port');
  const value = index >= 0 ? Number(argv[index + 1]) : 8095;
  if (!Number.isInteger(value) || value < 1024 || value > 65535) {
    throw new Error('A valid non-privileged --port is required.');
  }
  return value;
}

function parseScenario(argv) {
  const index = argv.indexOf('--scenario');
  const value = index >= 0 ? String(argv[index + 1] || '') : 'BASELINE';
  return normalizeScenario(value);
}

function normalizeScenario(value) {
  const allowed = new Set([
    'BASELINE',
    'AGENT_INCOMPLETE',
    'AGENT_ASYNC_SUCCESS',
    'AGENT_ASYNC_FAILED',
    'PROVIDER_TEST_FAILED',
    'SETTINGS_READ_FAILED',
    'AGENT_READ_FAILED',
    'PROVIDERS_READ_FAILED',
    'MUTATION_FAILED'
  ]);
  if (!allowed.has(value)) throw new Error(`Unsupported safe mock scenario: ${value}`);
  return value;
}

function setScenario(value) {
  scenario = normalizeScenario(String(value || ''));
  agentTestPollCount = 0;
  agentSettings = {
    ...agentSettings,
    configurationTest: { status: 'NOT_RUN' }
  };
  if (scenario === 'AGENT_INCOMPLETE') {
    agentSettings = {
      ...agentSettings,
      selectedRuntime: 'OPENAI_RESPONSES_CUSTOM',
      customRuntime: {
        ...agentSettings.customRuntime,
        apiKeyConfigured: false,
        apiKeyMasked: null,
        configurationComplete: false,
        workerSupported: false
      }
    };
  }
}
