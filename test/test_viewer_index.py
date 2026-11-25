from copy import deepcopy
import json
import shutil
import subprocess
import unittest
from unittest.mock import patch

from fieldnotes.cli import main
from fieldnotes.discovery import discover
from fieldnotes.execution import Quota, transcribe
from fieldnotes.exports import export_all
from fieldnotes.images import prepare_request
from fieldnotes.publication import generated_paths, publish, publish_files
from fieldnotes.storage import encoded, digest
from fieldnotes.viewer_index import DIRECTORY, build_index, search_keys, viewer_files
from test.helpers import ROOT, Workspace, Clock, FakeTransport, ServiceError, jpeg, rich_document


class ViewerIndexTests(Workspace):
    def setUp(self):
        super().setUp()
        self.setup_note(["A/set2/front.jpg", "A/set2/back.jpg"], complete_sets=["A/set2"])
        self.save(rich_document(self.note["image_ids"]))

    def test_incremental_publication_and_source_verification(self):
        files, warnings = viewer_files(self.store, self.inventory, verify_scans=True)
        self.assertFalse(warnings)
        dest = self.inputs / "Transcriptions"
        dest.mkdir()
        args = ["--store", str(self.store.root), "publish", "--viewer-only", "--verify-scans",
                "--output", str(self.root / "exports"), "--destination", str(dest)]
        self.assertEqual(main(args), 0)
        root = dest / DIRECTORY
        stamps = {p.name: p.stat().st_mtime_ns for p in root.iterdir()}
        before = self.store.journal.read_bytes()
        self.assertEqual(main(args), 0)
        self.assertEqual(stamps, {p.name: p.stat().st_mtime_ns for p in root.iterdir()})
        self.assertEqual(before, self.store.journal.read_bytes())
        self.assertEqual(files, {p.name: p.read_bytes() for p in root.iterdir()})
        self.assertEqual(generated_paths(self.store, self.inputs), {"Transcriptions/" + DIRECTORY + "/" + n for n in files})
        (self.inputs / "A/set2/front.jpg").write_bytes(b"changed fixture")
        self.assertEqual(main(args), 1)
        self.assertEqual(before, self.store.journal.read_bytes())
        (self.inputs / "A/set2/front.jpg").unlink()
        with self.assertRaisesRegex(ValueError, "Missing inventoried scan"):
            viewer_files(self.store, self.inventory, verify_scans=True)

    def test_validation_of_identity_order_and_projection(self):
        files, _ = viewer_files(self.store, self.inventory)
        objects = [json.loads(raw) for name, raw in files.items() if name != "index.json"]
        note = next(v for v in objects if isinstance(v, dict) and "scans" in v)
        self.assertNotIn("provenance", note)
        self.assertNotIn("search_text", note["catalogue"])
        self.assertEqual([s["image_id"] for s in note["scans"]], self.note["image_ids"])
        for change, message in [("note", "note ID"), ("scan", "scan identity"), ("pages", "page order")]:
            bad = deepcopy(note)
            if change == "scan":
                bad["scans"][1]["image_id"] = bad["scans"][0]["image_id"]
            if change == "pages":
                bad["pages"].reverse()
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, message):
                build_index([note, bad] if change == "note" else [bad])
        empty, _ = viewer_files(self.store, self.inventory, selected=[])
        self.assertEqual(json.loads(empty["index.json"])["count"], 0)
        with self.assertRaises(ValueError):
            viewer_files(self.store, self.inventory, selected=["unknown"])

    def test_partial_set_exports_and_both_publications_update_without_losing_pending_cards(self):
        fixture = json.loads((ROOT / "test/inputs/partial-set.json").read_text("utf-8"))
        folder = fixture["folder"]
        for name in fixture["filenames"]:
            jpeg(self.inputs / folder / name)
        log = self.store.root / "card-backs.txt"
        log.write_text(f"{folder} | all-pairs\n", encoding="utf-8")
        self.inventory = discover(self.inputs, self.inventory, complete_sets=[folder], card_back_log=log)
        self.store.append("inventory", self.inventory)
        cards = [n for n in self.inventory["notes"] if n["active"] and n["hints"]["collector_folder"] == "Example"]
        self.assertEqual([len(n["image_ids"]) for n in cards], [2, 2, 2])

        self.note = cards[0]
        self.request = prepare_request(self.inventory, self.note, self.config)
        doc = rich_document(self.note["image_ids"])
        doc["pages"][1]["text"] = fixture["reverse_text"]
        self.save(doc)
        self.note = cards[1]
        self.request = prepare_request(self.inventory, self.note, self.config)
        clock = Clock()
        transcribe(self.store, self.note, self.request, self.config,
                   lambda: FakeTransport([ServiceError(503)] * self.config.attempts),
                   quota=Quota(self.config, clock.time, clock.sleep), sleep=clock.sleep)

        output, destination = self.root / "exports", self.root / "published"
        destination.mkdir()
        for resumed in (False, True):
            if resumed:
                self.save(rich_document(self.note["image_ids"]))
            export_all(self.store, self.inventory, output)
            publish(self.store, self.inventory, output, destination)
            text = (destination / (folder + ".txt")).read_text("utf-8")
            self.assertIn(fixture["reverse_text"], text)
            for card in cards:
                self.assertEqual(text.count("Stable note ID: " + card["note_id"]), 1)
            self.assertIn("No complete transcription is available.", text)
            self.assertIn("Execution: unprocessed", text)
            self.assertEqual("Execution: failed" in text, not resumed)

            self.assertEqual(main(["--store", str(self.store.root), "publish", "--viewer-only", "--verify-scans",
                                   "--output", str(output), "--destination", str(destination)]), 0)
            objects = [json.loads(path.read_bytes()) for path in (destination / DIRECTORY).glob("*.json")]
            notes = {v["note_id"]: v for v in objects if isinstance(v, dict) and "note_id" in v and "scans" in v}
            manifest = json.loads((destination / DIRECTORY / "index.json").read_bytes())
            self.assertEqual(manifest["count"], 4)  # Prior set plus all three new cards.
            self.assertEqual([notes[c["note_id"]]["execution"] for c in cards],
                             ["complete", "complete" if resumed else "failed", "unprocessed"])
            self.assertEqual(notes[cards[0]["note_id"]]["pages"][1]["text"], fixture["reverse_text"])
            for card in cards:
                self.assertEqual([s["side"] for s in notes[card["note_id"]]["scans"]], ["Front", "Back"])
                self.assertEqual([s["image_id"] for s in notes[card["note_id"]]["scans"]], card["image_ids"])
            self.assertEqual(notes[cards[2]["note_id"]]["pages"], [])

    def test_explicit_empty_or_invalid_selection_never_defaults_to_all_cards(self):
        output = self.root / "selected"
        selection = self.root / "selection.json"
        args = ["--store", str(self.store.root), "export", "--viewer-only", "--viewer-notes", str(selection),
                "--output", str(output)]
        self.assertEqual(main(args), 1)
        selection.write_text("null")
        self.assertEqual(main(args), 1)
        selection.write_text("[]")
        self.assertEqual(main(args), 0)
        self.assertEqual(json.loads((output / DIRECTORY / "index.json").read_bytes())["count"], 0)

    def test_interrupted_update_preserves_old_root_then_resumes(self):
        root = self.root / "managed"
        first, _ = viewer_files(self.store, self.inventory)
        publish_files(self.store, self.inventory, first, root)
        changed = rich_document(self.note["image_ids"])
        changed["pages"][1]["text"] = "Updated synthetic back"
        self.save(changed)
        second, _ = viewer_files(self.store, self.inventory)
        from fieldnotes.storage import atomic_bytes
        def stop_at_root(path, content):
            if path.name == "index.json":
                raise OSError("simulated interruption")
            atomic_bytes(path, content)
        with patch("fieldnotes.publication.atomic_bytes", side_effect=stop_at_root), self.assertRaises(OSError):
            publish_files(self.store, self.inventory, second, root)
        for name, raw in first.items():
            self.assertEqual((root / name).read_bytes(), raw)
        publish_files(self.store, self.inventory, second, root)
        self.assertEqual(second, {p.name: p.read_bytes() for p in root.iterdir()})

    def test_range_candidates_cover_all_shared_examples(self):
        cases = json.loads((ROOT / "test/inputs/catalogue-ranges.json").read_text("utf-8"))
        for label, yes, _ in cases:
            keys = search_keys([label])
            for number in yes:
                with self.subTest(label=label, number=number):
                    self.assertTrue(keys & {"x" + digest(number.encode())[:2], f"r{len(number)}-{number[0]}"})

    @unittest.skipUnless(shutil.which("node"), "Node runs the Apps Script adapter")
    def test_ten_thousand_card_index_through_apps_script(self):
        files, _ = viewer_files(self.store, self.inventory)
        base = next(v for v in map(json.loads, files.values()) if isinstance(v, dict) and "note_id" in v)
        specs = json.loads((ROOT / "test/inputs/demo.json").read_text("utf-8"))["notes"]
        def cards():
            for i in range(10000):
                note = deepcopy(base)
                collector = "A" if i < 5000 else "B"
                folder = collector + "/set1"
                nid = "note_" + digest(str(i).encode())[:32]
                note["note_id"] = nid
                numbers = [str(i), "shared"] if i in (39, 5039) else [str(i)]
                if i == 39:
                    numbers.extend(["0012", "12a", "8419-20"])
                note["catalogue"].update(collector_folder=collector, collector=collector, numbers=numbers,
                                         number_label=", ".join(numbers), scan_sets=[folder])
                for j, (page, scan) in enumerate(zip(note["pages"], note["scans"])):
                    iid = "img_" + digest(f"{i}/{j}".encode())[:32]
                    page.update(image_id=iid, text=specs[0]["pages"][j]["text"])
                    scan.update(image_id=iid, folder=folder, path=f"{folder}/{i}-{j}.jpg")
                yield note
        # Supply the real resolver with the Python-produced bytes, without creating
        # ten thousand synced files or using a Google account.
        generated, _ = build_index(cards())
        self.assertLess(len(generated["index.json"]), 2000)
        subprocess.run(["node", "test/index_roundtrip.cjs"], cwd=ROOT,
                       input=encoded({n: raw.decode() for n, raw in generated.items()}), check=True)
