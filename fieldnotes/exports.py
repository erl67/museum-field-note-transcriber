"""Offline reading reports, related CSV tables and versioned Drive viewer data."""
from collections import defaultdict
from copy import deepcopy
import csv
from io import StringIO
import json
from pathlib import Path
import re
from .catalogue import authorities, note_number_key
from .card_backs import card_side
from .paths import inside, separate_from_sources
from .review import current_records
from .schema import ARRAYS, usable_date
from .storage import atomic_bytes, atomic_json, digest, encoded, now


def cell(value):
    if value is None:
        return ""
    text = str(value)
    return "'" + text if text.lstrip().startswith(("=", "+", "-", "@")) or text.startswith(("\t", "\r", "\n")) else text


def write_csv(path, fields, rows):
    output = StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fields, extrasaction="raise")
    writer.writeheader()
    writer.writerows({k: cell(v) for k, v in row.items()} for row in rows)
    atomic_bytes(path, b"\xef\xbb\xbf" + output.getvalue().encode("utf-8"))


def collector_filename(collector):
    return "collector_" + digest(collector.encode())[:24] + ".txt"


def reading(record, images):
    cat, doc = record["catalogue"], record["document"]
    lines = [cat["title"], "=" * 72, "Collector: " + cat["collector"] + " (" + cat["collector_basis"] + ")"]
    if cat["scan_sets"]:
        lines.append("Scan set: " + ", ".join(cat["scan_sets"]))
    lines.append("")
    if doc:
        if record["stale_source"]:
            lines += ["EARLIER READING — source contents or page order changed.", ""]
        lines += ["SOURCE-LANGUAGE TRANSCRIPTION", ""]
        manifest = {i["image_id"]: i for i in record["result"]["provenance"]["images"]}
        for number, page in enumerate(doc["pages"], 1):
            source = manifest.get(page["image_id"], {})
            lines += [f"--- PAGE {number} | {page['image_id']} | {source.get('path', images.get(page['image_id'], {}).get('path', 'unknown'))} ---",
                      page["text"], ""]
            for annotation in page["annotations"]:
                lines += [f"ANNOTATION ({annotation['kind']}): {annotation['text']}", ""]
        lines += ["CATALOGUE DETAILS — separate from source text"]
        for key in ARRAYS:
            for item in doc[key]:
                location = "; ".join(e["image_id"] + (" / " + e["entry_id"] if e.get("entry_id") else "") for e in item["evidence"])
                lines.append(f"{key.title()} [{item.get('entry_id') or 'whole note'}]: {item.get('value') or 'Unknown'} ({item['certainty']}; {location})")
                normalized = usable_date(item) if key == "dates" else item.get("normalized")
                if normalized and normalized != item.get("value"):
                    lines.append("  Search form: " + normalized)
        if doc["summary"]:
            lines += ["", "INTERPRETIVE SUMMARY", doc["summary"]]
        if doc["notes"]:
            lines += ["", "SEPARATE NOTES", *doc["notes"]]
        for item in doc["translations"]:
            lines += ["", f"OPTIONAL TRANSLATION | {item['image_id']} | {item['language']}", item["text"]]
    else:
        lines += ["No complete transcription is available."]
        if record.get("result") and record["result"].get("text"):
            lines += ["Available partial response is retained in the detailed report and history."]
    lines += ["", "STAFF RECORD", "Stable note ID: " + record["note_id"],
              f"Discovery: {record['discovery']} | Grouping: {record['grouping']} | Execution: {record['execution']}",
              f"Metadata review: {record['metadata_review']} | Transcription review: {record['transcription_review']}"]
    for position, iid in enumerate(record["image_ids"], 1):
        side = card_side(record, position)
        label = f"Current source ({side})" if side else "Current source"
        lines.append(label + ": " + images[iid]["path"])
    if record["review_reasons"]:
        lines += ["Review notes:", *["- " + r for r in record["review_reasons"]]]
    return "\n".join(lines) + "\n"


def viewer_note(record, images, mapping, number_order):
    doc = record["document"] or {}
    scans = []
    result = record.get("result")
    manifest = result["provenance"]["images"] if result and doc else []
    source = manifest if record["stale_source"] and manifest else [images[i] for i in record["image_ids"]]
    for order, item in enumerate(source, 1):
        iid = item["image_id"]
        current = images.get(iid, {})
        row = deepcopy(current)
        row.update(order=order, image_id=iid)
        side = item.get("side") if record["stale_source"] else card_side(record, order)
        if side:
            row["side"] = side
        if record["stale_source"]:
            row.update(path=item["path"], filename=Path(item["path"]).name,
                       sha256=item["original_sha256"], size=item["original_bytes"], status="stale_source")
        row.update(drive_file_id=mapping.get(iid, {}).get("file_id"),
                   mapping_status="mapped" if iid in mapping else "missing_mapping")
        scans.append(row)
    return dict(note_id=record["note_id"], active=record["active"], execution=record["execution"], processed_at=record["processed_at"],
                discovery=record["discovery"], grouping=record["grouping"],
                metadata_review=record["metadata_review"], transcription_review=record["transcription_review"],
                catalogue=deepcopy(record["catalogue"]), number_order=number_order,
                hints=deepcopy(record["hints"]), scans=scans, pages=doc.get("pages", []),
                metadata=doc.get("metadata", {}), entries=doc.get("entries", []),
                **{key: [dict(d, normalized=usable_date(d)) for d in doc.get(key, [])] if key == "dates"
                   else doc.get(key, []) for key in ARRAYS}, summary=doc.get("summary", ""),
                notes=doc.get("notes", []), translations=doc.get("translations", []),
                review_reasons=record["review_reasons"],
                provenance=result["provenance"] if result else None,
                partial_response=result.get("text", "") if result and not doc else "")


