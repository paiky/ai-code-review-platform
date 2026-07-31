import assert from 'node:assert/strict';
import test from 'node:test';

import { loadRuntimeSnapshot } from '../src/command-center/commandCenterApi.js';


test('requests enough active flows for the Phase 2D overflow aggregation', async () => {
  const originalFetch = globalThis.fetch;
  let requestedUrl = '';
  globalThis.fetch = async url => {
    requestedUrl = String(url);
    return {
      ok: true,
      status: 200,
      text: async () => JSON.stringify({ success: true, data: { activeFlows: [] } })
    };
  };

  try {
    await loadRuntimeSnapshot();
  } finally {
    globalThis.fetch = originalFetch;
  }

  const query = new URL(requestedUrl, 'http://localhost').searchParams;
  assert.equal(query.get('windowHours'), '24');
  assert.equal(query.get('activeLimit'), '50');
  assert.equal(query.get('alertLimit'), '20');
});
