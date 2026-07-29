import test from 'node:test';
import assert from 'node:assert/strict';

import { releaseNotes } from '../src/releaseNotes.js';

test('publishes v1.2.0 as the latest three-stage Agent Review governance release', () => {
  const latest = releaseNotes[0];
  const releaseText = JSON.stringify(latest);

  assert.equal(latest.version, 'v1.2.0');
  assert.equal(latest.releaseDate, '2026-07-29');
  assert.match(latest.title, /Worker.*队列运行治理/);
  assert.match(releaseText, /claimAttempt fencing/);
  assert.match(releaseText, /两个 capacity=1/);
  assert.match(releaseText, /priority DESC \+ queuedAt ASC/);
  assert.match(releaseText, /DRAINING/);
  assert.match(releaseText, /deploy-stage3\.sh/);
  assert.match(releaseText, /不引入自动扩缩容/);
  assert.equal(releaseNotes.filter(item => item.version === 'v1.2.0').length, 1);
});
