"""把 results.json（三條件）與 results_neckline.json（頸線）嵌進 template.html，產出 index.html（GitHub Pages 入口）。"""
import json, pathlib
here = pathlib.Path(__file__).parent
dump = lambda f: json.dumps(json.load(open(here / f, encoding="utf-8")), ensure_ascii=False, separators=(",", ":"))
html = (here / "template.html").read_text(encoding="utf-8").replace("/*DATA3*/", dump("results.json")).replace("/*DATANECK*/", dump("results_neckline.json"))
(here / "index.html").write_text(html, encoding="utf-8")
print("index.html", len(html) // 1024, "KB")
