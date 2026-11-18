"""Strict local relative paths; no source mutation or link traversal."""
from pathlib import Path, PurePosixPath


def relative_path(value):
    if (not isinstance(value, str) or not value or len(value) > 4096
            or any(ord(c) < 32 for c in value) or "\\" in value or ":" in value
            or any(p in {"", ".", ".."} for p in value.split("/"))):
        raise ValueError("Expected an exact safe root-relative path with / separators")
    return PurePosixPath(value)


def inside(root, relative):
    root = Path(root).resolve()
    parts = relative_path(relative)
    path = root.joinpath(*parts.parts)
    for item in (path, *path.parents):
        if item == root:
            break
        if item.is_symlink() or item.is_junction():
            raise ValueError("Paths cannot follow symbolic links or junctions")
    if not path.resolve().is_relative_to(root):
        raise ValueError("Path escapes its root")
    return path


def separate_from_sources(inventory, *paths):
    root = Path(inventory["input_root"]).resolve()
    for value in paths:
        target = Path(value).resolve()
        if target.is_relative_to(root) or root.is_relative_to(target):
            raise ValueError("Store, quota and ordinary exports must be outside the source root")
