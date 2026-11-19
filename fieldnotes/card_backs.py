"""Read a scanner's explicit front/back pairs from the private collection store."""
from datetime import datetime
from pathlib import Path
import re
from .paths import relative_path

LOG_NAME = "card-backs.txt"


def from_card_back_log(group):
    return isinstance(group, dict) and group.get("kind") in {"front_back", "awaiting_back"} and group.get("source") == LOG_NAME


def card_side(note, page_number):
    if (note.get("override") or {}).get("kind") in {"front_back", "awaiting_back"}:
        return ("Front", "Back")[page_number - 1]
    return None


def scanner_order(images, folder):
    times = {}
    for image in images:
        name = image["filename"]
        if image["folder"] != folder or Path(name).suffix.lower() not in {".jpg", ".jpeg"}:
            continue
        match = re.fullmatch(r"IMG_([0-9]{4}(?:_[0-9]{2}){5})S\.jpe?g", name, re.I)
        if not match:
            raise ValueError(f"Unknown scanner timestamp in {image['path']}; use explicit front/back filenames")
        stamp = datetime.strptime(match[1], "%Y_%m_%d_%H_%M_%S")
        if stamp in times:
            raise ValueError(f"Tied scanner timestamps in {folder}: {name} and {times[stamp]}")
        times[stamp] = image["path"]
    return [times[stamp] for stamp in sorted(times)]


def read_card_backs(log, images, previous_groups=(), scan_folders=None):
    """A missing log leaves saved decisions intact. A present log replaces its own pairs."""
    try:
        lines = Path(log).read_text(encoding="utf-8-sig").splitlines()
    except FileNotFoundError:
        return None
    by_path = {image["path"]: image for image in images}
    previous_pairs = {p: g["paths"] for g in previous_groups if from_card_back_log(g) for p in g["paths"]}
    groups, claimed, orders = [], set(), {}

    def add(paths, location, mode):
        for path in paths:
            if path not in by_path:
                raise ValueError(f"{location}: no inventoried scan at {path}")
            if path in claimed:
                raise ValueError(f"{location}: scan already used in a pair: {path}")
            prior = previous_pairs.get(path)
            if mode and prior and prior != paths[:len(prior)]:
                raise ValueError(f"{location}: scanner order would change the saved pair at {path}; verify the sequence and use explicit pairs")
            claimed.add(path)
        kind = "front_back" if len(paths) == 2 else "awaiting_back"
        group = dict(key="card-back:" + by_path[paths[0]]["image_id"], kind=kind, paths=paths, source=LOG_NAME)
        if mode:
            group["mode"] = mode
        groups.append(group)

    for number, line in enumerate(lines, 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        location = f"{LOG_NAME} line {number}"
        parts = [part.strip() for part in line.split("|")]
        if len(parts) not in {2, 3}:
            raise ValueError(f"{location}: expected folder | front filename, folder | front | back, or folder | all-pairs")
        folder, *names = parts
        try:
            directory = None if folder == "." else relative_path(folder)
            if scan_folders is not None and directory and len(directory.parts) >= 2 and folder not in scan_folders:
                continue
            files = [relative_path(name) for name in names]
        except ValueError as exc:
            raise ValueError(f"{location}: {exc}") from exc
        if len(names) == 1 and folder not in orders:
            orders[folder] = scanner_order(images, folder)
        if names == ["all-pairs"]:
            sequence = orders[folder]
            for offset in range(0, len(sequence), 2):
                add(sequence[offset:offset + 2], location, "all-pairs")
            continue
        if any(len(p.parts) != 1 or p.suffix.lower() not in {".jpg", ".jpeg"} for p in files):
            raise ValueError(f"{location}: use JPEG filenames from the named folder")
        paths = [(directory / p if directory else p).as_posix() for p in files]
        if len(paths) == 1:
            sequence = orders[folder]
            if paths[0] not in sequence:
                raise ValueError(f"{location}: no timestamped scan at {paths[0]}")
            offset = sequence.index(paths[0])
            add(sequence[offset:offset + 2], location, "next")
        else:
            add(paths, location, None)
    return groups
