from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
from fieldnotes.discovery import discover, regroup, reconcile_paths
from fieldnotes.images import prepare_request
from fieldnotes.paths import inside
from fieldnotes.storage import digest
from .helpers import Workspace, jpeg


class DiscoveryTests(Workspace):
    def test_old_path_reused_after_reconciliation_has_distinct_identity(self):
        self.setup_note(names=["C/first.jpg"])
        (self.inputs / "C/first.jpg").rename(self.inputs / "C/moved.jpg")
        moved = reconcile_paths(self.inventory, dict(version=1, source="Verified move", paths={"C/first.jpg": "C/moved.jpg"}))
        jpeg(self.inputs / "C/first.jpg", "red")
        refreshed = discover(self.inputs, moved)
        images = {i["path"]: i["image_id"] for i in refreshed["images"]}
        self.assertEqual(images["C/moved.jpg"], self.note["image_ids"][0])
        self.assertNotEqual(images["C/first.jpg"], images["C/moved.jpg"])
        self.assertEqual(len({n["note_id"] for n in refreshed["notes"] if n["active"]}), 2)

    def test_rotation_and_resize_record_submitted_bytes_without_changing_source(self):
        from dataclasses import replace
        from io import BytesIO
        from PIL import Image
        path = self.inputs / "card.jpg"
        exif = Image.Exif()
        exif[274] = 6
        Image.new("RGB", (120, 60)).save(path, format="JPEG", exif=exif)
        original = path.read_bytes()
        inventory = discover(self.inputs)
        for orient, size, tag in [(True, [30, 60], 1), (False, [60, 30], 6)]:
            request = prepare_request(inventory, inventory["notes"][0], replace(self.config, max_edge=60, apply_orientation=orient))
            manifest = request["provenance"]["images"][0]
            self.assertEqual(manifest["submitted_dimensions"], size)
            with Image.open(BytesIO(request["image_data"][0])) as image:
                self.assertEqual(image.getexif().get(274, 1), tag)
            self.assertNotEqual(manifest["original_sha256"], manifest["submitted_sha256"])
        self.assertEqual(path.read_bytes(), original)
    def test_case_insensitive_jpegs_one_scan_one_note(self):
        for name in ['C/one.JPG', 'C/two.jPeG', 'C/three.jpg']:
            jpeg(self.inputs / name)
        inv = discover(self.inputs)
        self.assertEqual(len(inv['notes']), 3)
        self.assertTrue(all(i['status'] == 'ready' and i['dimensions'] == [32, 48] for i in inv['images']))
        self.assertTrue(all(len(n['image_ids']) == 1 for n in inv['notes']))
        self.assertNotIn('date', inv['notes'][0]['hints'])

    def test_duplicate_names_and_bytes_do_not_merge(self):
        jpeg(self.inputs/'A/x.jpg'); jpeg(self.inputs/'B/x.jpg')
        inv = discover(self.inputs)
        self.assertEqual(len(inv['notes']), 2)
        self.assertNotEqual(*[i['image_id'] for i in inv['images']])
        self.assertTrue(all(len(i['warnings']) == 2 for i in inv['images']))

    def test_corrupt_unsupported_and_missing_visible(self):
        jpeg(self.inputs/'good.jpg'); (self.inputs/'bad.jpg').write_bytes(b'not jpeg')
        (self.inputs/'readme.txt').write_text('independent staff notes')
        old = discover(self.inputs); (self.inputs/'good.jpg').unlink()
        inv = discover(self.inputs, old)
        self.assertEqual({i['status'] for i in inv['images']}, {'unreadable', 'unsupported', 'missing'})
        self.assertEqual(len(inv['notes']), 3)

    def test_explicit_group_order_retained_no_auto_new_pages(self):
        self.setup_note()
        ids = self.note['image_ids']; nid = self.note['note_id']
        override = deepcopy(self.inventory['overrides'])
        override['groups'][0].update(note_id=nid, paths=list(reversed(override['groups'][0]['paths'])))
        inv = regroup(self.inventory, override)
        self.assertEqual(inv['notes'][0]['image_ids'], list(reversed(ids)))
        jpeg(self.inputs/'Carriker/new.jpg')
        refreshed = discover(self.inputs, inv)
        self.assertEqual(refreshed['notes'][0]['image_ids'], list(reversed(ids)))
        self.assertEqual(refreshed['notes'][0]['note_id'], nid)
        self.assertEqual(sum(n['active'] for n in refreshed['notes']), 2)

    def test_duplicate_unknown_and_escaping_group_paths_rejected(self):
        self.setup_note()
        for paths in [['Carriker/sample1.jpg'] * 2, ['absent.jpg'], ['../outside.jpg']]:
            with self.subTest(paths=paths), self.assertRaises(ValueError):
                regroup(self.inventory, dict(version=1, groups=[dict(key='x', paths=paths, source='synthetic')]))

    def test_replacement_retains_ids_but_not_hash(self):
        self.setup_note(names=['C/one.jpg']); old = self.inventory['images'][0]
        jpeg(self.inputs/'C/one.jpg', 'red')
        inv = discover(self.inputs, self.inventory)
        self.assertEqual(inv['images'][0]['image_id'], old['image_id'])
        self.assertEqual(inv['notes'][0]['note_id'], self.note['note_id'])
        self.assertNotEqual(inv['images'][0]['sha256'], old['sha256'])
        self.assertTrue(inv['images'][0]['warnings'])

    def test_explicit_hash_reconciliation_retains_history_and_ids(self):
        self.setup_note(names=['C/one.jpg']); old = deepcopy(self.inventory)
        (self.inputs/'C/one.jpg').rename(self.inputs/'C/new.jpg')
        inv = reconcile_paths(old, dict(version=1, source='External move verified', paths={'C/one.jpg':'C/new.jpg'}))
        self.assertEqual(inv['images'][0]['image_id'], old['images'][0]['image_id'])
        self.assertEqual(inv['notes'][0]['note_id'], old['notes'][0]['note_id'])
        self.assertEqual(inv['images'][0]['previous_paths'], ['C/one.jpg'])
        self.assertEqual(discover(self.inputs, inv)['notes'][0]['note_id'], self.note['note_id'])
        self.assertEqual(old, self.inventory)

    def test_reconciliation_refuses_changed_bytes_and_existing_identity(self):
        self.setup_note(names=['C/one.jpg']); (self.inputs/'C/one.jpg').unlink(); jpeg(self.inputs/'C/new.jpg','red')
        with self.assertRaisesRegex(ValueError, 'bytes differ'):
            reconcile_paths(self.inventory, dict(version=1, source='test', paths={'C/one.jpg':'C/new.jpg'}))
        jpeg(self.inputs/'C/one.jpg')
        with self.assertRaisesRegex(ValueError, 'must be absent'):
            reconcile_paths(self.inventory, dict(version=1, source='test', paths={'C/one.jpg':'C/new.jpg'}))

    def test_external_move_without_reconciliation_creates_separate_record(self):
        self.setup_note(names=['one.jpg']); (self.inputs/'one.jpg').rename(self.inputs/'two.jpg')
        inv = discover(self.inputs, self.inventory)
        self.assertEqual(len(inv['notes']), 2)
        self.assertEqual({i['status'] for i in inv['images']}, {'ready','missing'})

    def test_unavailable_retains_last_known_hash(self):
        self.setup_note(names=['one.jpg']); read = Path.read_bytes
        def unavailable(path):
            if path == self.inputs/'one.jpg': raise PermissionError('Drive file unavailable')
            return read(path)
        with patch.object(Path,'read_bytes',unavailable): inv=discover(self.inputs,self.inventory)
        self.assertEqual(inv['images'][0]['status'],'unavailable')
        self.assertEqual(inv['images'][0]['sha256'],self.inventory['images'][0]['sha256'])

    def test_duplicate_paths_casefold_blocked(self):
        jpeg(self.inputs/'card.jpg')
        with patch.object(Path,'walk',return_value=iter([(self.inputs,[],['card.jpg','CARD.jpg'])])):
            inv=discover(self.inputs)
        self.assertTrue(all(i['status']=='ambiguous_path' for i in inv['images']))
        self.assertTrue(all(n['grouping']=='needs_review' for n in inv['notes']))

    def test_payload_cannot_omit_large_or_missing_pages(self):
        from dataclasses import replace
        self.setup_note()
        for cfg in [replace(self.config,max_pages=1),replace(self.config,max_request_bytes=10)]:
            with self.assertRaises(ValueError): prepare_request(self.inventory,self.note,cfg)
        (self.inputs/'Carriker/sample2.jpg').unlink()
        with self.assertRaises(OSError): prepare_request(self.inventory,self.note,self.config)

    def test_source_integrity_and_unsafe_paths(self):
        self.setup_note(names=['one.jpg']); before=(self.inputs/'one.jpg').read_bytes()
        self.assertEqual(self.request['image_data'][0],before)
        self.assertEqual(digest(before),self.request['provenance']['images'][0]['submitted_sha256'])
        jpeg(self.inputs/'one.jpg','red')
        with self.assertRaisesRegex(ValueError,'changed since inventory'): prepare_request(self.inventory,self.note,self.config)
        for p in ['../escape','/absolute','C:/absolute','a\\b','a//b','a/./b']:
            with self.subTest(p=p),self.assertRaises(ValueError): inside(self.inputs,p)
