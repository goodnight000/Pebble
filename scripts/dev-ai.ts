import { spawn, spawnSync } from 'node:child_process';
import { existsSync, readFileSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createHash } from 'node:crypto';
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

const runApi = async () => {
  const python = getVenvPython();
  const port = process.env.PY_API_PORT ?? '8000';
  const databaseUrl = requireDatabaseUrl();
  const env = {
    ...process.env,
    PYTHONPATH: aiDir,
    DATABASE_URL: databaseUrl,
    REDIS_URL: process.env.REDIS_URL ?? '',
    CELERY_BROKER_URL: process.env.CELERY_BROKER_URL ?? 'memory://',
    CELERY_RESULT_BACKEND: process.env.CELERY_RESULT_BACKEND ?? 'cache+memory://',
  };

  const child = spawn(
    python,
    ['-m', 'uvicorn', 'app.api.main:app', '--host', '0.0.0.0', '--port', port],
    { stdio: 'inherit', cwd: aiDir, env }
  );

  const shutdown = () => {
    if (!child.killed) {
      child.kill('SIGINT');
    }
  };

  process.on('SIGINT', shutdown);
  process.on('SIGTERM', shutdown);

  child.on('exit', (code) => {
    process.exit(code ?? 0);
  });

  // Keep process alive if child exits unexpectedly very quickly.
  await sleep(1000);
};

const main = async () => {
  ensureVenv();
  ensureDeps();
  runMigrations();
  await runApi();
};

main().catch((error) => {
  console.error('[dev:ai] Failed to start Python API', error);
  process.exit(1);
});
