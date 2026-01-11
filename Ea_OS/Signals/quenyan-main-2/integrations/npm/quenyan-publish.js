#!/usr/bin/env node
const { spawnSync } = require('child_process');
const { existsSync, mkdirSync, readFileSync, writeFileSync } = require('fs');
const { join, resolve } = require('path');

function run(command, args, options = {}) {
  const result = spawnSync(command, args, {
    stdio: 'inherit',
    env: process.env,
    ...options,
  });
  if (result.status !== 0) {
    throw new Error(`${command} ${args.join(' ')} failed with ${result.status}`);
  }
}

function ensureConfig(projectRoot) {
  const configDir = join(projectRoot, '.quenyan');
  if (!existsSync(configDir)) {
    mkdirSync(configDir, { recursive: true });
  }
  const configPath = join(configDir, 'config.json');
  if (!existsSync(configPath)) {
    const defaultConfig = {
      default_compression_mode: 'balanced',
      default_backend: 'rans',
      cache_dir: join(configDir, 'cache'),
    };
    writeFileSync(configPath, JSON.stringify(defaultConfig, null, 2));
  }
  return configDir;
}

function loadKey(configDir) {
  const keyPath = join(configDir, 'keys', 'master.key');
  if (!existsSync(keyPath)) {
    run('quenyan', ['init', '--generate-keys']);
  }
  return readFileSync(keyPath, 'utf8').trim();
}

function encodeSources(projectRoot, sources, passphrase) {
  const outputDir = resolve(projectRoot, 'dist', 'mcs');
  if (!existsSync(outputDir)) {
    mkdirSync(outputDir, { recursive: true });
  }
  const args = [
    'encode-project',
    outputDir,
    ...sources,
    '--passphrase',
    passphrase,
    '--json',
  ];
  run('quenyan', args, { cwd: projectRoot });
}

(function main() {
  const projectRoot = process.cwd();
  const configDir = ensureConfig(projectRoot);
  const passphrase = loadKey(configDir);
  const packageJson = JSON.parse(readFileSync(join(projectRoot, 'package.json')));
  const sources = packageJson.quenyan && packageJson.quenyan.sources;
  if (!sources || sources.length === 0) {
    console.log('[quenyan] no sources configured; skipping encoding');
    return;
  }
  encodeSources(projectRoot, sources, passphrase);
})();
