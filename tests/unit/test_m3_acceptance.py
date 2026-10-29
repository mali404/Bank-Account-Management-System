"""M3 acceptance: DPoP, PAR, private_key_jwt, consent limits, and a PSP payment."""

from __future__ import annotations

import hashlib
import time
from pathlib import Path
from typing import Any, cast

from cryptography.hazmat.primitives.asymmetric.ec import EllipticCurvePrivateKey
from fastapi.testclient import TestClient
from httpx import Response

from agentbank_fdx.api import mount_fdx
from agentbank_fdx.errors import FDX_INTERACTION_ID_HEADER
from agentbank_fdx.fapi import (
    FapiGate,
    b64url,
    generate_p256,
    sign_client_assertion,
    sign_dpop,
)
from agentbank_ledger.api import create_bank_app
from agentbank_ledger.world import World

_ASSERTION = "urn:ietf:params:oauth:client-assertion-type:jwt-bearer"
_SCOPE = "fdx:payments fdx:accounts:read"
_VERIFIER = "verifier-verifier-verifier-verifier-verifier"
_CLIENT = "psp-pfm"


def _challenge(verifier: str) -> str:
    return b64url(hashlib.sha256(verifier.encode("ascii")).digest())


def _fund(world: World) -> str:
    debtor = world.bank("bank-b")
    creditor = world.bank("bank-a")
    debtor.add_customer("Alice Example", "alice@bank-b.test")
    creditor.add_customer("Landlord Example", "landlord@bank-a.test")
    account = debtor.add_account("alice@bank-b.test", "DDA", "200000001")
    creditor.add_account("landlord@bank-a.test", "DDA", "100000001")
    debtor.deposit(account, 1_000_000, "OPENING")
    creditor.deposit("bank-a:100000001", 1_000_000, "OPENING")
    return account


def _client(
    world: World, bank_id: str = "bank-b"
) -> tuple[TestClient, EllipticCurvePrivateKey, EllipticCurvePrivateKey, str | None]:
    bank = world.bank(bank_id)
    gate = FapiGate(issuer=f"https://{bank.bank_id}.test", variant=bank.profile.fapi_variant)
    signing = generate_p256()
    dpop_key = generate_p256()
    cert = "cert-fingerprint-bank-a" if gate.variant == "mtls" else None
    gate.register_client(_CLIENT, signing.public_key(), cert_sha256=cert)
    app = create_bank_app(bank)
    mount_fdx(app, bank, gate)
    return TestClient(app), signing, dpop_key, cert


def _access_token(
    client: TestClient,
    signing: EllipticCurvePrivateKey,
    dpop_key: EllipticCurvePrivateKey,
    cert: str | None,
    consent_id: str,
    sub: str,
) -> str:
    now = int(time.time())
    par_url = "http://testserver/oauth/par"
    pushed = client.post(
        "/oauth/par",
        data={
            "client_assertion": sign_client_assertion(
                signing, _CLIENT, par_url, now, f"par-{consent_id}-{now}"
            ),
            "client_assertion_type": _ASSERTION,
            "client_id": _CLIENT,
            "redirect_uri": "https://psp-pfm.test/cb",
            "scope": _SCOPE,
            "code_challenge": _challenge(_VERIFIER),
            "code_challenge_method": "S256",
            "consent_id": consent_id,
            "sub": sub,
        },
    )
    assert pushed.status_code == 200, pushed.text
    granted = client.get("/oauth/authorize", params={"request_uri": pushed.json()["request_uri"]})
    assert granted.status_code == 200, granted.text
    token_url = "http://testserver/oauth/token"
    headers = {
        "DPoP": sign_dpop(dpop_key, "POST", token_url, now, f"dpop-token-{consent_id}-{now}"),
    }
    if cert:
        headers["X-Client-Cert-Sha256"] = cert
    issued = client.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": granted.json()["code"],
            "code_verifier": _VERIFIER,
            "client_assertion": sign_client_assertion(
                signing, _CLIENT, token_url, now, f"tok-{consent_id}-{now}"
            ),
            "client_assertion_type": _ASSERTION,
        },
        headers=headers,
    )
    assert issued.status_code == 200, issued.text
    return str(issued.json()["access_token"])


