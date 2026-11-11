"""In-sandbox bootstrap for TerraBot programs (started by sandbox.py as `python -I -S sandbox_boot.py CONFIG_JSON`).

Sets resource limits, fixes sys.path (stdlib, tb, workspace), installs an audit hook that blocks network, process,
native-code and out-of-workspace file operations, then runs the program with runpy. The audit hook is defence in
depth, not a security boundary on its own (see sandbox.py).
"""
import json
import os
import resource
import runpy
import socket
import sys
import sysconfig
import traceback

import _posixsubprocess  # preloaded so it can be disarmed below; later (re)imports are blocked by the hook

MiB = 1 << 20
# Native modules that open files, load code or talk to the display outside the audit hook's view.
BLOCKED_IMPORTS = frozenset({"ctypes", "_ctypes", "_posixsubprocess", "_sqlite3", "_dbm", "_gdbm", "_posixshmem",
                             "_tkinter", "_multiprocessing", "_remote_debugging"})
PROCESS_EVENTS = frozenset({"subprocess.Popen", "os.system", "os.exec", "os.posix_spawn", "os.spawn", "os.fork",
                            "os.forkpty", "pty.spawn", "os.startfile", "os.popen"})
DNS_EVENTS = frozenset({"socket.getaddrinfo", "socket.gethostbyname", "socket.gethostbyaddr", "socket.getnameinfo",
                        "socket.sethostname"})
OTHER_BLOCKED = {
    "ctypes.dlopen": "loading native code (ctypes)",
    "ctypes.dlsym": "loading native code (ctypes)",
    "ctypes.cdata": "ctypes memory access",
    "sqlite3.connect": "sqlite3 (opens files outside the audit hook)",
    "sqlite3.enable_load_extension": "sqlite3 extensions",
    "sqlite3.load_extension": "sqlite3 extensions",
    "resource.setrlimit": "changing resource limits",
    "resource.prlimit": "changing resource limits",
    "os.chdir": "changing the working directory",
    "os.chroot": "chroot",
    "sys.remote_exec": "remote execution",
    "gc.get_objects": "gc introspection",
    "gc.get_referrers": "gc introspection",
    "gc.get_referents": "gc introspection",
}
# event -> (indexes of path arguments, write?, indexes of dir_fd arguments; the default dir_fd is AT_FDCWD < 0)
FILE_EVENTS = {
    "os.remove": ((0,), True, (1,)),
    "os.rename": ((0, 1), True, (2, 3)),
    "os.mkdir": ((0,), True, (2,)),
    "os.rmdir": ((0,), True, (1,)),
    "os.chmod": ((0,), True, (2,)),
    "os.chown": ((0,), True, (3,)),
    "os.chflags": ((0,), True, ()),
    "os.lchflags": ((0,), True, ()),
    "os.lchmod": ((0,), True, ()),
    "os.truncate": ((0,), True, ()),
    "os.utime": ((0,), True, (3,)),
    "os.setxattr": ((0,), True, ()),
    "os.removexattr": ((0,), True, ()),
    "os.listdir": ((0,), False, ()),
    "os.scandir": ((0,), False, ()),
    "os.getxattr": ((0,), False, ()),
    "os.listxattr": ((0,), False, ()),
}
WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND


def _real(p):
    return os.path.realpath(os.fsdecode(p))


def _under(path, roots):
    return any(path == r or path.startswith(r + os.sep) for r in roots)


def _is_fd(v):
    return isinstance(v, int) and v >= 0


def set_limits(cpu_seconds):
    for name, value in (("RLIMIT_AS", 2048 * MiB), ("RLIMIT_FSIZE", 64 * MiB), ("RLIMIT_NOFILE", 256),
                        ("RLIMIT_CPU", cpu_seconds), ("RLIMIT_CORE", 0)):
        lim = getattr(resource, name, None)
        if lim is None:
            continue
        try:
            resource.setrlimit(lim, (value, value))
        except (ValueError, OSError):
            try:  # e.g. macOS refuses some hard limits: at least lower the soft one
                resource.setrlimit(lim, (value, resource.getrlimit(lim)[1]))
            except (ValueError, OSError):
                pass


def stdlib_roots():
    paths = sysconfig.get_paths()
    roots = {paths.get("stdlib"), paths.get("platstdlib"), os.path.dirname(os.__file__)}
    roots.update(p for p in sys.path if os.path.basename(p) == "lib-dynload")
    roots = {_real(r) for r in roots if r}
    denied = {_real(paths[k]) for k in ("purelib", "platlib") if paths.get(k)}
    return roots, denied


