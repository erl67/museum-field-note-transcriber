# Staff review, aliases and grouping

Start with the original scan and its page-labelled reading. `show --note` includes the chosen revision, as-written fields, proposed normalizations, evidence, current human corrections and prior reviews. A completed response is ready for review. It starts with both approval states unreviewed.

## Edit a reading

The following PowerShell 7 example prepares a correction for a complete note. To practice with the invented collection, run `scripts/make_demo.py` first and use `$storeArgs = @('--store','local/demo/store')`. For the real inventory use `$storeArgs = @()`. Choose the correct record from the listing before setting `$note`.

```powershell
$py = '.\.venv\Scripts\python.exe'
$storeArgs = @('--store', 'local/demo/store')
$listing = & $py -m fieldnotes @storeArgs show --collector Carriker --query '12a' | ConvertFrom-Json
$note = $listing.records[0].note_id
$record = & $py -m fieldnotes @storeArgs show --note $note | ConvertFrom-Json -AsHashtable
$patch = & $py -m fieldnotes @storeArgs review-template --note $note | ConvertFrom-Json -AsHashtable
$patch.source = 'Practice correction checked against the invented valley card'
$patch.reviewer = 'Demonstration reviewer'
$patch['metadata_review'] = 'in_progress'
$patch['identifiers'] = $record.document.identifiers
# Edit the full identifiers array, including its evidence, before applying a real correction.
$patch | ConvertTo-Json -Depth 40 | Set-Content local/review.json -Encoding utf8
& $py -m fieldnotes @storeArgs review --file local/review.json
& $py -m fieldnotes @storeArgs export --output local/demo/exports
```

For the real store omit `--output local/demo/exports` to refresh the normal `local/exports`. The template supplies `note_id`, `base_revision` and `base_review`. The last digest binds a correction to the exact prior document, review states and source evidence. Refresh the template and inspect intervening work if the patch is stale. The journal supplies the UTC timestamp. Add a meaningful source/reason and reviewer when available.

- Supply `pages` as an object keyed by the actual image ID. Its value can contain `text`, `status`, or the complete `annotations` array. Replacing page text resets both review states to in_progress unless that same review explicitly sets a state.
- Supply `metadata` as an object keyed by field name. Replace the whole field object, including evidence. Supported fields are collector, language, document_type and physical_hand.
- Supply the complete replacement for any of `entries`, `identifiers`, `taxa`, `localities`, `dates`, `observations`, `notes`, or `translations`. A supplied empty array intentionally clears that field. Omitted arrays retain their prior contents. A supplied `summary` replaces the summary string. Retain unrelated items when correcting one member of an array.
- To approve metadata after checking it, set `metadata_review` to `approved`. Transcription approval is a separate explicit field. Metadata changes reopen metadata review while preserving prior text approval. Changes to image bytes, page order, or selected service revision leave earlier approvals in history for rebasing. Temporary scan unavailability preserves the saved reading and its review.

## Maintain a reviewed identity

Save a staff-prepared JSON object under `local/alias.json`. This invented example illustrates the shape.

```json
{"kind":"taxon","name":"Example marsh bird","rank":"species","aliases":["Example reed bird"],"review_status":"approved","source":"Invented example authority card","reviewer":"Example reviewer"}
```

```powershell
& $py -m fieldnotes alias --file local/alias.json
& $py -m fieldnotes export
& $py -m fieldnotes show --mode species --query 'Example reed bird'
```

Use kind `collector` for people and omit rank. Creation returns a permanent `tax_` or `col_` ID. To revise or withdraw an authority, supply its existing ID, the complete name/alias record, source and `review_status` of approved or withdrawn. An explicit review may also assign `authority_id` to a taxon field of the same rank or the written collector field. All original transcriptions remain in the underlying revisions. Multiple matches are surfaced for review. Approved names can provide suggestions in a later request. They do not establish authorship, handwriting or a species identification by themselves.

