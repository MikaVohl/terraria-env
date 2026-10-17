"""Generate a local, self-contained-in-directory replay report from a live run."""
import argparse
import html
import json
from pathlib import Path


def render(root):
    root = Path(root)
    manifest = json.loads((root / "manifest.json").read_text())
    result = json.loads((root / "result.json").read_text())
    escape = html.escape
    cards = []
    for reqpath in sorted(root.glob("request-*.json")):
        request = json.loads(reqpath.read_text())
        step = request["context"]["step"]
        responsepath = root / f"response-{step:03d}.json"
        response = json.loads(responsepath.read_text()) if responsepath.exists() else {}
        content = (response.get("choices") or [{}])[0].get("message", {}).get("content", "No completed response")
        try:
            content = json.dumps(json.loads(content), indent=2)
        except (ValueError, TypeError):
            content = str(content)
        cards.append(f'<section><h2>Decision {step + 1}</h2><div class="decision">'
                     f'<a href="frames/{step:05d}.png"><img src="frames/{step:05d}.png" alt="Game frame {step + 1}" loading="lazy"></a>'
                     f'<pre>{escape(content)}</pre></div><p>Usage: {escape(json.dumps(response.get("usage", {})))}</p></section>')
    title = escape(manifest["model"]["id"])
    content = f'''<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>TerrariaBench development replay</title>
<style>body{{background:#101713;color:#e4eee7;font:16px system-ui;max-width:1500px;margin:auto;padding:32px}}
h1{{font-size:32px}}h2{{font-size:20px}}.notice{{padding:16px;background:#3c3417;border-radius:8px}}
section{{margin:28px 0;padding:20px;background:#1b2620;border-radius:12px}}.decision{{display:grid;grid-template-columns:2fr 1fr;gap:20px}}
img{{width:100%;height:auto}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;max-height:600px;overflow:auto;font-size:13px}}
p{{overflow-wrap:anywhere}}a{{color:#a3deb7}}@media(max-width:900px){{.decision{{display:block}}}}</style>
<h1>TerrariaBench · {title}</h1><p class="notice">Development smoke only. Unofficial; one world and one attempt are not a model comparison.</p>
<section><h2>Evaluator result</h2><pre>{escape(json.dumps(result, indent=2))}</pre>
<a href="manifest.json">Frozen manifest</a> · <a href="result.json">Result JSON</a> · <a href="inputs.jsonl">OS input receipts</a></section>
{''.join(cards)}<section><h2>Final observation</h2><img src="final.png" alt="Final game observation"></section></html>'''
    path = root / "index.html"
    path.write_text(content)
    return path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    print(render(parser.parse_args().run))
