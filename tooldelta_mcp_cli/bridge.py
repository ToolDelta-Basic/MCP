"""Authenticated JSON calls to the ToolDelta plugin on loopback."""

import http.client
import ipaddress
import json
import os
from functools import cache
from importlib import resources
from itertools import zip_longest
from pathlib import Path
from urllib.parse import urlsplit

from . import wiki


LEGACY_RELATIVE = Path("插件数据文件") / "MCP游戏桥" / "connection.json"
DEFAULT_RELATIVE = Path("插件数据文件") / "ToolDelta-MCP" / "connection.json"
PROJECT = Path(r"D:\gitclone\ToolDelta")
MAX_RESPONSE = 16 * 1024 * 1024
DOC_TOOLS = ("docs_search", "docs_get")


class BridgeError(Exception):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


class BridgeUnavailable(BridgeError):
    """No live bridge response was obtained."""


@cache
def _bundled_tools():
    schemas = resources.files(__package__).joinpath("schemas.json")
    return {tool["name"]: tool for tool in json.loads(schemas.read_text(encoding="utf-8"))}


def _validate_doc_args(name, arguments):
    schema = _bundled_tools()[name]["inputSchema"]
    if missing := set(schema.get("required", [])) - arguments.keys():
        raise BridgeError(-32602, "缺少参数 " + ", ".join(sorted(missing)))
    for key, value in arguments.items():
        spec = schema["properties"].get(key)
        if spec is None:
            raise BridgeError(-32602, "未知参数 " + key)
        if spec["type"] == "string":
            valid = isinstance(value, str) and len(value) <= spec["maxLength"]
        else:
            valid = type(value) is int and spec["minimum"] <= value <= spec["maximum"]
        if not valid:
            raise BridgeError(-32602, "参数值无效 " + key)


def _require_wiki():
    if not wiki.available():
        raise BridgeError(
            "wiki_unavailable",
            "未找到内置 Wiki。使用源码时请运行 git submodule update --init；安装版请重新安装包含 Wiki 的包。",
        )


