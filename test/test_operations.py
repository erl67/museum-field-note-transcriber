from contextlib import redirect_stdout, redirect_stderr
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from io import StringIO
import json
from pathlib import Path
from unittest.mock import patch
from fieldnotes.cli import main, usage_summary
from fieldnotes.discovery import discover
from fieldnotes.execution import Quota, transcribe
from fieldnotes.exports import export_all
from fieldnotes.publication import publish, generated_paths
from fieldnotes.review import current_records
from fieldnotes.storage import atomic_json, encoded, Store
from fieldnotes.usage import read_usage, aggregate, estimate
from .helpers import Workspace, Clock, FakeTransport, response, rich_document, jpeg


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
        self.assertEqual(self.call('inventory','--input',str(self.inputs),'--output',str(out))[0],0)
        (self.inputs/'C/card.jpg').unlink()
        before=self.store.journal.read_bytes();self.assertEqual(self.call('export','--output',str(out))[0],0)
        self.assertEqual(before,self.store.journal.read_bytes());self.assertFalse(Path('local/fieldnotes-quota.json').exists())
    def test_pending_skips_complete_even_after_cache_expiry(self):
        self.setup_note(names=['C/a.jpg']);result=self.save()
        old=dict(result,saved_at=(datetime.now(timezone.utc)-timedelta(days=5)).isoformat());self.store.append('result',old)
        before=Path(self.config.quota_file).read_bytes()
        with patch('fieldnotes.cli.Gemini',side_effect=AssertionError('No service')),patch('fieldnotes.cli.api_key',side_effect=AssertionError('No credentials')):
            code,text=self.call('transcribe','--pending','--output',str(self.root/'exports'))
        self.assertEqual(code,0);self.assertEqual(Path(self.config.quota_file).read_bytes(),before)
        self.assertIn('"attempts": 0',text)
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
        count=publish(self.store,self.inventory,self.output,self.inputs);self.assertEqual(count,4)
        inv=discover(self.inputs,self.inventory,generated_paths=generated_paths(self.store,self.inputs))
        self.assertEqual(len(inv['images']),1);self.assertEqual((self.inputs/'C/a.jpg').read_bytes(),before)
        self.assertTrue((self.inputs/'Field_notes'/f"{self.note['note_id']}.txt").is_file())
    def test_unowned_and_edited_outputs_never_overwritten(self):
        p=self.destination/'Field_notes_transcriptions.txt';p.write_text('Staff text')
        with self.assertRaisesRegex(ValueError,'Unowned'):publish(self.store,self.inventory,self.output,self.destination)
        self.assertEqual(p.read_text(),'Staff text');p.unlink()
        publish(self.store,self.inventory,self.output,self.destination);p.write_text('Staff edit')
        with self.assertRaisesRegex(ValueError,'externally edited'):publish(self.store,self.inventory,self.output,self.destination)
        self.assertEqual(p.read_text(),'Staff edit')
    def test_superseded_owned_copy_archived(self):
        publish(self.store,self.inventory,self.output,self.destination)
        old=(self.destination/'Field_notes_transcriptions.txt').read_bytes()
        self.doc['pages'][0]['text']='New synthetic reading';self.save();export_all(self.store,self.inventory,self.output)
        publish(self.store,self.inventory,self.output,self.destination)
        archives=[e['data']['archived'] for e in self.store.events() if e['kind']=='publication' and e['data'].get('archived')]
        self.assertTrue(any((self.store.root/p).read_bytes()==old for a in archives for p in a.values()))
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
        self.assertEqual(publish(self.store,self.inventory,self.output,self.destination),4)
    def test_normal_export_never_republishes(self):
        publish(self.store,self.inventory,self.output,self.destination)
        before={p.name:p.read_bytes() for p in self.destination.rglob('*') if p.is_file()}
        self.doc['pages'][0]['text']='Changed local';self.save();export_all(self.store,self.inventory,self.output)
        self.assertEqual(before,{p.name:p.read_bytes() for p in self.destination.rglob('*') if p.is_file()})
    def test_same_display_labels_have_collision_free_outputs(self):
        jpeg(self.inputs/'C/b.jpg','red');inv=discover(self.inputs,self.inventory);self.store.append('inventory',inv)
        export_all(self.store,inv,self.output);publish(self.store,inv,self.output,self.destination)
        self.assertEqual(len(list((self.destination/'Field_notes').glob('note_*.txt'))),2)


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
    def test_cost_requires_explicit_dated_matching_assumptions(self):
        rates=dict(currency='USD',model='example',as_of='2026-11-17',source='Synthetic test assumption, not billing',input=1,cached=.1,output=2)
        result=estimate(read_usage(response({})),'example',rates)
        self.assertAlmostEqual(result['amount'],.000202);self.assertIn('not invoice',result['kind'])
        self.assertIsNone(estimate(read_usage(response({})),'other',rates))
