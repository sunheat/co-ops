# Margin Service (mock)

Mock Java service of the Acme Clearing & Fulfillment System (ACFS), part of
the Co-Ops RAG corpus. It exists so that code-aware retrieval, chunking, and
support-investigation demos have a realistic Java codebase to work against.
All business rules are fictional and deliberately simplified.

See `data/mock_domain/README.md` for the full domain definition.

## What It Does

The service covers two ACFS modules:

| Module | Class | Responsibility |
| --- | --- | --- |
| Margin Service | `MarginCalculator` | Calculates initial and variation margin per client account from positions, applies venue-specific rates, and produces a `MarginReport` per daily run. |
| Position Reconciler | `ReconciliationService` | Aggregates client-level positions per instrument and compares them with venue-published aggregate positions; raises breaks on any mismatch. |

## Layout

```text
margin-service/
  pom.xml
  src/main/java/com/acme/acfs/margin/
    model/
      Currency.java           Settlement currencies (SGD, AUD, HKD, USD)
      Venue.java              Venues (SGX, ASX, HKEX) with base currency
      Trade.java              Executed trade imported from venue files
      Position.java           Client-level position with price snapshot
      ClientAccount.java      Client record with status and margin model
      MarginReport.java       Output of one daily margin run
    service/
      MarginCalculator.java   Initial/variation margin calculation
      ReconciliationService.java  Client vs venue position reconciliation
```

## Business Rules (simplified)

- **Initial margin** = gross notional of the client's positions
  (`sum(|quantity| * lastPrice)`) multiplied by a venue-specific rate
  (SGX 8%, ASX 10%, HKEX 9%). Accounts on the `PORTFOLIO` margin model
  receive a 10% diversification offset.
- **Variation margin** = daily mark-to-market change
  (`sum(quantity * (lastPrice - previousClose))`).
- Amounts are rounded to two decimals in the venue's base currency.
- Run identifiers follow the corpus convention `MR-YYYYMMDD-{venue}`,
  e.g. `MR-20240315-SGX`.
- Only `ACTIVE` client accounts participate in a margin run.
- Reconciliation compares the union of instruments on both sides; a missing
  line on either side counts as a break against zero.

## Known Limitations

This is a corpus fixture, not a runnable service:

- No persistence layer: positions, accounts, and venue aggregates are passed
  in-memory; nothing reads or writes the `trades`, `positions`,
  `margin_runs`, or `margin_results` tables yet.
- No wiring to the Batch Scheduler or the Fulfillment Adapter, and no
  integration with the Python-based Trade Importer or Invoice Generator.
- Margin formulas are deliberately naive (flat venue rates, no product-level
  risk weights, no cross-currency handling beyond venue base currency).
- No unit tests or executable entry point; the `pom.xml` declares no
  dependencies and exists only to mirror a real project layout.
- No configuration management: venue rates and portfolio factors are
  constants in `MarginCalculator`.

These limitations are expected at this stage. Subsequent corpus updates add
the SQL schema, runbooks, tickets, and architecture docs that reference this
service.
