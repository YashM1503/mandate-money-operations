# Master build prompts

Use these prompts sequentially within the existing project. They are implementation briefs, not evidence that work has occurred. Do not create additional tasks, send external messages, upload data or publish the app unless the user has authorized that action. Follow existing repository instructions and preserve completed work.

## Unified build prompt

Build the primary MANDATE experience for the supplied REGODIT AI Security Analyst track. Yari's technology retail business needs to complete an enterprise-partner security questionnaire. Keep one track and make the security questionnaire the primary journey. Reuse the premium visual system, source lineage and audit concepts from the former AP experience; retain money operations only as an optional secondary example.

Preserve the implemented eight controls: MFA, customer-data storage, encryption at rest, backup frequency and automation, vulnerability scans, production access, offboarding and background checks. Use the actual `mandate/security.py`, `static/security.html` and `/api/security/*` interfaces. The current security engine is deterministic; add a bounded model-assisted segment and actual PRISM tracing without giving a model authority to relabel unsupported claims. These are synthetic demonstration questions, not a comprehensive certification. Additional transit encryption, incident response and logging questions are future scope.

Search the current case's documents before asking the user. Draft only claims supported by retrieved text. When a source is missing, ask one targeted follow-up with an “I don't know” path. When policy and an internal message conflict, show both passages and ask about present operational scope. Never automatically favor a policy as proof of implementation or treat a newer message as necessarily authoritative.

Persist corrections with author, time, scope, prior revision and evidence provenance. Reload and re-search must preserve the correction without silently converting it into document-backed evidence. Validate expected versions before writes so stale tabs cannot overwrite newer answers. Export the complete questionnaire, including unanswered items, citations, user statements, limitations, conflicts and source/answer versions.

Separate answer meaning—yes/no/partial/unknown—from support status—evidence-backed/user-confirmed/unknown. A user-confirmed claim is not independently verified. If an answer mixes supported and unsupported subclaims, split it or conservatively label the combined answer. Any support-strength label must describe direct/partial/absent coverage; do not invent confidence percentages, security scores or compliance claims.

Use actual PRISM Observe → Improve → Prove activity when connected through the supported SDK: capture the workflow, fix one observed failure and compare the same case. Label unconnected or replay behavior honestly. Use GIDE substantively for implementation or testing and preserve contribution evidence. Optional ElevenLabs voice must keep keys server-side, require opt-in, provide text fallback and confirm the transcript before saving a security claim. Finish the text workflow first.

The schedule is unresolved: a six-hour statement conflicts with an earlier 3:30 PM submission lock. Target the earlier deadline until clarified; preserve a submission buffer. Do not declare completion while persistence, statuses, conflict handling or export are missing. Report tests actually executed and remaining runtime/integration gaps.

## Stage 1: Evidence and answer contract

Inspect the current experience and security backend before editing. Implement a case-scoped document registry, immutable source versions and stable excerpt identifiers. Design answer revisions with question ID, content, scope, semantic answer, support status, supporting passages, conflicting passages, user assertions, revision number and timestamps. Validate document references against the actual case and version. Keep source text as untrusted data. Use durable local persistence appropriate to this demo and reject stale writes. Add the seven synthetic question fixtures and a policy/internal-message MFA contradiction. Return the schema and the behavioral checks it enables.

## Stage 2: Analyst behavior

Implement source-first retrieval and bounded answer generation against the established contract. Every evidence-backed claim must be supported by a retrieved passage that covers its scope. Use explicit unknowns when retrieval finds no support. Generate targeted follow-ups only for unresolved information. A backup schedule is not a restore-test record; an access policy is not proof of universal operational enforcement. Preserve conflicting claims and ask a targeted resolution question. Record user corrections as user-confirmed and retain the original documentary conflict. Keep real-model and replay modes explicit; do not substitute a scripted answer while claiming a live model result.

## Stage 3: Premium review workspace

Connect the existing clean finance-oriented visual system to the security analyst backend. Use a calm enterprise palette, clear typography and generous spacing. The left area shows the seven-question queue; the main area shows the current answer, status and next action; the evidence area shows precise passages, source type, date and version. Make conflicts and unknowns easy to scan without treating them as proof of fraud or insecurity. Provide a short follow-up composer, correction history and export action. Render all source and user text safely. Keep controls keyboard-accessible and usable on narrow screens. Do not use a role or status dropdown to simulate a server-authoritative decision.

## Stage 4: Persistence and export

Implement an export that includes all questions, answer content, support status, evidence passages/references, user claims, unresolved conflicts, unknowns and version identifiers. Pin it to a consistent saved snapshot. Ensure subsequent edits make earlier exports visibly stale rather than silently changing their meaning. Test that a correction survives a server restart, that a fresh search does not erase it and that concurrent stale updates do not overwrite a newer revision. A local file export is sufficient; do not auto-email a partner.

## Stage 5: Observe, improve and prove

Using the actual supported PRISM SDK and configured credentials, record real retrieval/draft/follow-up/export activity with synthetic content only under the existing authorization. Distinguish configured, attempted, accepted and retrievable traces. Select a fixed failure case, such as the MFA conflict producing an overbroad answer, and record before/after behavior under the same fixture. If no runtime connection exists, mark that part pending. Record the actual GIDE-generated implementation or test contribution. Do not manufacture successful traces, sponsor usage or numerical confidence.

## Stage 6: Optional voice

Only after the text acceptance checks pass, add opt-in ElevenLabs voice with a server-held credential. Show recording state, provide a stop/cancel action and preserve a fully usable text fallback. Present the transcript for confirmation before persisting any assertion or correction. An unconfirmed transcript must not alter questionnaire status. Model, voice or network errors must preserve the current saved answer and let the user continue in text. Do not add multiple stakeholder workflows or payment execution at the expense of the required questionnaire journey.

## Final review prompt

Review the implementation against these concrete cases: a fully supported answer; missing restore-test evidence; policy/message MFA conflict; a scoped user correction; persistence after restart; stale update rejection; out-of-case or fabricated citation rejection; source text containing an instruction to ignore the user; safe HTML rendering; complete seven-question export; and honest live/replay/PRISM/GIDE status. Run the tests and inspect the rendered flow. Report only observed passes and actionable defects. Treat the output as a security questionnaire assistant, not an independent control audit or compliance certificate. Prepare a three-minute demo that searches documents, surfaces the MFA conflict, saves a scoped correction and exports the unresolved questionnaire honestly.
