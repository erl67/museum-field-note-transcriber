# Project handoff · November 23, 2026

## November 23 indexed Apps Script reader

Apps Script is the first deployment target. The website migration follows private Drive testing. The current website correspondence/egg readers, shared CSS, redirects and publisher were inspected read-only. The website publisher already stages field-note JPEGs with its prepare-only field-notes option.

The indexed Apps Script deployment reads a collector/set manifest, 40-card browse pages, sharded identifier and ID directories, then the selected card and one hash-verified scan. Local export and managed publication use `--viewer-only`. The private manual-copy build accepts the original scan folder and Transcriptions parent IDs and generates Code, Viewer and the manifest under ignored `local/apps-script-install/`. The intended Drive location is a managed `Field_notes_index` child of Transcriptions. The [installation guide](../apps_script/viewer/README.md) and [portable archive contract](viewer-index.md) cover updates and migration.

The saved Carriker archive at this check held 462 active cards and 576 scans across two sets. The two independent exports agreed on every stable card ID, set position, written identifier array, transcription page, ordered image ID, source path and recorded hash. There were 456 complete readings and six failed readings. Set 1 contained 356 cards and 364 scans, set 2 contained 106 cards and 212 scans. Its new homepage manifest measured 644 bytes. A synthetic test exercises 10,000 cards and 20,000 scan references through the actual resolver, including set-page boundaries and exact identifier collisions. The Google session required sign-in, the mounted originals were inaccessible here, and browser rendering could not run in this environment. A live deployment, original-byte verification on the mounted collection and a fresh visual comparison remain operator checks.

## November 23 cumulative CLI progress

Every transcription command now ends with a cumulative completed/total-card count and remaining count, after the JSON and any error or interruption message. It reads current saved states across all active inventoried notes in the store, including earlier runs and sets outside the command's selection. Retired records, duplicate revisions and uninventoried scans do not inflate the denominator. Front/back pages remain one card; stale or unsuccessful readings do not count as complete. Retry behavior and collection history are unchanged. Synthetic checks cover a 503 stop followed by resumption, a no-op pending run, interruption, stale readings and the final-line placement.

## November 21 service retries and usage feedback

Compared the current egg-slip transport and saved field-note attempts without submitting requests. Both use the same configured Gemini model, 180-second timeout, high thinking and ordered inline JPEGs. Field notes requests structured JSON; egg slips request plain text. The saved 503 high-demand errors arrived well before the client timeout. The egg-slip profile allowed five attempts while field notes allowed three.

Field notes now defaults to five total attempts with transient-error backoff of approximately 1, 2, 4 and 8 minutes, small random jitter and a configurable 600-second wait cap. Wait progress appears at least once per minute. Persistent service failures, excessive server-directed waits, authentication/settings errors and exhausted quotas still stop the batch. Every submission remains counted by the one execution layer against the unchanged 500-attempt daily allocation. Ctrl+C during backoff/pacing saves the known previous outcome; interruption in a request retains the explicit acknowledgment requirement. No generation settings or transcription prompt were changed.

Usage reports now retain strict unknown totals and add reported subtotals with per-counter coverage. The CLI explains missing usage and cost estimates in plain text. These summaries work on earlier saved journals without rewriting them. Verification: 131 Python tests ran successfully (130 passed, one optional mounted-source test skipped), plus all 40 Node viewer tests. Tests cover recovery after four 503s and continuation to the next card, finite attempts, server waits, cancellation, daily limits and partially reported token usage. Live availability has not been tested. Existing November 20 website-reader documentation changes were preserved.

## November 20 website reader decision

The public field-note reader belongs in `ericlaslo-website`, alongside the egg-slip and correspondence readers. Transcription is still in progress. Website implementation is deferred. The Apps Script viewer in this repository is an earlier prototype for reference and offline tests.

The website checkout has two relevant guides. `EGG-READER.md` describes how the site stages scans and readings for lookup by E-number or species and browsing by family. `CORRESPONDENCE.md` describes how it turns a private working export and ordered JPEGs into a public catalogue with individual letter links. For field notes, the corresponding identifiers are the stable `note_id` for the whole card and its ordered image IDs for the pages. The public URL and website data format are still open.

## November 18 local application

The first field-note application is usable locally. Staff can inventory original JPEGs, inspect a read-only dry run, transcribe a selected batch when authorized, review the resulting pages and metadata, and regenerate a catalogue, reading files and Drive viewer bundle offline. An explicit publication operation manages its own outputs. This implementation used no live transcription, Drive publication, sharing change or deployment.

## November 18 scanning and viewer update

The two completed Carriker sets contain **576 JPEGs and 462 cards**. Set 1 has 364 scans covering 348 single-sided and eight two-sided cards. Set 2 has 212 scans covering 106 front/back pairs. The offline dry run prepared all 462 cards. The local catalogue, viewer bundle and reports agree on the page order, and all cards await transcription.

The partial set 2 intake was withdrawn before the completed set was inventoried. The completed set 2 has the 12:48:30 front followed by its 12:48:38 back. The earlier draft at 12:48:15 is absent. Source hashes and note IDs for set 1 match its preceding inventory. The journal retains the earlier inventory events. Future sets can stay in their scan folders until the operator uses `--complete-set` to admit the finished pile.

Use `show --set Carriker/set1` or the viewer's scan-set selector to browse that pile. The private scanner log identifies the set 1 fronts and configures `Carriker/set2` for alternating sides. The viewer can find individual members of written catalogue ranges. The [scanning instructions](../README.md#scan-a-pile-of-cards) cover the folder conventions.

