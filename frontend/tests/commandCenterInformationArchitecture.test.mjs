import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';


const appSource = await readFile(new URL('../src/App.jsx', import.meta.url), 'utf8');
const pageSource = await readFile(
  new URL('../src/command-center/CommandCenterPage.jsx', import.meta.url),
  'utf8'
);
const apiSource = await readFile(
  new URL('../src/command-center/commandCenterApi.js', import.meta.url),
  'utf8'
);


function sourceBetween(start, end) {
  const startIndex = appSource.indexOf(start);
  const endIndex = appSource.indexOf(end, startIndex + start.length);
  assert.notEqual(startIndex, -1, `missing source marker: ${start}`);
  assert.notEqual(endIndex, -1, `missing source marker: ${end}`);
  return appSource.slice(startIndex, endIndex);
}


test('root route renders Command Center while preserving the legacy taskId redirect', () => {
  const homePageSource = sourceBetween('function HomePage()', 'function AppFrame()');

  assert.equal(homePageSource.includes("new URLSearchParams(location.search).get('taskId')"), true);
  assert.equal(homePageSource.includes('to={`/tasks/${legacyTaskId}`}'), true);
  assert.equal(homePageSource.includes('<CommandCenterPage />'), true);
  assert.equal(homePageSource.includes('<TaskListPage />'), false);
});


test('task list and task detail routes remain explicit and separate from home', () => {
  assert.equal(appSource.includes('<Route path={HOME_ROUTE} element={<HomePage />} />'), true);
  assert.equal(appSource.includes('<Route path={TASK_LIST_ROUTE} element={<TaskListPage />} />'), true);
  assert.equal(
    appSource.includes('<Route path={`${TASK_LIST_ROUTE}/:taskId`} element={<TaskDetailPage />} />'),
    true
  );
  assert.equal(appSource.includes('const isCommandCenterRoute = location.pathname === HOME_ROUTE'), true);
  assert.equal(
    appSource.includes('const isTaskRoute = location.pathname.startsWith(TASK_LIST_ROUTE)'),
    true
  );
  assert.equal(appSource.includes('指挥中心'), true);
});


test('phase zero page is read-only and does not create Canvas behavior', () => {
  assert.equal(pageSource.includes('data-command-center-phase="PHASE_0"'), true);
  assert.equal(pageSource.includes('READ-ONLY CONTROL PLANE'), true);
  assert.equal(pageSource.includes('<canvas'), false);
  assert.equal(pageSource.includes('setInterval'), false);
  assert.equal(pageSource.includes('WebSocket'), false);
  assert.equal(pageSource.includes('EventSource'), false);
});


test('phase zero data layer calls only the two read snapshot endpoints', () => {
  assert.equal(apiSource.includes("fetchApi('/api/command-center/runtime'"), true);
  assert.equal(apiSource.includes("fetchApi('/api/command-center/governance'"), true);
  assert.equal(apiSource.includes("method: 'POST'"), false);
  assert.equal(apiSource.includes("method: 'PUT'"), false);
  assert.equal(apiSource.includes("method: 'DELETE'"), false);
});
