"""
The MPP wire format, hand-written so the SDK takes no protocol dependency.

The one rule that matters: the backend re-derives the challenge id as
``HMAC(secret, realm|method|intent|canonicalize(request)|expires|digest|opaque)``
from the fields carried inside the credential. ``request`` and ``opaque`` are
therefore passed through as the exact base64url strings received — this file
never re-encodes them.
"""

import base64
import binascii
import json
import re
from typing import Any, Dict, Optional, Tuple

from .errors import MppError
from .types import MppChallenge, MppChallengeRequest, MppReceipt

# A bare token (RFC 9110 5.6.2, used for auth-scheme names and auth-param keys).
_TOKEN = r"[!#$%&'*+\-.^_`|~0-9A-Za-z]+"
# Matches the start of a ``key=`` auth-param, i.e. a Payment challenge continuing.
_AUTH_PARAM_START = re.compile(rf"^{_TOKEN}\s*=")

# Matches the ``Payment`` scheme name at a genuine scheme boundary: start of the
# header value, or right after a top-level comma (RFC 9110 11.6.1 separates
# comma-separated challenges/credentials that way). Unanchored, ``Payment\s+``
# matches mid-token — ``XPayment abc``, ``NotPayment abc``,
# ``Bearer prepayment xyz`` — and also matches "Payment" text embedded inside a
# *different*, preceding scheme's quoted value (e.g.
# ``Digest username="my payment plan", …``), since plain whitespace alone is not
# a scheme boundary. Anchoring on comma-or-start (not bare whitespace) closes
# both: a scheme name is never preceded by an arbitrary space, only by the start
# of the header or the comma that separates it from what came before.
#
# This decides which protocol handles a request: ``extract_payment_scheme`` feeds
# the MPP-vs-x402 routing predicate in the middleware, so an unanchored match
# would divert an x402 buyer carrying a perfectly valid ``payment-signature``
# token, plus an unrelated ``Authorization`` header that happens to contain
# "payment" text, onto the MPP path and challenge them instead of serving the
# request.
_PAYMENT_SCHEME_BOUNDARY = re.compile(r"(?:^|,)\s*(Payment\s+)", re.IGNORECASE)

_PAYMENT_PREFIX = re.compile(r"^Payment\s+", re.IGNORECASE)


def _looks_like_structured_challenge(value: str) -> bool:
    """Whether ``value`` opens with a ``key=`` auth-param, i.e. it is a
    structured challenge rather than a bare token68 credential.

    Base64url PADDING is stripped before the test, and that is the whole point:
    ``=`` is both the padding character and what ends an auth-param key, so a
    padded credential (``…MH0=``) matched ``^{token}=`` and was classified as a
    challenge. RFC 7235 defines token68 as explicitly permitting trailing ``=``,
    so such a credential is well-formed on the wire — and the backend decodes it
    fine, which removes the justification for refusing it without a round-trip.
    A first-party buyer never hit this because :func:`build_credential_header`
    emits unpadded, so every test built its input the same way.
    """
    return bool(_AUTH_PARAM_START.match(value.rstrip("=")))


_TRAILING_COMMA = re.compile(r",\s*$")
_KEY_CHARS = re.compile(r"[a-zA-Z0-9_-]")
_SPACE_OR_COMMA = re.compile(r"[\s,]")
_SPACE = re.compile(r"\s")


