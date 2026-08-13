import assert from 'node:assert/strict';
import test from 'node:test';

import {
  buildCreateProviderRequest,
  createProviderDraft,
  matchesProviderDeleteConfirmation,
  normalizeProviderCode,
  providerDeleteAvailability,
  validateCreateProviderDraft
} from '../src/providerLifecycle.js';

test('normalizes and builds the explicit Provider create request', () => {
  const draft = {
    ...createProviderDraft(),
    providerCode: ' team_gateway ',
    providerName: ' Team Gateway ',
    endpointUrl: ' https://safe.invalid/v1 ',
    modelName: ' review-model ',
    timeoutSeconds: 120,
    apiKey: ' local-secret '
  };

  assert.equal(validateCreateProviderDraft(draft), null);
  assert.deepEqual(buildCreateProviderRequest(draft), {
    providerCode: 'TEAM_GATEWAY',
    providerName: 'Team Gateway',
    providerType: 'OPENAI_CHAT_COMPATIBLE',
    endpointUrl: 'https://safe.invalid/v1',
    modelName: 'review-model',
    timeoutSeconds: 120,
    apiKey: 'local-secret'
  });
});

test('validates code, protocol and timeout without a Provider enable gate', () => {
  const base = { ...createProviderDraft(), providerCode: 'CUSTOM', providerName: 'Custom' };
  assert.match(validateCreateProviderDraft({ ...base, providerCode: '1bad' }), /Provider Code/);
  assert.match(validateCreateProviderDraft({ ...base, providerType: 'UNKNOWN' }), /协议/);
  assert.match(validateCreateProviderDraft({ ...base, timeoutSeconds: 3601 }), /超时/);
  assert.equal(validateCreateProviderDraft({ ...base, enabled: false }), null);
  assert.equal(Object.hasOwn(buildCreateProviderRequest(base), 'enabled'), false);
});

test('exposes delete only for custom non-default Providers', () => {
  assert.equal(providerDeleteAvailability({ builtIn: true }).visible, false);
  assert.deepEqual(providerDeleteAvailability({ builtIn: false, defaultProvider: true }), {
    visible: true,
    disabled: true,
    reason: 'Standard 默认 Provider 不可删除'
  });
  assert.deepEqual(providerDeleteAvailability({ builtIn: false, defaultProvider: false }), {
    visible: true,
    disabled: false,
    reason: null
  });
});

test('requires the complete normalized Provider Code before deletion', () => {
  assert.equal(normalizeProviderCode(' custom_team '), 'CUSTOM_TEAM');
  assert.equal(matchesProviderDeleteConfirmation('CUSTOM_TEAM', 'CUSTOM_TEAM'), true);
  assert.equal(matchesProviderDeleteConfirmation('CUSTOM_TEAM', 'custom_team'), false);
  assert.equal(matchesProviderDeleteConfirmation('CUSTOM_TEAM', 'CUSTOM'), false);
});
