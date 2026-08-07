"""Drive terraria-lite in a real pty of a chosen size, send a key script, and
dump the final screen. This is the human-in-the-loop smoke test, minus human."""
import fcntl
import os
import pty
import select
import struct
import subprocess
import sys
import termios
import time

cols, rows = 120, 46
keys = sys.argv[1] if len(sys.argv) > 1 else "q"
seed = sys.argv[2] if len(sys.argv) > 2 else "9"

mfd, sfd = pty.openpty()
fcntl.ioctl(sfd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
p = subprocess.Popen(
    # --lockstep: one tick per keystroke. A real-time frontend would advance
    # the world between writes and make this replay nondeterministic.
    ["./terraria-lite", "--lockstep", "--seed", seed],
    stdin=sfd, stdout=sfd, stderr=sfd, close_fds=True,
)
os.close(sfd)

out = bytearray()


def pump(t=0.15):
    end = time.time() + t
    while time.time() < end:
        r, _, _ = select.select([mfd], [], [], 0.02)
        if r:
            try:
                chunk = os.read(mfd, 65536)
            except OSError:
                return
            if not chunk:
                return
            out.extend(chunk)


pump(0.3)
for k in keys:
    try:
        os.write(mfd, k.encode())
    except OSError:
        break
    pump(0.03)
pump(0.4)

try:
    p.terminate()
except Exception:
    pass
os.close(mfd)
sys.stdout.buffer.write(bytes(out))
