import http from 'node:http';

const completedTasks = new Set();
const port = parsePort(process.argv);
const host = '127.0.0.1';

function response(data) {
  return JSON.stringify({ success: true, data });
}

function safeReview(taskId, {
  engine = 'AGENT',
  effectiveEngine = engine,
  reviewKey = `${engine.toLowerCase()}-${taskId}`,
  status = 'RUNNING',
  findings = []
} = {}) {
  const provider = engine === 'AGENT' ? 'DeepSeek' : 'OpenAI';
  return {
    id: `${taskId}-${reviewKey}`,
    taskId,
    reviewKey,
    requestedEngine: engine,
    effectiveEngine,
    provider,
    model: engine === 'AGENT' ? 'agent-safe-model' : 'standard-safe-model',
    displayName: provider,
    status,
    overallLevel: findings.length ? 'HIGH' : 'LOW',
    summary: status === 'SUCCESS'
      ? '安全合成 Review 已完成。'
      : '安全合成 Review 正在运行。',
    findingCount: findings.length,
    findings,
    startedAt: '2026-07-30T05:30:00Z',
    finishedAt: status === 'SUCCESS' ? '2026-07-30T05:33:00Z' : null
  };
}

function safeFinding() {
  return {
    severity: 'HIGH',
    category: 'CORRECTNESS',
    title: '合成问题：缺少边界条件',
    description: '这是用于验证终态布局的本地合成问题。',
    recommendation: '补充显式边界检查和对应测试。',
    filePath: 'src/example/SafeExample.py',
    startLine: 12,
    endLine: 14,
    source: 'SYNTHETIC',
    confidence: 'HIGH',
    contextStatus: 'SUFFICIENT',
    evidence: []
  };
}

function taskDetail(taskId) {
  return {
    id: taskId,
    projectId: 7,
    projectName: '安全合成项目',
    gitProjectId: 700,
    triggerType: taskId === 47 ? 'GITLAB_PUSH_WEBHOOK' : 'GITLAB_MR_WEBHOOK',
    targetType: 'BACKEND',
    reviewStatus: taskId === 45 || completedTasks.has(taskId) ? 'SUCCESS' : 'RUNNING',
    status: 'SUCCESS',
    mrId: 42,
    sourceBranch: 'synthetic/source',
    targetBranch: 'synthetic/target',
    eventTime: '2026-07-30T05:29:00Z',
    templateCode: 'SAFE_TEMPLATE',
    codeQualityProfileCode: 'SAFE_PROFILE',
    changedFilesSummary: {
      count: 2,
      source: 'synthetic',
      files: [
        {
          path: 'src/example/SafeExample.py',
          oldPath: 'src/example/SafeExample.py',
          newPath: 'src/example/SafeExample.py',
          diffText: '@@ -12,1 +12,2 @@\n-safe\n+safe_checked'
        },
        {
          path: 'tests/test_safe_example.py',
          oldPath: 'tests/test_safe_example.py',
          newPath: 'tests/test_safe_example.py',
          diffText: '@@ -1,1 +1,2 @@\n-pass\n+assert safe'
        }
      ]
    },
    diffContextCapabilities: {
      fullContextAvailable: false
    }
  };
}

