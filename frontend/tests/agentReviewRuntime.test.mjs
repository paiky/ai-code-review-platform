import assert from 'node:assert/strict';
import test from 'node:test';

import {
  agentConfigurationTestPollTimeoutMs,
  buildAgentSettingsPayload,
  customAgentRuntime,
  defaultAgentRuntime,
  normalizeAgentRuntimeDraft,
  validateAgentRuntimeDraft
} from '../src/agentReviewRuntime.js';

test('limits the settings-page configuration test wait to 120 seconds', () => {
  assert.equal(agentConfigurationTestPollTimeoutMs, 120_000);
});

test('keeps Claude and DeepSeek as the backward-compatible default', () => {
  const draft = normalizeAgentRuntimeDraft({ enabled: true, apiKeyConfigured: true });
  assert.equal(draft.selectedRuntime, defaultAgentRuntime);
  assert.equal(draft.apiKey, '');
  assert.equal(draft.customRuntime.model, 'gpt-5.6-sol');
  assert.equal(draft.customRuntime.tlsVerify, true);
});

test('normalizes and validates a custom Responses runtime draft', () => {
  const settings = {
    selectedRuntime: customAgentRuntime,
    customRuntime: {
      displayName: 'Relay',
      baseUrl: 'https://relay.example/v1',
      model: 'gpt-5.6-sol',
      reasoningEffort: 'high',
      tlsVerify: false,
      apiKeyConfigured: true
    }
  };
  const draft = normalizeAgentRuntimeDraft(settings);
  assert.equal(draft.customRuntime.tlsVerify, false);
  assert.equal(validateAgentRuntimeDraft({ ...draft, enabled: true }, settings), null);
  assert.equal(validateAgentRuntimeDraft({
    ...draft,
    enabled: true,
    customRuntime: { ...draft.customRuntime, baseUrl: 'http://127.0.0.1:8080/v1' }
  }, settings), null);
  assert.match(
    validateAgentRuntimeDraft({
      ...draft,
      enabled: true,
      customRuntime: { ...draft.customRuntime, baseUrl: 'ftp://127.0.0.1/v1' }
    }, settings),
    /HTTP 或 HTTPS/
  );
});

test('builds independent key-slot payloads without moving the other key', () => {
  const customDraft = {
    ...normalizeAgentRuntimeDraft({ selectedRuntime: customAgentRuntime }),
    selectedRuntime: customAgentRuntime,
    enabled: true,
    budgets: { maxTurns: 12 },
    customRuntime: {
      displayName: 'Relay',
      baseUrl: 'https://relay.example/v1',
      apiKey: 'custom-secret',
      model: 'gpt-5.6-sol',
      reasoningEffort: 'high',
      tlsVerify: false
    }
  };
  const saved = buildAgentSettingsPayload(customDraft);
  assert.equal(saved.customRuntime.apiKey, 'custom-secret');
  assert.equal(saved.customRuntime.tlsVerify, false);
  assert.equal('apiKey' in saved, false);

  const cleared = buildAgentSettingsPayload(customDraft, { clearKey: true });
  assert.equal(cleared.enabled, false);
  assert.equal(cleared.customRuntime.clearApiKey, true);
  assert.equal('clearApiKey' in cleared, false);
});
