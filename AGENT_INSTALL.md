# ToolDelta MCP 的 Agent 安装指南

在用户指定的 ToolDelta 实例中安装 `ToolDelta-MCP` 插件，准备独立 CLI，再让目标 MCP 客户端（harness）通过 stdio 启动 CLI。以目标客户端中实际调用 `status` 的结果验收。以下命令以 Windows PowerShell 为例。

## 1. 确认安装目标

- 找到 ToolDelta **实例的运行目录**，也就是该实例存放 `插件文件`、`插件数据文件` 等目录的位置。有多个实例时，确认哪一个对应用户要连接的游戏。
- 确认目标 harness 及其运行环境。harness 启动的 CLI 必须能读取 ToolDelta 生成的连接文件，并访问插件所在环境的 `127.0.0.1`。如果使用 WSL、容器或远程主机，核对两项条件再配置。
- 确认 CLI 源码目录和可用的 Python 3.10 或更高版本。能够从当前工作区或配置确定的信息可以直接使用。

如果路径或客户端尚未确定，可以一次问清两项信息。

> 你要连接哪个 ToolDelta 实例？请提供它的运行目录，以及要配置的 MCP 客户端名称。

## 2. 准备 CLI

CLI 使用 Python 标准库。已有 CLI 仓库时，在仓库根目录用 `git submodule update --init` 获取 Wiki 子模块，再运行 `run.py`。尚无源码时，克隆到用户选定的目录。 [CLI 源码](https://github.com/ToolDelta-Basic/MCP)

```powershell
git clone --recurse-submodules https://github.com/ToolDelta-Basic/MCP.git 'D:\gitclone\tooldelta-mcp-cli'
```

将下面的两个目录换成实测路径。若 `python` 指向其他解释器，将其换成选定的 Python 可执行文件。

```powershell
$toolDeltaRoot = (Resolve-Path -LiteralPath 'D:\gitclone\ToolDelta').Path
$cliRoot = (Resolve-Path -LiteralPath 'D:\gitclone\tooldelta-mcp-cli').Path
$cli = (Resolve-Path -LiteralPath (Join-Path $cliRoot 'run.py')).Path
$connection = Join-Path $toolDeltaRoot '插件数据文件\ToolDelta-MCP\connection.json'
$python = python -c "import sys; print(sys.executable)"
& $python --version
& $python -B $cli --version
& $python -B $cli docs get bundled-wiki/plugin-dev/index.md
```

确认 Python 为 3.10 或更高版本，CLI 能打印版本，且 `docs get` 返回 Wiki 正文。查询这份文档无需启动 ToolDelta。需要把 CLI 安装为 Python 包时，在选定的 Python 环境运行 `& $python -m pip install $cliRoot`，然后用 `& $python -m tooldelta_mcp_cli --version` 检查。后续也可继续用已验证的 `run.py`。

## 3. 安装并加载 ToolDelta 插件

如果目标实例已加载 `ToolDelta-MCP`，直接检查就绪状态和连接文件。需要安装时，在**已连接游戏的 ToolDelta 控制台**输入以下命令。

```text
plg add tooldelta-mcp-bridge
```

也可在 ToolDelta 控制台输入 `插件市场`，按名称选择 `ToolDelta-MCP`。带启动菜单的发行版可从菜单进入插件市场。Agent 无法向控制台输入时，把命令交给用户执行，并请用户回报安装结果。 [市场插件目录](https://github.com/ToolDelta-Basic/PluginMarket/tree/main/ToolDelta-MCP)

安装后按该实例的正常方式启动 ToolDelta。源码版可在其实例目录执行 `python main.py`。若 ToolDelta 正在运行且要立即加载，在 ToolDelta 控制台输入 `reload`，它会浅重载整组插件。

等待日志出现 `[ToolDelta-MCP] 本机游戏桥已就绪`，再用下面的命令检查文件。它由插件自动创建，里面的 `url` 和 `token` 供 CLI 连接本机游戏桥。把文件路径传给 harness 即可，令牌留在本机文件中。 [连接文件说明](README.md#连接游戏)

```powershell
Test-Path -LiteralPath $connection -PathType Leaf
```

## 4. 验证 CLI 和游戏桥

```powershell
& $python -B $cli --connection $connection status |
    ConvertFrom-Json |
    Select-Object bridge_connected, connected, catalog_source, reason, message
```

- `bridge_connected: true` 和 `catalog_source: plugin` 表示 CLI 已连上插件。
- `connected: true` 表示游戏也已就绪。若为 `false`，继续检查 ToolDelta 的游戏启动或登录状态。
- `reason: offline` 表示所查找的连接文件缺失。核对实例路径和插件就绪日志。
- `reason: transport` 表示传输失败。确认生成该文件的插件仍在运行，且执行 CLI 的环境能访问它的本机回环地址。

离线时 `status` 仍可能以退出码 `0` 结束，`tools` 也可展示 CLI 自带的清单。内置 Wiki 可通过 `docs search` 和 `docs get` 查阅。按 `bridge_connected` 和 `catalog_source` 判断游戏桥是否可用。 [离线行为](README.md#连接游戏)

## 5. 配置并验收目标 MCP 客户端

在实际使用的 harness 配置中注册 stdio 服务，启动命令使用 Python 的绝对路径，参数使用 `-B`、`run.py` 的绝对路径、`serve` 和 `--stdio`。通过 `TOOLDELTA_MCP_CONNECTION` 传入连接文件的绝对路径。使用 `mcpServers` 格式的客户端可用下面的 PowerShell 命令生成配置，再将 `mcpServers.tooldelta` 合入现有配置。 [客户端配置参考](README.md#配置-mcp-客户端)

```powershell
@{
    mcpServers = @{
        tooldelta = @{
            command = $python
            args = @('-B', $cli, 'serve', '--stdio')
            env = @{ TOOLDELTA_MCP_CONNECTION = $connection }
        }
    }
} | ConvertTo-Json -Depth 5
```

若客户端无法传入环境变量，在参数中把 `--connection` 和文件绝对路径放在 `serve` 前。两种设置同时存在时，`--connection` 优先。重新加载客户端的 MCP 配置或重启该 MCP 服务。

在**目标 harness** 中调用 `tooldelta` 的 `status`，确认 `bridge_connected: true` 和 `catalog_source: plugin`。若终端验证通过但这里返回 `offline`，对照响应中的路径与第 4 步使用的路径，检查客户端实际传入的参数、环境变量及其进程对该路径的可见性。若用户要求验收游戏连接，再确认 `connected: true`，可调用只读工具 `players_list` 检查游戏数据。

验证 Wiki 查询时，在目标 harness 中调用 `docs_search`，搜索「插件开发」，再把结果中任意一个 `bundled-wiki/` 开头的 ID 传给 `docs_get` 并确认返回正文。

向用户报告所用的 ToolDelta 实例目录、配置的 harness、游戏桥和游戏连接状态，以及尚待完成的任何一步。
