"""Append-only, revision/evidence-bound corrections and independent approval states."""
from copy import deepcopy
import re
from .catalogue import authorities, project
from .schema import ARRAYS, FIELDS, validate_document
from .storage import digest, encoded, identity

REPLACEMENTS = (*ARRAYS, "entries", "summary", "notes", "translations")


def source_basis(note, images):
    return digest(encoded([(iid, images[iid].get("sha256")) for iid in note["image_ids"]]))


def review_basis(record):
    return digest(encoded(dict(revision=(record.get("result") or {}).get("revision_id"),
                               source=record["source_basis"], document=record["document"],
                               metadata_review=record["metadata_review"], transcription_review=record["transcription_review"])))


def update_document(document, patch):
    document["metadata"].update(deepcopy(patch.get("metadata", {})))
    for page in document["pages"]:
        page.update(deepcopy(patch.get("pages", {}).get(page["image_id"], {})))
    for field in REPLACEMENTS:
        if field in patch:
            document[field] = deepcopy(patch[field])


def current_records(store, inventory):
    results, events, registry = store.current_results(), store.events(), authorities(store)
    images = {i["image_id"]: i for i in inventory["images"]}
    completed_attempts = {aid for event in events if event["kind"] == "result" for aid in event["data"]["attempt_ids"]}
    preflight = {}
    attempt_notes, processed = {}, {}
    for event in events:
        payload = event["data"]
        if event["kind"] == "attempt_start":
            attempt_notes[payload["attempt_id"]] = payload["note_id"]
        elif event["kind"] == "attempt_end" and payload.get("ended_at") and payload["attempt_id"] in attempt_notes:
            processed[attempt_notes[payload["attempt_id"]]] = payload["ended_at"]
        if event["kind"] == "preflight_failure":
            preflight[payload["note_id"]] = payload["error"]
        elif event["kind"] in {"result", "selection", "preflight_ready"}:
            preflight.pop(payload["note_id"], None)
    records = []
    for note in inventory["notes"]:
        result = results.get(note["note_id"])
        record = deepcopy(note)
        record.update(execution="blocked" if note["grouping"] == "needs_review" else "unprocessed",
                      metadata_review="unreviewed", transcription_review="unreviewed",
                      document=None, result=result, processed_at=processed.get(note["note_id"]),
                      review_history=[], stale_reviews=[], stale_source=False,
                      source_basis=source_basis(note, images))
        if result:
            old_basis = digest(encoded([(i["image_id"], i["original_sha256"]) for i in result["provenance"]["images"]]))
            stale = old_basis != record["source_basis"]
            record["stale_source"] = stale
            record["execution"] = "stale" if stale else result["execution"]
            if result["execution"] == "complete":
                record["document"] = deepcopy(result["document"])
            record["review_reasons"] += result.get("errors", [])
            if not record["document"]:
                record["review_reasons"] += result.get("review_reasons", [])
            if stale:
                record["review_reasons"].append("Source content/order changed; earlier reading retained with its original evidence")
        # A process killed without a checkpoint stays visible, not silently pending.
        if note["note_id"] in preflight:
            if not result:
                record["execution"] = "blocked"
            record["review_reasons"].append("Last request preparation failed: " + preflight[note["note_id"]])
        unresolved = [e["data"]["attempt_id"] for e in events if e["kind"] == "attempt_start"
                      and e["data"]["note_id"] == note["note_id"] and e["data"]["attempt_id"] not in completed_attempts]
        if unresolved:
            record["execution"] = "interrupted"
            record["review_reasons"].append("Uncheckpointed attempt; inspect saved response before retrying")
        for event in events:
            if event["kind"] != "review" or event["data"].get("note_id") != note["note_id"]:
                continue
            patch = event["data"]
            record["review_history"].append(event)
            if (not result or not record["document"] or record["stale_source"]
                    or patch["base_revision"] != result["revision_id"]
                    or patch["source_basis"] != record["source_basis"]
                    or patch["base_review"] != review_basis(record)):
                record["stale_reviews"].append(event["event_id"]); continue
            if patch.get("pages"):
                record["metadata_review"] = record["transcription_review"] = "in_progress"
            elif patch.get("metadata") or any(k in patch for k in REPLACEMENTS):
                record["metadata_review"] = "in_progress"
            update_document(record["document"], patch)
            for field in ("metadata_review", "transcription_review"):
                if field in patch:
                    record[field] = patch[field]
        if record["stale_reviews"]:
            record["review_reasons"].append("Earlier reviews need rebasing; history is retained")
        if record["document"]:
            _, reasons = validate_document(record["document"], [p["image_id"] for p in record["document"]["pages"]])
            record["review_reasons"] += reasons
        record["review_reasons"] = sorted(set(record["review_reasons"]))
        record["review_basis"] = review_basis(record)
        record["catalogue"] = project(record, registry)
        record["review_reasons"] += record["catalogue"]["conflicts"]
        records.append(record)
    return records