The default daily allocation is 500 attempts for `gemini-3.5-flash-lite`, as specified by the operator. The example configuration uses the same limit. Requests are paced at one per minute, and retries and format corrections each count toward the daily total.

Transcription batches now sort by collector/set and the first page's scan filename. Scanner filenames supply chronological order within each set; natural sorting keeps `set2` before `set10`. This fixes the inventory's explicit-groups-first order leaking into the execution queue. Saved page order, inventory and completed results remain intact. The CLI announces the queue order, and the change takes effect on the next start without re-inventorying.

The current correspondence stylesheet and the field-note viewer's reference and embedded copies match with SHA-256 `82ddc4e76fa105bad5668707e73d20d5e33448771567c9b0197aa58185be4804`. Both templates rendered the same scan and text panel geometry at 1365 and 390 CSS pixels. The updated viewer and exports are local.

## November 17 inventory

The November 17 inventory contained **122 Carriker JPEGs and 122 active provisional notes**, all ready for preparation and all unprocessed. The source grew from the initial 19, through 21 during early inspection, to 122 at the resumed check. These are dated observations, not expected counts in reusable tests. The catalogue includes every note without guessing any species or number.

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
| `fieldnotes/discovery.py`, `card_backs.py`, `paths.py` | Field-note inventory, scanner-log pairs, manual ordered grouping, retained records and hash-verified path reconciliation. |
| `prompt.py`, `schema.py` | New whole-note reading policy and v1 schema with page/entry evidence, identifiers, taxa, source uncertainty and date precision. |
| `catalogue.py`, `review.py`, `profiles.py` | Conservative searchable projections, append-only revision-bound corrections, approved aliases and explicitly selected versioned handwriting context. Profile limits and immutability adapt the correspondence mechanism. |
| `config.py`, `provider.py`, `execution.py`, `usage.py`, `storage.py` | Adapted small modules from the local correspondence checkout. They handle effective settings, SDK transport, one retry loop, shared-field-note quota locking, raw blobs, accounting, durable checkpointing, cache selection and recovery. Field notes have their own journal guard and quota format. No historical prices or counters were brought over. |
| `images.py` | Whole-group manifest and request preparation. JPEG preservation, EXIF handling and optional Lanczos resizing descend through correspondence from the museum-transcription image routine (build 2026-10-19.1). The field-note version records original/submitted hashes, dimensions and transformations. |
| `exports.py`, `publication.py`, `cli.py` | Staff TXT, JSON and related CSVs, offline reader bundle, verified managed publication and Windows command entry points. |
| `apps_script/viewer/` | Independent, read-only viewer adapted from the current correspondence server and HTML template. No runtime sibling import, collection mapping, credential, deployment ID or private configuration is included. |
| `test/`, `scripts/` | Domain and execution tests, mounted read-only check, synthetic fixtures, embedded-client builder, local preview and optional browser comparison. |

Initial reference inspection used correspondence commit `0609a72`. During the interruption the reference advanced through `6c44177` to local HEAD `53899c9`. Its latest HTML and server changes were inspected and the updated stylesheet, simple row presentation, processing-activity ordering, divider and page counts were incorporated. Field-note-specific number/species browsing and opening Carriker by name remain in place. Correspondence-specific name redirects, letter grouping rules and its optional alternate-model recipe were not imported. The new app reports stopped batches and the retained error to staff. The reference checkout was read-only throughout, including its pre-existing unpushed commit.

The separate field-note control styles are listed in the viewer README. The verified [repository remote](https://github.com/erl67/museum-field-note-transcriber) is used for the footer. All runtime defaults remain local and restricted.

## Verification and remaining work

After the CLI ordering change, the offline suite ran 122 Python tests successfully (one optional mounted-source test skipped) and all 40 Node viewer tests passed. The new synthetic batch checks mixed single cards and pairs, chronological filenames, natural collector/set and fallback filename order, exact page order, and skipping completed cards on resumption. A read-only check of the saved inventory places the first Carriker scan at `set1/IMG_2026_11_17_12_02_18S.jpg`, followed by the remaining set 1 cards and then set 2. No service requests or collection writes were made for this change.

On November 18, **118 Python tests and 40 Node viewer tests passed**, including the mounted set 2 check, isolation of unfinished piles, range lookup, alternating scan pairs and the Python-export-to-Apps-Script round trip. A synthetic batch starting at 499 of 500 daily attempts sent both sides of one card together, stopped at the cap, and resumed the remaining card at midnight Pacific. The November 17 field-note baseline passed 110 Python and 36 Node tests. On November 17 the correspondence checkout passed 131 Python and 58 viewer tests.

Local Edge rendered both current templates with identical invented scans at 1365 × 950 and 390 × 844. With a long source line, the desktop scan and text columns measured 592.7 and 668.3 CSS pixels. Mobile stacked the pages and preserved each image's proportions. Enlargement, keyboard dismissal, return navigation, collector/species filtering, Search and Show all passed. Screenshots and measurements are under `local/visual-check/`. The physical phones, live Apps Script frame and real Drive authentication were outside the offline check.

The November 18 offline checks did not measure real handwriting accuracy, billed usage or live model availability. The local application reads the JSONL history in full. Select a whole note or group within configured input limits. Preserve private backups of the journal and blobs before moving a store.

Start with the [staff guide](../README.md). For record formats and regeneration see [schema](schema.md), [review](review.md), [outputs](outputs.md), [tests](testing.md) and the [viewer prototype](../apps_script/viewer/README.md).
