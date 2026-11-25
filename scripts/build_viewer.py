"""Embed the client and optionally prepare a configured, three-file manual installation."""
import argparse
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
viewer = ROOT / "apps_script" / "viewer"
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--scan-root", help="Original scans' Drive folder ID")
parser.add_argument("--index-parent", help="Drive folder ID containing Field_notes_index")
parser.add_argument("--public-notes", metavar="PATH", help=argparse.SUPPRESS)
args = parser.parse_args()
if args.public_notes is not None:
    parser.error("To publish that subset, pass --viewer-notes PATH to fieldnotes publish --viewer-only. "
                 "Build the viewer using just --scan-root and --index-parent.")
if any((args.scan_root, args.index_parent)) and not all(
        re.fullmatch(r"[A-Za-z0-9_-]{10,}", v or "") for v in (args.scan_root, args.index_parent)):
    parser.error("Provide both --scan-root and --index-parent with valid Drive folder IDs")
html = (viewer / "Viewer.html").read_text(encoding="utf-8")
client = (viewer / "client.js").read_text(encoding="utf-8")
html = re.sub(r"  <script>[\s\S]*?</script>", lambda _: "  <script>\n" + client + "\n  </script>", html)
(viewer / "Viewer.html").write_text(html, encoding="utf-8", newline="\n")
if args.index_parent:
    install = ROOT / "local/apps-script-install"
    install.mkdir(parents=True, exist_ok=True)
    code = (viewer / "Code.gs").read_text("utf-8") + "\n" + (viewer / "Index.gs").read_text("utf-8")
    for key, value in (("SCAN_ROOT_FOLDER_ID", args.scan_root), ("INDEX_PARENT_FOLDER_ID", args.index_parent)):
        code, count = re.subn(rf"(?m)^  {key}: '',", f"  {key}: '{value}',", code)
        if count != 1:
            parser.error(f"Expected one blank {key} in the template")
    (install / "Code.gs").write_text(code, encoding="utf-8", newline="\n")
    (install / "Viewer.html").write_text(html, encoding="utf-8", newline="\n")
    (install / "appsscript.json").write_bytes((viewer / "appsscript.json").read_bytes())
    print(f"Manual installation ready in {install}")
