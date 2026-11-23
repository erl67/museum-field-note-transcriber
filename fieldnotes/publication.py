"""Opt-in managed outputs; explicit destination each time, never automatic publication."""
from collections import defaultdict
from pathlib import Path
from .catalogue import note_number_key
from .exports import reading
from .paths import inside, relative_path
from .review import current_records
from .storage import atomic_bytes, digest


def state_for(store, destination):
    root = str(Path(destination).resolve())
    return next((e["data"] for e in reversed(store.events()) if e["kind"] == "publication" and e["data"]["destination"] == root), {})


def generated_paths(store, input_root):
    # Only exact owned output paths beneath this input root are excluded.
    root, paths = Path(input_root).resolve(), set()
    latest = {e["data"]["destination"]: e["data"] for e in store.events() if e["kind"] == "publication"}
    for destination, state in latest.items():
        target = Path(destination)
        if not (target.is_relative_to(root) or root.is_relative_to(target)):
            continue
        for relative in state.get("files", {}):
            path = inside(state["destination"], relative)
            if path.is_relative_to(root):
                paths.add(path.relative_to(root).as_posix())
    return paths


def set_readers(store, inventory):
    images = {image["image_id"]: image for image in inventory["images"]}
    records = sorted((r for r in current_records(store, inventory) if r["active"]), key=note_number_key)
    by_folder = defaultdict(list)
    for record in records:
        folders = {relative_path(images[iid]["path"]).parent for iid in record["image_ids"]}
        text = reading(record, images)
        for folder in folders:
            by_folder[folder].append(text)

    files, used = {}, set()
    for folder, texts in sorted(by_folder.items()):
        if len(folder.parts) >= 2:
            target = folder.parent / (folder.name + ".txt")
        else:
            target = folder / "Unfiled_transcriptions.txt"
        name = target.as_posix()
        if name.casefold() in used:
            raise ValueError(f"Scan folders would share the same publication filename: {name}")
        used.add(name.casefold())
        heading = folder.as_posix() if folder.parts else "Scans at the collection root"
        files[name] = (heading + "\n\n" + "\n\n".join(texts)).encode("utf-8")
    for name in files:
        if any(parent.as_posix().casefold() in used for parent in relative_path(name).parents):
            raise ValueError(f"A set reader would occupy a folder needed by another reader: {name}")
    return files


def publish(store, inventory, output, destination):
    """Caller holds store lock. Journal ownership before writes; archive before replacement."""
    root, output = Path(destination).resolve(), Path(output)
    if not root.is_dir():
        raise ValueError("Publication destination must be an existing accessible directory")
    files = set_readers(store, inventory)
    files["Field_notes_viewer.json"] = (output / "Field_notes_viewer.json").read_bytes()
    return publish_files(store, inventory, files, root)


def publish_files(store, inventory, files, root):
    """Preflight the entire managed destination and write in producer order."""
    previous = state_for(store, root)
    owned = previous.get("files", {})
    source_paths = {str((Path(inventory["input_root"]) / i["path"]).resolve()).casefold() for i in inventory["images"]}
    pending, archived, changed = {}, {}, set()
    for relative in files.keys() | owned.keys():
        path = inside(root, relative)
        if str(path).casefold() in source_paths or path.suffix.lower() not in {".txt", ".json"}:
            raise ValueError("Refusing publication over an inventoried source")
        if path.exists():
            raw = path.read_bytes()
            if digest(raw) not in owned.get(relative, []):
                raise ValueError(f"Unowned or externally edited output: {relative}")
            if relative not in files or files[relative] != raw:
                archived[relative] = store.blob(raw, path.suffix)
                changed.add(relative)
        elif relative in files:
            changed.add(relative)
        pending[relative] = sorted(set(owned.get(relative, []) + ([digest(files[relative])] if relative in files else [])))
    if not changed and previous.get("status") == "complete" and owned.keys() == files.keys():
        return len(files)
    store.append("publication", dict(destination=str(root), files=pending, archived=archived, status="pending"))
    for relative, content in files.items():
        if relative not in changed:
            continue
        path = inside(root, relative)
        if path.exists():
            raw = path.read_bytes()
            if digest(raw) not in owned.get(relative, []):
                raise ValueError(f"Output changed during publication: {relative}")
            if raw == content:
                continue
        atomic_bytes(path, content)
    for relative in owned.keys() - files.keys():
        path = inside(root, relative)
        if path.exists():
            if digest(path.read_bytes()) not in owned[relative]:
                raise ValueError(f"Retired output externally edited: {relative}")
            path.unlink()
    store.append("publication", dict(destination=str(root), files={p: [digest(b)] for p, b in files.items()}, status="complete"))
    return len(files)
