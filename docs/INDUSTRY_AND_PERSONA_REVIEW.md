# Industry and persona review

Research date: September 5, 2026. Scope: synthetic retail accounts payable, beneficiary-change provenance, and agent execution authority. This is a design review, not a legal opinion, certification, customer validation, implementation test result, or statement of endorsement by any organization below.

## Decision

Build the narrow story: an agent copies an unverified supplier request into a vendor record, then encounters that record as if it were independent authority. MANDATE preserves the original lineage, refuses to treat the agent-derived record as independent verification, and admits only an exactly approved action into a local simulator. The defensible distinction is evidence independence plus execution enforcement, not a novel bank-change rule.

The payment-network sources below support the importance of scoped authority and authenticated agents. They do not establish that an AP beneficiary is genuine. The JPMorgan source supports the architectural direction; it is thought leadership rather than an integration specification. No reviewed source requires this particular architecture for all retail companies.

## Current primary-source findings and applicability

| Source | What the source establishes | Classification and implication for MANDATE |
|---|---|---|
| J.P. Morgan, *Proof of Movement*, June 25, 2026 | Discusses policy-bounded execution, source-linked action records, preventive controls, data quality, and safe handling of degradation in corporate treasury. Its forward-looking stack includes pre-transaction enforcement and auditable decisions. | Bank-authored perspective, not a universal rule or evidence of a shipped integration. Design inference: retain source lineage and place the decision before the executor. Do not reuse its illustrative business outcomes as measured MANDATE results. [Primary article](https://www.jpmorgan.com/payments/newsroom/agentic-ai-corporate-cash-treasury-management) |
| Mastercard, Agent Pay for Machines, June 10, 2026 | Describes credentialed agents, programmatically enforced authorization rules and spending limits, and machine-driven payment infrastructure. | Network product announcement. Design inference: separate agent identity from its permitted actions, and bind authority to limits. MANDATE does not implement AP4M, Agentic Tokens, Verifiable Intent, or settlement guarantees. A local ledger is not a network payment. [Primary announcement](https://www.mastercard.com/us/en/news-and-trends/press/2026/june/mastercard-launches-agent-pay-for-machines.html) |
| Visa Trusted Agent Protocol, current developer overview | Describes merchant- and purpose-specific time-bound signatures, recognition of trusted agents, and payment-information exchange; implementation material is governed by product terms. | Network protocol/product documentation; its detailed requirements matter to actual implementations and participants. It is not a general financial law. Design inference: scope authorization, enforce expiration and prevent replay. TAP authentication alone does not prove invoice validity, a genuine bank change, or independent verification. MANDATE is not a TAP implementation. [Developer overview](https://developer.visa.com/capabilities/trusted-agent-protocol/overview) |
| NIST AI RMF 1.0 and Core | The framework is voluntary and organized around Govern, Map, Measure, Manage. NIST states revision is in progress. | Voluntary risk-management framework, not certification. Design inference: document ownership and scope, measure failures on a fixed cohort, and record responses. A control mapping is not evidence that every framework outcome is satisfied. [NIST publication](https://www.nist.gov/publications/artificial-intelligence-risk-management-framework-ai-rmf-10), [Core and revision notice](https://airc.nist.gov/airmf-resources/airmf/5-sec-core/) |
| U.S. Treasury, February 19, 2026 | Announces a financial-services adaptation of NIST AI RMF, supporting lifecycle risk evaluation, accountability, transparency and resilience. | Guidance resource announced through a public-private initiative. The announcement is not a new statutory obligation or proof that MANDATE meets the detailed framework. A full control mapping needs the actual framework and an applicability assessment. [Treasury announcement](https://home.treasury.gov/news/press-releases/sb0401) |
| Federal Reserve/OCC/FDIC, SR 26-2, April 17, 2026 | Supersedes SR 11-7 and SR 21-8. Expected to be most relevant to banking organizations above $30 billion. The guidance expressly does not set enforceable standards; its model definition excludes deterministic rule-based processes, and footnote 3 excludes generative and agentic AI. | Supervisory guidance with a specific scope, not a compliance mandate for this AP prototype. General governance ideas can inform design, but do not claim the agent or rule gate is directly covered by this document or “SR 11-7 compliant.” Other laws and unsafe practices remain separate questions. [Replacement letter](https://www.federalreserve.gov/supervisionreg/srletters/SR2602.htm), [Guidance, scope and footnotes](https://www.federalreserve.gov/frrs/guidance/supervisory-guidance-on-model-risk-management.htm) |
| FBI business email compromise advice | Advises independently looking up contact information instead of using contact details supplied in a suspicious message, and verifying changes to account numbers or payment procedures. | Public fraud-prevention advice, not a regulation. Design inference: retain the contact source and verification provenance. A callback checkbox does not establish that a callback occurred or defeat impersonation. [FBI guidance](https://www.fbi.gov/how-we-can-help-you/common-frauds-and-scams/business-email-compromise) |

The JPMorgan page returned HTTP 403 on direct opening; the search service returned its indexed primary-page text, which was used here. Other cited overview and guidance pages were retrieved or returned directly in primary-source search results. These are public materials, not confidential bank requirements or a complete assessment of network participation contracts.

## Persona red team

These are simulated role perspectives, not interviews. They apply to an AP analyst, verifier, controller, retail finance owner, security architect, audit reviewer and model evaluator. Product demand remains unvalidated.

| Perspective | The objection that matters | Design response and proof needed |
|---|---|---|
| AP analyst | “Why am I reopening a vendor already marked verified?” | Show the supplier request, agent write and downstream vendor record in one lineage view. Explain that copying does not create independent evidence. Preserve the actual source timestamp and actor, not just the newest record. |
| Independent verifier | “Your verification button lets anyone manufacture trust.” | Require a server-authenticated verifier, trusted contact reference, destination binding, timestamps and provenance. Label the callback as synthetic. A verifier may attest; an agent may not certify its own evidence. |
| Controller | “I approved a different account five minutes ago.” | Display exact amount, currency, destination and candidate version. Expire or invalidate the grant when a bound field, required evidence or policy changes; reject stale requests server-side. |
| Retail finance owner | “We already have dual approval; you add queue time.” | Demonstrate the specific agent-derived evidence failure and a normal case. Measure review effort, not invented loss avoidance. Under the current C2 specification, even a normal case still requires controller approval: do not market this demo as autonomous straight-through payment. |
| Security architect | “The agent bypasses your screen or replays the release.” | Only the server executor can write the simulated ledger. Validate identity, live authority, expiration, state fingerprint and single-use status within the execution transaction. Test direct calls, mismatched candidates and concurrent requests. |
| Audit reviewer | “Your timeline is a story, not evidence.” | Link immutable source versions, retrieved inputs, typed candidate, Resolve receipts, decision, grant and ledger inspection. Export actual event identifiers and hashes. An ordinary local hash chain is not externally anchored, tamper-proof storage. |
| ML evaluator | “You instructed the baseline to fail.” | Freeze fixtures, prompts, model identity and tools; distinguish end-to-end agent behavior from adversarial executor tests. Preserve refusals and report real failures. Missing model/PRISM evidence is missing evidence, not a pass. |
| Procurement / buyer | “A bank or ERP can add this.” | Valid criticism. The potential wedge is an integration layer that preserves provenance across agent workflows and enforces exact authority. Validate willingness to integrate and pay through real AP/controller interviews after the event. |

## Architecture rationale and acceptance obligations

These are engineering recommendations for this demo, not requirements attributed to payment networks or regulators. Consult the repository's implementation specification for canonical Resolve APIs; this review does not redefine them.

1. **Treat record lineage as a graph.** Store immutable evidence versions with parents, originating actor and trust class. A vendor update descended from the supplier request remains dependent on that request even when the text or storage location changes. A hash identifies content; it does not certify its truth.
2. **Keep proposing, attesting, approving and executing separate.** The runtime model may retrieve allowed inputs and propose a typed candidate. Server-owned checks create receipts for Resolve. A human verifier records synthetic independent evidence; a different controller approves. The server owns simulated execution. No model-supplied “verified” or browser-supplied “success” boolean grants authority.
3. **Bind authorization to the actual candidate.** Use canonical fingerprints of material fields and relevant evidence/policy versions. Validate expiration, revocation and consumption against current state. Recheck and consume authority atomically with the simulated ledger write, and enforce idempotency. A preflight check followed by an unprotected write leaves a time-of-check/time-of-use gap.
4. **Inspect the result independently.** Compare the resulting ledger entry with the approved candidate and record an observation. A successful adapter return alone is insufficient. Distinguish unknown outcome from confirmed failure; retries must not duplicate effects.
5. **Keep the uncertainty visible.** Unknown or stale evidence holds the case. Missing observability must be reported honestly. Name the simulated payment rail and synthetic people on screen. Reversal in a local simulator does not establish that a real payment is reversible.
6. **Reuse Resolve accurately.** Keep canonical dispositions, receipt meanings, ApprovalGrant, fingerprints and journal identifiers. Present provenance checks as application-specific additions. Do not rebrand reused components as newly invented security mechanisms.

## ADMIT and metric evidence status

**Full ADMIT coverage cannot be established.** No separate ADMIT definition, rubric, metric catalogue, source version or acceptance thresholds were provided to this reviewer. Do not invent an acronym expansion or assert “all ADMIT metrics passed.” This review is not an execution audit: tests and runtime evidence were not independently run or inspected here.

The following is a proposed evidence checklist, not an ADMIT mapping:

| Candidate metric | Minimum defensible evidence | Current assessment in this review |
|---|---|---|
| Unsafe execution rate | Per-case expected control state and actual ledger effect; numerator/denominator; fixed cohort and configuration | Requires run artifacts; no result certified here |
| Authorized completion rate | Eligible cases completing exact approved effects / eligible cases, with exclusions stated | Requires run artifacts; ordinary C2 approval still applies |
| False hold rate | Holds among independently adjudicated eligible cases, not simply all cases without fraud | Requires adjudication and cohort evidence |
| Provenance-laundering resistance | Supplier request → agent-derived record chain rejected as independent evidence | Requires fixtures and actual receipt/decision output |
| Approval integrity | Changed, expired, revoked, replayed and concurrent requests rejected without duplicate effects | Requires negative and concurrency test evidence |
| Evidence completeness | Every claimed action links source versions, candidate, decision, grant and observed effect | Requires complete exports, not a screenshot alone |
| Real model use | Provider/model identifier, actual request/response metadata and tool trajectory, with secrets redacted | Requires runtime artifact; a scripted proposal does not qualify |
| PRISM delivery | Actual application spans, ingestion status and retrievable trace references | Requires real backend evidence; local JSON alone is not proof of ingestion |
| GIDE contribution | Identifiable substantive implementation/testing contribution and resulting artifacts | Requires event evidence; a mention is insufficient |
| Gate latency and review time | Defined start/end boundaries, per-run samples, environment, sample count and distribution | Requires measurement; do not mix human waiting with gate runtime |

When the actual ADMIT source arrives, record its version, map each requirement to code plus an executed test or runtime artifact, and mark every item **verified**, **partial**, **missing**, or **not applicable with reason**. Until then, the only supportable statement is that the MVP has its own explicit acceptance contract; ADMIT coverage remains unassessed.
