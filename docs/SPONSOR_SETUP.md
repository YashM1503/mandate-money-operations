# Mandatory tools: setup and evidence of use

Prepared 5 September 2026. The supplied organizer messages require both PRISM and GIDE. This repository contains pinned prismtrace-sdk 0.4.2 integration and an optional PRISM HTTP adapter and an optional live advisory model path. Implementation and mocked tests do **not** establish live sponsor usage. GIDE development work and actual PRISM project evidence remain operator tasks until completed and recorded. No sponsor affiliation or endorsement is claimed.

## Configure once, retain both local and cloud options

The same Python application can run locally or behind a cloud HTTPS ingress. Keep server keys in environment secrets; never embed them in HTML or a committed environment file. Start with synthetic fixtures only. Live integrations require:

| Variable | Meaning |
|---|---|
| `MANDATE_ALLOW_SYNTHETIC_EGRESS=1` | Explicitly permits sending allowlisted synthetic metadata to the chosen model and PRISM |
| `MANDATE_MODEL_URL` | Full HTTPS chat-completions endpoint; no query-string keys, user-info or fragments |
| `MANDATE_MODEL_KEY` | Provider credential, server-only |
| `MANDATE_MODEL_NAME` | Model supported by that provider and account; no guessed default |
| `PRISMTRACE_HOST` | Defaults to `https://prism.blockconvey.com`; if changed must be an HTTPS origin |
| `PRISMTRACE_PROJECT_ID` | Project ID copied from PRISM project settings |
| `PRISMTRACE_API_KEY` | Project-scoped ingest key; diagnostic access may need additional read permission |

Unset the egress flag to use the local deterministic replay without external requests. The app does not load `.env` automatically: use the repository's documented launch/deployment mechanism or export variables in the shell. Never paste secrets into code-assistant prompts.

