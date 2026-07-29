import test from 'node:test';
import assert from 'node:assert/strict';

import {
  formatWorkerActivity,
  normalizeAgentWorkerPool,
  workerStateColor,
  workerStateLabel
} from '../src/agentWorkerPool.js';

test('normalizes registered worker pool counts and safe node fields', () => {
  const pool = normalizeAgentWorkerPool({
    workerStatus: 'ONLINE',
    workerPool: {
      onlineCount: 2,
      busyCount: 1,
      idleCount: 1,
      drainingCount: 0,
      totalCapacity: 2,
      totalCount: 2,
      nodes: [
        {
          workerId: 'agent-worker-a',
          workerVersion: 'worker-v2',
          cliVersion: '2.1.112',
          state: 'BUSY',
          capacity: 1,
          activeJobId: 8,
          activeRunId: 9,
          lastHeartbeatAt: '2026-07-29T12:00:00Z',
          online: true,
          source: 'SECRET_SOURCE'
        },
        {
          workerId: 'agent-worker-b',
          state: 'IDLE',
          capacity: 1,
          online: true
        }
      ]
    }
  });

  assert.equal(pool.status, 'ONLINE');
  assert.equal(pool.onlineCount, 2);
  assert.equal(pool.totalCapacity, 2);
  assert.equal(formatWorkerActivity(pool.nodes[0]), 'Job #8 / Run #9');
  assert.equal(JSON.stringify(pool).includes('SECRET_SOURCE'), false);
  assert.deepEqual(Object.keys(pool.nodes[0]), [
    'workerId',
    'workerVersion',
    'cliVersion',
    'state',
    'capacity',
    'activeJobId',
    'activeRunId',
    'startedAt',
    'lastHeartbeatAt',
    'online',
    'legacy'
  ]);
});

test('keeps legacy singleton worker settings visible without registration rows', () => {
  const pool = normalizeAgentWorkerPool({
    workerStatus: 'ONLINE',
    workerId: 'legacy-worker-1',
    workerVersion: 'legacy-v1',
    cliVersion: '2.1.112',
    lastWorkerHeartbeatAt: '2026-07-29T12:00:00Z',
    workerPool: {
      onlineCount: 0,
      busyCount: 0,
      idleCount: 0,
      totalCapacity: 0,
      totalCount: 0,
      nodes: []
    }
  });

  assert.equal(pool.status, 'ONLINE');
  assert.equal(pool.onlineCount, 1);
  assert.equal(pool.totalCapacity, 1);
  assert.equal(pool.nodes[0].legacy, true);
});

test('formats worker states and never exposes activity for idle nodes', () => {
  assert.equal(workerStateLabel('IDLE'), '空闲');
  assert.equal(workerStateLabel('BUSY'), '忙碌');
  assert.equal(workerStateLabel('DRAINING'), '排空中');
  assert.equal(workerStateColor('BUSY', true), 'blue');
  assert.equal(workerStateColor('BUSY', false), 'default');
  assert.equal(formatWorkerActivity({ state: 'IDLE', activeJobId: 1 }), '-');
  assert.equal(formatWorkerActivity({ state: 'BUSY' }), '配置测试或任务启动中');
});
