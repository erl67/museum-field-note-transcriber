# Museum field notes

Staff can inventory scanned cards, transcribe selected notes, correct readings, and browse a collection by collector, species or collection number. Start with the JPEGs in the collector folders. An existing spreadsheet is optional.

Each ordinary card starts as one provisional note. A recorded front and back become two ordered pages of the same note. A note keeps its ID even when its species or numbers change. One page can describe several specimens at different places. Each number and locality can point to its own passage in the complete page transcription. Missing species and undated notes stay in the catalogue.

## Start in PowerShell

Use Python 3.12 or newer. The tested environment used Python 3.14.2 and Node 24.22.1. Node is needed for viewer tests and the synthetic preview. Run commands from this checkout. PowerShell 7 is recommended for Unicode text through pipelines.

```powershell
Set-Location 'C:\Users\x5769\Documents\GitHub\museum-field-note-transcriber'
if (-not (Test-Path '.venv\Scripts\python.exe')) { python -m venv .venv }
$py = '.\.venv\Scripts\python.exe'
& $py -m pip install -r requirements.txt
$env:PYTHONUTF8 = '1'
$scans = 'G:\My Drive\Field Notes'
# Once scanning is finished for this set:
& $py -m fieldnotes dry-run --input $scans --complete-set 'Carriker/set1'
& $py -m fieldnotes inventory --input $scans --complete-set 'Carriker/set1'
& $py -m fieldnotes show --collector Carriker
```

The dry run reads the selected scans, builds complete requests in memory, and prints readiness. It needs no key and creates no journal, lock, quota reservation or report. Inventory saves stable IDs, relative paths, original hashes, dimensions, and issues under `local/collection`. It also writes one readable report per note and a spreadsheet catalogue under `local/exports`. Both operations open originals for reading only. To retain the identity of an externally moved inventoried scan, reconcile its path **before** inventorying its new location. See [grouping and path changes](docs/review.md).

## Scan a pile of cards

Give each pile its own folder under the collector, such as `Carriker/set1` and `Carriker/set2`. Keep the input root at **Field Notes**. While a pile is in progress you can inspect, delete or rescan its draft images. When the pile is complete, use `inventory --input $scans --complete-set 'Carriker/set2'` to admit its final files. An ordinary inventory refresh checks previously saved set members and picks up loose files directly under the root or a collector. Use `--complete-set` again to admit later additions to a finished pile.

In a mixed pile such as `Carriker/set1`, scan a two-sided card front first, then back. Record just the front filename in `local/collection/card-backs.txt`. The app finds the next JPEG in that folder using the timestamp in its scanner filename. Single-sided cards need no entry.

```text
Carriker/set1 | IMG_2020_01_02_11_00_10S.jpg
Carriker/set2 | all-pairs
```

The `all-pairs` line configures the whole second pile. Scan every card into `Carriker/set2` front first, followed by its back, even when blank. Inventory pairs scans 1–2, 3–4, and so on. A final front waits for its back before transcription. A dry run previews the grouping. Inventory saves it and keeps the front's note ID. You can still specify both filenames for exceptions. [Scanner log and grouping details](docs/review.md#record-two-sided-cards)

## Find and read a note

```powershell
& $py -m fieldnotes show --mode species --sort species
& $py -m fieldnotes show --set 'Carriker/set1'
& $py -m fieldnotes show --mode species --collector Carriker --query 'March'
& $py -m fieldnotes show --query '0012'
$listing = & $py -m fieldnotes show --collector Carriker | ConvertFrom-Json
$note = $listing.records[0].note_id
& $py -m fieldnotes show --note $note
& $py -m fieldnotes export
```

Choose the intended row before using its ID for transcription. The examples use the first listed note for inspection. The collection number and species appear after a reading supplies them. Folder names are provisional collector attribution. Search covers every number, source name, approved alias, locality, date text, and saved transcription. Number order has no chronological meaning. The same number can occur in different collector folders.

A digits-only catalogue search finds each card carrying that identifier, including members of a written range. For example, `8420` matches both `8419-20` and `8410-8430`.

