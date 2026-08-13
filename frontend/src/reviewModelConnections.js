import { customAgentRuntime, defaultAgentRuntime } from './agentReviewRuntime.js';

export const agentReviewConnection = 'AGENT';
export const standardReviewConnection = 'STANDARD';

export const connectionConfigurationStatus = Object.freeze({
  READY: 'READY',
  UNAVAILABLE: 'UNAVAILABLE',
  DISABLED: 'DISABLED',
  INCOMPLETE: 'INCOMPLETE',
  WORKER_UNSUPPORTED: 'WORKER_UNSUPPORTED'
});

function text(value) {
  return typeof value === 'string' ? value.trim() : '';
}

function optionalBoolean(value) {
  return typeof value === 'boolean' ? value : null;
}

function agentConnectionId(runtimeType) {
  return `${agentReviewConnection}:${runtimeType}`;
}

function standardConnectionId(providerCode) {
  return `${standardReviewConnection}:${providerCode}`;
}

function statusFor({ enabled, apiKeyConfigured, configurationComplete, workerSupported }) {
  if (apiKeyConfigured === false) return connectionConfigurationStatus.UNAVAILABLE;
  if (!configurationComplete) return connectionConfigurationStatus.INCOMPLETE;
  if (workerSupported === false) return connectionConfigurationStatus.WORKER_UNSUPPORTED;
  if (!enabled) return connectionConfigurationStatus.DISABLED;
  return connectionConfigurationStatus.READY;
}

function runtimeLabel(settings, runtimeType, fallback) {
  const option = Array.isArray(settings?.runtimeOptions)
    ? settings.runtimeOptions.find(item => text(item?.value) === runtimeType)
    : null;
  return text(option?.label) || fallback;
}

function buildAgentRows(agentSettings) {
  const selectedRuntime = agentSettings?.selectedRuntime === customAgentRuntime
    ? customAgentRuntime
    : defaultAgentRuntime;
  const enabled = agentSettings?.enabled === true;
  const updatedAt = text(agentSettings?.updatedAt) || null;
  const defaultRuntime = agentSettings?.defaultRuntime || {};
  const customRuntime = agentSettings?.customRuntime || {};

  const defaultEndpoint = text(defaultRuntime.endpoint);
  const defaultModel = text(defaultRuntime.model);
  const defaultKeyConfigured = defaultRuntime.apiKeyConfigured === true;
  const defaultComplete = Boolean(defaultEndpoint && defaultModel && defaultKeyConfigured);
  const defaultWorkerSupported = optionalBoolean(defaultRuntime.workerSupported);

  const customEndpoint = text(customRuntime.baseUrl);
  const customModel = text(customRuntime.model);
  const customKeyConfigured = customRuntime.apiKeyConfigured === true;
  const customComplete = typeof customRuntime.configurationComplete === 'boolean'
    ? customRuntime.configurationComplete
    : Boolean(customEndpoint && customModel && customKeyConfigured);
  const customWorkerSupported = optionalBoolean(customRuntime.workerSupported);

  return [
    {
      id: agentConnectionId(defaultAgentRuntime),
      reviewType: agentReviewConnection,
      connectionType: 'RUNTIME',
      runtimeType: defaultAgentRuntime,
      providerCode: null,
      name: runtimeLabel(agentSettings, defaultAgentRuntime, 'Claude Code + DeepSeek'),
      protocol: 'ANTHROPIC_COMPATIBLE',
      endpoint: defaultEndpoint || null,
      model: defaultModel || null,
      isDefault: true,
      isCurrent: selectedRuntime === defaultAgentRuntime,
      enabled,
      apiKeyConfigured: defaultKeyConfigured,
      configurationComplete: defaultComplete,
      workerSupported: defaultWorkerSupported,
      configurationStatus: statusFor({
        enabled,
        apiKeyConfigured: defaultKeyConfigured,
        configurationComplete: defaultComplete,
        workerSupported: defaultWorkerSupported
      }),
      updatedAt
    },
    {
      id: agentConnectionId(customAgentRuntime),
      reviewType: agentReviewConnection,
      connectionType: 'RUNTIME',
      runtimeType: customAgentRuntime,
      providerCode: null,
      name: text(customRuntime.displayName)
        || runtimeLabel(agentSettings, customAgentRuntime, '自定义 OpenAI Responses Agent'),
      protocol: text(customRuntime.protocol) || 'OPENAI_RESPONSES',
      endpoint: customEndpoint || null,
      model: customModel || null,
      isDefault: false,
      isCurrent: selectedRuntime === customAgentRuntime,
      enabled,
      apiKeyConfigured: customKeyConfigured,
      configurationComplete: customComplete,
      workerSupported: customWorkerSupported,
      configurationStatus: statusFor({
        enabled,
        apiKeyConfigured: customKeyConfigured,
        configurationComplete: customComplete,
        workerSupported: customWorkerSupported
      }),
      updatedAt
    }
  ];
}

