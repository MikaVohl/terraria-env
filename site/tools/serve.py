"""Static file server for the site with HTTP Range support, so browsers can seek in the run videos.

python -m http.server answers every request with the whole file (200), and browsers then cannot seek
in an MP4. This adds single-range 206 responses and nothing else.

    python3 site/tools/serve.py [port]      # serves the current directory on 127.0.0.1
"""
import os
import re
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer


class Handler(SimpleHTTPRequestHandler):
    def send_head(self):
        m = re.fullmatch(r"bytes=(\d*)-(\d*)", self.headers.get("Range", ""))
        path = self.translate_path(self.path)
        if not m or not os.path.isfile(path):
            return super().send_head()
        size = os.path.getsize(path)
        a, b = m.groups()
        start, end = (int(a), int(b) if b else size - 1) if a else (max(0, size - int(b)), size - 1)
        if start >= size or start > end:
            self.send_error(416, "Range not satisfiable")
            return None
        end = min(end, size - 1)
        f = open(path, "rb")
        f.seek(start)
        self.send_response(206)
        self.send_header("Content-Type", self.guess_type(path))
        self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Content-Length", str(end - start + 1))
        self.send_header("Accept-Ranges", "bytes")
        self.end_headers()
        self.remaining = end - start + 1
        return f

    def copyfile(self, source, outputfile):
        n = getattr(self, "remaining", None)
        if n is None:
            return super().copyfile(source, outputfile)
        while n > 0:
            buf = source.read(min(1 << 16, n))
            if not buf:
                break
            outputfile.write(buf)
            n -= len(buf)

    def end_headers(self):
        if not self.headers.get("Range"):
            self.send_header("Accept-Ranges", "bytes")
        super().end_headers()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8778
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
