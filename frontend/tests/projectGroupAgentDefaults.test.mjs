import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const appSource = await readFile(new URL('../src/App.jsx', import.meta.url), 'utf8');

test('project group Agent Review fixed defaults stay out of the settings controls', () => {
  assert.equal(appSource.includes("reviewEngine: 'AGENT'"), true);
  assert.equal(appSource.includes('agentSourceExportAllowed: true'), true);
  assert.equal(appSource.includes('aiReviewEnabled: true'), true);
  assert.equal(appSource.includes('triggerOnManual: true'), true);
  assert.equal(appSource.includes('此处决定所选项目组后续 MR、Push 和默认 Manual Review 使用的主引擎'), false);
  assert.equal(appSource.includes('<Text strong>Review 引擎</Text>'), false);
  assert.equal(appSource.includes('<Text strong>手动触发</Text>'), false);
  assert.equal(appSource.includes('<Text strong>允许 Agent 外发源码片段</Text>'), false);
  assert.equal(appSource.includes('<Text strong>启用项目组 AI Review</Text>'), false);
});
