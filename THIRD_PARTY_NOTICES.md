# Resolve reuse

`mandate/core/case.py`, `contract.py`, `approval.py` and `journal.py` are copied unchanged from https://github.com/YashM1503/lan-lords-resolve at commit `87169fe1131fa2903fdcad7324e828ebd4c0885e`. The original Apache 2.0 license is retained at `THIRD_PARTY_LICENSES/Resolve-LICENSE`. Original source docstrings and semantics remain. The surrounding Mandate domain policy, server, UI, fixtures, authentication, persistence and tests adapt these primitives into an accounts-payable structure.

This is disclosed reuse, not a claim of original invention of those primitives. The previous Resolve runtime, simulator, model mock and automatic approval workflow were not imported. No ADMIT implementation is claimed without its separate source definition.