def _resource(
    client: TestClient,
    dpop_key: EllipticCurvePrivateKey,
    token: str,
    method: str,
    path: str,
    cert: str | None,
    jti: str,
    **kwargs: Any,
) -> Response:
    htu = "http://testserver" + path
    incoming = kwargs.pop("headers", {})
    headers: dict[str, str] = {}
    if isinstance(incoming, dict):
        headers = {str(key): str(value) for key, value in incoming.items()}
    headers["Authorization"] = f"DPoP {token}"
    headers["DPoP"] = sign_dpop(dpop_key, method, htu, int(time.time()), jti, access_token=token)
    if cert:
        headers["X-Client-Cert-Sha256"] = cert
    sent = client.request(method, path, headers=headers, **kwargs)
    return cast(Response, sent)


def test_token_without_dpop_is_rejected(tmp_path: Path) -> None:
    world = World.create(tmp_path)
    account = _fund(world)
    client, signing, dpop_key, cert = _client(world)
    consent = world.bank("bank-b").grant_consent(
        _CLIENT, "alice@bank-b.test", _SCOPE, limits_json='{"perPaymentMinor": 50000}'
    )
    token = _access_token(client, signing, dpop_key, cert, consent, "alice@bank-b.test")
    bare = client.get("/fdx/v6/accounts", headers={"Authorization": f"DPoP {token}"})
    assert bare.status_code == 401
    bearer = client.get("/fdx/v6/accounts", headers={"Authorization": f"Bearer {token}"})
    assert bearer.status_code == 401
    ok = _resource(client, dpop_key, token, "GET", "/fdx/v6/accounts", cert, "accounts-once")
    assert ok.status_code == 200
    assert ok.json()["accounts"][0]["accountId"] == account


def test_replayed_dpop_is_rejected(tmp_path: Path) -> None:
    world = World.create(tmp_path)
    _fund(world)
    client, signing, dpop_key, cert = _client(world)
    consent = world.bank("bank-b").grant_consent(_CLIENT, "alice@bank-b.test", _SCOPE)
    token = _access_token(client, signing, dpop_key, cert, consent, "alice@bank-b.test")
    htu = "http://testserver/fdx/v6/accounts"
    proof = sign_dpop(dpop_key, "GET", htu, int(time.time()), "same-jti", access_token=token)
    headers = {"Authorization": f"DPoP {token}", "DPoP": proof}
    assert client.get("/fdx/v6/accounts", headers=headers).status_code == 200
    replay = client.get("/fdx/v6/accounts", headers=headers)
    assert replay.status_code == 401


def test_authorize_without_par_is_rejected(tmp_path: Path) -> None:
    world = World.create(tmp_path)
    client, signing, _dpop, _cert = _client(world)
    rejected = client.get(
        "/oauth/authorize", params={"client_id": _CLIENT, "response_type": "code"}
    )
    assert rejected.status_code == 400
    assert rejected.json()["error"] == "invalid_request"
    secret = client.post(
        "/oauth/token",
        data={
            "grant_type": "client_credentials",
            "client_secret": "not-a-key",
            "client_assertion_type": _ASSERTION,
        },
    )
    assert secret.status_code == 401
    del signing


def test_consent_limit_and_revocation(tmp_path: Path) -> None:
    world = World.create(tmp_path)
    account = _fund(world)
    client, signing, dpop_key, cert = _client(world)
    bank = world.bank("bank-b")
    consent = bank.grant_consent(
        _CLIENT, "alice@bank-b.test", _SCOPE, limits_json='{"perPaymentMinor": 1000}'
    )
    token = _access_token(client, signing, dpop_key, cert, consent, "alice@bank-b.test")
    body = {
        "consent_id": consent,
        "debtor_account_id": account,
        "creditor_name": "Landlord Example",
        "creditor_account": "100000001",
        "creditor_routing": world.bank("bank-a").routing,
        "amount_minor": 2_000,
        "remittance": ["RENT"],
    }
    over = _resource(
        client, dpop_key, token, "POST", "/fdx/v6/payments", cert, "over-limit", json=body
    )
    assert over.status_code == 403
    assert over.json()["code"] == "CONSENT_LIMIT"
    bank.revoke_consent(consent, "alice@bank-b.test")
    small = dict(body, amount_minor=500)
    revoked = _resource(
        client, dpop_key, token, "POST", "/fdx/v6/payments", cert, "revoked", json=small
    )
    assert revoked.status_code == 403
    assert revoked.json()["code"] == "CONSENT_REVOKED"
    assert world.bank("bank-a").notifications() == []


