# ComputeMate 使用指南

以 **Skill 与独立脚本** 为核心的云服务器工具集。Agent、CLI、网页和 VS Code 共用服务器台账及操作接口。无必需常驻服务，无远端专用守护程序。

功能包括服务器分组、硬件与资源探测、已有环境发现和登记、项目与产物管理、远程代码搜索/读取/补丁、rsync、SSH 命令，以及原生 tmux/Slurm 薄封装。训练流程与环境创建由 Agent 或用户组织。

## 快速开始

需要 Python 3.11+ 和 OpenSSH；文件同步需要本地及远端 rsync。远端以 Linux/Bash 为目标；Git、tmux、Slurm 按所用功能提供。

无需安装依赖即可使用：

```bash
python3 skills/cloud-servers/scripts/computemate.py --help
python3 skills/cloud-servers/scripts/computemate.py init /path/to/project
python3 skills/cloud-servers/scripts/computemate.py --workspace /path/to/project --json snapshot
```

安装 CLI（任选一种）：

```bash
uv tool install .
# 或在自己的 Python 虚拟环境中：
python3 -m pip install .
```

在目标项目内初始化台账并探测已有 SSH 连接：

```bash
cd /path/to/project
computemate init
computemate scope
computemate group add --id lab --data '{"name":"实验组"}'
computemate server add --id gpu01 --data '{"name":"GPU 01","ssh":{"alias":"my-gpu-host"},"groups":["lab"],"role":"compute"}'
computemate probe gpu01
computemate server list
computemate --json exec gpu01 --cwd /workspace/model -- python train.py --help
```

`ssh.alias` 对应已有 SSH 配置，亦可填写 `host`、`user`、`port`、`identity_file`、`proxy_jump`。密钥解锁和主机指纹校验沿用 OpenSSH。初次连接可先用普通 `ssh` 建立信任。

Skill 和脚本可以共用，每个项目的台账独立存于 `.cloud-servers/inventory.sqlite3`，项目标识存于 `.cloud-servers/config.json`。从项目及子目录运行时自动识别绑定，并在 Git 仓库／worktree 边界停止查找；未初始化的项目不会默认读取全局台账。同名服务器、环境和实验记录在不同项目间互不覆盖。

从其他目录调用使用 `--workspace /path/to/project`。`--db PATH` 为显式台账覆盖，不能与 `--workspace` 同用；`CLOUD_SERVERS_DB` 仅在没有显式或自动识别的项目绑定时生效。旧版用户台账仍可通过 `--db ~/.local/share/cloud-servers/inventory.sqlite3` 显式读取，迁移时只导入目标项目相关记录。共享 GPU 的实际占用仍通过 SSH／调度器查询。

示例导入不会自动连接服务器：

```bash
computemate --db ./demo.sqlite3 inventory import --document-file examples/inventory.json
```

## 安装 Skill

将完整的 `skills/cloud-servers` 目录放入目标 Agent 支持的 skills 目录。也可以显式指定目标目录：

```bash
python3 scripts/package-skill.py --install-to /path/to/agent/skills
```

此命令拒绝覆盖已有目录。复制后的 Skill 自带核心 Python 代码，不依赖当前仓库路径或 CLI 安装。入口与用法见 [SKILL.md](../skills/cloud-servers/SKILL.md)，详细示例按主题放在 `references/`。

## 网页与 VS Code

前端使用 React + TypeScript，公共 Python 核心仍然没有第三方运行依赖。构建需要 Node.js 20.19+：

```bash
npm ci
npm run build
computemate --workspace /path/to/project serve
```

若 CLI 是在构建前安装的副本，从仓库运行 `uv tool install --reinstall .`，或在自己的虚拟环境中运行 `python3 -m pip install --force-reinstall .`。也可直接运行仓库内的独立脚本 `python3 skills/cloud-servers/scripts/computemate.py --workspace /path/to/project serve`。尚未构建时，启动命令会提示构建及重新安装步骤，不会输出无法使用的网页链接。

同一台机器上开启多个项目的网页时，使用 `serve --port 0` 自动选择空闲端口，或指定 `--port 8766` 等不同端口。分别打开各次启动输出的完整 URL。

打开终端输出的完整 URL（包含 token）。网页只监听 `127.0.0.1`。默认读取缓存；“刷新状态”才连接远端，自动刷新可按需开启。首页仅展示服务器列表，支持搜索与分组筛选；点击服务器，在侧边详情中查看资源、环境、项目、会话与产物。“更多操作”提供全部公共操作，表单中的次要参数默认折叠。网页与 VS Code 共用这套界面和校验。

打包 VS Code 扩展：

```bash
npm run package:vscode
```

在 VS Code 中选择 **Extensions: Install from VSIX**，安装 `extensions/vscode/computemate-0.1.0.vsix`，打开 ComputeMate 活动栏。扩展自带脚本和同一套界面，在项目所在主机调用 Python。选择 **ComputeMate: 初始化项目台账** 完成首次绑定。多根工作区按项目分开展示，打开面板时选择目标项目，面板及后续操作固定使用该项目。可配置 `cloudServers.pythonPath`，以及按项目覆盖的 `cloudServers.databasePath`。Remote SSH 工作区使用远端 Python 和远端项目台账，需在远端设置 Python 3.11+ 路径。

macOS/Linux 可使用全部入口；Windows 第一版使用 WSL 中的 CLI/网页，原生 Windows 扩展宿主尚未验证。

