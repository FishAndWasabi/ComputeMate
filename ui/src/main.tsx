import React, { useEffect, useState, useCallback, useRef } from "react";
import { createRoot } from "react-dom/client";
import { invoke, setToken, type Envelope } from "./bridge";
import { presentResult, statusOf } from "./presentation";
import "./style.css";

type Field = {
  type: string;
  description: string;
  required: boolean;
  default: unknown;
  choices?: string[];
};
type Operation = {
  name: string;
  description: string;
  mutating: boolean;
  fields: Record<string, Field>;
};
type Row = Record<string, any>;
type Snapshot = {
  workspace?: {
    kind: string;
    name: string;
    root: string | null;
    database: string;
  };
  servers: Row[];
  groups: Row[];
  environments: Row[];
  projects: Row[];
  artifacts: Row[];
  native_refs: Row[];
  pagination: { server_total: number };
};
const empty: Snapshot = {
  servers: [],
  groups: [],
  environments: [],
  projects: [],
  artifacts: [],
  native_refs: [],
  pagination: { server_total: 0 },
};
const categories: Record<string, string> = {
  server: "服务器",
  group: "分组",
  environment: "环境",
  project: "项目",
  fs: "代码与文件",
  exec: "执行命令",
  tmux: "tmux 会话",
  slurm: "Slurm 作业",
  artifact: "实验产物",
  sync: "代码同步",
  transfer: "文件传输",
  inventory: "台账导入导出",
  probe: "刷新探测",
  capabilities: "可用工具",
  snapshot: "总览快照",
  operations: "接口说明",
  scope: "当前项目",
};
const labels: Record<string, string> = {
  data: "记录内容",
  id: "记录 ID",
  server: "服务器",
  name: "会话名",
  path: "远程路径",
  local: "本地路径",
  remote: "远程路径",
  cwd: "工作目录",
  environment: "已有环境",
  argv: "命令参数",
  script: "Shell 脚本",
  patch: "补丁内容",
  direction: "同步方向",
  apply: "实际应用更改",
  delete: "删除目的端额外文件",
  exclude: "排除规则",
  refresh: "连接服务器刷新",
  archived: "包含归档记录",
  revision: "预期版本号",
  query: "搜索",
  group: "分组",
  limit: "结果数量",
  offset: "跳过数量",
  max_bytes: "输出字节上限",
  timeout: "超时秒数",
  job: "Slurm Job ID",
  options: "sbatch 选项",
  stream: "日志类型",
  lines: "日志行数",
  start: "起始行",
  end: "结束行",
  paths: "虚拟环境路径",
  pattern: "搜索表达式",
  log_path: "日志路径",
  document: "导入台账",
  overwrite: "覆盖同 ID 记录",
  expected_revision: "预期 Git 提交",
  expected_hashes: "预期文件 SHA-256",
  user: "用户",
  label: "标签",
  min_gpus: "最少 GPU 数量",
  min_gpu_memory_mib: "每卡剩余显存 MiB",
  min_memory_gib: "剩余内存 GiB",
  max_gpu_utilization: "GPU 占用率上限",
  include_stale: "包含过期快照",
};
const examples: Record<string, Row> = {
  server: {
    name: "GPU 实验服务器",
    ssh: { alias: "gpu-lab" },
    role: "compute",
    groups: [],
    labels: [],
  },
  group: { name: "实验组", description: "" },
  environment: {
    name: "PyTorch",
    server: "",
    type: "conda",
    selector: "torch",
  },
  project: {
    name: "实验项目",
    local_path: "",
    placements: [{ server: "", path: "/workspace/project" }],
  },
  artifact: {
    name: "Checkpoint",
    server: "",
    path: "/workspace/outputs/model.pt",
    type: "checkpoint",
  },
};
const time = (value?: string) =>
  value
    ? new Date(value).toLocaleString("zh-CN", { hour12: false })
    : "尚未探测";
