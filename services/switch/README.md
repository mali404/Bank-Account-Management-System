# services/switch

The SimNow instant-payment switch: ISO 20022 validation, routing by `ClrSysMmbId`, participant limits, TigerBeetle settlement, status/return/RfP orchestration, and a hash-chained message archive.

Defined in SPEC §5.3 (also §3.3). Implemented in **M2** as `agentbank_ledger.simnow.SimNow`, in the same process as the three banks. Settlement uses the pending / post / void counters described in `libs/agentbank_ledger/README.md`.
