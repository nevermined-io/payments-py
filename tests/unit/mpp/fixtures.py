"""
Shared MPP wire fixtures for the unit tests.

``CHALLENGE_HEADER``, ``CHALLENGE_HEADER_WITH_COMMA_DESCRIPTION`` and
``MPPX_CREDENTIAL`` are hand-maintained fixtures modelled on real
``mppx@0.6.31`` output — inline string literals, not a vendored or regenerable
artifact, so treat them as illustrative of the wire shape rather than as a
pinned, reproducible capture. They are the same literals the TypeScript SDK
pins (``tests/unit/mpp/codec.test.ts`` in ``nevermined-io/payments``), copied
rather than re-derived so the two SDKs cannot drift apart silently.

What IS pinned exactly, byte-for-byte, is the property that actually matters:
the challenge id is an HMAC over ``canonicalize(request)`` and ``opaque``, and
``challenge.request_encoded`` / ``challenge.opaque`` are asserted against these
exact strings — a silent re-encode of either one, which is what would actually
break settlement, is what these fixtures exist to catch. This SDK takes no
``mppx`` dependency, so these fixtures are the compatibility contract in lieu
of one.
"""

import base64
import json
from typing import Any, Optional

REQUEST_ENCODED = (
    "eyJjcmVkaXRzIjoiMiIsInBsYW5JZCI6IjQ0NzQyNzYzMDc2MDQ3NDk3NjQwMDgwMjMwMjM2Nzgx"
    "NDc0MTI5OTcwOTkyNzI3ODk2NTkzODYxOTk3MzQ3MTM1NjEzMTM1NTcxMDcifQ"
)
OPAQUE_ENCODED = (
    "eyJfbXBweF9zY29wZSI6IlBPU1QgL2FzayIsIm5vbmNlIjoiMTExMTExMTEtMjIyMi0zMzMzLTQ0"
    "NDQtNTU1NTU1NTU1NTU1In0"
)
CHALLENGE_ID = "CQszOngfvT1RIGSajipZJvg-lBCEDugWLDF7SD_w1og"

CHALLENGE_HEADER = (
    f'Payment id="{CHALLENGE_ID}", realm="api.nevermined.app", '
    'method="nevermined", intent="charge", '
    f'request="{REQUEST_ENCODED}", '
    'expires="2026-08-12T10:05:00.000Z", '
    f'opaque="{OPAQUE_ENCODED}"'
)

# A structured challenge with a comma inside a quoted auth-param value
# (``description``), placed BEFORE ``opaque`` so a naive comma split truncates
# the scheme mid-quote and silently drops ``opaque``.
CHALLENGE_HEADER_WITH_COMMA_DESCRIPTION = (
    f'Payment id="{CHALLENGE_ID}", realm="api.nevermined.app", '
    'method="nevermined", intent="charge", '
    f'request="{REQUEST_ENCODED}", '
    'expires="2026-08-12T10:05:00.000Z", '
    'description="Standard, non-refundable request", '
    f'opaque="{OPAQUE_ENCODED}"'
)

RECEIPT_HEADER = (
    "eyJtZXRob2QiOiJuZXZlcm1pbmVkIiwicmVmZXJlbmNlIjoiQ1Fzek9uZ2Z2VDFSSUdTYWppcFpK"
    "dmctbEJDRUR1Z1dMREY3U0RfdzFvZyIsInN0YXR1cyI6InN1Y2Nlc3MiLCJ0aW1lc3RhbXAiOiIy"
    "MDI2LTA4LTEyVDEwOjAwOjMwLjAwMFoifQ"
)


def b64url(raw: bytes) -> str:
    """Unpadded base64url, the shape every MPP field is carried in."""
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def b64url_json(value: Any) -> str:
    """Encode ``value`` the way a seller encodes a ``request=`` param."""
    return b64url(json.dumps(value).encode("utf-8"))


def decode_credential(credential: str) -> Any:
    """Decode a ``Payment <token68>`` credential back into its JSON body."""
    token68 = credential[len("Payment ") :]
    padded = token68 + "=" * (-len(token68) % 4)
    return json.loads(base64.urlsafe_b64decode(padded))


def mpp_credential_fixture(challenge_id: str, expires: Optional[str] = None) -> str:
    """Build a real MPP credential for the middleware tests.

    The middleware keys single-use and the in-flight guard on the credential's
    decoded ``challenge.id``, and refuses a credential that carries none — so a
    fixture has to be a real credential, not an arbitrary token68 string.
    """
    wire = {
        "challenge": {
            "id": challenge_id,
            "realm": "api.nevermined.app",
            "method": "nevermined",
            "intent": "charge",
            "request": "eyJjcmVkaXRzIjoiMiIsInBsYW5JZCI6IjEyMyJ9",
        },
        "payload": {"accessToken": "BASE64_MPP_TOKEN"},
    }
    if expires:
        wire["challenge"]["expires"] = expires
    return f"Payment {b64url(json.dumps(wire, separators=(',', ':')).encode('utf-8'))}"


def mppx_auth_param(name: str, value: str) -> str:
    """Mirror mppx's own ``authParam`` serializer (``Challenge.ts:316-319``):
    backslashes then quotes are escaped. Fixtures built with this are escaped
    the way the real backend actually emits them, not hand-waved."""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'{name}="{escaped}"'


def build_challenge_params(description: str) -> str:
    """A full structured challenge (sans ``"Payment "`` prefix) with a given
    ``description``."""
    return ", ".join(
        [
            mppx_auth_param("id", CHALLENGE_ID),
            mppx_auth_param("realm", "api.nevermined.app"),
            mppx_auth_param("method", "nevermined"),
            mppx_auth_param("intent", "charge"),
            mppx_auth_param("request", REQUEST_ENCODED),
            mppx_auth_param("description", description),
            mppx_auth_param("opaque", OPAQUE_ENCODED),
        ]
    )


def build_challenge_with_request(request_encoded: str) -> str:
    """A structurally complete challenge header carrying a caller-chosen
    ``request=`` value."""
    return (
        f'Payment id="{CHALLENGE_ID}", realm="api.nevermined.app", '
        'method="nevermined", intent="charge", '
        f'request="{request_encoded}", '
        'expires="2026-08-12T10:05:00.000Z", '
        f'opaque="{OPAQUE_ENCODED}"'
    )
