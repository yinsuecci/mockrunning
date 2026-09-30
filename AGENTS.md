# Agent 工作指南

本文件适用于整个仓库。先阅读 `README.md` 与 `pyproject.toml`；以当前代码为准，不把旧备份或生成物当作实现依据。

## 项目与代码入口

- 这是本地运行的路线编辑器和 iPhone 模拟定位测试工具。编辑路线与控制手机是两个不同流程；编辑草稿绝不能隐式连接设备或发送定位。
- `src/ios_location_controller/web.py`：仅监听 localhost 的 HTTP 服务、静态资源与 `/api/*` 接口；`static/index.html`、`static/app.js`、`static/app.css` 是无前端构建步骤的页面。Leaflet 静态资源随项目提供。
- `playback.py`：网页回放状态与持久化；所有设备 I/O 和状态迁移集中在其专属 asyncio 事件循环中，由 HTTP 线程通过 `call()` 访问。修改时维护串行化、超时、错误处理及资源清理。
- `motion.py`：路线/设置校验和网页回放运动模型；`gpx.py`：坐标几何与 CLI GPX 解析；`device.py`：`pymobiledevice3` 设备适配及可选 WDA 读取；`cli.py`：独立的 CLI 路径。不要误认为 CLI 的 `play()` 与网页的 `Motion` 使用同一回放逻辑。
- `tests/test_*.py` 覆盖 GPX、运动、状态机和 HTTP；`tests/browser_*.py` 为独立的浏览器脚本，非 pytest 常规测试。

## 本地开发与验证

- Python >=3.11；依赖和入口以 `pyproject.toml` 为准。Linux 缺少可用环境时可在项目根目录运行 `uv venv --python 3.13 .venv && uv pip install -e . pytest`；不要默认已有 `.venv` 可跨系统使用。
- 常规测试：`./.venv/bin/python -m pytest -q`（Windows：`.\.venv\Scripts\python.exe -m pytest -q`）。优先运行相关测试，再运行全套；修改 HTTP/状态机/运动模型时补充相应回归测试，设备交互使用 fake，不要求接入实机。
- 手动启动参见 `README.md`：Linux `./start-map.sh`，Windows `start-map.cmd`，默认 `http://127.0.0.1:8765`。需要隔离测试数据时设置 `IOS_LOCATION_STATE` 为临时文件；默认状态文件在 `~/.ios-location-controller/session.json`。
- 浏览器脚本需预先启动本地服务，并依赖 Playwright 与 Edge；`tests/browser_smoke.py` 不连接手机，但会修改服务保存的路线/设置、浏览器草稿并写入 `artifacts/`。仅在需要 UI 验证且隔离状态后运行。

## 安全边界与修改约定

- **不要在未经明确授权的情况下执行实机操作**：包括 `tests/browser_device.py`、CLI `play`/`clear`、连接/开始/位置切换 API；它们可能改变手机定位。CLI 和网页不要同时控制同一设备。实机测试完成后必须尝试停止、清除模拟并断开连接。
- 保持网页接口仅限 localhost；修改 API 时保留 Host/Origin、请求体大小、GPX/坐标/参数与静态文件路径校验。外部地点搜索需要网络；底图或 WDA 失败不应阻断离线路线编辑或模拟定位主流程。
- 服务恢复保存的路线与参数时不得自动连接或自动回放。区分“最近成功发送的模拟坐标”和 WDA 返回的实测坐标；停止/断开时优先清除模拟并释放资源。
- 采用最小、针对性的改动；不要顺手改 `backups/`、`artifacts/`、日志或虚拟环境。`.venv/` 等生成物已被忽略；不要因整理工作区而重置、删除或提交其他无关变更。交付前只检查本次改动及对应验证结果，无法验证时说明原因。

## Git 工作流

- 开始前查看 `git status --short` 和相关文件的历史/差异；区分任务改动与已有改动，保留他人的工作。`.venv/` 已停止跟踪；其他已跟踪的生成物仍需单独处理，`.gitignore` 不会自动取消对它们的跟踪。
- 保持改动聚焦且可审查；不要为本任务以外的问题批量格式化、更新依赖或清理工作区。提交前运行适用的测试，并用 `git diff --check` 检查空白问题。
- 完成并验证任务后，按最小的独立逻辑改动提交：一个 commit 只包含一项变更所需的代码、测试和文档；不要混入无关修改，也不要为凑数量拆分不可独立运行的改动。若用户明确要求不提交，则不提交。
- 用 `git add -- <本次修改的路径>` 精确暂存，避免 `git add .` / `git add -A`。提交前核对 `git diff --cached --stat` 与 `git diff --cached`，确保只包含预期文件；工作区有其他改动时尤其要隔离提交范围。
- 提交信息遵循 Conventional Commits：`<type>(<scope>): <imperative summary>`，scope 可省略；使用小写类型（如 `feat`、`fix`、`docs`、`test`、`refactor`、`chore`），摘要简短准确、使用祈使语气，例如 `docs: clarify agent git workflow`。不要使用 `update`、`misc` 等无法说明意图的消息。
- 未经明确授权不要 `git reset --hard`、`git clean`、强推、变基或覆盖他人的提交；不要擅自推送远端。若工作区已有冲突或意外暂存内容，先说明并停下，不要用破坏性命令“修复”。
