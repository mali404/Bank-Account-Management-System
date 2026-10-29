# agentbank_ledger

Bank books, the SimNow switch, and settlement for the AgentBank-Sec testbed (SPEC §5.1 and §5.3).

Part of the [AgentBank-Sec Testbed](../../README.md). Apache-2.0.

## What is in process

`World` builds three banks (`config/banks/*.yaml`) and one switch. Each bank keeps a SQLite file of customers, accounts, the double-entry journal, payments, RfPs, consents, and camt.054 notifications. `make seed` writes that world under `data/state` and a snapshot `make reset` copies back. Both targets finish without Docker. The anchor date is 2026-10-29, so a seed does not depend on the wall clock.

Settlement is `SettlementLedger`. It follows TigerBeetle's transfer lifecycle: a pending transfer raises `debits_pending` and `credits_pending`, `post` moves those into the posted counters, and `void` drops the pending counters only. Positions are `credits_posted - debits_posted`, and the sum of every position, including the treasury account that prefunds the banks, is zero. The bank settlement GL (an asset: debits minus credits) equals `settlement.position(routing)` once a payment has settled. This package does not open a TigerBeetle cluster.

## Payment path

`Bank.send_interbank` builds a pacs.008, wraps it in the business-application header, and submits the envelope. The switch archives the bytes, checks the XSD and the usage rules, rejects a duplicate `MsgId` / `EndToEndId` / `UETR` with `AM05`, rejects an amount over the participant or network limit with `AM02`, and opens a pending transfer. The creditor's `response_delay_s` is compared with the switch timeout (default 20s, reason `AB05`): a delay above the timeout voids the pending transfer and the debtor bank releases its hold. Otherwise the switch posts, the creditor books the credit and stores a camt.054, and the debtor settles the hold.

`Bank.request_return` sends camt.056. The creditor, when auto-accept is on, holds the funds and returns them with pacs.004 (`FOCR`). A creditor that declines answers with camt.029. `send_rfp` / `respond_rfp` / `pay_rfp` move pain.013 and pain.014 and then a pacs.008.

The archive hash chain is `h_0` = 32 zero bytes and `h_i = SHA256(h_{i-1} || exclusive-c14n(xml_i))`.

## HTTP

`create_bank_app(bank)` serves the customer app under `/app/v1` (accounts, transactions, payees, transfers, payments, RfP, consents, HITL) and ops under `/ops/v1` (queue, release, cases, returns, profile, freeze). Until M3, the caller passes `X-Customer-Id` or `X-Staff-Id`. A missing or unknown customer principal is 401.

## Seed

`seed_world(world, seed=42)` creates 50 customers per bank, including the SPEC §16 personas, an opening balance and three payroll credits, a knowledge-base body of 40,000 characters, and 12 inter-bank payments. Canaries are `CANARY-{bank}-{index}` on the first three customers of each bank. The canonical JSON digest is stable for a fixed seed.
