const vscode = require('vscode');
const cp = require('child_process');
const path = require('path');
const { promises: fsp } = require('fs');
const os = require('os');
const crypto = require('crypto');

const openDocuments = new Map();
let statusBarItem;

function getCliInvocation() {
  const config = vscode.workspace.getConfiguration('quenyan');
  const command = config.get('cliCommand');
  if (command) {
    const parts = command.split(/\s+/).filter(Boolean);
    if (parts.length === 0) {
      throw new Error('CLI command is empty');
    }
    return { executable: parts[0], baseArgs: parts.slice(1) };
  }
  const executable = process.env.QYN_PYTHON || 'python3';
  return { executable, baseArgs: ['-m', 'qyn1.cli'] };
}

function runCli(args, cwd) {
  const { executable, baseArgs } = getCliInvocation();
  return new Promise((resolve, reject) => {
    const proc = cp.spawn(executable, [...baseArgs, ...args], {
      cwd,
      env: { ...process.env, QUENYAN_NONINTERACTIVE: '1' },
    });
    let stdout = '';
    let stderr = '';
    proc.stdout.on('data', (chunk) => (stdout += chunk.toString()));
    proc.stderr.on('data', (chunk) => (stderr += chunk.toString()));
    proc.on('close', (code) => {
      if (code === 0) {
        resolve({ stdout, stderr });
      } else {
        reject(new Error(stderr || `CLI exited with code ${code}`));
      }
    });
  });
}

async function ensureStorage(context) {
  const storageUri = context.globalStorageUri;
  try {
    await fsp.mkdir(storageUri.fsPath, { recursive: true });
  } catch (error) {
    // ignored: directory already exists
  }
  return storageUri.fsPath;
}

async function getKeyFile(context) {
  const config = vscode.workspace.getConfiguration('quenyan');
  const keyFile = config.get('keyFile');
  if (keyFile) {
    return keyFile;
  }
  let passphrase = await context.secrets.get('passphrase');
  if (!passphrase) {
    passphrase = await vscode.window.showInputBox({
      prompt: 'Enter Quenyan passphrase',
      password: true,
      placeHolder: 'Stored securely for this workspace',
    });
    if (!passphrase) {
      throw new Error('A passphrase is required to decode packages');
    }
    await context.secrets.store('passphrase', passphrase);
  }
  const storagePath = await ensureStorage(context);
  const keyPath = path.join(storagePath, 'session.key');
  await fsp.writeFile(keyPath, `${passphrase}\n`, { encoding: 'utf8', mode: 0o600 });
  return keyPath;
}

async function requirePackagePath() {
  const editor = vscode.window.activeTextEditor;
  if (editor && editor.document.uri.scheme === 'file' && editor.document.uri.fsPath.endsWith('.qyn1')) {
    return editor.document.uri.fsPath;
  }
  const selection = await vscode.window.showOpenDialog({
    canSelectFiles: true,
    canSelectMany: false,
    filters: { 'QYN Packages': ['qyn1'] },
  });
  if (!selection || selection.length === 0) {
    return undefined;
  }
  return selection[0].fsPath;
}

function updateStatus(text, tooltip) {
  if (!statusBarItem) {
    statusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 100);
    statusBarItem.name = 'Quenyan Status';
    statusBarItem.show();
  }
  statusBarItem.text = `$(shield) Quenyan: ${text}`;
  statusBarItem.tooltip = tooltip;
}

async function decodePackage(context, packagePath) {
  try {
    const storage = await ensureStorage(context);
    const decodedPath = path.join(storage, `${path.basename(packagePath)}.decoded.py`);
    const keyFile = await getKeyFile(context);
    await runCli(['decode', packagePath, '--key', keyFile, '-o', decodedPath, '--quiet'], path.dirname(packagePath));
    const document = await vscode.workspace.openTextDocument(decodedPath);
    openDocuments.set(document.uri.toString(), { packagePath, decodedPath, keyFile });
    await vscode.window.showTextDocument(document, { preview: false });
    updateStatus('Decrypted', packagePath);
  } catch (error) {
    vscode.window.showErrorMessage(`Failed to decode package: ${error.message}`);
  }
}

async function encodeDocument(entry) {
  try {
    await runCli(['encode', entry.decodedPath, '--key', entry.keyFile, '-o', entry.packagePath, '--quiet'], path.dirname(entry.packagePath));
    updateStatus('Encrypted', entry.packagePath);
  } catch (error) {
    vscode.window.showErrorMessage(`Failed to encode package: ${error.message}`);
  }
}

async function inspectMetadata() {
  const packagePath = await requirePackagePath();
  if (!packagePath) {
    return;
  }
  try {
    const { stdout } = await runCli(['inspect', packagePath, '--json', '--show-metadata'], path.dirname(packagePath));
    const json = JSON.parse(stdout);
    const metadata = json.metadata || {};
    const lines = Object.entries(metadata).map(([key, value]) => `${key}: ${value}`);
    vscode.window.showInformationMessage(`QYN Package: ${path.basename(packagePath)}\n${lines.join('\n')}`);
  } catch (error) {
    vscode.window.showErrorMessage(`Failed to inspect package: ${error.message}`);
  }
}

async function exportSourceMap(context) {
  const packagePath = await requirePackagePath();
  if (!packagePath) {
    return;
  }
  const destination = await vscode.window.showSaveDialog({
    defaultUri: vscode.Uri.file(`${packagePath}.map`),
    filters: { 'QYN Source Maps': ['map'] },
  });
  if (!destination) {
    return;
  }
  try {
    const keyFile = await getKeyFile(context);
    await runCli(['source-map', packagePath, '--key', keyFile, '--output', destination.fsPath, '--json'], path.dirname(packagePath));
    vscode.window.showInformationMessage(`Source map exported to ${destination.fsPath}`);
  } catch (error) {
    vscode.window.showErrorMessage(`Failed to export source map: ${error.message}`);
  }
}