class Bridge:
    def __init__(self, connection=None):
        self.connection = connection or os.environ.get("TOOLDELTA_MCP_CONNECTION")

    def _endpoint(self):
        if self.connection:
            path = Path(self.connection).expanduser()
            if path.parts[-3:] == LEGACY_RELATIVE.parts:
                renamed = path.parent.parent / "ToolDelta-MCP" / "connection.json"
                if renamed.is_file():
                    path = renamed
        else:
            candidates = [base / relative for base in (Path.cwd(), PROJECT)
                          for relative in (DEFAULT_RELATIVE, LEGACY_RELATIVE)]
            path = next((p for p in candidates if p.is_file()), candidates[0])
        try:
            config = json.loads(path.read_text(encoding="utf-8-sig"))
        except FileNotFoundError:
            message = f"找不到连接文件 {path}，请启动 ToolDelta 游戏桥或指定 --connection"
            raise BridgeUnavailable("offline", message) from None
        except (OSError, UnicodeError, ValueError) as exc:
            raise BridgeError("connection_file", f"无法读取连接文件 {path}: {exc}") from None
        if not isinstance(config, dict):
            raise BridgeError("connection_file", "连接文件应包含 url 和 token")
        url, token = config.get("url"), config.get("token")
        if not isinstance(url, str) or not isinstance(token, str) or not token:
            raise BridgeError("connection_file", "连接文件缺少 url 或 token")
        if (
            not token.isascii() or not token.isprintable()
            or any(c.isspace() for c in token)
        ):
            raise BridgeError("connection_file", "连接令牌的格式无效")
        try:
            parts = urlsplit(url)
            host = parts.hostname or ""
            if host.lower() == "localhost":
                host = "127.0.0.1"
            if (
                parts.scheme != "http"
                or not ipaddress.ip_address(host).is_loopback
                or parts.username is not None
                or parts.password is not None
                or parts.query
                or parts.fragment
                or parts.path.rstrip("/") not in ("", "/rpc")
            ):
                raise ValueError()
            port = parts.port or 80
        except ValueError:
            raise BridgeError("connection_file", "连接地址必须是本机回环 HTTP 端点") from None
        return host, port, token

    def _rpc(self, method, params, timeout):
        host, port, token = self._endpoint()
        conn = http.client.HTTPConnection(host, port, timeout=timeout)
        data = {"method": method, "params": params}
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        try:
            conn.request("POST", "/rpc", body, {
                "Content-Type": "application/json; charset=utf-8",
                "Authorization": "Bearer " + token,
            })
            reply = conn.getresponse()
            if 300 <= reply.status < 400:
                raise BridgeError("http_redirect", "游戏桥返回了重定向，请检查连接文件")
            raw = reply.read(MAX_RESPONSE + 1)
            if len(raw) > MAX_RESPONSE:
                raise BridgeError("response_size", "游戏桥响应过大，请分页或缩小查询范围")
        except (OSError, http.client.HTTPException) as exc:
            message = f"游戏桥连接中断或不可用: {exc}。已发送的操作可能已执行"
            raise BridgeUnavailable("transport", message) from None
        finally:
            conn.close()
        try:
            data = json.loads(raw)
        except (ValueError, UnicodeError):
            raise BridgeError("bad_response", f"游戏桥未返回 JSON (HTTP {reply.status})") from None
        if isinstance(data, dict) and isinstance(data.get("error"), dict):
            error = data["error"]
            code = error.get("code", "bridge")
            raise BridgeError(code, str(error.get("message", "游戏桥返回错误")))
        if not 200 <= reply.status < 300:
            raise BridgeError(reply.status, f"游戏桥请求失败 (HTTP {reply.status})")
        if not isinstance(data, dict) or "result" not in data:
            raise BridgeError("bad_response", "游戏桥响应缺少 result")
        return data["result"]

    def tools(self):
        try:
            data = self._rpc("tools/list", {}, 10)
        except BridgeUnavailable:
            return list(_bundled_tools().values())
        if not isinstance(data, dict) or not isinstance(data.get("tools"), list):
            raise BridgeError("bad_response", "游戏桥未返回工具列表")
        docs = {name: _bundled_tools()[name] for name in DOC_TOOLS}
        tools = [docs.pop(tool["name"], tool) for tool in data["tools"]]
        return tools + list(docs.values())

    def call(self, name, arguments):
        if name in DOC_TOOLS:
            _validate_doc_args(name, arguments)
            if name == "docs_search":
                return self._search_docs(arguments)
            if arguments["id"].startswith(wiki.ID_PREFIX):
                _require_wiki()
                try:
                    return wiki.get(**arguments)
                except KeyError:
                    raise BridgeError(-32602, "未知文档 ID，请先用 docs_search 查询") from None
        return self._call_bridge(name, arguments)

    def _search_docs(self, arguments):
        terms = arguments.get("query", "").casefold().split()
        limit = arguments.get("limit", 15)
        local = wiki.search(terms, limit)
        try:
            remote = self._call_bridge("docs_search", arguments)
        except BridgeError as exc:
            # The bridge can be offline or reject this tool via its plugin configuration.
            if not isinstance(exc, BridgeUnavailable) and exc.code not in ("connection_file", -32602):
                raise
            _require_wiki()
            return local
        if not local["total"]:
            return remote
        if (not isinstance(remote, dict) or type(remote.get("total")) is not int
                or not isinstance(remote.get("items"), list)):
            raise BridgeError("bad_response", "游戏桥未返回有效的文档搜索结果")
        hits = [
            hit for pair in zip_longest(remote["items"], local["items"])
            for hit in pair if hit is not None
        ]
        hits.sort(key=lambda hit: wiki.rank(hit, terms), reverse=True)
        return {"total": remote["total"] + local["total"], "items": hits[:limit]}

    def _call_bridge(self, name, arguments):
        timeout = arguments.get("timeout", 60 if name == "execute_code" else 30)
        if not isinstance(timeout, (float, int)) or not 0 <= timeout <= 86400:
            timeout = 30
        params = {"name": name, "arguments": arguments}
        try:
            data = self._rpc("tools/call", params, max(30, timeout + 10))
        except BridgeUnavailable as exc:
            if name != "status" or arguments:
                raise
            return {
                "bridge_connected": False, "connected": None, "catalog_source": "bundled",
                "reason": exc.code, "message": str(exc),
            }
        if name == "status" and isinstance(data, dict):
            return {**data, "bridge_connected": True, "catalog_source": "plugin"}
        return data
