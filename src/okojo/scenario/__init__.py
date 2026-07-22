"""Synthetic scenario generation for Okojo.

Everything in this package is fabricated. It replicates the *behavioral
patterns* of real sanctions-evasion networks (shell-entity rings, reused KYC
documents, shared devices, structured transfers, false RFI narratives) so the
co-pilot has realistic material to reason over — without any real identities,
addresses, or documents.
"""

from .generator import generate_scenario  # noqa: F401
