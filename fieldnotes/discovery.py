"""One scan per provisional note. Grouping and reconciliation are always explicit."""
from collections import defaultdict
from copy import deepcopy
from io import BytesIO
from pathlib import Path
import re
import uuid
from PIL import Image
from .card_backs import from_card_back_log, read_card_backs
from .paths import inside, relative_path
from .storage import digest


def stable(prefix, collection, key):
    return prefix + uuid.uuid5(uuid.UUID(collection), key).hex


def scan_order(notes, images):
    """Queue whole notes by their first page's folder and scan filename."""
    paths = {image["image_id"]: image["path"] for image in images}

    def key(note):
        path = paths[note["image_ids"][0]]
        # Scanner filenames encode year/month/day/time. Numeric chunks also keep
        # set2 before set10 and give other filenames a predictable natural order.
        natural = tuple(tuple((0, int(part)) if part.isascii() and part.isdigit() else (1, part.casefold())
                              for part in re.split(r"([0-9]+)", component) if part)
                        for component in relative_path(path).parts)
        return natural, path, note["note_id"]

    return sorted(notes, key=key)


def inspect_file(path, root, collection, previous):
    rel = path.relative_to(root).as_posix()
    old = previous.get(rel, {})
    row = dict(image_id=old.get("image_id", stable("img_", collection, rel)),
               path=rel, filename=path.name, folder=path.parent.relative_to(root).as_posix(),
               collector_folder=rel.split("/")[0] if "/" in rel else "Unknown collector",
               status="ready", sha256=None, size=None, dimensions=None, warnings=[])
    if old.get("previous_paths"):
        row["previous_paths"] = deepcopy(old["previous_paths"])
    if path.is_symlink() or path.is_junction():
        row["status"] = "linked_path"
        return row
    try:
        raw = path.read_bytes()
        row.update(sha256=digest(raw), size=len(raw))
        if path.suffix.lower() not in {".jpg", ".jpeg"}:
            row["status"] = "unsupported"
        else:
            with Image.open(BytesIO(raw)) as image:
                if image.format != "JPEG":
                    raise ValueError("JPEG filename has non-JPEG contents")
                image.load()
                row["dimensions"] = list(image.size)
        if old.get("sha256") and old["sha256"] != row["sha256"]:
            row["warnings"].append("Content replaced at this path; prior hashes remain in inventory history")
    except OSError as exc:
        row.update(status="unavailable" if row["sha256"] is None else "unreadable", error=str(exc))
        # Unavailable evidence is not evidence of changed bytes.
        if row["sha256"] is None:
            for key in ("sha256", "size", "dimensions"):
                row[key] = old.get(key)
    except (ValueError, Image.DecompressionBombError) as exc:
        row.update(status="unreadable", error=str(exc))
    return row


