"""Build local/demo from the invented cards in test/inputs. Uses no external services."""
import json
from pathlib import Path
import sys
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from fieldnotes.config import Config
from fieldnotes.discovery import discover
from fieldnotes.execution import checkpoint_result
from fieldnotes.exports import export_all
from fieldnotes.images import prepare_request
from fieldnotes.schema import empty_document, validate_document
from fieldnotes.storage import Store, digest, encoded, lock
from fieldnotes.viewer_index import DIRECTORY, viewer_files, write_index

LABEL = "SYNTHETIC EXAMPLE"


def render_card(path, page):
    image = Image.new("RGB", tuple(page["size"]), "#f8f4e6")
    ink = ImageDraw.Draw(image)
    ink.rectangle((18, 18, image.width-19, image.height-19), outline="#908b7e", width=2)
    ink.text((40, 38), LABEL, fill="#5e685d", font=ImageFont.load_default(size=17))
    ink.multiline_text((40, 92), page["text"], fill="#202820", font=ImageFont.load_default(size=23), spacing=10)
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="JPEG", quality=92)


def demo_document(note, spec):
    ids = note["image_ids"]
    doc = empty_document(ids)
    for page, example in zip(doc["pages"], spec["pages"], strict=True):
        page["text"] = LABEL + "\n\n" + example["text"]
    def field(value, entry=None, **extra):
        return dict(value=value, normalized=value, certainty="explicit", entry_id=entry,
                    evidence=[dict(image_id=ids[0], entry_id=entry, quote=value)], **extra)
    if "species" in spec:
        doc["taxa"].append(field(spec["species"], name_type="vernacular", rank="species", role="principal",
                                 source_uncertain=False, alternative_group=None))
    for passage in spec["passages"]:
        entry, place = passage["key"], passage["locality"]
        doc["entries"].append(dict(entry_id=entry, image_id=ids[0], label=place,
                                   evidence=[dict(image_id=ids[0], quote=place)]))
        doc["localities"].append(field(place, entry))
        doc["identifiers"].append(field(passage["number"], entry, number_type="collection", namespace=None))
    doc["summary"] = spec["summary"]
    return doc


def make_demo():
    demo = ROOT / "local" / "demo"
    marker = demo / "synthetic-fixture.txt"
    if demo.exists() and any(demo.iterdir()) and not marker.is_file():
        raise ValueError("local/demo contains other work. Choose a clean workspace for the synthetic demo.")
    demo.mkdir(parents=True, exist_ok=True)
    marker.write_text("Local synthetic viewer fixture. No collection data.\n", encoding="utf-8")
    specs = json.loads((ROOT / "test/inputs/demo.json").read_text(encoding="utf-8"))["notes"]
    store, inputs = Store(demo / "store"), demo / "cards"
    groups, by_path = [], {}
    with lock(store.root / "store.lock"):
        for spec in specs:
            paths = [page["path"] for page in spec["pages"]]
            if len(paths) > 1:
                groups.append(dict(key=spec["key"], paths=paths, source="Explicit synthetic continuation"))
            by_path[paths[0]] = spec
            for page in spec["pages"]:
                render_card(inputs / page["path"], page)
        previous = store.latest("inventory")
        sets = sorted({str(Path(p).parent.as_posix()) for p in by_path if p.count("/") >= 2})
        inventory = discover(inputs, previous, dict(version=1, groups=groups), complete_sets=sets)
        if inventory != previous:
            store.append("inventory", inventory)
        images = {i["image_id"]: i["path"] for i in inventory["images"]}
        current = store.current_results()
        for note in inventory["notes"]:
            if not note["active"]:
                continue
            spec = by_path[images[note["image_ids"][0]]]
            if spec.get("pending"):
                continue
            doc = demo_document(note, spec)
            errors, reasons = validate_document(doc, note["image_ids"])
            if errors:
                raise ValueError(errors)
            request = prepare_request(inventory, note, Config())
            request["provenance"].update(provider="offline-fixture", model="synthetic example", prompt="No service request.")
            request["provenance"]["prompt_sha256"] = digest(b"No service request.")
            request["fingerprint"] = digest(encoded([request["provenance"], doc]))
            if current.get(note["note_id"], {}).get("fingerprint") == request["fingerprint"]:
                continue
            checkpoint_result(store, note, request, dict(execution="complete", text="", document=doc, errors=[],
                              review_reasons=reasons, returned_model=None), [], "synthetic-demo")
        export_all(store, inventory, demo / "exports")
        files, _ = viewer_files(store, inventory)
        write_index(demo / "exports" / DIRECTORY, files)
    print("Synthetic viewer export ready in local/demo/exports. Run node scripts/preview.cjs.")


if __name__ == "__main__":
    make_demo()
