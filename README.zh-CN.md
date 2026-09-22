<div align="center">

<img src="docs/assets/computemate-icon.png" alt="ComputeMate 算力管家图标" width="112" height="112" />

# ComputeMate · 算力管家

[English](README.md) | **简体中文**

**少翻终端，多跑实验。**

你的服务器搭子，也是 Agent 的算力工具箱。

按项目管理服务器、代码、环境和实验产物。Agent 来操作，你随时看得见。

[给 Agent 安装](#快速开始) · [交给 Agent](#交给-agent) · [可视化](#想自己看也很方便) · [使用指南](docs/usage.md) · [反馈建议](https://github.com/FishAndWasabi/ComputeMate/issues)

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

### 1. 给 Agent 安装（推荐）

先在能读写文件、执行 Shell 的 Agent 中打开**你的实验项目**，再复制对应的话术发送给它。Skill 自带 Python 脚本，无需先安装 CLI 或启动网页。

**Codex** — 直接发送：

```text
$skill-installer 请从 https://github.com/FishAndWasabi/ComputeMate
安装 skills/cloud-servers 这个 Skill 到当前项目的 .agents/skills 目录，
包含其中的 scripts 和 references。
```

**Claude Code** — 直接发送：

```text
请给当前项目安装 ComputeMate。从 https://github.com/FishAndWasabi/ComputeMate
下载完整的 skills/cloud-servers 目录到当前项目的 .claude/skills/cloud-servers，
包含其中的 scripts 和 references。
```

**Cursor** — 在 Agent 对话中发送：

```text
请给当前项目安装 ComputeMate。从 https://github.com/FishAndWasabi/ComputeMate
下载完整的 skills/cloud-servers 目录到当前项目的 .cursor/skills/cloud-servers，
包含其中的 scripts 和 references。
```

以上示例使用各 Agent 官方文档中的项目 Skill 目录：

| Agent | 安装后的 Skill 入口 |
| --- | --- |
| [Codex](https://learn.chatgpt.com/docs/build-skills#where-codex-loads-local-skills) | `.agents/skills/cloud-servers/SKILL.md` |
| [Claude Code](https://code.claude.com/docs/en/skills) | `.claude/skills/cloud-servers/SKILL.md` |
| [Cursor](https://cursor.com/help/customization/skills) | `.cursor/skills/cloud-servers/SKILL.md` |

安装后，下一条消息就可以这样发：

```text
使用 cloud-servers Skill，通过它自带的 Python 脚本初始化当前项目的台账，
显示绑定的项目，并列出已登记的服务器。
```

如果 Skill 尚未出现，重新在该项目中打开 Agent。台账保存在实验项目的 `.cloud-servers/` 目录中。接下来可以直接参考上面的[请求示例](#交给-agent)使用；下面的 CLI 安装是可选方式。

<details>
<summary>想自己复制 Skill，或使用其他 Agent？</summary>

克隆本仓库后，在仓库根目录运行安装脚本。按 Agent 选择目标目录；下面以 Codex 为例，使用实验项目的绝对路径：

```bash
git clone https://github.com/FishAndWasabi/ComputeMate.git
cd ComputeMate
python3 scripts/package-skill.py --install-to /path/to/your/experiment/.agents/skills
```

Claude Code 使用 `/path/to/your/experiment/.claude/skills`，Cursor 使用 `/path/to/your/experiment/.cursor/skills`。脚本会复制完整的 `cloud-servers` 目录，遇到已有安装时拒绝覆盖。

其他 Agent 可使用其支持的 Skill 目录，或直接读取 [SKILL.md](skills/cloud-servers/SKILL.md) 并调用配套脚本。执行服务器操作需要 Agent 具备文件和 Shell 访问能力。

</details>

### 2. 安装 CLI（可选）

需要自己在终端操作时，再运行以下命令。如果上面已克隆仓库，直接在该目录从 `uv tool install .` 开始即可。

```bash
git clone https://github.com/FishAndWasabi/ComputeMate.git
cd ComputeMate
uv tool install .
```

上面的命令适用于已安装 `uv` 的用户。提示找不到 `computemate` 时，运行 `uv tool update-shell` 后重新打开终端。

没有 `uv`，也可以用 Python 自带的虚拟环境安装：

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install .
```

不安装 CLI 时，直接调用 `python3 skills/cloud-servers/scripts/computemate.py --help`。

### 3. 通过 CLI 配置项目

如果 Agent 已经初始化过项目，下面的命令会使用同一份台账。

在**实际实验项目目录**运行；下面的 `lab-gpu` 请替换为你能正常连接的 SSH alias。
首次使用该连接时，先在同一台客户端运行 `ssh lab-gpu`，完成主机指纹确认和认证，再退出 SSH 回到本地。ComputeMate 使用非交互连接，不会弹出密码或指纹确认提示。

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

<details>
<summary>暂时没有服务器？先用示例台账体验</summary>

从 ComputeMate 仓库运行以下命令。它只导入演示记录，不连接服务器：

```bash
mkdir -p /tmp/computemate-demo
computemate init /tmp/computemate-demo
computemate --workspace /tmp/computemate-demo inventory import --document-file examples/inventory.json
computemate --workspace /tmp/computemate-demo server list
```

构建网页后，将下面网页启动命令中的项目路径替换为 `/tmp/computemate-demo`。示例 SSH 地址不可连接，换成自己的连接后再刷新。

</details>

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
如果端口被占用，在 `serve` 后加 `--port 0` 自动选择空闲端口。每个项目启动自己的网页，页面顶部显示绑定的项目名称。

若想使用安装后的 `computemate serve`，请在构建完成后从仓库重新运行 `uv tool install --reinstall .`；使用虚拟环境安装的用户运行 `python3 -m pip install --force-reinstall .`。上面的独立脚本始终读取仓库内最新构建。

VS Code 扩展运行 `npm run package:vscode` 构建，在编辑器中通过 **Install from VSIX** 安装 `extensions/vscode/computemate-0.1.0.vsix`。打开项目文件夹后，在 ComputeMate 活动栏点击“初始化此项目的台账”即可开始。

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
安装与三端上手体验的检查结果见 [首次使用检查](docs/usability-review.md)。

## 一起把服务器杂活变少

欢迎用自己的实验场景来提 [Issue](https://github.com/FishAndWasabi/ComputeMate/issues)：多机训练、论文复现、测评、共享实验室服务器，都可以。

如果 ComputeMate 刚好替你省下一次“那个权重到底在哪”的搜索，欢迎点个 **Star ⭐**，也分享给还在终端标签页里找机器的朋友。
