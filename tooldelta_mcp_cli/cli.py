import argparse
import json
import sys
import time
from pathlib import Path

from . import __version__
from .bridge import Bridge, BridgeError
from .server import Server


def filters(parser, event=False):
    parser.add_argument("--after", type=int, help="上次读取的游标")
    parser.add_argument("--session", help="游标对应的游戏桥会话")
    parser.add_argument("--limit", type=int, help="最大返回条数")
    parser.add_argument("--contains", help="匹配文字")
    if event:
        parser.add_argument("--kind", help="游戏事件类型")
    else:
        parser.add_argument("--level", help="日志级别")
        parser.add_argument("--date", help="读取指定日期的日志 (YYYY-MM-DD)")


def parser_for_cli():
    parser = argparse.ArgumentParser(prog="tooldelta-mcp", description="ToolDelta 游戏桥客户端")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--connection", help="插件生成的 connection.json 路径")
    subs = parser.add_subparsers(dest="subcommand", required=True)
    serve = subs.add_parser("serve", help="启动 MCP stdio 服务")
    serve.add_argument("--stdio", action="store_true", help="使用 stdio 传输（默认）")
    subs.add_parser("tools", help="列出运行时工具及参数模式")
    subs.add_parser("status", help="游戏桥和启动器状态").set_defaults(tool="status")
    subs.add_parser("players", help="在线玩家").set_defaults(tool="players_list")
    subs.add_parser("console", help="列出已注册的控制台命令").set_defaults(tool="console_list")

    call = subs.add_parser("call", help="调用任意已注册工具")
    call.add_argument("name", help="工具名")
    args = call.add_mutually_exclusive_group()
    args.add_argument("arguments", nargs="?", help="JSON 参数对象，默认 {}")
    args.add_argument("--file", help="从 UTF-8 文件读取 JSON，- 表示标准输入")

    cmd = subs.add_parser("command", help="执行游戏或 ToolDelta 控制台指令")
    cmd.set_defaults(tool="game_command")
    cmd.add_argument("command", help="完整指令文本，含空格时加引号")
    cmd.add_argument("--channel", help="通道名称，见 tools 中的 game_command")
    cmd.add_argument("--wait", action=argparse.BooleanOptionalAction, default=None, help="等待游戏回执")
    cmd.add_argument("--timeout", type=float, help="等待秒数")

    logs = subs.add_parser("logs", help="读取实时或历史控制台日志")
    logs.set_defaults(tool="logs_read")
    filters(logs)
    logs.add_argument("--timeout", type=float, help="等候新日志的秒数")
    logs.add_argument("--follow", action="store_true", help="持续输出实时日志，每条一行 JSON")
    events = subs.add_parser("events", help="读取或等待游戏事件")
    events.add_argument("--wait", action="store_true", help="等候匹配的事件")
    events.add_argument("--timeout", type=float, help="等待时间，仅用于 --wait")
    filters(events, event=True)

    docs = subs.add_parser("docs", help="搜索或分页阅读本地文档")
    doc_cmds = docs.add_subparsers(dest="doc_command", required=True)
    search = doc_cmds.add_parser("search", help="搜索文档")
    search.set_defaults(tool="docs_search")
    search.add_argument("query", nargs="?", default="", help="搜索词")
    search.add_argument("--limit", type=int)
    get = doc_cmds.add_parser("get", help="按搜索结果中的 ID 读取文档")
    get.set_defaults(tool="docs_get")
    get.add_argument("id")
    get.add_argument("--offset", type=int)
    get.add_argument("--limit", type=int)

    run = subs.add_parser("exec", help="向插件的 execute_code 工具提交代码")
    run.set_defaults(tool="execute_code")
    code = run.add_mutually_exclusive_group(required=True)
    code.add_argument("code", nargs="?", help="代码字符串")
    code.add_argument("--file", help="从 UTF-8 文件读取代码，- 表示标准输入")
    return parser


def read_input(path):
    if path == "-":
        return sys.stdin.buffer.read().decode("utf-8-sig")
    return Path(path).read_text(encoding="utf-8-sig")


def print_json(value, *, pretty=False, stream=None):
    stream = sys.stdout if stream is None else stream
    text = json.dumps(value, ensure_ascii=False, indent=2 if pretty else None)
    stream.buffer.write(text.encode("utf-8") + b"\n")
    stream.buffer.flush()


def follow_logs(bridge, values):
    if "date" in values:
        raise ValueError("--follow 用于实时日志，历史日志请指定 --date 分页读取")
    if values.get("timeout", 10) <= 0:
        raise ValueError("--follow 的 --timeout 必须大于零")
    values.setdefault("timeout", 10)
    retry_delay = 1
    while True:
        try:
            page = bridge.call("logs_read", values)
        except BridgeError as exc:
            if exc.code not in ("offline", "transport"):
                raise
            if retry_delay == 1:
                print_json({"reconnecting": str(exc)}, stream=sys.stderr)
            time.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, 5)
            continue
        retry_delay = 1
        if (not isinstance(page, dict) or not isinstance(page.get("items"), list)
                or not isinstance(page.get("session"), str)
                or type(page.get("next_cursor")) is not int):
            raise BridgeError("bad_response", "日志返回缺少有效的会话、游标或记录")
        values.update(session=page["session"], after=page["next_cursor"])
        if page.get("gap") or page.get("reset"):
            print_json({"session": page["session"], "next_cursor": page["next_cursor"],
                        "gap": bool(page.get("gap")), "reset": bool(page.get("reset"))},
                       stream=sys.stderr)
        for row in page["items"]:
            print_json(row)
        if page.get("closed"):
            time.sleep(1)


def run(args):
    bridge = Bridge(args.connection)
    if args.subcommand == "serve":
        Server(bridge).run()
        return
    if args.subcommand == "tools":
        return {"tools": bridge.tools()}
    if args.subcommand == "call":
        raw = read_input(args.file) if args.file else args.arguments
        data = json.loads(raw) if raw is not None else {}
        if not isinstance(data, dict):
            raise ValueError("工具参数必须是 JSON 对象")
        return bridge.call(args.name, data)
    if args.subcommand == "exec":
        code = read_input(args.file) if args.file else args.code
        return bridge.call("execute_code", {"code": code})
    if args.subcommand == "events":
        if args.timeout is not None and not args.wait:
            raise ValueError("events --timeout 需要同时指定 --wait")
        args.tool = "events_wait" if args.wait else "events_read"
        del args.wait
    routing = {"connection", "subcommand", "tool", "doc_command", "follow"}
    values = {k: v for k, v in vars(args).items() if k not in routing and v is not None}
    if args.subcommand == "logs" and args.follow:
        return follow_logs(bridge, values)
    return bridge.call(args.tool, values)


def main(argv=None):
    parser = parser_for_cli()
    args = parser.parse_args(argv)
    try:
        result = run(args)
        if args.subcommand != "serve":
            print_json(result, pretty=True)
        return 0
    except KeyboardInterrupt:
        return 130
    except (BridgeError, OSError, ValueError) as exc:
        code = exc.code if isinstance(exc, BridgeError) else "client"
        print_json({"error": {"code": code, "message": str(exc)}}, stream=sys.stderr)
        return 1
