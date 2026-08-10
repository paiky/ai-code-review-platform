import {
  agentReviewConnection,
  standardReviewConnection
} from './reviewModelConnections.js';

export const reasoningEffortOptions = Object.freeze(['low', 'medium', 'high']);

const standardProtocols = Object.freeze([
  { value: 'OPENAI_RESPONSES', label: 'OpenAI Responses' },
  { value: 'ANTHROPIC_MESSAGES', label: 'Anthropic Messages' },
  { value: 'OPENAI_CHAT_COMPATIBLE', label: 'OpenAI Chat Compatible' }
]);

const agentProtocols = Object.freeze([
  { value: 'ANTHROPIC_COMPATIBLE', label: 'Anthropic Compatible（Claude Code）' },
  { value: 'OPENAI_RESPONSES', label: 'OpenAI Responses' },
  { value: 'OPENAI_CHAT_COMPLETIONS', label: 'OpenAI Chat Completions' },
  { value: 'ANTHROPIC_MESSAGES', label: 'Anthropic Messages' }
]);

function text(value) {
  return typeof value === 'string' ? value.trim() : '';
}

export function connectionProtocolOptions(reviewType) {
  return reviewType === standardReviewConnection
    ? standardProtocols.map(item => ({ ...item }))
    : agentProtocols.map(item => ({ ...item }));
}

export function presetProtocolOptions(preset, reviewType, workerPool = null) {
  const labels = new Map(connectionProtocolOptions(reviewType).map(item => [item.value, item.label]));
  const protocols = preset?.custom
    ? connectionProtocolOptions(reviewType).map(item => item.value)
    : (preset?.variants || []).map(item => item.protocol);
  if (reviewType !== agentReviewConnection) {
    return protocols.map(value => ({ value, label: labels.get(value) || value, disabled: false }));
  }
  const capabilityByProtocol = {
    ANTHROPIC_COMPATIBLE: ['CLAUDE_CODE', 'CLAUDE_CODE_DEEPSEEK'],
    OPENAI_RESPONSES: ['OPENAI_RESPONSES_AGENT', 'OPENAI_RESPONSES_CUSTOM'],
    OPENAI_CHAT_COMPLETIONS: ['OPENAI_CHAT_AGENT'],
    ANTHROPIC_MESSAGES: ['ANTHROPIC_MESSAGES_AGENT']
  };
  const availableCapabilities = new Set(
    (Array.isArray(workerPool?.nodes) ? workerPool.nodes : [])
      .filter(node => node?.online === true && text(node?.state).toUpperCase() !== 'DRAINING')
      .flatMap(node => Array.isArray(node?.capabilities) ? node.capabilities : [])
      .map(value => text(value).toUpperCase())
  );
  return protocols.map(value => {
    const supported = (capabilityByProtocol[value] || []).some(
      capability => availableCapabilities.has(capability)
    );
    return {
      value,
      label: labels.get(value) || value,
      disabled: !supported,
      reason: supported ? null : `当前在线 Worker 未提供 ${capabilityByProtocol[value]?.[0] || value}`
    };
  });
}

export function normalizeReviewModelPresets(raw, reviewType) {
  const items = Array.isArray(raw) ? raw : (Array.isArray(raw?.items) ? raw.items : []);
  const expectedType = text(reviewType).toUpperCase();
  return items.flatMap(item => {
    const presetCode = text(item?.presetCode).toUpperCase();
    if (!presetCode || text(item?.reviewType).toUpperCase() !== expectedType) return [];
    return [{
      presetCode,
      reviewType: expectedType,
      vendorCode: text(item?.vendorCode).toUpperCase(),
      vendorName: text(item?.vendorName) || presetCode,
      custom: item?.custom === true,
      variants: (Array.isArray(item?.variants) ? item.variants : []).flatMap(variant => {
        const protocol = text(variant?.protocol).toUpperCase();
        if (!protocol) return [];
        const models = Array.from(new Set(
          (Array.isArray(variant?.models) ? variant.models : [])
            .map(text)
            .filter(Boolean)
        ));
        return [{
          protocol,
          baseUrl: text(variant?.baseUrl),
          models,
          defaultModel: text(variant?.defaultModel) || models[0] || '',
          reasoningEfforts: (Array.isArray(variant?.reasoningEfforts)
            ? variant.reasoningEfforts
            : []).map(text).filter(value => reasoningEffortOptions.includes(value)),
          defaultReasoningEffort: text(variant?.defaultReasoningEffort) || null
        }];
      })
    }];
  });
}

export function presetForDraft(presets, draft) {
  return (Array.isArray(presets) ? presets : []).find(
    item => item.presetCode === text(draft?.presetCode).toUpperCase()
  ) || null;
}

