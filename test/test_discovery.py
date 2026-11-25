from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
from fieldnotes.discovery import discover, regroup, reconcile_paths
from fieldnotes.images import prepare_request
from fieldnotes.paths import inside
from fieldnotes.storage import digest
from .helpers import Workspace, jpeg


class DiscoveryTests(Workspace):
    def test_collector_scope_cannot_silently_drop_previously_saved_scans(self):
        jpeg(self.inputs / "A/one.jpg")
        jpeg(self.inputs / "B/two.jpg")
        before = discover(self.inputs)
        with self.assertRaisesRegex(ValueError, "exclude saved scans"):
            discover(self.inputs, before, collectors=["A"])
        for scope in ([], ["A/set1"], ["../A"], "A"):
            with self.subTest(scope=scope), self.assertRaises(ValueError):
                discover(self.inputs, collectors=scope)
        scoped = discover(self.inputs, before, collectors=["A", "B"])
        self.assertEqual(scoped["images"], before["images"])
        self.assertEqual(scoped["notes"], before["notes"])

    def test_prepared_prompt_uses_exact_scan_set_for_the_whole_card(self):
        folders = ["Carriker/set1", "Carriker/set2", "Carriker/set3", "Carriker/set20", "Other/set2"]
        log = self.root / "card-backs.txt"
        log.write_text("\n".join(f"{folder} | front.jpg | back.jpg" for folder in folders), encoding="utf-8")
        for folder in folders:
            jpeg(self.inputs / folder / "front.jpg", "blue")
            jpeg(self.inputs / folder / "back.jpg", "white")
        inventory = discover(self.inputs, card_back_log=log, complete_sets=folders)
        for note in inventory["notes"]:
            provenance = prepare_request(inventory, note, self.config)["provenance"]
            folder = provenance["images"][0]["path"].rsplit("/", 1)[0]
            with self.subTest(folder=folder):
                prompt = provenance["prompt"]
                self.assertEqual([page["side"] for page in provenance["images"]], ["Front", "Back"])
                self.assertEqual("mixes single-sided" in prompt, folder == "Carriker/set1")
                self.assertEqual("broad wavy strokes" in prompt, folder in {"Carriker/set2", "Carriker/set3"})

        group = dict(key="mixed", paths=["Carriker/set2/front.jpg", "Other/set2/back.jpg"],
                     source="Synthetic grouping across folders")
        mixed = regroup(inventory, dict(version=1, groups=[group]), card_backs=[])
        note = next(n for n in mixed["notes"] if n["active"] and n["override"])
        prompt = prepare_request(mixed, note, self.config)["provenance"]["prompt"]
        self.assertNotIn("Reading guidance for", prompt)

    def test_staging_deletions_and_rescans_are_invisible_until_set_completion(self):
        log = self.root / "card-backs.txt"
        log.write_text("C/set2 | all-pairs", encoding="utf-8")
        jpeg(self.inputs / "C/set1/done.jpg", "blue")
        draft = self.inputs / "C/set2/discarded.jpg"
        jpeg(draft)
        first = discover(self.inputs, card_back_log=log, complete_sets=["C/set1"])
        self.assertEqual([i["path"] for i in first["images"]], ["C/set1/done.jpg"])
        draft.unlink()
        names = ["IMG_2020_01_02_11_00_10S.jpg", "IMG_2020_01_02_11_00_20S.jpg"]
        for name, color in zip(names, ("red", "white"), strict=True):
            jpeg(self.inputs / "C/set2" / name, color)
        jpeg(self.inputs / "C/set1/later.jpg")
        self.assertEqual(discover(self.inputs, first, card_back_log=log), first)
        second = discover(self.inputs, first, card_back_log=log, complete_sets=["C/set2"])
        self.assertEqual({i["path"] for i in second["images"]}, {"C/set1/done.jpg", *("C/set2/" + n for n in names)})
        self.assertIn(first["notes"][0], second["notes"])
        self.assertEqual([n["hints"]["filenames"] for n in second["notes"] if n["override"]], [names])

    def test_timestamp_order_explicit_front_and_duplex_set_with_a_pending_back(self):
        def scan(folder, second, color):
            name = f"IMG_2020_01_02_11_00_{second:02d}S.jpg"
            jpeg(self.inputs / folder / name, color)
            return name
        front = scan("C/one", 20, "green")
        back = scan("C/one", 30, "blue")
        loose = scan("C/one", 10, "red")
        # Deliberately insert out of order. The white JPEG represents a blank reverse.
        last = scan("C/two", 30, "red")
        second = scan("C/two", 20, "white")
        first = scan("C/two", 10, "blue")
        log = self.root / "card-backs.txt"
        log.write_text(f"C/one | {front}\nC/two | all-pairs\n", encoding="utf-8")
        before = discover(self.inputs, card_back_log=log, complete_sets=["C/one", "C/two"])
        notes = {tuple(n["hints"]["filenames"]): n for n in before["notes"]}
        self.assertEqual(set(notes), {(front, back), (loose,), (first, second), (last,)})
        waiting = notes[(last,)]
        self.assertEqual(waiting["grouping"], "needs_review")
        with self.assertRaisesRegex(ValueError, "Awaiting"):
            prepare_request(before, waiting, self.config)
        final = scan("C/two", 40, "white")
        after = discover(self.inputs, before, card_back_log=log, complete_sets=["C/two"])
        ready = next(n for n in after["notes"] if n["note_id"] == waiting["note_id"])
        self.assertEqual(ready["hints"]["filenames"], [last, final])
        self.assertEqual(len(prepare_request(after, ready, self.config)["image_data"]), 2)
        four = ["C/two/" + name for name in [first, second, last, final]]
        combined = regroup(after, dict(version=1, groups=[dict(key="long", paths=four, source="Checked continuation")]))
        self.assertIn(four, [n["override"]["paths"] for n in combined["notes"] if n["active"] and n["override"]])
        scan("C/two", 15, "red")
        with self.assertRaisesRegex(ValueError, "change the saved pair"):
            discover(self.inputs, after, card_back_log=log, complete_sets=["C/two"])

    def test_duplex_rule_is_folder_scoped_and_fails_for_tied_scanner_times(self):
        log = self.root / "card-backs.txt"
        log.write_text("C/set2 | all-pairs", encoding="utf-8")
        jpeg(self.inputs / "C/set20/unrelated.jpg")
        self.assertEqual(len(discover(self.inputs, card_back_log=log, complete_sets=["C/set20"])["notes"]), 1)
        for ext in ("jpg", "jpeg"):
            jpeg(self.inputs / ("C/set2/IMG_2020_01_02_11_00_30S." + ext))
        with self.assertRaisesRegex(ValueError, "Tied scanner timestamps"):
            discover(self.inputs, card_back_log=log, complete_sets=["C/set2"])

    def test_scan_log_pairs_only_named_sides_and_keeps_front_ids(self):
        folder = "Collector/set1"
        for index, name in enumerate(("one.jpg", "two.jpg", "three.jpg", "four.jpg", "five.jpg")):
            jpeg(self.inputs / folder / name, (index * 30, 100, 150))
        jpeg(self.inputs / "Collector/set10/two.jpg")
        completed = [folder, "Collector/set10"]
        before = discover(self.inputs, complete_sets=completed)
        ids = {n["image_ids"][0]: n["note_id"] for n in before["notes"]}
        images = {i["path"]: i["image_id"] for i in before["images"]}
        log = self.root / "card-backs.txt"
        log.write_text("# scanner log\nCollector/set1 | one.jpg | two.jpg\nCollector/set1 | three.jpg | four.jpg\n", encoding="utf-8-sig")
        after = discover(self.inputs, before, card_back_log=log)
        first_inventory = discover(self.inputs, card_back_log=log, complete_sets=completed)
        notes = {n["note_id"]: n for n in after["notes"]}
        for front, back in [("one.jpg", "two.jpg"), ("three.jpg", "four.jpg")]:
            pair = [images[folder + "/" + name] for name in (front, back)]
            note = notes[ids[pair[0]]]
            self.assertEqual(note["image_ids"], pair)
            self.assertFalse(notes[ids[pair[1]]]["active"])
            self.assertIn(note, first_inventory["notes"])
            prepared = prepare_request(after, note, self.config)
            self.assertEqual([i["side"] for i in prepared["provenance"]["images"]], ["Front", "Back"])
            self.assertEqual(prepared["image_data"], [(self.inputs / folder / name).read_bytes() for name in (front, back)])
        self.assertEqual(sum(n["active"] for n in notes.values()), 4)
        self.assertEqual(discover(self.inputs, after, card_back_log=log), after)
        log.unlink()
        self.assertEqual(discover(self.inputs, after, card_back_log=log), after)
        log.write_text("Collector/set1 | one.jpg | five.jpg\n", encoding="utf-8")
        corrected = discover(self.inputs, after, card_back_log=log)
        front = next(n for n in corrected["notes"] if n["note_id"] == ids[images[folder + "/one.jpg"]])
        self.assertEqual(front["image_ids"], [images[folder + "/" + name] for name in ("one.jpg", "five.jpg")])
        self.assertEqual(sum(n["active"] for n in corrected["notes"]), 5)

    def test_scan_log_preserves_other_groups_and_rejects_conflicts_and_typos(self):
        self.setup_note(names=["C/set1/first.jpg", "C/set1/second.jpg"], complete_sets=["C/set1"])
        for name in ("third.jpg", "fourth.jpg"):
            jpeg(self.inputs / "C/set1" / name)
        log = self.root / "card-backs.txt"
        log.write_text("C/set1 | third.jpg | fourth.jpg\n", encoding="utf-8")
        inventory = discover(self.inputs, self.inventory, card_back_log=log, complete_sets=["C/set1"])
        self.assertEqual(inventory["overrides"]["groups"][0], self.inventory["overrides"]["groups"][0])
        manual_reset = regroup(inventory, {"version": 1, "groups": []})
        self.assertEqual([g["paths"] for g in manual_reset["overrides"]["groups"]], [["C/set1/third.jpg", "C/set1/fourth.jpg"]])
        for entry in ("first.jpg | third.jpg", "third.jpg | unknown.jpg", "third.jpg | ../fourth.jpg",
                      "third.jpg | third.jpg", "third.jpg | fourth.jpg\nC/set1 | fourth.jpg | third.jpg",
                      "third.jpg", "third.jpg | nonimage.txt"):
            with self.subTest(entry=entry):
                log.write_text("C/set1 | " + entry, encoding="utf-8")
                with self.assertRaises(ValueError):
                    discover(self.inputs, inventory, card_back_log=log)

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

    def test_corrupt_and_missing_jpegs_visible_nonimages_ignored(self):
        jpeg(self.inputs/'good.jpg'); (self.inputs/'bad.jpg').write_bytes(b'not jpeg')
        (self.inputs/'readme.txt').write_text('independent staff notes')
        old = discover(self.inputs); (self.inputs/'good.jpg').unlink()
        inv = discover(self.inputs, old)
        self.assertEqual({i['status'] for i in inv['images']}, {'unreadable', 'missing'})
        self.assertEqual({i['path'] for i in inv['images']}, {'good.jpg', 'bad.jpg'})
        self.assertEqual(len(inv['notes']), 2)

    def test_non_jpegs_are_not_opened_or_added_to_duplex_pairs(self):
        folder = self.inputs / "C/set3"
        for name in ("IMG_2020_01_02_11_00_10S.JPG", "IMG_2020_01_02_11_00_20S.jPeG"):
            jpeg(folder / name)
        ignored = [self.inputs / "reference.lnk", folder / "IMG_2020_01_02_11_00_15S.jpg.lnk",
                   folder / "notes.txt", folder / "preview.png", folder / "index.json"]
        for path in ignored:
            path.write_bytes(b"Synthetic reference file, not a scan")
        log = self.root / "card-backs.txt"
        log.write_text("C/set3 | all-pairs", encoding="utf-8")
        read = Path.read_bytes
        def scan_bytes(path):
            self.assertNotIn(path, ignored)
            return read(path)
        with patch.object(Path, "read_bytes", scan_bytes):
            inventory = discover(self.inputs, card_back_log=log, complete_sets=["C/set3"])
        self.assertEqual(len(inventory["images"]), 2)
        self.assertEqual(len(inventory["notes"]), 1)
        self.assertEqual(len(inventory["notes"][0]["image_ids"]), 2)
        self.assertEqual(inventory["notes"][0]["discovery"], "ready")
        self.assertTrue(all(path.read_bytes() == b"Synthetic reference file, not a scan" for path in ignored))

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
