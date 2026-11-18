# Repository instructions

- Read README, docs/PROJECT_HANDOFF.md, relevant code/docs, status and diffs first.
- Preserve local work. No service request, publication, deployment, commit or push
  without task authorization. Routine tests are offline.
- Source scans and sibling repositories are read-only. No runtime sibling imports.
- Keep domain discovery/prompt/schema/review/catalogue separate from provider,
  execution/accounting and storage. Small ordinary modules; no database or plugins.
- Preserve whole notes, exact page order, historical text, uncertainty, raw responses,
  original/submitted hashes, stable IDs, all revisions and append-only human reviews.
- Default Gemini model: gemini-3.5-flash-lite, temperature 1.0, high thinking.
  Never substitute silently. Exactly one execution layer owns retries and accounting.
- Complete does not mean approved. Reviewed names do not identify a hand.
- Use neutral transcription terminology; use Codex only where attribution is needed.
- Keep credentials, stores, quotas, collection data and generated files in ignored local paths.
- Preserve the viewer's verbatim reference.css base style. Document minimal additions.
- Run python -m unittest discover -s test -t . -v and
  node --test apps_script/viewer/test_viewer.cjs after cross-cutting changes.
- Tests and preview use synthetic fixtures in test/inputs. Document limitations honestly.