export function variantForDraft(preset, draft) {
  return preset?.variants?.find(
    item => item.protocol === text(draft?.protocol).toUpperCase()
  ) || null;
}

export function createReviewModelConnectionDraft(reviewType, presets, presetCode = null) {
  const items = Array.isArray(presets) ? presets : [];
  const preset = items.find(item => item.presetCode === text(presetCode).toUpperCase())
    || items[0]
    || null;
  const variant = preset?.variants?.[0] || null;
  return {
    reviewType,
    presetCode: preset?.presetCode || '',
    protocol: variant?.protocol || '',
    baseUrl: variant?.baseUrl || '',
    model: variant?.defaultModel || '',
    reasoningEffort: variant?.defaultReasoningEffort || null,
    apiKey: '',
    tlsVerify: true
  };
}

export function applyReviewModelPreset(draft, presets, presetCode) {
  return createReviewModelConnectionDraft(
    draft?.reviewType || agentReviewConnection,
    presets,
    presetCode
  );
}

export function applyReviewModelVariant(draft, preset, protocol) {
  const normalizedProtocol = text(protocol).toUpperCase();
  const variant = preset?.variants?.find(item => item.protocol === normalizedProtocol) || null;
  return {
    ...draft,
    protocol: normalizedProtocol,
    baseUrl: variant?.baseUrl || '',
    model: variant?.defaultModel || '',
    reasoningEffort: variant?.defaultReasoningEffort || null
  };
}

export function draftReasoningEfforts(preset, draft) {
  const variant = variantForDraft(preset, draft);
  if (variant) return variant.reasoningEfforts;
  return ['OPENAI_RESPONSES', 'ANTHROPIC_COMPATIBLE'].includes(text(draft?.protocol).toUpperCase())
    ? [...reasoningEffortOptions]
    : [];
}

export function draftModelOptions(preset, draft) {
  return (variantForDraft(preset, draft)?.models || []).map(model => ({
    value: model,
    label: model
  }));
}

export function validateReviewModelConnectionDraft(draft, presets) {
  const preset = presetForDraft(presets, draft);
  if (!preset) return '请选择供应商';
  const protocol = text(draft?.protocol).toUpperCase();
  if (!protocol) return '请选择协议';
  const knownProtocols = connectionProtocolOptions(draft?.reviewType).map(item => item.value);
  if (!knownProtocols.includes(protocol)) return '请选择受支持的协议';
  if (!preset.custom && !preset.variants.some(item => item.protocol === protocol)) {
    return '当前协议不属于所选供应商';
  }
  const baseUrl = text(draft?.baseUrl);
  if (!baseUrl) return '请填写 Base URL';
  if (baseUrl.length > 1024) return 'Base URL 最多 1024 个字符';
  if (!baseUrl.toLowerCase().startsWith('https://')) return 'Base URL 必须使用 HTTPS';
  const model = text(draft?.model);
  if (!model) return '请填写模型';
  if (model.length > 128) return '模型最多 128 个字符';
  const efforts = draftReasoningEfforts(preset, draft);
  const reasoningEffort = text(draft?.reasoningEffort);
  if (efforts.length && !efforts.includes(reasoningEffort)) return '请选择受支持的推理强度';
  if (!efforts.length && reasoningEffort) return '当前协议不支持推理强度';
  const apiKey = text(draft?.apiKey);
  if (!apiKey) return 'API Key 为必填项';
  if (apiKey.length > (draft?.reviewType === standardReviewConnection ? 1024 : 4096)) {
    return `API Key 最多 ${draft?.reviewType === standardReviewConnection ? 1024 : 4096} 个字符`;
  }
  return null;
}

export function buildReviewModelConnectionRequest(draft) {
  const request = {
    reviewType: text(draft?.reviewType).toUpperCase(),
    presetCode: text(draft?.presetCode).toUpperCase(),
    protocol: text(draft?.protocol).toUpperCase(),
    baseUrl: text(draft?.baseUrl),
    model: text(draft?.model),
    apiKey: text(draft?.apiKey),
    tlsVerify: draft?.tlsVerify !== false
  };
  const reasoningEffort = text(draft?.reasoningEffort);
  if (reasoningEffort) request.reasoningEffort = reasoningEffort;
  return request;
}

export function reviewModelConnectionDraftHasInput(draft, presets) {
  if (text(draft?.apiKey)) return true;
  const baseline = createReviewModelConnectionDraft(
    draft?.reviewType,
    presets,
    draft?.presetCode
  );
  return ['protocol', 'baseUrl', 'model', 'reasoningEffort', 'tlsVerify'].some(
    key => (draft?.[key] ?? null) !== (baseline?.[key] ?? null)
  );
}