function agentProgress(taskId, reviewKey) {
  return [
    progressEvent(1, taskId, reviewKey, 'QUEUED', '{}', '2026-07-30T05:30:00Z'),
    progressEvent(
      2,
      taskId,
      reviewKey,
      'CONTEXT_PACK_BUILT',
      JSON.stringify({
        summary: {
          changedFileCount: 2,
          truncated: false,
          plannerSignalCount: 3,
          localRepository: { enabled: true, status: 'PREPARED' },
          localReferenceSearch: {
            status: 'COMPLETED',
            queryCount: 2,
            matchedFileCount: 2,
            includedSnippetCount: 3
          },
          requestedContextAvailability: { available: 2, unavailable: 1 },
          budgetCutSummary: { truncated: false, notInjectedEvidence: [] }
        },
        prompt: 'SYNTHETIC_PROMPT_MUST_NOT_RENDER',
        workerId: 'SYNTHETIC_WORKER_MUST_NOT_RENDER'
      }),
      '2026-07-30T05:30:20Z'
    ),
    progressEvent(
      3,
      taskId,
      reviewKey,
      'LOCAL_REPO_PREPARED',
      '{"status":"PREPARED","enabled":true}',
      '2026-07-30T05:30:30Z'
    ),
    progressEvent(
      4,
      taskId,
      null,
      'DETERMINISTIC_PRECHECK_COMPLETED',
      '{"status":"COMPLETED","checkType":"SECRET_SCAN","findingCount":0,"scannedFileCount":2}',
      '2026-07-30T05:30:40Z'
    ),
    progressEvent(
      5,
      taskId,
      reviewKey,
      'AGENT_ANALYZING',
      '{"runId":8,"claimAttempt":1,"sequence":0}',
      '2026-07-30T05:31:00Z'
    ),
    progressEvent(
      6,
      taskId,
      reviewKey,
      'AGENT_TOOL_ACTIVITY',
      '{"runId":8,"claimAttempt":1,"sequence":1,"toolName":"read_source","toolCallCount":2,"evidenceCallsUsed":1,"sourceBytesReturned":1024,"effectiveBudgets":{"maxToolCalls":10,"maxEvidenceCalls":6,"maxSourceBytes":12000}}',
      '2026-07-30T05:31:10Z'
    ),
    progressEvent(
      7,
      taskId,
      reviewKey,
      'AGENT_HEARTBEAT',
      '{"runId":8,"claimAttempt":1,"heartbeatSequence":3,"toolCallCount":2,"evidenceCallsUsed":1,"sourceBytesReturned":1024,"effectiveBudgets":{"maxToolCalls":10,"maxEvidenceCalls":6,"maxSourceBytes":12000}}',
      new Date().toISOString(),
      'DEBUG'
    )
  ];
}

function terminalProgress(taskId, reviewKey) {
  return [
    progressEvent(20, taskId, reviewKey, 'RESULT_SAVED', '{}', '2026-07-30T05:32:40Z'),
    progressEvent(21, taskId, reviewKey, 'FINISHED', '{}', '2026-07-30T05:33:00Z')
  ];
}

function progressEvent(id, taskId, reviewKey, phase, detail, createdAt, level = 'INFO') {
  return { id, taskId, reviewKey, phase, level, detail, createdAt };
}

function reviews(taskId) {
  if (taskId === 42) {
    return [
      safeReview(taskId, { reviewKey: 'agent-running' }),
      safeReview(taskId, {
        engine: 'STANDARD',
        reviewKey: 'standard-terminal',
        status: 'SUCCESS',
        findings: [safeFinding()]
      })
    ];
  }
  if (taskId === 43) {
    return [safeReview(taskId, {
      engine: 'STANDARD',
      reviewKey: 'standard-running'
    })];
  }
  if (taskId === 44) {
    return [safeReview(taskId, {
      reviewKey: 'fallback-running',
      effectiveEngine: 'STANDARD_FALLBACK'
    })];
  }
  if (taskId === 45 || completedTasks.has(taskId)) {
    return [safeReview(taskId, {
      reviewKey: taskId === 45 ? 'terminal-result' : 'polling-review',
      status: 'SUCCESS',
      findings: [safeFinding()]
    })];
  }
  return [safeReview(taskId, {
    reviewKey: taskId === 46 ? 'polling-review' : `agent-${taskId}`
  })];
}