def _find_structured_challenge_end(rest: str) -> int:
    """Find where a structured challenge's auth-param list ends within ``rest``
    (the content right after ``"Payment "``).

    Scans quote- and escape-aware so neither a comma nor a ``\\"`` inside a
    ``"…"`` value is mistaken for a boundary. mppx serializes quoted values by
    escaping backslashes and quotes (``Challenge.ts:316-319``), so a
    seller-supplied ``description`` like ``5" screen replacement plan`` wire-
    encodes as ``description="5\\" screen replacement plan"``. A scanner that
    toggles quote state on every literal ``"`` — escaped or not — desyncs on
    that ``\\"``, stays stuck "inside" a quote for the rest of the header, and
    swallows a genuine trailing scheme. This mirrors mppx's own reference
    parser's ``escaped`` flag (``Challenge.ts:362-379``) rather than inventing
    new semantics.

    A top-level (non-quoted, non-escaped) comma only ends the scheme if what
    follows it does NOT itself look like a continuing ``key=value`` auth-param —
    which is also how a following literal ``"Payment "`` (the merged-challenge
    case) is recognized as a new scheme: "Payment" followed by whitespace never
    matches ``_AUTH_PARAM_START``, since that requires ``=`` immediately (modulo
    optional whitespace) after the leading token.

    An unterminated quote is not an error here: the loop simply runs out of
    input without finding a boundary and falls back to treating the whole
    remainder as this scheme — a safe, total (never-raising) O(n) fallback.
    """
    in_quotes = False
    escaped = False
    for i, ch in enumerate(rest):
        if in_quotes:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_quotes = False
            continue
        if ch == '"':
            in_quotes = True
            continue
        if ch == "," and not _AUTH_PARAM_START.match(rest[i + 1 :].lstrip()):
            return i
    return len(rest)


def extract_payment_scheme(header_value: str) -> Optional[str]:
    """Extract the ``Payment`` scheme from a header value that may carry several
    schemes comma-separated (RFC 9110 11.6.1).

    The ``Payment`` scheme takes one of two shapes on our wire: a bare token68
    credential (``Payment <base64url>``, which cannot itself contain a comma or
    a quote) or a structured challenge (``Payment id="...", realm="...", ...``,
    comma-separated ``key="value"`` auth-params, where a value MAY contain a
    comma). Bounding the match at the next literal ``"Payment "`` occurrence — or
    at end-of-string otherwise — corrupts the first shape whenever a *different*
    trailing scheme follows: e.g. ``Payment <token>, Bearer <jwt>`` would extract
    the whole remainder including the trailing scheme. Bounding a structured
    challenge with a naive, quote-unaware comma split corrupts the second shape
    whenever a value contains a comma: it truncates mid-quote and silently drops
    every param after it. Instead: a bare token68 is bounded by its first
    top-level comma; a structured challenge is bounded by
    :func:`_find_structured_challenge_end`'s quote-aware scan.
    """
    scheme_match = _PAYMENT_SCHEME_BOUNDARY.search(header_value)
    if not scheme_match:
        return None

    # Group 1 ("Payment\s+") is the tail of the whole match, so the full match's
    # end position is also where the captured keyword ends; its start is offset
    # back by the keyword's own length, which skips the leading
    # comma/whitespace the boundary alternation consumed.
    keyword = scheme_match.group(1)
    content_start = scheme_match.end()
    start = content_start - len(keyword)
    rest = header_value[content_start:]

    if not _looks_like_structured_challenge(rest):
        # Bare token68 credential: bounded by its first top-level comma, since a
        # token68 cannot itself contain one (or a quote, so no quote-tracking is
        # needed here).
        comma_index = rest.find(",")
        end = len(header_value) if comma_index == -1 else content_start + comma_index
        return header_value[start:end].strip()

    end = content_start + _find_structured_challenge_end(rest)
    return _TRAILING_COMMA.sub("", header_value[start:end]).strip()


def _b64url_decode(encoded: str) -> bytes:
    """Decode unpadded base64url. Raises ``binascii.Error`` on input that cannot
    be decoded at all."""
    padded = encoded + "=" * (-len(encoded) % 4)
    return base64.urlsafe_b64decode(padded)


def _b64url_encode(raw: bytes) -> str:
    """Encode to unpadded base64url — the shape every MPP field is carried in."""
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def extract_credential_challenge_id(credential: str) -> Optional[str]:
    """The stable identity of a credential: the challenge id it carries.

    The header bytes are NOT that identity. ``_PAYMENT_SCHEME_BOUNDARY`` is
    case-insensitive and :func:`extract_payment_scheme` returns the matched
    slice verbatim, so ``Payment x``, ``payment x`` and ``Payment  x`` are three
    different strings for one credential — and the body is base64url of JSON the
    BUYER assembles, so re-ordering its keys yields more. The backend collapses
    every one of them onto a single burn, because its own idempotency key is the
    decoded challenge id. Anything at the seller edge enforcing single-use has to
    key on the same thing, or a buyer flips one byte of case and buys the
    response again.

    Returns the ``challenge.id`` a token68 credential decodes to, or ``None``
    when the credential cannot be decoded into one — a structured
    ``key="value"`` scheme (that shape is a challenge, never a credential),
    undecodable base64url JSON, or JSON without a non-empty string
    ``challenge.id``. The backend rejects all of those anyway; returning ``None``
    lets the caller refuse them without a round-trip rather than fall back to a
    key it cannot trust.
    """
    challenge = _decode_credential_challenge(credential)
    if challenge is None:
        return None
    challenge_id = challenge.get("id")
    return challenge_id if isinstance(challenge_id, str) and challenge_id else None


