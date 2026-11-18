"""Conservative, offline display/search projections; canonical source readings stay intact."""
import json
import re
from .schema import usable_date


def search_name(value):
    return " ".join((value or "").split()).casefold()


def authorities(store):
    return {e["data"]["authority_id"]: e["data"] for e in store.events() if e["kind"] == "authority"}


def request_authorities(registry):
    return [dict(kind=a["kind"], name=a["name"], aliases=a["aliases"], rank=a.get("rank"))
            for _, a in sorted(registry.items()) if a["review_status"] == "approved"]


def resolve(field, kind, registry, rank=None):
    value = field.get("value") or field.get("normalized") or ""
    linked = registry.get(field.get("authority_id"))
    if (linked and linked["kind"] == kind and linked["review_status"] == "approved"
            and (rank is None or linked.get("rank") == rank)):
        return linked, None
    if field.get("authority_id"):
        return None, "Reviewed identity is withdrawn, missing or a different rank: " + str(field["authority_id"])
    matches = [a for a in registry.values() if a["kind"] == kind and a["review_status"] == "approved"
               and (rank is None or a.get("rank") == rank)
               and search_name(value) in {search_name(x) for x in [a["name"], *a["aliases"]]}]
    if len(matches) == 1:
        return matches[0], None
    return None, "Conflicting reviewed aliases: " + value if len(matches) > 1 else None


def number_key(value):
    """Clean digits first numerically; suffixes next naturally; other forms; missing last."""
    if not value:
        return (3, (), "")
    if re.fullmatch(r"[0-9]+", value):
        return (0, ((0, int(value)),), value)
    if re.fullmatch(r"[0-9]+[A-Za-z]+", value):
        digits, suffix = re.fullmatch(r"([0-9]+)([A-Za-z]+)", value).groups()
        return (1, ((0, int(digits)), (1, suffix.casefold())), value)
    parts = tuple((0, int(p)) if p.isascii() and p.isdigit() else (1, p.casefold())
                  for p in re.split(r"([0-9]+)", value) if p)
    return (2, parts, value)


def note_number_key(record):
    values = sorted((number_key(v) for v in record["catalogue"]["numbers"]), key=lambda x: x)
    return (values[0] if values else number_key(None), tuple(values), record["note_id"])


def project(record, registry):
    doc = record.get("document") or {}
    collector_field = doc.get("metadata", {}).get("collector", {})
    authority, conflict = resolve(collector_field, "collector", registry)
    folder = record["hints"]["collector_folder"]
    # A folder may be standardized by an explicit alias, but remains contextual attribution.
    if not collector_field.get("value") and not collector_field.get("normalized"):
        authority, conflict = resolve({"value": folder}, "collector", registry)
    collector = authority["name"] if authority else collector_field.get("value") or folder
    collector_basis = "reviewed identity" if collector_field.get("authority_id") and authority else "source reading" if collector_field.get("value") else "folder attribution"
    conflicts = [conflict] if conflict else []
    numbers = list(dict.fromkeys(f["value"] for f in doc.get("identifiers", []) if f.get("value")))
    groups, names, aliases = [], [], []
    if authority:
        aliases += [authority["name"], *authority["aliases"]]
    for taxon in doc.get("taxa", []):
        raw = taxon.get("value") or ""
        if not raw:
            continue
        authority, conflict = resolve(taxon, "taxon", registry, taxon.get("rank"))
        if conflict:
            conflicts.append(conflict)
        name = authority["name"] if authority else raw
        # Do not use a model-proposed broader equivalence for automatic grouping.
        key = authority["authority_id"] if authority else "name:" + taxon.get("rank", "unknown") + ":" + search_name(raw)
        uncertain = (taxon.get("source_uncertain", False) or bool(taxon.get("alternative_group"))
                     or taxon.get("certainty") not in {"explicit"} or "?" in raw or "[uncertain:" in raw.lower())
        group = dict(key=key, name=name, rank=taxon.get("rank", "unknown"), uncertain=uncertain,
                     role=taxon.get("role", "principal"), as_written=raw)
        if group not in groups:
            groups.append(group)
        if taxon.get("role") == "principal":
            names.append(name + (" (uncertain identification)" if uncertain else ""))
        if authority:
            aliases += [authority["name"], *authority["aliases"]]
    if not groups:
        groups = [dict(key="unknown", name="Unknown species", rank="unknown", uncertain=True, role="principal", as_written="")]
    species = "; ".join(dict.fromkeys(names)) or "Unknown species"
    number_label = ", ".join(numbers) or "Number not recorded"
    search_doc = dict(doc)
    search_doc["dates"] = [dict(d, normalized=usable_date(d)) for d in doc.get("dates", [])]
    search_text = " ".join([record["note_id"], collector, folder, *record["hints"].get("filenames", []),
                            *aliases, json.dumps(search_doc, ensure_ascii=False)])
    return dict(collector=collector, collector_folder=folder, collector_basis=collector_basis,
                numbers=numbers, number_label=number_label, species=species,
                title=species + " — " + number_label, species_groups=groups,
                aliases=sorted(set(aliases)), search_text=search_text.casefold(), conflicts=conflicts)


def browse(records, *, query="", collector="", mode="collector", sort="number"):
    if mode not in {"collector", "species"} or sort not in {"number", "species"}:
        raise ValueError("Browse mode collector/species; sort number/species")
    matches = [r for r in records if r["active"] and (not collector or collector in
               {r["catalogue"]["collector"], r["catalogue"]["collector_folder"]})
               and query.casefold() in r["catalogue"]["search_text"]]
    matches.sort(key=(lambda r: (search_name(r["catalogue"]["species"]), note_number_key(r)))
                 if sort == "species" else note_number_key)
    groups = {}
    for record in matches:
        memberships = [dict(key=record["catalogue"]["collector_folder"], name=record["catalogue"]["collector_folder"], uncertain=False)] if mode == "collector" else record["catalogue"]["species_groups"]
        for member in memberships:
            group = groups.setdefault(member["key"], dict(key=member["key"], name=member["name"], notes=[], confirmed=0, uncertain=0))
            if record["note_id"] not in group["notes"]:
                group["notes"].append(record["note_id"])
                group["uncertain" if member["uncertain"] else "confirmed"] += 1
    ordered_groups = sorted(groups.values(), key=lambda g: (search_name(g["name"]), g["key"]))
    if mode == "collector":
        activity = {}
        for record in records:
            if record["active"] and record.get("processed_at"):
                folder = record["catalogue"]["collector_folder"]
                activity[folder] = max(activity.get(folder, ""), record["processed_at"])
        ordered_groups.sort(key=lambda g: activity.get(g["key"], ""), reverse=True)
    return dict(total=len(matches), order=[r["note_id"] for r in matches], groups=ordered_groups)
