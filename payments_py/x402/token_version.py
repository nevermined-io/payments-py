"""
The x402 access-token version ordinals.

A leaf module on purpose: ``token.py`` (which decodes a token to detect its
version) imports ``token_request.py`` (which gates the v3 binding on the same
ordinal), so the constants cannot live in either without a cycle.
"""

#: The access-token version the backend still mints by default. Its EIP-712
#: signature covers ``[from, sessionKeysProvider, sessionKeys, planId]`` only —
#: ``agentId``, ``resourceUrl`` and ``httpVerb`` sit outside it and there is no
#: nonce — so a v2 token is a bearer credential that settles more than once.
X402_TOKEN_VERSION_V2 = 2

#: The seller/resource-bound, single-use access token (nvm-monorepo#2646). Its
#: signature additionally covers ``agentId``, ``resourceUrl``, ``httpVerb`` and
#: a one-time ``nonce``; the FIRST ``POST /x402/settle`` consumes it and a
#: second settle of the same token fails with ``BCK.X402.0059``. ``verify()``
#: never consumes, so verify-then-settle is unchanged.
X402_TOKEN_VERSION_V3 = 3

__all__ = ["X402_TOKEN_VERSION_V2", "X402_TOKEN_VERSION_V3"]
