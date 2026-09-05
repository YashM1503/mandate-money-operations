# Mandate MVP technical specification

## 1 Purpose and delivery boundary

Mandate controls a proposed supplier payment before a simulated financial effect. The distinguishing failure is evidence laundering: an agent writes unverified bank details into an internal record, then treats that record as independent confirmation. Mandate preserves ancestry, checks independent beneficiary authority, binds human approval to exact intent and context, and admits one matching effect through a server transaction.

The delivered source implements an authenticated API, unified HTML interface, synthetic persona fixtures, deterministic permission checks, optional advisory model integration, mandatory PRISM SDK integration, journal export and automated QA. The package runs locally. Container and cloud configurations are prepared; their deployment needs verification on the selected host. Live model and PRISM calls need operator credentials and explicit synthetic egress. Actual GIDE development use must be recorded separately. These remaining release gates are not inferred from code or mocked tests.

No real financial account or payment network is connected. An attestation records a demo analyst's claim; it does not prove a real supplier callback occurred. Audit authenticity and factual truth are separate properties. The system is a single-organization demonstration, not a banking compliance certification or a fraud probability model.

## 2 Persona and financial workflow

The deck describes Yari, a growing retail business owner. For the demonstration, $47 million means assumed annual revenue in USD. The claim is improved control and review capacity, not a proven reduction from five finance staff to two. Yari maps to the controller role; a separate analyst verifies exceptions and an auditor inspects records. The three accounts demonstrate role separation but are not substitutes for individual enterprise identities.

Northstar Packaging proposes $8,240 with matching invoice, purchase order, acceptance and approved onboarding. Atlas Maintenance proposes $47,850 with bank token 4831 changed to 9924 through a request, extraction and agent-written master. Forma Fixtures proposes $18,500 with two records derived from one source. Kite Logistics proposes $4,800 using established onboarding. These are fictional cases. The complete initial queue is $79,390.

Initial cash is $90,000. Seven-day commitments are $30,000, comprising $20,000 payroll and $10,000 rent and utilities. A further $10,000 reserve leaves $50,000 available. This is a conservative aggregate snapshot, not a time-stepped cash forecast. Cash is dated at initialization and must be no more than 24 hours old. Paying Atlas leaves $2,150 available; later larger payments should then fail policy. Run the routine Northstar path in a fresh demo if showing both outcomes independently.

## 3 Architecture and responsibility boundaries

The architecture is a bounded orchestrator. It reads stored evidence, derives deterministic controls, optionally requests one model explanation, validates the explanation's schema and citations, then records the investigation. The model has no approval, verification, vendor-write or payment tool. It explains typed provenance and control facts; it does not perform OCR or autonomous raw-document reasoning. Raw-invoice ingestion and tool-selecting research agents are explicitly later segments, with their own tests and permissions.

The server supplies the trusted policy and source registry. An analyst adds a verification attestation through an allowlisted established contact. A separate controller approves the exact decision. The effect executor re-evaluates inside a SQLite write transaction, validates and consumes authority, inserts one ledger entry, reads it back, updates cash and journals the result. No network call occurs inside this transaction.

A second language model would not establish independent evidence. It could repeat the same source error. The independent components here are domain checks, a distinct authorized human, and persisted-effect inspection. Future specialized agents should get bounded read tools and typed outputs; the effect executor must remain outside their direct tool set. JPMorgan, Mastercard and Visa sources support explicit identity, intent, policy and traceability boundaries; they do not prescribe this exact topology or endorse the implementation.

## 4 Source layout and reuse

mandate/api.py defines validated request models, authentication, routes and the effect transaction. mandate/store.py defines SQLite persistence, signed cash snapshots, per-case journal linkage, anchors and ledger reconciliation. mandate/controls.py supplies finance policy, evidence lineage and the adapter to reused permission primitives. mandate/fixtures.py generates reproducible synthetic cases with fresh timestamps. mandate/integrations.py implements advisory inference, egress controls, PRISM and diagnostics. static/index.html is the complete UI with inline CSS and JavaScript and no remote assets.

The four modules in mandate/core are copied unchanged from Resolve commit 87169fe1131fa2903fdcad7324e828ebd4c0885e. Their existing permission, approval and journal semantics are retained, with Apache attribution. Mandate's surrounding modules and interface adapt them to the accounts-payable structure. Do not copy Resolve's older mock runtime or automatic human-approval path. This is reused work and must be disclosed to the hackathon organizer.

The tests directory contains API, integration, concurrency, tampering and evaluation checks. scripts/run_evaluation.py writes the constructed comparison report. sample-data contains readable JSON and CSV fixtures. docs contains research, sponsor setup, deployment, master prompts and QA results. docs/openapi.json is generated from the actual application and is authoritative for exact request and response types.

