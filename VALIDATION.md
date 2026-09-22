# 验证记录

验证日期：2026-09-22。

## 已完成

- Python 核心与接口：`python3 -m unittest discover -s tests -v`，38 项通过。
- 项目隔离：验证不同项目使用相同服务器 ID 时独立更新与归档、重复初始化保留身份、子目录发现、嵌套仓库边界、损坏配置拒绝回退，以及 CLI/RPC/HTTP 固定项目绑定。
- 覆盖台账增删改查、归档关联、导入原子性、并发版本冲突、过期快照、环境归属、资源筛选、结构化错误和输出上限。
- 真实回环 SSH：在临时目录生成测试密钥并启动独立 sshd；验证特殊字符参数、非零退出码、代码补丁与冲突、文件读取、rsync 预览/应用/取回，以及保留目的端额外文件。
- 真实 Linux 部署：在已有项目中完成 Skill 安装、台账迁移、GPU 探测、已有 Python 环境调用、实验状态文件读取与原生 tmux 查询。
- Conda 非交互入口：新增可选绝对路径字段 `conda_executable`。测试覆盖路径/参数中的特殊字符和无效配置；真实 SSH 使用既有 Conda 的绝对路径，经登记环境返回 Python 3.10.19。既有环境产生 libtinfo 版本信息提示，退出码为 0，未修改环境依赖。
- Linux 目录浏览：真实部署试用发现 Bash 会丢弃脚本中的字面 NUL，已改为让 GNU find 解码转义；本地新增回归用例，真实 SSH 验证含制表符、换行、单引号的文件名和分页，测试临时目录已清理。
- 原生 tmux：使用独立临时 socket 目录，验证退出 SSH 后继续运行、读取持久日志、查询已结束 pane 的退出码、结束指定会话。
- HTTP：验证 token、Origin、Host、静态路径边界，以及相同操作契约的调用与结果。
- Skill：通过 `quick_validate.py`，核心无第三方 Python 运行依赖。
- 前端和扩展：TypeScript 类型检查、Vite 构建、扩展 bundling 通过。
- 网页交互：简化为列表、侧边详情和“更多操作”；从简化表单新增测试节点，公共 API 读回并归档测试记录。验证搜索、分组、无匹配状态、详情分页、参数折叠及错误反馈；原 54 个操作入口逐类别核对可达，新增第 55 个 `scope` 操作沿用相同目录与表单。通过 SSH 隧道打开真实项目台账，页面显示绑定项目和服务器，浏览器无控制台错误。
- 窄面板：420px 宽度下检查首页与详情，无页面横向溢出；验证 Esc 关闭详情，并恢复浏览器原尺寸。
- 此次可视化修改后重新通过 TypeScript/Vite 构建与 VS Code Extension Host 冒烟测试；Skill ZIP、wheel、VSIX 中的前端资源均与本次构建逐字节一致。
- VS Code 1.138.0：独立临时用户配置与扩展目录中的真实 Extension Host 测试通过；验证扩展激活、命令注册、Webview 消息桥，以及两个工作区使用相同服务器 ID 时分别读取各自快照，继承的全局数据库变量不会覆盖项目绑定。
- 发布包：Skill ZIP、Python wheel 和 VSIX 的全部 Python 模块与当前源码逐字节一致，HTML 引用的资源均存在。独立脚本与 wheel 均提供完整操作目录。

- ComputeMate 更名：新旧 CLI 已在隔离虚拟环境安装 wheel 后验证，读取同一项目、同一服务器记录及完整的 55 项能力目录。新品牌 VS Code Extension Host 多项目验证通过，现有项目记录保持不变。

## 验证范围

- 本地环境为 macOS、Python 3.13.2、Node.js 22.22.0。回环 SSH 测试验证了真实传输与原生工具调用；Linux `/proc` 和 NVIDIA 硬件解析另由样例测试覆盖。
- Slurm 使用样例/模拟输出验证提交解析、原生状态和缺失 accounting 的处理，尚未连接真实 Slurm 集群。
- Docker 环境的工作目录与命令构造已测试，未在真实 Docker 容器内执行训练。
- Windows/WSL 和其他 Linux 发行版尚未执行宿主回归；第一版 Windows 使用 WSL 中的 CLI/网页。
- VS Code 多工作区测试在本地宿主完成；Remote SSH 扩展运行位置已配置为 workspace，尚未进行真实 Remote SSH 编辑器宿主联调。

复验命令与依赖见 README。VS Code 宿主测试可用 `python3 tests/run-vscode-smoke.py` 运行；它只使用临时配置，不修改日常编辑器配置。
