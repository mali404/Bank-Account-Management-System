"""In-process sim-mail, merchant-sim, and user-sim (SPEC §4, §9 D7).

User-sim is the only human in the loop. There is no human-subjects study.
``always-approve`` accepts every prompt, ``careful`` accepts a prompt that
names the task, and ``fatigue`` starts refusing and accepts from the third
prompt on.
"""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = ["Mailbox", "MerchantSim", "UserSim"]


@dataclass
class Mailbox:
    """One customer's inbox and the bank's outbound queue."""

    inbox: list[tuple[str, str]] = field(default_factory=lambda: [("Rent invoice", "invoice due")])
    outbox: list[str] = field(default_factory=list)

    def latest(self) -> str:
        subject, body = self.inbox[-1]
        return f"{subject} {body}"

    def deliver(self, subject: str, body: str) -> None:
        self.inbox.append((subject, body))

    def send(self, body: str) -> str:
        self.outbox.append(body)
        return "queued notice"


@dataclass
class MerchantSim:
    """Invoices a payment-initiator PSP can read."""

    invoices: tuple[str, ...] = ("INV-200 amount 4200", "INV-100 open")

    def listing(self) -> str:
        return self.invoices[0]


@dataclass
class UserSim:
    """Scripted approval model for HITL prompts."""

    model: str = "always-approve"
    prompts: int = 0

    def approve(self, prompt: str, task_id: str) -> bool:
        self.prompts += 1
        if self.model == "always-approve":
            return True
        if self.model == "careful":
            return task_id in prompt
        if self.model == "fatigue":
            return self.prompts >= 3
        return False