def _decode_credential_challenge(credential: str) -> Optional[Dict[str, Any]]:
    """The ``challenge`` object inside a token68 credential, or ``None`` when the
    credential cannot be decoded into one."""
    token68 = _PAYMENT_PREFIX.sub("", credential).strip()
    if not token68 or _looks_like_structured_challenge(token68):
        return None

    try:
        decoded = json.loads(_b64url_decode(token68))
    except (ValueError, binascii.Error):
        return None
    if not isinstance(decoded, dict):
        return None

    challenge = decoded.get("challenge")
    return challenge if isinstance(challenge, dict) else None


def extract_credential_challenge_expires(credential: str) -> Optional[str]:
    """The ``expires`` the credential's own sealed challenge carries, if any.

    Read for one purpose: the seller's single-use store has to remember a
    credential for at least as long as the backend would still honour it, and
    the challenge states that itself. Pinning the store to a constant copied
    from the backend instead means nothing here notices if that TTL is raised —
    the store would forget a credential the backend still accepts, and
    "single use" quietly becomes "replayable after the local TTL".

    Like :func:`extract_credential_challenge_id`, this trusts nothing: the value
    is buyer-supplied and unsigned, so its only use is to EXTEND how long we
    refuse a credential, never to shorten it.
    """
    challenge = _decode_credential_challenge(credential)
    if challenge is None:
        return None
    expires = challenge.get("expires")
    return expires if isinstance(expires, str) and expires else None


def _read_quoted_value(input_str: str, start: int) -> Tuple[str, int]:
    """Read a quoted-string value starting right after its opening ``"``,
    unescaping ``\\"`` to a literal ``"`` and ``\\\\`` to a literal ``\\``
    (mirrors mppx's ``readQuotedAuthParamValue``, ``Challenge.ts:461-465``).

    An unterminated quote is not an error here (unlike mppx's reference parser,
    which throws): the loop runs out of input and returns whatever was
    accumulated, matching :func:`_find_structured_challenge_end`'s equally
    permissive fallback for the same input shape.
    """
    i = start
    value: list = []
    escaped = False
    while i < len(input_str):
        ch = input_str[i]
        i += 1
        if escaped:
            value.append(ch)
            escaped = False
            continue
        if ch == "\\":
            escaped = True
            continue
        if ch == '"':
            return "".join(value), i
        value.append(ch)
    return "".join(value), i


def _parse_auth_params(input_str: str) -> Dict[str, str]:
    """Split ``key="value", key2="value2"`` into a map.

    Quoted values are read escape-aware and unescaped
    (:func:`_read_quoted_value`), so a value may itself contain a comma, a quote
    (``\\"``) or a backslash (``\\\\``) without corrupting the param that follows
    it. Unquoted values are tolerated too.
    """
    params: Dict[str, str] = {}
    i = 0
    length = len(input_str)

    while i < length:
        while i < length and _SPACE_OR_COMMA.match(input_str[i]):
            i += 1
        if i >= length:
            break

        key_start = i
        while i < length and _KEY_CHARS.match(input_str[i]):
            i += 1
        key = input_str[key_start:i]
        if not key:
            break

        while i < length and _SPACE.match(input_str[i]):
            i += 1
        if i >= length or input_str[i] != "=":
            break
        i += 1
        while i < length and _SPACE.match(input_str[i]):
            i += 1

        if i < length and input_str[i] == '"':
            value, i = _read_quoted_value(input_str, i + 1)
        else:
            value_start = i
            while i < length and input_str[i] != ",":
                i += 1
            value = input_str[value_start:i].strip()

        params[key] = value

    return params