const gib = (n?: number) =>
  n == null ? "—" : `${(n / 1024 ** 3).toFixed(1)} GiB`;

const actionNames: Record<string, string> = {
  "server.select": "筛选可用资源",
  probe: "刷新状态",
  capabilities: "查看可用工具",
  exec: "执行命令",
  snapshot: "查看全部记录",
  scope: "查看当前项目",
  operations: "查看接口说明",
  "environment.discover": "发现环境",
  "project.status": "查看 Git 状态",
  "fs.list": "浏览文件",
  "fs.read": "读取文件",
  "fs.search": "搜索代码",
  "fs.patch": "应用补丁",
  sync: "同步文件",
  "transfer.get": "下载文件",
  "transfer.put": "上传文件",
  "artifact.fetch": "取回产物",
  "tmux.start": "启动会话",
  "tmux.list": "查询会话",
  "tmux.show": "查看会话",
  "tmux.logs": "读取会话日志",
  "tmux.stop": "结束会话",
  "slurm.submit": "提交作业",
  "slurm.list": "查询队列",
  "slurm.resources": "查询集群资源",
  "slurm.show": "查看作业",
  "slurm.logs": "读取作业日志",
  "slurm.cancel": "取消作业",
  "inventory.export": "导出台账",
  "inventory.import": "导入台账",
};
function actionName(name: string) {
  const [kind, verb] = name.split(".");
  return (
    actionNames[name] ||
    `${({ add: "添加", update: "编辑", get: "查看", remove: "归档", list: "查询" } as Row)[verb] || ""}${categories[kind] || name}`
  );
}
function Status({ server }: { server: Row }) {
  const status = statusOf(server);
  return (
    <span
      className={
        "status " +
        (status === "可达" ? "green" : status === "连接异常" ? "red" : "")
      }
    >
      <i />
      {status}
    </span>
  );
}
function Dialog({
  children,
  title,
  onClose,
  busy = false,
  drawer = false,
}: {
  children: React.ReactNode;
  title: string;
  onClose: () => void;
  busy?: boolean;
  drawer?: boolean;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current!;
    dialog.showModal();
    return () => dialog.close();
  }, []);
  return (
    <dialog
      ref={ref}
      className={drawer ? "detail-drawer" : "modal"}
      aria-label={title}
      onCancel={(e) => {
        e.preventDefault();
        if (!busy) onClose();
      }}
      onClick={(e) => {
        const r = e.currentTarget.getBoundingClientRect();
        if (
          !busy &&
          (e.clientX < r.left ||
            e.clientX > r.right ||
            e.clientY < r.top ||
            e.clientY > r.bottom)
        )
          onClose();
      }}
    >
      {children}
    </dialog>
  );
}
function Result({
  value,
  mutating,
}: {
  value: Envelope | null;
  mutating: boolean;
}) {
  if (!value) return null;
  const { failed, data, title, message, guidance } = presentResult(value);
  return (
    <div className={"result " + (failed ? "failed" : "")} role="status">
      <strong>{title}</strong>
      {message && <p>{message}</p>}
      {guidance && <p>{guidance}</p>}
      {data?.stdout !== undefined && (!failed || data.stdout) ? (
        <pre>{data.stdout || "（无输出）"}</pre>
      ) : !failed && data?.content !== undefined ? (
        <pre>{data.content || "（空文件）"}</pre>
      ) : !failed && mutating && data?.name && data?.id ? (
        <p>已保存：{data.name}</p>
      ) : (
        !failed && <pre>{JSON.stringify(data, null, 2)}</pre>
      )}
      {data?.stderr && <pre className="stderr">{data.stderr}</pre>}
      {failed && data?.exit_code != null && <p>退出码：{data.exit_code}</p>}
      {data?.truncated && <p>输出已截断，可缩小查询范围或增加输出上限。</p>}
      <details>
        <summary>原始结果</summary>
        <pre>{JSON.stringify(value, null, 2)}</pre>
      </details>
    </div>
  );
}

