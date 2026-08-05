import assert from 'node:assert/strict';
import test from 'node:test';

import {
  affectedRiskVisual,
  findingSeverityVisual,
  providerQualityVisual
} from '../src/command-center/commandCenterQualityVisual.js';


test('M2-1 provider micro visual uses only real success and failure counts', () => {
  assert.deepEqual(providerQualityVisual({
    available: true,
    successCount: 17,
    failureCount: 3
  }), {
    available: true,
    empty: false,
    successCount: 17,
    failureCount: 3,
    successPercent: 85,
    failurePercent: 15,
    label: '成功 17，失败 3'
  });
  assert.equal(providerQualityVisual({ available: true }).empty, true);
  assert.equal(providerQualityVisual({ available: false, successCount: 99 }).successCount, 0);
});


test('M2-1 finding visual normalizes real severity counts without synthesizing bars', () => {
  const visual = findingSeverityVisual({
    available: true,
    severityCounts: { critical: 2, HIGH: 4, medium: 1, low: 3, unknown: 2 }
  });
  assert.equal(visual.empty, false);
  assert.deepEqual(visual.bars.map(item => [item.token, item.count, item.percent]), [
    ['critical', 2, 40],
    ['high', 4, 80],
    ['medium', 1, 20],
    ['low-other', 5, 100]
  ]);
  assert.equal(visual.label, '严重 2，高 4，中 1，低/其他 5');
  assert.equal(findingSeverityVisual({ available: true, severityCounts: {} }).empty, true);
});


test('M2-1 risk ladder maps only the observed highest risk category', () => {
  assert.equal(affectedRiskVisual({ available: true, highestRisk: 'HIGH' }).level, 3);
  assert.equal(affectedRiskVisual({ available: true, highestRisk: null }).empty, true);
  assert.equal(affectedRiskVisual({ available: false, highestRisk: 'CRITICAL' }).level, 0);
});
