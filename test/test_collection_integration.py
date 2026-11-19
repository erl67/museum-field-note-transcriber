"""Optional read-only check of a mounted Field Notes collection. No expected scan count."""
import hashlib
import os
from pathlib import Path
import unittest
from PIL import Image
from fieldnotes.config import Config
from fieldnotes.discovery import discover
from fieldnotes.images import prepare_request
from fieldnotes.paths import inside


class CarrikerIntegration(unittest.TestCase):
    def test_mounted_originals_and_request_bytes(self):
        configured = os.environ.get("FIELDNOTES_TEST_ROOT")
        if not configured:
            self.skipTest("Set FIELDNOTES_TEST_ROOT to opt into the mounted Carriker check")
        root = Path(configured)
        name = os.environ.get("FIELDNOTES_TEST_SET")
        if not name:
            self.skipTest("Set FIELDNOTES_TEST_SET to the exact completed set to check")
        folder = inside(root, name)
        if not folder.is_dir():
            self.skipTest("Completed source folder is unavailable on this machine")
        paths = sorted(p for p in folder.iterdir() if p.suffix.lower() in {".jpg", ".jpeg"})
        self.assertTrue(paths, "The selected completed set has no JPEGs")
        originals = {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
        inventory = discover(root, complete_sets=[name])
        by_path = {i["path"]: i for i in inventory["images"] if i["path"] in originals}
        self.assertEqual(set(originals), set(by_path))
        for relative, scan in by_path.items():
            self.assertEqual(scan["status"], "ready", relative)
            self.assertEqual(scan["sha256"], originals[relative])
            with Image.open(root / relative) as image:
                self.assertEqual(image.format, "JPEG")
                self.assertEqual(list(image.size), scan["dimensions"])
                self.assertGreater(min(image.size), 0)
            self.assertEqual((root / relative).stat().st_size, scan["size"])
        notes = {tuple(n["image_ids"]): n for n in inventory["notes"] if n["active"]}
        for path in {paths[0], paths[len(paths) // 2], paths[-1]}:
            scan = by_path[path.relative_to(root).as_posix()]
            note = notes[(scan["image_id"],)]
            request = prepare_request(inventory, note, Config())
            self.assertEqual(request["image_data"][0], path.read_bytes())
            self.assertEqual(request["provenance"]["images"][0]["submitted_sha256"], scan["sha256"])
        self.assertEqual(originals, {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})
