"""Minimal VT100 screen reconstructor: replays a captured frame stream and
prints the final screen. Used to eyeball the renderer without a human at a tty."""
import re
import sys

W, H = 200, 60
COLOR = "--color" in sys.argv


def main():
    data = sys.stdin.buffer.read().decode("utf-8", "replace")
    grid = [[" "] * W for _ in range(H)]
    attr = [[""] * W for _ in range(H)]
    r = c = 0
    sgr = ""
    i = 0
    while i < len(data):
        ch = data[i]
        if ch == "\x1b" and i + 1 < len(data) and data[i + 1] == "[":
            m = re.match(r"\x1b\[([0-9;]*)([A-Za-z])", data[i:])
            if not m:
                i += 1
                continue
            params, cmd = m.group(1), m.group(2)
            nums = [int(p) for p in params.split(";") if p != ""]
            if cmd == "H":
                r = (nums[0] - 1) if len(nums) > 0 else 0
                c = (nums[1] - 1) if len(nums) > 1 else 0
            elif cmd == "J":
                n = nums[0] if nums else 0
                if n == 2:
                    grid = [[" "] * W for _ in range(H)]
                elif n == 0:
                    for rr in range(r + 1, H):
                        grid[rr] = [" "] * W
            elif cmd == "K":
                if 0 <= r < H:
                    for cc in range(c, W):
                        grid[r][cc] = " "
            elif cmd == "m":
                sgr = "" if (not nums or nums == [0]) else m.group(0)
            i += m.end()
            continue
        if ch == "\n":
            r, c = r + 1, 0
        elif ch == "\r":
            c = 0
        elif ch >= " ":
            if 0 <= r < H and 0 <= c < W:
                grid[r][c] = ch
                attr[r][c] = sgr
            c += 1
        i += 1

    last = max((y for y in range(H) if "".join(grid[y]).strip()), default=0)
    for y in range(last + 1):
        row = "".join(grid[y]).rstrip()
        if COLOR:
            out, cur = [], ""
            for x, g in enumerate(grid[y][: len(row)]):
                a = attr[y][x]
                if a != cur:
                    out.append("\x1b[0m" + a)
                    cur = a
                out.append(g)
            row = "".join(out) + "\x1b[0m"
        print(row)


main()
