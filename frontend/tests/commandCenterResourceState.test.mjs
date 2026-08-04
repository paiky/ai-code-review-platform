import assert from 'node:assert/strict';
import test from 'node:test';

import {
  createSnapshotResourceState,
  presentSnapshotResource,
  reduceSnapshotResourceState
} from '../src/command-center/commandCenterResourceState.js';


test('resource transitions distinguish loading, success and empty failure', () => {
  const initial = createSnapshotResourceState();
  assert.deepEqual(initial, {
    data: null,
    loading: true,
    error: '',
    updatedAt: null
  });

  const failed = reduceSnapshotResourceState(initial, {
    type: 'LOAD_FAILED',
    error: new Error('HTTP 503'),
    staleAfterMs: 15_000,
    now: Date.parse('2026-08-04T10:00:00Z')
  });
  assert.equal(failed.data, null);
  assert.equal(failed.loading, false);
  assert.equal(failed.error, 'HTTP 503');
  assert.deepEqual(presentSnapshotResource(failed), {
    state: 'ERROR_EMPTY',
    freshness: 'EMPTY',
    available: false,
    retained: false,
    loading: false,
    generatedAt: null,
    error: 'HTTP 503',
    schemaCompatible: null,
    truncated: false
  });
});


test('failed refresh retains the last snapshot and recomputes freshness', () => {
  const loaded = reduceSnapshotResourceState(createSnapshotResourceState(), {
    type: 'LOAD_SUCCEEDED',
    data: {
      generatedAt: '2026-08-04T09:59:00Z',
      freshness: 'FRESH',
      schemaCompatible: true,
      coverage: { truncated: true }
    },
    updatedAt: '2026-08-04T09:59:01Z'
  });
  const loading = reduceSnapshotResourceState(loaded, { type: 'LOAD_STARTED' });
  assert.equal(loading.data, loaded.data);
  assert.equal(loading.loading, true);

  const retained = reduceSnapshotResourceState(loading, {
    type: 'LOAD_FAILED',
    error: 'network unavailable',
    staleAfterMs: 15_000,
    now: Date.parse('2026-08-04T10:00:00Z')
  });
  assert.equal(retained.data.freshness, 'STALE');
  assert.equal(retained.updatedAt, '2026-08-04T09:59:01Z');
  assert.deepEqual(presentSnapshotResource(retained), {
    state: 'ERROR_RETAINED',
    freshness: 'STALE',
    available: true,
    retained: true,
    loading: false,
    generatedAt: '2026-08-04T09:59:00Z',
    error: 'network unavailable',
    schemaCompatible: true,
    truncated: true
  });
});


test('successful retry replaces retained data and clears its error', () => {
  const retained = {
    data: { generatedAt: '2026-08-04T09:59:00Z', freshness: 'STALE' },
    loading: true,
    error: 'previous failure',
    updatedAt: '2026-08-04T09:59:01Z'
  };
  const recovered = reduceSnapshotResourceState(retained, {
    type: 'LOAD_SUCCEEDED',
    data: { generatedAt: '2026-08-04T10:00:00Z', freshness: 'FRESH' },
    updatedAt: '2026-08-04T10:00:01Z'
  });
  assert.equal(recovered.error, '');
  assert.equal(recovered.loading, false);
  assert.equal(recovered.data.freshness, 'FRESH');
  assert.equal(presentSnapshotResource(recovered).state, 'FRESH');
});
