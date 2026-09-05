Implementation note: the final package uses eight controls in `mandate/security.py`; any seven-control proposal below is an earlier design alternative.

# Track adaptation review

Updated September 5, 2026. This review treats the newly supplied REGODIT AI Security Analyst brief as the working product requirement. It does not establish organizer endorsement or independently verify event timing. Council perspectives are simulated expert judgments, not interviews or objective ratings.

## Recommendation

Make the primary experience an evidence-grounded security questionnaire for Yari's technology retail business pursuing an enterprise partnership. The product searches its source documents first, answers what the sources support, asks a small number of targeted questions, remembers corrections, and exports an honest questionnaire. Keep one track. The former AP payment workspace can remain a separate optional example of controlled actions; it should not consume the primary demo or be presented as satisfying the security analyst task.

Retain the premium visual system and the useful ideas from the previous build: source lineage, explicit human action, revision history and honest integration status. Replace payment amounts, beneficiary gates and transfer approvals with questionnaire progress, supporting passages, conflicts and unresolved questions. Do not transplant payment-specific Resolve gates merely to make an answer appear certified.

## Council feedback

| Perspective | Challenge to the former AP build | Decision for this adaptation |
|---|---|---|
| Track reviewer | A persuasive bank-change demo does not show an analyst filling a security questionnaire. | Lead with the seven-question review and its export. Demonstrate all required information-handling behaviors in one compact story. |
| Security analyst | Policy describes intended controls, while an internal message may describe exceptions in actual operation. | Show both passages, source kinds and dates. Flag the contradiction and ask who can confirm current scope. Do not automatically declare either source true. |
| Enterprise buyer | A polished “Yes” can conceal a gap or a narrow exception. | Include answer scope, limitations and evidence links. Evidence-backed “No” is a valid result; evidence-backed does not mean secure or compliant. |
| Yari / business owner | A long intake form wastes time and asks things already documented. | Search first. Ask only for unresolved scope or missing facts, explain why the question matters, and allow “I don't know.” |
| Product designer | Confidence percentages imply calibration that the demo does not have. | Separate semantic answer status from support strength. Use passages and explicit limitations, not invented confidence scores or composite security grades. |
| Application security reviewer | Uploaded text can tell the assistant to ignore instructions or invent answers. | Treat documents as untrusted data. Restrict retrieval to the current case, validate source references and keep source text out of executable UI markup. |
| Evaluator | A prepared happy path can hide repeated questions or overwritten corrections. | Run fixed cases for missing information, conflict, a scoped correction and export after restart. Record observed results, including failures. |
| Delivery lead | Payment infrastructure, voice and extra stakeholders can consume the available build window. | Complete the text workflow and export first. Add voice only after acceptance checks pass; leave money operations secondary. |

## Seven-question questionnaire

Use one synthetic business, one partnership request and a small set of versioned documents. The questions below are a proposed demo fixture, not an official REGODIT questionnaire or a complete security assessment.

| ID | Question | Deliberately useful evidence condition |
|---|---|---|
| Q1 | Is MFA required for all privileged access, including exceptions? | Policy says required; an internal message reports a legacy exception. This must create a visible conflict, not an automatic “Yes.” |
| Q2 | Is customer data encrypted in transit and at rest, and what systems are in scope? | Direct evidence supports one portion; missing scope must remain partial rather than expanding to all systems. |
| Q3 | Are backups protected, and when was restoration last tested? | Backup schedule exists, but no restore-test date is supplied. Ask only for the missing restore evidence. |
| Q4 | How are access grants, reviews and employee departures handled? | A procedure gives documented steps. Distinguish documented procedure from proof that every departure followed it. |
| Q5 | Is there an incident-response owner and a documented response process? | A named synthetic owner and policy passage support a bounded answer. Avoid inventing exercises, response times or external certifications. |
| Q6 | How are vulnerabilities tracked and critical patches prioritized? | A user supplies a scoped operational claim after the search finds a gap. Label it user-confirmed until documentary support is supplied. |
| Q7 | Are relevant security events logged, and what retention period applies? | Evidence is absent or contradictory. Keep unknown or request a targeted follow-up instead of estimating a common industry duration. |

The first three questions are sufficient for the spoken demo; all seven must appear in the export. Fixtures should be explicitly synthetic and carry stable document IDs, versions, source type, timestamp and paragraph identifiers.

## Answer semantics and provenance

Every answer needs two separate dimensions:

- **Answer content:** yes, no, partial or unknown, plus a concise scope statement. This describes the control, not the quality of the evidence.
- **Support status:** evidence-backed, user-confirmed or unknown. Evidence-backed requires source passages that actually support the stated claim. User-confirmed records who stated what and when; it never means independently verified. Unknown covers missing information and unresolved contradictions.