The portable adapter uses the common chat-completions request shape: `model`, `messages`, `stream:false`; it reads `choices[0].message.content`. The model must return a JSON object with exactly `summary` and `cited_evidence_ids`. It uses no provider-specific tool-calling or JSON-schema extension, so compatibility must be established against the actual endpoint. See the [official chat-completions API reference](https://developers.openai.com/api/reference/cli/resources/chat/subresources/completions). A provider with a different API needs a dedicated tested adapter.

## What the investigator receives

Only opaque evidence references, parent relationships, selected typed control metadata, deterministic disposition, and recognized gate names/values leave the application. Vendor names, account tokens, document contents, freeform evidence text, credentials, approver identities, and human comments are excluded. Original evidence identifiers are mapped to `E1`, `E2`, and so on; validated citations are mapped back locally. Session IDs are stable hashes of case IDs. Do not put personal data or secret values into IDs or permitted numeric metadata.

This bounds the advisory model's role: it explains the control assessment. It does **not** perform invoice OCR, independently validate a vendor's bank details, detect prompt injection in raw invoices, or discover off-platform facts. Raw-invoice adversarial evaluations require a separate isolated ingestion design. Never claim those capabilities from the present tests.

## PRISM proof sequence

1. Create the event project and an ingest key in PRISM. Configure the variables above, including the synthetic egress opt-in and a working model endpoint.
2. Run `python -m mandate.integrations` from the repository root. Before real traffic, model status may be `configured_unverified` and PRISM `pending`; those are not passing checks.
3. Start the application and investigate a seeded case through its authenticated UI. `live_advisory` establishes that a response passed the local schema and citation checks. `prism_status: submitted_unverified` is the default SDK outcome because its public method returns no ingest receipt. With MANDATE_PRISM_TRANSPORT=http, accepted establishes HTTP 200 plus stored trace identity. Neither proves dashboard analysis completed.
4. Run `python -m mandate.integrations --verify-prism`. This performs a read-only `GET /api/setup-doctor?project_id=...`; it does not manufacture usage. A project-level `live_connected:true` may refer to another application. Correlate the precise returned local `trace_id`, opaque case session, model name, agent `mandate-investigator`, and timestamp in PRISM's dashboard.
5. Save a **redacted** screenshot/export and date, project label, commit SHA, trace ID, tested case, operator, and outcome in a manually reviewed build evidence record. Keep keys and sensitive account details out. Confirm the intended model exchange and current build are visible. Repeat for a held case and a normal case.
6. Inspect PRISM's evaluations/flags and retain at least one meaningful finding, remediation or comparison. Do not invent a score or say the trace was analyzed merely because ingest returned 200. The current HTTP adapter does not retrieve automated scores.

HTTP sends the actual bounded input messages and returned model text after the response. Invalid model JSON is discarded by the product but traced with `output_schema_valid:false`. Known configured credentials are redacted if echoed. Invalid or oversized model transport responses are not represented as successful exchanges. There is no manufactured model trace in replay mode.

PRISM distinguishes HTTP/SDK flagging after a response from the proxy's inline model guardrails. Its wider evaluations and remediation overlap with parts of a decision-contract narrative. Mandate's distinct boundary is evidence-origin independence plus exact transaction authorization and execution verification. The present HTTP integration supplies model-exchange observability; it is not the payment gate. See [PRISM documentation](https://blockconvey.com/docs).

The direct synchronous adapter intentionally awaits trace delivery, with a 15-second HTTPX timeout per phase, so the returned status reflects the observed ingest result. Model plus trace can add latency; the API must run this outside write transactions. HTTPX phase timeouts are not a strict total wall-clock deadline. A production service should use a durable transactional outbox, retry by the same trace ID, per-host egress policy and bounded total deadlines; these are outside this four-hour demo.

## GIDE: genuine development usage

No GIDE work is claimed by the checked-in code. Obtain the event's current product access and instructions through the organizer product channel. Use the actual GIDE product to make a useful code change, inspect its diff, run the relevant tests, and retain evidence. Do not substitute Cursor, Claude, ChatGPT, or a fabricated integration badge for this requirement.

A bounded GIDE work item is provided in `PARALLEL_BUILD_PROMPTS.md`: add or improve an integration validation test, then improve the sponsor-status explanation without changing control logic. Record the GIDE workspace/session reference or screenshot, task prompt, actual modified files, resulting diff/commit, command and test output, operator, timestamp, and a short explanation of the product's contribution. If event organizers require runtime GIDE use rather than development use, obtain that clarification and adapt to their supported API before claiming compliance.

The API intentionally reports `gide: usage_pending` rather than trusting an environment flag as proof. A manually reviewed external evidence record can establish usage for the submission without letting a Boolean setting impersonate verification. A future UI may show “development usage documented” only when it links to reviewed evidence; it must not imply runtime connectivity.

## Deployment dependencies and failures

| Situation | Local plan | Cloud plan |
|---|---|---|
| No sponsor credentials | Replay and core controls still run; live requirement remains open | Deploy only with explicit replay disclosure |
| Working model, PRISM unavailable | Advisory works; report trace error and retain test evidence | Same; do not show PRISM connected |
| No usable GIDE access | Continue independent implementation, obtain organizer access | Same; hosting does not satisfy GIDE use |
| Host undecided | Run API and UI together on loopback | Use one private service, HTTPS ingress, persistent data volume and secrets |
| Ephemeral serverless filesystem | Local SQLite is suitable for a single instance demo | Choose a persistent-volume host or implement and test a transactional database adapter before moving |
| Several replicas | Single worker simplifies honest status and SQLite ownership | Do not scale horizontally before shared database, identity and integration-status design |
| Real financial data requested | Stop using demo egress assumptions and review data contracts/access | Add institutional requirements, vendor review, retention, encryption and incident operations before real data |

Status observations in this module are worker-local and reset on restart. They are operational hints, not a durable attestation or deployment certification. Mandatory-use acceptance and organizer rules (including prebuilt code) require organizer confirmation. Keep a local demo backup even if cloud hosting becomes available.

## Event promotion and SDK update

The supplied organizer post provides MONEYTALKS#1 for Builder plus 100 credits. Type it into the billing code field, not a URL. SDK 0.4.2 is pinned in requirements.lock; the actual investigator invokes its public trace_llm method and flushes by default. Set MANDATE_PRISM_TRANSPORT=http only if choosing the documented alternative. No promotion has been redeemed and no live sponsor run has been claimed. See QUALIFICATION_AND_DEMO.md for rule uncertainties and mixed-editor workflow.
