"""Versioned response contract. Structural failures never erase available source text."""
from datetime import date
import json
import re
import unicodedata

FIELDS = ("collector", "language", "document_type", "physical_hand")
ARRAYS = ("identifiers", "taxa", "localities", "dates", "observations")
CERTAINTY = {"explicit", "inferred", "uncertain", "unknown"}
MONTH_WORDS = (
    "january jan enero ene janvier janv", "february feb febrero fevrier fevr",
    "march mar marzo mars", "april apr abril abr avril avr", "may mayo mai",
    "june jun junio juin", "july jul julio juillet juil", "august aug agosto ago aout",
    "september sept sep septiembre setiembre septembre", "october oct octubre octobre",
    "november nov noviembre novembre", "december dec diciembre dic decembre",
)


def supported_components(written, year, month, day=None):
    """Check the proposed precision against recognizable source components, without guessing order."""
    folded = "".join(c for c in unicodedata.normalize("NFKD", written.casefold()) if not unicodedata.combining(c))
    if set(re.findall(r"[^\W\d_]+", folded)) & set(MONTH_WORDS[month - 1].split()):
        days = [int(n) for n in re.findall(r"(?<!\d)(\d{1,2})(?!\d)", folded)]
        return day is None or day in days
    if year is None:
        return written.strip() == f"--{month:02d}"
    # Year-first numeric dates establish order. Other numeric dates need an unambiguous day.
    for y, m, d in re.findall(r"(?<!\d)(\d{4})[-/.](\d{1,2})(?:[-/.](\d{1,2}))?(?!\d)", written):
        if int(y) == year and int(m) == month and (day is None or d and int(d) == day):
            return True
    for a, b, y in re.findall(r"(?<!\d)(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})(?!\d)", written):
        a, b = int(a), int(b)
        if int(y) == year and (max(a, b) > 12 or a == b) and min(a, b) == month and (day is None or max(a, b) == day):
            return True
    return False


def unknown():
    return dict(value=None, normalized=None, certainty="unknown", evidence=[])


def empty_document(image_ids):
    return dict(schema_version=1,
                pages=[dict(image_id=i, status="text", text="", annotations=[]) for i in image_ids],
                metadata={key: unknown() for key in FIELDS}, entries=[],
                identifiers=[], taxa=[], localities=[], dates=[], observations=[],
                summary="", notes=[], translations=[])


def usable_date(field):
    """Return only supported precision-preserving values, never fabricate missing components."""
    value, written, precision = field.get("normalized"), field.get("value"), field.get("precision")
    if not isinstance(value, str) or not isinstance(written, str) or field.get("certainty") not in {"explicit", "inferred"}:
        return None
    if precision == "month_only":
        return value if re.fullmatch(r"--(0[1-9]|1[0-2])", value) and supported_components(written, None, int(value[2:])) else None
    if precision == "range":
        parts = value.split("/")
        if len(parts) != 2:
            return None
        valid = []
        for part in parts:
            kind = {4: "year", 7: "month", 10: "day"}.get(len(part))
            valid.append(usable_date(dict(field, normalized=part, precision=kind)))
        return value if all(valid) and parts[0] <= parts[1] else None
    patterns = {"year": r"\d{4}", "month": r"\d{4}-\d{2}", "day": r"\d{4}-\d{2}-\d{2}"}
    if precision not in patterns or not re.fullmatch(patterns[precision], value):
        return None
    # A proposed expanded two-digit year is retained in history but not used as a search date.
    if value[:4] not in re.findall(r"\b\d{4}\b", written):
        return None
    try:
        parts = [int(p) for p in value.split("-")]
        date(*(parts + [1] * (3 - len(parts))))
    except ValueError:
        return None
    if len(parts) > 1 and not supported_components(written, *parts):
        return None
    return value


