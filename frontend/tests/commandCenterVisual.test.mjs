import assert from 'node:assert/strict';
import test from 'node:test';

import { commandCenterMotionState } from '../src/command-center/commandCenterVisual.js';


test('enables decorative motion only for an idle-loading fresh Runtime snapshot', () => {
  assert.equal(
    commandCenterMotionState({ hud: { resourceState: 'FRESH' } }, false),
    'enabled'
  );
  assert.equal(
    commandCenterMotionState({ hud: { resourceState: 'FRESH' } }, true),
    'paused'
  );
});


test('pauses decorative motion for stale empty and failed Runtime resources', () => {
  for (const resourceState of ['STALE', 'EMPTY', 'ERROR_RETAINED', 'ERROR_EMPTY']) {
    assert.equal(
      commandCenterMotionState({ hud: { resourceState } }, false),
      'paused',
      resourceState
    );
  }
  assert.equal(commandCenterMotionState(null, false), 'paused');
});
