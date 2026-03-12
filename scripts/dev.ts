import { spawn, spawnSync } from 'node:child_process';
import { existsSync, readFileSync, writeFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import net from 'node:net';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { config as loadDotenv } from 'dotenv';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const rootDir = path.resolve(__dirname, '..');
const aiDir = path.join(rootDir, 'ai_news');
const venvDir = path.join(aiDir, '.venv');
const requirementsFile = path.join(aiDir, 'requirements-lite.txt');
const markerFile = path.join(venvDir, '.deps-installed');

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

const loadEnvFiles = () => {
  const envFiles = [
    path.join(rootDir, '.env'),
    path.join(aiDir, '.env'),
    path.join(rootDir, '.env.local'),
    path.join(aiDir, '.env.local'),
  ];
  for (const envFile of envFiles) {
    if (existsSync(envFile)) {
      loadDotenv({ path: envFile, override: false });
    }
  }
};

loadEnvFiles();

const requireDatabaseUrl = () => {
  const databaseUrl = process.env.DATABASE_URL?.trim();
  if (!databaseUrl) {
    console.error('[dev:ai] DATABASE_URL is required. Point it at your Supabase Postgres database.');
    process.exit(1);
  }
  if (databaseUrl.startsWith('sqlite')) {
    console.error('[dev:ai] SQLite DATABASE_URL values are not supported. Use your Supabase Postgres database.');
    process.exit(1);
  }
  if (databaseUrl) return databaseUrl;
  process.exit(1);
};

const waitForPythonApi = async (baseUrl: string) => {
  const normalized = baseUrl.replace(/\/$/, '');
  const healthUrl = `${normalized}/v1/health`;
  let waited = 0;

  while (true) {
    try {
      const response = await fetch(healthUrl);
      if (response.ok) return;
    } catch {
      // Ignore until API is ready.
    }
    await sleep(2000);
    waited += 2000;
    if (waited % 10000 === 0) {
      console.log(`[dev] Waiting for Python API at ${healthUrl}...`);
    }
  }
};

const findAvailablePort = (start: number, attempts = 20): Promise<number> => {
  return new Promise((resolve, reject) => {
    let port = start;

    const tryPort = () => {
      if (port >= start + attempts) {
        reject(new Error(`No available port found in range ${start}-${start + attempts - 1}`));
        return;
      }

      const server = net.createServer();
      server.unref();
      server.on('error', () => {
        port += 1;
        tryPort();
      });
      server.listen(port, '0.0.0.0', () => {
        const chosen = port;
        server.close(() => resolve(chosen));
      });
    };

    tryPort();
  });
};

const findSystemPython = () => {
  const candidates = process.platform === 'win32' ? ['python'] : ['python3', 'python'];
  for (const candidate of candidates) {
    const result = spawnSync(candidate, ['--version'], { stdio: 'ignore' });
    if (result.status === 0) return candidate;
  }
  return null;
};

const getVenvPython = () => {
  if (process.platform === 'win32') {
    return path.join(venvDir, 'Scripts', 'python.exe');
  }
  return path.join(venvDir, 'bin', 'python');
};

const ensureVenv = () => {
  const python = findSystemPython();
  if (!python) {
    console.error('[dev:ai] Python not found. Please install Python 3.11+.');
    process.exit(1);
  }
  if (!existsSync(getVenvPython())) {
    console.log('[dev:ai] Creating Python virtual environment...');
    const result = spawnSync(python, ['-m', 'venv', venvDir], { stdio: 'inherit' });
    if (result.status !== 0) {
      process.exit(result.status ?? 1);
    }
  }
};

const ensureDeps = () => {
  const python = getVenvPython();
  const requirementsHash = createHash('sha256')
    .update(readFileSync(requirementsFile, 'utf8'))
    .digest('hex');
  const markerHash = existsSync(markerFile) ? readFileSync(markerFile, 'utf8').trim() : '';

  if (markerHash !== requirementsHash) {
    console.log('[dev:ai] Installing Python dependencies (lite)...');
    let result = spawnSync(python, ['-m', 'pip', 'install', '--upgrade', 'pip'], { stdio: 'inherit' });
    if (result.status !== 0) {
      process.exit(result.status ?? 1);
    }
    result = spawnSync(python, ['-m', 'pip', 'install', '-r', requirementsFile], {
      stdio: 'inherit',
    });
    if (result.status !== 0) {
      process.exit(result.status ?? 1);
    }
    writeFileSync(markerFile, requirementsHash, 'utf8');
  }
};

const runMigrations = () => {
  const python = getVenvPython();
  const databaseUrl = requireDatabaseUrl();
  console.log('[dev:ai] Running alembic upgrade head...');
  const result = spawnSync(python, ['-m', 'alembic', 'upgrade', 'head'], {
    stdio: 'inherit',
    cwd: aiDir,
    env: {
      ...process.env,
      PYTHONPATH: aiDir,
      DATABASE_URL: databaseUrl,
    },
  });
  if (result.status !== 0) {
    process.exit(result.status ?? 1);
  }
};

type Child = { name: string; proc: ReturnType<typeof spawn> };
const children: Child[] = [];
let shuttingDown = false;

const startProcess = (
  name: string,
  command: string,
  args: string[],
  opts?: { env?: NodeJS.ProcessEnv; cwd?: string },
) => {
  const proc = spawn(command, args, {
    stdio: 'inherit',
    cwd: opts?.cwd,
    env: { ...process.env, ...opts?.env },
  });
  children.push({ name, proc });
  proc.on('exit', (code) => {
    if (shuttingDown) return;
    if (code && code !== 0) {
      console.error(`[dev] ${name} exited with code ${code}`);
      shutdown();
    }
  });
};

const shutdown = () => {
  if (shuttingDown) return;
  shuttingDown = true;
  for (const child of children) {
    if (!child.proc.killed) {
      child.proc.kill('SIGINT');
    }
  }
  process.exit(1);
};

process.on('SIGINT', shutdown);
process.on('SIGTERM', shutdown);

const main = async () => {
  // Set up Python venv and deps inline (avoids tsx spawning tsx, which hangs)
  ensureVenv();
  ensureDeps();
  runMigrations();

  let pythonApiBaseUrl = process.env.PY_API_BASE_URL ?? '';
  let pythonPort: number | null = null;

  if (!pythonApiBaseUrl) {
    pythonPort = await findAvailablePort(8000);
    pythonApiBaseUrl = `http://localhost:${pythonPort}`;
  }

  const port = pythonPort ? String(pythonPort) : '8000';
  const python = getVenvPython();
  const databaseUrl = requireDatabaseUrl();

  // Spawn uvicorn directly instead of going through a second tsx process
  startProcess('dev:ai', python, [
    '-m', 'uvicorn', 'app.api.main:app', '--host', '0.0.0.0', '--port', port,
  ], {
    cwd: aiDir,
    env: {
      PYTHONPATH: aiDir,
      DATABASE_URL: databaseUrl,
      REDIS_URL: process.env.REDIS_URL ?? '',
      CELERY_BROKER_URL: process.env.CELERY_BROKER_URL ?? 'memory://',
      CELERY_RESULT_BACKEND: process.env.CELERY_RESULT_BACKEND ?? 'cache+memory://',
    },
  });

  await waitForPythonApi(pythonApiBaseUrl);

  const parsedPort = (() => {
    try {
      return String(new URL(pythonApiBaseUrl).port || 8000);
    } catch {
      return pythonPort ? String(pythonPort) : '8000';
    }
  })();
  console.log(`[dev] Using Python API at ${pythonApiBaseUrl} (proxy port ${parsedPort})`);

  startProcess('dev:web', 'vite', [], {
    env: { VITE_API_PORT: parsedPort },
  });
};

main().catch((error) => {
  console.error('[dev] Failed to start dev environment', error);
  process.exit(1);
});
