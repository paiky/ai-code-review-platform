import assert from 'node:assert/strict';
import test from 'node:test';

import {
  COMMAND_CENTER_CONNECTIONS,
  measureCommandCenterTopology,
  observeCommandCenterTopology
} from '../src/command-center/commandCenterTopology.js';


test('M2-1 measures six semantic cable paths from real port centers', () => {
  const harness = createHarness();
  const snapshot = measureCommandCenterTopology(harness.container);

  assert.equal(snapshot.ready, true);
  assert.equal(snapshot.width, 1200);
  assert.equal(snapshot.height, 440);
  assert.deepEqual(snapshot.paths.map(path => path.id), COMMAND_CENTER_CONNECTIONS.map(item => item.id));
  assert.deepEqual(snapshot.paths[0].from, { x: 156, y: 220 });
  assert.deepEqual(snapshot.paths[0].to, { x: 244, y: 180 });
  assert.equal(snapshot.paths[0].kind, 'direct');
  assert.equal(snapshot.paths[0].d, 'M 156 220 L 170 220 H 189.2 Q 202 220 202 207.2 V 192.8 Q 202 180 214.8 180 H 234');
  assert.equal(snapshot.paths[1].kind, 'branch');
  assert.match(snapshot.paths[1].d, / Q /);
  assert.equal(snapshot.paths[3].kind, 'result');
  assert.match(snapshot.paths[3].d, / Q /);
  assert.match(snapshot.paths[3].d, / H 1054$/);
  assert.equal(snapshot.paths.some(path => path.d.includes(' C ')), false);
  assert.equal(snapshot.paths.at(-1).token, 'fallback');
  assert.equal(snapshot.paths.at(-1).kind, 'fallback');
  assert.equal(snapshot.paths.at(-1).d, 'M 744 194 L 744 208 V 236');
});


test('M2-1 owns one ResizeObserver, deduplicates unchanged coordinates and disconnects once', () => {
  const harness = createHarness();
  const snapshots = [];
  const owner = observeCommandCenterTopology(
    harness.container,
    snapshot => snapshots.push(snapshot),
    { ResizeObserverClass: harness.ResizeObserverClass }
  );

  assert.equal(harness.observers.length, 1);
  assert.equal(harness.observers[0].observed.length, 6);
  assert.equal(snapshots.length, 1);
  harness.observers[0].callback();
  assert.equal(snapshots.length, 1);

  harness.rects['engine-in'].left += 20;
  harness.observers[0].callback();
  assert.equal(snapshots.length, 2);
  assert.equal(snapshots[1].paths[0].to.x, 264);

  owner.disconnect();
  owner.disconnect();
  assert.equal(harness.observers[0].disconnectCount, 1);
  assert.equal(owner.measure(), false);
  assert.equal(snapshots.length, 2);
});


test('M2-1 hides decorative paths for zero size or missing ports while semantic DOM remains independent', () => {
  const zero = createHarness({ width: 0, height: 0 });
  assert.deepEqual(measureCommandCenterTopology(zero.container), {
    ready: false,
    width: 0,
    height: 0,
    paths: []
  });

  const missing = createHarness();
  delete missing.rects['result-standard-in'];
  assert.equal(measureCommandCenterTopology(missing.container).ready, false);
  assert.deepEqual(measureCommandCenterTopology(missing.container).paths, []);
});


function createHarness({ width = 1200, height = 440 } = {}) {
  const rects = {
    'queue-out': rect(151, 215),
    'engine-in': rect(239, 175),
    'engine-agent-out': rect(385, 112),
    'agent-in': rect(471, 99),
    'engine-standard-out': rect(385, 318),
    'standard-in': rect(471, 331),
    'agent-out': rect(990, 99),
    'result-agent-in': rect(1059, 120),
    'standard-out': rect(990, 331),
    'result-standard-in': rect(1059, 310),
    'agent-down': rect(739, 189),
    'standard-up': rect(739, 241)
  };
  const nodeElements = [{}, {}, {}, {}, {}];
  const observers = [];
  class FakeResizeObserver {
    constructor(callback) {
      this.callback = callback;
      this.observed = [];
      this.disconnectCount = 0;
      observers.push(this);
    }

    observe(element) {
      this.observed.push(element);
    }

    disconnect() {
      this.disconnectCount += 1;
    }
  }
  const container = {
    getBoundingClientRect: () => ({ left: 0, top: 0, width, height }),
    querySelector(selector) {
      const match = selector.match(/data-command-center-port="([^"]+)"/);
      const value = match ? rects[match[1]] : null;
      return value ? { getBoundingClientRect: () => value } : null;
    },
    querySelectorAll(selector) {
      return selector === '[data-command-center-map-node="true"]' ? nodeElements : [];
    }
  };
  return { container, rects, observers, ResizeObserverClass: FakeResizeObserver };
}


function rect(left, top) {
  return { left, top, width: 10, height: 10 };
}
