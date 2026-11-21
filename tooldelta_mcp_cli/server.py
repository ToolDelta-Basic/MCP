"""Newline-delimited MCP stdio transport. Only tool capabilities are advertised."""

import json
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

from . import __version__
from .bridge import BridgeError


VERSIONS = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")


class RpcError(Exception):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


def tool_result(data, version, error=False):
    text = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False)
    result = {"content": [{"type": "text", "text": text}], "isError": error}
    if version >= "2025-06-18" and isinstance(data, dict) and not error:
        result["structuredContent"] = data
    return result


class Server:
    def __init__(self, bridge):
        self.bridge = bridge
        self.version = None
        self.output_lock = threading.Lock()
        self.pending_lock = threading.Lock()
        self.pending = {}
        self.capacity = threading.BoundedSemaphore(32)

    def send(self, request_id, *, result=None, error=None):
        message = {"jsonrpc": "2.0", "id": request_id}
        if error is None:
            message["result"] = result
        else:
            message["error"] = error
        payload = json.dumps(message, ensure_ascii=False, separators=(",", ":"))
        with self.output_lock:
            sys.stdout.buffer.write(payload.encode("utf-8") + b"\n")
            sys.stdout.buffer.flush()

    def dispatch(self, method, params):
        if method == "initialize":
            requested = params.get("protocolVersion")
            if not isinstance(requested, str):
                raise RpcError(-32602, "Missing protocolVersion")
            self.version = requested if requested in VERSIONS else VERSIONS[0]
            return {
                "protocolVersion": self.version,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "tooldelta-mcp", "version": __version__},
            }
        if method == "ping":
            return {}
        if self.version is None:
            raise RpcError(-32600, "Initialize the MCP session first")
        if method == "tools/list":
            return {"tools": self.bridge.tools()}
        if method == "tools/call":
            name, args = params.get("name"), params.get("arguments", {})
            if not isinstance(name, str) or not isinstance(args, dict):
                raise RpcError(-32602, "Expected a tool name and an arguments object")
            try:
                return tool_result(self.bridge.call(name, args), self.version)
            except BridgeError as exc:
                detail = {"code": exc.code, "message": str(exc)}
                return tool_result(detail, self.version, error=True)
        raise RpcError(-32601, "Method not found")

    def process(self, request_id, method, params, cancelled=None):
        try:
            if cancelled is not None and cancelled.is_set():
                return
            try:
                output = {"result": self.dispatch(method, params)}
            except RpcError as exc:
                output = {"error": {"code": exc.code, "message": str(exc)}}
            except BridgeError as exc:
                output = {"error": {
                    "code": -32000, "message": str(exc), "data": {"code": exc.code}
                }}
            except Exception as exc:
                output = {"error": {"code": -32603, "message": str(exc)}}
            if cancelled is None or not cancelled.is_set():
                self.send(request_id, **output)
        finally:
            if cancelled is not None:
                with self.pending_lock:
                    self.pending.pop(request_id, None)
                self.capacity.release()

    def accept(self, msg, pool):
        if (
            not isinstance(msg, dict)
            or msg.get("jsonrpc") != "2.0"
            or not isinstance(msg.get("method"), str)
        ):
            self.send(None, error={"code": -32600, "message": "Invalid request"})
            return
        method, params = msg["method"], msg.get("params", {})
        if "id" not in msg:
            if method == "notifications/cancelled" and isinstance(params, dict):
                target = params.get("requestId")
                if type(target) in (str, int):
                    with self.pending_lock:
                        event = self.pending.get(target)
                        if event is not None:
                            event.set()
            return
        request_id = msg["id"]
        if type(request_id) not in (str, int):
            self.send(None, error={"code": -32600, "message": "Invalid request ID"})
            return
        if not isinstance(params, dict):
            error = {"code": -32602, "message": "Expected an object for params"}
            self.send(request_id, error=error)
            return
        if method not in ("tools/list", "tools/call"):
            self.process(request_id, method, params)
            return
        with self.pending_lock:
            if request_id in self.pending:
                error = {"code": -32600, "message": "Request ID already in use"}
                self.send(request_id, error=error)
                return
            if not self.capacity.acquire(blocking=False):
                error = {"code": -32000, "message": "Too many requests in flight"}
                self.send(request_id, error=error)
                return
            cancelled = threading.Event()
            self.pending[request_id] = cancelled
        pool.submit(self.process, request_id, method, params, cancelled)

    def run(self):
        with ThreadPoolExecutor(max_workers=8) as pool:
            for line in sys.stdin.buffer:
                if not line.strip():
                    continue
                try:
                    msg = json.loads(line)
                except (ValueError, UnicodeError):
                    self.send(None, error={"code": -32700, "message": "Parse error"})
                    continue
                self.accept(msg, pool)
