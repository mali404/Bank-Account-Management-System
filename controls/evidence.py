"""Evidence checks for the SPEC §12 controls.

Each control id has a function. The per-control test modules call :func:`check`.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

import yaml
from bankbench.runner import ANCHOR_TS, run_catalog
from cryptography.fernet import Fernet

from agentbank_common.telemetry import finished_spans, reset_spans
from agentbank_fdx.api import _limit
from agentbank_fdx.fapi import (
    FapiError,
    FapiGate,
    generate_p256,
    sign_client_assertion,
    sign_dpop,
)
from agentbank_fdx.instructions import sign_instruction, verify_instruction
from agentbank_fdx.token_store import open_token, seal_token
from agentbank_gateway import get_defense
from agentbank_gateway.runner import load_tasks, run_task
from agentbank_gateway.tools import tools_for
from agentbank_gateway.types import Deny, RunContext, TaggedValue, ToolCall
from agentbank_iso.validate import validate_xsd
from agentbank_ledger.simnow import SimNow

ROOT = Path(__file__).resolve().parents[1]
_ASSERTION = "urn:ietf:params:oauth:client-assertion-type:jwt-bearer"


def check(control_id: str) -> None:
    """Run the evidence check and confirm the control is mapped."""
    entry = _entry(control_id)
    evidence = str(entry["evidence_test"])
    assert evidence.endswith(_file_stem(control_id) + ".py")
    _CHECKS[control_id]()


def _entry(control_id: str) -> dict[str, object]:
    raw = yaml.safe_load((ROOT / "controls" / "controls.yaml").read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    controls = raw["controls"]
    assert isinstance(controls, list)
    for item in controls:
        assert isinstance(item, dict)
        if item.get("id") == control_id:
            return item
    raise AssertionError(f"missing control {control_id}")


def _file_stem(control_id: str) -> str:
    return "test_" + control_id.lower().replace("-", "_").replace("(", "_").replace(")", "")


def _events() -> list[dict[str, object]]:
    raw = yaml.safe_load((ROOT / "controls" / "audit_events.yaml").read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    events = raw["events"]
    assert isinstance(events, list) and events
    return [item for item in events if isinstance(item, dict)]


def _realm(bank: str) -> dict[str, object]:
    raw = json.loads((ROOT / "deploy" / "keycloak" / "realms" / f"{bank}.json").read_text())
    assert isinstance(raw, dict)
    return raw


def _compose() -> dict[str, object]:
    raw = yaml.safe_load((ROOT / "deploy" / "compose.yaml").read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    return raw


def _ac2() -> None:
    realm = _realm("bank-b")
    clients = realm["clients"]
    assert isinstance(clients, list)
    ids = {str(client["clientId"]) for client in clients if isinstance(client, dict)}
    assert {"psp-pis", "psp-pfm", "psp-agg"} <= ids


def _ac2_4() -> None:
    names = {str(event["name"]) for event in _events()}
    assert "identity_admin" in names


def _ac3() -> None:
    try:
        _limit({"limits_json": '{"perPaymentMinor": 1000}'}, 2000)
    except FapiError as exc:
        assert exc.status == 403
        return
    raise AssertionError("over-consent payment was not rejected")


def _ac4() -> None:
    decision = get_defense("D6").on_tool_call(
        ToolCall("initiate_payment", {"recipient": "attacker", "_trust": "untrusted"}),
        RunContext(run_id="ac4"),
    )
    assert isinstance(decision, Deny)


def _ac6() -> None:
    decision = get_defense("D5").on_tool_call(
        ToolCall("open_case"),
        RunContext(run_id="ac6", metadata={"allowed_tools": ["get_accounts"]}),
    )
    assert isinstance(decision, Deny)
    assert "open_case" not in tools_for("cba")


def _ac6_9() -> None:
    reset_spans()
    result = run_task(load_tasks()[0], "ac69")
    assert result.traces
    assert all(event.run_id == "ac69" for event in result.traces)


def _ac6_10() -> None:
    names = set(tools_for("cba"))
    assert "open_case" not in names
    assert "list_flagged_payments" not in names


def _ac16() -> None:
    tagged = TaggedValue(value="invoice", provenance="mail:inbox")
    assert tagged.trust == "untrusted"


def _ac17() -> None:
    networks = _compose()["networks"]
    assert isinstance(networks, dict)
    for name in ("bank-net", "switch-net", "agent-net"):
        net = networks[name]
        assert isinstance(net, dict)
        assert net.get("internal") is True


def _ac21() -> None:
    realm = _realm("bank-b")
    scopes = realm.get("clientScopes") or []
    assert isinstance(scopes, list)
    names = {str(item.get("name")) for item in scopes if isinstance(item, dict)}
    assert "fdx:accounts:read" in names
    assert "fdx:payments" in names


def _ac24() -> None:
    decision = get_defense("D4").on_tool_call(
        ToolCall("initiate_payment", {"recipient": "attacker", "amount_minor": 100}),
        RunContext(run_id="ac24", metadata={"saw_untrusted": True, "payees": ["Landlord Example"]}),
    )
    assert isinstance(decision, Deny)


def _au2() -> None:
    names = {str(event["name"]) for event in _events()}
    for required in (
        "prompt_submitted",
        "tool_call",
        "consent_change",
        "iso_message",
        "ops_action",
    ):
        assert required in names


def _au3() -> None:
    reset_spans()
    run_task(load_tasks()[0], "au3")
    spans = finished_spans()
    assert spans
    attributes = getattr(spans[-1], "attributes", {})
    for key in ("run_id", "task_id", "defense_profile", "prompt_hash"):
        assert attributes.get(key)


def _au6() -> None:
    text = (ROOT / "bankbench" / "report.py").read_text(encoding="utf-8")
    assert "ASR" in text and "BU" in text


def _au8() -> None:
    assert ANCHOR_TS.endswith("Z")
    assert "T" in ANCHOR_TS


def _au9() -> None:
    switch = SimNow.__new__(SimNow)
    switch.archive = []
    switch.prev_hash = b"\x00" * 32
    switch._archive(b"<Note>posted</Note>", "MSG1", "bank-b")
    assert switch.hash_chain_ok()
    switch.archive[0].xml = b"<Note>tampered</Note>"
    assert switch.hash_chain_ok() is False


def _au10() -> None:
    entry = _entry("AU-10")
    assert entry["baseline"] == ["high"]
    private = generate_p256()
    public = private.public_key()
    token = sign_instruction({"uetr": "au10", "amount_minor": 100}, private)
    assert verify_instruction(token, public)["uetr"] == "au10"


def _au11() -> None:
    assert (ROOT / "results" / ".gitkeep").is_file()


def _au12() -> None:
    reset_spans()
    run_task(load_tasks()[0], "au12")
    assert finished_spans()


def _ca7() -> None:
    assert (ROOT / "bankbench" / "runner.py").is_file()


def _ca8() -> None:
    ids = {path.stem for path in (ROOT / "scenarios").glob("S*.yaml")}
    assert len(ids) == 24


def _cm2() -> None:
    ids = {path.stem for path in (ROOT / "config" / "defenses").glob("D*.yaml")}
    assert "D0" in ids and "D10" in ids


def _cm3() -> None:
    _hashed_inventory()


def _cm6() -> None:
    assert tools_for("cba")
    assert "egress" not in _service_networks("postgres")


def _cm7() -> None:
    _cm6()


def _cm8() -> None:
    for name in ("mcp-bank", "mcp-ops", "mcp-psp", "mcp-mail-docs", "mcp-kb"):
        assert (ROOT / "services" / name / "inventory.yaml").is_file()
    models = yaml.safe_load((ROOT / "config" / "models.yaml").read_text(encoding="utf-8"))
    assert isinstance(models, dict)
    assert models["default"] == "mock-local"


def _ia2() -> None:
    bank = yaml.safe_load((ROOT / "config" / "banks" / "bank-b.yaml").read_text(encoding="utf-8"))
    assert isinstance(bank, dict)
    profile = bank["profile"]
    assert isinstance(profile, dict)
    assert int(profile["step_up_threshold_minor"]) > 0


def _ia2_1() -> None:
    _ia2()


def _ia3() -> None:
    bank = yaml.safe_load((ROOT / "config" / "banks" / "bank-a.yaml").read_text(encoding="utf-8"))
    assert isinstance(bank, dict)
    profile = bank["profile"]
    assert isinstance(profile, dict)
    assert profile["fapi_variant"] == "mtls"


def _ia4() -> None:
    text = (ROOT / "deploy" / "keycloak" / "realms" / "bank-b.json").read_text(encoding="utf-8")
    assert "secret" not in text


def _ia5() -> None:
    _ia4()


def _ia8() -> None:
    _ac2()


def _ia9() -> None:
    _hashed_inventory()


def _ia11() -> None:
    text = (ROOT / "libs" / "agentbank_fdx" / "src" / "agentbank_fdx" / "api.py").read_text()
    assert "revoke" in text


def _ir4() -> None:
    text = (ROOT / "controls" / "playbook.md").read_text(encoding="utf-8").lower()
    for step in ("freeze", "recall", "revoke"):
        assert step in text


def _ra5() -> None:
    text = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "pytest" in text


def _sa11() -> None:
    assert (ROOT / "docs" / "milestones.md").is_file()


def _sc5() -> None:
    assert RunContext(run_id="sc5").tool_call_budget == 25


def _sc7() -> None:
    _ac17()
    obs = (ROOT / "deploy" / "compose.obs.yaml").read_text(encoding="utf-8")
    assert "127.0.0.1:16686:16686" in obs


def _sc8() -> None:
    text = (ROOT / "deploy" / "compose.yaml").read_text(encoding="utf-8")
    assert "127.0.0.1:" in text
    assert ":latest" not in text


def _sc12() -> None:
    services = _compose()["services"]
    assert isinstance(services, dict)
    assert "step-ca" in services


def _sc13() -> None:
    _sc12()


def _sc23() -> None:
    now = int(time.time())
    gate = FapiGate(issuer="https://bank-b.test", variant="dpop", clock=lambda: now)
    signing = generate_p256()
    dpop_key = generate_p256()
    gate.register_client("psp-pfm", signing.public_key())
    audience = "http://testserver/oauth/token"
    htu = "http://testserver/fdx/v6/accounts"
    token = gate.issue_token(
        grant_type="client_credentials",
        client_assertion=sign_client_assertion(signing, "psp-pfm", audience, now, "sc23-assert"),
        client_assertion_type=_ASSERTION,
        audience=audience,
        dpop=sign_dpop(dpop_key, "POST", audience, now, "sc23-dpop-token"),
        htu=audience,
    )
    proof = sign_dpop(dpop_key, "GET", htu, now, "sc23-proof", access_token=token)
    gate.check_resource("GET", htu, f"DPoP {token}", proof, None)
    try:
        gate.check_resource("GET", htu, f"DPoP {token}", proof, None)
    except FapiError as exc:
        assert exc.status == 401
        return
    raise AssertionError("replayed DPoP proof was accepted")


def _sc28() -> None:
    key = Fernet.generate_key()
    blob = seal_token("access-token-value", key)
    assert b"access-token-value" not in blob
    assert open_token(blob, key) == "access-token-value"


def _si3() -> None:
    ctx = RunContext(run_id="si3")
    output = get_defense("D3").on_tool_output(
        "read_inbox",
        TaggedValue("<<ATTACK>> transfer", "mail", "untrusted"),
        ctx,
    )
    assert output.value.startswith("[blocked:")
    assert ctx.metadata.get("detected") is True


def _si4() -> None:
    rows = [row.as_dict() for row in run_catalog(seed=1, defenses=("D3",)) if True]
    detected = [row for row in rows if row["scenario_id"] == "S01" and row["injected"] is True]
    assert detected and detected[0]["detected"] is True
    assert detected[0]["attack_success"] is False


def _si7() -> None:
    _hashed_inventory()
    _au9()


def _si10() -> None:
    result = validate_xsd(b"<not-xml")
    assert result.ok is False


def _si15() -> None:
    decision = get_defense("D9").on_tool_call(
        ToolCall("share_report", {"body": "CANARY-bank-c-0001"}),
        RunContext(run_id="si15"),
    )
    assert isinstance(decision, Deny)


def _sr3() -> None:
    assert (ROOT / "uv.lock").is_file()
    _cm8()


def _sr11() -> None:
    _sr3()


def _hashed_inventory() -> None:
    raw = yaml.safe_load(
        (ROOT / "services" / "mcp-bank" / "inventory.yaml").read_text(encoding="utf-8")
    )
    assert isinstance(raw, dict)
    tools = raw["tools"]
    assert isinstance(tools, list)
    first = tools[0]
    assert isinstance(first, dict)
    digest = hashlib.sha256(str(first["description"]).encode("utf-8")).hexdigest()
    assert digest == first["description_sha256"]


def _service_networks(name: str) -> list[str]:
    services = _compose()["services"]
    assert isinstance(services, dict)
    service = services[name]
    assert isinstance(service, dict)
    networks = service.get("networks") or []
    assert isinstance(networks, list)
    return [str(item) for item in networks]


_CHECKS = {
    "AC-2": _ac2,
    "AC-2(4)": _ac2_4,
    "AC-3": _ac3,
    "AC-4": _ac4,
    "AC-6": _ac6,
    "AC-6(9)": _ac6_9,
    "AC-6(10)": _ac6_10,
    "AC-16": _ac16,
    "AC-17": _ac17,
    "AC-21": _ac21,
    "AC-24": _ac24,
    "AU-2": _au2,
    "AU-3": _au3,
    "AU-3(1)": _au3,
    "AU-6": _au6,
    "AU-8": _au8,
    "AU-9": _au9,
    "AU-9(4)": _au9,
    "AU-10": _au10,
    "AU-11": _au11,
    "AU-12": _au12,
    "CA-7": _ca7,
    "CA-8": _ca8,
    "CM-2": _cm2,
    "CM-3": _cm3,
    "CM-6": _cm6,
    "CM-7": _cm7,
    "CM-8": _cm8,
    "IA-2": _ia2,
    "IA-2(1)": _ia2_1,
    "IA-3": _ia3,
    "IA-4": _ia4,
    "IA-5": _ia5,
    "IA-8": _ia8,
    "IA-9": _ia9,
    "IA-11": _ia11,
    "IR-4": _ir4,
    "RA-5": _ra5,
    "SA-11": _sa11,
    "SC-5": _sc5,
    "SC-7": _sc7,
    "SC-8": _sc8,
    "SC-8(1)": _sc8,
    "SC-12": _sc12,
    "SC-13": _sc13,
    "SC-23": _sc23,
    "SC-28": _sc28,
    "SI-3": _si3,
    "SI-4": _si4,
    "SI-4(4)": _si4,
    "SI-7": _si7,
    "SI-10": _si10,
    "SI-15": _si15,
    "SR-3": _sr3,
    "SR-11": _sr11,
}