def test_psp_payment_notifies_creditor(tmp_path: Path) -> None:
    world = World.create(tmp_path)
    account = _fund(world)
    client, signing, dpop_key, cert = _client(world)
    bank = world.bank("bank-b")
    consent = bank.grant_consent(
        _CLIENT, "alice@bank-b.test", _SCOPE, limits_json='{"perPaymentMinor": 25000}'
    )
    token = _access_token(client, signing, dpop_key, cert, consent, "alice@bank-b.test")
    paid = _resource(
        client,
        dpop_key,
        token,
        "POST",
        "/fdx/v6/payments",
        cert,
        "pay-rent",
        json={
            "consent_id": consent,
            "debtor_account_id": account,
            "creditor_name": "Landlord Example",
            "creditor_account": "100000001",
            "creditor_routing": world.bank("bank-a").routing,
            "amount_minor": 4_200,
            "remittance": ["RENT"],
        },
        headers={FDX_INTERACTION_ID_HEADER: "11111111-1111-1111-1111-111111111111"},
    )
    assert paid.status_code == 201, paid.text
    assert paid.json()["status"] == "COMPLETED"
    assert paid.headers[FDX_INTERACTION_ID_HEADER] == "11111111-1111-1111-1111-111111111111"
    notes = world.bank("bank-a").notifications()
    assert notes
    assert "BkToCstmrDbtCdtNtfctn" in notes[-1]
    assert world.check_invariants() == []


def test_bank_a_requires_the_client_certificate(tmp_path: Path) -> None:
    world = World.create(tmp_path)
    bank = world.bank("bank-a")
    bank.add_customer("Landlord Example", "landlord@bank-a.test")
    bank.add_account("landlord@bank-a.test", "DDA", "100000001")
    client, signing, dpop_key, cert = _client(world, "bank-a")
    assert cert
    consent = bank.grant_consent(_CLIENT, "landlord@bank-a.test", _SCOPE)
    token = _access_token(client, signing, dpop_key, cert, consent, "landlord@bank-a.test")
    missing = client.get("/fdx/v6/accounts", headers={"Authorization": f"Bearer {token}"})
    assert missing.status_code == 401
    present = client.get(
        "/fdx/v6/accounts",
        headers={"Authorization": f"Bearer {token}", "X-Client-Cert-Sha256": cert},
    )
    assert present.status_code == 200


def test_realms_name_the_fapi_profiles(repo_root: Path) -> None:
    import json

    bank_a = json.loads((repo_root / "deploy/keycloak/realms/bank-a.json").read_text())
    bank_b = json.loads((repo_root / "deploy/keycloak/realms/bank-b.json").read_text())
    bank_c = json.loads((repo_root / "deploy/keycloak/realms/bank-c.json").read_text())
    assert bank_a["clientPolicies"]["policies"][0]["profiles"] == ["fapi-2-security-profile"]
    assert bank_b["clientPolicies"]["policies"][0]["profiles"] == ["fapi-2-dpop-security-profile"]
    assert bank_c["clientPolicies"]["policies"][0]["profiles"] == ["fapi-2-dpop-security-profile"]
    for realm in (bank_a, bank_b, bank_c):
        ids = {client["clientId"] for client in realm["clients"]}
        assert ids == {"psp-pis", "psp-pfm", "psp-agg"}
        for client in realm["clients"]:
            assert client["clientAuthenticatorType"] == "client-jwt"
            assert "secret" not in client
