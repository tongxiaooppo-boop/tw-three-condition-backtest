"""把 results.json 嵌進 template.html，產出 index.html（GitHub Pages 入口）。"""
import json, pathlib
here = pathlib.Path(__file__).parent
data = json.dumps(json.load(open(here / "results.json", encoding="utf-8")), ensure_ascii=False, separators=(",", ":"))
html = (here / "template.html").read_text(encoding="utf-8").replace("/*DATA*/", data)
(here / "index.html").write_text(html, encoding="utf-8")
print("index.html", len(html) // 1024, "KB")
