export const providerTypeOptions = Object.freeze([
  { value: 'OPENAI_CHAT_COMPATIBLE', label: 'OpenAI Chat Completions Compatible' },
  { value: 'OPENAI_RESPONSES', label: 'OpenAI Responses' },
  { value: 'ANTHROPIC_MESSAGES', label: 'Anthropic Messages' }
]);

const providerTypes = new Set(providerTypeOptions.map(item => item.value));
const providerCodePattern = /^[A-Z][A-Z0-9_]{0,63}$/;

function text(value) {
  return typeof value === 'string' ? value.trim() : '';
}

export function createProviderDraft() {
  return {
    providerCode: '',
    providerName: '',
    providerType: 'OPENAI_CHAT_COMPATIBLE',
    endpointUrl: '',
    modelName: '',
    timeoutSeconds: null,
    apiKey: ''
  };
}

export function normalizeProviderCode(value) {
  return text(value).toUpperCase();
}

export function validateCreateProviderDraft(draft) {
  const providerCode = normalizeProviderCode(draft?.providerCode);
  const providerName = text(draft?.providerName);
  const providerType = text(draft?.providerType);
  const endpointUrl = text(draft?.endpointUrl);
  const modelName = text(draft?.modelName);
  const apiKey = text(draft?.apiKey);
  const timeout = draft?.timeoutSeconds;

  if (!providerCodePattern.test(providerCode)) {
    return 'Provider Code 必须以大写字母开头，且只能包含大写字母、数字和下划线（最多 64 位）';
  }
  if (!providerName || providerName.length > 128) return '配置名称长度必须为 1～128 个字符';
  if (!providerTypes.has(providerType)) return '请选择受支持的 Provider 协议';
  if (endpointUrl.length > 512) return 'Endpoint URL 最多 512 个字符';
  if (modelName.length > 128) return '模型名称最多 128 个字符';
  if (apiKey.length > 1024) return 'API Key 最多 1024 个字符';
  if (timeout !== null && timeout !== undefined && timeout !== '') {
    if (!Number.isInteger(timeout) || timeout < 1 || timeout > 3600) {
      return 'Review 超时秒数必须为 1～3600 的整数';
    }
  }
  return null;
}

export function buildCreateProviderRequest(draft) {
  return {
    providerCode: normalizeProviderCode(draft?.providerCode),
    providerName: text(draft?.providerName),
    providerType: text(draft?.providerType),
    endpointUrl: text(draft?.endpointUrl) || null,
    modelName: text(draft?.modelName) || null,
    timeoutSeconds: draft?.timeoutSeconds || null,
    apiKey: text(draft?.apiKey) || null
  };
}

export function providerDeleteAvailability(provider) {
  if (!provider || provider.builtIn !== false) {
    return { visible: false, disabled: true, reason: '内置 Provider 不可删除' };
  }
  if (provider.defaultProvider === true) {
    return { visible: true, disabled: true, reason: 'Standard 默认 Provider 不可删除' };
  }
  return { visible: true, disabled: false, reason: null };
}

export function matchesProviderDeleteConfirmation(providerCode, confirmation) {
  return text(confirmation) === normalizeProviderCode(providerCode);
}
