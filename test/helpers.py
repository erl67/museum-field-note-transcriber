from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from PIL import Image
from fieldnotes.config import Config
from fieldnotes.discovery import discover, regroup
from fieldnotes.images import prepare_request
from fieldnotes.schema import empty_document
from fieldnotes.storage import Store, encoded

ROOT = Path(__file__).resolve().parents[1]


def jpeg(path, color="white", size=(32, 48)):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color).save(path, "JPEG")


def field(value, iid, *, entry_id=None, **extra):
    return dict(value=value, normalized=value, certainty="explicit", entry_id=entry_id,
                evidence=[dict(image_id=iid, quote=value, entry_id=entry_id)], **extra)


def document(ids):
    doc = empty_document(ids)
    for p in doc["pages"]:
        p["text"] = "SYNTHETIC SOFTWARE FIXTURE. Example bird. 0012 ♂\nNorth valley. March.\n9846 ♀ South slope. [deleted: all] [inserted: some]"
    return doc


def rich_document(ids):
    doc, iid = document(ids), ids[0]
    doc["entries"] = [dict(entry_id="north", image_id=iid, label="North passage", evidence=[dict(image_id=iid, quote="North valley.")]),
                      dict(entry_id="south", image_id=iid, label="South passage", evidence=[dict(image_id=iid, quote="South slope.")])]
    doc["identifiers"] = [field("0012", iid, entry_id="north", number_type="collection", namespace="Example collector"),
                          field("9846", iid, entry_id="south", number_type="collection", namespace="Example collector")]
    doc["localities"] = [field("North valley", iid, entry_id="north"), field("South slope", iid, entry_id="south")]
    doc["dates"] = [dict(field("March", iid, entry_id="north", precision="month_only", event="breeding"), normalized="--03")]
    doc["taxa"] = [field("Example bird", iid, role="principal", name_type="vernacular", rank="species", source_uncertain=False, alternative_group=None)]
    doc["observations"] = [field("♂", iid, entry_id="north", kind="sex_age")]
    doc["summary"] = "Synthetic summary of two separate observations."
    return doc


def response(doc, finish="STOP", usage=True):
    return dict(candidates=[dict(finish_reason=finish, content={"parts": [{"text": encoded(doc).decode()}]})],
                model_version="synthetic-test-model", usage_metadata=dict(prompt_token_count=100,
                candidates_token_count=50, thoughts_token_count=10, cached_content_token_count=20, total_token_count=160) if usage else None)


class FakeTransport:
    def __init__(self, answers):
        self.answers, self.calls, self.closed = list(answers), [], False
    def send(self, request, prompt):
        self.calls.append(prompt)
        item = self.answers.pop(0)
        if isinstance(item, BaseException):
            raise item
        return deepcopy(item)
    def clean_error(self, exc):
        return str(exc)
    def close(self):
        self.closed = True


class Clock:
    def __init__(self):
        self.value, self.waits = 1792440000.0, []
    def time(self):
        return self.value
    def sleep(self, duration):
        self.waits.append(duration); self.value += duration


class ServiceError(Exception):
    def __init__(self, code, message="synthetic service failure", payload=None, headers=None):
        super().__init__(message)
        from types import SimpleNamespace
        self.code, self.response_json = code, payload
        self.response = SimpleNamespace(headers=headers or {})


class Workspace(unittest.TestCase):
    def setUp(self):
        temp_root = ROOT / "local" / "test-tmp"; temp_root.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=temp_root); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.inputs = self.root / "inputs"; self.inputs.mkdir()
        self.store = Store(self.root / "store")
        self.config = replace(Config(), quota_file=str(self.root / "quota.json"))
    def setup_note(self, names=("Carriker/sample1.jpg", "Carriker/sample2.jpg"), *, complete_sets=()):
        for index, name in enumerate(names):
            jpeg(self.inputs / name, (index * 50, 100, 150))
        self.inventory = discover(self.inputs, complete_sets=complete_sets)
        if len(names) > 1:
            self.inventory = regroup(self.inventory, dict(version=1, groups=[dict(key="synthetic", paths=list(names), source="Synthetic explicit grouping")]))
        self.store.append("inventory", self.inventory)
        self.note = self.inventory["notes"][0]
        self.request = prepare_request(self.inventory, self.note, self.config)
        self.doc = document(self.note["image_ids"])
        return self.note
    def save(self, doc=None):
        from fieldnotes.execution import transcribe, Quota
        clock = Clock()
        return transcribe(self.store, self.note, self.request, self.config,
                         lambda: FakeTransport([response(doc or self.doc)]), fresh=True,
                         quota=Quota(self.config, clock.time, clock.sleep), sleep=clock.sleep)[0]
