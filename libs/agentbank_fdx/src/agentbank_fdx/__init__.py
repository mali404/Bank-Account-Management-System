"""FDX-inspired API and FAPI 2.0 resource-server checks (not FDX-certified).

M0 shipped the error model and the interaction-id header. M3 adds the
resource routes and the DPoP, PAR, private_key_jwt, and mTLS checks.
Import those from ``agentbank_fdx.api`` and ``agentbank_fdx.fapi``.
"""

from __future__ import annotations

from .errors import FDX_INTERACTION_ID_HEADER, FdxError

__version__ = "0.1.0"

__all__ = ["FDX_INTERACTION_ID_HEADER", "FdxError"]
