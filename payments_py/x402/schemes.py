"""X402 Protocol Supported Payment Schemes.

Nevermined's credit-based payment system uses smart contracts,
so we only support the "contract" scheme.
"""

from typing import Literal

SupportedSchemes = Literal["contract"]
