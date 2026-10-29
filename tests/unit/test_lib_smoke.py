"""Import smoke tests and the FDX error model / oracle placeholders."""

from __future__ import annotations

import agentbank_common
import agentbank_fdx
import agentbank_gateway
import agentbank_iso
import agentbank_ledger
from agentbank_common.oracle import OracleResult, StateSnapshot
from agentbank_fdx import FDX_INTERACTION_ID_HEADER, FdxError


def test_libs_import_with_version() -> None:
    for mod in (
        agentbank_common,
        agentbank_iso,
        agentbank_fdx,
        agentbank_ledger,
        agentbank_gateway,
    ):
        assert mod.__version__ == "0.1.0"


def test_fdx_error_model() -> None:
    assert FDX_INTERACTION_ID_HEADER == "x-fapi-interaction-id"
    err = FdxError(code="400", message="bad", debug_message="detail")
    assert err.to_dict() == {"code": "400", "message": "bad", "debugMessage": "detail"}
    assert "debugMessage" not in FdxError(code="400", message="bad").to_dict()


def test_oracle_placeholders() -> None:
    result = OracleResult(success=True, evidence={"k": 1})
    assert result.success is True
    assert result.evidence == {"k": 1}
    snap = StateSnapshot()
    assert snap.bank_db == {}
    assert snap.psp_egress == {}
