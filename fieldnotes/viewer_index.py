"""Portable, content-addressed reader files. The journal and JPEGs stay authoritative."""
from collections import Counter, defaultdict
import hashlib
import re

from .discovery import scan_order
from .exports import mapped_images, viewer_note
from .paths import inside, relative_path
from .review import current_records
from .schema import validate_document
from .storage import atomic_bytes, digest, encoded


DIRECTORY = "Field_notes_index"
PAGE_SIZE = 40
MAX_JSON_BYTES = 10 * 1024 * 1024
CATALOGUE_FIELDS = ("collector", "collector_folder", "collector_basis", "species", "title",
                    "number_label", "numbers", "scan_sets", "species_groups", "aliases")
SCAN_FIELDS = ("image_id", "path", "filename", "folder", "order", "side", "status",
               "dimensions", "size", "sha256", "drive_file_id")


def search_keys(numbers):
    """Hash exact labels. Numeric queries also check a small shard of compound labels."""
    keys = set()
    for label in numbers:
        # Fold ASCII capital letters, preserving punctuation, Unicode and significant zeros.
        term = re.sub("[A-Z]", lambda m: m[0].lower(), label.strip())
        keys.add("x" + digest(term.encode())[:2])
        if re.fullmatch("[0-9]+", term):
            continue
        if not re.search(r"[0-9]", term):
            continue
        # A range can cross powers of ten or use an abbreviated end. Its full written
        # value stays intact; the reader's existing range matcher decides membership.
        for part in re.split(r";|,(?![0-9]{3}\b)|(?<=[0-9]{4}),", term.strip("()")):
            match = re.fullmatch(r"\s*([0-9]+)(?:[ \t]*[-–—−][ \t]*([0-9]+))?\s*", part)
            if not match:
                continue
            first, end = match.groups()
            if not end:
                keys.add("x" + digest(first.encode())[:2])
                continue
            end = first[:max(0, len(first) - len(end))] + end
            for width in range(len(first), min(len(end), 200) + 1):
                low = int(first[0]) if width == len(first) else 1
                high = int(end[0]) if width == len(end) else 9
                keys.update(f"r{width}-{digit}" for digit in range(low, high + 1))
    return keys


def reader_note(record, images, mapping):
    value = viewer_note(record, images, mapping, 0)
    if record["document"]:
        errors, _ = validate_document(record["document"], [s["image_id"] for s in value["scans"]])
        if errors:
            raise ValueError(f"Invalid reading for {record['note_id']}: " + "; ".join(errors))
    for key in ("number_order", "processed_at", "provenance", "partial_response", "review_reasons"):
        del value[key]
    value["catalogue"] = {k: value["catalogue"][k] for k in CATALOGUE_FIELDS}
    value["hints"] = {k: value["hints"][k] for k in ("collector_folder", "filenames")}
    value["scans"] = [{k: scan[k] for k in SCAN_FIELDS if k in scan} for scan in value["scans"]]
    return value


