# Project handoff · November 17, 2026

The first field-note application is usable locally. Staff can inventory original JPEGs, inspect a read-only dry run, transcribe a selected batch when authorized, review the resulting pages and metadata, and regenerate a catalogue, reading files and Drive viewer bundle offline. An explicit publication operation manages its own outputs. This implementation used no live transcription, Drive publication, sharing change or deployment.

## Current local collection

The latest saved inventory contains **122 Carriker JPEGs and 122 active provisional notes**, all ready for preparation and all unprocessed. The source grew from the initial 19, through 21 during early inspection, to 122 at the resumed check. These are dated observations, not expected counts in reusable tests. The catalogue includes every note without guessing any species or number.

- The snapshot spans `IMG_2026_11_17_12_02_18S.jpg` through `IMG_2026_11_17_15_58_39S.jpg`. Original bytes total 100,785,780. Widths range from 2606 to 2648 pixels and heights from 2080 to 2251. The first three scans measured 2648 × 2080, 2624 × 2104 and 2639 × 2106. The inventory reported no duplicate-name/content or image-read warnings.
- The default dry run prepared every whole note at original quality. The mounted integration test independently checked JPEG format, dimensions and hashes, compared representative submitted bytes with originals, and rehashed the sources. The real store's only event at handoff was its inventory. It contains no service response, reviewed reading or paid attempt.
- Local staff data is under `local/collection` and `local/exports`. Synthetic examples have a different store under `local/demo`. The first row of the real catalogue can legitimately say “Unknown species — Number not recorded.” Identifiers come from readings or human review.

## Scan inspection and staff follow-up

These observations motivated test cases. They are initial visual impressions and have not been entered as catalogue metadata, verified examples or reviewed transcriptions.

| Carriker scan (scanner time suffix) | What to check against the original |
| --- | --- |
| `12_02_18S` | The first line appears to be a locality. A number looks like 9827. Sex marks and habitat/elevation material are present. Leave species open if the card does not supply one. |
| `12_02_47S` | The heading appears to read *Tinamus tao*. Reconcile the initial report of **8058** with the apparent reading **8085** against the actual numerals. Its stable note ID in this store is `note_183653cf2b23528aaf10ed490fbee40c`. |
| `12_03_12S` | Apparent numbers 7893 and 9846 belong to different locality passages on the same sheet. A March reference and cancellations need their own context. |
| `12_08_58S` | The heading presents alternatives with question marks. Retain the writer's doubt even if the lettering can be read clearly. |
| `12_05_00S`, `13_10_17S`, `13_13_44S` | These additional checks showed vernacular material and sex symbols, edited wording, and several numbered locality passages. Scanner sequence alone supplies no grouping or species. |

## Implementation and origins

| Files | Responsibility and origin |
| --- | --- |
| `fieldnotes/discovery.py`, `paths.py` | New field-note inventory, single-card default, explicit ordered grouping, retained records and hash-verified path reconciliation. |
| `prompt.py`, `schema.py` | New whole-note reading policy and v1 schema with page/entry evidence, identifiers, taxa, source uncertainty and date precision. |
| `catalogue.py`, `review.py`, `profiles.py` | Conservative searchable projections, append-only revision-bound corrections, approved aliases and explicitly selected versioned handwriting context. Profile limits and immutability adapt the correspondence mechanism. |
| `config.py`, `provider.py`, `execution.py`, `usage.py`, `storage.py` | Adapted small modules from the local correspondence checkout. They handle effective settings, SDK transport, one retry loop, shared-field-note quota locking, raw blobs, accounting, durable checkpointing, cache selection and recovery. Field notes have their own journal guard and quota format. No historical prices or counters were brought over. |
| `images.py` | Whole-group manifest and request preparation. JPEG preservation, EXIF handling and optional Lanczos resizing descend through correspondence from the museum-transcription image routine (build 2026-10-19.1). The field-note version records original/submitted hashes, dimensions and transformations. |
| `exports.py`, `publication.py`, `cli.py` | Staff TXT, JSON and related CSVs, offline reader bundle, verified managed publication and Windows command entry points. |
| `apps_script/viewer/` | Independent, read-only viewer adapted from the current correspondence server and HTML template. No runtime sibling import, collection mapping, credential, deployment ID or private configuration is included. |
| `test/`, `scripts/` | Domain and execution tests, mounted read-only check, synthetic fixtures, embedded-client builder, local preview and optional browser comparison. |

Initial reference inspection used correspondence commit `0609a72`. During the interruption the reference advanced through `6c44177` to local HEAD `53899c9`. Its latest HTML and server changes were inspected and the updated stylesheet, simple row presentation, processing-activity ordering, divider and page counts were incorporated. Field-note-specific number/species browsing and opening Carriker by name remain in place. Correspondence-specific name redirects, letter grouping rules and its optional alternate-model recipe were not imported. The new app reports stopped batches and the retained error to staff. The reference checkout was read-only throughout, including its pre-existing unpushed commit.

The extracted first CSS block and the embedded copy have SHA-256 `47bbfecd8f0f1793e7407c96322992814fb56c17e0dad82373c7eb011a4e2ee2` with LF line endings. The separate control styles are listed in the viewer README. The verified [repository remote](https://github.com/erl67/museum-field-note-transcriber) is used for the footer. All runtime defaults remain local and restricted.

## Verification and remaining work

**110 Python tests and 36 Node viewer tests passed**, with zero failures or skips, including the mounted Carriker check and actual Python-export-to-Apps-Script round trip. The reference baseline initially passed 122 Python and 55 viewer tests. Its updated checkout passed **131 Python and 58 viewer tests**, also with zero failures or skips. Reference test scratch files were redirected to this project's ignored local workspace.

Local Edge rendered both actual templates with identical invented scan inputs at 1365 × 950 and 390 × 844. The common computed styles and the scan/text panel geometry matched. For the 900 × 570 invented scan, the desktop sheet measured 630.5 × 399.3 CSS pixels and the mobile sheet 358 × 226.7. The second, portrait scan kept its own proportions. Enlargement, keyboard dismissal, return navigation, collector/species filtering, Search and Show all passed. Screenshots and measurements are under `local/visual-check/`. The physical phones, live Apps Script frame and real Drive authentication were outside the offline check.

Staff still need to authorize a service run, provide their key and account allocation, and review the historical readings. Real handwriting accuracy, actual billed usage and live model availability are unmeasured. The optional viewer requires real Drive file/folder IDs, access decisions and a deployment. The current implementation reads the local JSONL history and a bounded Drive bundle in full. Large collections may eventually need smaller viewer exports. Select a whole note or group within configured input limits. Preserve private backups of the journal and blobs before moving a store.

Start with the [staff guide](../README.md). For record formats and regeneration see [schema](schema.md), [review](review.md), [outputs](outputs.md), [tests](testing.md) and [viewer installation](../apps_script/viewer/README.md).