Open `local/exports/catalogue.csv` to browse all records. Import identifiers as **Text** to retain leading zeros. Open `local/exports/combined.txt` to read the collection in one file. For a single card, use `local/exports/readable/<note_id>.txt` or `details/<note_id>.txt` for the evidence and provenance. Rebuild the reports and viewer JSON with `export`, even when the scan drive is disconnected. See [outputs and publication](docs/outputs.md).

## Transcribe when authorized

An authorized transcription sends the selected images, prompt, folder/filename hints, approved name context and any selected handwriting profile to Gemini. These requests can incur charges. Put your `GEMINI_API_KEY` assignment in the project's private `.env` file. The CLI reads it automatically when run from this checkout. The defaults use `gemini-3.5-flash-lite`, temperature `1.0`, high thinking, one request per minute, and a daily limit of 500 attempts. See [configuration and credentials](docs/configuration.md).

```powershell
# Choose one command for the intended scope.
& $py -m fieldnotes transcribe --note $note
& $py -m fieldnotes transcribe --pending --collector Carriker
& $py -m fieldnotes transcribe --pending --set 'Carriker/set1'
& $py -m fieldnotes transcribe --collector Carriker
& $py -m fieldnotes transcribe --number '0012' --collector Carriker
& $py -m fieldnotes transcribe --all
& $py -m fieldnotes transcribe --note $note --fresh
& $py -m fieldnotes usage --run latest
& $py -m fieldnotes usage
```

Use **`--pending` to continue** after a pause. It skips current complete records of any age. A regular selection can reuse a complete exact request for 48 hours. An older regular selection or an explicit `--fresh` can spend again. A failed export can be rebuilt with `export` after the result has been saved. An unknown interrupted service outcome needs inspection before an explicit retry. See [reading and rerunning](docs/transcription.md).

Cards are processed by collector folder, then set (`set1`, `set2`, …), then scan filename. Your scanner filenames contain the date and time, so each pile runs chronologically. A front/back pair takes the front scan's position and keeps both sides together. Other filenames use natural order, such as `card2` before `card10`.

Count one initial request per card, including a card with two scans. Retries and format corrections each use another attempt. The default daily limit is 500 attempts per Pacific day, matching the operator's specified allocation. At the cap the batch saves its progress and stops. Rerun the same `--pending` selection after midnight Pacific to continue.

For temporary service errors such as HTTP 503, the default allows five attempts per card with waits of approximately 1, 2, 4 and 8 minutes. The CLI reports progress during those waits. Persistent service errors still stop the batch after that budget; saved cards remain complete. The final summary shows reported token subtotals even when failed requests supplied no counts. A JSON `null` means unknown, including costs without configured prices.

## Correct and share readings

The saved service result, human corrections, and review decisions have separate histories. Completing a reading leaves metadata and transcription unreviewed. A correction updates titles and browse groups when reports are regenerated. Staff can approve a number while leaving the page text under review.

```powershell
& $py -m fieldnotes review-template --note $note | Set-Content local/review.json -Encoding utf8
# Edit local/review.json against the scans before applying it.
& $py -m fieldnotes review --file local/review.json
& $py -m fieldnotes alias --file local/alias.json
& $py -m fieldnotes group --file local/grouping.json
& $py -m fieldnotes reconcile-paths --file local/paths.json
& $py -m fieldnotes export
```

These are independent operations, each using a staff-prepared file. The review guide gives working file shapes, replacement rules and examples. [Human review, aliases and grouping](docs/review.md) · [Transcription record schema](docs/schema.md) · [Handwriting profiles](docs/handwriting.md)

## Website reader

Field notes will appear on the birds website alongside the egg-slip and correspondence readers. Work on the website reader is deferred while transcription continues. For now, use the local catalogue and reading files above to browse actual notes.

The earlier Apps Script prototype remains available for an offline preview with invented cards.

```powershell
& $py scripts/make_demo.py
node scripts/preview.cjs
```

Open [the local synthetic preview](http://127.0.0.1:8783/) while the command is running. Press Ctrl+C to stop it. See the [prototype notes](apps_script/viewer/README.md) and [guide to local exports and managed working copies](docs/outputs.md).

For maintainers, see [offline tests and visual checks](docs/testing.md) and [project handoff, origins and collection inspection](docs/PROJECT_HANDOFF.md).