def build_index(notes):
    """Accept active reader notes in collection/first-scan order. Return reachable files only."""
    files, routes, lookup = {}, defaultdict(dict), defaultdict(list)
    sets, collector_counts, collector_scans = defaultdict(list), Counter(), Counter()
    seen, image_ids, paths = set(), set(), set()
    warnings = []

    def object_ref(value):
        raw = encoded(value)
        if len(raw) > MAX_JSON_BYTES:
            raise ValueError("Reader JSON exceeds the per-file limit")
        ref = digest(raw)
        files[f"{ref}.json"] = raw
        return ref

    for note in notes:
        nid, cat, scans = note["note_id"], note["catalogue"], note["scans"]
        if not re.fullmatch("note_[a-f0-9]{32}", nid) or nid in seen:
            raise ValueError(f"Duplicate or invalid note ID: {nid}")
        seen.add(nid)
        if not scans:
            raise ValueError(f"No scan manifest for {nid}")
        for order, scan in enumerate(scans, 1):
            iid, path = scan["image_id"], relative_path(scan["path"]).as_posix().casefold()
            if (not re.fullmatch("img_[0-9a-f]{32}", iid) or iid in image_ids or path in paths
                    or scan["order"] != order):
                raise ValueError(f"Duplicate scan identity/path or invalid order: {nid} / {iid}")
            image_ids.add(iid)
            paths.add(path)
            if scan["status"] != "ready":
                warnings.append(f"{nid} / {iid}: scan {scan['status']}")
            elif not re.fullmatch("[0-9a-f]{64}", scan["sha256"]) or scan["size"] <= 0:
                raise ValueError(f"Invalid size or original hash: {nid} / {iid}")
        page_ids = [p["image_id"] for p in note["pages"]]
        if (page_ids or note["execution"] == "complete") and page_ids != [s["image_id"] for s in scans]:
            raise ValueError(f"Transcription page order differs from scans: {nid}")
        if note["execution"] != "complete":
            warnings.append(f"{nid}: {note['execution']} transcription")
        collector = cat["collector_folder"]
        collector_counts[collector] += 1
        collector_scans[collector] += len(scans)
        # Loose cards at the collector root have their own selectable set.
        memberships = list(dict.fromkeys(s["folder"] for s in scans))
        row = dict(note_id=nid, collector=collector, sets=memberships, numbers=cat["numbers"],
                   species=cat["species"], number_label=cat["number_label"], pages=len(scans),
                   execution=note["execution"])
        positions = []
        for name in memberships:
            rows = sets[collector, name]
            positions.append([name, len(rows)])
            rows.append(row)
        routes[nid[5:7]][nid] = dict(ref=object_ref(note), collector=collector, positions=positions)
        for key in search_keys(cat["numbers"]):
            lookup[key].append(row)

    collectors = defaultdict(list)
    for (collector, name), rows in sets.items():
        pages = [object_ref(rows[i:i + PAGE_SIZE]) for i in range(0, len(rows), PAGE_SIZE)]
        collectors[collector].append(dict(name=name, count=len(rows), scans=sum(r["pages"] for r in rows),
                                          pages=object_ref(pages)))
    manifest = dict(schema_version=2, export_kind="fieldnotes-index", page_size=PAGE_SIZE,
                    count=len(seen), scans=len(image_ids),
                    members_sha256=digest("\n".join(sorted(seen)).encode()),
                    collectors=[dict(name=c, count=collector_counts[c], scans=collector_scans[c], sets=s)
                                for c, s in collectors.items()],
                    routes=object_ref({k: object_ref(v) for k, v in routes.items()}),
                    lookup=object_ref({k: object_ref(v) for k, v in lookup.items()}))
    files["index.json"] = encoded(manifest)
    if len(files["index.json"]) > MAX_JSON_BYTES:
        raise ValueError("Collection manifest exceeds the per-file limit")
    return files, warnings


def viewer_files(store, inventory, mapping=None, selected=None, verify_scans=False):
    images, mapping = mapped_images(inventory, mapping)
    if len(images) != len(inventory["images"]):
        raise ValueError("Duplicate image ID in inventory")
    records = [r for r in current_records(store, inventory) if r["active"]]
    if selected is not None:
        if (not isinstance(selected, list) or not all(isinstance(n, str) for n in selected)
                or len(set(selected)) != len(selected) or set(selected) - {r["note_id"] for r in records}):
            raise ValueError("Viewer selection must be a JSON array of unique active note IDs")
        ids = set(selected)
        records = [r for r in records if r["note_id"] in ids]
    ordered = scan_order(records, inventory["images"])
    def notes():
        for record in ordered:
            note = reader_note(record, images, mapping)
            if verify_scans:
                for scan in note["scans"]:
                    if scan["status"] == "ready":
                        path = inside(inventory["input_root"], scan["path"])
                        if not path.is_file():
                            raise ValueError(f"Missing inventoried scan: {scan['path']}")
                        with path.open("rb") as stream:
                            checksum = hashlib.file_digest(stream, "sha256").hexdigest()
                        if checksum != scan["sha256"] or path.stat().st_size != scan["size"]:
                            raise ValueError(f"Original scan differs from inventory: {scan['path']}")
            yield note
    return build_index(notes())


def write_index(root, files):
    """Install immutable objects before replacing the manifest. Repeated exports reuse bytes."""
    for name, raw in files.items():
        path = inside(root, name)
        if path.exists() and path.read_bytes() == raw:
            continue
        if path.exists() and name != "index.json":
            raise ValueError(f"Existing reader object differs from its hash: {name}")
        atomic_bytes(path, raw)
