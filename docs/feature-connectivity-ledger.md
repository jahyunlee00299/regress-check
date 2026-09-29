# Feature Connectivity Ledger

One entry per rule. Evidence = `tests/test_regress_check.py` (41 tests).

## unit: rule `moved` (R1)

- **Scope**: core
- **Inputs**: registry golden (`actual`, `rtol`, `atol`, `critical`), lock entry (`expected`, frozen `rtol`/`atol`), the actual number
- **Outputs**: `violation / certain` finding with id, expected, actual, absolute and relative delta, tolerance used, critical tag; fix `unsafe / suggest_only`
- **State ownership**: none — reads registry, lock and results file
- **External effects**: none
- **Evidence (Prove)**: freeze then check is clean; a value beyond `rtol` exits 1; `atol` contributes to the band
- **Refutation (Refute)**: value exactly at the boundary passes, epsilon beyond fails; the move is still reported when the registry tolerance was widened (judged against the tighter of registry and frozen tolerance); a narrowed registry tolerance takes effect immediately
- **Regress**: full suite
- **Deferred risk**: relative delta is n/a when the expected value is 0 (only `atol` can then admit a difference); no array/series comparison — one scalar per golden

## unit: rule `tolerance-widened` (R2)

- **Scope**: core (anti-shortcut)
- **Inputs**: registry `rtol`/`atol`, lock frozen `rtol`/`atol`
- **Outputs**: `violation / certain`, fix `unsafe / suggest_only` ("re-freeze with --reason")
- **State ownership**: none; the lock is only written by `freeze`
- **External effects**: none
- **Evidence (Prove)**: widening `rtol` or `atol` after the freeze exits 1 even when the value did not move
- **Refutation (Refute)**: narrowing exits 0; widening plus a move reports both findings; a re-freeze with a reason accepts the wider tolerance and records it in history
- **Regress**: full suite
- **Deferred risk**: a person can still re-freeze with a meaningless reason — the tool makes the decision visible and attributable, it cannot judge the reason

## unit: rule `unfrozen` (R3)

- **Scope**: core
- **Inputs**: registry golden ids, lock golden ids
- **Outputs**: `cannot_check / certain` finding; exit 2 unless a violation is also present
- **State ownership**: none
- **External effects**: none
- **Evidence (Prove)**: a golden added to the registry after the freeze exits 2 with "never frozen"
- **Refutation (Refute)**: a missing lock file is exit 2 with "run freeze first" rather than a clean pass
- **Regress**: full suite
- **Deferred risk**: none known

## unit: rule `lock-orphan` (R4)

- **Scope**: core (anti-shortcut)
- **Inputs**: lock golden ids, registry golden ids
- **Outputs**: `violation / needs_review`, fix `safe / suggest_only`
- **State ownership**: a full `freeze --reason` moves the orphan to `retired` in the lock; `--only` never does
- **External effects**: none
- **Evidence (Prove)**: deleting a golden from the registry exits 1 with the orphan finding in JSON
- **Refutation (Refute)**: `freeze --only a` leaves the orphan in place; a full freeze retires it with the reason and the check goes green
- **Regress**: full suite
- **Deferred risk**: `retired` entries are kept forever (small); there is no `unretire`
- **Not implemented on purpose**: `critical-untagged` (R5) — goldens without a `critical` tag are allowed
