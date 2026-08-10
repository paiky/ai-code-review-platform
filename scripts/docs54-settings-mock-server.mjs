import http from 'node:http';

const host = '127.0.0.1';
const port = parsePort(process.argv);
let scenario = parseScenario(process.argv);
let agentTestPollCount = 0;
let connectionSequence = 0;

const reviewModelPresets = {
  AGENT: [
    preset('AGENT_CLAUDE_CODE_DEEPSEEK', 'AGENT', 'DEEPSEEK', 'Claude Code + DeepSeek', [
      variant('ANTHROPIC_COMPATIBLE', 'https://safe-mock.invalid/anthropic', 'deepseek-v4-pro[1m]', true)
    ]),
    preset('AGENT_OPENAI', 'AGENT', 'OPENAI', 'OpenAI', [
      variant('OPENAI_RESPONSES', 'https://safe-mock.invalid/v1', 'gpt-5.6-sol', true),
      variant('OPENAI_CHAT_COMPLETIONS', 'https://safe-mock.invalid/v1', 'synthetic-chat-model')
    ]),
    preset('AGENT_ANTHROPIC', 'AGENT', 'ANTHROPIC', 'Anthropic / Claude', [
      variant('ANTHROPIC_MESSAGES', 'https://safe-mock.invalid/v1', 'synthetic-anthropic-model')
    ]),
    preset('AGENT_CUSTOM', 'AGENT', 'CUSTOM', '自定义', [], true)
  ],
  STANDARD: [
    preset('STANDARD_OPENAI', 'STANDARD', 'OPENAI', 'OpenAI', [
      variant('OPENAI_RESPONSES', 'https://safe-mock.invalid/responses', 'gpt-5.6-sol', true)
    ]),
    preset('STANDARD_ANTHROPIC', 'STANDARD', 'ANTHROPIC', 'Anthropic / Claude', [
      variant('ANTHROPIC_MESSAGES', 'https://safe-mock.invalid/messages', 'claude-sonnet')
    ]),
    preset('STANDARD_DEEPSEEK', 'STANDARD', 'DEEPSEEK', 'DeepSeek', [
      variant('OPENAI_CHAT_COMPATIBLE', 'https://safe-mock.invalid/deepseek', 'deepseek-v4-pro')
    ]),
    preset('STANDARD_XIAOMIMO', 'STANDARD', 'XIAOMIMO', 'XiaoMIMO / Xiaomi MiMo', [
      variant('OPENAI_CHAT_COMPATIBLE', 'https://safe-mock.invalid/mimo', 'mimo-v2.5-pro')
    ]),
    preset('STANDARD_GLM', 'STANDARD', 'GLM', '智谱 GLM', [
      variant('OPENAI_CHAT_COMPATIBLE', 'https://safe-mock.invalid/glm', 'glm-4.5')
    ]),
    preset('STANDARD_CUSTOM', 'STANDARD', 'CUSTOM', '自定义', [], true)
  ]
};

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
    nodes: [{
      workerId: 'safe-mock-worker',
      online: true,
      state: 'IDLE',
      capabilities: [
        'CLAUDE_CODE_DEEPSEEK',
        'OPENAI_RESPONSES_AGENT',
        'OPENAI_CHAT_AGENT',
        'ANTHROPIC_MESSAGES_AGENT'
      ]
    }]
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

let agentRuntimes = [
  agentRuntime('CLAUDE_CODE_DEEPSEEK', 'Claude Code + DeepSeek', 'ANTHROPIC_COMPATIBLE', true, true),
  agentRuntime('OPENAI_RESPONSES_CUSTOM', 'Safe Mock Relay', 'OPENAI_RESPONSES', false, false)
];

