from copy import deepcopy
from dataclasses import replace
import csv
import json
import shutil
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch
from fieldnotes.catalogue import browse, matches_number, number_key
from fieldnotes.cli import parser, select
from fieldnotes.discovery import discover, regroup, reconcile_paths
from fieldnotes.exports import export_all, cell
from fieldnotes.images import prepare_request
from fieldnotes.profiles import load_profile, register_profile
from fieldnotes.review import current_records, apply_review, apply_authority
from fieldnotes.storage import atomic_json, digest
from .helpers import Workspace, rich_document, field, jpeg


class ReviewTests(Workspace):
    def setUp(self):
        super().setUp();self.setup_note(names=['Carriker/one.jpg']);self.result=self.save(rich_document(self.note['image_ids']))
    def current(self): return current_records(self.store,self.inventory)[0]
    def test_range_lookup_through_catalogue_and_transcription_selection(self):
        cases = json.loads((Path(__file__).parent / "inputs/catalogue-ranges.json").read_text(encoding="utf-8"))
        for raw, yes, no in cases:
            for query in yes + no:
                with self.subTest(raw=raw, query=query):
                    self.assertEqual(matches_number([raw], query), query in yes)
        self.review(identifiers=[field("8419-20", self.note["image_ids"][0], entry_id="north",
                                      number_type="collection", namespace="Example")])
        record = self.current()
        self.assertEqual(record["catalogue"]["numbers"], ["8419-20"])
        self.assertEqual(browse([record], query="8420")["order"], [record["note_id"]])
        args = parser().parse_args(["transcribe", "--number", "8420"])
        self.assertEqual(select([record], args), [record])
        with self.assertRaisesRegex(ValueError, "ambiguous"):
            select([record, dict(record, note_id="another")], args)
    def review(self,**changes):
        r=self.current()
        return apply_review(self.store,self.inventory,dict(note_id=r['note_id'],base_revision=r['result']['revision_id'],base_review=r['review_basis'],source='Synthetic review',**changes))
    def test_metadata_approval_does_not_approve_transcription(self):
        self.review(metadata_review='approved');self.assertEqual(self.current()['transcription_review'],'unreviewed')
    def test_explicit_taxon_identity_must_match_rank(self):
        authority = apply_authority(self.store, dict(kind="taxon", name="Synthetic subspecies",
            rank="subspecies", aliases=[], review_status="approved", source="Synthetic review"))["data"]
        taxon = dict(self.current()["document"]["taxa"][0], authority_id=authority["authority_id"])
        with self.assertRaisesRegex(ValueError, "rank-mismatched"):
            self.review(taxa=[taxon])
    @unittest.skipUnless(shutil.which("node"), "Node required for the Python-to-viewer export check")
    def test_actual_python_export_is_accepted_by_apps_script(self):
        export_all(self.store, self.inventory, self.root / "exports")
        raw = (self.root / "exports/Field_notes_viewer.json").read_bytes()
        program = """
const raw = require('node:fs').readFileSync(0, 'utf8');
const { context } = require('./apps_script/viewer/test_support.cjs');
const bundle = JSON.parse(raw), api = context(bundle, {exportText: raw}).sandbox;
const row = api.listFolders({query: '0012'}).folders[0].notes[0];
const result = api.loadNote(row.note_id, {});
if (result.note.pages.length !== 1 || !result.note.pages[0].text.includes('♂')) process.exit(1);
"""
        subprocess.run(["node", "-e", program], input=raw, cwd=Path(__file__).resolve().parents[1], check=True)
    def test_corrections_survive_export_and_original_is_immutable(self):
        old=deepcopy(self.result);iid=self.note['image_ids'][0]
        self.review(pages={iid:{'text':'Human synthetic correction ♂'}},summary='Corrected summary',notes=['New note'])
        before=self.store.journal.read_bytes();export_all(self.store,self.inventory,self.root/'exports')
        self.assertEqual(self.store.journal.read_bytes(),before);self.assertEqual(self.store.results()[0],old)
        text=(self.root/'exports/readable'/f"{self.note['note_id']}.txt").read_text(encoding='utf-8')
        self.assertIn('Human synthetic correction',text);self.assertIn('Corrected summary',text)
    def test_page_change_invalidates_both_approvals(self):
        self.review(metadata_review='approved',transcription_review='approved')
        self.review(pages={self.note['image_ids'][0]:{'text':'Changed evidence'}})
        self.assertEqual(self.current()['metadata_review'],'in_progress');self.assertEqual(self.current()['transcription_review'],'in_progress')
    def test_number_change_preserves_text_approval_and_changes_search(self):
        self.review(transcription_review='approved',metadata_review='approved')
        number=field('0009',self.note['image_ids'][0],entry_id='north',number_type='collection',namespace='Example')
        self.review(identifiers=[number])
        r=self.current();self.assertEqual(r['transcription_review'],'approved');self.assertEqual(r['metadata_review'],'in_progress')
        self.assertEqual(browse([r],query='0009')['total'],1);self.assertEqual(r['note_id'],self.note['note_id'])
        self.assertIn('0009',r['catalogue']['title'])
    def test_new_service_revision_does_not_inherit_correction(self):
        self.review(summary='Manual',transcription_review='approved');self.save(rich_document(self.note['image_ids']))
        r=self.current();self.assertEqual(r['transcription_review'],'unreviewed');self.assertNotEqual(r['document']['summary'],'Manual');self.assertTrue(r['stale_reviews'])
    def test_stale_same_revision_review_rejected(self):
        r=self.current();old=dict(note_id=r['note_id'],base_revision=self.result['revision_id'],base_review=r['review_basis'],source='test',summary='old')
        self.review(summary='new')
        with self.assertRaisesRegex(ValueError,'base_review'):apply_review(self.store,self.inventory,old)
    def test_source_replacement_invalidates_review_and_scan_pairing(self):
        self.review(transcription_review='approved');jpeg(self.inputs/'Carriker/one.jpg','red')
        self.inventory=discover(self.inputs,self.inventory);r=self.current()
        self.assertEqual(r['execution'],'stale');self.assertEqual(r['transcription_review'],'unreviewed')
        export_all(self.store,self.inventory,self.root/'exports')
        bundle=json.loads((self.root/'exports/Field_notes_viewer.json').read_text())
        scan=bundle['notes'][0]['scans'][0];self.assertEqual(scan['status'],'stale_source')
        self.assertEqual(scan['sha256'],self.result['provenance']['images'][0]['original_sha256'])
    def test_missing_scan_does_not_erase_completed_reviewed_text(self):
        self.review(transcription_review='approved');(self.inputs/'Carriker/one.jpg').unlink()
        self.inventory=discover(self.inputs,self.inventory);r=self.current()
        self.assertEqual(r['execution'],'complete');self.assertEqual(r['discovery'],'unavailable');self.assertEqual(r['transcription_review'],'approved')
        export_all(self.store,self.inventory,self.root/'exports')
    def test_regrouping_expires_review_even_if_same_bytes(self):
        self.review(metadata_review='approved');jpeg(self.inputs/'Carriker/two.jpg')
        inv=discover(self.inputs,self.inventory)
        self.inventory=regroup(inv,dict(version=1,groups=[dict(key='both',note_id=self.note['note_id'],paths=['Carriker/one.jpg','Carriker/two.jpg'],source='test')]))
        self.assertEqual(self.current()['execution'],'stale');self.assertEqual(self.current()['metadata_review'],'unreviewed')
    def test_explicit_path_reconciliation_preserves_approvals(self):
        self.review(metadata_review='approved');(self.inputs/'Carriker/one.jpg').rename(self.inputs/'Carriker/renamed.jpg')
        self.inventory=reconcile_paths(self.inventory,dict(version=1,source='verified external move',paths={'Carriker/one.jpg':'Carriker/renamed.jpg'}))
        self.assertEqual(self.current()['metadata_review'],'approved')
    def test_invalid_review_preserves_journal(self):
        before=self.store.journal.read_bytes()
        for changes in [dict(notes=[4]),dict(taxa=[{}]),dict(metadata={'sender':{}}),dict(pages={'absent':{'text':'x'}}),dict(metadata_review='done')]:
            with self.subTest(changes=changes),self.assertRaises(ValueError):self.review(**changes)
            self.assertEqual(self.store.journal.read_bytes(),before)
    def test_empty_replacement_arrays_clear_selected_values(self):
        self.review(identifiers=[],taxa=[],notes=[])
        self.assertEqual(self.current()['catalogue']['numbers'],[]);self.assertEqual(self.current()['catalogue']['species'],'Unknown species')
    def test_alias_refresh_without_requests_and_conflicts_visible(self):
        a=apply_authority(self.store,dict(kind='taxon',name='Reviewed example',rank='species',aliases=['Example bird'],review_status='approved',source='Synthetic authority'))
        r=self.current();self.assertEqual(r['catalogue']['species'],'Reviewed example');self.assertEqual(browse([r],query='Reviewed example')['total'],1)
        self.assertEqual(r['document']['taxa'][0]['value'],'Example bird')
        apply_authority(self.store,dict(kind='taxon',name='Conflicting example',rank='species',aliases=['Example bird'],review_status='approved',source='Synthetic'))
        self.assertTrue(self.current()['catalogue']['conflicts']);self.assertEqual(self.current()['catalogue']['species'],'Example bird')
        self.assertEqual(len(self.store.results()),1)
    def test_species_subspecies_and_alternatives_separate(self):
        doc=deepcopy(self.current()['document']);taxon=doc['taxa'][0]
        doc['taxa']=[dict(taxon,value='Example bird?',source_uncertain=True,alternative_group='a'),dict(taxon,value='Other bird?',normalized='Other bird?',source_uncertain=True,alternative_group='a'),dict(taxon,value='Example bird minor',normalized='Example bird minor',rank='subspecies')]
        self.review(taxa=doc['taxa']);result=browse([self.current()],mode='species')
        self.assertEqual(len(result['groups']),3);self.assertEqual(sum(g['uncertain'] for g in result['groups']),2)
        self.assertEqual(result['total'],1)
    def test_numeric_sort_deterministic_exact_display(self):
        values=['12b','unknown','0012','2','12','12a','12–15',None]
        ordered=sorted(values,key=number_key)
        self.assertEqual(ordered[:5],['2','0012','12','12a','12b']);self.assertIsNone(ordered[-1])
    def test_related_tables_unicode_multiline_and_formula_protection(self):
        self.review(summary='=HYPERLINK("x")\n♂')
        export_all(self.store,self.inventory,self.root/'exports')
        with (self.root/'exports/catalogue.csv').open(encoding='utf-8-sig',newline='') as f:rows=list(csv.DictReader(f))
        self.assertTrue(rows[0]['summary'].startswith("'="));self.assertIn('\n♂',rows[0]['summary'])
        with (self.root/'exports/identifiers.csv').open(encoding='utf-8-sig',newline='') as f:ids=list(csv.DictReader(f))
        self.assertEqual([r['value'] for r in ids],['0012','9846']);self.assertEqual(len(ids),2)
        self.assertEqual(self.current()['document']['summary'],'=HYPERLINK("x")\n♂')
        for value in [' =x','+x','-x','@x','\tx','\nx']:self.assertTrue(cell(value).startswith("'"))
    def test_drive_mapping_hash_and_source_export_boundary(self):
        iid=self.note['image_ids'][0]
        with self.assertRaises(ValueError):export_all(self.store,self.inventory,self.inputs/'reports')
        with self.assertRaises(ValueError):export_all(self.store,self.inventory,self.root/'exports',dict(version=1,images={iid:dict(file_id='synthetic_drive_id',original_sha256='0'*64)}))


