Fix the following issues. The issues can be from different files or can overlap on same lines in one file.

- Verify each finding against the current code and only fix it if needed.

In @islam-intelligent/.sisyphus/drafts/roadmap-milestones-table.md at line 14, Update the assignee field for the "Persiapan & Audit" milestone row (the "Tambah CI minimal (GitHub Actions) untuk jalankan `python scripts/verify_all.py` dan UI tests (Vitest + Playwright)" task) by replacing "unspecified-high" with a specific agent (e.g., "islam-security", "islam-eval", or "devops") to assign clear ownership; ensure the chosen agent string replaces the existing "unspecified-high" token in that table cell so the milestone now shows a concrete responsible party.

- Verify each finding against the current code and only fix it if needed.

In @islam-intelligent/.sisyphus/drafts/roadmap-milestones-table.md at line 24, The RAG response alignment task currently marked "unspecified-high" needs a clear owner: assign the islam-rag or islam-kg agent to take responsibility for updating the `/rag/query` endpoint and enforcing the `rag_answer.json` schema plus citation-first behavior; update the task metadata and PR description to set the chosen agent (islam-rag or islam-kg), ensure they run/update tests for the `/rag/query` route and enforce abstain-on-unresolved-citation logic, and add the assignee to related code review and documentation tasks so ownership is clear.

- Verify each finding against the current code and only fix it if needed.

In @islam-intelligent/.sisyphus/run-continuation/ses_34d8375b3ffeZYwCpdnK5953aU.json around lines 1 - 11, This runtime session file under the .sisyphus run-continuation folder (ses_34d8375b3ffeZYwCpdnK5953aU.json) should not be committed; add an entry for .sisyphus/ to .gitignore, remove the committed runtime file from the repo index (e.g., git rm --cached for the session file or the whole .sisyphus directory), and commit the updated .gitignore and removal so future session files are ignored.

- Verify each finding against the current code and only fix it if needed.