## 常见操作

```bash
# 查询资源，Agent 自行选择候选机器
computemate --json server select --min-gpus 1 --min-gpu-memory-mib 16000
computemate --json slurm resources cluster-login

# 有限范围读取和补丁修改
computemate --json fs read gpu01 --path /workspace/model/train.py --start 1 --end 80
computemate --json fs patch gpu01 --cwd /workspace/model --patch-file change.patch

# 增量同步默认预览；加 --apply 才传输，默认不删除目的端额外文件
computemate sync gpu01 --direction push --local ./model/ --remote /workspace/model/ --exclude '[".git/","outputs/"]'

# 原生后台会话
computemate --json tmux start gpu01 --name train --cwd /workspace/model -- python train.py
computemate tmux logs gpu01 --name train
computemate tmux show gpu01 --name train

# 原生 Slurm 作业
computemate --json slurm submit cluster-login --script-file job.sbatch
computemate slurm show cluster-login --job 12345

# 查看完整接口、保存或导入台账
computemate --json operations
computemate --json inventory export > inventory.json
computemate inventory import --document-file inventory.json --overwrite
```

普通调用提供表格或文本；`--json` 提供版本化结果。每个命令支持 `--help`，大文本可用 `--script-file`、`--patch-file`、`--data-file` 等读取文件。`rpc` 从 stdin 读取一条 `{operation, arguments}` 请求并返回同一格式，供其他宿主集成。

`probe` 返回探测记录：接口成功返回不代表连接成功，应检查 `data.reachable` 以及 `observations` 中的错误。CLI 快照用 `connection_failed` 区分连接异常与单纯过期，网页直接展示 SSH 原因。命令执行失败会展示 stdout、stderr 和退出码；结果不确定时先查原生状态。同步预览明确显示“尚未传输文件”。网页中的修改操作成功后会禁用重复提交，修改参数或重新打开表单后才能再次提交。

## 首次使用排障

| 遇到的问题 | 下一步 |
| --- | --- |
| `computemate: command not found` | 使用 uv 安装时运行 `uv tool update-shell` 并重开终端；虚拟环境安装时先激活环境。 |
| `workspace_not_initialized` | 在实际实验项目运行 `computemate init`，或在命令中指定已经初始化的 `--workspace`。 |
| `web_assets_missing` | 从仓库构建网页，再使用独立脚本启动，或重新安装 CLI。 |
| `port_in_use` | 使用 `serve --port 0`，从终端获取新 URL。 |
| 网页令牌过期 | 重新打开当前服务启动时输出的完整 URL，包含 `#token=…`。服务重启后旧令牌失效。 |
| SSH 连接失败 | 从运行 ComputeMate 的主机手动 `ssh` 到相同地址，核对密钥、跳板机、端口和主机指纹。 |
| VS Code 无法启动 Python | 在设置中将 `cloudServers.pythonPath` 指向 Python 3.11+；Remote SSH 时设置远端路径。 |

HTTP 适配层只提供 `/api/v1/operations`、`/api/v1/snapshot` 和 `/api/v1/invoke`，校验 Bearer token、Host 与浏览器 Origin。Skill 和 CLI 无需启动它。

## 行为边界

- 台账移除采用归档，保留关联信息；不购买、销毁或开关云实例。
- 探测快照超过五分钟标记过期；连接失败保留最后数据。资源候选不等于预约或独占。
- 环境只发现、登记、使用。Conda/CUDA 发现依赖远端非交互 SSH PATH；使用 Conda 时也可指定 `conda_executable` 的绝对路径。venv 探测使用显式路径。
- tmux/Slurm 保留原生状态和标识；不自动排队、重试或编排实验。SSH 断连后的变更结果可能不确定，先查询再决定是否重试。
- 代码补丁采用合作锁与上下文/可选哈希检查；外部编辑器不受该锁约束。
- `tmux stop` 使用原生 kill-session 语义；故意脱离会话的子进程需要单独处理。Slurm 使用目标站点已有命令与权限。
- 普通 SSH 命令有超时及输出上限；长任务使用 tmux/Slurm。完整日志保留在远端文件。

## 开发与验证

```bash
python3 -m unittest discover -s tests -v
npm run test:ui
npm run build
python3 scripts/package-skill.py
```

测试包括事务与并发修改、缓存、JSON/CLI 契约、HTTP 鉴权、输出限制、Slurm 样例解析；具备本地 sshd 时还会启动隔离的回环 SSH 服务，使用临时密钥验证真实 SSH、rsync、Git 补丁与 tmux。测试不修改 `~/.ssh`，tmux 使用独立临时 socket 目录。缺少 sshd 或相应工具时集成用例会明确跳过。

Slurm 的真实集群联调需要可访问的测试集群；当前样例/模拟测试不能替代站点验证。具体交付验证记录见 [VALIDATION.md](../VALIDATION.md)。

## 名称与兼容性

对外名称为 **ComputeMate（算力管家）**，首选命令是 `computemate`。`cloud-servers` 命令、`cloud_servers.py` 脚本、`cloud-servers` Skill 标识、`.cloud-servers/` 台账及 VS Code 的 `cloudServers.*` 设置保留兼容，无需迁移项目记录。新的发布包为 `computemate-skill.zip`、`computemate-0.1.0-py3-none-any.whl` 和 `computemate-0.1.0.vsix`。
