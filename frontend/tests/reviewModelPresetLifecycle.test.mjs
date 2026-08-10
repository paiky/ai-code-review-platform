import assert from 'node:assert/strict';
import test from 'node:test';

import {
  applyReviewModelPreset,
  applyReviewModelVariant,
  buildReviewModelConnectionRequest,
  createReviewModelConnectionDraft,
  draftModelOptions,
  draftReasoningEfforts,
  normalizeReviewModelPresets,
  presetProtocolOptions,
  reviewModelConnectionDraftHasInput,
  validateReviewModelConnectionDraft
} from '../src/reviewModelPresetLifecycle.js';

const rawPresets = [
  {
    presetCode: 'STANDARD_OPENAI',
    reviewType: 'STANDARD',
    vendorCode: 'OPENAI',
    vendorName: 'OpenAI',
    custom: false,
    variants: [{
      protocol: 'OPENAI_RESPONSES',
      baseUrl: 'https://safe.invalid/v1/responses',
      models: ['gpt-5.6-sol'],
      defaultModel: 'gpt-5.6-sol',
      reasoningEfforts: ['low', 'medium', 'high'],
      defaultReasoningEffort: 'high'
    }]
  },
  {
    presetCode: 'STANDARD_CUSTOM',
    reviewType: 'STANDARD',
    vendorCode: 'CUSTOM',
    vendorName: '自定义',
    custom: true,
    variants: []
  }
];

test('normalizes presets and fills protocol URL model and reasoning from Backend data', () => {
  const presets = normalizeReviewModelPresets(rawPresets, 'STANDARD');
  const draft = createReviewModelConnectionDraft('STANDARD', presets);

  assert.deepEqual(draft, {
    reviewType: 'STANDARD',
    presetCode: 'STANDARD_OPENAI',
    protocol: 'OPENAI_RESPONSES',
    baseUrl: 'https://safe.invalid/v1/responses',
    model: 'gpt-5.6-sol',
    reasoningEffort: 'high',
    apiKey: '',
    tlsVerify: true
  });
  assert.deepEqual(draftModelOptions(presets[0], draft), [
    { value: 'gpt-5.6-sol', label: 'gpt-5.6-sol' }
  ]);
  assert.deepEqual(draftReasoningEfforts(presets[0], draft), ['low', 'medium', 'high']);
});

test('gates Agent preset protocols by online non-draining Worker capabilities', () => {
  const preset = {
    custom: false,
    variants: [{ protocol: 'ANTHROPIC_COMPATIBLE' }]
  };
  assert.equal(presetProtocolOptions(preset, 'AGENT', { nodes: [] })[0].disabled, true);
  assert.equal(presetProtocolOptions(preset, 'AGENT', {
    nodes: [{ online: true, state: 'IDLE', capabilities: ['CLAUDE_CODE'] }]
  })[0].disabled, false);
  assert.equal(presetProtocolOptions(preset, 'AGENT', {
    nodes: [{ online: true, state: 'DRAINING', capabilities: ['CLAUDE_CODE'] }]
  })[0].disabled, true);
});

test('switching supplier and variant clears stale dependent values', () => {
  const presets = normalizeReviewModelPresets(rawPresets, 'STANDARD');
  const populated = { ...createReviewModelConnectionDraft('STANDARD', presets), apiKey: 'secret' };
  const custom = applyReviewModelPreset(populated, presets, 'STANDARD_CUSTOM');
  assert.equal(custom.protocol, '');
  assert.equal(custom.baseUrl, '');
  assert.equal(custom.model, '');
  assert.equal(custom.reasoningEffort, null);
  assert.equal(custom.apiKey, '');

  const restored = applyReviewModelVariant(custom, presets[0], 'OPENAI_RESPONSES');
  assert.equal(restored.baseUrl, 'https://safe.invalid/v1/responses');
  assert.equal(restored.model, 'gpt-5.6-sol');
});

test('requires key and builds only the unified public contract', () => {
  const presets = normalizeReviewModelPresets(rawPresets, 'STANDARD');
  const draft = createReviewModelConnectionDraft('STANDARD', presets);
  assert.match(validateReviewModelConnectionDraft(draft, presets), /API Key/);

  const complete = { ...draft, apiKey: ' local-secret ', tlsVerify: false };
  assert.equal(validateReviewModelConnectionDraft(complete, presets), null);
  assert.deepEqual(buildReviewModelConnectionRequest(complete), {
    reviewType: 'STANDARD',
    presetCode: 'STANDARD_OPENAI',
    protocol: 'OPENAI_RESPONSES',
    baseUrl: 'https://safe.invalid/v1/responses',
    model: 'gpt-5.6-sol',
    reasoningEffort: 'high',
    apiKey: 'local-secret',
    tlsVerify: false
  });
  assert.equal(reviewModelConnectionDraftHasInput(draft, presets), false);
  assert.equal(reviewModelConnectionDraftHasInput(complete, presets), true);
});
