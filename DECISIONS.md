Why does the credit system use a transaction ledger instead of a balance column?

I used a ledger because it keeps a complete history of credit movement. Every grant, deduction, and refund is stored as a separate row, so I can always explain how a balance changed. A single balance column is easier to read, but it hides history and makes audits and debugging harder. With a ledger, balance is always the sum of recorded transactions.

How did you handle the simultaneous credit deduction problem?

I handled it with a database transaction and row lock. During deduction, the code locks the organisation row with SELECT FOR UPDATE, calculates current balance, checks if enough credits exist, and then writes the debit before commit. If two requests arrive at the same time and only one should succeed, one request commits first and the second sees the updated balance and fails. This prevents double spending.

What happens when the background worker fails after credits have been deducted?

The job is moved to failed with an explicit error. This happens if enqueue fails, worker execution fails, or the job stays pending or running for too long. In these failure cases, the system writes a +10 refund transaction for summarise. The refund key is based on job id, so retries do not create duplicate refunds.

How does your idempotency implementation work, and where does it live?

Idempotency is implemented in idempotency_records and credit_transactions. On analyse and summarise, the API first claims a unique row scoped by organisation, endpoint, and idempotency key. If another request with the same key arrives, it replays the stored response or waits briefly for completion. Credit deduction also uses a unique idempotency key at ledger level, so duplicate billing is blocked in the database. The 24-hour replay rule is preserved by deriving ledger idempotency from the claimed record id.

What would break first at 10x the current load, and what would you do about it?

The first likely bottleneck is credit deduction contention for very active organisations, because deduction uses locking and repeated balance aggregation. The next likely bottleneck is queue backlog if worker throughput cannot keep up, which increases polling traffic. I would scale in steps: add better indexes, use a lightweight balance projection or cache for hot reads, autoscale workers, add queue lag alerts, and partition large tables as data grows.
