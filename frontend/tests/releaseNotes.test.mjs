import test from 'node:test';
import assert from 'node:assert/strict';

import { releaseNotes } from '../src/releaseNotes.js';

test('publishes v1.3.0 as the latest AI Review runtime overview release', () => {
  const latest = releaseNotes[0];
  const releaseText = JSON.stringify(latest);

  assert.equal(latest.version, 'v1.3.0');
  assert.equal(latest.releaseDate, '2026-08-05');
  assert.match(latest.title, /运行总览.*动态拓扑/);
  assert.match(releaseText, /Agent Review 主通道/);
  assert.match(releaseText, /Standard Review 降级辅助/);
  assert.match(releaseText, /顶部固定展示 Runtime 更新时间/);
  assert.match(releaseText, /最近活动 ReviewTask/);
  assert.match(releaseText, /北京时间自然日今日 Result/);
  assert.match(releaseText, /六条连接基于真实 DOM 端口动态测量/);
  assert.match(releaseText, /圆形双箭头降级节点/);
  assert.match(releaseText, /只有真实 fallback Item/);
  assert.match(releaseText, /“预览动画”.*约 6 秒.*不创建任务或改变指标/);
  assert.match(releaseText, /reduced-motion/);
  assert.match(releaseText, /不制造任务完成抵达事件/);
  assert.doesNotMatch(releaseText, /指挥中心|双执行轨|双 Review/);
  assert.equal(releaseNotes.filter(item => item.version === 'v1.3.0').length, 1);
});

test('keeps v1.2.0 as the unique Worker Pool governance release', () => {
  const workerPoolRelease = releaseNotes.find(item => item.version === 'v1.2.0');
  const releaseText = JSON.stringify(workerPoolRelease);

  assert.ok(workerPoolRelease);
  assert.match(workerPoolRelease.title, /Worker.*队列运行治理/);
  assert.match(releaseText, /claimAttempt fencing/);
  assert.match(releaseText, /deploy-stage3\.sh/);
  assert.equal(releaseNotes.filter(item => item.version === 'v1.2.0').length, 1);
});