## 5 Data contracts and provenance

A payment case contains id, vendor, invoice_id, integer amount_minor, currency, destination, original_destination, version, state, evidence, bank_evidence_ids, trusted_contact, verification, approval, investigation and ledger. USD minor units are cents. Destination values are fictional bank tokens, never routable accounts. Input mutation accepts only bank followed by a colon and four digits.

Each evidence record has an id, label, kind, JSON content, parent IDs, actor, source, created_at and sha256. The hash covers every record field except the hash itself, including attribution and ancestry. The persisted server journal protects the case snapshot containing these records. Duplicate IDs, missing parents, cycles and content-hash mismatches fail closed. Copying or forwarding an item preserves its parent, so a hundred copies still contribute one origin root. Root count is explanatory metadata, not a trust probability.

Beneficiary authorization depends on roots in bank_evidence_ids, not unrelated invoice roots. Trusted onboarding has an explicit source and authorized actor. Changed-beneficiary verification is added only by the analyst route, from the established contact and exact destination. It expires after 24 hours. Neither a model-created record nor a caller-supplied label can create an independent verification through the API. A demo administrator controlling the database and signing key is outside this trust boundary.

A decision envelope binds case policy, candidate, evidence registry, relevant state and resulting permission. The candidate contains action_type, vendor target, invoice ID, destination token, amount and currency. Relevant state contains intent version, dated cash, policy version and attestation. Currency, destination, amount, evidence or cash changes therefore cannot silently reuse the previous approval. Case, evidence and candidate fingerprints are preserved in exports.

## 6 Controls and Resolve adaptation

The intent gate checks the authorized accounts-payable objective. Evidence requires invoice, purchase order, delivery acceptance, onboarding and independent beneficiary authorization. Constraints enforce source integrity, matching amounts and identifiers, USD, positive integer value, duplicate-payment prevention and the available-cash floor. Policy caps a single simulated payment at $50,000.

The consequence gate uses C2 for the simulated transfer. Reversibility means an explicit compensating entry in this local ledger; it says nothing about recalling real bank funds. The rehearsal gate evaluates the deterministic checks before execution. Authority requires the controller role, with an independently performed exception check. The verification gate means a feasible persisted-effect inspection plan; it is separate from beneficiary verification.

The reused internal dispositions are BLOCKED, MORE_EVIDENCE_REQUIRED, WAITING_HUMAN and ADMISSIBLE. The UI says Blocked, Hold and Ready for approval. WAITING_HUMAN remains the correct pre-effect result even when an external exact grant has been issued; the grant is validated separately. Missing independent evidence cannot be overridden by a high model confidence score. Source integrity errors are failures, not successful empty graphs.

The controller's approval request contains the displayed decision fingerprint, not only the case version. A different case spending cash changes this fingerprint; the controller must review again. The server stores an HMAC-protected grant with exact bindings, controller identity, nonce, five-minute lifetime and use status. Revocation is an explicit journaled operation. Renewal is a new controller action after fresh checks.

## 7 API and atomic execution

All business routes require a server-validated bearer session. POST /api/login accepts username and password and returns a one-hour token. POST /api/logout revokes it. GET /api/cases returns the queue, cash and integration status. GET /api/cases/{id} returns the case and current decision. The analyst and controller may POST /investigate under a case; auditors are read-only.

POST /api/cases/{id}/verify requires version, destination, established contact_id and a 12-to-1000-character note; only the analyst may use it. POST /approve requires version and the 64-hex displayed decision_fingerprint; only the controller may use it. POST /revoke requires version and an eight-to-1000-character reason. POST /mutate requires version and a new synthetic destination and is a visibly labeled analyst stress-test route. These endpoints do not operate a real ERP.

POST /execute requires version and an idempotency_key of 16 to 80 permitted characters. BEGIN IMMEDIATE serializes writers. The transaction verifies journal and snapshot integrity, current control state, grant signature, bindings, expiry, revocation and unused authority. It inserts a ledger row with unique case and vendor-invoice identity, stores the idempotency receipt, reads back the exact effect, debits available cash, consumes the grant and appends the signed event. An exception rolls back the whole operation.

A retry with the same key and request returns the existing exact ledger entry. The same key with another case or version conflicts. A new key cannot pay an already released case. Persisted ledger identity and contents are reconciled against the authenticated case before replay, compensation or export. POST /compensate credits one simulated debit once and preserves the original invoice in deduplication history. Real external-effect delivery would need a provider adapter and asynchronous reconciliation; no claim of distributed exactly-once execution is made.

