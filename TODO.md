# TODO

## Runtime / Kernel

- Surface structured `ATTACK_HINT` skips as degraded scan state when unavailable tools prevent expansion.
- Continue reducing legacy `Node` dependence.
  - Reporting and summaries should rely on kernel assets first.
  - `nodes` / `node_count` should remain compatibility-only until removed.

## Product / UX

- Surface degraded components more clearly in CLI summaries.
- Review TUI screens for any remaining wording that implies old manager-era architecture.

## Quality / Tests

- Keep replacing deleted legacy-path coverage with active-kernel coverage where it still provides signal.
- Add focused tests when legacy `Node` compatibility is reduced further.

## Docs

- Keep historical research docs explicitly labeled as historical when they describe pre-kernel behavior.
- Add more detailed operator guidance if the legacy SQLite reset flow changes beyond the current `kodiak migrate --reset --force` path.
