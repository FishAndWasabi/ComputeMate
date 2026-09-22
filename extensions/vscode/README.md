# ComputeMate

项目独立的服务器台账，复用 ComputeMate Skill 的公共接口与网页组件。

1. 打开项目目录，在 ComputeMate 活动栏点击 **初始化此项目的台账**，或运行 **ComputeMate: 初始化项目台账**。
2. 使用 ComputeMate 活动栏查看服务器，或打开实验工作台。
3. 多根工作区按目录区分，打开面板时选择项目；面板不会随当前编辑文件自动切换台账。

扩展在项目所在主机运行：本地目录使用本地 Python，Remote SSH 使用远端 Python。`cloudServers.pythonPath` 指定 Python 3.11+；`cloudServers.databasePath` 可在项目设置中显式覆盖数据库。

默认读取所选目录的 `.cloud-servers/config.json` 与 `.cloud-servers/inventory.sqlite3`，没有项目绑定时提示初始化。所有操作通过本机脚本 RPC 完成，无需 HTTP 服务。未信任工作区只允许查询。

构建与打包：仓库根目录执行 `npm run package:vscode`。