function progress(taskId) {
  if (taskId === 42) {
    return [
      ...agentProgress(taskId, 'agent-running'),
      ...terminalProgress(taskId, 'standard-terminal')
    ];
  }
  if (taskId === 43) {
    return [
      progressEvent(
        30,
        taskId,
        'standard-running',
        'OPENAI_REQUEST',
        '{}',
        '2026-07-30T05:31:00Z'
      )
    ];
  }
  if (taskId === 44) {
    return [
      progressEvent(
        40,
        taskId,
        'fallback-running',
        'AGENT_FALLBACK',
        '{"failureMessage":"SYNTHETIC_EXCEPTION_MUST_NOT_RENDER"}',
        '2026-07-30T05:30:00Z',
        'WARN'
      ),
      progressEvent(
        41,
        taskId,
        'fallback-running',
        'AGENT_FALLBACK_QUEUED',
        '{}',
        '2026-07-30T05:30:10Z'
      ),
      progressEvent(
        42,
        taskId,
        'fallback-running',
        'OPENAI_REQUEST',
        '{}',
        '2026-07-30T05:31:00Z'
      )
    ];
  }
  if (taskId === 45 || completedTasks.has(taskId)) {
    return terminalProgress(
      taskId,
      taskId === 45 ? 'terminal-result' : 'polling-review'
    );
  }
  return agentProgress(
    taskId,
    taskId === 46 ? 'polling-review' : `agent-${taskId}`
  );
}

function taskIdFromPath(pathname) {
  const match = /^\/api\/review-tasks\/(\d+)/.exec(pathname);
  return match ? Number(match[1]) : null;
}

const server = http.createServer((request, reply) => {
  const url = new URL(request.url, `http://${host}:${port}`);
  reply.setHeader('Content-Type', 'application/json; charset=utf-8');
  reply.setHeader('Cache-Control', 'no-store');

  if (url.pathname === '/api/__docs50__/health') {
    reply.end(response({
      service: 'docs50-safe-mock',
      version: 1
    }));
    return;
  }

  const completeMatch = /^\/__mock__\/complete\/(\d+)$/.exec(url.pathname);
  if (completeMatch) {
    completedTasks.add(Number(completeMatch[1]));
    reply.end(response({ completed: true }));
    return;
  }
  const resetMatch = /^\/__mock__\/reset\/(\d+)$/.exec(url.pathname);
  if (resetMatch) {
    completedTasks.delete(Number(resetMatch[1]));
    reply.end(response({ reset: true }));
    return;
  }

  if (url.pathname === '/api/code-quality-reviews/job-queue') {
    reply.end(response({ activeCount: 0, groups: [] }));
    return;
  }
  if (url.pathname === '/api/code-quality-reviews/failure-notifications') {
    reply.end(response({ failureCount: 0, items: [] }));
    return;
  }

  const taskId = taskIdFromPath(url.pathname);
  if (taskId !== null) {
    if (url.pathname === `/api/review-tasks/${taskId}`) {
      reply.end(response(taskDetail(taskId)));
      return;
    }
    if (url.pathname === `/api/review-tasks/${taskId}/code-quality-results`) {
      reply.end(response(reviews(taskId)));
      return;
    }
    if (url.pathname === `/api/review-tasks/${taskId}/code-quality-result`) {
      reply.end(response(reviews(taskId)[0] || null));
      return;
    }
    if (url.pathname === `/api/review-tasks/${taskId}/code-quality-progress`) {
      reply.end(response(progress(taskId)));
      return;
    }
    if (url.pathname === `/api/review-tasks/${taskId}/code-quality-gate`) {
      reply.end(response(null));
      return;
    }
    if (url.pathname === `/api/review-tasks/${taskId}/code-quality-fix-previews`) {
      reply.end(response([]));
      return;
    }
    if (url.pathname === `/api/review-tasks/${taskId}/deterministic-checks`) {
      reply.end(response({ status: 'COMPLETED', latestRun: null, runs: [] }));
      return;
    }
  }

  if (request.method === 'POST' && url.pathname.includes('/cancel')) {
    reply.end(response({ status: 'CANCELLED' }));
    return;
  }

  reply.statusCode = 404;
  reply.end(JSON.stringify({
    success: false,
    message: 'Synthetic endpoint not found'
  }));
});

server.listen(port, host, () => {
  console.log(`docs/50 safe mock ready at http://${host}:${port}`);
});

function parsePort(argv) {
  const index = argv.indexOf('--port');
  const value = index >= 0 ? Number(argv[index + 1]) : 8080;
  if (!Number.isInteger(value) || value < 1 || value > 65535) {
    throw new Error('A valid --port is required.');
  }
  return value;
}
