import assert from 'node:assert/strict';
import test from 'node:test';

import {
  agentReviewConnection,
  buildReviewModelConnectionCatalog,
  connectionConfigurationStatus,
  resolveReviewModelConnectionSelection,
  standardReviewConnection
} from '../src/reviewModelConnections.js';

function fixtures() {
  return {
    defaultProviderCode: 'deepseek',
    agentSettings: {
      enabled: true,
      selectedRuntime: 'OPENAI_RESPONSES_CUSTOM',
      updatedAt: '2026-08-08T08:00:00Z',
      runtimeOptions: [
        { value: 'CLAUDE_CODE_DEEPSEEK', label: 'Claude Code + DeepSeek', isDefault: true },
        { value: 'OPENAI_RESPONSES_CUSTOM', label: 'Responses Relay', isDefault: false }
      ],
      defaultRuntime: {
        endpoint: 'https://agent.example/v1',
        model: 'deepseek-v4-pro[1m]',
        apiKeyConfigured: true,
        apiKeyMasked: 'agent...mask',
        apiKey: 'AGENT_DEFAULT_SECRET'
      },
      customRuntime: {
        displayName: 'Review Relay',
        protocol: 'OPENAI_RESPONSES',
        baseUrl: 'https://relay.example/v1',
        model: 'gpt-5.6-sol',
        apiKeyConfigured: true,
        apiKeyMasked: 'relay...mask',
        apiKey: 'AGENT_CUSTOM_SECRET',
        configurationComplete: true,
        workerSupported: true
      }
    },
    agentRuntimes: [
      {
        runtimeCode: 'CLAUDE_CODE_DEEPSEEK',
        displayName: 'Claude Code + DeepSeek',
        protocol: 'ANTHROPIC_COMPATIBLE',
        baseUrl: 'https://agent.example/v1',
        model: 'deepseek-v4-pro[1m]',
        enabled: true,
        builtIn: true,
        selected: false,
        apiKeyConfigured: true,
        configurationComplete: true,
        protocolAvailable: true,
        updatedAt: '2026-08-08T08:00:00Z'
      },
      {
        runtimeCode: 'TEAM_RELAY',
        displayName: 'Review Relay',
        protocol: 'OPENAI_RESPONSES',
        baseUrl: 'https://relay.example/v1',
        model: 'gpt-5.6-sol',
        enabled: true,
        builtIn: false,
        selected: true,
        apiKeyConfigured: true,
        configurationComplete: true,
        protocolAvailable: true,
        configurationTest: { status: 'SUCCESS' },
        updatedAt: '2026-08-08T08:01:00Z'
      }
    ],
    providers: [
      {
        providerCode: 'DEEPSEEK',
        providerName: 'DeepSeek V4 Pro',
        providerType: 'OPENAI_CHAT_COMPATIBLE',
        endpointUrl: 'https://api.deepseek.com',
        modelName: 'deepseek-v4-pro',
        enabled: true,
        defaultProvider: true,
        apiKeyConfigured: true,
        apiKeyMasked: 'std...mask',
        apiKey: 'STANDARD_SECRET',
        updatedAt: '2026-08-08T08:05:00Z'
      },
      {
        providerCode: 'ANTHROPIC',
        providerName: 'Claude',
        providerType: 'ANTHROPIC_MESSAGES',
        endpointUrl: 'https://api.anthropic.com/v1',
        modelName: 'claude-sonnet',
        enabled: false,
        apiKeyConfigured: true,
        updatedAt: '2026-08-08T08:06:00Z'
      }
    ]
  };
}

test('maps Agent runtimes before Standard providers with stable domain IDs', () => {
  const rows = buildReviewModelConnectionCatalog(fixtures());

  assert.deepEqual(rows.map(item => item.id), [
    'AGENT:CLAUDE_CODE_DEEPSEEK',
    'AGENT:TEAM_RELAY',
    'STANDARD:DEEPSEEK',
    'STANDARD:ANTHROPIC'
  ]);
  assert.deepEqual(rows.map(item => item.reviewType), [
    agentReviewConnection,
    agentReviewConnection,
    standardReviewConnection,
    standardReviewConnection
  ]);

  const custom = rows[1];
  assert.equal(custom.name, 'Review Relay');
  assert.equal(custom.protocol, 'OPENAI_RESPONSES');
  assert.equal(custom.endpoint, 'https://relay.example/v1');
  assert.equal(custom.isCurrent, true);
  assert.equal(custom.workerSupported, true);
  assert.equal(custom.updatedAt, '2026-08-08T08:01:00Z');

  const standard = rows[2];
  assert.equal(standard.name, 'DeepSeek V4 Pro');
  assert.equal(standard.isDefault, true);
  assert.equal(standard.isCurrent, true);
  assert.equal(standard.configurationStatus, connectionConfigurationStatus.READY);
});

