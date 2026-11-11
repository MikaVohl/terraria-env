"""JSON-lines RPC over a Unix socket (the per-run proxy, which forwards to the TerraBot mod)."""
import itertools
import json
import os
import socket
import threading


class TbError(RuntimeError):
    """An API call the game refused (e.g. 'cannot craft Furnace: missing station WorkBenches')."""


class Connection:
    def __init__(self, path=None):
        self.path = path or os.environ.get("TB_SOCKET")
        if not self.path:
            raise TbError("TB_SOCKET is not set: tb programs run inside the TerraBot runner")
        self.sock = None
        self.ids = itertools.count(1)
        self.lock = threading.Lock()

    def _connect(self):
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.connect(self.path)
        self.sock, self.file = s, s.makefile("rwb", buffering=0)

    def call(self, op, **args):
        with self.lock:
            if self.sock is None:
                self._connect()
            rid = next(self.ids)
            self.file.write((json.dumps({"id": rid, "op": op, "args": args}) + "\n").encode())
            line = self.file.readline()
            if not line:
                self.sock = None
                raise TbError("connection to the game closed")
            reply = json.loads(line)
        if not reply.get("ok"):
            raise TbError(f"{op}: {reply.get('error')}")
        return reply.get("result")

    def close(self):
        if self.sock:
            self.sock.close()
            self.sock = None


_conn = None


def call(op, **args):
    global _conn
    if _conn is None:
        _conn = Connection()
    return _conn.call(op, **args)
