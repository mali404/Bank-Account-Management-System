# Mojaloop overlay

`deploy/compose.mojaloop.yaml` is an empty compose overlay. Mojaloop's
central ledger and API adapter expect a Kubernetes-style stack and a
different settlement scheme from SimNow. This testbed keeps the custom
SimNow switch as the base (SPEC §1.2, §20). The overlay is not started
by `make up` and does not vendor Mojaloop.
