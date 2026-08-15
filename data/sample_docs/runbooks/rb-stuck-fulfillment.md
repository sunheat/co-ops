# Runbook: Stuck Fulfillment Instruction

## Purpose

Diagnose settlement instructions that the Fulfillment Adapter sent but that
never received an acknowledgment from the venue or custodian.

## When To Use

- An instruction has been in `SENT` state beyond the acknowledgment
  timeout.
- A custodian reports missing or duplicated settlement messages.

## Prerequisites

- The settlement instruction identifier, e.g. `SI-20240315-007`.
- Access to the Fulfillment Adapter log for the send window.

## Investigation Steps

1. Confirm the adapter state: the log must show the message as `SENT`. If
   the adapter never sent, the problem is upstream approval, not transport.
2. Check the counterparty health: custodian or venue maintenance windows
   are a known cause of lost acknowledgments.
3. Verify no acknowledgment was received but misrouted: search the adapter
   log for the instruction identifier around the expected acknowledgment
   time.
4. Confirm the instruction was not already fulfilled through a manual
   channel; resending against a fulfilled instruction creates duplicates.

## Resolution Options

- Resend the instruction with the same identifier; the adapter deduplicates
  by identifier on the receiving side.
- If the counterparty confirms receipt out-of-band, mark the instruction
  acknowledged manually and record the exception.

## Escalation

Escalate to service developers when the adapter log shows transport errors,
and to operations analysts when settlement deadlines are at risk.

## Related Artifacts

- Module: Fulfillment Adapter (Java)
- Tables: `batch_jobs` (adapter runs are recorded as batch executions)