## Record two-sided cards

Keep `card-backs.txt` beside the journal in the selected store, normally `local/collection/`. Use a plain UTF-8 text file. Each line names the folder relative to **Field Notes**. For a mixed pile, give the front filename or both exact filenames. For a pile scanned on both sides throughout, use one `all-pairs` line.

```text
Carriker/set1 | IMG_2020_01_02_11_00_10S.jpg
Other collector | separate-front.jpg | verified-back.jpg
Carriker/set2 | all-pairs
```

Blank lines and lines beginning with `#` are fine. Use `/` between folder names. Automatic pairing uses JPEGs from the exact folder and sorts by the full scanner date and time. For example, `IMG_2020_01_02_11_00_10S.jpg` precedes `IMG_2020_01_02_11_00_25S.jpg`. A missing final back leaves that front waiting. An unrecognized filename, tied timestamp, or changed order that would reassign a saved partner requires checking the filenames. Existing three-column entries can specify exact partners regardless of naming or scan order. If a note spans multiple physical cards in an `all-pairs` folder, use an explicit manual group containing all sides in their verified page order.

You can prepare the scanner log while a set is in progress. Once scanning is complete, use `dry-run --input $scans --complete-set 'Carriker/set2'` to preview the pairs, then `inventory` with the same arguments to save them. A routine refresh leaves unadmitted set folders alone. Each pair keeps the front's note ID and the exact order of both images. A back with an existing individual record is retired with its history. The transcription and metadata still have their own review states. Edit or remove a line and rerun inventory to correct the log for saved scans. If the file is absent, the last saved pairs stay available. Back it up with the journal and update its filenames after reconciling moved scans.

## Assemble a note and preserve links

Use `show --note` or `images.csv` to identify exact paths for other multipage notes. JSON group overrides replace the full set of manually defined JSON groups. Include existing manual groups when adding another. Scanner-log pairs are retained separately. Each group needs a persistent key, ordered relative paths with forward slashes, and source/reason. Include an optional reviewer. Without a supplied note ID a new explicit group receives its own stable ID. To keep a particular bookmark, add the existing `note_id` of the note that should continue. The order in `paths` is the page order.

```json
{"version":1,"groups":[{"key":"valley-card","paths":["Carriker/valley.jpg","Carriker/continuation.jpg"],"source":"Invented fixture labels the second page as a continuation","reviewer":"Example reviewer"}]}
```

```powershell
& $py -m fieldnotes group --file local/grouping.json
& $py -m fieldnotes export
```

Unclaimed scans remain individual records. A newly discovered page stays separate until explicitly added. Displaced records are retired and retain their IDs, earlier results and links. Duplicate assignments are rejected. An explicit group spanning folders carries a review reason. Rerunning inventory reuses saved manual groups unless a replacement `--overrides` file is supplied. A changed group or reordered pages requires a new complete reading for the new evidence.

If someone moves a file **outside the application**, supply the old and new paths before inventorying the new path. The old path must be absent, the new file must be an unclaimed JPEG inside the same root, and its bytes must match the saved original SHA-256. Reconciliation leaves the filesystem alone, updates paths and group definitions, and keeps the previous paths and both stable IDs. A filename alone or a matching hash elsewhere never joins records automatically.

```json
{"version":1,"source":"Staff verified an external move of an invented card","paths":{"Carriker/old-card.jpg":"Carriker/renamed-card.jpg"}}
```

```powershell
& $py -m fieldnotes reconcile-paths --file local/paths.json
& $py -m fieldnotes inventory --input 'G:\My Drive\Field Notes'
```

A new inventory without reconciliation retains the old missing record and creates another record at the new location. Already inventoried identities are not silently merged. Replacement bytes at the same path keep the archival IDs but produce a new inventory snapshot, invalidate obsolete approvals, and mark the earlier reading stale. Reusing a previously reconciled path for another scan gives that scan a distinct ID.
