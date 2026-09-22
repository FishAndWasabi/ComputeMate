import * as vscode from "vscode";
import { spawn } from "node:child_process";
import { readFile } from "node:fs/promises";

type Response = {
  schema_version: number;
  ok: boolean;
  data: any;
  error: { code: string; message: string } | null;
  meta: { observed_at: string };
};
const failure = (message: string): Response => ({
  schema_version: 1,
  ok: false,
  data: null,
  error: { code: "extension_error", message },
  meta: { observed_at: new Date().toISOString() },
});

export function activate(context: vscode.ExtensionContext) {
  let panel: vscode.WebviewPanel | undefined;
  let panelBinding = "";
  type Binding = { python: string; db?: string; root?: string; name: string };

  function binding(folder?: vscode.WorkspaceFolder): Binding {
    const config = vscode.workspace.getConfiguration(
      "cloudServers",
      folder?.uri,
    );
    return {
      python: config.get<string>("pythonPath", "python3"),
      db: config.get<string>("databasePath") || undefined,
      root: folder?.uri.fsPath,
      name: folder?.name || "独立台账",
    };
  }

  async function chooseFolder(resource?: vscode.Uri) {
    if (resource) return vscode.workspace.getWorkspaceFolder(resource);
    const folders = vscode.workspace.workspaceFolders || [];
    return folders.length === 1
      ? folders[0]
      : folders.length > 1
        ? await vscode.window.showWorkspaceFolderPick({
            placeHolder: "选择 ComputeMate 绑定的项目",
          })
        : undefined;
  }
  const children = new Set<ReturnType<typeof spawn>>();

  function run(
    operation: string,
    args: Record<string, unknown> = {},
    scope: Binding = binding(),
  ): Promise<Response> {
    if (!scope.root && !scope.db && operation !== "operations")
      return Promise.resolve(
        failure(
          "Open a project folder or explicitly configure its databasePath.",
        ),
      );
    const python = scope.python;
    const script = vscode.Uri.joinPath(
      context.extensionUri,
      "resources",
      "runtime",
      "cloud_servers.py",
    ).fsPath;
    const selection = scope.db
      ? ["--db", scope.db]
      : scope.root
        ? ["--workspace", scope.root]
        : [];
    return new Promise((resolve) => {
      const child = spawn(
        python,
        [
          script,
          ...selection,
          ...(operation === "init" ? ["--json", "init"] : ["rpc"]),
        ],
        { stdio: ["pipe", "pipe", "pipe"], shell: false, cwd: scope.root },
      );
      children.add(child);
      let stdout = "",
        stderr = "",
        finished = false;
      const finish = (value: Response) => {
        if (!finished) {
          finished = true;
          clearTimeout(timer);
          children.delete(child);
          resolve(value);
        }
      };
      const timeout = Math.max(
        300_000,
        (Number(args.timeout) || 60) * 1000 + 15000,
      );
      const timer = setTimeout(() => {
        child.kill();
        finish(
          failure(
            "Local bridge timed out; remote outcome may be unknown. Query native status before retrying.",
          ),
        );
      }, timeout);
      child.stdout.on("data", (chunk: Buffer) => {
        stdout += chunk.toString();
        if (stdout.length > 12 * 1024 * 1024) {
          child.kill();
          finish(
            failure(
              "Response exceeds the bridge output limit. Narrow the query.",
            ),
          );
        }
      });
      child.stderr.on("data", (chunk: Buffer) => {
        stderr = (stderr + chunk.toString()).slice(-65536);
      });
      child.on("error", (error) => finish(failure(error.message)));
      child.on("close", () => {
        try {
          finish(JSON.parse(stdout));
        } catch {
          finish(
            failure(
              stderr ||
                "Python returned no valid JSON. Check Python 3.11+ and extension settings.",
            ),
          );
        }
      });
      child.stdin.on("error", () => {});
      child.stdin.end(JSON.stringify({ operation, arguments: args }));
    });
  }

  class Inventory implements vscode.TreeDataProvider<vscode.TreeItem> {
    private changed = new vscode.EventEmitter<vscode.TreeItem | undefined>();
    readonly onDidChangeTreeData = this.changed.event;
    refresh() {
      this.changed.fire(undefined);
    }
    getTreeItem(item: vscode.TreeItem) {
      return item;
    }
    async getChildren(parent?: vscode.TreeItem) {
      const folders = vscode.workspace.workspaceFolders || [];
      if (!parent && folders.length > 1)
        return folders.map((folder) => {
          const item = new vscode.TreeItem(
            folder.name,
            vscode.TreeItemCollapsibleState.Collapsed,
          );
          item.resourceUri = folder.uri;
          return item;
        });
      const folder = parent?.resourceUri
        ? vscode.workspace.getWorkspaceFolder(parent.resourceUri)
        : folders[0];
      const response = await run("snapshot", { limit: 1000 }, binding(folder));
      if (!response.ok)
        return [
          new vscode.TreeItem(
            response.error?.message || "Unable to load inventory",
          ),
        ];
      if (!response.data.servers.length) {
        const item = new vscode.TreeItem("添加第一台服务器");
        item.command = {
          command: "cloudServers.open",
          title: "Open",
          arguments: [folder?.uri],
        };
        return [item];
      }
      return response.data.servers.map((s: any) => {
        const item = new vscode.TreeItem(s.name);
        item.description = s.ssh.alias || s.ssh.host;
        item.tooltip = `${s.id}\n${s.purpose || ""}\n${s.observations?.hardware?.observed_at || "尚未探测"}`;
        item.iconPath = new vscode.ThemeIcon("server");
        item.command = {
          command: "cloudServers.open",
          title: "Open server",
          arguments: [folder?.uri],
        };
        return item;
      });
    }
  }
  const inventory = new Inventory();
  context.subscriptions.push(
    vscode.window.registerTreeDataProvider("cloudServers.inventory", inventory),
  );

  async function open(resource?: vscode.Uri) {
    const folder = await chooseFolder(resource);
    if (!folder && (vscode.workspace.workspaceFolders?.length || 0) > 1) return;
    const selected = binding(folder);
    const key = JSON.stringify(selected);
    if (panel && panelBinding === key) {
      panel.reveal();
      return;
    }
    panel?.dispose();
    panelBinding = key;
    const assets = vscode.Uri.joinPath(
      context.extensionUri,
      "resources",
      "web",
    );
    panel = vscode.window.createWebviewPanel(
      "cloudServers",
      `ComputeMate · ${selected.name}`,
      vscode.ViewColumn.One,
      {
        enableScripts: true,
        localResourceRoots: [assets],
        retainContextWhenHidden: true,
      },
    );
    const current = panel;
    current.onDidDispose(() => {
      if (panel === current) panel = undefined;
    });
    const catalog = await run("operations", {}, selected);
    const operations = new Map<string, any>(
      (catalog.data?.operations || []).map((op: any) => [op.name, op]),
    );
    current.webview.onDidReceiveMessage(
      async (message) => {
        if (
          !message ||
          typeof message.id !== "string" ||
          typeof message.operation !== "string"
        )
          return;
        const spec = operations.get(message.operation);
        let response: Response;
        if (!spec)
          response = failure(
            "Unknown operation or unavailable Python runtime.",
          );
        else if (spec.mutating && !vscode.workspace.isTrusted)
          response = failure(
            "Trust this VS Code workspace before running operations that change state.",
          );
        else
          response = await run(message.operation, message.arguments, selected);
        if (panel === current) {
          await current.webview.postMessage({ id: message.id, response });
        }
        if (response.ok && spec?.mutating) inventory.refresh();
      },
      undefined,
      context.subscriptions,
    );
    try {
      let html = await readFile(
        vscode.Uri.joinPath(assets, "index.html").fsPath,
        "utf8",
      );
      html = html.replace(
        /(src|href)="\.\/([^"]+)"/g,
        (_match, attr, path) =>
          `${attr}="${current.webview.asWebviewUri(vscode.Uri.joinPath(assets, path))}"`,
      );
      const source = current.webview.cspSource;
      const base = current.webview.asWebviewUri(assets).toString() + "/";
      html = html.replace(
        "<head>",
        `<head><meta http-equiv="Content-Security-Policy" content="default-src 'none'; base-uri ${source}; script-src ${source}; style-src ${source} 'unsafe-inline'; img-src ${source} data:; font-src ${source};"><base href="${base}">`,
      );
      current.webview.html = html;
    } catch (error) {
      vscode.window.showErrorMessage(
        `ComputeMate assets unavailable: ${String(error)}`,
      );
    }
  }

  context.subscriptions.push(
    vscode.commands.registerCommand("cloudServers.open", open),
    vscode.commands.registerCommand("cloudServers.initialize", async () => {
      if (!vscode.workspace.isTrusted) {
        vscode.window.showErrorMessage(
          "Trust this workspace before initializing its inventory.",
        );
        return;
      }
      const folder = await chooseFolder();
      if (!folder) return;
      const selected = { ...binding(folder), db: undefined };
      const result = await run("init", {}, selected);
      if (!result.ok)
        vscode.window.showErrorMessage(
          result.error?.message || "Initialization failed",
        );
      else {
        panel?.dispose();
        inventory.refresh();
        await open(folder.uri);
      }
    }),
  );
  context.subscriptions.push(
    vscode.commands.registerCommand("cloudServers.refresh", () =>
      inventory.refresh(),
    ),
  );
  context.subscriptions.push(
    vscode.workspace.onDidChangeConfiguration((e) => {
      if (e.affectsConfiguration("cloudServers")) {
        panel?.dispose();
        inventory.refresh();
      }
    }),
  );
  context.subscriptions.push(
    vscode.workspace.onDidChangeWorkspaceFolders(() => {
      panel?.dispose();
      inventory.refresh();
    }),
  );
  context.subscriptions.push({
    dispose: () => {
      for (const child of children) child.kill();
      panel?.dispose();
    },
  });
}
