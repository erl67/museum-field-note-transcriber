from contextlib import redirect_stdout, redirect_stderr
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from io import StringIO
import json
from pathlib import Path
from unittest.mock import patch
from fieldnotes.cli import main, parser, select, usage_summary, print_cumulative_progress
from fieldnotes.discovery import discover
from fieldnotes.execution import Quota, transcribe
from fieldnotes.exports import export_all
from fieldnotes.publication import publish, generated_paths
from fieldnotes.review import current_records
from fieldnotes.storage import atomic_json, digest, encoded, Store
from fieldnotes.usage import read_usage, aggregate, estimate, reported_usage
from .helpers import Workspace, Clock, FakeTransport, ServiceError, response, rich_document, jpeg


class CliTests(Workspace):
    def call(self,*args):
        output=StringIO()
        with redirect_stdout(output),redirect_stderr(output):code=main(['--store',str(self.store.root),*args])
        return code,output.getvalue()
    def snapshot(self):
        return {p.relative_to(self.root).as_posix():p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
    def test_dry_run_has_no_state_reports_locks_or_credentials(self):
        jpeg(self.inputs/'C/card.jpg');before=self.snapshot()
        with patch('fieldnotes.cli.Gemini',side_effect=AssertionError('No service')):
            code,text=self.call('dry-run','--input',str(self.inputs))
        self.assertEqual(code,0);self.assertEqual(before,self.snapshot());self.assertIn('zero requests',text)
    def test_inventory_and_offline_exports_without_scans(self):
        jpeg(self.inputs/'C/card.jpg');out=self.root/'exports'
        with patch("fieldnotes.cli.load_config", return_value=self.config):
            self.assertEqual(self.call('inventory','--input',str(self.inputs),'--output',str(out))[0],0)
            (self.inputs/'C/card.jpg').unlink()
            before=self.store.journal.read_bytes();self.assertEqual(self.call('export','--output',str(out))[0],0)
        self.assertEqual(before,self.store.journal.read_bytes());self.assertFalse(Path(self.config.quota_file).exists())

    def test_inventory_remembers_collector_scope_and_ignores_top_level_staging(self):
        for name in ("Carriker/set1/done.jpg", "Carriker/set3/draft.jpg", "set4/draft.jpg", "loose.jpg",
                     "Other/set1/card.jpg"):
            jpeg(self.inputs / name)
        scope = ("--collector", "Carriker", "--complete-set", "Carriker/set1")
        before = self.snapshot()
        code, text = self.call("dry-run", "--input", str(self.inputs), *scope)
        self.assertEqual(code, 0, text)
        self.assertEqual(text.count("READY "), 1)
        self.assertEqual(before, self.snapshot())
        code, text = self.call("inventory", "--input", str(self.inputs), *scope, "--output", str(self.root / "exports"))
        self.assertEqual(code, 0, text)
        first = self.store.latest("inventory")
        self.assertEqual(first["collector_scope"], ["Carriker"])
        self.assertEqual([i["path"] for i in first["images"]], ["Carriker/set1/done.jpg"])
        jpeg(self.inputs / "set4/another.jpg")
        code, text = self.call("inventory", "--input", str(self.inputs), "--output", str(self.root / "exports"))
        self.assertEqual(code, 0, text)
        self.assertEqual(self.store.latest("inventory"), first)
        before = self.store.journal.read_bytes()
        code, text = self.call("inventory", "--input", str(self.inputs), "--complete-set", "Other/set1",
                               "--output", str(self.root / "exports"))
        self.assertEqual(code, 1)
        self.assertIn("outside the saved collector scope", text)
        self.assertEqual(before, self.store.journal.read_bytes())

    def test_inventory_dry_run_and_selection_use_the_same_set_and_scanner_log(self):
        for name in ("C/set1/f.jpg", "C/set1/b.jpg", "C/set10/f.jpg", "A/set1/f.jpg", "C/loose.jpg"):
            jpeg(self.inputs / name)
        self.store.root.mkdir()
        log = self.store.root / "card-backs.txt"
        log.write_text("C/set1 | f.jpg | b.jpg", encoding="utf-8")
        out = self.root / "exports"
        before = self.snapshot()
        code, output = self.call("dry-run", "--input", str(self.inputs))
        self.assertEqual(code, 0, output)
        self.assertEqual(output.count("READY "), 1)  # The loose collector card.
        completed = ("--complete-set", "C/set1", "--complete-set", "C/set10", "--complete-set", "A/set1")
        code, output = self.call("dry-run", "--input", str(self.inputs), *completed)
        self.assertEqual(code, 0, output)
        self.assertEqual(output.count("READY "), 4)
        self.assertEqual(before, self.snapshot())
        code, output = self.call("inventory", "--input", str(self.inputs), "--output", str(out), *completed)
        self.assertEqual(code, 0, output)
        code, output = self.call("show", "--set", "C/set1")
        self.assertEqual(code, 0, output)
        listing = json.loads(output)
        self.assertEqual(listing["total"], 1)
        self.assertEqual(listing["records"][0]["files"], ["f.jpg", "b.jpg"])
        self.assertEqual(listing["records"][0]["scan_sets"], ["C/set1"])
        records = current_records(self.store, self.store.latest("inventory"))
        scope = parser().parse_args(["transcribe", "--pending", "--set", "C/set1"])
        self.assertEqual([n["note_id"] for n in select(records, scope)], listing["order"])
        bundle = json.loads((out / "Field_notes_viewer.json").read_text(encoding="utf-8"))
        paired = next(n for n in bundle["notes"] if n["note_id"] == listing["order"][0])
        self.assertEqual([s["side"] for s in paired["scans"]], ["Front", "Back"])
        self.assertEqual(paired["transcription_review"], "unreviewed")
        log.write_text("C/set1 | b.jpg | typo.jpg", encoding="utf-8")
        journal = self.store.journal.read_bytes()
        code, output = self.call("inventory", "--input", str(self.inputs), "--output", str(out))
        self.assertEqual(code, 1)
        self.assertIn("card-backs.txt line 1", output)
        self.assertEqual(self.store.journal.read_bytes(), journal)
    def test_pending_skips_complete_even_after_cache_expiry(self):
        self.setup_note(names=['C/a.jpg']);result=self.save()
        old=dict(result,saved_at=(datetime.now(timezone.utc)-timedelta(days=5)).isoformat());self.store.append('result',old)
        before=Path(self.config.quota_file).read_bytes()
        with patch('fieldnotes.cli.Gemini',side_effect=AssertionError('No service')),patch('fieldnotes.cli.api_key',side_effect=AssertionError('No credentials')):
            code,text=self.call('transcribe','--pending','--output',str(self.root/'exports'))
        self.assertEqual(code,0);self.assertEqual(Path(self.config.quota_file).read_bytes(),before)
        self.assertIn('"attempts": 0',text)

    def test_batch_continues_after_extended_overload_retry(self):
        for name in ("C/a.jpg", "C/b.jpg"):
            jpeg(self.inputs / name)
        inventory = discover(self.inputs)
        self.store.append("inventory", inventory)
        first, second = inventory["notes"]
        fake = FakeTransport([ServiceError(503)] * 4 + [response(rich_document(n["image_ids"]))
                                                       for n in (first, second)])
        clock = Clock()
        def execute(*args, **kwargs):
            return transcribe(*args, **kwargs, sleep=clock.sleep,
                              quota=Quota(self.config, clock.time, clock.sleep))
        with patch("fieldnotes.cli.load_config", return_value=self.config), \
             patch("fieldnotes.cli.api_key", return_value="dummy"), patch("fieldnotes.cli.Gemini", return_value=fake), \
             patch("fieldnotes.cli.transcribe", side_effect=execute):
            code, message = self.call("transcribe", "--pending", "--output", str(self.root / "exports"))
        self.assertEqual(code, 0, message)
        self.assertIn("2/2 cards complete", message)
        self.assertIn("Reported tokens: 320 from 2/6 attempts", message)
        self.assertIn("Token counts unavailable for 4 attempts", message)
        self.assertEqual(len(fake.calls), 6)
        self.assertEqual([r["execution"] for r in self.store.results()], ["complete", "complete"])

    def test_cumulative_last_line_includes_previous_sets_after_503_and_resume(self):
        self.setup_note(names=["C/set1/front.jpg", "C/set1/back.jpg"], complete_sets=["C/set1"])
        self.save(); self.save()  # Two revisions still represent one completed card.
        jpeg(self.inputs / "C/set2/next.jpg")
        jpeg(self.inputs / "C/set3/still-scanning.jpg")
        inventory = discover(self.inputs, self.inventory, complete_sets=["C/set2"])
        self.store.append("inventory", inventory)
        next_note = next(n for n in inventory["notes"] if n["active"] and n["note_id"] != self.note["note_id"])
        fake = FakeTransport([ServiceError(503)] * 5 + [response(rich_document(next_note["image_ids"]))])
        clock = Clock()
        def execute(*args, **kwargs):
            return transcribe(*args, **kwargs, sleep=clock.sleep,
                              quota=Quota(self.config, clock.time, clock.sleep))
        args = ("transcribe", "--pending", "--set", "C/set2", "--output", str(self.root / "exports"))
        with patch("fieldnotes.cli.load_config", return_value=self.config), \
             patch("fieldnotes.cli.api_key", return_value="dummy"), patch("fieldnotes.cli.Gemini", return_value=fake), \
             patch("fieldnotes.cli.transcribe", side_effect=execute):
            code, message = self.call(*args)
            self.assertEqual(code, 1, message)
            self.assertEqual(json.loads(message.splitlines()[-2])["attempts"], 5)
            self.assertEqual(message.splitlines()[-1],
                             "Cumulative progress (all prepared sets): 1/2 cards completed; 1 remaining.")
            code, message = self.call(*args)
            self.assertEqual(code, 0, message)
            self.assertEqual(json.loads(message.splitlines()[-2])["attempts"], 1)
            self.assertEqual(message.splitlines()[-1],
                             "Cumulative progress (all prepared sets): 2/2 cards completed; 0 remaining.")
            code, message = self.call(*args)
            self.assertEqual(code, 0, message)
            self.assertEqual(json.loads(message.splitlines()[-2])["attempts"], 0)
            self.assertEqual(message.splitlines()[-1],
                             "Cumulative progress (all prepared sets): 2/2 cards completed; 0 remaining.")
        self.assertEqual(len(fake.calls), 6)

    def test_cumulative_line_is_last_after_interruption_and_uses_current_status(self):
        self.setup_note(names=["C/a.jpg"])
        self.save()
        clock = Clock()
        with patch("fieldnotes.cli.load_config", return_value=self.config), \
             patch("fieldnotes.cli.api_key", return_value="dummy"), \
             patch("fieldnotes.cli.Gemini", return_value=FakeTransport([KeyboardInterrupt()])), \
             patch("fieldnotes.execution.Quota", side_effect=lambda config, sleep: Quota(config, clock.time, clock.sleep)):
            code, message = self.call("transcribe", "--all", "--fresh", "--output", str(self.root / "exports"))
        self.assertEqual(code, 130, message)
        self.assertIn("Interrupted; saved work retained", message)
        self.assertEqual(message.splitlines()[-1],
                         "Cumulative progress (all prepared sets): 0/1 cards completed; 1 remaining.")

    def test_cumulative_totals_do_not_count_stale_results_or_write_history(self):
        self.setup_note(names=["C/a.jpg"])
        self.save()
        changed = deepcopy(self.inventory)
        changed["images"][0]["sha256"] = "changed source hash"
        self.store.append("inventory", changed)
        before = self.store.journal.read_bytes()
        output = StringIO()
        with redirect_stdout(output):
            print_cumulative_progress(self.store)
        self.assertEqual(output.getvalue().strip(),
                         "Cumulative progress (all prepared sets): 0/1 cards completed; 1 remaining.")
        self.assertEqual(self.store.journal.read_bytes(), before)

    def test_transcription_follows_scan_order_and_preserves_whole_notes(self):
        groups = json.loads((Path(__file__).parent / "inputs/scan-order.json").read_text(encoding="utf-8"))
        for group in groups:
            for name in group:
                jpeg(self.inputs / name)
        self.store.root.mkdir()
        log = self.store.root / "card-backs.txt"
        log.write_text("\n".join(" | ".join([Path(group[0]).parent.as_posix(),
                                            *[Path(p).name for p in group]])
                                 for group in groups if len(group) == 2), encoding="utf-8")
        folders = sorted({Path(group[0]).parent.as_posix() for group in groups})
        inventory = discover(self.inputs, card_back_log=log, complete_sets=folders)
        self.store.append("inventory", inventory)
        images = {image["image_id"]: image["path"] for image in inventory["images"]}
        by_front = {images[note["image_ids"][0]]: note for note in inventory["notes"]}
        ordered = [by_front[group[0]] for group in groups]
        self.assertNotEqual(inventory["notes"], ordered)  # Inventory stores explicit groups first.
        original = deepcopy(inventory)
        fake = FakeTransport([response(rich_document(note["image_ids"])) for note in ordered])
        clock = Clock()
        args = ("transcribe", "--pending", "--output", str(self.root / "exports"))
        with patch("fieldnotes.cli.load_config", return_value=self.config), \
             patch("fieldnotes.cli.api_key", return_value="dummy"), patch("fieldnotes.cli.Gemini", return_value=fake), \
             patch("fieldnotes.execution.Quota", side_effect=lambda config, sleep: Quota(config, clock.time, clock.sleep)):
            code, message = self.call(*args)
            self.assertEqual(code, 0, message)
            self.assertIn("Processing order: collector/set", message)
            code, message = self.call(*args)
            self.assertEqual(code, 0, message)
            self.assertIn("Selected 0 cards", message)
        starts = [event["data"]["note_id"] for event in self.store.events() if event["kind"] == "attempt_start"]
        self.assertEqual(starts, [note["note_id"] for note in ordered])
        self.assertEqual(len(fake.calls), len(groups))
        actual = [[images[page["image_id"]] for page in result["provenance"]["images"]]
                  for result in self.store.results()]
        self.assertEqual(actual, groups)
        self.assertEqual(self.store.latest("inventory"), original)

    def test_pending_batch_uses_last_daily_attempt_for_a_whole_card_and_resumes_next_day(self):
        for name, color in (("front.jpg", "red"), ("back.jpg", "blue"), ("next.jpg", "green")):
            jpeg(self.inputs / "C/set1" / name, color)
        self.store.root.mkdir()
        (self.store.root / "card-backs.txt").write_text("C/set1 | front.jpg | back.jpg", encoding="utf-8")
        output = str(self.root / "exports")
        code, message = self.call("inventory", "--input", str(self.inputs), "--complete-set", "C/set1", "--output", output)
        self.assertEqual(code, 0, message)
        pair, single = self.store.latest("inventory")["notes"]
        self.assertEqual([len(pair["image_ids"]), len(single["image_ids"])], [2, 1])

        config_path = self.root / "config.json"
        atomic_json(config_path, {"quota_file": self.config.quota_file})
        model = "gemini/" + self.config.model
        atomic_json(self.config.quota_file, {"schema": "fieldnotes-quota-1", "models": {model: {
            "day": "2026-11-18", "attempts": 499, "next_start": 0, "exhausted": False}}})
        clock = Clock()
        clock.value = datetime(2026, 11, 19, 7, 58, tzinfo=timezone.utc).timestamp()
        fake = FakeTransport([response(rich_document(n["image_ids"])) for n in (pair, single)])
        args = ("--config", str(config_path), "transcribe", "--pending", "--set", "C/set1", "--output", output)
        with patch("fieldnotes.cli.api_key", return_value="dummy"), patch("fieldnotes.cli.Gemini", return_value=fake), \
             patch("fieldnotes.execution.Quota", side_effect=lambda config, sleep: Quota(config, clock.time, clock.sleep)):
            code, message = self.call(*args)
            self.assertEqual(code, 1, message)
            self.assertIn("Model gemini-3.5-flash-lite", message)
            self.assertIn("Daily limit 500 attempts", message)
            self.assertIn("[1/2] Preparing scans from C/set1 (front.jpg, back.jpg)", message)
            self.assertIn("Gemini request 1/5. Daily attempts 500/500", message)
            self.assertIn("Updating saved reports", message)
            self.assertIn("1/2 cards complete", message)
            self.assertEqual(json.loads(message.splitlines()[-2])["attempts"], 1)
            self.assertEqual(message.splitlines()[-1],
                             "Cumulative progress (all prepared sets): 1/2 cards completed; 1 remaining.")
            self.assertIn("500 of 500 attempts", message)
            self.assertIn("--pending", message)
            self.assertEqual(len(fake.calls), 1)
            clock.value += 120  # Midnight in the configured Pacific time zone.
            code, message = self.call(*args)
            self.assertEqual(code, 0, message)

        starts = [event["data"]["note_id"] for event in self.store.events() if event["kind"] == "attempt_start"]
        self.assertEqual(starts, [pair["note_id"], single["note_id"]])
        self.assertEqual(len(fake.calls), 2)

    def test_cli_checkpoint_then_export_failure_pending_no_second_request(self):
        self.setup_note(names=['C/a.jpg']);fake=FakeTransport([response(self.doc)])
        config=self.root/'config.json';atomic_json(config,{'quota_file':self.config.quota_file})
        with patch('fieldnotes.cli.api_key',return_value='dummy'),patch('fieldnotes.cli.Gemini',return_value=fake),patch('fieldnotes.cli.export_all',side_effect=OSError('disk full')):
            code,_=self.call('--config',str(config),'transcribe','--all','--output',str(self.root/'exports'))
        self.assertEqual(code,1);self.assertEqual(len(fake.calls),1);self.assertEqual(self.store.results()[-1]['execution'],'complete')
        with patch('fieldnotes.cli.Gemini',side_effect=AssertionError('No service')):
            code,_=self.call('transcribe','--pending','--output',str(self.root/'exports'))
        self.assertEqual(code,0)
    def test_number_collision_requires_id_or_collector(self):
        self.setup_note(names=['A/a.jpg']);self.save(rich_document(self.note['image_ids']))
        jpeg(self.inputs/'B/b.jpg','red');inv=discover(self.inputs,self.inventory);self.inventory=inv;self.store.append('inventory',inv)
        from fieldnotes.images import prepare_request
        self.note=next(n for n in inv['notes'] if n['hints']['collector_folder']=='B');self.request=prepare_request(inv,self.note,self.config);self.save(rich_document(self.note['image_ids']))
        code,text=self.call('transcribe','--number','0012','--output',str(self.root/'exports'))
        self.assertEqual(code,1);self.assertIn('ambiguous',text)
        with patch('fieldnotes.cli.Gemini',side_effect=AssertionError('Cached')):
            code,text=self.call('transcribe','--number','0012','--collector','B','--output',str(self.root/'exports'))
        self.assertEqual(code,0);self.assertIn('reused',text)
    def test_fresh_pending_conflict_and_unknown_selectors(self):
        self.setup_note(names=['C/a.jpg'])
        for selector in [('transcribe',),('transcribe','--note','absent'),('transcribe','--pending','--fresh')]:
            self.assertEqual(self.call(*selector,'--output',str(self.root/'exports'))[0],1)
    def test_show_species_cross_collector_and_review_template(self):
        self.setup_note(names=['Carriker/a.jpg']);self.save(rich_document(self.note['image_ids']))
        code,text=self.call('show','--mode','species','--query','9846');self.assertEqual(code,0);self.assertIn('Example bird',text)
        code,text=self.call('review-template','--note',self.note['note_id']);self.assertEqual(code,0);self.assertIn('base_review',text)
    def test_recovered_old_complete_pending_does_not_spend(self):
        self.setup_note(names=['C/a.jpg']);old=(datetime.now(timezone.utc)-timedelta(days=5)).isoformat()
        self.store.append('attempt_start',dict(attempt_id='att_old',note_id=self.note['note_id'],fingerprint=self.request['fingerprint'],run_id='run_old'))
        raw=self.store.blob(encoded(response(self.doc)),'.json');self.store.append('attempt_end',dict(attempt_id='att_old',ended_at=old,response=raw))
        result,reused=transcribe(self.store,self.note,self.request,self.config,lambda:self.fail('No request'),pending_only=True)
        self.assertTrue(reused);self.assertEqual(result['saved_at'],old)
    def test_unknown_interrupted_acknowledgement_clears_unresolved_state(self):
        self.setup_note(names=['C/a.jpg']);self.store.append('attempt_start',dict(attempt_id='att_unknown',note_id=self.note['note_id'],fingerprint=self.request['fingerprint'],run_id='run_old'))
        self.assertEqual(current_records(self.store,self.inventory)[0]['execution'],'interrupted')
        clock=Clock()
        transcribe(self.store,self.note,self.request,self.config,lambda:FakeTransport([response(self.doc)]),retry_interrupted=True,quota=Quota(self.config,clock.time,clock.sleep))
        self.assertEqual(current_records(self.store,self.inventory)[0]['execution'],'complete');self.assertTrue(self.store.latest('retry_acknowledged'))
    def test_preflight_failure_is_visible_without_transport(self):
        self.setup_note(names=["C/a.jpg"])
        (self.inputs / "C/a.jpg").write_bytes(b"changed since inventory")
        with patch("fieldnotes.cli.Gemini", side_effect=AssertionError("No transport")):
            code, _ = self.call("transcribe", "--note", self.note["note_id"], "--output", str(self.root / "exports"))
        self.assertEqual(code, 1)
        record = current_records(self.store, self.inventory)[0]
        self.assertEqual(record["execution"], "blocked")
        self.assertTrue(any("Scan changed since inventory" in reason for reason in record["review_reasons"]))
    def test_overlapping_publication_cannot_clobber_unowned_export(self):
        self.setup_note(names=["C/a.jpg"])
        out = self.root / "dest"
        out.mkdir()
        existing = out / "Field_notes_viewer.json"
        existing.write_bytes(b"unowned")
        code, message = self.call("publish", "--output", str(out), "--destination", str(out))
        self.assertEqual(code, 1)
        self.assertIn("separate directories", message)
        self.assertEqual(existing.read_bytes(), b"unowned")
    def test_interrupted_fresh_attempt_is_not_hidden_by_older_cache_hit(self):
        self.setup_note(names=["C/a.jpg"])
        first = self.save()
        self.store.append("attempt_start", dict(attempt_id="att_later", note_id=self.note["note_id"],
                          fingerprint=self.request["fingerprint"], run_id="run_later"))
        clock = Clock()
        transport = FakeTransport([response(self.doc)])
        result, reused = transcribe(self.store, self.note, self.request, self.config, lambda: transport,
            retry_interrupted=True, quota=Quota(self.config, clock.time, clock.sleep))
        self.assertFalse(reused)
        self.assertNotEqual(result["revision_id"], first["revision_id"])
        self.assertIn("att_later", result["attempt_ids"])
        self.assertEqual(current_records(self.store, self.inventory)[0]["execution"], "complete")
    def test_wrong_store_schema_rejected_read_only(self):
        self.store.root.mkdir();self.store.journal.write_text('{"schema_version":1,"data":{},"kind":"inventory"}\n')
        before=self.store.journal.read_bytes()
        with self.assertRaises(ValueError):self.store.events()
        self.assertEqual(self.store.journal.read_bytes(),before)


class PublicationTests(Workspace):
    def setUp(self):
        super().setUp();self.setup_note(names=['C/a.jpg']);self.save(rich_document(self.note['image_ids']));self.output=self.root/'exports'
        export_all(self.store,self.inventory,self.output);self.destination=self.root/'published';self.destination.mkdir()
    def test_publication_explicit_owned_stable_names_and_discovery_exclusion(self):
        before=(self.inputs/'C/a.jpg').read_bytes()
        self.assertEqual(publish(self.store, self.inventory, self.output, self.inputs), 2)
        self.assertEqual(generated_paths(self.store, self.inputs),
                         {"C/Unfiled_transcriptions.txt", "Field_notes_viewer.json"})
        self.assertIn("C/a.jpg", (self.inputs / "C" / "Unfiled_transcriptions.txt").read_text(encoding="utf-8"))
        inv=discover(self.inputs,self.inventory,generated_paths=generated_paths(self.store,self.inputs))
        self.assertEqual(len(inv['images']),1);self.assertEqual((self.inputs/'C/a.jpg').read_bytes(),before)
    def test_unowned_and_edited_outputs_never_overwritten(self):
        p=self.destination/'C'/'Unfiled_transcriptions.txt';p.parent.mkdir();p.write_text('Staff text')
        with self.assertRaisesRegex(ValueError,'Unowned'):publish(self.store,self.inventory,self.output,self.destination)
        self.assertEqual(p.read_text(),'Staff text');p.unlink()
        publish(self.store,self.inventory,self.output,self.destination);p.write_text('Staff edit')
        with self.assertRaisesRegex(ValueError,'externally edited'):publish(self.store,self.inventory,self.output,self.destination)
        self.assertEqual(p.read_text(),'Staff edit')
    def test_superseded_owned_copy_archived(self):
        publish(self.store,self.inventory,self.output,self.destination)
        old=(self.destination/'C'/'Unfiled_transcriptions.txt').read_bytes()
        self.doc['pages'][0]['text']='New synthetic reading';self.save();export_all(self.store,self.inventory,self.output)
        publish(self.store,self.inventory,self.output,self.destination)
        archives=[e['data']['archived'] for e in self.store.events() if e['kind']=='publication' and e['data'].get('archived')]
        self.assertTrue(any((self.store.root/p).read_bytes()==old for a in archives for p in a.values()))
    def test_obsolete_readers_are_archived_when_switching_to_set_readers(self):
        folder = self.destination / "Field_notes"
        folder.mkdir()
        old_reader = folder / f"{self.note['note_id']}.txt"
        contents = b"Previously published card reading"
        old_reader.write_bytes(contents)
        combined = self.destination / "Field_notes_transcriptions.txt"
        combined.write_bytes(b"Previously published collection reading")
        unrelated = folder / "staff.txt"
        unrelated.write_bytes(b"Unmanaged staff note")
        relative = old_reader.relative_to(self.destination).as_posix()
        self.store.append("publication", {"destination": str(self.destination.resolve()), "status": "complete",
                                           "files": {relative: [digest(contents)], combined.name: [digest(combined.read_bytes())]}})

        publish(self.store, self.inventory, self.output, self.destination)

        self.assertFalse(old_reader.exists())
        self.assertFalse(combined.exists())
        self.assertEqual(unrelated.read_bytes(), b"Unmanaged staff note")
        pending = [e["data"] for e in self.store.events()
                   if e["kind"] == "publication" and e["data"]["status"] == "pending"][-1]
        self.assertEqual((self.store.root / pending["archived"][relative]).read_bytes(), contents)
    def test_interrupted_publication_resumes_from_ownership_journal(self):
        from fieldnotes.storage import atomic_bytes
        calls=[]
        def interrupted(path,data):
            calls.append(path)
            if len(calls)==2:raise OSError('simulated interruption')
            atomic_bytes(path,data)
        with patch('fieldnotes.publication.atomic_bytes',side_effect=interrupted):
            with self.assertRaises(OSError):publish(self.store,self.inventory,self.output,self.destination)
        self.assertEqual(self.store.latest('publication')['status'],'pending')
        self.assertEqual(publish(self.store,self.inventory,self.output,self.destination),2)
    def test_normal_export_never_republishes(self):
        publish(self.store,self.inventory,self.output,self.destination)
        before={p.name:p.read_bytes() for p in self.destination.rglob('*') if p.is_file()}
        self.doc['pages'][0]['text']='Changed local';self.save();export_all(self.store,self.inventory,self.output)
        self.assertEqual(before,{p.name:p.read_bytes() for p in self.destination.rglob('*') if p.is_file()})
    def test_cli_publishes_separate_set_readers_under_each_collector(self):
        sets = {"Carriker/set1": ["a.jpg", "b.jpg"], "Carriker/set2": ["a.jpg"], "Other/set1": ["a.jpg"]}
        for index, scan in enumerate(f"{folder}/{name}" for folder, names in sets.items() for name in names):
            jpeg(self.inputs / scan, (25 * index, 65, 100))
        inv = discover(self.inputs, self.inventory, complete_sets=sets)
        self.store.append("inventory", inv)
        status = main(["--store", str(self.store.root), "publish", "--output", str(self.output),
                       "--destination", str(self.destination)])
        self.assertEqual(status, 0)
        readers = {p.relative_to(self.destination).as_posix(): p.read_text(encoding="utf-8")
                   for p in self.destination.rglob("*.txt")}
        self.assertEqual(set(readers), {folder + ".txt" for folder in sets} | {"C/Unfiled_transcriptions.txt"})
        all_scans = {f"{folder}/{name}" for folder, names in sets.items() for name in names}
        for folder, names in sets.items():
            text = readers[folder + ".txt"]
            self.assertEqual({path for path in all_scans if path in text},
                             {f"{folder}/{name}" for name in names})
        bundle = json.loads((self.destination / "Field_notes_viewer.json").read_text(encoding="utf-8"))
        self.assertEqual({s["path"] for n in bundle["notes"] for s in n["scans"]}, all_scans | {"C/a.jpg"})


class UsageTests(Workspace):
    def test_cached_run_reports_its_revision_history_apart_from_new_usage(self):
        self.setup_note(names=["C/a.jpg"])
        saved = self.save()
        with patch("fieldnotes.cli.Gemini", side_effect=AssertionError("Reuse needs no client")):
            code = main(["--store", str(self.store.root), "transcribe", "--note", self.note["note_id"],
                         "--output", str(self.root / "exports")])
        self.assertEqual(code, 0)
        report = usage_summary(self.store, "latest")
        self.assertEqual(report["attempts"], 0)
        self.assertEqual(report["usage"]["total"], 0)
        self.assertEqual(report["reused_history"]["revisions"], [saved["revision_id"]])
        self.assertEqual(report["reused_history"]["usage"]["total"], 160)
        self.assertEqual(usage_summary(self.store)["attempts"], 1)
    def test_usage_does_not_add_total_or_cached_twice(self):
        usage=read_usage(response({}));self.assertEqual(usage['billed_output'],60);self.assertEqual(usage['total'],160)
        self.assertEqual(aggregate([{'usage':usage}])['total'],160)
    def test_missing_usage_cost_and_mixed_attempts_remain_unknown(self):
        self.assertTrue(all(v is None for v in read_usage({}).values()))
        self.assertIsNone(aggregate([{'usage':read_usage(response({}))},{'usage':read_usage({})}])['total'])
        self.assertIsNone(estimate(read_usage({}),'example',None))
    def test_reported_usage_keeps_subtotals_and_counts_missing_fields(self):
        partial = read_usage(response({}))
        partial["cached"] = None
        totals = reported_usage([{"usage": partial}, {"usage": read_usage({})}, {"usage": read_usage(response({}))}])
        self.assertEqual(totals["total"], dict(tokens=320, reported_attempts=2, missing_attempts=1))
        self.assertEqual(totals["cached"], dict(tokens=20, reported_attempts=1, missing_attempts=2))
        self.assertEqual(reported_usage([])["total"], dict(tokens=0, reported_attempts=0, missing_attempts=0))
        self.assertIsNone(reported_usage([{}])["total"]["tokens"])
    def test_saved_run_usage_displays_known_subtotal_with_unfinished_attempt(self):
        self.setup_note(names=["C/a.jpg"])
        result = self.save()
        self.store.append("attempt_start", dict(attempt_id="att_unfinished", note_id=self.note["note_id"],
                          fingerprint=self.request["fingerprint"], run_id=result["run_id"]))
        report = usage_summary(self.store, result["run_id"])
        self.assertEqual(report["attempts"], 2)
        self.assertEqual(report["unknown_outcomes"], 1)
        self.assertIsNone(report["usage"]["total"])
        self.assertEqual(report["reported_usage"]["total"], dict(tokens=160, reported_attempts=1, missing_attempts=1))
        output, messages = StringIO(), StringIO()
        with redirect_stdout(output), redirect_stderr(messages):
            code = main(["--store", str(self.store.root), "usage", "--run", result["run_id"]])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output.getvalue()), report)
        self.assertIn("Reported tokens: 160 from 1/2 attempts", messages.getvalue())
        self.assertIn("subtotal", messages.getvalue())
        self.assertIn("null means unknown, not zero", messages.getvalue())
    def test_cost_requires_explicit_dated_matching_assumptions(self):
        rates=dict(currency='USD',model='example',as_of='2026-11-17',source='Synthetic test assumption, not billing',input=1,cached=.1,output=2)
        result=estimate(read_usage(response({})),'example',rates)
        self.assertAlmostEqual(result['amount'],.000202);self.assertIn('not invoice',result['kind'])
        self.assertIsNone(estimate(read_usage(response({})),'other',rates))
