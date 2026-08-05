import http from 'node:http';

import {
  COMMAND_CENTER_M4_SCENARIOS,
  commandCenterGovernanceFixture,
  commandCenterRuntimeFixture
} from './command-center-m4-fixtures.mjs';


const port = parsePort(process.argv);
const host = '127.0.0.1';
let scenario = parseScenario(process.argv);


const server = http.createServer((request, reply) => {
  const url = new URL(request.url, `http://${host}:${port}`);
  reply.setHeader('Content-Type', 'application/json; charset=utf-8');
  reply.setHeader('Cache-Control', 'no-store');

  if (url.pathname === '/api/__command-center-m4__/health') {
    send(reply, 200, { service: 'command-center-m4-safe-mock', scenario });
    return;
  }

  const scenarioMatch = /^\/__mock__\/scenario\/([a-z-]+)$/.exec(url.pathname);
  if (request.method === 'POST' && scenarioMatch) {
    const requested = scenarioMatch[1];
    if (!COMMAND_CENTER_M4_SCENARIOS.includes(requested)) {
      sendError(reply, 400, 'Unknown M4 scenario');
      return;
    }
    scenario = requested;
    send(reply, 200, { scenario });
    return;
  }

  if (url.pathname === '/api/command-center/runtime') {
    if (scenario === 'runtime-error') {
      sendError(reply, 503, 'Synthetic Runtime failure');
      return;
    }
    send(reply, 200, commandCenterRuntimeFixture(scenario));
    return;
  }

  if (url.pathname === '/api/command-center/governance') {
    if (scenario === 'governance-error') {
      sendError(reply, 503, 'Synthetic Governance failure');
      return;
    }
    send(reply, 200, commandCenterGovernanceFixture());
    return;
  }

  sendError(reply, 404, 'Synthetic endpoint not found');
});


server.listen(port, host, () => {
  console.log(`Command Center M4 safe mock ready at http://${host}:${port} (${scenario})`);
});


for (const signal of ['SIGINT', 'SIGTERM']) {
  process.on(signal, () => server.close(() => process.exit(0)));
}


function send(reply, statusCode, data) {
  reply.statusCode = statusCode;
  reply.end(JSON.stringify({ success: true, data }));
}


function sendError(reply, statusCode, message) {
  reply.statusCode = statusCode;
  reply.end(JSON.stringify({ success: false, message }));
}


function parsePort(argv) {
  const index = argv.indexOf('--port');
  const value = index >= 0 ? Number(argv[index + 1]) : 8094;
  if (!Number.isInteger(value) || value < 1 || value > 65535) {
    throw new Error('A valid --port is required.');
  }
  return value;
}


function parseScenario(argv) {
  const index = argv.indexOf('--scenario');
  const value = index >= 0 ? argv[index + 1] : 'idle';
  if (!COMMAND_CENTER_M4_SCENARIOS.includes(value)) {
    throw new Error(`Unknown Command Center M4 scenario: ${value}`);
  }
  return value;
}