def make_hook(workspace, tb_dir, socket_path):
    ws_roots = (workspace,)
    std, denied = stdlib_roots()
    read_roots = tuple(sorted(std | {tb_dir, workspace}))
    denied = tuple(sorted(denied))
    devices_rw = ("/dev/null",)
    devices_r = ("/dev/null", "/dev/urandom", "/dev/random")
    socket_real = _real(socket_path)
    my_pid = os.getpid()

    def deny(what):
        raise PermissionError(f"sandbox: {what} is not allowed in TerraBot programs")

    def readable(path):
        if _under(path, ws_roots) or path in devices_r:
            return True
        if _under(path, denied) or any(part in ("site-packages", "dist-packages") for part in path.split(os.sep)):
            return False
        return _under(path, read_roots)

    def check_path(p, write, what):
        if isinstance(p, int):  # an already-open descriptor
            return
        try:
            path = _real(p if p is not None else ".")
        except (TypeError, ValueError):
            deny(f"{what} {p!r}")
        if write:
            if not (_under(path, ws_roots) or path in devices_rw):
                deny(f"{what} {path} (writes are limited to the workspace {workspace})")
        elif not readable(path):
            deny(f"{what} {path} (reads are limited to the workspace, tb and the standard library)")
        elif not _under(path, ws_roots) and os.path.isdir(path) and what == "open":
            deny(f"opening directory {path} outside the workspace")

    def check_unix_address(event, address):
        if isinstance(address, (str, bytes)) and address and address[:1] not in ("\0", b"\0"):
            try:
                if _real(address) == socket_real:
                    return
            except (TypeError, ValueError):
                pass
        deny(f"{event} to {address!r} (only the game socket {socket_path} is reachable)")

    def hook(event, args):
        if event == "open":
            path, mode, flags = (tuple(args) + (None, None, None))[:3]
            if isinstance(mode, str):
                write = any(c in mode for c in "wax+")
            else:
                write = bool((flags or 0) & WRITE_FLAGS)
            check_path(path, write, "open")
        elif event in FILE_EVENTS:
            idx, write, dir_fd_idx = FILE_EVENTS[event]
            if any(i < len(args) and _is_fd(args[i]) for i in dir_fd_idx):
                deny(f"{event} with dir_fd")
            for i in idx:
                check_path(args[i] if i < len(args) else None, write, event)
        elif event in ("os.symlink", "os.link"):
            src, dst = args[0], args[1]
            if any(_is_fd(a) for a in args[2:4]):
                deny(f"{event} with dir_fd")
            src_s = os.fsdecode(src)
            if event == "os.symlink" and not os.path.isabs(src_s):
                deny(f"relative symlink target {src_s!r} (use an absolute path inside the workspace)")
            check_path(src, True, f"{event} target")
            check_path(dst, True, event)
        elif event == "import":
            name = args[0] if args else ""
            if isinstance(name, str) and name.rpartition(".")[2] in BLOCKED_IMPORTS:
                deny(f"importing {name}")
            filename = args[1] if len(args) > 1 else None
            if isinstance(filename, (str, bytes)):
                check_path(filename, False, f"importing {name} from")
        elif event == "socket.__new__":
            family = args[1] if len(args) > 1 else None
            if family != socket.AF_UNIX:
                deny(f"creating a non-AF_UNIX socket (family {family})")
        elif event in ("socket.connect", "socket.bind", "socket.sendto", "socket.sendmsg"):
            sock, address = args[0], args[1] if len(args) > 1 else None
            if event == "socket.sendmsg" and address is None:
                return
            if getattr(sock, "family", None) != socket.AF_UNIX:
                deny(f"{event} on a non-AF_UNIX socket")
            check_unix_address(event, address)
        elif event in DNS_EVENTS:
            deny(f"name resolution ({event})")
        elif event in PROCESS_EVENTS:
            deny(f"starting processes ({event})")
        elif event in ("os.kill", "os.killpg"):
            if event == "os.killpg" or (args and args[0] not in (my_pid, 0)):
                deny(f"signalling other processes ({event})")
        elif event in OTHER_BLOCKED:
            deny(OTHER_BLOCKED[event])

    return hook


def _blocked_fork_exec(*args, **kwargs):
    raise PermissionError("sandbox: starting processes (_posixsubprocess.fork_exec) is not allowed in TerraBot programs")


def main():
    cfg = json.loads(sys.argv[1])
    workspace, tb_dir = _real(cfg["workspace"]), _real(cfg["tb_dir"])
    program = _real(cfg["program"])
    set_limits(int(cfg["cpu_seconds"]))
    os.chdir(workspace)
    sys.dont_write_bytecode = True
    sys.path[:] = [p for p in sys.path if p] + [tb_dir, workspace, os.path.join(workspace, "programs")]
    _posixsubprocess.fork_exec = _blocked_fork_exec
    sys.argv[:] = [program]
    sys.addaudithook(make_hook(workspace, tb_dir, cfg["socket"]))
    try:
        runpy.run_path(program, run_name="__main__")
    except SystemExit:
        raise
    except BaseException as e:  # show only the program's own frames, not runpy/bootstrap ones
        tb = e.__traceback__
        while tb is not None and tb.tb_frame.f_code.co_filename != program:
            tb = tb.tb_next
        traceback.print_exception(type(e), e, tb or e.__traceback__)
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(1)  # do not wait for the program's non-daemon threads


if __name__ == "__main__":
    main()
