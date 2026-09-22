<div align="center">

<img src="docs/assets/computemate-icon.png" alt="ComputeMate 算力管家图标" width="112" height="112" />

# ComputeMate · 算力管家

**少翻终端，多跑实验。**

你的服务器搭子，也是 Agent 的算力工具箱。

按项目管理服务器、代码、环境和实验产物。Agent 来操作，你随时看得见。

[快速开始](#快速开始) · [交给 Agent](#交给-agent) · [可视化](#想自己看也很方便) · [使用指南](docs/usage.md) · [反馈建议](https://github.com/FishAndWasabi/ComputeMate/issues)

`Agent Skill` · `Python 3.11+` · `SSH / tmux / Slurm` · `CLI / Web / VS Code`

</div>

## 实验还没开始，人先被服务器管理跑累了

机器有好几台，项目也不止一个。每天开工先回忆：

- 这次该连哪台机器，哪张卡还有空间？
- 代码在 `/workspace`，还是上次那个目录？
- 这个项目用哪个 Conda 环境？
- 昨晚的任务在哪个 tmux 会话里，日志和 checkpoint 又放哪了？

**ComputeMate 把这些零散信息放进项目自己的台账，再给 Agent 一套能实际调用的工具。**

你描述目标，Agent 查询资源、访问代码、使用已有环境、调用原生任务工具；你也可以直接打开终端、网页或 VS Code 查看。

## 六个让实验少点内耗的理由

| 优点 | 用起来有什么不同 |
| --- | --- |
| 🧠 **给 Agent 一份说明书，也给它工具** | `SKILL.md` 配套可执行脚本和 JSON 接口，能查服务器，也能通过 SSH 执行操作。 |
| 📁 **一个项目，一本账** | 服务器、环境、代码位置和产物关联按项目保存，同名记录互不覆盖。 |
| 🔌 **接着用你的 SSH** | 复用已有 alias、密钥和跳板机；服务器无需安装本项目的常驻程序。 |
| 🛠️ **服务器杂活有统一入口** | 读代码、查 Git、打补丁、预览同步、取回文件、读日志，减少临时拼接脚本。 |
| 👀 **Agent 能用，你也看得懂** | CLI、网页、VS Code 共用操作接口；网页关闭后，Skill 和脚本仍可独立使用。 |
| 🪶 **从一个项目就能开始** | 本地 SQLite 台账，Python 核心只用标准库；先登记一台机器，按需增加能力。 |

## 交给 Agent

让支持读取 Skill、调用 Shell 的 Agent 加载 [ComputeMate Skill](skills/cloud-servers/SKILL.md)，然后像这样提需求：

> “看看当前项目有哪些可连接的 GPU 服务器，按显存情况列出候选，再告诉我依据。”

> “去 gpu01 检查训练代码，只读入口文件前 80 行，核对 Git 状态，再准备补丁。”

> “预览这次代码同步的差异。同步完成后，用已有环境启动指定的 tmux 命令，告诉我会话名和日志路径。”

> “提交这份 Slurm 脚本，保留原生 Job ID，查一下队列和输出日志。”

以上是**请求示例**。实际操作取决于你登记的路径、已有环境、权限和目标机器能力；实验步骤由 Agent 结合项目要求组织。

## 快速开始

客户端需要 **Python 3.11+、OpenSSH**。文件同步使用 `rsync`；Git、tmux、Slurm 按实际功能使用。远端以 Linux/Bash 为基础，macOS 和 Linux 可作客户端，Windows 使用 WSL。

### 1. 获取代码，安装命令

```bash
git clone https://github.com/FishAndWasabi/ComputeMate.git
cd ComputeMate
uv tool install .
```

也可在自己的 Python 虚拟环境中运行 `python3 -m pip install .`。不安装 CLI 时，直接调用 `python3 skills/cloud-servers/scripts/computemate.py --help`。

### 2. 给你的实验项目建一本账

在**实际实验项目目录**运行；下面的 `lab-gpu` 请替换为你能正常连接的 SSH alias。

```bash
cd /path/to/your/experiment
computemate init
computemate server add --id gpu01 \
  --data '{"name":"实验节点","ssh":{"alias":"lab-gpu"},"role":"compute"}'
computemate probe gpu01
computemate server list
```

台账保存到该项目的 `.cloud-servers/`。从其他目录操作时，显式指定项目：

```bash
computemate --workspace /path/to/your/experiment --json snapshot
```

### 3. 把 Skill 接给 Agent

从本仓库运行，将完整 Skill 复制到你的 Agent 支持的目录：

```bash
python3 scripts/package-skill.py --install-to /path/to/agent/skills
```

也可以让 Agent 直接读取仓库中的 [SKILL.md](skills/cloud-servers/SKILL.md)，使用其相对路径下的脚本。自动发现规则由 Agent 宿主决定，公共脚本不依赖特定 Agent 工具名。

## 想自己看，也很方便

| 入口 | 适合什么时候用 |
| --- | --- |
| **CLI** | 快速查询和脚本调用；人看文本，Agent 用 `--json`。 |
| **本地网页** | 看服务器分组、GPU 状态、环境和产物；点开详情再操作。 |
| **VS Code** | 在项目工作区里看同一份台账；多项目分别绑定，Webview 无需另开网页服务。 |

网页首次使用需要构建前端，以下命令从 ComputeMate 仓库运行（Node.js 20.19+）：

```bash
npm ci
npm run build
python3 skills/cloud-servers/scripts/computemate.py \
  --workspace /path/to/your/experiment serve
```

打开终端输出的本机 URL。默认读取最近记录，点击刷新才重新探测；自动刷新可以手动开启。

VS Code 扩展运行 `npm run package:vscode` 构建，在编辑器中通过 **Install from VSIX** 安装 `extensions/vscode/computemate-0.1.0.vsix`。

## 从找机器，到拿回结果

```text
你 / Agent
    │
    ▼
ComputeMate Skill + 公共脚本
    │
    ├── 项目台账：服务器 · 环境 · 代码路径 · 产物
    ├── SSH / rsync：查询 · 执行 · 代码访问 · 文件传输
    └── tmux / Slurm：原生会话 · Job ID · 状态 · 日志
```

| 你要做的事 | ComputeMate 提供的接口 |
| --- | --- |
| 看机器、看 GPU、找候选 | `server` / `probe` / `capabilities` |
| 找代码、读文件、检查 Git、应用补丁 | `project` / `fs` |
| 发现、登记和使用已有环境 | `environment` / `exec` |
| 预览增量同步、上传或取回文件 | `sync` / `transfer` |
| 启动后台会话、提交作业、读取日志 | `tmux` / `slurm` |
| 记录权重、checkpoint、指标与日志位置 | `artifact` |

常用的一条命令：

```bash
# 让 Agent 先了解“这里有什么能力”
computemate --json operations
```

更多可复制命令见 [使用指南](docs/usage.md)，接口细节见 [Skill 参考文档](skills/cloud-servers/references/interfaces.md)。

## 用之前，知道这几件事就够了

- 项目隔离的是**台账和关联信息**，物理 GPU 仍然共享；候选筛选不等于资源预留。
- 训练流程、依赖安装和环境创建由你或 Agent 组织；ComputeMate 提供服务器工具，不自动决定实验方案。
- 保留原生 tmux 会话名和 Slurm Job ID。提交结果不确定时会明确返回，避免盲目重复执行。
- 同步默认预览，保留目的端额外文件；删除服务器记录采用归档，不删除远端数据。
- 资源记录带采集时间。连接失败保留最近结果并标记状态，缓存不会伪装成实时数据。

当前已完成核心接口、真实回环 SSH、tmux、网页和 VS Code 宿主验证，并有 Linux GPU 服务器实机试用。Slurm 目前使用样例/模拟验证，真实集群联调范围见 [验证记录](VALIDATION.md)。

## 一起把服务器杂活变少

欢迎用自己的实验场景来提 [Issue](https://github.com/FishAndWasabi/ComputeMate/issues)：多机训练、论文复现、测评、共享实验室服务器，都可以。

如果 ComputeMate 刚好替你省下一次“那个权重到底在哪”的搜索，欢迎点个 **Star ⭐**，也分享给还在终端标签页里找机器的朋友。

<details>
<summary>已有用户：更名后怎么兼容？</summary>

对外名称统一为 **ComputeMate（算力管家）**，首选命令为 `computemate`。旧 `cloud-servers` 命令、`cloud_servers.py` 脚本、Skill 标识 `cloud-servers`、项目 `.cloud-servers/` 数据目录及 VS Code 的 `cloudServers.*` 设置继续可用；现有台账无需迁移。

</details>
