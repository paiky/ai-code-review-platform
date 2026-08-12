export const agentProtocolOptions = Object.freeze([
  { value: 'OPENAI_RESPONSES', label: 'OpenAI Responses', disabled: false, reason: null },
  {
    value: 'OPENAI_CHAT_COMPLETIONS',
    label: 'OpenAI Chat Completions',
    disabled: false,
    reason: null
  },
  {
    value: 'ANTHROPIC_MESSAGES',
    label: 'Anthropic Messages',
    disabled: false,
    reason: null
  }
]);

export function agentProtocolOptionsForWorkerPool(workerPool) {
  const nodes = Array.isArray(workerPool?.nodes) ? workerPool.nodes : [];
  const runners = {
    OPENAI_CHAT_COMPLETIONS: 'OPENAI_CHAT_AGENT',
    ANTHROPIC_MESSAGES: 'ANTHROPIC_MESSAGES_AGENT'
  };
  return agentProtocolOptions.map(option => {
    const runner = runners[option.value];
    if (!runner) return option;
    const available = nodes.some(node => (
      node?.online === true
      && String(node?.state || 'IDLE').toUpperCase() !== 'DRAINING'
      && Array.isArray(node?.capabilities)
      && node.capabilities.includes(runner)
    ));
    return available
      ? option
      : { ...option, disabled: true, reason: `当前没有在线 Worker 支持 ${runner}` };
  });
}

const runtimeCodePattern = /^[A-Z][A-Z0-9_]{0,39}$/;
const protocols = new Set(agentProtocolOptions.map(item => item.value));

function text(value) {
  return typeof value === 'string' ? value.trim() : '';
}

export function normalizeAgentRuntimeCode(value) {
  return text(value).toUpperCase();
}

export function createAgentRuntimeDraft(runtime = null) {
  return {
    runtimeCode: normalizeAgentRuntimeCode(runtime?.runtimeCode),
    displayName: text(runtime?.displayName),
    protocol: text(runtime?.protocol) || 'OPENAI_RESPONSES',
    baseUrl: text(runtime?.baseUrl),
    model: text(runtime?.model) || 'gpt-5.6-sol',
    reasoningEffort: text(runtime?.reasoningEffort) || 'high',
    tlsVerify: runtime?.tlsVerify !== false,
    apiKey: '',
    enabled: runtime?.enabled === true
  };
}

export function validateAgentRuntimeDraft(draft, { creating = false, apiKeyConfigured = false } = {}) {
  const runtimeCode = normalizeAgentRuntimeCode(draft?.runtimeCode);
  const displayName = text(draft?.displayName);
  const protocol = text(draft?.protocol);
  const baseUrl = text(draft?.baseUrl);
  const model = text(draft?.model);
  const apiKey = text(draft?.apiKey);
  if (creating && !runtimeCodePattern.test(runtimeCode)) {
    return 'Runtime Code 必须以大写字母开头，且只能包含大写字母、数字和下划线（最多 40 位）';
  }
  if (!displayName || displayName.length > 64) return '配置名称长度必须为 1～64 个字符';
  if (!protocols.has(protocol)) return '请选择受支持的 Agent 协议';
  const option = agentProtocolOptions.find(item => item.value === protocol);
  if (option?.disabled) return option.reason;
  if (!baseUrl || baseUrl.length > 1024) return 'Base URL 长度必须为 1～1024 个字符';
  if (!model || model.length > 128) return '模型名称长度必须为 1～128 个字符';
  if (apiKey.length > 1024) return 'API Key 最多 1024 个字符';
  if (!apiKey && !apiKeyConfigured) return '请填写 Agent Runtime API Key';
  if (protocol === 'OPENAI_RESPONSES' && !['low', 'medium', 'high'].includes(draft?.reasoningEffort)) {
    return '请选择有效的推理强度';
  }
  return null;
}

export function buildCreateAgentRuntimeRequest(draft) {
  const request = {
    runtimeCode: normalizeAgentRuntimeCode(draft?.runtimeCode),
    displayName: text(draft?.displayName),
    protocol: text(draft?.protocol),
    baseUrl: text(draft?.baseUrl),
    model: text(draft?.model),
    tlsVerify: draft?.tlsVerify !== false,
    apiKey: text(draft?.apiKey) || null,
    enabled: draft?.enabled === true
  };
  if (draft?.protocol === 'OPENAI_RESPONSES') request.reasoningEffort = draft?.reasoningEffort;
  return request;
}

export function buildUpdateAgentRuntimeRequest(draft) {
  const request = {
    displayName: text(draft?.displayName),
    baseUrl: text(draft?.baseUrl),
    model: text(draft?.model),
    tlsVerify: draft?.tlsVerify !== false,
    enabled: true
  };
  if (draft?.protocol === 'OPENAI_RESPONSES') request.reasoningEffort = draft?.reasoningEffort;
  const apiKey = text(draft?.apiKey);
  if (apiKey) request.apiKey = apiKey;
  return request;
}

export function buildTestAgentRuntimeRequest(draft) {
  const request = {
    baseUrl: text(draft?.baseUrl),
    model: text(draft?.model),
    tlsVerify: draft?.tlsVerify !== false
  };
  if (draft?.protocol === 'OPENAI_RESPONSES') request.reasoningEffort = draft?.reasoningEffort;
  const apiKey = text(draft?.apiKey);
  if (apiKey) request.apiKey = apiKey;
  return request;
}

export function agentRuntimeDeleteAvailability(runtime) {
  if (!runtime || runtime.builtIn === true) {
    return { visible: false, disabled: true, reason: '内置 Runtime 不可删除' };
  }
  if (runtime.selected === true) {
    return { visible: true, disabled: true, reason: '当前 Runtime 不可删除' };
  }
  const testStatus = text(runtime.configurationTest?.status).toUpperCase();
  if (['QUEUED', 'RUNNING'].includes(testStatus)) {
    return { visible: true, disabled: true, reason: '配置测试进行中' };
  }
  return { visible: true, disabled: false, reason: null };
}

export function matchesAgentRuntimeDeleteConfirmation(runtimeCode, confirmation) {
  return text(confirmation) === normalizeAgentRuntimeCode(runtimeCode);
}
