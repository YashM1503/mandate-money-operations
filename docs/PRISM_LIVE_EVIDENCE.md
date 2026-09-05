# PRISM live evidence — Money Operations

Verified in the PRISM dashboard on 5 September 2026 against project
`cb615645-2204-4ce6-a6cb-013562d3cc59`.

## Observe → Improve proof

| Run | PRISM trace | Validation sent to PRISM | Observed result |
|---|---|---|---|
| `mo-demo-weak` | `d285c684-66bf-4e52-bb48-c3e0e4c14cd9` | `numeric_validation=reject`; `citation_validation=reject` | PRISM received the invented Other Opex explanation and displayed quality 25/100. |
| `mo-demo-corrected` | `18e10623-749f-48c7-905b-bf703d32beb4` | `numeric_validation=pass`; `citation_validation=pass` | PRISM received the claim-backed narrative, kept Other Opex unexplained, and displayed quality 45/100. |

The project Traces page showed two live traces. The corrected trace contains the
canonical revenue movement of $675,000 / 18.0%, enterprise contribution of
$576,000, top-three contribution of $432,000 / 64.0%, Software movement of
$82,000 with context confirmation required, and Other Opex of $57,000 with the
cause left open.

## Receipt limitation

`prismtrace-sdk==0.4.2` submitted and flushed both observations but returned no
ingest receipt to the local process. The script therefore reported
`live_trace_pending` and `application_trace_id=None`. Dashboard inspection
independently verified ingestion and supplied the trace IDs above. Do not alter
the runtime state machine to invent a receipt that the SDK did not return.

## Data boundary

Only allowlisted narrative metadata and validated narrative text were sent.
Raw transaction rows, credentials, customer tables, and deterministic engine
arithmetic were not transmitted by the Money Operations PRISM adapter.
