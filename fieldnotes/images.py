"""Image preparation adapted from museum-transcription, build 2026-10-19.1."""
from io import BytesIO
from copy import deepcopy
from pathlib import Path
from PIL import Image, ImageOps
from . import SCHEMA_VERSION, __version__
from .prompt import PROMPT_VERSION, build_prompt
from .storage import digest, encoded
from .paths import inside


def prepare_image(raw, max_edge=0, apply_orientation=False):
    with Image.open(BytesIO(raw)) as source:
        if source.format != "JPEG":
            raise ValueError("Only JPEG content is supported")
        source.load()
        orientation = source.getexif().get(274, 1)
        resize = bool(max_edge and max(source.size) > max_edge)
        operations = []
        if apply_orientation and orientation not in (None, 1):
            operations.append(f"EXIF orientation {orientation} applied")
        if resize:
            operations.append(f"longest edge <= {max_edge}; Lanczos")
        if operations and source.mode not in {"RGB", "L"}:
            operations.append(f"{source.mode} to RGB")
        if not operations:
            return raw, ["original JPEG bytes"]
        image = (ImageOps.exif_transpose(source) if apply_orientation else source.copy()).convert("RGB")
        if resize:
            image.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)
        output = BytesIO()
        options = {}
        if not apply_orientation and orientation in range(2, 9):
            exif = Image.Exif()
            exif[274] = orientation
            options["exif"] = exif
            operations.append(f"EXIF orientation {orientation} retained")
        image.save(output, "JPEG", quality=95, subsampling=0, **options)
        return output.getvalue(), operations + ["JPEG quality 95; subsampling 0"]


def prepare_request(inventory, note, config, profile=None, *, authorities=None):
    if not note["active"] or note["grouping"] not in {"provisional", "reviewed"}:
        raise ValueError("Grouping needs a reviewed override before transcription")
    images = {i["image_id"]: i for i in inventory["images"]}
    if len(note["image_ids"]) > config.max_pages:
        raise ValueError("Note exceeds max_pages; no pages were omitted")
    authorities = deepcopy(authorities or [])
    prompt = build_prompt(note, profile, authorities)
    manifest, data = [], []
    size = len(encoded(config.generation())) + len(prompt.encode("utf-8")) * 6 + 8192
    for iid in note["image_ids"]:
        item = images[iid]
        if item["status"] != "ready":
            raise ValueError(f"Image unavailable ({item['status']}): {item['path']}")
        path = inside(inventory["input_root"], item["path"])
        raw = path.read_bytes()
        if digest(raw) != item["sha256"]:
            raise ValueError(f"Scan changed since inventory: {item['path']}; rerun inventory")
        submitted, operations = prepare_image(raw, config.max_edge, config.apply_orientation)
        with Image.open(BytesIO(submitted)) as prepared:
            submitted_dimensions = list(prepared.size)
        label = f"PAGE image_id={iid}; original relative path={item['path']}"
        manifest.append(dict(image_id=iid, path=item["path"], label=label,
                             original_sha256=item["sha256"], original_bytes=len(raw), dimensions=item.get("dimensions"),
                             submitted_sha256=digest(submitted),
                             submitted_bytes=len(submitted), submitted_dimensions=submitted_dimensions,
                             transformations=operations))
        data.append(submitted)
        size += 4 * ((len(submitted) + 2) // 3) + len(label.encode("utf-8")) * 6 + 1024
    if size > config.max_request_bytes:
        raise ValueError(f"Whole note needs approximately {size:,} request bytes; local limit "
                         f"{config.max_request_bytes:,}. No pages omitted. Consider explicit max_edge.")
    provenance = dict(schema_version=SCHEMA_VERSION, application_version=__version__,
                      schema_sha256=digest(Path(__file__).with_name("schema.py").read_bytes()),
                      application_sha256=digest(encoded({p.name: digest(p.read_bytes()) for p in sorted(Path(__file__).parent.glob("*.py"))})),
                      provider="gemini", model=config.model, generation=config.generation(),
                      prompt_version=PROMPT_VERSION, prompt=prompt, prompt_sha256=digest(prompt.encode()),
                      hints=deepcopy(note["hints"]), handwriting_profile=deepcopy(profile),
                      known_authorities=authorities, images=manifest,
                      max_edge=config.max_edge, apply_orientation=config.apply_orientation)
    return dict(fingerprint=digest(encoded(provenance)), provenance=provenance,
                image_data=data, estimated_bytes=size)
