import assert from 'node:assert/strict';
import test from 'node:test';

import { restoreCommandCenterFocus } from '../src/command-center/commandCenterInteractions.js';


test('restores Modal focus to its connected overflow trigger', () => {
  const trigger = focusTarget(true);
  const fallback = focusTarget(true);

  assert.equal(restoreCommandCenterFocus(trigger, fallback), true);
  assert.equal(trigger.focusCount, 1);
  assert.equal(fallback.focusCount, 0);
});


test('falls back to the connected page target when the overflow trigger disappeared during polling', () => {
  const trigger = focusTarget(false);
  const fallback = focusTarget(true);

  assert.equal(restoreCommandCenterFocus(trigger, fallback), true);
  assert.equal(trigger.focusCount, 0);
  assert.equal(fallback.focusCount, 1);
});


test('does not focus a disconnected or invalid fallback', () => {
  assert.equal(restoreCommandCenterFocus(null, focusTarget(false)), false);
  assert.equal(restoreCommandCenterFocus(null, { isConnected: true }), false);
});


function focusTarget(isConnected) {
  return {
    isConnected,
    focusCount: 0,
    focus() {
      this.focusCount += 1;
    }
  };
}
