# Offline verification

Use the same environment as the CLI. The core suite creates synthetic JPEGs, mock service responses, and temporary stores under ignored `local/test-tmp/`. Unit tests block outbound socket connections. The SDK transport test uses `httpx.MockTransport` to inspect actual request serialization and verify that a 503 produces one SDK attempt. Node uses local Apps Script and DOM adapters. No suite requires a service key or an online deployment.

```powershell
Set-Location 'C:\Users\x5769\Documents\GitHub\museum-field-note-transcriber'
$py = '.\.venv\Scripts\python.exe'
& $py -m unittest discover -s test -t . -v
node --test apps_script/viewer/test_viewer.cjs
```

The mounted-collection check skips explicitly unless opted in. To include it, set the root before running the Python suite or run just that test. It enumerates the current Carriker JPEGs, compares original hashes, sizes and decoded dimensions, inspects representative unmodified request bytes, and rechecks source hashes. It has no hard-coded inventory count. The Python-to-Apps-Script export test skips if Node is unavailable.

```powershell
$env:FIELDNOTES_TEST_ROOT = 'G:\My Drive\Field Notes'
& $py -m unittest test.test_collection_integration -v
Remove-Item Env:FIELDNOTES_TEST_ROOT
```

| Area | What is exercised |
| --- | --- |
| Inventory and preparation | Case-insensitive JPEGs, damaged/missing/duplicate items, unsupported files, grouping, moved paths, reuse of a reconciled path, source changes, EXIF orientation, image limits and no omitted pages. |
| Reading and review | Multiple passages and numbers, absent species, symbols and edits, alternative taxa, supported precision, invalid and dangling evidence, failure preservation, independent approvals, stale reviews, reviewed authorities and profile isolation. |
| Execution and storage | Real SDK with local HTTP responses, bounded retries, pause/stop conditions, quota persistence and process contention, interrupted-attempt recovery, partial output, failure after checkpoint, 48-hour selection, old pending continuation, fresh revisions and unknown usage. |
| Export and publication | Offline regeneration, quoted Unicode CSV, formula handling, output-name collisions, ownership, archives, interruption recovery, overlapping paths and safe scan exclusion. Publication tests use temporary synthetic destinations only. |
| Apps Script | CSS/embedded-client fidelity, collector expansion and activity ordering, search, context navigation, two-page scans, safe text, restrictions and public filtering, absent/duplicate paths, changed file/export bytes, stale requests and bounded error handling. A Python-produced complete export is also consumed directly by the actual Apps Script functions. |

## Browser comparison

Build the invented fixture with `& $py scripts/make_demo.py`. For a synthetic viewer preview run `node scripts/preview.cjs`. The optional comparison takes a local copy of the reference **HTML template only** as its argument. No reference repository is needed for normal tests or preview. Keep any comparison copy under ignored `local/`.

```powershell
# First PowerShell window, from the repository root:
node scripts/preview.cjs local/reference-baseline/Viewer.html
# Second window, with Playwright resolvable by Node and Edge installed:
node scripts/check_layout.cjs
```

For the optional browser harness, use an installed Playwright package through Node's module resolution or set `NODE_PATH` to the directory that contains it. Verification used Playwright 1.62.1 and Edge 157.0.4341.60. The browser channel defaults to `msedge` and can be set with `FIELDNOTES_BROWSER_CHANNEL`. This is a QA dependency only. The harness prevents external page requests. It opens the reference and field-note templates with the same synthetic card data, checks common computed styles, measures both real page panels at 1365 × 950 and 390 × 844, and exercises enlargement, return, species filtering, Search and Show all. PNGs and numeric measurements go into `local/visual-check/`. Stop the local server with Ctrl+C.

The [handoff](PROJECT_HANDOFF.md) records the dated results, observed scan count and interpretation limits. Browser fixtures exercise a local rendering of the templates. Live Apps Script authorization, Drive sync and item visibility require a separately authorized deployment check.
