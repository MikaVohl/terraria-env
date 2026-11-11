import json
import os
from pathlib import Path
import shutil
import socket
import tempfile
import threading
import unittest

from tools.terrabot.sandbox import run_program

TB_DIR = Path(__file__).resolve().parents[1] / "terrariabench"


class JsonLineServer:
    """Tiny AF_UNIX server answering each JSON-lines request with {"id", "ok": true, "result": request}."""

    def __init__(self, path):
        self.path = path
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.bind(path)
        self.sock.listen(4)
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()

    def _serve(self):
        while True:
            try:
                conn, _ = self.sock.accept()
            except OSError:
                return
            threading.Thread(target=self._client, args=(conn,), daemon=True).start()

    @staticmethod
    def _client(conn):
        with conn, conn.makefile("rwb", buffering=0) as f:
            for line in f:
                req = json.loads(line)
                f.write((json.dumps({"id": req.get("id"), "ok": True, "result": req}) + "\n").encode())

    def close(self):
        self.sock.close()
        os.unlink(self.path)


class SandboxTest(unittest.TestCase):
    def setUp(self):
        self.ws = Path(tempfile.mkdtemp(prefix="tbsb-ws-"))
        self.outside = Path(tempfile.mkdtemp(prefix="tbsb-out-"))
        self.sock_path = f"/tmp/tbsb-{os.getpid()}-{id(self) % 10000}.sock"
        self.addCleanup(shutil.rmtree, self.ws, True)
        self.addCleanup(shutil.rmtree, self.outside, True)

    def run_code(self, code, **kw):
        kw.setdefault("timeout", 20)
        return run_program(code, workspace=self.ws, socket_path=self.sock_path, tb_dir=TB_DIR, **kw)

    def assertBlocked(self, code):
        r = self.run_code(f"try:\n    {code}\nexcept PermissionError as e:\n    print('BLOCKED', e)\n")
        self.assertEqual(r["exit"], "ok", r)
        self.assertIn("BLOCKED", r["stdout"], r)
        return r

    def test_normal_program(self):
        r = self.run_code("import json, math, tb, collections, re, dataclasses\nprint(json.dumps({'pi': round(math.pi, 2)}))"
                          "\nprint(tb.API_VERSION)\nimport sys\nprint(sys.flags.isolated)")
        self.assertEqual(r["exit"], "ok", r)
        self.assertEqual(r["returncode"], 0)
        self.assertEqual(r["stdout"].split(), ['{"pi":', '3.14}', "tb-api-1.0", "1"])
        self.assertEqual(r["traceback_tail"], "")
        self.assertEqual(r["name"], "program")
        self.assertTrue((self.ws / "programs" / "program.py").exists())

    def test_error_traceback(self):
        r = self.run_code("def f():\n    raise ValueError('boom')\nprint('before')\nf()", name="bad")
        self.assertEqual(r["exit"], "error")
        self.assertEqual(r["returncode"], 1)
        self.assertIn("before", r["stdout"])
        self.assertIn("ValueError: boom", r["traceback_tail"])
        self.assertIn("bad.py", r["traceback_tail"])
        self.assertNotIn("runpy", r["traceback_tail"])

    def test_third_party_unavailable(self):
        r = self.run_code("import sys\nprint([p for p in sys.path if 'site-packages' in p or 'dist-packages' in p])\n"
                          "for m in ('numpy', 'requests', 'PIL', 'pip'):\n"
                          "    try:\n        __import__(m)\n        print('IMPORTED', m)\n"
                          "    except ImportError:\n        pass\n")
        self.assertEqual(r["exit"], "ok", r)
        self.assertEqual(r["stdout"].strip(), "[]")

    def test_site_packages_not_readable(self):
        import sysconfig
        purelib = sysconfig.get_paths()["purelib"]
        self.assertBlocked(f"import os; os.listdir({purelib!r})")

    def test_read_outside_blocked(self):
        self.assertBlocked("open('/etc/hosts').read()")
        ssh = os.path.join(os.path.expanduser("~"), ".ssh")
        self.assertBlocked(f"import os; os.listdir({ssh!r})")
        self.assertBlocked(f"open({os.path.join(ssh, 'id_rsa')!r}).read()")
        self.assertBlocked("open('../../../../../../../etc/passwd').read()")

    def test_write_outside_blocked(self):
        target = self.outside / "x.txt"
        self.assertBlocked(f"open({str(target)!r}, 'w').write('x')")
        self.assertBlocked(f"import os; os.open({str(target)!r}, os.O_WRONLY | os.O_CREAT)")
        self.assertBlocked(f"import os; os.mkdir({str(self.outside / 'd')!r})")
        self.assertBlocked(f"import os; os.symlink('/etc/hosts', 'link')")
        self.assertFalse(target.exists())
        self.assertFalse((self.outside / "d").exists())

    def test_symlink_escape_blocked(self):
        r = self.run_code("import os\ntry:\n    os.symlink('/tmp', 'out')\nexcept PermissionError:\n    print('B1')\n"
                          "try:\n    os.symlink('..', 'up')\nexcept PermissionError:\n    print('B2')\n")
        self.assertEqual(r["stdout"].split(), ["B1", "B2"], r)

    def test_write_inside_workspace(self):
        r = self.run_code("import os\nos.makedirs('data/sub', exist_ok=True)\nopen('data/sub/a.txt', 'w').write('hi')\n"
                          "os.rename('data/sub/a.txt', 'data/b.txt')\nprint(open('data/b.txt').read(), os.listdir('data'))")
        self.assertEqual(r["exit"], "ok", r)
        self.assertEqual((self.ws / "data" / "b.txt").read_text(), "hi")

    def test_helper_module_import(self):
        (self.ws / "helpers.py").write_text("def twice(x):\n    return 2 * x\n")
        r = self.run_code("import helpers\nprint(helpers.twice(21))")
        self.assertEqual(r["stdout"].strip(), "42", r)

    def test_network_blocked(self):
        self.assertBlocked("import socket; socket.create_connection(('1.1.1.1', 80), timeout=2)")
        self.assertBlocked("import socket; socket.socket(socket.AF_INET, socket.SOCK_DGRAM)")
        self.assertBlocked("import socket; socket.getaddrinfo('example.com', 80)")
        r = self.run_code("import urllib.request, urllib.error\ntry:\n"
                          "    urllib.request.urlopen('http://example.com', timeout=2)\n"
                          "except urllib.error.URLError as e:\n    print(type(e.reason).__name__)\n")
        self.assertEqual(r["stdout"].strip(), "PermissionError", r)
        self.assertBlocked("import socket; s = socket.socket(socket.AF_UNIX); s.connect('/var/run/syslog')")

    def test_processes_blocked(self):
        self.assertBlocked("import subprocess; subprocess.run(['echo', 'hi'])")
        self.assertBlocked("import os; os.system('echo hi')")
        self.assertBlocked("import os; os.fork()")
        self.assertBlocked("import os; os.execv('/bin/echo', ['echo'])")
        self.assertBlocked("import _posixsubprocess; _posixsubprocess.fork_exec()")
        self.assertBlocked("import os; os.kill(os.getppid(), 0)")

    def test_ctypes_blocked(self):
        self.assertBlocked("import ctypes")
        self.assertBlocked("import _ctypes")

    def test_timeout_kills(self):
        r = self.run_code("print('start', flush=True)\nwhile True:\n    pass\n", timeout=2)
        self.assertEqual(r["exit"], "timeout")
        self.assertIn("start", r["stdout"])
        self.assertLess(r["seconds"], 6)

    def test_output_truncated(self):
        r = self.run_code("print('A' * 50000)\nprint('END')", max_output=1000)
        self.assertLess(len(r["stdout"]), 1100)
        self.assertIn("bytes truncated", r["stdout"])
        self.assertTrue(r["stdout"].startswith("AAAA"))
        self.assertIn("END", r["stdout"])

    def test_cleanup_called(self):
        calls = []
        r = run_program("print(1)", workspace=self.ws, socket_path=self.sock_path, tb_dir=TB_DIR, timeout=20,
                        cleanup=lambda: calls.append(1))
        self.assertEqual(r["exit"], "ok")
        self.assertEqual(calls, [1])

    def test_store_persists(self):
        r1 = self.run_code("import tb\ntb.store['n'] = tb.store.get('n', 0) + 1\ntb.store['path'] = [1, 2]\nprint(tb.store['n'])")
        self.assertEqual(r1["exit"], "ok", r1)
        r2 = self.run_code("import tb\ntb.store['n'] = tb.store.get('n', 0) + 1\nprint(tb.store['n'], tb.store['path'])")
        self.assertEqual(r2["stdout"].strip(), "2 [1, 2]", r2)
        self.assertEqual(json.loads((self.ws / "store.json").read_text())["n"], 2)

    def test_env_minimal(self):
        r = self.run_code("import os\nprint(sorted(os.environ))\nprint(os.environ['HOME'] == os.getcwd())")
        self.assertEqual(r["exit"], "ok", r)
        lines = r["stdout"].splitlines()
        self.assertEqual(set(eval(lines[0])) - {"__CF_USER_TEXT_ENCODING"}, {"HOME", "LANG", "PATH", "TB_SOCKET", "TB_STORE"})
        self.assertEqual(lines[1], "True")

    def test_unix_socket_allowed(self):
        server = JsonLineServer(self.sock_path)
        self.addCleanup(server.close)
        r = self.run_code("import socket, os, tb\nfrom tb import _rpc\n"
                          "s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)\ns.connect(os.environ['TB_SOCKET'])\n"
                          "s.sendall(b'{\"id\": 7}\\n')\nprint(s.makefile('rb').readline().decode().strip())\n"
                          "print(_rpc.call('ping', a=1)['args'])\n")
        self.assertEqual(r["exit"], "ok", r)
        lines = r["stdout"].splitlines()
        self.assertEqual(json.loads(lines[0])["id"], 7)
        self.assertEqual(lines[1], "{'a': 1}")


if __name__ == "__main__":
    unittest.main()