def apply_authority(store, item):
    item = deepcopy(item)
    kind = item.get("kind")
    if (kind not in {"collector", "taxon"} or not item.get("source")
            or not isinstance(item.get("name"), str) or not item["name"].strip()
            or not isinstance(item.get("aliases"), list) or any(not isinstance(a, str) or not a.strip() for a in item["aliases"])
            or item.get("review_status") not in {"approved", "withdrawn"}):
        raise ValueError("Authority needs collector/taxon kind, name, aliases, approved/withdrawn status and source")
    if kind == "taxon" and item.get("rank") not in {"species", "subspecies", "genus", "unknown"}:
        raise ValueError("Taxon authority needs rank")
    registry = authorities(store)
    prefix = "col_" if kind == "collector" else "tax_"
    if item.get("authority_id"):
        if item["authority_id"] not in registry or registry[item["authority_id"]]["kind"] != kind:
            raise ValueError("Use an existing matching authority_id for updates, or omit it for creation")
    else:
        item["authority_id"] = identity(prefix)
    return store.append("authority", item)


def apply_review(store, inventory, patch):
    patch = deepcopy(patch)
    allowed = {"note_id", "base_revision", "base_review", "source", "reviewer", "metadata", "pages",
               "metadata_review", "transcription_review", *REPLACEMENTS}
    if not isinstance(patch, dict) or set(patch) - allowed or not patch.get("source"):
        raise ValueError("Review needs source/reason and only supported correction fields")
    record = next((r for r in current_records(store, inventory) if r["note_id"] == patch.get("note_id")), None)
    if (not record or not record["document"] or record["execution"] != "complete"
            or patch.get("base_revision") != record["result"]["revision_id"]
            or patch.get("base_review") != record["review_basis"]):
        raise ValueError("Review must cite the current complete base_revision and base_review from show")
    if not isinstance(patch.get("metadata", {}), dict) or set(patch.get("metadata", {})) - set(FIELDS):
        raise ValueError("Unknown metadata field")
    pages = {p["image_id"] for p in record["document"]["pages"]}
    if not isinstance(patch.get("pages", {}), dict):
        raise ValueError("pages correction must be an image-ID keyed object")
    for iid, changes in patch.get("pages", {}).items():
        if iid not in pages or not isinstance(changes, dict) or set(changes) - {"text", "status", "annotations"}:
            raise ValueError("Page corrections target current image IDs and reading fields only")
    for field in ("metadata_review", "transcription_review"):
        if field in patch and patch[field] not in {"unreviewed", "in_progress", "approved"}:
            raise ValueError("Review state must be unreviewed, in_progress or approved")
    document = deepcopy(record["document"])
    update_document(document, patch)
    errors, _ = validate_document(document, record["image_ids"])
    if errors:
        raise ValueError("; ".join(errors))
    registry = authorities(store)
    for field, kind in [(document["metadata"]["collector"], "collector"), *[(t, "taxon") for t in document["taxa"]]]:
        aid = field.get("authority_id")
        if aid and (aid not in registry or registry[aid]["kind"] != kind or registry[aid]["review_status"] != "approved"
                    or (kind == "taxon" and registry[aid]["rank"] != field["rank"])):
            raise ValueError("Unknown, withdrawn or rank-mismatched reviewed authority_id")
    patch["source_basis"] = record["source_basis"]
    return store.append("review", patch)
