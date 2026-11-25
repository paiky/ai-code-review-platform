const { createHash, randomUUID } = require('node:crypto');
const { readFileSync, statSync } = require('node:fs');
const { isIP } = require('node:net');
const path = require('node:path');
const { promisify } = require('node:util');

function shellQuote(value) {
  return `'${value.replace(/'/g, `'"'"'`)}'`;
}

function connect(client, config) {
  let actualFingerprint;
  return new Promise((resolve, reject) => {
    client.once('ready', resolve);
    client.once('close', () => reject(new Error('SSH connection closed before authentication completed.')));
    client.on('error', (error) => {
      if (actualFingerprint && actualFingerprint !== config.fingerprint) {
        reject(new Error(`SSH host key fingerprint mismatch. Received ${actualFingerprint}.`));
      } else {
        reject(error);
      }
    });
    client.connect({
      host: config.host,
      port: config.port,
      username: config.username,
      privateKey: readFileSync(config.privateKeyPath),
      readyTimeout: 10000,
      keepaliveInterval: 15000,
      hostVerifier(hostKey) {
        const digest = createHash('sha256').update(hostKey).digest('base64').replace(/=+$/, '');
        actualFingerprint = `SHA256:${digest}`;
        return actualFingerprint === config.fingerprint;
      },
    });
  });
}

function runRemote(client, script) {
  return new Promise((resolve, reject) => {
    client.exec(`bash -c ${shellQuote(script)}`, (error, stream) => {
      if (error) {
        reject(error);
        return;
      }
      stream.on('data', (chunk) => process.stdout.write(chunk));
      stream.stderr.on('data', (chunk) => process.stdout.write(chunk));
      stream.on('error', reject);
      stream.on('close', (code, signal) => {
        if (code === 0) {
          resolve();
        } else {
          reject(new Error(`Remote command failed (${signal || code || 'connection closed'}).`));
        }
      });
    });
  });
}

async function uploadPackage(client, config, stagingDir) {
  const { packageDir, version } = config;
  const files = [
    `ai-code-review-backend-${version}.tar`,
    `ai-code-review-frontend-${version}.tar`,
    `ai-code-review-agent-worker-${version}.tar`,
    `ai-code-review-agent-egress-${version}.tar`,
    'docker-compose.yml',
    '.env.example',
    'load-images.sh',
    'deploy-stage3.sh',
  ].map((name) => {
    const local = path.join(packageDir, name);
    const info = statSync(local);
    if (!info.isFile() || info.size === 0) {
      throw new Error(`Invalid package file: ${local}`);
    }
    return { name, local, size: info.size };
  });

  await runRemote(client, `umask 077\nmkdir -- ${shellQuote(stagingDir)}`);
  const sftp = await promisify(client.sftp.bind(client))();
  try {
    const put = promisify(sftp.fastPut.bind(sftp));
    const stat = promisify(sftp.stat.bind(sftp));
    for (const { name, local, size } of files) {
      const remote = path.posix.join(stagingDir, name);
      console.log(`Uploading ${name} (${size} bytes)`);
      await put(local, remote);
      if ((await stat(remote)).size !== size) {
        throw new Error(`Upload size mismatch: ${name}`);
      }
    }
  } finally {
    sftp.end();
  }
}

