"""Windows-friendly CLI. Only an explicitly selected transcribe command contacts Gemini."""
import argparse
import json
from pathlib import Path
import sys
from . import __version__
from .catalogue import authorities, browse, request_authorities
from .config import load_config
from .discovery import discover, regroup, reconcile_paths
from .execution import transcribe
from .exports import export_all
from .images import prepare_request
from .paths import separate_from_sources
from .profiles import load_profile, register_profile
from .provider import Gemini, api_key
from .publication import generated_paths, publish
from .review import apply_authority, apply_review, current_records
from .storage import Store, identity, lock, read_json
from .usage import aggregate, read_usage


def parser():
    p = argparse.ArgumentParser(description="Museum field notes: inventory, transcription, review and offline browsing.")
    p.add_argument("--version", action="version", version=__version__)
    p.add_argument("--store", default="local/collection")
    p.add_argument("--config", help="Operational JSON settings; no credentials")
    commands = p.add_subparsers(dest="command", required=True)
    for name in ("inventory", "dry-run"):
        sub = commands.add_parser(name)
        sub.add_argument("--input", required=True)
        sub.add_argument("--overrides")
        if name == "inventory":
            sub.add_argument("--output", default="local/exports")
        else:
            sub.add_argument("--profile")
    sub = commands.add_parser("transcribe", help="Send complete selected notes to Gemini; may incur costs")
    scope = sub.add_mutually_exclusive_group()
    scope.add_argument("--all", action="store_true")
    scope.add_argument("--pending", action="store_true")
    scope.add_argument("--note", action="append")
    scope.add_argument("--number", help="Exact saved number; rejects ambiguous matches")
    sub.add_argument("--collector", help="Exact saved collector name or folder")
    sub.add_argument("--fresh", action="store_true")
    sub.add_argument("--retry-interrupted", action="store_true")
    sub.add_argument("--profile")
    sub.add_argument("--env-file")
    sub.add_argument("--output", default="local/exports")
    sub.add_argument("--mapping")
    for name in ("export", "publish"):
        sub = commands.add_parser(name)
        sub.add_argument("--output", default="local/exports")
        sub.add_argument("--mapping")
        if name == "publish":
            sub.add_argument("--destination", required=True, help="Explicit managed publication directory; not remembered as an automatic action")
    for name in ("group", "reconcile-paths", "review", "alias"):
        sub = commands.add_parser(name)
        sub.add_argument("--file", required=True)
    sub = commands.add_parser("show")
    sub.add_argument("--note")
    sub.add_argument("--query", default="")
    sub.add_argument("--collector", default="")
    sub.add_argument("--mode", choices=("collector", "species"), default="collector")
    sub.add_argument("--sort", choices=("number", "species"), default="number")
    sub = commands.add_parser("review-template")
    sub.add_argument("--note", required=True)
    sub = commands.add_parser("usage")
    sub.add_argument("--run", help="Run ID, or latest for last run; omit for historical attempts")
    return p


def load_file(path):
    value = read_json(path)
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object in {path}")
    return value


def require_inventory(store):
    value = store.latest("inventory")
    if not value:
        raise ValueError("No inventory; run inventory --input PATH first")
    return value


def usage_summary(store, run_id=None):
    events = store.events()
    if run_id == "latest":
        run_id = next((e["data"]["run_id"] for e in reversed(events) if e["kind"] == "run_start"), "no-run")
    starts = {e["data"]["attempt_id"] for e in events if e["kind"] == "attempt_start"
              and (not run_id or e["data"]["run_id"] == run_id)}
    calls = [e["data"] for e in events if e["kind"] == "attempt_end" and e["data"]["attempt_id"] in starts]
    report = dict(scope=run_id or "historical attempts", attempts=len(starts), known_outcomes=len(calls),
                usage=aggregate(calls + [{"usage": read_usage(None)}] * (len(starts) - len(calls))),
                costs=[c.get("cost") for c in calls], unknown_outcomes=len(starts) - len(calls))
    if run_id:
        reused = [e["data"] for e in events if e["kind"] == "reuse" and e["data"]["run_id"] == run_id]
        ended = {e["data"]["attempt_id"]: e["data"] for e in events if e["kind"] == "attempt_end"}
        historical_ids = {aid for reuse in reused for aid in reuse["attempt_ids"]} - starts
        historical = [ended.get(aid, {"usage": read_usage(None)}) for aid in sorted(historical_ids)]
        report["reused_history"] = dict(revisions=[r["revision_id"] for r in reused], attempts=len(historical),
                                        usage=aggregate(historical), costs=[c.get("cost") for c in historical])
    return report


