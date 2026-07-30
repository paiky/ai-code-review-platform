import {
  closeSync,
  mkdirSync,
  openSync
} from 'node:fs';
import { dirname, resolve } from 'node:path';
import { spawn } from 'node:child_process';

const separatorIndex = process.argv.indexOf('--');
if (separatorIndex < 0 || separatorIndex >= process.argv.length - 1) {
  fail('Usage: start-detached.mjs --cwd <path> --stdout <path> --stderr <path> -- <file> [...args]');
}

const options = parseOptions(process.argv.slice(2, separatorIndex));
const command = process.argv[separatorIndex + 1];
const commandArgs = process.argv.slice(separatorIndex + 2);
const cwd = resolve(options.cwd || process.cwd());
const stdoutPath = resolve(options.stdout);
const stderrPath = resolve(options.stderr);

mkdirSync(dirname(stdoutPath), { recursive: true });
mkdirSync(dirname(stderrPath), { recursive: true });

const stdoutFd = openSync(stdoutPath, 'a');
const stderrFd = openSync(stderrPath, 'a');
let child;
try {
  child = spawn(command, commandArgs, {
    cwd,
    detached: true,
    windowsHide: true,
    stdio: ['ignore', stdoutFd, stderrFd]
  });
  child.unref();
} finally {
  closeSync(stdoutFd);
  closeSync(stderrFd);
}

process.stdout.write(`${JSON.stringify({ pid: child.pid })}\n`);

function parseOptions(args) {
  const result = {};
  for (let index = 0; index < args.length; index += 2) {
    const key = args[index];
    const value = args[index + 1];
    if (!key?.startsWith('--') || value === undefined) {
      fail('Detached launcher options must be key/value pairs.');
    }
    result[key.slice(2)] = value;
  }
  for (const required of ['cwd', 'stdout', 'stderr']) {
    if (!result[required]) fail(`Missing --${required}.`);
  }
  return result;
}

function fail(message) {
  process.stderr.write(`${message}\n`);
  process.exit(1);
}