def regroup(inventory, overrides, card_backs=None):
    if (not isinstance(overrides, dict) or overrides.get("version") != 1
            or not isinstance(overrides.get("groups"), list)):
        raise ValueError("Grouping needs version 1 and a groups array")
    if card_backs is None and "overrides" in inventory:
        card_backs = [g for g in inventory["overrides"]["groups"] if from_card_back_log(g)]
    if card_backs is not None:
        manual = [g for g in overrides["groups"] if not from_card_back_log(g)]
        # Keep the alternating sequence aligned when a manual note spans whole cards.
        owners = {p: index for index, g in enumerate(manual) if isinstance(g, dict)
                  and isinstance(g.get("paths"), list) for p in g["paths"] if isinstance(p, str)}
        card_backs = [g for g in card_backs if not (g.get("mode") == "all-pairs"
                      and g["kind"] == "front_back" and g["paths"][0] in owners
                      and owners[g["paths"][0]] == owners.get(g["paths"][1]))]
        overrides = dict(overrides, groups=manual + card_backs)
    updated = deepcopy(inventory)
    images = {i["path"]: i for i in updated["images"]}
    old = {n["note_id"]: n for n in inventory.get("notes", [])}
    old_keys = {n["group_key"]: n["note_id"] for n in old.values()}
    claimed, used, keys, notes = set(), set(), set(), []

    def add(key, nid, paths, override=None):
        members = [images[p] for p in paths]
        reasons = sorted({reason for i in members for reason in i.get("warnings", [])})
        states = [i["status"] for i in members]
        reasons += [f"{i['status']}: {i['path']}" for i in members if i["status"] != "ready"]
        collectors = list(dict.fromkeys(i["collector_folder"] for i in members))
        if len(collectors) > 1:
            reasons.append("Explicit group spans collector folders; attribution needs review")
        waiting = (override or {}).get("kind") == "awaiting_back"
        if waiting:
            reasons.append("Awaiting the next chronological scan for this card's back")
        notes.append(dict(note_id=nid, group_key=key, active=True,
                          image_ids=[i["image_id"] for i in members],
                          grouping="needs_review" if waiting or "ambiguous_path" in states else "reviewed" if override else "provisional",
                          discovery="ready" if all(s == "ready" for s in states) else "unavailable",
                          hints=dict(collector_folder=collectors[0], collector_folders=collectors,
                                     filenames=[i["filename"] for i in members]),
                          review_reasons=reasons, override=deepcopy(override)))
        used.add(nid)

    for group in overrides["groups"]:
        if not isinstance(group, dict) or not isinstance(group.get("key"), str) or not group["key"].strip() or not group.get("source"):
            raise ValueError("Each group needs a unique key, source/reason and ordered paths")
        key, paths = "override:" + group["key"], group.get("paths")
        if not isinstance(paths, list) or not paths or any(not isinstance(p, str) for p in paths):
            raise ValueError("Grouping paths must be a nonempty ordered array")
        for p in paths:
            relative_path(p)
        for p in paths:
            if p not in images or p in claimed:
                raise ValueError(f"Unknown or already grouped scan: {p} ({group['source']})")
        identity_key = key
        if group.get("kind") == "awaiting_back":
            if len(paths) != 1:
                raise ValueError("A card awaiting its back must have one front")
            identity_key = "single:" + images[paths[0]]["image_id"]
        elif group.get("kind") == "front_back":
            if len(paths) != 2 or images[paths[0]]["folder"] != images[paths[1]]["folder"]:
                raise ValueError("A front and back must be two scans from the same folder")
            identity_key = "single:" + images[paths[0]]["image_id"]
        nid = (group.get("note_id") or old_keys.get(key) or old_keys.get(identity_key)
               or stable("note_", inventory["collection_id"], identity_key))
        if group.get("note_id") and nid not in old:
            raise ValueError("Retained note_id must already exist; omit it for a new note")
        if key in keys or nid in used or len(set(paths)) != len(paths):
            raise ValueError("Duplicate group, page or note ID")
        keys.add(key); claimed.update(paths)
        add(key, nid, paths, group)
    for path, image in images.items():
        if path in claimed:
            continue
        key = "single:" + image["image_id"]
        nid = old_keys.get(key) or stable("note_", inventory["collection_id"], key)
        if nid in used:
            nid = stable("note_", inventory["collection_id"], "remainder:" + key)
        add(key, nid, [path])
    notes += [dict(n, active=False, grouping="retired") for nid, n in old.items() if nid not in used]
    updated.update(notes=notes, overrides=deepcopy(overrides))
    return updated