GET /api/export/{id} downloads an authenticated evidence package. GET /api/metrics returns observed counts and denominators. /healthz exposes liveness without case data; /docs provides the interactive OpenAPI reference. Exact schemas and validation errors are in openapi.json. Do not infer capability from a successful HTTP response alone; inspect the resulting decision or ledger record.

## 8 Authentication storage and verification limits

Bootstrap creates separate random credentials, salts, PBKDF2-SHA256 hashes with 600,000 iterations and a signing key in owner-readable files. There is no default password, registration route or browser-selected role. Tokens are stored hashed in SQLite and only in browser memory. The login route limits attempts per connection IP. Cloud ingress must apply its own rate limit; forwarded headers are not blindly trusted.

Request models forbid extra fields, reject booleans as versions, constrain strings and enforce a 16 KiB request cap. Database statements are parameterized. The interface escapes dynamic text, loads no third-party scripts, disables actions while requests are pending and keeps stable retry keys. Response headers prevent caching, framing and MIME sniffing. Hostnames are allowlisted. The unified HTML uses inline script/style under a restricted CSP; deployment requiring a nonce-only policy should split or hash these assets and retest.

The journal uses HMAC-linked events, increasing sequences, timestamps, actor, payload and snapshot hashes. An anchor is required and a missing anchor fails. Cash snapshots are HMAC protected. The same-database anchor detects a missing event tail when its anchor is retained, but cannot establish that the entire database and anchor were not rolled back together. Independent protected anchor storage, SSO/MFA, individual users, managed key rotation, cross-tenant isolation and enterprise retention are prerequisites beyond this demo.

## 9 Model and mandatory tools

Outbound calls require MANDATE_ALLOW_SYNTHETIC_EGRESS=1 and complete provider configuration. The model receives opaque evidence IDs, parent relationships and allowlisted control metadata. Vendor names, bank tokens, raw documents and freeform human notes are excluded. Output must contain exactly summary and cited_evidence_ids; unknown citations or malformed JSON cause a disclosed replay fallback. This schema check does not guarantee the prose is correct. The browser and server never convert prose into payment permission.

PRISM uses its pinned SDK by default. SDK trace_llm records the actual exchange and flushes; SDK 0.4.2 does not return a stored receipt, so the application reports submitted_unverified. Optional HTTP transport can report accepted only after a 200 with stored trace identity. Diagnostic live_connected and dashboard scoring must be checked separately. Stable session and agent IDs connect the observations. PRISM HTTP/SDK flags after the model response; the Mandate executor enforces transaction permission independently.

GIDE must perform substantive development or testing, with a retained session record, resulting diff/commit and passing tests. Other editors can technically share the repo; only organizers can settle whether that satisfies event rules. The package's GIDE status deliberately stays usage_pending. PRISM and GIDE logos, dependencies or a repo push alone are not evidence of meaningful use. See QUALIFICATION_AND_DEMO.md and SPONSOR_SETUP.md for the supplied promotion and actual-use sequence.

## 10 Metrics and acceptance

The UI measures case count, cases with independent beneficiary evidence, verified simulated effects, valid case journals, pending verification, revoked approvals and deduplicated bank roots. Every proportional comparison has an explicit denominator. Gates and their failure reasons are per-case rather than combined into an invented risk score. Model mode and PRISM observation status are separate from finance control results.

The constructed evaluation contains nine unsafe-to-admit scenarios and three legitimate scenarios. Compare a deliberately weak matching-record baseline to Mandate on the same fixtures. Report unsafe admissions and false holds, not just overall accuracy. The current deterministic result is 12 of 12 expected outcomes, zero of nine unsafe admissions and zero of three false holds. These small authored tests demonstrate specified invariants, not real-world fraud reduction, model robustness or a representative production distribution.

Resolve concepts are covered through all eight gates, exact fingerprints, validated receipts, signed expiring authority, immutable-value grant consumption, journal linkage and replay anchors. Mandate adds source-root ancestry, established-contact attestation, cash constraints and atomic persistence. A separate ADMIT metric inventory was not supplied; its complete coverage is unassessed. Add an explicit mapping and tests once the actual definitions arrive rather than inventing an acronym or denominator.

The release evidence comprises automated API and integration tests, concurrent retry tests, mutation and tampering tests, dependency scan and a real local browser walkthrough. QA_REPORT.md records results and limits. Before event submission complete a real model run, PRISM Observe–Improve–Prove evidence, substantive GIDE work, organizer eligibility confirmation, and a demo/repo link. Before cloud release additionally verify image build, HTTPS, secrets, persistent-volume restart and smoke tests on the actual host. Before real money, replace the synthetic rail and onboarding assumptions under an appropriate customer security and legal review.