async function main() {
  const mode = process.argv[2];
  const config = JSON.parse(readFileSync(0, 'utf8'));
  const deployRoot = config.deployRoot.replace(/\/+$/, '');
  if (!isIP(config.host)) {
    throw new Error('-Server must be an IPv4 or IPv6 address.');
  }
  if (!deployRoot.startsWith('/') || /[\r\n\0]/.test(deployRoot)) {
    throw new Error('-DeployRoot must be an absolute Linux path containing runtime/.');
  }
  if (!/^SHA256:[A-Za-z0-9+/]{43}$/.test(config.fingerprint)) {
    throw new Error('-HostKeyFingerprint must be an OpenSSH SHA256 fingerprint.');
  }
  if (!/^\d{14}$/.test(config.version) || !Number.isInteger(config.workers)
      || config.workers < 1 || config.workers > 100 || !['preflight', 'deploy'].includes(mode)) {
    throw new Error('Invalid deployment version, worker count, or command.');
  }

  const { Client } = require(config.ssh2ModulePath);
  const client = new Client();
  const runtime = shellQuote(`${deployRoot}/runtime`);
  const versionDir = shellQuote(`${deployRoot}/${config.version}`);
  const checkEnv = '[ -f "$runtime/.env" ] && [ -r "$runtime/.env" ] && [ -w "$runtime/.env" ]'
    + ' || { echo "Configure a readable and writable runtime/.env before upgrading." >&2; exit 1; }';
  let stage = 'SSH connection';
  try {
    await connect(client, config);
    if (mode === 'preflight') {
      stage = 'Remote preflight';
      await runRemote(client, `set -e
runtime=${runtime}
[ -d ${shellQuote(deployRoot)} ] && [ -w ${shellQuote(deployRoot)} ] && [ -d "$runtime" ] && [ -w "$runtime" ] \\
  || { echo "Deploy root and existing runtime directory must be writable." >&2; exit 1; }
${checkEnv}
[ -f "$runtime/docker-compose.yml" ] || { echo "Existing runtime/docker-compose.yml is required." >&2; exit 1; }
[ ! -e ${versionDir} ] || { echo "Remote version directory already exists." >&2; exit 1; }
command -v flock >/dev/null || { echo "flock is required on the server." >&2; exit 1; }
if [ -e "$runtime/.remote-deploy.lock" ]; then
  flock -n 8 8<"$runtime/.remote-deploy.lock" || { echo "Another one-click deployment is using this runtime." >&2; exit 1; }
fi
docker info --format '{{.ServerVersion}}' >/dev/null
docker compose version >/dev/null
echo "Remote preflight passed."`);
      return;
    }

    stage = 'SFTP upload';
    const stagingDir = `${deployRoot}/.upload-${config.version}-${randomUUID()}`;
    console.log(`Remote staging directory: ${stagingDir}`);
    const uploadStarted = performance.now();
    try {
      await uploadPackage(client, config, stagingDir);
    } finally {
      console.log(`SFTP upload took ${((performance.now() - uploadStarted) / 1000).toFixed(1)}s.`);
    }

    stage = 'Remote image loading and Stage 3 upgrade';
    await runRemote(client, `set -e
runtime=${runtime}
exec 8>"$runtime/.remote-deploy.lock"
flock -n 8 || { echo "Another one-click deployment is using this runtime." >&2; exit 1; }
${checkEnv}
[ ! -e ${versionDir} ] && [ ! -L ${versionDir} ] || { echo "Remote version directory already exists." >&2; exit 1; }
mv -T -- ${shellQuote(stagingDir)} ${versionDir}
cd -- ${versionDir}
echo "Loading images for version ${config.version}."
started=$SECONDS
code=0
DEPLOY_HOME="$runtime" bash ./load-images.sh || code=$?
echo "Remote image loading took $((SECONDS - started))s."
[ "$code" -eq 0 ] || { echo "Image loading failed." >&2; exit "$code"; }
cd -- "$runtime"
echo "Running Stage 3 upgrade with ${config.workers} workers."
started=$SECONDS
./deploy-stage3.sh upgrade --workers ${config.workers} || code=$?
echo "Stage 3 upgrade took $((SECONDS - started))s."
[ "$code" -eq 0 ] || { echo "Stage 3 upgrade failed." >&2; exit "$code"; }`);
  } catch (error) {
    throw new Error(`${stage}: ${error.message}`);
  } finally {
    client.end();
  }
}

main().catch((error) => {
  console.log(`ERROR: ${error.message}`);
  process.exitCode = 1;
});