def _decode_base64url_json(encoded: str, context: str) -> Any:
    """Decode a base64url string as JSON, raising a typed :class:`MppError`
    rather than a raw ``JSONDecodeError`` / ``binascii.Error`` on malformed
    input.

    Garbage would otherwise escape as a bare decoding error that names neither
    MPP nor payment, invisible to a caller writing ``except MppError:`` exactly
    as our own docs tell them to.
    """
    try:
        return json.loads(_b64url_decode(encoded))
    except (ValueError, binascii.Error) as error:
        raise MppError(f"Could not decode the {context}: {error}") from error


def _is_valid_challenge_request_shape(value: Any) -> bool:
    """Validate a decoded ``request`` param's shape before it is trusted.

    The raw decode only guarantees valid JSON, not the right shape: a remote
    challenge's ``request=`` can decode to ``null``, an array, or ``{}``, all of
    which would otherwise sail through and reach ``payments.mpp.fetch`` with an
    unusable or missing ``plan_id``.

    ``planId`` is the field with the documented failure mode (an unusable or
    missing value reaching the mint) and is checked strictly: a non-empty
    string, full stop. ``agentId`` is unchecked structurally but IS load-bearing
    once present — the buyer helper forwards it straight into the token mint —
    so a wrong-typed value is rejected here rather than reaching that spend path.
    ``credits``, by contrast, is not what anything spends: the amount the backend
    re-derives comes from ``request_encoded``, forwarded byte-verbatim, so
    rejecting a perfectly reasonable JSON-number encoding of "credits" would
    make a valid third-party seller wholly unpayable over a field this SDK does
    not itself act on — it is coerced by :func:`_to_challenge_request` instead.
    """
    if not isinstance(value, dict):
        return False
    plan_id = value.get("planId")
    credits = value.get("credits")
    agent_id = value.get("agentId")
    if not isinstance(plan_id, str) or plan_id == "":
        return False
    # ``bool`` subclasses ``int``: a JSON ``true`` is not a credits amount.
    if isinstance(credits, bool) or not isinstance(credits, (str, int, float)):
        return False
    if agent_id is not None and not isinstance(agent_id, str):
        return False
    return True


def _format_credits(credits: Any) -> str:
    """Render a validated ``credits`` value as the decimal string the type
    promises. An integer-valued float renders without a trailing ``.0`` so a
    JSON ``5`` and a JSON ``5.0`` both read back as ``"5"``."""
    if isinstance(credits, str):
        return credits
    if isinstance(credits, float) and credits.is_integer():
        return str(int(credits))
    return str(credits)


def _to_challenge_request(shape: Dict[str, Any]) -> MppChallengeRequest:
    """Normalize a validated decoded request into :class:`MppChallengeRequest`'s
    declared shape, coercing a numeric ``credits`` to a decimal string."""
    return MppChallengeRequest(
        plan_id=shape["planId"],
        credits=_format_credits(shape["credits"]),
        agent_id=shape.get("agentId"),
    )


def parse_challenge_header(header_value: str) -> Optional[MppChallenge]:
    """Parse a ``WWW-Authenticate`` header into a challenge.

    Returns ``None`` when there is no usable ``Payment`` challenge to parse: the
    header carries no ``Payment`` scheme at all, OR the scheme is present but
    missing one of the structural auth-params
    (``id``/``realm``/``method``/``intent``/``request``) needed to even attempt
    decoding it. Both cases mean the same thing to a caller deciding whether to
    retry: there is nothing here to pay.

    A ``Payment`` scheme that has all of those structural params present, but
    whose ``request`` value fails to decode as JSON or decodes to something that
    is not a usable ``{planId, credits}`` object, raises a typed
    :class:`MppError` instead — that is a seller who tried to speak MPP and sent
    something broken, a distinct failure from "there is no challenge here to
    parse".
    """
    scheme = extract_payment_scheme(header_value)
    if not scheme:
        return None

    params = _parse_auth_params(_PAYMENT_PREFIX.sub("", scheme))
    challenge_id = params.get("id")
    realm = params.get("realm")
    method = params.get("method")
    intent = params.get("intent")
    request = params.get("request")
    if not challenge_id or not realm or not method or not intent or not request:
        return None

    decoded_request = _decode_base64url_json(request, "MPP challenge request parameter")
    if not _is_valid_challenge_request_shape(decoded_request):
        raise MppError(
            "The MPP challenge names a request parameter that is not a valid "
            "{ planId: string, credits: string | number, agentId?: string } object."
        )

    return MppChallenge(
        id=challenge_id,
        realm=realm,
        method=method,
        intent=intent,
        request=_to_challenge_request(decoded_request),
        request_encoded=request,
        expires=params.get("expires") or None,
        digest=params.get("digest") or None,
        opaque=params.get("opaque") or None,
        description=params.get("description") or None,
    )