An optional support-strength label can be **direct**, **partial** or **absent**, defined by claim coverage. It must not be a probability or a substitute for citations. Represent a conflict as a separate flag with both competing claims and their passages; use unknown for the contested answer until resolved. A documented policy supports “the policy requires MFA,” not automatically “MFA is enforced everywhere.”

If one questionnaire answer mixes supported and unsupported subclaims, split it into subclaims or conservatively mark the combined answer partial/unknown. Do not assign an evidence-backed badge to a paragraph containing a user-only restore-test assertion.

## Required interaction

1. Open the partnership questionnaire. Show the available documents and last search time.
2. Search the sources before generating follow-up questions. Show retrieved excerpts and distinguish no matching text from missing documents.
3. Draft bounded answers. A document that tells the model to ignore the task remains source text, never authority.
4. Ask targeted follow-ups for gaps or contradictions. For Q1, ask whether the legacy privileged account still exists and whether MFA now covers it; do not ask the user to restate the entire security program.
5. Accept a correction such as “MFA covers cloud administrators; the legacy POS admin remains excluded.” Persist its author, time, scope and superseded answer. Mark it user-confirmed and keep the policy conflict visible until appropriately resolved.
6. Reload the page and confirm the correction survives. Re-running document search must not silently overwrite it or ask the identical resolved question again.
7. Export all seven answers with support status, citations, user statements, conflicts and unknowns. Pin the export to source and answer versions; show when later changes make an export stale.

The security analyst may prepare an answer, but the interface should not send it to an enterprise partner without an explicit user action. Exporting a local review artifact is sufficient for the demo.

## Build window and priority

There is an unresolved schedule conflict: the new request describes a six-hour build, while earlier organizer material in this task indicated an 11:00 AM start and 3:30 PM submission lock. Do not treat six hours as permission to miss the earlier deadline. Until the organizer clarifies, plan the required deliverable for the earlier lock and reserve a submission buffer. Preserve exactly one selected track.

| Elapsed time from start | Required deliverable |
|---|---|
| 0–30 minutes | Freeze the seven questions, synthetic source set, status contract and first three demo beats. |
| 30–90 minutes | Implement scoped retrieval, answer/source records and durable correction storage. |
| 90–150 minutes | Implement source-first drafting, missing-information follow-ups, conflict handling and conservative status assignment. |
| 150–195 minutes | Connect the premium UI, persistent revision view and complete questionnaire export. |
| 195–225 minutes | Run behavioral checks, capture a trace if connected, record actual GIDE work and rehearse the story. |
| 225 minutes onward | Freeze and submit before the applicable deadline; retain at least 15 minutes for submission failure. If six hours is confirmed, use the extra time for polish and optional voice. |

If time slips, reduce document formats and visual extras. Do not cut persistence, honest unknowns, citations or the exported statuses: those distinguish this track from a generic chatbot.

## Integrations and evidence

Use the organizer's PRISM Observe → Improve → Prove workflow and the supported SDK/configuration available to the team. Observe actual source retrieval, drafting, follow-up and export events; improve one demonstrated failure; prove the change with the same fixed case before and after. Configuration is not proof of ingestion. Keep trace acceptance, retrieval and evaluation status explicit, and label missing runtime evidence as pending.

GIDE must have an actual development contribution: record the implementation or test it helped produce and the resulting artifact. Do not label it used merely because its name appears in the UI. Neither PRISM nor GIDE has endorsed or certified this application.

ElevenLabs voice is optional. It requires opt-in, a server-held key, visible recording state, a text fallback and user confirmation of the transcript before it changes an answer. Do not infer agreement from audio or silently treat transcription as verified security evidence. Voice failure must leave the text workflow usable.

## Acceptance checklist

- Search precedes follow-up; already-supported questions are not re-asked.
- Answers cite real, current source passages; fabricated or out-of-case citations are rejected.
- Missing restore-test information remains unknown until a user or document supplies it.
- The MFA policy/message contradiction is visible and prevents an unqualified “Yes.”
- A user correction survives restart, retains its provenance and is not upgraded to independent verification.
- Stale writes are rejected or explicitly reconciled; another answer revision is never silently lost.
- The export contains all seven questions, truthful support statuses, limitations, source versions and unresolved items.
- Source text and user comments render as text rather than executable HTML.
- A synthetic/replay mode is visibly distinguished from real model calls and accepted PRISM traces.
- The track, deadline assumption and actual sponsor usage are stated honestly in the submission.
