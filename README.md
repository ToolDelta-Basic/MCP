# ToolDelta MCP CLI

这个命令行工具连接本机正在运行的 ToolDelta「ToolDelta-MCP」插件，让终端用户和支持 MCP 的 AI 客户端调用同一组工具。需要 Python 3.10 或更高版本。运行时仅使用 Python 标准库。

## 从官方插件市场安装

游戏端插件名为 **ToolDelta-MCP**，市场 ID 为 `tooldelta-mcp-bridge`。在已连接游戏的 **ToolDelta 控制台**输入以下命令，或输入 `插件市场` 后按名称选择安装。[市场插件目录](https://github.com/ToolDelta-Basic/PluginMarket/tree/main/ToolDelta-MCP) · [已合并的投稿 PR](https://github.com/ToolDelta-Basic/PluginMarket/pull/201)

```text
plg add tooldelta-mcp-bridge
```

下次启动 ToolDelta 时会加载插件。若要立即加载，在 ToolDelta 控制台输入 `reload`，这会浅重载整组插件。看到 `[ToolDelta-MCP] 本机游戏桥已就绪` 后，在 CLI 仓库目录执行 `python run.py status`。`bridge_connected=true` 表示 CLI 已连上插件，`connected=true` 表示游戏已就绪。

**从旧版 MCP游戏桥 迁移**时，让活动插件目录只加载新版。需要保留自定义权限时，把 `插件配置文件/MCP游戏桥.json` 中的设置迁入 `插件配置文件/ToolDelta-MCP.json`。新版会生成自己的连接文件；CLI 遇到显式指定的旧标准路径时，会优先使用同一实例的新连接文件。

## 连接游戏

可以先连接 MCP 客户端查看工具清单。要实际操作游戏，请在 ToolDelta 项目目录执行 `python main.py` 并等待插件就绪。在本项目目录运行以下命令。

```powershell
python -m tooldelta_mcp_cli status
python -m tooldelta_mcp_cli tools
python -m tooldelta_mcp_cli players
python -m tooldelta_mcp_cli command "list"
python -m tooldelta_mcp_cli logs --limit 20
python -m tooldelta_mcp_cli logs --follow --level warning
python -m tooldelta_mcp_cli console
python -m tooldelta_mcp_cli docs search "ListenChat"
```

游戏桥离线时，`tools` 提供 CLI 随包的基础接口清单，`status` 返回 `bridge_connected: false`、`connected: null` 和离线原因。此时玩家和游戏运行情况未知。游戏桥上线后，同一 MCP 会话即可调用游戏工具。`tools` 将读取插件按配置开放的实时清单，`status` 返回 `bridge_connected: true` 和实际游戏连接状态。任何操作的权限均由在线插件核验。

`command` 默认使用 WebSocket 身份。可用通道包括 `ws`（WebSocket）、`player`（机器人玩家）、`wo`（游戏控制台，只发送）、`ai`（具有最高操作台权限的魔法命令）和 `console`（已允许的 ToolDelta 菜单）。`status` 可查看启动器是否支持魔法命令回执。执行操作后遇到连接中断时，应先查看游戏状态或日志以确认结果，自动重试可能造成重复执行。

连接信息由插件写入 `插件数据文件/ToolDelta-MCP/connection.json`。CLI 依次使用全局选项 `--connection`、环境变量 `TOOLDELTA_MCP_CONNECTION`、当前目录中的上述文件，以及默认项目 `D:\gitclone\ToolDelta` 下的同名文件。连接文件包含令牌，请仅在本机使用。每次调用都会重新读取文件，以适应插件重载后的端口和令牌变化。

## MCP 工具与 CLI 对照

插件默认提供 11 个工具。运行 `python run.py tools` 可以查看工具的输入参数；在线清单会反映本机的权限配置。

| MCP 工具 | CLI 子命令 | 用途 |
| --- | --- | --- |
| `status` | `status` | 查看启动器、机器人、在线人数、会话和租赁服号 `rental_server_id`。游戏未连接或启动器未提供服号时，插件返回 `null`。 |
| `players_list` | `players` | 列出在线玩家和机器人身份。 |
| `game_command` | `command` | 执行游戏指令或允许的控制台菜单，读取派发状态或游戏回执。 |
| `console_list` | `console` | 查看实际注册的控制台菜单和允许调用的触发词。 |
| `bot_chat` | `call bot_chat` | 以机器人身份发送普通聊天，参数为 `message`。 |
| `logs_read` | `logs` | 读取实时日志，或用 `--date YYYY-MM-DD` 查询历史日志。 |
| `events_read` | `events` | 按类型、关键词和游标读取游戏事件。 |
| `events_wait` | `events --wait` | 等待匹配的事件，可指定超时。 |
| `docs_search` | `docs search` | 搜索工具说明、示例和本地开发文档。 |
| `docs_get` | `docs get` | 按 ID 阅读文档，例如 `python run.py docs get guide/code`。 |
| `execute_code` | `exec` | 执行游戏自动化 Python 子集，返回 `result`、`stdout`、步数和工具调用次数。 |

## 重载插件并验证

需要浅重载整组插件时，在 CLI 仓库目录用 PowerShell 记下旧会话，再提交一次重载。

```powershell
$before = (python run.py status | ConvertFrom-Json).session
python run.py command reload --channel console
```

`dispatched` 表示已派发。等游戏桥上线后，运行下面的查询。确认 `connected` 为真、会话 ID 已变化，并在新会话日志中找到“全部插件重载成功”。若桥仍在启动，继续查询状态即可。

```powershell
$after = python run.py status | ConvertFrom-Json
$after | Select-Object connected, session, rental_server_id
$after.connected -and ($before -ne $after.session)
python run.py logs --session $after.session --contains "重载" --limit 20
```

同一 MCP 客户端可以跨插件重载继续使用。插件设置位于 `插件配置文件/ToolDelta-MCP.json`。“禁用工具”“开放指令通道”“控制台允许的触发词”同时约束直接调用和脚本调用。默认允许浅重载 `reload`；需要重新导入插件子模块时，可在 ToolDelta 控制台执行 `deepreload`。“开发文档目录”可指向本机的 `ToolDelta-Wiki/docs/plugin-dev`。

## 指定参数

`call` 支持运行时工具清单中的每一个工具。PowerShell 下可以用管道传入 JSON。也可以将包含中文的参数保存为 UTF-8 文件，通过 `--file <路径>` 传入。

```powershell
python -m tooldelta_mcp_cli --connection "D:\gitclone\ToolDelta\插件数据文件\ToolDelta-MCP\connection.json" status
'{"command":"list","channel":"player","wait":true}' | python -m tooldelta_mcp_cli call game_command --file -
python -m tooldelta_mcp_cli events --wait --timeout 10
python -m tooldelta_mcp_cli docs get "<搜索结果中的 ID>" --offset 0 --limit 4000
python -m tooldelta_mcp_cli exec --file .\query.py
```

`exec` 调用插件的 `execute_code` 工具，在一次请求中执行游戏自动化 Python 子集。工具名可当作函数调用，`if` 可判断结果，`for` 可遍历玩家或日志。`print` 输出文字，赋给 `result` 的值作为结果返回。例如，在 PowerShell 中运行以下命令即可列出在线真人玩家并返回人数。

```powershell
@'
count = 0
for player in players_list()["players"]:
    if not player["is_bot"]:
        print(player["name"])
        count += 1
result = count
'@ | python -m tooldelta_mcp_cli exec --file -
```

`logs --follow` 先打印最近匹配的日志，随后按会话和游标长轮询，每条记录单独输出一行 JSON。插件重载或短暂掉线后会恢复，记录被覆盖或会话切换时会在 stderr 提示。按 Ctrl+C 结束。也可记录一次查询结果的 `session` 和 `next_cursor`，再通过 `logs --session … --after …` 或 `events --session … --after … --wait` 手动读取下一批。

## 配置 MCP 客户端

### 注册到 Codex

在 CLI 仓库目录打开 PowerShell，将第一行改为你的 ToolDelta 根目录。使用绝对路径注册后，Codex 可以从任意工作目录启动 MCP。

```powershell
$toolDeltaRoot = 'D:\gitclone\ToolDelta'
$connection = Join-Path $toolDeltaRoot '插件数据文件\ToolDelta-MCP\connection.json'
$python = python -c "import sys; print(sys.executable)"
$cli = (Resolve-Path .\run.py).Path
codex mcp add tooldelta --env "TOOLDELTA_MCP_CONNECTION=$connection" -- $python -B $cli serve --stdio
codex mcp get tooldelta
```

在 Codex 中输入 `/mcp` 查看连接状态。如果当前聊天尚未显示新服务，打开 **设置 → MCP servers** 并选择 **Restart**。可以用这句话做只读验收：“用 tooldelta 的 status 查当前租赁服号，再用 game_command 的 ws 通道执行 /list，返回在线名单。” [Codex MCP 配置说明](https://learn.chatgpt.com/docs/extend/mcp)

### 其他 stdio 客户端

可通过绝对路径直接启动独立 CLI，无需安装或设置客户端工作目录。将以下配置加入支持 stdio 的 MCP 客户端，ToolDelta 可随后启动。

```json
{
  "mcpServers": {
    "tooldelta": {
      "command": "python",
      "args": ["D:\\gitclone\\tooldelta-mcp-cli\\run.py", "serve", "--stdio"],
      "env": {
        "TOOLDELTA_MCP_CONNECTION": "D:\\gitclone\\ToolDelta\\插件数据文件\\ToolDelta-MCP\\connection.json"
      }
    }
  }
}
```

也可在本项目目录执行 `python -m pip install .`，然后使用 `tooldelta-mcp serve --stdio`。stdio 服务支持初始化、ping、工具发现和调用，协商 MCP 2024-11-05 至 2025-11-25 四个协议版本。请求以 UTF-8 JSON Lines 交换。工具返回的对象在支持的协议版本下同时提供结构化结果与文字。