def build_credential_header(challenge: MppChallenge, payload: Dict[str, Any]) -> str:
    """Build the ``Authorization: Payment …`` value for a challenge.

    Key order in the JSON is irrelevant — the server parses it — but the two
    base64url strings are emitted untouched, which is what keeps the HMAC valid.
    """
    wire_challenge: Dict[str, Any] = {
        "id": challenge.id,
        "realm": challenge.realm,
        "method": challenge.method,
        "intent": challenge.intent,
    }
    if challenge.expires:
        wire_challenge["expires"] = challenge.expires
    if challenge.digest:
        wire_challenge["digest"] = challenge.digest
    if challenge.description:
        wire_challenge["description"] = challenge.description
    if challenge.opaque:
        wire_challenge["opaque"] = challenge.opaque
    wire_challenge["request"] = challenge.request_encoded

    wire = {"challenge": wire_challenge, "payload": payload}
    encoded = _b64url_encode(json.dumps(wire, separators=(",", ":")).encode("utf-8"))
    return f"Payment {encoded}"


def _is_valid_receipt(value: Any) -> bool:
    """Validate a decoded ``Payment-Receipt`` body against
    :class:`MppReceipt`'s shape — mirrors
    :func:`_is_valid_challenge_request_shape`'s strictness for the same reason:
    without it, ``null``, an array, or ``{}`` all sail through and surface later
    as an untyped ``AttributeError`` on a field access, with nothing pointing
    back at the header that caused it."""
    if not isinstance(value, dict):
        return False
    method = value.get("method")
    reference = value.get("reference")
    status = value.get("status")
    timestamp = value.get("timestamp")
    return (
        isinstance(method, str)
        and isinstance(reference, str)
        and reference != ""
        and isinstance(status, str)
        and isinstance(timestamp, str)
    )


def parse_receipt_header(header_value: str) -> MppReceipt:
    """Decode a ``Payment-Receipt`` header value.

    Raises a typed :class:`MppError` on malformed input — undecodable base64url
    JSON, or JSON that decodes to something that is not a usable
    ``{method, reference, status, timestamp}`` object — rather than a raw
    decoding error or an untyped receipt. This function does not decide whether
    that failure is fatal for its caller (the receipt is "unsigned by design,
    and carries no balance", so a caller may reasonably treat a decode failure
    as non-fatal and simply omit the receipt); it only guarantees the failure is
    typed and raised at the boundary, not as a later ``AttributeError`` on a
    field access with nothing pointing back at the header that caused it — the
    same asymmetry :func:`parse_challenge_header` closes for ``request=``.
    """
    decoded = _decode_base64url_json(header_value.strip(), "MPP receipt")
    if not _is_valid_receipt(decoded):
        raise MppError(
            "The Payment-Receipt header is not a valid "
            "{ method: string, reference: string, status: string, timestamp: string } object."
        )
    return MppReceipt(
        method=decoded["method"],
        reference=decoded["reference"],
        status=decoded["status"],
        timestamp=decoded["timestamp"],
    )


__all__ = [
    "build_credential_header",
    "extract_credential_challenge_expires",
    "extract_credential_challenge_id",
    "extract_payment_scheme",
    "parse_challenge_header",
    "parse_receipt_header",
]
