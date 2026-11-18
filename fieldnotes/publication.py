"""Opt-in managed outputs; explicit destination each time, never automatic publication."""
from pathlib import Path
from .exports import collector_filename, reading
from .paths import inside
from .review import current_records
from .storage import atomic_bytes, digest


def state_for(store, destination):
    root = str(Path(destination).resolve())
    return next((e["data"] for e in reversed(store.events()) if e["kind"] == "publication" and e["data"]["destination"] == root), {})


def generated_paths(store, input_root):
    # Only exact owned output paths beneath this input root are excluded.
    root, paths = Path(input_root).resolve(), set()
    for event in store.events():
        if event["kind"] != "publication":
            continue
        state = state_for(store, event["data"]["destination"])
        for relative in state.get("files", {}):
            path = inside(state["destination"], relative)
            if path.is_relative_to(root):
                paths.add(path.relative_to(root).as_posix())
    return paths


def publish(store, inventory, output, destination):
    """Caller holds store lock. Journal ownership before writes; archive before replacement."""
    root, output = Path(destination).resolve(), Path(output)
    if not root.is_dir():
        raise ValueError("Publication destination must be an existing accessible directory")
    records = [r for r in current_records(store, inventory) if r["active"]]
    images = {i["image_id"]: i for i in inventory["images"]}
    files = {"Field_notes/" + r["note_id"] + ".txt": reading(r, images).encode("utf-8") for r in records}
    for collector in {r["catalogue"]["collector_folder"] for r in records}:
        name = collector_filename(collector)
        files["Field_notes/" + name] = (output / "collectors" / name).read_bytes()
    files["Field_notes_transcriptions.txt"] = (output / "combined.txt").read_bytes()
    files["Field_notes_viewer.json"] = (output / "Field_notes_viewer.json").read_bytes()
    if len({p.casefold() for p in files}) != len(files):
        raise ValueError("Publication output-name collision")
    owned = state_for(store, root).get("files", {})
    source_paths = {str((Path(inventory["input_root"]) / i["path"]).resolve()).casefold() for i in inventory["images"]}
    pending, archived = {}, {}
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
        pending[relative] = sorted(set(owned.get(relative, []) + ([digest(files[relative])] if relative in files else [])))
    store.append("publication", dict(destination=str(root), files=pending, archived=archived, status="pending"))
    for relative, content in files.items():
        path = inside(root, relative)
        if path.exists() and digest(path.read_bytes()) not in owned.get(relative, []):
            raise ValueError(f"Output changed during publication: {relative}")
        atomic_bytes(path, content)
    for relative in owned.keys() - files.keys():
        path = inside(root, relative)
        if path.exists():
            if digest(path.read_bytes()) not in owned[relative]:
                raise ValueError(f"Retired output externally edited: {relative}")
            path.unlink()
    store.append("publication", dict(destination=str(root), files={p: [digest(b)] for p, b in files.items()}, status="complete"))
    return len(files)