function buildDynamicAgentRows(agentRuntimes) {
  const seen = new Set();
  return agentRuntimes.flatMap(runtime => {
    const runtimeCode = text(runtime?.runtimeCode).toUpperCase();
    if (!runtimeCode || seen.has(runtimeCode)) return [];
    seen.add(runtimeCode);
    const configurationComplete = runtime?.configurationComplete === true;
    const protocolAvailable = optionalBoolean(runtime?.protocolAvailable);
    return [{
      id: agentConnectionId(runtimeCode),
      reviewType: agentReviewConnection,
      connectionType: 'RUNTIME',
      runtimeType: runtimeCode,
      runtimeCode,
      providerCode: null,
      name: text(runtime?.displayName) || runtimeCode,
      protocol: text(runtime?.protocol) || null,
      endpoint: text(runtime?.baseUrl) || null,
      model: text(runtime?.model) || null,
      isDefault: runtime?.builtIn === true,
      isCurrent: runtime?.selected === true,
      enabled: runtime?.enabled === true,
      builtIn: runtime?.builtIn === true,
      apiKeyConfigured: runtime?.apiKeyConfigured === true,
      configurationComplete,
      workerSupported: protocolAvailable,
      unavailableReason: text(runtime?.unavailableReason) || null,
      configurationTest: runtime?.configurationTest || null,
      configurationStatus: statusFor({
        enabled: runtime?.enabled === true,
        apiKeyConfigured: runtime?.apiKeyConfigured === true,
        configurationComplete,
        workerSupported: protocolAvailable
      }),
      updatedAt: text(runtime?.updatedAt) || null
    }];
  });
}

function effectiveDefaultProviderCode(providers, defaultProviderCode) {
  const explicit = text(defaultProviderCode).toUpperCase();
  if (explicit) return explicit;
  const provider = providers.find(item => item?.defaultProvider === true);
  return text(provider?.providerCode).toUpperCase();
}

function buildStandardRows(providers, defaultProviderCode) {
  const defaultCode = effectiveDefaultProviderCode(providers, defaultProviderCode);
  const seen = new Set();
  const rows = [];

  providers.forEach(provider => {
    if (provider?.catalogVisible === false) return;
    const providerCode = text(provider?.providerCode).toUpperCase();
    if (!providerCode || seen.has(providerCode)) return;
    seen.add(providerCode);

    const endpoint = text(provider?.endpointUrl);
    const model = text(provider?.modelName);
    const apiKeyConfigured = provider?.apiKeyConfigured === true;
    const configurationComplete = Boolean(endpoint && model && apiKeyConfigured);
    const isDefault = providerCode === defaultCode;

    rows.push({
      id: standardConnectionId(providerCode),
      reviewType: standardReviewConnection,
      connectionType: 'PROVIDER',
      runtimeType: null,
      providerCode,
      name: text(provider?.providerName) || providerCode,
      protocol: text(provider?.providerType) || null,
      endpoint: endpoint || null,
      model: model || null,
      isDefault,
      isCurrent: isDefault,
      enabled: true,
      apiKeyConfigured,
      configurationComplete,
      workerSupported: null,
      configurationStatus: statusFor({
        enabled: true,
        apiKeyConfigured,
        configurationComplete,
        workerSupported: null
      }),
      updatedAt: text(provider?.updatedAt) || null
    });
  });

  return rows;
}

export function buildReviewModelConnectionCatalog({
  agentSettings = null,
  agentRuntimes = null,
  providers = [],
  defaultProviderCode = null
} = {}) {
  const providerItems = Array.isArray(providers) ? providers : [];
  const runtimeItems = Array.isArray(agentRuntimes) ? agentRuntimes : null;
  return [
    ...(runtimeItems ? buildDynamicAgentRows(runtimeItems) : buildAgentRows(agentSettings)),
    ...buildStandardRows(providerItems, defaultProviderCode)
  ];
}

export function resolveReviewModelConnectionSelection(rows, previousSelectedId = null) {
  const items = Array.isArray(rows) ? rows : [];
  const previous = text(previousSelectedId);
  if (previous && items.some(item => item?.id === previous)) return previous;

  return items.find(item => item?.reviewType === standardReviewConnection && item?.isDefault)?.id
    || items.find(item => item?.reviewType === agentReviewConnection && item?.isCurrent)?.id
    || items[0]?.id
    || null;
}
