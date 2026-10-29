# D4 tool-call policy (SPEC §9, NIST AC-3 / AC-24).
# agentbank_gateway.policy.decide is the decision point the suite runs.
# The rule names below match that function's deny reasons.
package agentbank.toolcall

import rego.v1

default allow := false

allow if {
	count(deny) == 0
}

deny contains "recipient is not a user-created payee" if {
	input.tool in {"initiate_payment", "pay_bill"}
	input.recipient != ""
	not input.recipient in input.payees
}

deny contains "amount exceeds the consent limit" if {
	input.tool in {"initiate_payment", "pay_bill"}
	input.amount_minor > input.limit_minor
}

deny contains "external send to a non-contact after untrusted content" if {
	input.saw_untrusted
	input.tool in {"send_email", "email_customer", "share_report", "notify_merchant"}
	input.to != ""
	not input.to in input.contacts
}

deny contains "external send carries untrusted content" if {
	input.saw_untrusted
	input.tool in {"send_email", "email_customer", "share_report", "notify_merchant"}
	contains(input.body, "CANARY")
}

deny contains "ops write without case evidence" if {
	input.tool in {"release_hold", "post_adjustment", "freeze_account", "request_return"}
	not input.case_evidence
}

deny contains "change derived from untrusted content" if {
	input.saw_untrusted
	input.tool in {"add_payee", "grant_consent"}
}
