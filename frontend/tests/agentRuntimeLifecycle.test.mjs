import assert from 'node:assert/strict';
import test from 'node:test';

import {
  agentProtocolOptions,
  agentProtocolOptionsForWorkerPool,
  agentRuntimeDeleteAvailability,
  buildCreateAgentRuntimeRequest,
  buildTestAgentRuntimeRequest,
  buildUpdateAgentRuntimeRequest,
  createAgentRuntimeDraft,
  matchesAgentRuntimeDeleteConfirmation,
  normalizeAgentRuntimeCode,
  validateAgentRuntimeDraft
} from '../src/agentRuntimeLifecycle.js';

test('creates a safe Responses draft and opens only production-ready protocols', () => {
  assert.deepEqual(createAgentRuntimeDraft(), {
    runtimeCode: '',
    displayName: '',
    protocol: 'OPENAI_RESPONSES',
    baseUrl: '',
    model: 'gpt-5.6-sol',
    reasoningEffort: 'high',
    tlsVerify: true,
    apiKey: '',
    enabled: false
  });
  assert.deepEqual(agentProtocolOptions.map(item => item.disabled), [false, false, false]);
  assert.equal(agentProtocolOptions[1].reason, null);
});

test('opens Chat creation only for a capable online non-draining Worker', () => {
  const unavailable = agentProtocolOptionsForWorkerPool({ nodes: [] });
  assert.equal(unavailable[1].disabled, true);
  assert.match(unavailable[1].reason, /OPENAI_CHAT_AGENT/);

  const available = agentProtocolOptionsForWorkerPool({
    nodes: [{
      online: true,
      state: 'IDLE',
      capabilities: ['OPENAI_CHAT_AGENT']
    }]
  });
  assert.equal(available[1].disabled, false);
  assert.equal(available[1].reason, null);

  const draining = agentProtocolOptionsForWorkerPool({
    nodes: [{
      online: true,
      state: 'DRAINING',
      capabilities: ['OPENAI_CHAT_AGENT']
    }]
  });
  assert.equal(draining[1].disabled, true);
});

test('opens Anthropic creation only for a capable online non-draining Worker', () => {
  const unavailable = agentProtocolOptionsForWorkerPool({ nodes: [] });
  assert.equal(unavailable[2].disabled, true);
  assert.match(unavailable[2].reason, /ANTHROPIC_MESSAGES_AGENT/);

  const available = agentProtocolOptionsForWorkerPool({
    nodes: [{
      online: true,
      state: 'BUSY',
      capabilities: ['ANTHROPIC_MESSAGES_AGENT']
    }]
  });
  assert.equal(available[2].disabled, false);
  assert.equal(available[2].reason, null);
});

test('validates and builds create and update requests without inventing a runner', () => {
  const draft = {
    ...createAgentRuntimeDraft(),
    runtimeCode: ' team_relay ',
    displayName: ' Team Relay ',
    baseUrl: ' https://relay.example/v1 ',
    apiKey: ' secret ',
    enabled: true
  };
  assert.equal(validateAgentRuntimeDraft(draft, { creating: true }), null);
  assert.equal(normalizeAgentRuntimeCode(draft.runtimeCode), 'TEAM_RELAY');
  const created = buildCreateAgentRuntimeRequest(draft);
  assert.equal(created.runtimeCode, 'TEAM_RELAY');
  assert.equal(created.apiKey, 'secret');
  assert.equal(Object.hasOwn(created, 'runnerType'), false);
  const updated = buildUpdateAgentRuntimeRequest({ ...draft, apiKey: '' });
  assert.equal(Object.hasOwn(updated, 'apiKey'), false);
  assert.equal(Object.hasOwn(updated, 'runtimeCode'), false);
  assert.equal(updated.enabled, true);
  assert.deepEqual(buildTestAgentRuntimeRequest(draft), {
    baseUrl: 'https://relay.example/v1',
    model: 'gpt-5.6-sol',
    reasoningEffort: 'high',
    tlsVerify: true,
    apiKey: 'secret'
  });
});

test('rejects invalid, unavailable and incomplete Runtime drafts', () => {
  const base = createAgentRuntimeDraft();
  assert.match(validateAgentRuntimeDraft(base, { creating: true }), /Runtime Code/);
  assert.match(validateAgentRuntimeDraft({ ...base, runtimeCode: 'VALID' }, { creating: true }), /配置名称/);
  assert.equal(validateAgentRuntimeDraft({
    ...base,
    runtimeCode: 'VALID',
    displayName: 'Valid',
    protocol: 'ANTHROPIC_MESSAGES',
    baseUrl: 'https://relay.example/v1',
    model: 'claude-sonnet',
    apiKey: 'secret'
  }, { creating: true }), null);

  const chat = {
    ...base,
    runtimeCode: 'CHAT_AGENT',
    displayName: 'Chat Agent',
    protocol: 'OPENAI_CHAT_COMPLETIONS',
    baseUrl: 'https://relay.example/v1',
    model: 'chat-model',
    apiKey: 'secret'
  };
  assert.equal(validateAgentRuntimeDraft(chat, { creating: true }), null);
  assert.equal(Object.hasOwn(buildCreateAgentRuntimeRequest(chat), 'reasoningEffort'), false);
});

test('protects built-in, current and testing runtimes from deletion', () => {
  assert.equal(agentRuntimeDeleteAvailability({ builtIn: true }).visible, false);
  assert.equal(agentRuntimeDeleteAvailability({ builtIn: false, selected: true }).disabled, true);
  assert.equal(agentRuntimeDeleteAvailability({
    builtIn: false,
    selected: false,
    configurationTest: { status: 'RUNNING' }
  }).disabled, true);
  assert.equal(agentRuntimeDeleteAvailability({ builtIn: false, selected: false }).disabled, false);
  assert.equal(matchesAgentRuntimeDeleteConfirmation('team_relay', 'TEAM_RELAY'), true);
});
