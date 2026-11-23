# Offline verification

Use the same environment as the CLI. The core suite creates synthetic JPEGs, mock service responses, and temporary stores under ignored `local/test-tmp/`. Unit tests block outbound socket connections. The SDK transport test uses `httpx.MockTransport` to inspect actual request serialization and verify that a 503 produces one SDK attempt. Node uses local Apps Script and DOM adapters. No suite requires a service key or an online deployment.

```powershell
Set-Location 'C:\Users\x5769\Documents\GitHub\museum-field-note-transcriber'
$py = '.\.venv\Scripts\python.exe'
& $py -m unittest discover -s test -t . -v
node --test apps_script/viewer/test_viewer.cjs
```

The mounted-collection check takes the root and the exact completed set to inspect. It compares original hashes, sizes and decoded dimensions in that folder, inspects representative unmodified request bytes, and rechecks source hashes. It skips when either setting is absent. It has no hard-coded inventory count. The Python-to-Apps-Script export test skips if Node is unavailable.

```powershell
$env:FIELDNOTES_TEST_ROOT = 'G:\My Drive\Field Notes'
$env:FIELDNOTES_TEST_SET = 'Carriker/set2'
& $py -m unittest test.test_collection_integration -v
Remove-Item Env:FIELDNOTES_TEST_ROOT, Env:FIELDNOTES_TEST_SET
```

| Area | What is exercised |
| --- | --- |
| Inventory and preparation | Case-insensitive JPEGs, damaged/missing/duplicate items, unsupported files, grouping, moved paths, reuse of a reconciled path, source changes, EXIF orientation, image limits and no omitted pages. |
| Reading and review | Multiple passages and numbers, absent species, symbols and edits, alternative taxa, supported precision, invalid and dangling evidence, failure preservation, independent approvals, stale reviews, reviewed authorities and profile isolation. |
| Execution and storage | Real SDK with local HTTP responses, bounded retries, pause/stop conditions, quota persistence and process contention, interrupted-attempt recovery, partial output, failure after checkpoint, 48-hour selection, old pending continuation, fresh revisions and unknown usage. |
| Export and publication | Offline regeneration, quoted Unicode CSV, formula handling, output-name collisions, ownership, archives, interruption recovery, overlapping paths and safe scan exclusion. Publication tests use temporary synthetic destinations only. |
| Apps Script | CSS/embedded-client fidelity, collector expansion and activity ordering, search, context navigation, two-page scans, safe text, restrictions and public filtering, absent/duplicate paths, changed file/export bytes, stale requests and bounded error handling. A Python-produced complete export is also consumed directly by the actual Apps Script functions. |

## Browser comparison

Build invented cards from `test/inputs/demo.json` and start the loopback preview. In another PowerShell window, run the comparison with Playwright resolvable by Node and Microsoft Edge installed.

```powershell
& $py scripts/make_demo.py
node scripts/preview.cjs
# In a second window, pass a read-only copy of the current website's dist directory:
node scripts/check_layout.cjs ../ericlaslo-website/dist
```

The harness serves synthetic catalogue and JPEG responses to the actual website Correspondence HTML, JavaScript and shared CSS. It compares computed reader styles and scan columns at 1365 and 390 CSS pixels, then checks enlargement, page navigation, Back, identifier filtering and range highlighting. Measurements and synthetic screenshots go under `local/visual-check/`. The website files are an optional comparison input. Routine tests and preview run independently.

The Python suite also runs the Apps Script resolver with a generated archive of **10,000 two-page cards**. It checks the exact index reads for home and set browsing, bounded search reads, duplicate identifiers, leading zeros, search scope, cross-page neighbors, individual scan links, lost access, stale data and zero JPEG reads on listing. The managed publisher tests check unchanged bytes, external edits, original-byte verification and interrupted replacement. These checks measure local behavior. Live Drive latency, authentication and quota behavior require a deployed viewer.