In @islam-intelligent/.sisyphus/run-continuation/ses_352686818ffeQlPPnHDPMf2FO4.json around lines 1 - 10, The session continuation JSON files under .sisyphus/run-continuation/ are runtime artifacts and should be excluded from VCS; add a line ".sisyphus/run-continuation/" to .gitignore, remove any already-committed files with git rm --cached .sisyphus/run-continuation/* (then commit the .gitignore and the removal), and optionally add a note to project docs/README that .sisyphus/run-continuation/ is ignored; verify the file ses_352686818ffeQlPPnHDPMf2FO4.json is no longer tracked after these changes.

- Verify each finding against the current code and only fix it if needed.

In @islam-intelligent/.sisyphus/tasks/T-05db1f94-fa38-45ba-8a02-a5154be6e827.json around lines 6 - 7, The root-level fields "blocks" and "blockedBy" are duplicated and conflict with the values inside "metadata"; remove the ambiguity by deleting the root-level "blocks" and "blockedBy" entries and rely on the authoritative values under "metadata" (or alternatively, move the metadata values up to the root if your schema expects root-level fields); update any code that reads these fields to reference metadata.blocks and metadata.blockedBy (or the chosen canonical location) so the schema is consistent across the T-05db1f94-fa38-45ba-8a02-a5154be6e827 object.

- Verify each finding against the current code and only fix it if needed.

In @islam-intelligent/.sisyphus/tasks/T-18fd286e-ccbc-4b58-8b11-5b6f9fb9be93.json at line 9, The JSON contains a hardcoded session identifier in the "threadID" field (value "ses_351295d1affetrHHEHR5A40vYP"); remove or redact that value by either deleting the "threadID" property, replacing it with a non-sensitive placeholder (e.g. "THREAD_ID_PLACEHOLDER"), or move the real session value into a runtime configuration or environment file that is gitignored; update any code that reads this file to tolerate the missing/placeholder value (look for consumers referencing threadID) and ensure no active session tokens remain in source control.

- Verify each finding against the current code and only fix it if needed.

In @islam-intelligent/.sisyphus/tasks/T-2f1b3cfb-7a3c-4152-90a2-ddce17258c4f.json at line 7, The JSON contains duplicate "blockedBy" fields with conflicting values; remove the empty top-level "blockedBy": [] entry and keep the authoritative "blockedBy": ["M3","M5"] (or, if the empty array is correct, replace the later array with []). Locate the two "blockedBy" keys in the task JSON and ensure only one remains with the correct milestone IDs (M3 and M5) to eliminate ambiguity.

- Verify each finding against the current code and only fix it if needed.

In @islam-intelligent/.sisyphus/tasks/T-36d63b82-2754-4d01-9188-28466894f2dd.json around lines 5 - 6, The JSON task shows an inconsistent state: the "status" key is set to "completed" while the "activeForm" contains an outstanding implementation directive; verify the true task state and either clear or replace "activeForm" with a final summary if the task is actually done, or change "status" from "completed" to an appropriate active state (e.g., "in_progress" or "open") and keep/update "activeForm" to a concrete task description like "Implement citation verification tests..." so both "status" and "activeForm" accurately reflect the task's current progress.

- Verify each finding against the current code and only fix it if needed.

In @islam-intelligent/.sisyphus/tasks/T-3d90f539-bc22-4cdf-abe1-faad4b8c1701.json around lines 5 - 6, The JSON has an inconsistency: the "status" field is "completed" while the "activeForm" field ("Verifying apps/api RAGPipeline implementation exists.") implies an ongoing action; update the "activeForm" value to a past/complete phrasing (for example "Verified apps/api RAGPipeline implementation exists." or "Verification complete: apps/api RAGPipeline implementation exists.") so it matches the "status": "completed" state and keep the change confined to the "activeForm" field.

- Verify each finding against the current code and only fix it if needed.

In @islam-intelligent/.sisyphus/tasks/T-4e9b1847-3329-42c4-b968-969b2c3c2f20.json around lines 6 - 7, The root-level "blocks" array is empty while "metadata.blocks" contains ["M2","M3"], causing inconsistency; move the blocking IDs from "metadata.blocks" into the root-level "blocks" field (i.e., set "blocks": ["M2","M3"]) and remove the duplicate "metadata.blocks" entry (or keep only one canonical location), ensuring the "blocks" and "metadata.blocks" fields are not conflicting and match the project schema.

- Verify each finding against the current code and only fix it if needed.

In @islam-intelligent/.sisyphus/tasks/T-6232d8be-f259-4122-b07e-da2e39e45150.json around lines 6 - 7, Top-level "blocks" and "blockedBy" are empty while metadata contains values, causing inconsistency; update the JSON so there is a single source of truth by copying metadata.blocks and metadata.blockedBy into the top-level "blocks" and "blockedBy" fields (or remove the metadata duplicates and keep only top-level), and ensure the fields "blocks", "blockedBy", "metadata.blocks", and "metadata.blockedBy" are synchronized/removed accordingly so consumers see the same dependency lists.

- Verify each finding against the current code and only fix it if needed.

In @islam-intelligent/.sisyphus/tasks/T-7114cb32-f798-4675-b156-96bbaf2b9266.json at line 11, The threadID value "ses_..." in the task descriptor is a runtime/session identifier and should not be stored in version control; replace the concrete session string in the "threadID" field with a non-sensitive placeholder (e.g., "ses_PLACEHOLDER" or null) and update the code that creates Task descriptors to populate threadID at runtime, or remove the field from committed descriptors and ensure any serialization/deserialization logic (the code that reads/writes the task descriptor) tolerates its absence; if this value must remain in files for tests, mark those files as test fixtures only and document they contain dummy IDs.

- Verify each finding against the current code and only fix it if needed.

In @islam-intelligent/.sisyphus/tasks/T-ccfbac3d-81d5-4fb8-9b56-68f55f8f401a.json around lines 6 - 7, Consolidate the dependency fields by moving the dependency arrays from the metadata object up to the root and removing the duplicate empty root fields: replace the root-level "blocks": [] and "blockedBy": [] with the actual arrays from metadata ("blocks": ["M3","M4"], "blockedBy": ["M1"]) and then delete those two keys from the "metadata" object so "blocks" and "blockedBy" exist only at the root level.

- Verify each finding against the current code and only fix it if needed.

In @islam-intelligent/.sisyphus/tasks/T-f4b5db58-4429-42c3-b96e-d2df24a29879.json around lines 6 - 7, The root-level JSON arrays "blocks" and "blockedBy" are empty but the "metadata" object declares dependencies ("metadata.blockedBy": ["M3","M4"], "metadata.blocks": ["M6"]), causing inconsistent dependency info; fix by either removing the top-level "blocks" and "blockedBy" fields entirely so metadata is authoritative, or update the top-level "blocks" and "blockedBy" to match "metadata.blocks" and "metadata.blockedBy" respectively (ensure you edit the root keys "blocks" and "blockedBy" to contain ["M6"] and ["M3","M4"] if you choose to sync).# Task 30 Remediation Checklist (Realtime)

## Milestone 1 - Discovery and Reproduction
- [x] Parse roadmap/status/remediation docs and identify executable scope.
- [x] Run baseline `python scripts/verify_all.py` and confirm baseline health.
- [x] Run required UI commands and reproduce failure in full e2e run.

## Milestone 2 - Bug Fix and Targeted Validation
- [x] Diagnose WebKit timeout root cause (`Ask` button remained disabled).
- [x] Patch UI form hydration/input readiness in `apps/ui/src/components/QueryForm.tsx`.
- [x] Run targeted validation: WebKit citations e2e spec passes.

## Milestone 3 - Final Mandatory Verification
- [x] Run `python scripts/verify_all.py` and save evidence output.
- [x] Run `npm --prefix apps/ui ci` and save evidence output.
- [x] Run `npm --prefix apps/ui test -- --run` and save evidence output.
- [x] Run `npm --prefix apps/ui run test:e2e` and save evidence output.

## Milestone 4 - Closeout
- [x] Update checklist and status docs with final results.
- [x] Create atomic milestone commits with clear messages.
- [x] Produce final change summary, test results, and residual risks.