test('uses the explicit Settings default instead of a stale Provider flag', () => {
  const input = fixtures();
  input.defaultProviderCode = 'ANTHROPIC';

  const rows = buildReviewModelConnectionCatalog(input);
  assert.equal(rows.find(item => item.id === 'STANDARD:DEEPSEEK').isDefault, false);
  assert.equal(rows.find(item => item.id === 'STANDARD:ANTHROPIC').isDefault, true);
});

test('derives truthful incomplete disabled and worker-unsupported states', () => {
  const input = fixtures();
  input.agentRuntimes[0].configurationComplete = false;
  input.agentRuntimes[1].protocolAvailable = false;
  input.providers[0].modelName = '';

  const rows = buildReviewModelConnectionCatalog(input);
  assert.equal(rows[0].configurationStatus, connectionConfigurationStatus.INCOMPLETE);
  assert.equal(rows[1].configurationStatus, connectionConfigurationStatus.WORKER_UNSUPPORTED);
  assert.equal(rows[2].configurationStatus, connectionConfigurationStatus.INCOMPLETE);
  assert.equal(rows[3].configurationStatus, connectionConfigurationStatus.DISABLED);
});

test('hides never-configured Standard placeholders and keeps cleared connections unavailable', () => {
  const input = fixtures();
  input.providers.push({
    providerCode: 'GLM',
    providerName: 'GLM placeholder',
    catalogVisible: false,
    apiKeyConfigured: false
  });
  input.providers[0].apiKeyConfigured = false;
  input.providers[0].enabled = false;

  const rows = buildReviewModelConnectionCatalog(input);
  assert.equal(rows.some(item => item.id === 'STANDARD:GLM'), false);
  assert.equal(
    rows.find(item => item.id === 'STANDARD:DEEPSEEK').configurationStatus,
    connectionConfigurationStatus.UNAVAILABLE
  );
  assert.equal(rows.find(item => item.id === 'STANDARD:DEEPSEEK').isDefault, true);
});

test('keeps only safe catalog fields and never serializes key material', () => {
  const rows = buildReviewModelConnectionCatalog(fixtures());
  const serialized = JSON.stringify(rows);

  assert.equal(serialized.includes('AGENT_DEFAULT_SECRET'), false);
  assert.equal(serialized.includes('AGENT_CUSTOM_SECRET'), false);
  assert.equal(serialized.includes('STANDARD_SECRET'), false);
  assert.equal(serialized.includes('agent...mask'), false);
  assert.equal(serialized.includes('relay...mask'), false);
  assert.equal(serialized.includes('std...mask'), false);
  assert.equal(Object.hasOwn(rows[0], 'apiKey'), false);
  assert.equal(Object.hasOwn(rows[0], 'apiKeyMasked'), false);
});

test('preserves provider order, normalizes IDs, and ignores invalid or duplicate codes', () => {
  const input = fixtures();
  input.providers = [
    input.providers[1],
    { ...input.providers[0], providerCode: ' deepseek ' },
    { ...input.providers[0], providerCode: 'DEEPSEEK', providerName: 'Duplicate' },
    { providerName: 'Missing code' }
  ];

  const rows = buildReviewModelConnectionCatalog(input);
  assert.deepEqual(rows.slice(2).map(item => item.id), [
    'STANDARD:ANTHROPIC',
    'STANDARD:DEEPSEEK'
  ]);
  assert.equal(rows[3].name, 'DeepSeek V4 Pro');
});

test('selects the previous row, then Standard default, Agent current, and finally first row', () => {
  const rows = buildReviewModelConnectionCatalog(fixtures());
  assert.equal(
    resolveReviewModelConnectionSelection(rows, 'STANDARD:ANTHROPIC'),
    'STANDARD:ANTHROPIC'
  );
  assert.equal(
    resolveReviewModelConnectionSelection(rows, 'STANDARD:REMOVED'),
    'STANDARD:DEEPSEEK'
  );

  const withoutDefault = rows.filter(item => item.reviewType === agentReviewConnection);
  assert.equal(
    resolveReviewModelConnectionSelection(withoutDefault, 'STANDARD:REMOVED'),
    'AGENT:TEAM_RELAY'
  );

  const noCurrent = withoutDefault.map(item => ({ ...item, isCurrent: false }));
  assert.equal(resolveReviewModelConnectionSelection(noCurrent), 'AGENT:CLAUDE_CODE_DEEPSEEK');
  assert.equal(resolveReviewModelConnectionSelection([]), null);
});

test('returns safe Agent placeholders when responses are missing', () => {
  const rows = buildReviewModelConnectionCatalog();

  assert.equal(rows.length, 2);
  assert.equal(rows[0].isCurrent, true);
  assert.equal(rows[0].endpoint, null);
  assert.equal(rows[0].configurationStatus, connectionConfigurationStatus.UNAVAILABLE);
  assert.equal(rows[1].workerSupported, null);
});

test('uses explicit dynamic selected flags instead of the legacy projected setting', () => {
  const input = fixtures();
  input.agentSettings.selectedRuntime = 'DAMAGED_RUNTIME';

  const rows = buildReviewModelConnectionCatalog(input);
  assert.equal(rows[0].isCurrent, false);
  assert.equal(rows[1].isCurrent, true);
});