function App() {
  const [snapshot, setSnapshot] = useState<Snapshot>(empty);
  const [operations, setOperations] = useState<Operation[]>([]);
  const [selection, setSelection] = useState("");
  const [group, setGroup] = useState("");
  const [query, setQuery] = useState("");
  const [detailTab, setDetailTab] = useState("resources");
  const [showTools, setShowTools] = useState(false);
  const [active, setActive] = useState<Operation | null>(null);
  const [fields, setFields] = useState<Row>({});
  const [simpleServer, setSimpleServer] = useState({
    name: "",
    alias: "",
    group: "",
  });
  const [rawServer, setRawServer] = useState(false);
  const [output, setOutput] = useState<Envelope | null>(null);
  const [busy, setBusy] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [initialized, setInitialized] = useState(false);
  const [auto, setAuto] = useState(false);
  const [message, setMessage] = useState("");
  const [formMessage, setFormMessage] = useState("");
  const [unauthorized, setUnauthorized] = useState(false);
  const [token, setTokenInput] = useState("");
  const [category, setCategory] = useState("server");

  const load = useCallback(async (refresh = false) => {
    setRefreshing(true);
    try {
      const r = await invoke<Snapshot>("snapshot", { refresh, limit: 1000 });
      if (!r.ok) {
        setUnauthorized(r.error?.code === "unauthorized");
        setMessage(r.error?.code === "unauthorized"
          ? "访问令牌无效或已过期。请重新打开启动命令输出的完整链接，或在下方填写令牌。"
          : r.error?.message || "读取失败");
      } else {
        setSnapshot(r.data);
        setUnauthorized(false);
        setMessage("");
      }
    } catch (e) {
      setMessage(String(e));
    } finally {
      setRefreshing(false);
      setInitialized(true);
    }
  }, []);
  const initialize = useCallback(async () => {
    try {
      const r = await invoke<{ operations: Operation[] }>("operations");
      if (r.ok) setOperations(r.data.operations);
      await load();
    } catch (e) {
      setMessage(String(e));
      setInitialized(true);
    }
  }, [load]);
  useEffect(() => {
    void initialize();
  }, [initialize]);
  useEffect(() => {
    if (!auto) return;
    const id = window.setInterval(() => {
      if (!document.hidden && !refreshing && !busy) void load(true);
    }, 30000);
    return () => clearInterval(id);
  }, [auto, load, refreshing, busy]);

  function open(name: string, initial: Row = {}) {
    const op = operations.find((o) => o.name === name);
    if (!op) return;
    const defaults: Row = {};
    for (const [key, f] of Object.entries(op.fields)) {
      defaults[key] =
        f.default != null
          ? ["object", "array"].includes(f.type)
            ? JSON.stringify(f.default, null, 2)
            : f.default
          : f.type === "boolean"
            ? false
            : "";
    }
    if ("server" in op.fields && selection) defaults.server = selection;
    if (op.fields.data) {
      const example = structuredClone(examples[name.split(".")[0]] || {});
      if ("server" in example) example.server = selection;
      if (name === "project.add" && selection)
        example.placements[0].server = selection;
      defaults.data = JSON.stringify(example, null, 2);
    }
    setFields({ ...defaults, ...initial });
    setActive(op);
    setOutput(null);
    setFormMessage("");
    setSimpleServer({ name: "", alias: "", group });
    setRawServer(false);
    setShowTools(false);
  }
  async function run(event: React.FormEvent) {
    event.preventDefault();
    if (!active) return;
    setBusy(true);
    setFormMessage("");
    setOutput(null);
    try {
      const args: Row = {};
      if (active.name === "server.add" && !rawServer) {
        args.data = {
          name: simpleServer.name.trim(),
          ssh: { alias: simpleServer.alias.trim() },
          role: "compute",
          groups: simpleServer.group ? [simpleServer.group] : [],
        };
      } else {
        for (const [key, f] of Object.entries(active.fields)) {
          const value = fields[key];
          if (value === "" || value == null) continue;
          if (["object", "array"].includes(f.type)) {
            try {
              args[key] = JSON.parse(value);
            } catch {
              throw new Error(`${labels[key] || key}需要有效的 JSON，请检查双引号、逗号和括号。`);
            }
          } else {
            args[key] = f.type === "integer" ? Number(value) : value;
          }
        }
      }
      const r = await invoke(active.name, args);
      setOutput(r);
      if (r.ok) await load();
    } catch (e) {
      setFormMessage(String(e));
    } finally {
      setBusy(false);
    }
  }
  const servers = snapshot.servers.filter(
    (s) =>
      (!group || s.groups?.includes(group)) &&
      [s.name, s.id, s.ssh?.alias, s.ssh?.host, ...(s.labels || [])]
        .join(" ")
        .toLowerCase()
        .includes(query.toLowerCase()),
  );
  const server = snapshot.servers.find((s) => s.id === selection);
  const sample = server?.observations?.hardware;
  const hardware = sample?.data;
  const rows = (
    key: "environments" | "projects" | "artifacts" | "native_refs",
  ) =>
    snapshot[key].filter(
      (r) =>
        r.server === selection ||
        r.placements?.some((p: Row) => p.server === selection),
    );
  const related = {
    environments: rows("environments"),
    projects: rows("projects"),
    artifacts: rows("artifacts"),
    native_refs: rows("native_refs"),
  };
  const mainFields = new Set([
    "server",
    "cwd",
    "environment",
    "script",
    "path",
    "start",
    "end",
    "query",
    "pattern",
    "direction",
    "local",
    "remote",
    "apply",
    "delete",
    "options",
    "log_path",
  ]);
  const advancedField = (key: string, f: Field) =>
    !f.required && !mainFields.has(key);
  function renderField([key, f]: [string, Field]) {
    return (
      <label
        key={key}
        className={
          ["object", "array"].includes(f.type) ||
          ["script", "patch"].includes(key)
            ? "wide"
            : ""
        }
      >
        <span>
          {labels[key] || key}
          {f.required && <em> *</em>}
        </span>
        {f.type === "boolean" ? (
          <input
            type="checkbox"
            checked={Boolean(fields[key])}
            onChange={(e) => setFields({ ...fields, [key]: e.target.checked })}
          />
        ) : f.choices ? (
          <select
            value={fields[key]}
            onChange={(e) => setFields({ ...fields, [key]: e.target.value })}
          >
            <option value="">请选择</option>
            {f.choices.map((c) => (
              <option key={c}>{c}</option>
            ))}
          </select>
        ) : key === "server" || key === "environment" ? (
          <select
            value={fields[key]}
            onChange={(e) => setFields({ ...fields, [key]: e.target.value })}
          >
            <option value="">
              {key === "environment" ? "默认环境" : "请选择"}
            </option>
            {(key === "server"
              ? snapshot.servers
              : snapshot.environments.filter(
                  (s) => !fields.server || s.server === fields.server,
                )
            ).map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
        ) : ["object", "array"].includes(f.type) ||
          ["script", "patch"].includes(key) ? (
          <textarea
            spellCheck={false}
            rows={key === "data" || key === "patch" ? 9 : 4}
            value={fields[key]}
            onChange={(e) => setFields({ ...fields, [key]: e.target.value })}
          />
        ) : (
          <input
            type={f.type === "integer" ? "number" : "text"}
            value={fields[key]}
            onChange={(e) => setFields({ ...fields, [key]: e.target.value })}
          />
        )}
        {["object", "array"].includes(f.type) && <small>JSON 格式</small>}
        {key === "script" && <small>由远端 Shell 解释执行。</small>}
      </label>
    );
  }
  return (
    <div className="app">
      <header className="topbar">
        <span className="brand">
          <img className="brand-mark" src="./computemate-icon.png" alt="" width="28" height="28" /> ComputeMate
          {snapshot.workspace && (
            <small
              className="workspace-name"
              title={snapshot.workspace.root || snapshot.workspace.database}
            >
              {snapshot.workspace.kind === "project"
                ? snapshot.workspace.name
                : "独立台账"}
            </small>
          )}
        </span>
        <button className="quiet" disabled={!operations.length || unauthorized} onClick={() => setShowTools(true)}>
          更多操作
        </button>
      </header>
      <main className="content">
        <div className="page-heading">
          <h1>
            服务器 <span>{snapshot.pagination.server_total}</span>
          </h1>
          <div className="actions">
            <button
              disabled={refreshing || busy}
              onClick={() => void load(true)}
            >
              {refreshing ? "刷新中…" : "刷新状态"}
            </button>
            <button className="primary" disabled={!snapshot.workspace || unauthorized} onClick={() => open("server.add")}>
              添加服务器
            </button>
          </div>
        </div>
        {message && (
          <div className="notice" role="alert">
            {message}
          </div>
        )}
        {unauthorized && (
          <form
            className="token-form"
            onSubmit={(e) => {
              e.preventDefault();
              setToken(token);
              void initialize();
            }}
          >
            <label>
              本地服务访问令牌
              <input
                type="password"
                value={token}
                onChange={(e) => setTokenInput(e.target.value)}
              />
            </label>
            <button className="primary">连接</button>
          </form>
        )}
        <div className="filters">
          <input
            className="search"
            placeholder="搜索服务器…"
            aria-label="搜索服务器"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <select
            aria-label="筛选分组"
            value={group}
            onChange={(e) => setGroup(e.target.value)}
          >
            <option value="">全部分组</option>
            {snapshot.groups.map((g) => (
              <option key={g.id} value={g.id}>
                {g.name}
              </option>
            ))}
          </select>
        </div>
        <div className="fleet">
          {!initialized ? (
            <div className="empty-state">正在读取…</div>
          ) : message && !snapshot.workspace ? (
            <div className="empty-state">
              <h2>暂时无法读取台账</h2>
              <p>连接成功后会显示当前项目的服务器。</p>
              {!unauthorized && <button onClick={() => void initialize()}>重新连接</button>}
            </div>
          ) : servers.length ? (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>服务器</th>
                    <th>状态</th>
                    <th>资源</th>
                    <th>分组</th>
                  </tr>
                </thead>
                <tbody>
                  {servers.map((s) => {
                    const hw = s.observations?.hardware?.data;
                    return (
                      <tr
                        key={s.id}
                        onClick={() => {
                          setSelection(s.id);
                          setDetailTab("resources");
                        }}
                      >
                        <td>
                          <button
                            className="server-link"
                            onClick={() => {
                              setSelection(s.id);
                              setDetailTab("resources");
                            }}
                          >
                            {s.name}
                          </button>
                          <small>{s.ssh?.alias || s.ssh?.host}</small>
                        </td>
                        <td>
                          <Status server={s} />
                        </td>
                        <td>
                          {s.role === "login"
                            ? "集群登录节点"
                            : hw
                              ? `${hw.cpu_count ?? "—"} CPU · ${gib(hw.memory?.MemTotal)}`
                              : "—"}
                          {hw?.gpus?.length > 0 && (
                            <small>
                              {hw.gpus.length} GPU ·{" "}
                              {[
                                ...new Set(hw.gpus.map((g: Row) => g.name)),
                              ].join(", ")}
                            </small>
                          )}
                        </td>
                        <td className="muted">
                          {(s.groups || [])
                            .map(
                              (id: string) =>
                                snapshot.groups.find((g) => g.id === id)
                                  ?.name || id,
                            )
                            .join("、") || "—"}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="empty-state">
              <h2>
                {query || group ? "没有匹配的服务器" : "添加你的第一台服务器"}
              </h2>
              <p>
                {query || group
                  ? "试试其他名称或分组。"
                  : "使用已有 SSH 连接开始。"}
              </p>
              <button
                onClick={() => {
                  if (query || group) {
                    setQuery("");
                    setGroup("");
                  } else open("server.add");
                }}
              >
                {query || group ? "清除筛选" : "添加服务器"}
              </button>
            </div>
          )}
        </div>
        <div className="list-footer">
          <span>状态来自最近一次探测</span>
          <label>
            <input
              type="checkbox"
              checked={auto}
              onChange={(e) => setAuto(e.target.checked)}
            />
            每 30 秒刷新
          </label>
        </div>
        {snapshot.pagination.server_total > snapshot.servers.length && (
          <p className="notice">
            当前显示前 {snapshot.servers.length}{" "}
            台服务器；可在更多操作中分页查询。
          </p>
        )}
      </main>
      {server && (
        <Dialog drawer title={server.name} onClose={() => setSelection("")}>
          <div className="dialog-header">
            <div>
              <h2>{server.name}</h2>
              <small>{server.ssh?.alias || server.ssh?.host}</small>
            </div>
            <button
              className="quiet close"
              aria-label="关闭详情"
              onClick={() => setSelection("")}
            >
              ×
            </button>
          </div>
          <div className="detail-summary">
            <Status server={server} />
            <small>
              {sample?.observed_at
                ? `最近探测 ${time(sample.observed_at)}`
                : "尚未探测"}
            </small>
          </div>
          <nav className="detail-tabs" aria-label="服务器详情">
            {[
              ["resources", "概况"],
              ["environments", "环境"],
              ["projects", "项目"],
              ["native_refs", "会话与作业"],
              ["artifacts", "产物"],
            ].map(([id, label]) => (
              <button
                key={id}
                aria-current={detailTab === id ? "page" : undefined}
                onClick={() => setDetailTab(id)}
              >
                {label}
              </button>
            ))}
          </nav>
          <div className="detail-body">
            {detailTab === "resources" ? (
              <>
                <div className="actions">
                  <button className="primary" onClick={() => open("exec")}>
                    执行命令
                  </button>
                  <button onClick={() => open("probe")}>刷新此服务器</button>
                  <button
                    onClick={() =>
                      open("server.update", {
                        id: server.id,
                        revision: server.revision,
                        data: JSON.stringify(
                          Object.fromEntries(
                            Object.entries(server).filter(
                              ([k]) =>
                                ![
                                  "id",
                                  "revision",
                                  "updated_at",
                                  "archived",
                                  "observations",
                                ].includes(k),
                            ),
                          ),
                          null,
                          2,
                        ),
                      })
                    }
                  >
                    编辑
                  </button>
                </div>
                {sample?.error && (
                  <div className="notice">
                    <p>{sample.error.message}</p>
                    {sample.error.details?.stderr && <pre>{sample.error.details.stderr}</pre>}
                  </div>
                )}
                <dl className="facts">
                  <div>
                    <dt>CPU</dt>
                    <dd>{hardware?.cpu_count ?? "—"}</dd>
                  </div>
                  <div>
                    <dt>可用内存 / 总内存</dt>
                    <dd>
                      {gib(hardware?.memory?.MemAvailable)} /{" "}
                      {gib(hardware?.memory?.MemTotal)}
                    </dd>
                  </div>
                  <div>
                    <dt>用途</dt>
                    <dd>{server.purpose || "—"}</dd>
                  </div>
                </dl>
                {server.role === "login" && (
                  <p className="muted">
                    以上为登录节点资源。
                    <button
                      className="text-button"
                      onClick={() => open("slurm.resources")}
                    >
                      查询集群资源
                    </button>
                  </p>
                )}
                {hardware?.gpus?.map((g: Row) => (
                  <div className="gpu" key={g.index}>
                    <div>
                      <strong>
                        GPU {g.index} · {g.name}
                      </strong>
                      <small>
                        {g.memory_used_mib ?? "—"} / {g.memory_total_mib ?? "—"}{" "}
                        MiB
                      </small>
                    </div>
                    <progress
                      max={g.memory_total_mib || 1}
                      value={g.memory_used_mib || 0}
                    />
                    <small>利用率 {g.utilization_percent ?? "—"}%</small>
                  </div>
                ))}
                {server.notes && <p>{server.notes}</p>}
                {!!server.labels?.length && (
                  <p className="muted">标签：{server.labels.join("、")}</p>
                )}
                <details>
                  <summary>连接与探测详情</summary>
                  <pre>
                    {JSON.stringify(
                      { ssh: server.ssh, observations: server.observations },
                      null,
                      2,
                    )}
                  </pre>
                </details>
              </>
            ) : detailTab === "native_refs" ? (
              <>
                <div className="actions">
                  <button onClick={() => open("tmux.start")}>启动会话</button>
                  <button onClick={() => open("slurm.submit")}>提交作业</button>
                  <button onClick={() => open("tmux.list")}>查询会话</button>
                  <button onClick={() => open("slurm.list")}>查询队列</button>
                </div>
                {related.native_refs.length ? (
                  related.native_refs.map((r) => (
                    <button
                      className="record"
                      key={r.id}
                      onClick={() =>
                        open(r.backend + ".show", {
                          server: r.server,
                          ...(r.backend === "tmux"
                            ? { name: r.native_id }
                            : { job: r.native_id }),
                        })
                      }
                    >
                      <strong>{r.native_id}</strong>
                      <small>{r.backend}</small>
                      <span>›</span>
                    </button>
                  ))
                ) : (
                  <p className="empty-note">暂无登记的会话或作业</p>
                )}
              </>
            ) : (
              <>
                <div className="actions">
                  <button
                    onClick={() =>
                      open(
                        (
                          {
                            environments: "environment.add",
                            projects: "project.add",
                            artifacts: "artifact.add",
                          } as Row
                        )[detailTab],
                      )
                    }
                  >
                    添加
                    {
                      (
                        {
                          environments: "环境",
                          projects: "项目",
                          artifacts: "产物",
                        } as Row
                      )[detailTab]
                    }
                  </button>
                  {detailTab === "environments" && (
                    <button onClick={() => open("environment.discover")}>
                      发现环境
                    </button>
                  )}
                  {detailTab === "projects" && (
                    <>
                      <button onClick={() => open("fs.list")}>浏览文件</button>
                      <button onClick={() => open("sync")}>同步文件</button>
                    </>
                  )}
                </div>
                <Collection
                  rows={
                    related[
                      detailTab as "environments" | "projects" | "artifacts"
                    ]
                  }
                  action={(r) =>
                    open(
                      (
                        {
                          environments: "environment.get",
                          projects: "project.get",
                          artifacts: "artifact.get",
                        } as Row
                      )[detailTab],
                      { id: r.id },
                    )
                  }
                />
              </>
            )}
          </div>
        </Dialog>
      )}
      {showTools && (
        <Dialog title="更多操作" onClose={() => setShowTools(false)}>
          <div className="dialog-header">
            <h2>更多操作</h2>
            <button
              className="quiet close"
              aria-label="关闭更多操作"
              onClick={() => setShowTools(false)}
            >
              ×
            </button>
          </div>
          <div className="tools-body">
            <select
              aria-label="操作类别"
              value={category}
              onChange={(e) => setCategory(e.target.value)}
            >
              {Object.entries(categories).map(([key, label]) => (
                <option key={key} value={key}>
                  {label}
                </option>
              ))}
            </select>
            <div className="tool-list">
              {operations
                .filter((o) => o.name.split(".")[0] === category)
                .map((op) => (
                  <button key={op.name} onClick={() => open(op.name)}>
                    <span>{actionName(op.name)}</span>
                    <small>{op.name}</small>
                    <span>›</span>
                  </button>
                ))}
            </div>
          </div>
        </Dialog>
      )}
      {active && (
        <Dialog
          title={actionName(active.name)}
          busy={busy}
          onClose={() => setActive(null)}
        >
          <div className="dialog-header">
            <h2>{actionName(active.name)}</h2>
            <button
              className="quiet close"
              disabled={busy}
              aria-label="关闭操作"
              onClick={() => setActive(null)}
            >
              ×
            </button>
          </div>
          <form onSubmit={run}>
            <fieldset disabled={busy} onChange={() => setOutput(null)}>
              {active.name === "server.add" && !rawServer ? (
                <>
                  <div className="form-fields">
                    <label className="wide">
                      名称
                      <input
                        autoFocus
                        required
                        value={simpleServer.name}
                        placeholder="例如：GPU 实验节点"
                        onChange={(e) =>
                          setSimpleServer({
                            ...simpleServer,
                            name: e.target.value,
                          })
                        }
                      />
                    </label>
                    <label className="wide">
                      SSH 连接
                      <input
                        required
                        value={simpleServer.alias}
                        placeholder="例如：gpu-lab"
                        onChange={(e) =>
                          setSimpleServer({
                            ...simpleServer,
                            alias: e.target.value,
                          })
                        }
                      />
                      <small>填写 SSH 配置中已有的别名。</small>
                    </label>
                    <label className="wide">
                      分组
                      <select
                        value={simpleServer.group}
                        onChange={(e) =>
                          setSimpleServer({
                            ...simpleServer,
                            group: e.target.value,
                          })
                        }
                      >
                        <option value="">未分组</option>
                        {snapshot.groups.map((g) => (
                          <option key={g.id} value={g.id}>
                            {g.name}
                          </option>
                        ))}
                      </select>
                    </label>
                  </div>
                  <button
                    type="button"
                    className="text-button advanced-toggle"
                    onClick={() => {
                      setFields({
                        ...fields,
                        data: JSON.stringify(
                          {
                            name: simpleServer.name,
                            ssh: { alias: simpleServer.alias },
                            role: "compute",
                            groups: simpleServer.group
                              ? [simpleServer.group]
                              : [],
                          },
                          null,
                          2,
                        ),
                      });
                      setRawServer(true);
                    }}
                  >
                    使用 JSON 编辑更多字段
                  </button>
                </>
              ) : (
                <>
                  <div className="form-fields">
                    {Object.entries(active.fields)
                      .filter(([key, f]) => !advancedField(key, f))
                      .map(renderField)}
                  </div>
                  {Object.entries(active.fields).some(([key, f]) =>
                    advancedField(key, f),
                  ) && (
                    <details className="advanced-fields">
                      <summary>更多参数</summary>
                      <div className="form-fields">
                        {Object.entries(active.fields)
                          .filter(([key, f]) => advancedField(key, f))
                          .map(renderField)}
                      </div>
                    </details>
                  )}
                </>
              )}
              {formMessage && (
                <p className="notice" role="alert">
                  {formMessage}
                </p>
              )}
              <div className="form-actions">
                <button type="button" onClick={() => setActive(null)}>
                  关闭
                </button>
                <button className="primary" disabled={Boolean(output?.ok && active.mutating)}>
                  {busy
                    ? "执行中…"
                    : output?.ok && active.mutating
                      ? "已完成"
                      : active.name.endsWith(".add") ||
                        active.name.endsWith(".update")
                      ? "保存"
                      : active.mutating
                        ? "执行"
                        : "查询"}
                </button>
              </div>
            </fieldset>
          </form>
          <Result value={output} mutating={active.mutating} />
        </Dialog>
      )}
    </div>
  );
}
function Collection({
  rows,
  action,
}: {
  rows: Row[];
  action: (row: Row) => void;
}) {
  return rows.length ? (
    <div>
      {rows.map((r) => (
        <button className="record" key={r.id} onClick={() => action(r)}>
          <strong>{r.name}</strong>
          <small>{r.selector || r.path || r.repo_url || r.id}</small>
          <span>›</span>
        </button>
      ))}
    </div>
  ) : (
    <p className="empty-note">暂无记录</p>
  );
}
createRoot(document.getElementById("root")!).render(<App />);