def export_all(store, inventory, output, mapping=None):
    separate_from_sources(inventory, output)
    output = Path(output)
    for folder in ("readable", "details", "collectors"):
        inside(output, folder)
    mapping = mapping or {"version": 1, "images": {}}
    if mapping.get("version") != 1 or not isinstance(mapping.get("images"), dict):
        raise ValueError("Drive mapping needs version 1 and images object")
    images = {i["image_id"]: i for i in inventory["images"]}
    for iid, item in mapping["images"].items():
        if (iid not in images or not isinstance(item, dict)
                or not re.fullmatch(r"[A-Za-z0-9_-]{10,}", item.get("file_id", ""))
                or item.get("original_sha256") != images[iid]["sha256"]):
            raise ValueError("Mapping needs a known image ID, actual Drive ID and matching original_sha256")
    records = current_records(store, inventory)
    ordered = sorted(records, key=note_number_key)
    order = {r["note_id"]: n for n, r in enumerate(ordered)}
    catalogue, image_rows, entry_rows, evidence_rows = [], [], [], []
    repeated = {k: [] for k in ARRAYS}
    collector_text, combined, bundle = defaultdict(list), [], []
    for record in ordered:
        nid, cat, doc = record["note_id"], record["catalogue"], record["document"]
        text = reading(record, images)
        atomic_bytes(output / "readable" / (nid + ".txt"), text.encode("utf-8"))
        technical = text + "\nTECHNICAL PROVENANCE AND HISTORY\n" + json.dumps(record, ensure_ascii=False, indent=2) + "\n"
        atomic_bytes(output / "details" / (nid + ".txt"), technical.encode("utf-8"))
        if record["active"]:
            combined.append(text); collector_text[cat["collector_folder"]].append(text)
        catalogue.append(dict(note_id=nid, active=record["active"], collector_folder=cat["collector_folder"],
                              scan_sets="; ".join(cat["scan_sets"]),
                              collector_display=cat["collector"], species_display=cat["species"],
                              numbers_display=cat["number_label"], discovery=record["discovery"], grouping=record["grouping"],
                              execution=record["execution"], metadata_review=record["metadata_review"],
                              transcription_review=record["transcription_review"], page_count=len(record["image_ids"]),
                              summary=doc["summary"] if doc else "", report_path="readable/" + nid + ".txt"))
        for position, iid in enumerate(record["image_ids"], 1):
            item = images[iid]
            image_rows.append(dict(note_id=nid, image_id=iid, order=position, side=card_side(record, position),
                                   **{k: item.get(k) for k in ("path", "filename", "folder", "status", "sha256", "size")},
                                   width=(item.get("dimensions") or [None, None])[0], height=(item.get("dimensions") or [None, None])[1]))
        if doc:
            for entry in doc["entries"]:
                entry_rows.append(dict(note_id=nid, entry_id=entry["entry_id"], image_id=entry["image_id"], label=entry["label"]))
            fields = [("metadata." + k, 0, v) for k, v in doc["metadata"].items()]
            fields += [(k, i, v) for k in ARRAYS for i, v in enumerate(doc[k])]
            fields += [("entries", i, v) for i, v in enumerate(doc["entries"])]
            for key, index, item in fields:
                if key in repeated:
                    repeated[key].append(dict(note_id=nid, item_index=index, entry_id=item.get("entry_id"),
                        value=item.get("value"), normalized=usable_date(item) if key == "dates" else item.get("normalized"),
                        certainty=item.get("certainty"), details_json=json.dumps({k: v for k, v in item.items() if k not in {"value", "normalized", "certainty", "evidence", "entry_id"}}, ensure_ascii=False)))
                for ev in item.get("evidence", []):
                    evidence_rows.append(dict(note_id=nid, field=key, item_index=index, image_id=ev["image_id"],
                                              entry_id=ev.get("entry_id") or item.get("entry_id"), quote=ev.get("quote"), location=ev.get("location")))
        bundle.append(viewer_note(record, images, mapping["images"], order[nid]))
    fields = ["note_id", "active", "collector_folder", "collector_display", "species_display", "numbers_display", "discovery", "grouping", "execution", "metadata_review", "transcription_review", "page_count", "summary", "report_path", "scan_sets"]
    write_csv(output / "catalogue.csv", fields, catalogue)
    write_csv(output / "images.csv", ["note_id", "image_id", "order", "path", "filename", "folder", "status", "sha256", "size", "width", "height", "side"], image_rows)
    write_csv(output / "entries.csv", ["note_id", "entry_id", "image_id", "label"], entry_rows)
    write_csv(output / "evidence.csv", ["note_id", "field", "item_index", "image_id", "entry_id", "quote", "location"], evidence_rows)
    for key, rows in repeated.items():
        write_csv(output / (key + ".csv"), ["note_id", "item_index", "entry_id", "value", "normalized", "certainty", "details_json"], rows)
    for collector, texts in collector_text.items():
        atomic_bytes(output / "collectors" / collector_filename(collector), (collector + "\n\n" + "\n\n".join(texts)).encode("utf-8"))
    atomic_bytes(output / "combined.txt", "\n\n".join(combined).encode("utf-8"))
    atomic_json(output / "records.json", dict(schema_version=1, inventory=inventory, records=records, authorities=authorities(store)))
    value = dict(schema_version=1, export_kind="fieldnotes-viewer", exported_at=now(), notes=bundle)
    # Hash the exact UTF-8 payload. Re-serializing it in JS changes numbers such as 1.0.
    payload = encoded(value) + b"\n"
    header = b'{"content_sha256":"' + digest(payload).encode("ascii") + b'",'
    atomic_bytes(output / "Field_notes_viewer.json", header + payload[1:])
    return len(records)