def validate_document(document, image_ids, hints=None):
    errors, reasons = [], []
    if not isinstance(document, dict) or document.get("schema_version") != 1:
        return ["Expected schema_version 1 object"], []
    pages = document.get("pages")
    if not isinstance(pages, list) or any(not isinstance(p, dict) for p in pages):
        return ["pages must be an ordered array"], []
    if [p.get("image_id") for p in pages] != list(image_ids) or len(set(image_ids)) != len(image_ids):
        errors.append("Page coverage/order must exactly match supplied image IDs without duplicates")
    texts = {}
    for page in pages:
        iid, text, annotations = page.get("image_id"), page.get("text"), page.get("annotations")
        if (not isinstance(iid, str) or not isinstance(text, str) or not text.strip()
                or not isinstance(annotations, list)):
            errors.append("Every page needs its image_id, nonempty text/marker and annotations array")
            continue
        if page.get("status") not in {"text", "blank", "unrelated", "illegible", "cropped"}:
            errors.append("Invalid page status")
        texts[iid] = text
        for index, note in enumerate(annotations):
            if (not isinstance(note, dict) or not isinstance(note.get("text"), str)
                    or note.get("kind") not in {"marginal", "later", "signature", "pagination", "mark", "unknown"}):
                errors.append(f"Page {iid} annotations[{index}] needs a text string and kind "
                              "marginal|later|signature|pagination|mark|unknown")
            else:
                texts[iid] += "\n" + note["text"]
        if page.get("status") in {"unrelated", "illegible", "cropped"}:
            reasons.append(f"{iid}: {page['status']}")
        if re.search(r"\[(?:uncertain:|illegible|cropped)", texts[iid], re.I):
            reasons.append(f"{iid}: uncertain, illegible or cropped reading")
    entries = document.get("entries")
    if not isinstance(entries, list) or any(not isinstance(e, dict) for e in entries):
        return errors + ["entries must be an array of section records"], reasons
    entry_map = {}
    for entry in entries:
        eid = entry.get("entry_id")
        if (not isinstance(eid, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", eid)
                or eid in entry_map or entry.get("image_id") not in texts
                or not isinstance(entry.get("label"), str)):
            errors.append("Entry needs unique entry_id, supplied image_id and label")
        else:
            entry_map[eid] = entry

    def evidence(items, label, entry_id=None):
        if not isinstance(items, list):
            errors.append(f"{label}: evidence must be an array"); return
        for item in items:
            if (not isinstance(item, dict) or item.get("image_id") not in texts
                    or not all(item.get(k) is None or isinstance(item[k], str) for k in ("quote", "location", "entry_id"))
                    or not (item.get("quote") or item.get("location"))):
                errors.append(f"{label}: evidence needs a supplied image and short quote or precise location"); continue
            eid = item.get("entry_id") or entry_id
            if entry_id and eid != entry_id:
                errors.append(f"{label}: evidence belongs to a different entry")
            if eid and eid not in entry_map:
                errors.append(f"{label}: evidence entry_id {eid!r} must reference an existing entry")
            elif eid and entry_map[eid]["image_id"] != item["image_id"]:
                errors.append(f"{label}: evidence image {item['image_id']} differs from entry {eid!r}'s "
                              f"image {entry_map[eid]['image_id']}. Give each page its own entry_id.")
            if item.get("quote") and item["quote"] not in texts[item["image_id"]]:
                reasons.append(f"{label}: evidence quotation not found verbatim")

    def field(value, label, linked=False):
        if not isinstance(value, dict):
            errors.append(f"{label}: expected field object"); return False
        for key in ("value", "normalized"):
            if key not in value or (value[key] is not None and not isinstance(value[key], str)):
                errors.append(f"{label}.{key}: expected string or null")
        if value.get("certainty") not in CERTAINTY:
            errors.append(f"{label}: invalid certainty")
        eid = value.get("entry_id")
        if linked and ("entry_id" not in value or (eid is not None and eid not in entry_map)):
            errors.append(f"{label}: include an entry_id key referencing an existing section or null, "
                          "in addition to entry_id inside evidence")
        evidence(value.get("evidence"), label, eid)
        if value.get("value") or value.get("normalized"):
            if not value.get("evidence"):
                reasons.append(f"{label}: value lacks evidence")
            if value.get("certainty") != "explicit":
                reasons.append(f"{label}: {value.get('certainty')}")
            if value.get("normalized") and not value.get("value"):
                reasons.append(f"{label}: search value lacks source reading")
        return True

    meta = document.get("metadata")
    if not isinstance(meta, dict):
        errors.append("metadata must be an object"); meta = {}
    if set(meta) - set(FIELDS):
        errors.append("Unexpected metadata field")
    for name in FIELDS:
        field(meta.get(name), name)
    for entry in entries:
        evidence(entry.get("evidence"), "entry", entry.get("entry_id"))
    for key in ARRAYS:
        items = document.get(key)
        if not isinstance(items, list):
            errors.append(f"{key}: expected array"); continue
        for index, item in enumerate(items):
            label = f"{key}[{index}]"
            if not field(item, label, linked=True):
                continue
            if key == "identifiers":
                if item.get("number_type") not in {"collection", "specimen", "unknown"}:
                    errors.append("Identifier number_type must be collection, specimen or unknown; counts/elevations belong in observations")
                if "namespace" not in item or item["namespace"] is not None and not isinstance(item["namespace"], str):
                    errors.append("Identifier namespace must be a string or null")
                if item.get("normalized") != item.get("value") and item.get("normalized") is not None:
                    reasons.append(f"{label}: normalized number differs; retain original and review")
            if key == "taxa":
                if (item.get("role") not in {"principal", "incidental", "comparison"}
                        or item.get("name_type") not in {"scientific", "vernacular", "unknown"}
                        or item.get("rank") not in {"species", "subspecies", "genus", "unknown"}
                        or type(item.get("source_uncertain")) is not bool
                        or "alternative_group" not in item
                        or item["alternative_group"] is not None and not isinstance(item["alternative_group"], str)):
                    errors.append("Taxon needs role, name_type, rank, source_uncertain and alternative_group")
                if item.get("source_uncertain") or item.get("alternative_group"):
                    reasons.append(f"{label}: author identification is uncertain/alternative")
                if item.get("value") and "?" in item["value"] and not item.get("source_uncertain"):
                    reasons.append(f"{label}: source question mark needs uncertainty review")
            if key == "dates":
                if item.get("precision") not in {"day", "month", "month_only", "year", "range", "partial", "ambiguous", "unknown"} or not isinstance(item.get("event"), str):
                    errors.append("Date needs precision and event kind")
                if item.get("normalized") and usable_date(item) is None:
                    reasons.append(f"{label}: unsupported date normalization; excluded from normalized search")
            if key == "observations" and not isinstance(item.get("kind"), str):
                errors.append("Observation needs kind (habitat, elevation, sex_age, breeding, measurement, behavior, other)")
    if not isinstance(document.get("summary"), str):
        errors.append("summary must be a separate string")
    if not isinstance(document.get("notes"), list) or any(not isinstance(n, str) for n in document.get("notes", [])):
        errors.append('notes must be an array of plain strings, for example ["An explanatory note."]')
    translations = document.get("translations")
    if not isinstance(translations, list):
        errors.append("translations must be an array")
    else:
        for translation in translations:
            if (not isinstance(translation, dict) or translation.get("image_id") not in texts
                    or not isinstance(translation.get("text"), str) or not isinstance(translation.get("language"), str)):
                errors.append("Translation needs supplied image_id, language and text")
    return errors, sorted(set(reasons))


def parse_response(text, image_ids, hints=None):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = value
        return result
    try:
        document = json.loads(text, object_pairs_hook=unique, parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Nonfinite JSON")))
    except (ValueError, TypeError):
        return None, ["Malformed JSON; raw response preserved"], []
    try:
        errors, reasons = validate_document(document, image_ids, hints)
        if isinstance(document, dict):
            fields = list((document.get("metadata") or {}).values()) + list(document.get("taxa") or [])
            if any(isinstance(f, dict) and "authority_id" in f for f in fields):
                errors.append("Service output cannot assign human-reviewed authority IDs")
    except (TypeError, ValueError, KeyError, AttributeError):
        return document, ["Malformed nested fields; raw response preserved"], []
    return document, errors, reasons