async function diffPackages(context) {
  const selection = await vscode.window.showOpenDialog({
    canSelectFiles: true,
    canSelectMany: true,
    filters: { 'QYN Packages': ['qyn1'] },
  });
  if (!selection || selection.length !== 2) {
    vscode.window.showWarningMessage('Select exactly two packages to diff.');
    return;
  }
  const keyFile = await getKeyFile(context);
  const storage = await ensureStorage(context);
  const decoded = [];
  for (const uri of selection) {
    const decodedPath = path.join(storage, `${path.basename(uri.fsPath)}.diff.py`);
    await runCli(['decode', uri.fsPath, '--key', keyFile, '-o', decodedPath, '--quiet'], path.dirname(uri.fsPath));
    decoded.push(vscode.Uri.file(decodedPath));
  }
  const title = `${path.basename(selection[0].fsPath)} ↔ ${path.basename(selection[1].fsPath)}`;
  await vscode.commands.executeCommand('vscode.diff', decoded[0], decoded[1], title);
}

async function openCliTerminal() {
  const terminal = vscode.window.createTerminal({ name: 'Quenyan CLI' });
  terminal.show(true);
  terminal.sendText('quenyan --help');
}

async function generateKey(context) {
  const data = crypto.randomBytes(32).toString('base64');
  const destination = await vscode.window.showSaveDialog({
    defaultUri: vscode.Uri.file(path.join(os.homedir(), 'quenyan.key')),
  });
  if (!destination) {
    return;
  }
  await fsp.writeFile(destination.fsPath, `${data}\n`, { encoding: 'utf8', mode: 0o600 });
  await vscode.workspace.getConfiguration('quenyan').update('keyFile', destination.fsPath, vscode.ConfigurationTarget.Workspace);
  vscode.window.showInformationMessage(`Saved new key to ${destination.fsPath}`);
}

async function importKey(context) {
  const selection = await vscode.window.showOpenDialog({
    canSelectFiles: true,
    canSelectMany: false,
    filters: { Keys: ['key', 'txt'] },
  });
  if (!selection || selection.length === 0) {
    return;
  }
  const keyPath = selection[0].fsPath;
  await vscode.workspace.getConfiguration('quenyan').update('keyFile', keyPath, vscode.ConfigurationTarget.Workspace);
  vscode.window.showInformationMessage(`Using key file ${keyPath}`);
}

async function exportPassphrase(context) {
  const passphrase = await context.secrets.get('passphrase');
  if (!passphrase) {
    vscode.window.showWarningMessage('No passphrase stored in the workspace secret storage.');
    return;
  }
  const destination = await vscode.window.showSaveDialog({
    defaultUri: vscode.Uri.file(path.join(os.homedir(), 'quenyan-export.key')),
  });
  if (!destination) {
    return;
  }
  await fsp.writeFile(destination.fsPath, `${passphrase}\n`, { encoding: 'utf8', mode: 0o600 });
  vscode.window.showInformationMessage(`Exported passphrase to ${destination.fsPath}`);
}

async function verifyPackage(context) {
  const packagePath = await requirePackagePath();
  if (!packagePath) {
    return;
  }
  const keyFile = await getKeyFile(context);
  try {
    const { stdout } = await runCli(['verify', packagePath, '--key', keyFile, '--check-signature', '--json'], path.dirname(packagePath));
    const json = JSON.parse(stdout);
    vscode.window.showInformationMessage(`Verified ${json.package} in ${json.duration_s.toFixed(2)}s`);
  } catch (error) {
    vscode.window.showErrorMessage(`Verification failed: ${error.message}`);
  }
}

function activate(context) {
  updateStatus('Idle', 'Waiting for Quenyan activity');

  context.subscriptions.push(
    vscode.commands.registerCommand('qyn.inspectMetadata', inspectMetadata),
    vscode.commands.registerCommand('qyn.exportSourceMap', () => exportSourceMap(context)),
    vscode.commands.registerCommand('qyn.decodePackage', (uri) => decodePackage(context, uri.fsPath)),
    vscode.commands.registerCommand('qyn.diffPackages', () => diffPackages(context)),
    vscode.commands.registerCommand('qyn.openTerminal', openCliTerminal),
    vscode.commands.registerCommand('qyn.generateKey', () => generateKey(context)),
    vscode.commands.registerCommand('qyn.importKey', () => importKey(context)),
    vscode.commands.registerCommand('qyn.exportKey', () => exportPassphrase(context)),
    vscode.commands.registerCommand('qyn.verifyPackage', () => verifyPackage(context))
  );

  context.subscriptions.push(
    vscode.workspace.onDidOpenTextDocument((document) => {
      if (document.uri.scheme === 'file' && document.uri.fsPath.endsWith('.qyn1')) {
        decodePackage(context, document.uri.fsPath);
      }
    }),
    vscode.workspace.onDidSaveTextDocument((document) => {
      const entry = openDocuments.get(document.uri.toString());
      if (entry) {
        encodeDocument(entry);
      }
    }),
    vscode.workspace.onDidCloseTextDocument((document) => {
      openDocuments.delete(document.uri.toString());
      if (openDocuments.size === 0) {
        updateStatus('Idle', 'Waiting for Quenyan activity');
      }
    })
  );
}

function deactivate() {
  if (statusBarItem) {
    statusBarItem.dispose();
  }
  openDocuments.clear();
}

module.exports = {
  activate,
  deactivate,
};