def select(records, args):
    if not any((args.all, args.pending, args.note, args.number, args.collector)):
        raise ValueError("Select --note, --number, --collector, --pending or --all explicitly")
    if args.fresh and args.pending:
        raise ValueError("--pending skips completed work; choose --note/--collector/--all with --fresh for a new reading")
    selected = [r for r in records if r["active"] and (not args.collector or args.collector in
                {r["catalogue"]["collector"], r["catalogue"]["collector_folder"]})]
    if args.note:
        selected = [r for r in selected if r["note_id"] in args.note]
        if set(args.note) != {r["note_id"] for r in selected}:
            raise ValueError("Unknown, retired or collector-mismatched note ID")
    if args.number:
        selected = [r for r in selected if args.number in r["catalogue"]["numbers"]]
        if len(selected) != 1:
            raise ValueError("Number selector is absent or ambiguous; select stable IDs: " + ", ".join(r["note_id"] for r in selected))
    if args.pending:
        selected = [r for r in selected if r["execution"] != "complete"]
    if args.collector and not selected and not args.pending:
        raise ValueError("No active notes match that exact collector")
    return selected


def run(args):
    config, store = load_config(args.config), Store(args.store)
    if args.command == "publish":
        destination, output = Path(args.destination).resolve(), Path(args.output).resolve()
        if destination.is_relative_to(output) or output.is_relative_to(destination):
            raise ValueError("Keep ordinary exports and the managed publication destination in separate directories")
    if args.command == "usage":
        print(json.dumps(usage_summary(store, args.run), ensure_ascii=False, indent=2)); return 0
    if args.command == "dry-run":
        previous = store.latest("inventory")
        overrides = load_file(args.overrides) if args.overrides else None
        inventory = discover(args.input, previous, overrides, generated_paths(store, args.input))
        separate_from_sources(inventory, store.root, config.quota_file)
        profile = load_profile(args.profile)
        context = request_authorities(authorities(store))
        failures = 0
        for note in inventory["notes"]:
            if not note["active"]:
                continue
            try:
                request = prepare_request(inventory, note, config, profile, authorities=context)
                print(f"READY {note['note_id']}: {request['estimated_bytes']:,} bytes; {note['hints']['filenames']}")
            except (OSError, ValueError) as exc:
                failures += 1; print(f"BLOCKED {note['note_id']}: {exc}")
            for reason in note["review_reasons"]:
                print("  REVIEW: " + reason)
        for issue in inventory["issues"]:
            print("INVENTORY ISSUE: " + json.dumps(issue)); failures += 1
        print(f"{len(inventory['images'])} inventoried files. Read-only: zero requests, reports, journal changes, locks or quota reservations.")
        return int(bool(failures))
    if args.command in {"show", "review-template"}:
        inventory = require_inventory(store)
        records = current_records(store, inventory)
        if args.note:
            value = next((r for r in records if r["note_id"] == args.note), None)
            if not value:
                raise ValueError("Unknown note ID")
            if args.command == "review-template":
                if not value["document"] or value["execution"] != "complete":
                    raise ValueError("A review template needs a current complete transcription")
                value = dict(note_id=args.note, base_revision=value["result"]["revision_id"], base_review=value["review_basis"],
                             source="REPLACE with review basis", reviewer="")
        else:
            value = browse(records, query=args.query, collector=args.collector, mode=args.mode, sort=args.sort)
            indexed = {r["note_id"]: r for r in records}
            value["records"] = [dict(note_id=nid, title=indexed[nid]["catalogue"]["title"],
                                     collector=indexed[nid]["catalogue"]["collector"], execution=indexed[nid]["execution"],
                                     files=indexed[nid]["hints"]["filenames"]) for nid in value["order"]]
        print(json.dumps(value, ensure_ascii=False, indent=2)); return 0
    # Source destinations are checked before creating the first write lock.
    if args.command == "inventory":
        input_stub = dict(input_root=str(Path(args.input).resolve()))
        separate_from_sources(input_stub, store.root, config.quota_file, args.output)
    else:
        inventory = require_inventory(store)
        separate_from_sources(inventory, store.root, config.quota_file)
        if hasattr(args, "output"):
            separate_from_sources(inventory, args.output)
    with lock(store.root / "store.lock"):
        if args.command == "inventory":
            inventory = discover(args.input, store.latest("inventory"), load_file(args.overrides) if args.overrides else None,
                                 generated_paths(store, args.input))
            store.append("inventory", inventory)
            count = export_all(store, inventory, args.output)
            print(f"Saved {count} note records and {len(inventory['images'])} files to {args.output}; zero requests")
            return 0
        inventory = require_inventory(store)
        if args.command in {"group", "reconcile-paths"}:
            operation = regroup if args.command == "group" else reconcile_paths
            updated = operation(inventory, load_file(args.file))
            store.append("inventory", updated)
            print("Saved explicit identity/grouping history. Run export to refresh reading files.")
        elif args.command in {"review", "alias"}:
            patch = load_file(args.file)
            event = apply_review(store, inventory, patch) if args.command == "review" else apply_authority(store, patch)
            print(json.dumps(event, ensure_ascii=False, indent=2))
            print("Saved append-only review. Run export to refresh titles, search and groups.")
        elif args.command in {"export", "publish"}:
            count = export_all(store, inventory, args.output, load_file(args.mapping) if args.mapping else None)
            print(f"Exported {count} notes to {args.output}; zero requests")
            if args.command == "publish":
                print(f"Published {publish(store, inventory, args.output, args.destination)} managed outputs to {args.destination}")
        elif args.command == "transcribe":
            selected = select(current_records(store, inventory), args)
            profile = load_profile(args.profile)  # Frozen for the batch; no automatic profile selection.
            context = request_authorities(authorities(store))
            register_profile(store, profile)
            run_id, failures, reused = identity("run_"), 0, 0
            store.append("run_start", dict(run_id=run_id, note_ids=[r["note_id"] for r in selected], settings=config.public(), fresh=args.fresh))
            try:
                for note in selected:
                    try:
                        request = prepare_request(inventory, note, config, profile, authorities=context)
                    except (ValueError, OSError) as exc:
                        failures += 1
                        store.append("preflight_failure", dict(run_id=run_id, note_id=note["note_id"], error=str(exc)))
                        print(f"BLOCKED {note['note_id']}: {exc}"); continue
                    if any(reason.startswith("Last request preparation failed:") for reason in note["review_reasons"]):
                        store.append("preflight_ready", dict(run_id=run_id, note_id=note["note_id"]))
                    result, cached = transcribe(store, note, request, config,
                        lambda: Gemini(config, api_key(args.env_file)), fresh=args.fresh,
                        retry_interrupted=args.retry_interrupted, pending_only=args.pending, run_id=run_id)
                    if cached:
                        store.append("reuse", dict(run_id=run_id, note_id=note["note_id"], revision_id=result["revision_id"],
                                                 attempt_ids=result["attempt_ids"]))
                    reused += int(cached); failures += int(result["execution"] != "complete")
                    print(f"{note['note_id']}: {result['execution']}" + (" (reused; zero new requests)" if cached else ""))
                    if result["execution"] != "complete":
                        for error in result.get("errors", []):
                            print("  ERROR: " + error)
                    export_all(store, inventory, args.output, load_file(args.mapping) if args.mapping else None)
                    if result.get("stop_batch"):
                        print("Batch stopped. Remaining notes were not attempted. Saved results and errors are retained.")
                        break
                export_all(store, inventory, args.output, load_file(args.mapping) if args.mapping else None)
            finally:
                summary = dict(usage_summary(store, run_id), run_id=run_id, reused_results=reused, failures=failures)
                store.append("run_end", summary)
                print(json.dumps(summary, ensure_ascii=False))
            return int(bool(failures))
    return 0


def main(argv=None):
    try:
        return run(parser().parse_args(argv))
    except KeyboardInterrupt:
        print("Interrupted; saved work retained. Inspect show/export before retrying.", file=sys.stderr); return 130
    except (OSError, ValueError, RuntimeError, ImportError, TypeError, KeyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr); return 1
