# Incident playbook (IR-4)

Simulation only. The steps are freeze, recall, and revoke.

1. Freeze the victim account (`ops` freeze) so further payments stop.
2. Recall the payment (camt.056) when the receiving bank still holds the funds.
3. Revoke the consent the agent used, so the PSP cannot start another payment.
