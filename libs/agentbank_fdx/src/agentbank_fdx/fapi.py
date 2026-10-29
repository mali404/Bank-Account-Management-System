"""In-process FAPI 2.0 checks (SPEC §5.2).

Keycloak is the identity server named in the deployment. These checks are the
same decisions the resource server has to make when a token arrives: DPoP
proofs (RFC 9449), pushed authorization requests (RFC 9126),
``private_key_jwt`` client authentication, and the mTLS sender constraint used
by bank-a. Interactive login at Keycloak is represented by the ``sub`` stored
with the pushed request. A raw ``/authorize`` query is rejected.

Nothing here copies the FDX specification. Tokens are testbed JWTs.
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass, field

import jwt
from cryptography.hazmat.primitives.asymmetric import ec

__all__ = [
    "AccessClaims",
    "FapiError",
    "FapiGate",
    "b64url",
    "generate_p256",
    "public_jwk",
    "sign_client_assertion",
    "sign_dpop",
    "thumbprint",
]

_ASSERTION_TYPE = "urn:ietf:params:oauth:client-assertion-type:jwt-bearer"
_REQUEST_URI_PREFIX = "urn:ietf:params:oauth:request_uri:"
_PROOF_TTL_S = 60
_TOKEN_TTL_S = 600


class FapiError(Exception):
    """An OAuth or FAPI failure with an HTTP status."""

    def __init__(self, status: int, error: str, description: str) -> None:
        super().__init__(description)
        self.status = status
        self.error = error
        self.description = description


@dataclass
class AccessClaims:
    """The claims a resource server needs from an access token."""

    sub: str
    client_id: str
    scope: str
    consent_id: str
    jkt: str
    cert_sha256: str


@dataclass
class _Client:
    client_id: str
    public_key: ec.EllipticCurvePublicKey
    cert_sha256: str | None


@dataclass
class _Pushed:
    client_id: str
    redirect_uri: str
    scope: str
    consent_id: str
    code_challenge: str
    sub: str


@dataclass
class _Code:
    client_id: str
    sub: str
    scope: str
    consent_id: str
    code_challenge: str
    expires_at: int


@dataclass
class FapiGate:
    """PAR, token issue, and sender-constrained verification for one bank."""

    issuer: str
    variant: str
    clock: Callable[[], int] = field(default_factory=lambda: lambda: int(time.time()))
    server_key: ec.EllipticCurvePrivateKey = field(default_factory=lambda: generate_p256())
    _clients: dict[str, _Client] = field(default_factory=dict)
    _pushed: dict[str, _Pushed] = field(default_factory=dict)
    _codes: dict[str, _Code] = field(default_factory=dict)
    _seen_jti: set[str] = field(default_factory=set)

    def register_client(
        self,
        client_id: str,
        public_key: ec.EllipticCurvePublicKey,
        cert_sha256: str | None = None,
    ) -> None:
        if self.variant == "mtls" and not cert_sha256:
            raise FapiError(
                400, "invalid_client", "bank-a clients require a certificate fingerprint"
            )
        self._clients[client_id] = _Client(client_id, public_key, cert_sha256)

    def push(
        self,
        *,
        client_assertion: str,
        client_assertion_type: str,
        audience: str,
        client_id: str,
        redirect_uri: str,
        scope: str,
        code_challenge: str,
        code_challenge_method: str,
        consent_id: str,
        sub: str,
    ) -> str:
        """Store an authorization request and return its ``request_uri``."""
        self._authenticate(client_assertion, client_assertion_type, audience, client_id)
        if code_challenge_method != "S256" or not code_challenge:
            raise FapiError(400, "invalid_request", "PKCE S256 is required")
        if not redirect_uri or not scope or not sub:
            raise FapiError(400, "invalid_request", "redirect_uri, scope and sub are required")
        request_uri = _REQUEST_URI_PREFIX + secrets.token_urlsafe(24)
        self._pushed[request_uri] = _Pushed(
            client_id=client_id,
            redirect_uri=redirect_uri,
            scope=scope,
            consent_id=consent_id,
            code_challenge=code_challenge,
            sub=sub,
        )
        return request_uri

    def authorize(self, request_uri: str | None) -> tuple[str, str, str]:
        """Issue a code for a pushed request. Anything else is rejected.

        Returns ``(code, redirect_uri, sub)``.
        """
        if not request_uri:
            raise FapiError(400, "invalid_request", "authorization requests must use PAR")
        pushed = self._pushed.pop(request_uri, None)
        if pushed is None:
            raise FapiError(400, "invalid_request", "unknown or reused request_uri")
        code = secrets.token_urlsafe(24)
        self._codes[code] = _Code(
            client_id=pushed.client_id,
            sub=pushed.sub,
            scope=pushed.scope,
            consent_id=pushed.consent_id,
            code_challenge=pushed.code_challenge,
            expires_at=self.clock() + _TOKEN_TTL_S,
        )
        return code, pushed.redirect_uri, pushed.sub

    def consent_of(self, code: str) -> str:
        pending = self._codes.get(code)
        return pending.consent_id if pending is not None else ""

    def issue_token(
        self,
        *,
        grant_type: str,
        client_assertion: str,
        client_assertion_type: str,
        audience: str,
        code: str = "",
        code_verifier: str = "",
        dpop: str | None = None,
        cert_sha256: str | None = None,
        htu: str = "",
    ) -> str:
        """Exchange a PAR-issued code, or mint a client-credentials token."""
        client = self._authenticate(client_assertion, client_assertion_type, audience)
        now = self.clock()
        if self.variant == "mtls":
            if not cert_sha256 or cert_sha256 != client.cert_sha256:
                raise FapiError(401, "invalid_token", "mTLS certificate does not match the client")
            jkt = ""
            bound_cert = client.cert_sha256 or ""
        else:
            proof = self._proof(dpop, "POST", htu, access_token=None, now=now)
            jkt = thumbprint(proof)
            bound_cert = ""
        if grant_type == "client_credentials":
            return self._access_token(
                client.client_id, client.client_id, "fdx:payments", "", jkt, bound_cert, now
            )
        if grant_type != "authorization_code":
            raise FapiError(400, "unsupported_grant_type", "unsupported grant_type")
        pending = self._codes.pop(code, None)
        if pending is None or pending.expires_at < now:
            raise FapiError(400, "invalid_grant", "authorization code is unknown or expired")
        if pending.client_id != client.client_id:
            raise FapiError(400, "invalid_grant", "authorization code was issued to another client")
        challenge = b64url(hashlib.sha256(code_verifier.encode("ascii")).digest())
        if challenge != pending.code_challenge:
            raise FapiError(400, "invalid_grant", "PKCE verifier does not match")
        return self._access_token(
            pending.sub, pending.client_id, pending.scope, pending.consent_id, jkt, bound_cert, now
        )

    def check_resource(
        self,
        method: str,
        htu: str,
        authorization: str | None,
        dpop: str | None,
        cert_sha256: str | None,
    ) -> AccessClaims:
        """Validate a resource request. Missing or replayed DPoP proofs fail."""
        if not authorization:
            raise FapiError(401, "invalid_token", "missing access token")
        scheme, _, token = authorization.partition(" ")
        now = self.clock()
        if self.variant == "mtls":
            if scheme not in {"Bearer", "DPoP"} or not token:
                raise FapiError(401, "invalid_token", "missing access token")
            claims = self._decode_access(token, now)
            if not claims.cert_sha256 or claims.cert_sha256 != (cert_sha256 or ""):
                raise FapiError(
                    401, "invalid_token", "token is not bound to the presented certificate"
                )
            return claims
        if scheme != "DPoP" or not token:
            raise FapiError(401, "invalid_token", "DPoP-bound access token required")
        if not dpop:
            raise FapiError(401, "invalid_dpop", "DPoP proof is required")
        claims = self._decode_access(token, now)
        proof = self._proof(dpop, method.upper(), htu, access_token=token, now=now)
        if thumbprint(proof) != claims.jkt:
            raise FapiError(401, "invalid_dpop", "DPoP key does not match the token confirmation")
        return claims

    def _authenticate(
        self,
        assertion: str,
        assertion_type: str,
        audience: str,
        expected_client: str = "",
    ) -> _Client:
        if assertion_type != _ASSERTION_TYPE or not assertion:
            raise FapiError(401, "invalid_client", "private_key_jwt is required")
        try:
            unverified = jwt.decode(assertion, options={"verify_signature": False})
        except jwt.InvalidTokenError as exc:
            raise FapiError(401, "invalid_client", "client assertion is not a JWT") from exc
        client_id = str(unverified.get("sub", ""))
        client = self._clients.get(client_id)
        if client is None or (expected_client and expected_client != client_id):
            raise FapiError(401, "invalid_client", "unknown client")
        if str(unverified.get("iss", "")) != client_id:
            raise FapiError(401, "invalid_client", "client assertion iss must equal sub")
        try:
            claims = jwt.decode(
                assertion,
                client.public_key,
                algorithms=["ES256"],
                audience=audience,
                options={"require": ["exp", "iat", "jti", "iss", "sub"]},
            )
        except jwt.InvalidTokenError as exc:
            raise FapiError(401, "invalid_client", "client assertion was rejected") from exc
        self._take_jti(str(claims["jti"]))
        return client

    def _proof(
        self,
        dpop: str | None,
        method: str,
        htu: str,
        access_token: str | None,
        now: int,
    ) -> dict[str, str]:
        if not dpop:
            raise FapiError(401, "invalid_dpop", "DPoP proof is required")
        try:
            header = jwt.get_unverified_header(dpop)
        except jwt.InvalidTokenError as exc:
            raise FapiError(401, "invalid_dpop", "DPoP proof is not a JWT") from exc
        if header.get("typ") != "dpop+jwt" or header.get("alg") != "ES256":
            raise FapiError(401, "invalid_dpop", "DPoP header is not ES256 dpop+jwt")
        jwk = header.get("jwk")
        if not isinstance(jwk, dict):
            raise FapiError(401, "invalid_dpop", "DPoP proof is missing a public JWK")
        try:
            public = jwk_to_public(jwk)
            claims = jwt.decode(dpop, public, algorithms=["ES256"], options={"verify_aud": False})
        except (FapiError, jwt.InvalidTokenError) as exc:
            if isinstance(exc, FapiError):
                raise
            raise FapiError(401, "invalid_dpop", "DPoP proof signature was rejected") from exc
        if str(claims.get("htm", "")) != method or str(claims.get("htu", "")) != htu:
            raise FapiError(401, "invalid_dpop", "DPoP htm or htu does not match the request")
        iat = int(claims.get("iat", 0))
        if abs(now - iat) > _PROOF_TTL_S:
            raise FapiError(401, "invalid_dpop", "DPoP proof is outside the time window")
        if access_token is not None:
            expected = b64url(hashlib.sha256(access_token.encode("ascii")).digest())
            if str(claims.get("ath", "")) != expected:
                raise FapiError(401, "invalid_dpop", "DPoP ath does not match the access token")
        self._take_jti(str(claims.get("jti", "")))
        return {str(key): str(value) for key, value in jwk.items() if isinstance(value, str)}

    def _take_jti(self, jti: str) -> None:
        if not jti or jti in self._seen_jti:
            raise FapiError(401, "invalid_dpop", "DPoP proof jti was replayed")
        self._seen_jti.add(jti)

    def _decode_access(self, token: str, now: int) -> AccessClaims:
        try:
            claims = jwt.decode(
                token,
                self.server_key.public_key(),
                algorithms=["ES256"],
                audience=self.issuer,
                options={"require": ["exp", "iat", "sub", "client_id"]},
            )
        except jwt.InvalidTokenError as exc:
            raise FapiError(401, "invalid_token", "access token was rejected") from exc
        if int(claims["exp"]) < now:
            raise FapiError(401, "invalid_token", "access token is expired")
        confirmation = claims.get("cnf")
        jkt = ""
        cert = ""
        if isinstance(confirmation, dict):
            jkt = str(confirmation.get("jkt", ""))
            cert = str(confirmation.get("x5t#S256", ""))
        return AccessClaims(
            sub=str(claims["sub"]),
            client_id=str(claims["client_id"]),
            scope=str(claims.get("scope", "")),
            consent_id=str(claims.get("consent_id", "")),
            jkt=jkt,
            cert_sha256=cert,
        )

    def _access_token(
        self,
        sub: str,
        client_id: str,
        scope: str,
        consent_id: str,
        jkt: str,
        cert_sha256: str,
        now: int,
    ) -> str:
        confirmation: dict[str, str] = {}
        if jkt:
            confirmation["jkt"] = jkt
        if cert_sha256:
            confirmation["x5t#S256"] = cert_sha256
        payload = {
            "iss": self.issuer,
            "aud": self.issuer,
            "sub": sub,
            "client_id": client_id,
            "scope": scope,
            "consent_id": consent_id,
            "cnf": confirmation,
            "iat": now,
            "exp": now + _TOKEN_TTL_S,
        }
        encoded = jwt.encode(payload, self.server_key, algorithm="ES256")
        return encoded if isinstance(encoded, str) else encoded.decode("ascii")


def generate_p256() -> ec.EllipticCurvePrivateKey:
    return ec.generate_private_key(ec.SECP256R1())


def public_jwk(private: ec.EllipticCurvePrivateKey) -> dict[str, str]:
    numbers = private.public_key().public_numbers()
    return {
        "kty": "EC",
        "crv": "P-256",
        "x": b64url(numbers.x.to_bytes(32, "big")),
        "y": b64url(numbers.y.to_bytes(32, "big")),
    }


def thumbprint(jwk: dict[str, str]) -> str:
    """RFC 7638 thumbprint for an EC P-256 public JWK."""
    canonical = json.dumps(
        {"crv": jwk["crv"], "kty": jwk["kty"], "x": jwk["x"], "y": jwk["y"]},
        separators=(",", ":"),
        sort_keys=True,
    )
    return b64url(hashlib.sha256(canonical.encode("ascii")).digest())


def jwk_to_public(jwk: dict[str, object]) -> ec.EllipticCurvePublicKey:
    if jwk.get("kty") != "EC" or jwk.get("crv") != "P-256" or "d" in jwk:
        raise FapiError(401, "invalid_dpop", "DPoP JWK must be a public P-256 key")
    x = jwk.get("x")
    y = jwk.get("y")
    if not isinstance(x, str) or not isinstance(y, str):
        raise FapiError(401, "invalid_dpop", "DPoP JWK is missing coordinates")
    point = b"\x04" + _fixed(b64url_decode(x)) + _fixed(b64url_decode(y))
    return ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), point)


def sign_client_assertion(
    private: ec.EllipticCurvePrivateKey, client_id: str, audience: str, now: int, jti: str
) -> str:
    payload = {
        "iss": client_id,
        "sub": client_id,
        "aud": audience,
        "iat": now,
        "exp": now + 60,
        "jti": jti,
    }
    encoded = jwt.encode(payload, private, algorithm="ES256")
    return encoded if isinstance(encoded, str) else encoded.decode("ascii")


def sign_dpop(
    private: ec.EllipticCurvePrivateKey,
    htm: str,
    htu: str,
    now: int,
    jti: str,
    access_token: str | None = None,
) -> str:
    payload: dict[str, object] = {"htm": htm, "htu": htu, "iat": now, "jti": jti}
    if access_token is not None:
        payload["ath"] = b64url(hashlib.sha256(access_token.encode("ascii")).digest())
    encoded = jwt.encode(
        payload,
        private,
        algorithm="ES256",
        headers={"typ": "dpop+jwt", "jwk": public_jwk(private)},
    )
    return encoded if isinstance(encoded, str) else encoded.decode("ascii")


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def b64url_decode(value: str) -> bytes:
    pad = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + pad)


def _fixed(raw: bytes) -> bytes:
    if len(raw) > 32:
        raise FapiError(401, "invalid_dpop", "DPoP coordinate is too long")
    return raw.rjust(32, b"\x00")