def discover(root, previous=None, overrides=None, generated_paths=(), *, card_back_log=None, complete_sets=()):
    root = Path(root).resolve()
    if not root.is_dir():
        raise ValueError(f"Input root is unavailable: {root}; saved records remain usable offline")
    previous = previous or {}
    if previous and previous["input_root"] != str(root):
        raise ValueError("Store belongs to another input root; do not replace its history")
    collection = previous.get("collection_id", str(uuid.uuid5(uuid.NAMESPACE_URL, str(root))))
    old = {i["path"]: i for i in previous.get("images", [])}
    complete_sets = set(complete_sets)
    for name in complete_sets:
        if len(relative_path(name).parts) < 2 or not inside(root, name).is_dir():
            raise ValueError(f"Expected an existing collector/set folder for --complete-set: {name}")
    # Saved members stay addressable. Only an explicit completion admits new members.
    scan_folders = complete_sets | {i["folder"] for i in old.values() if "/" in i["folder"]}
    branches = {parent.as_posix() for name in scan_folders for parent in (Path(name), *Path(name).parents)}
    assigned_ids = {i["image_id"] for i in old.values()}
    images, issues = [], []
    generated = set(generated_paths)
    def walk_error(error):
        issues.append(dict(path=str(error.filename), status="unavailable_directory", error=str(error)))
    for folder, dirs, files in root.walk(on_error=walk_error, follow_symlinks=False):
        relative = folder.relative_to(root)
        if relative.parts:
            dirs[:] = [name for name in dirs if (relative / name).as_posix() in branches]
        for name in list(dirs):
            path = folder / name
            if path.is_symlink() or path.is_junction():
                dirs.remove(name); files.append(name)
        for name in sorted(files):
            path = folder / name
            rel = (relative / name).as_posix()
            if len(relative.parts) >= 2 and relative.as_posix() not in complete_sets and rel not in old:
                continue
            if rel not in generated:
                row = inspect_file(path, root, collection, old)
                if row["path"] not in old:
                    # An externally moved, reconciled image may still own the original path-derived ID.
                    generation = 1
                    while row["image_id"] in assigned_ids:
                        row["image_id"] = stable("img_", collection, f"new-at-path:{generation}:{row['path']}")
                        generation += 1
                    assigned_ids.add(row["image_id"])
                images.append(row)
    present = {i["path"] for i in images}
    images += [dict(i, status="missing") for p, i in old.items() if p not in present]
    images.sort(key=lambda i: i["path"])
    names, paths, hashes = defaultdict(list), defaultdict(list), defaultdict(list)
    for row in images:
        if row["status"] == "missing":
            continue
        names[row["filename"].casefold()].append(row)
        paths[row["path"].casefold()].append(row)
        if row["sha256"]:
            hashes[row["sha256"]].append(row)
    for table, warning in [(names, "Same filename in distinct folders; records remain separate"),
                            (hashes, "Identical contents; archival records are not merged")]:
        for group in table.values():
            if len(group) > 1:
                for row in group:
                    row["warnings"].append(warning)
    for group in paths.values():
        if len(group) > 1:
            for row in group:
                row["status"] = "ambiguous_path"
                row["warnings"].append("Case-insensitive duplicate path")
    inventory = dict(schema_version=1, collection_id=collection, input_root=str(root),
                     images=images, notes=deepcopy(previous.get("notes", [])), issues=issues)
    if "overrides" in previous:
        inventory["overrides"] = previous["overrides"]
    if overrides is None:
        overrides = previous.get("overrides", {"version": 1, "groups": []})
    saved = previous.get("overrides", {}).get("groups", [])
    pairs = read_card_backs(card_back_log, images, saved, scan_folders) if card_back_log is not None else None
    return regroup(inventory, overrides, pairs)


def reconcile_paths(inventory, mapping):
    if not isinstance(mapping, dict) or mapping.get("version") != 1 or not mapping.get("source"):
        raise ValueError("Reconciliation needs version 1, source and explicit paths")
    paths = mapping.get("paths")
    if not isinstance(paths, dict) or not paths or not all(isinstance(p, str) for pair in paths.items() for p in pair):
        raise ValueError("Expected old-path to new-path mapping")
    updated = deepcopy(inventory)
    images = {i["path"]: i for i in updated["images"]}
    if set(paths) - images.keys() or len({p.casefold() for p in paths.values()}) != len(paths):
        raise ValueError("Unknown old path or duplicate target")
    for old, new in paths.items():
        source, target = inside(inventory["input_root"], old), inside(inventory["input_root"], new)
        if source.exists() or new.casefold() in {p.casefold() for p in images}:
            raise ValueError("Old path must be absent and target not already inventoried")
        if target.suffix.lower() not in {".jpg", ".jpeg"} or not target.is_file():
            raise ValueError("Target must be an existing JPEG")
        row = images[old]
        if not row["sha256"] or digest(target.read_bytes()) != row["sha256"]:
            raise ValueError("Target bytes differ from original hash; refusing identity reconciliation")
        row.setdefault("previous_paths", []).append(old)
        row.update(path=new, filename=target.name, folder=Path(new).parent.as_posix(),
                   collector_folder=new.split("/")[0] if "/" in new else "Unknown collector", status="ready")
    for group in updated["overrides"]["groups"]:
        group["paths"] = [paths.get(p, p) for p in group["paths"]]
    updated = regroup(updated, updated["overrides"])
    updated["path_reconciliation"] = deepcopy(mapping)
    return updated