let providers = [
  provider('DEEPSEEK', 'DeepSeek V4 Pro', 'OPENAI_CHAT_COMPATIBLE', 'deepseek-v4-pro', true, true),
  provider('OPENAI', 'OpenAI', 'OPENAI_CHAT_COMPATIBLE', 'gpt-5.6-sol', true, false),
  provider('ANTHROPIC', 'Claude Sonnet', 'ANTHROPIC_MESSAGES', 'claude-sonnet', false, false),
  { ...provider('GLM', '智谱 GLM', 'OPENAI_CHAT_COMPATIBLE', 'glm-4.5', false, false), catalogVisible: false, apiKeyConfigured: false }
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
  agentRuntimes = agentRuntimes.map(item => item.runtimeCode === 'OPENAI_RESPONSES_CUSTOM'
    ? { ...item, apiKeyConfigured: false, configurationComplete: false, protocolAvailable: false }
    : item);
}
if (scenario === 'NO_WORKER_CAPABILITY') {
  agentSettings.workerPool.nodes = agentSettings.workerPool.nodes.map(node => ({
    ...node,
    capabilities: []
  }));
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
  if (request.method === 'GET' && url.pathname === '/api/review-model-presets') {
    const reviewType = String(url.searchParams.get('reviewType') || '').toUpperCase();
    send(reply, 200, reviewModelPresets[reviewType] || []);
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
  if (request.method === 'GET' && url.pathname === '/api/code-quality-agent-runtimes') {
    if (scenario === 'AGENT_READ_FAILED') {
      sendError(reply, 503, 'Synthetic Agent Runtime read failure');
      return;
    }
    advanceAgentTestScenario();
    send(reply, 200, agentRuntimes);
    return;
  }
  if (request.method === 'POST' && url.pathname === '/api/review-model-connections') {
    if (scenario === 'MUTATION_FAILED') {
      sendError(reply, 503, 'Synthetic model connection create failure');
      return;
    }
    const body = await readJson(request);
    if (!String(body.apiKey || '').trim()) {
      sendError(reply, 400, 'API Key 为必填项');
      return;
    }
    if (body.reviewType === 'AGENT' && scenario === 'NO_WORKER_CAPABILITY') {
      sendError(reply, 409, 'Synthetic Worker capability unavailable');
      return;
    }
    const presets = reviewModelPresets[body.reviewType] || [];
    const selectedPreset = presets.find(item => item.presetCode === body.presetCode);
    if (!selectedPreset) {
      sendError(reply, 400, 'Synthetic preset not found');
      return;
    }
    connectionSequence += 1;
    const baseName = `${selectedPreset.vendorName} · ${body.model}`;
    if (body.reviewType === 'AGENT') {
      const duplicateCount = agentRuntimes.filter(item => item.displayName === baseName || item.displayName.startsWith(`${baseName}（`)).length;
      const runtimeCode = `AGENT_${selectedPreset.vendorCode}_${String(connectionSequence).padStart(4, '0')}`;
      const created = {
        ...agentRuntime(runtimeCode, duplicateCount ? `${baseName}（${duplicateCount + 1}）` : baseName, body.protocol, false, false),
        baseUrl: body.baseUrl,
        model: body.model,
        reasoningEffort: body.reasoningEffort || null,
        tlsVerify: body.tlsVerify !== false,
        enabled: true,
        apiKeyConfigured: true,
        configurationComplete: true,
        updatedAt: new Date().toISOString()
      };
      agentRuntimes = [...agentRuntimes, created];
      send(reply, 200, created);
      return;
    }
    const duplicateCount = providers.filter(item => item.providerName === baseName || item.providerName.startsWith(`${baseName}（`)).length;
    const providerCode = `STANDARD_${selectedPreset.vendorCode}_${String(connectionSequence).padStart(4, '0')}`;
    const created = {
      providerCode,
      providerName: duplicateCount ? `${baseName}（${duplicateCount + 1}）` : baseName,
      providerType: body.protocol,
      endpointUrl: body.baseUrl,
      modelName: body.model,
      reasoningEffort: body.reasoningEffort || null,
      tlsVerify: body.tlsVerify !== false,
      timeoutSeconds: null,
      enabled: true,
      builtIn: false,
      defaultProvider: false,
      catalogVisible: true,
      apiKeyConfigured: true,
      apiKeyMasked: 'mock...only',
      updatedAt: new Date().toISOString()
    };
    providers = [...providers, created];
    send(reply, 200, created);
    return;
  }
  if (request.method === 'POST' && url.pathname === '/api/code-quality-agent-runtimes') {
    if (scenario === 'MUTATION_FAILED') {
      sendError(reply, 503, 'Synthetic Agent Runtime create failure');
      return;
    }
    const body = await readJson(request);
    const runtimeCode = String(body.runtimeCode || '').trim().toUpperCase();
    if (agentRuntimes.some(item => item.runtimeCode === runtimeCode)) {
      sendError(reply, 409, 'Synthetic duplicate Agent Runtime');
      return;
    }
    const created = {
      ...agentRuntime(runtimeCode, body.displayName, body.protocol, false, false),
      baseUrl: body.baseUrl,
      model: body.model,
      reasoningEffort: body.reasoningEffort,
      tlsVerify: body.tlsVerify !== false,
      enabled: body.enabled === true,
      apiKeyConfigured: Boolean(body.apiKey),
      configurationComplete: Boolean(body.baseUrl && body.model && body.apiKey),
      updatedAt: new Date().toISOString()
    };
    agentRuntimes = [...agentRuntimes, created];
    send(reply, 200, created);
    return;
  }
  const agentRuntimeMatch = /^\/api\/code-quality-agent-runtimes\/([^/]+)$/.exec(url.pathname);
  if (request.method === 'PUT' && agentRuntimeMatch) {
    const body = await readJson(request);
    let updated = null;
    agentRuntimes = agentRuntimes.map(item => {
      if (item.runtimeCode !== agentRuntimeMatch[1]) return item;
      updated = { ...item, ...body, updatedAt: new Date().toISOString() };
      if (body.apiKey) updated.apiKeyConfigured = true;
      if (body.clearApiKey) {
        updated.apiKeyConfigured = false;
        updated.enabled = false;
      }
      updated.configurationComplete = Boolean(updated.baseUrl && updated.model && updated.apiKeyConfigured);
      delete updated.apiKey;
      delete updated.clearApiKey;
      return updated;
    });
    send(reply, 200, updated);
    return;
  }
  if (request.method === 'DELETE' && agentRuntimeMatch) {
    const target = agentRuntimes.find(item => item.runtimeCode === agentRuntimeMatch[1]);
    if (!target || target.builtIn || target.selected) {
      sendError(reply, 409, 'Synthetic protected Agent Runtime');
      return;
    }
    agentRuntimes = agentRuntimes.filter(item => item.runtimeCode !== target.runtimeCode);
    send(reply, 200, { runtimeCode: target.runtimeCode, deleted: true });
    return;
  }
  const runtimeTestMatch = /^\/api\/code-quality-agent-runtimes\/([^/]+)\/test$/.exec(url.pathname);
  if (request.method === 'POST' && runtimeTestMatch) {
    const asyncScenario = ['AGENT_ASYNC_SUCCESS', 'AGENT_ASYNC_FAILED'].includes(scenario);
    const configurationTest = {
      runtimeCode: runtimeTestMatch[1],
      requestId: `safe-mock-runtime-test:${runtimeTestMatch[1]}`,
      status: asyncScenario ? 'QUEUED' : 'SUCCESS',
      message: asyncScenario ? '本地安全 mock 测试已排队' : '本地安全 mock 测试成功',
      durationMs: asyncScenario ? null : 12
    };
    agentRuntimes = agentRuntimes.map(item => item.runtimeCode === runtimeTestMatch[1]
      ? { ...item, configurationTest }
      : item);
    agentTestPollCount = 0;
    send(reply, 200, configurationTest);
    return;
  }
  const runtimeCurrentMatch = /^\/api\/code-quality-agent-runtimes\/([^/]+)\/set-current$/.exec(url.pathname);
  if (request.method === 'POST' && runtimeCurrentMatch) {
    agentRuntimes = agentRuntimes.map(item => ({
      ...item,
      selected: item.runtimeCode === runtimeCurrentMatch[1]
    }));
    send(reply, 200, { selectedRuntimeCode: runtimeCurrentMatch[1] });
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
  if (request.method === 'POST' && url.pathname === '/api/code-quality-review-providers') {
    if (scenario === 'MUTATION_FAILED') {
      sendError(reply, 503, 'Synthetic Provider create failure');
      return;
    }
    const body = await readJson(request);
    const providerCode = String(body.providerCode || '').trim().toUpperCase();
    if (providers.some(item => item.providerCode === providerCode)) {
      sendError(reply, 409, `Synthetic duplicate Provider: ${providerCode}`);
      return;
    }
    const created = {
      providerCode,
      providerName: String(body.providerName || providerCode).trim(),
      providerType: body.providerType,
      endpointUrl: body.endpointUrl || null,
      modelName: body.modelName || null,
      timeoutSeconds: body.timeoutSeconds || null,
      enabled: body.enabled === true,
      builtIn: false,
      defaultProvider: false,
      apiKeyConfigured: Boolean(body.apiKey),
      apiKeyMasked: body.apiKey ? 'mock...only' : null,
      updatedAt: new Date().toISOString()
    };
    providers = [...providers, created];
    send(reply, 200, created);
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
  if (request.method === 'DELETE' && providerMatch) {
    if (scenario === 'MUTATION_FAILED') {
      sendError(reply, 503, 'Synthetic Provider delete failure');
      return;
    }
    const providerCode = providerMatch[1];
    const target = providers.find(item => item.providerCode === providerCode);
    if (!target) {
      sendError(reply, 404, `Synthetic Provider not found: ${providerCode}`);
      return;
    }
    if (target.builtIn) {
      sendError(reply, 409, `Synthetic built-in Provider cannot be deleted: ${providerCode}`);
      return;
    }
    if (target.defaultProvider) {
      sendError(reply, 409, `Synthetic default Provider cannot be deleted: ${providerCode}`);
      return;
    }
    if (scenario === 'PROVIDER_DELETE_IN_USE') {
      sendError(reply, 409, `Synthetic Provider is in use: ${providerCode}`);
      return;
    }
    providers = providers.filter(item => item.providerCode !== providerCode);
    send(reply, 200, { providerCode, deleted: true });
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
    reasoningEffort: type === 'OPENAI_RESPONSES' ? 'high' : null,
    tlsVerify: true,
    catalogVisible: true,
    enabled,
    builtIn: true,
    defaultProvider: isDefault,
    apiKeyConfigured: true,
    apiKeyMasked: 'mock...only',
    updatedAt: '2026-08-08T08:05:00Z'
  };
}

function agentRuntime(code, name, protocol, builtIn, selected) {
  const responses = protocol === 'OPENAI_RESPONSES';
  const chat = protocol === 'OPENAI_CHAT_COMPLETIONS';
  const anthropic = protocol === 'ANTHROPIC_MESSAGES';
  return {
    runtimeCode: code,
    displayName: name,
    protocol,
    runnerType: responses ? 'OPENAI_RESPONSES_AGENT' : chat ? 'OPENAI_CHAT_AGENT' : anthropic ? 'ANTHROPIC_MESSAGES_AGENT' : 'CLAUDE_CODE',
    baseUrl: responses || chat || anthropic ? 'https://safe-mock.invalid/v1' : 'https://safe-mock.invalid/agent',
    model: responses ? 'gpt-5.6-sol' : chat ? 'synthetic-chat-model' : anthropic ? 'synthetic-anthropic-model' : 'deepseek-v4-pro[1m]',
    reasoningEffort: responses ? 'high' : null,
    tlsVerify: true,
    enabled: true,
    builtIn,
    selected,
    apiKeyConfigured: true,
    apiKeyMasked: 'mock...only',
    configurationComplete: true,
    protocolAvailable: true,
    unavailableReason: null,
    configurationTest: { status: 'NOT_RUN' },
    updatedAt: '2026-08-08T08:00:00Z'
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
      next.enabled = false;
    }
    delete next.apiKey;
    delete next.clearApiKey;
    return next;
  });
}

function advanceAgentTestScenario() {
  if (!['AGENT_ASYNC_SUCCESS', 'AGENT_ASYNC_FAILED'].includes(scenario)) return;
  const activeRuntime = agentRuntimes.find(item => (
    ['QUEUED', 'RUNNING'].includes(item.configurationTest?.status)
  ));
  const legacyActive = ['QUEUED', 'RUNNING'].includes(agentSettings.configurationTest?.status);
  if (!activeRuntime && !legacyActive) return;
  agentTestPollCount += 1;
  if (agentTestPollCount === 1) {
    if (activeRuntime) {
      agentRuntimes = agentRuntimes.map(item => item.runtimeCode === activeRuntime.runtimeCode
        ? {
          ...item,
          configurationTest: {
            ...item.configurationTest,
            status: 'RUNNING',
            message: '本地安全 mock Worker 正在执行'
          }
        }
        : item);
    }
    if (!legacyActive) return;
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
  if (activeRuntime) {
    agentRuntimes = agentRuntimes.map(item => item.runtimeCode === activeRuntime.runtimeCode
      ? {
        ...item,
        configurationTest: {
          ...item.configurationTest,
          status: success ? 'SUCCESS' : 'FAILED',
          message: success ? '本地安全 mock 异步测试成功' : '本地安全 mock 异步测试失败',
          durationMs: 24
        }
      }
      : item);
  }
  if (!legacyActive) return;
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
    'PROVIDER_DELETE_IN_USE',
    'NO_WORKER_CAPABILITY',
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
    configurationTest: { status: 'NOT_RUN' },
    workerPool: {
      ...agentSettings.workerPool,
      nodes: agentSettings.workerPool.nodes.map(node => ({
        ...node,
        capabilities: [
          'CLAUDE_CODE_DEEPSEEK',
          'OPENAI_RESPONSES_AGENT',
          'OPENAI_CHAT_AGENT',
          'ANTHROPIC_MESSAGES_AGENT'
        ]
      }))
    }
  };
  agentRuntimes = agentRuntimes.map(item => ({
    ...item,
    protocolAvailable: true,
    configurationTest: { status: 'NOT_RUN' }
  }));
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
    agentRuntimes = agentRuntimes.map(item => item.runtimeCode === 'OPENAI_RESPONSES_CUSTOM'
      ? { ...item, apiKeyConfigured: false, configurationComplete: false, protocolAvailable: false }
      : item);
  }
  if (scenario === 'NO_WORKER_CAPABILITY') {
    agentSettings = {
      ...agentSettings,
      workerPool: {
        ...agentSettings.workerPool,
        nodes: agentSettings.workerPool.nodes.map(node => ({ ...node, capabilities: [] }))
      }
    };
  }
}

function preset(presetCode, reviewType, vendorCode, vendorName, variants, custom = false) {
  return { presetCode, reviewType, vendorCode, vendorName, custom, variants };
}

function variant(protocol, baseUrl, model, reasoning = false) {
  return {
    protocol,
    baseUrl,
    models: [model],
    defaultModel: model,
    reasoningEfforts: reasoning ? ['low', 'medium', 'high'] : [],
    defaultReasoningEffort: reasoning ? 'high' : null
  };
}
