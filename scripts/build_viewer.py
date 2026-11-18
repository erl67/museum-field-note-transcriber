"""Embed the client source in the three-file Apps Script installation. Offline only."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
viewer = ROOT / "apps_script" / "viewer"
html = (viewer / "Viewer.html").read_text(encoding="utf-8")
client = (viewer / "client.js").read_text(encoding="utf-8")
html = re.sub(r"  <script>[\s\S]*?</script>", lambda _: "  <script>\n" + client + "\n  </script>", html)
(viewer / "Viewer.html").write_text(html, encoding="utf-8", newline="\n")
