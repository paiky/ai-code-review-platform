export const defaultAgentRuntime = 'CLAUDE_CODE_DEEPSEEK';
export const customAgentRuntime = 'OPENAI_RESPONSES_CUSTOM';
export const agentConfigurationTestPollTimeoutMs = 120_000;

export function normalizeAgentRuntimeDraft(settings) {
  const selectedRuntime = settings?.selectedRuntime === customAgentRuntime
    ? customAgentRuntime
    : defaultAgentRuntime;
  return {
    enabled: settings?.enabled ?? false,
    selectedRuntime,
    apiKey: '',
    customRuntime: {
      displayName: settings?.customRuntime?.displayName || 'Custom OpenAI Agent',
      baseUrl: settings?.customRuntime?.baseUrl || '',
      apiKey: '',
      model: settings?.customRuntime?.model || 'gpt-5.6-sol',
      reasoningEffort: settings?.customRuntime?.reasoningEffort || 'high',
      tlsVerify: settings?.customRuntime?.tlsVerify !== false
    }
  };
}

export function selectedRuntimeSettings(settings, selectedRuntime) {
  return selectedRuntime === customAgentRuntime
    ? (settings?.customRuntime || {})
    : (settings?.defaultRuntime || settings || {});
}

export function validateAgentRuntimeDraft(draft, settings) {
  if (![defaultAgentRuntime, customAgentRuntime].includes(draft?.selectedRuntime)) {
    return '请选择有效的 Agent 运行时';
  }
  if (!draft.enabled) return null;
  if (draft.selectedRuntime === customAgentRuntime) {
    const custom = draft.customRuntime || {};
    if (!String(custom.baseUrl || '').trim()) return '请填写自定义中转站 Base URL';
    try {
      const url = new URL(String(custom.baseUrl).trim());
      if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password || url.search || url.hash) {
        return 'Base URL 必须是无凭据、查询参数和片段的 HTTP 或 HTTPS 地址';
      }
    } catch {
      return 'Base URL 格式不正确';
    }
    if (!String(custom.model || '').trim()) return '请填写自定义 Agent 模型';
    if (!['low', 'medium', 'high'].includes(custom.reasoningEffort)) return '请选择有效的推理强度';
  }
  const selected = selectedRuntimeSettings(settings, draft.selectedRuntime);
  const draftKey = draft.selectedRuntime === customAgentRuntime
    ? String(draft.customRuntime?.apiKey || '').trim()
    : String(draft.apiKey || '').trim();
  if (!draftKey && !selected.apiKeyConfigured) return '启用 Agent Review 前请配置当前运行时的 API Key';
  return null;
}

export function buildAgentSettingsPayload(draft, { clearKey = false } = {}) {
  const body = {
    enabled: clearKey ? false : Boolean(draft.enabled),
    selectedRuntime: draft.selectedRuntime,
    budgets: draft.budgets
  };
  if (draft.selectedRuntime === customAgentRuntime) {
    const custom = draft.customRuntime || {};
    body.customRuntime = {
      displayName: String(custom.displayName || '').trim(),
      baseUrl: String(custom.baseUrl || '').trim(),
      model: String(custom.model || '').trim(),
      reasoningEffort: custom.reasoningEffort || 'high',
      tlsVerify: custom.tlsVerify !== false
    };
    const apiKey = String(custom.apiKey || '').trim();
    if (apiKey) body.customRuntime.apiKey = apiKey;
    if (clearKey) body.customRuntime.clearApiKey = true;
  } else {
    const apiKey = String(draft.apiKey || '').trim();
    if (apiKey) body.apiKey = apiKey;
    if (clearKey) body.clearApiKey = true;
  }
  return body;
}
