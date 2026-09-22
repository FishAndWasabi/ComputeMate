const vscode = require('vscode');
const fs = require('node:fs/promises');
const path = require('node:path');
const assert = require('node:assert/strict');

exports.run = async function () {
  const root = process.env.CLOUD_SERVERS_TEST_ROOT;
  const extension = vscode.extensions.getExtension('cloud-server-skills.cloud-server-skills');
  assert(extension);
  await vscode.workspace.getConfiguration('cloudServers').update('pythonPath', process.env.CLOUD_SERVERS_TEST_PYTHON, vscode.ConfigurationTarget.Global);
  await extension.activate();
  const commands = await vscode.commands.getCommands();
  assert(commands.includes('cloudServers.initialize'));
  let records = [];
  for (const name of ['Project-A', 'Project-B']) {
    const folder = vscode.workspace.workspaceFolders.find(f => f.name === name);
    assert(folder, name);
    await vscode.commands.executeCommand('cloudServers.open', folder.uri);
    let proof;
    for (let i = 0; i < 200; i++) {
      try { records = (await fs.readFile(path.join(root, 'requests.jsonl'), 'utf8')).trim().split('\n').filter(Boolean).map(JSON.parse); } catch {}
      proof = records.find(r => r.operation === 'snapshot' && r.scope?.name === name);
      if (proof) break;
      await new Promise(resolve => setTimeout(resolve, 100));
    }
    assert(proof?.ok, 'Bound snapshot for ' + name);
    assert.deepEqual(proof.servers, [name], 'Same server ID stays isolated by project');
    assert(proof.argv.includes('--workspace'));
    assert.equal(proof.scope.root, await fs.realpath(folder.uri.fsPath));
  }
  assert(records.filter(r => r.operation === 'operations').length >= 4);
  assert(!await fs.stat(path.join(root, 'wrong-global.sqlite3')).catch(() => null), 'Inherited global DB is never touched');
  await fs.writeFile(path.join(root, 'result.json'), JSON.stringify({activated: true, webviewRpc: true, projectIsolation: true, projects: records.filter(r => r.operation === 'snapshot').map(r => r.scope.name)}));
  await vscode.commands.executeCommand('workbench.action.closeActiveEditor');
};
