import assert from 'node:assert/strict';
import test from 'node:test';

import {
  createVisibilityRefreshLifecycle,
  FOCUS_AFTER_VISIBILITY_SUPPRESSION_MS
} from '../src/visibilityRefreshLifecycle.js';


test('pauses while hidden and coalesces visibility plus focus into one resume', () => {
  const documentTarget = createEventTarget({ hidden: false, visibilityState: 'visible' });
  const windowTarget = createEventTarget();
  const events = [];
  let now = 0;
  const lifecycle = createVisibilityRefreshLifecycle({
    documentTarget,
    windowTarget,
    now: () => now,
    onPause: source => events.push(`pause:${source}`),
    onResume: source => events.push(`resume:${source}`)
  });

  lifecycle.start();
  lifecycle.start();
  assert.deepEqual(events, ['resume:mount']);
  assert.equal(lifecycle.getSnapshot().listenerRegistrationCount, 2);

  documentTarget.hidden = true;
  documentTarget.visibilityState = 'hidden';
  documentTarget.emit('visibilitychange');
  windowTarget.emit('focus');
  assert.deepEqual(events, ['resume:mount', 'pause:visibility']);

  now = 100;
  documentTarget.hidden = false;
  documentTarget.visibilityState = 'visible';
  documentTarget.emit('visibilitychange');
  now += FOCUS_AFTER_VISIBILITY_SUPPRESSION_MS - 1;
  windowTarget.emit('focus');
  assert.deepEqual(events, [
    'resume:mount',
    'pause:visibility',
    'resume:visibility'
  ]);
  assert.equal(lifecycle.getSnapshot().suppressedFocusCount, 1);

  now += 2;
  windowTarget.emit('focus');
  assert.equal(events.at(-1), 'resume:focus');

  lifecycle.dispose();
  assert.equal(lifecycle.getSnapshot().listenerRegistrationCount, 0);
  assert.equal(documentTarget.listenerCount(), 0);
  assert.equal(windowTarget.listenerCount(), 0);
});


test('keeps two listeners and exactly one resume across repeated visibility cycles', () => {
  const documentTarget = createEventTarget({ hidden: false, visibilityState: 'visible' });
  const windowTarget = createEventTarget();
  let now = 0;
  let pauses = 0;
  let resumes = 0;
  const lifecycle = createVisibilityRefreshLifecycle({
    documentTarget,
    windowTarget,
    now: () => now,
    onPause: () => { pauses += 1; },
    onResume: () => { resumes += 1; }
  });

  lifecycle.start();
  for (let index = 0; index < 120; index += 1) {
    documentTarget.hidden = true;
    documentTarget.visibilityState = 'hidden';
    documentTarget.emit('visibilitychange');
    now += 1_000;
    documentTarget.hidden = false;
    documentTarget.visibilityState = 'visible';
    documentTarget.emit('visibilitychange');
    windowTarget.emit('focus');
  }

  const snapshot = lifecycle.getSnapshot();
  assert.equal(pauses, 120);
  assert.equal(resumes, 121);
  assert.equal(snapshot.pauseCount, 120);
  assert.equal(snapshot.resumeCount, 121);
  assert.equal(snapshot.suppressedFocusCount, 120);
  assert.equal(snapshot.listenerRegistrationCount, 2);
  assert.equal(documentTarget.listenerCount(), 1);
  assert.equal(windowTarget.listenerCount(), 1);

  lifecycle.dispose();
  assert.equal(documentTarget.listenerCount(), 0);
  assert.equal(windowTarget.listenerCount(), 0);
});


function createEventTarget(initial = {}) {
  const listeners = new Map();
  return {
    ...initial,
    addEventListener(type, listener) {
      if (!listeners.has(type)) listeners.set(type, new Set());
      listeners.get(type).add(listener);
    },
    removeEventListener(type, listener) {
      listeners.get(type)?.delete(listener);
    },
    emit(type) {
      for (const listener of listeners.get(type) || []) listener();
    },
    listenerCount() {
      return [...listeners.values()].reduce((count, bucket) => count + bucket.size, 0);
    }
  };
}
