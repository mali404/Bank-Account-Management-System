"""FDX-inspired API models (not FDX-certified; see SPEC §1.1).

Milestone M3 fills this package with the Pydantic models for the FDX-style
accounts/transactions/consents/payments resources. M0 ships the error model and
the FAPI interaction-id header constant used across the API surface.
"""

from __future__ import annotations

from .errors import FDX_INTERACTION_ID_HEADER, FdxError

__version__ = "0.1.0"

__all__ = ["FDX_INTERACTION_ID_HEADER", "FdxError"]