class ProfileTests(Workspace):
    def profile(self):
        return dict(schema_version=1,profile_id='hand_example',version='1',hand_description='Synthetic',review_status='approved',reviewer='Tester',notes=['Verified example note'],examples=[dict(image_id='img_example',source_sha256='a'*64,region='top line',transcription='Verified text',review_status='verified',reviewer='Tester')])
    def test_approved_bounded_versioned_profiles(self):
        profile=self.profile();path=self.root/'profile.json';atomic_json(path,profile);loaded=load_profile(path)
        register_profile(self.store,loaded);register_profile(self.store,loaded)
        self.assertEqual(len(self.store.events()),1)
        profile['notes'].append('New note');atomic_json(path,profile)
        with self.assertRaisesRegex(ValueError,'new version'):register_profile(self.store,load_profile(path))
        profile['version']='2';atomic_json(path,profile);register_profile(self.store,load_profile(path))
        self.assertEqual(len(self.store.events()),2)
    def test_unapproved_examples_missing_regions_and_oversize_rejected(self):
        for update in ['unapproved','region','count','size']:
            p=self.profile()
            if update=='unapproved':p['examples'][0]['review_status']='model_output'
            if update=='region':p['examples'][0].pop('region')
            if update=='count':p['examples']*=6
            if update=='size':p['notes']=['a'*17000]
            path=self.root/'p.json';atomic_json(path,p)
            with self.subTest(update=update),self.assertRaises(ValueError):load_profile(path)
    def test_profile_and_request_snapshots_isolated(self):
        self.setup_note();profile=self.profile();request=prepare_request(self.inventory,self.note,self.config,profile)
        profile['notes'].append('Changed after freeze')
        self.assertNotIn('Changed after freeze',request['provenance']['handwriting_profile']['notes'])
        self.assertNotEqual(request['fingerprint'],prepare_request(self.inventory,self.note,self.config,profile)['fingerprint'])
        self.assertNotEqual(request['fingerprint'],self.request['fingerprint'])
    def test_fingerprint_sensitive_to_all_effective_context(self):
        self.setup_note();base=self.request['fingerprint']
        for cfg in [replace(self.config,model='gemini-example'),replace(self.config,temperature=.5),replace(self.config,thinking_level='low'),replace(self.config,max_edge=16)]:
            self.assertNotEqual(base,prepare_request(self.inventory,self.note,cfg)['fingerprint'])
        note=deepcopy(self.note);note['image_ids'].reverse();self.assertNotEqual(base,prepare_request(self.inventory,note,self.config)['fingerprint'])
        note=deepcopy(self.note);note['hints']['collector_folder']='Other';self.assertNotEqual(base,prepare_request(self.inventory,note,self.config)['fingerprint'])
        self.assertNotEqual(base,prepare_request(self.inventory,self.note,self.config,authorities=[dict(kind='collector',name='Other',aliases=[])])['fingerprint'])
