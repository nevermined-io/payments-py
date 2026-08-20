"""
The buyer half of MPP: pay a challenged endpoint with an existing Nevermined
delegation.

The buyer learns nothing about MPP beyond calling this instead of
``requests.request``. The plan comes out of the challenge, the credential is
built from the challenge plus an MPP-domain access token, and the request is
retried once.

Two error families are used deliberately:

- :class:`PaymentsError` (``code='validation'``) for guards this call refuses to
  even attempt — a bad argument, a challenge that violates a caller-supplied
  constraint (``plan_id``, ``max_credits``), or a body that cannot be replayed.
  None of these mean a payment failed; nothing was ever attempted.
- :class:`MppError` (and its typed subclasses) for what the wire actually said:
  a rejected credential, a malformed challenge, an MPP-disabled environment. A
  caller branching on ``except MppError`` to mean "the payment failed" gets
  exactly that, and no more.
"""

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, FrozenSet, Optional, Union
from urllib.parse import urlsplit

import requests

from payments_py.common.payments_error import PaymentsError
from payments_py.x402.types import DelegationConfig, X402TokenOptions

from .codec import build_credential_header, parse_challenge_header, parse_receipt_header
from .errors import (
    MppError,
    MppSpendOutcomeUnknownError,
    MppSpendReport,
    is_retryable_mpp_code,
    to_mpp_error,
)
from .types import MppChallenge, MppReceipt

logger = logging.getLogger(__name__)

_DECIMAL_INTEGER_STRING = re.compile(r"^\d+$")

# Cap on how much of a 402's error body is buffered before parsing it.
#
# The body is seller-controlled and read purely to look for a ``code``, so a
# hostile or broken endpoint answering a 402 with an unbounded stream must not
# be able to exhaust the buyer.
#
# NOTE, and this is a real difference from the TypeScript SDK: ``requests``
# buffers a response body in full at ``request()`` time unless the caller passed
# ``stream=True``. When they did not, this cap bounds what is PARSED, not what
# was received. Pass ``stream=True`` to get the bound applied to the transfer
# itself.
#
# A truncated read of a body large enough to matter will usually not parse; if
# it does, the prefix necessarily contains the complete ``code`` object — a
# truncated prefix of one JSON object can only parse once its closing brace is
# inside the cap — so the classification is unchanged either way. The branch
# keys on the JSON parsing succeeding, never on "truncated implies unparseable",
# which is false: ``<complete JSON><whitespace><garbage>`` parses after
# truncation and raises before it.
MAX_ERROR_BODY_BYTES = 64 * 1024

# Receipt ``status`` values that state failure outright, lower-cased.
#
# ``MppReceipt.status`` is a seller-set string and this SDK deliberately does not
# try to recognize *success*: ``'success'`` is the only value with any agreement
# behind it, so treating an unrecognized ``'ok'``/``'completed'`` as failure
# would report an unpaid call that was in fact paid. The asymmetry is the point
# — an explicit negative is not an unknown vocabulary, and reporting
# ``paid=True`` for a receipt that says the settlement failed is wrong in the one
# direction this field must never be wrong.
#
# Only unambiguous negatives belong here; anything genuinely ambiguous stays
# unrecognized and is reported as settled, with ``receipt`` on the result for a
# caller that wants to judge for itself.
_EXPLICIT_FAILURE_RECEIPT_STATUSES: FrozenSet[str] = frozenset(
    {"failed", "failure", "declined", "error"}
)

#: Mints an MPP access token for a plan. Supplied by ``MppAPI``.
MppTokenMinter = Callable[..., Dict[str, Any]]


@dataclass
class MppFetchOptions:
    """Options for :func:`mpp_fetch` / ``MppAPI.fetch``.

    .. warning:: **Experimental.** The MPP buyer surface may change in a minor
       release.

    A request body must be replayable **if the endpoint may challenge the
    request**: a generator, iterator or file-like ``data=``, or an open handle
    inside ``files=``, raises a typed :class:`PaymentsError` once a 402 challenge
    actually requires a retry, since it cannot be resent. A request that is never
    challenged sends such a body exactly once, exactly like a plain ``requests``
    call.

    This helper mints ``nvm:erc4337`` access tokens only in this release — a
    buyer holding an ``nvm:card-delegation`` delegation cannot use it yet.
    """

    #: The delegation that backs the payment — the same one x402 uses.
    delegation_config: DelegationConfig
    #: Overrides the agent id the seller's challenge names — the minted token is
    #: addressed to this agent id instead of whatever the challenge carries.
    #: Unlike ``plan_id``, this is not a guard: a mismatch is not checked or
    #: refused, it simply replaces what the seller asked for. Leave unset to
    #: honor the challenge as issued.
    agent_id: Optional[str] = None
    #: Fail before minting if the challenge names a different plan than this.
    plan_id: Optional[str] = None
    #: Budget for the WHOLE call, not for one challenge: the helper refuses to
    #: mint whenever the credits named so far plus the credits this challenge
    #: asks for would exceed it. A seller unilaterally names the price, and a
    #: re-challenge names it again — a per-turn cap would therefore bound each
    #: turn at ``max_credits`` and the call at twice it, which is not what "cap"
    #: reads as. ``credits_presented`` on the result is the same running total,
    #: so the two always speak about the same number.
    #:
    #: Must be a non-negative integer (a decimal string or an int); anything
    #: else is refused with a :class:`PaymentsError` at entry, before the first
    #: request, rather than mid-flight on the first 402.
    max_credits: Optional[Union[str, int]] = None


@dataclass
class MppFetchResult:
    """What :func:`mpp_fetch` / ``MppAPI.fetch`` returns.

    .. warning:: **Experimental.** Fields may be added or change meaning in a
       minor release.
    """

    #: The final response — the paid one when a payment happened.
    response: requests.Response
    #: Whether the endpoint returned settlement evidence: a ``Payment-Receipt``
    #: that decoded cleanly and does not state failure outright. Never derived
    #: from the HTTP status. See :data:`_EXPLICIT_FAILURE_RECEIPT_STATUSES` for
    #: why ``receipt.status`` is read asymmetrically.
    settled: bool
    #: Whether a credential was presented AND the final response looks
    #: successful: ``response.ok and settled``. A 2xx with no receipt (a
    #: settlement that silently failed) and a non-2xx with a receipt
    #: (settle-then-error) are both ``paid=False`` — check ``settled`` and
    #: ``credentials_presented`` for the honest picture in either case.
    #:
    #: ``ok=True, paid=False, credentials_presented=1`` is a ROUTINE outcome,
    #: not an exotic one: a seller whose handler streams or flushes has already
    #: sent its headers when settlement runs, so ``Payment-Receipt`` cannot be
    #: attached to a response that is already on the wire. The credits were
    #: burned. Never read this combination as "the payment did not happen" and
    #: retry.
    paid: bool
    #: How many credentials were minted and presented to the endpoint during
    #: this call (0, 1 or 2). This is NOT the same as ``settled``:
    #: ``credentials_presented > 0`` with ``settled=False`` means the seller may
    #: already have burned credits for a credential whose fate is unknown to the
    #: caller — treat that as "do not blindly retry", not as "nothing happened".
    credentials_presented: int = 0
    #: TOTAL credits named by every challenge a credential was minted against
    #: during this call, as a decimal string — summed, not the last turn's
    #: amount, since a re-challenge is free to name a different price and the
    #: caller is accounting for the call. Present whenever
    #: ``credentials_presented > 0``.
    #:
    #: It is an **upper bound** on what may have burned, never a lower one. A
    #: seller that answers a retryable code while replaying the identical
    #: challenge id gets a second credential minted against that same challenge
    #: (a code decides alone — see :func:`mpp_fetch`), and against a seller that
    #: keys single-use on the challenge id, as this SDK's middleware does, that
    #: second credential is refused as a replay and burns nothing. The count is
    #: deliberately not lowered for it: this field answers "what could have
    #: left", and guessing which of a remote's credentials it honoured would
    #: answer a question the buyer cannot see.
    credits_presented: Optional[str] = None
    #: The decoded ``Payment-Receipt``, when the server returned one and it
    #: decoded cleanly. A malformed receipt never raises — it leaves this
    #: ``None`` (with a logged warning) rather than destroying a response the
    #: caller already paid for.
    receipt: Optional[MppReceipt] = field(default=None)


def _is_one_shot_stream(value: Any) -> bool:
    """Whether ``value`` is consumed by being read once."""
    if isinstance(value, (str, bytes, bytearray)):
        return False
    return hasattr(value, "read") or hasattr(value, "__next__")


def _files_hold_a_stream(files: Any) -> bool:
    """Whether any ``files=`` entry carries an open handle rather than bytes.

    ``requests`` encodes ``files=`` through ``RequestEncodingMixin._encode_files``,
    which calls ``fp.read()`` on each handle — so the SECOND encode gets an
    exhausted one and sends an empty part. Measured on this SDK's own dependency:
    the same ``{"f": ("a.txt", BytesIO(b"PAYLOAD…"))}`` encodes to 161 bytes with
    the payload and then 138 bytes without it.

    Every documented shape is walked, since the handle can sit at any of them:
    a bare ``fp``, or the ``(name, fp)`` / ``(name, fp, content_type)`` /
    ``(name, fp, content_type, headers)`` tuples, in either the dict or the
    list-of-pairs form. A ``bytes``/``str`` payload is replayable and stays
    allowed — that is the common case for a small in-memory upload.
    """
    if not files:
        return False
    entries = files.items() if isinstance(files, dict) else files
    for entry in entries:
        value = (
            entry[1] if isinstance(entry, (tuple, list)) and len(entry) == 2 else entry
        )
        if isinstance(value, (tuple, list)):
            # (name, fp[, content_type[, headers]]) — the handle is element 1.
            candidate = value[1] if len(value) > 1 else None
        else:
            candidate = value
        if candidate is not None and _is_one_shot_stream(candidate):
            return True
    return False


def _is_non_replayable_body(request_kwargs: Dict[str, Any]) -> bool:
    """Whether the request body can only be sent once.

    ``requests`` accepts a generator, an iterator or a file-like object as
    ``data=``, and open handles inside ``files=``; all of them are consumed by
    the first send, so replaying them on the retry would silently transmit an
    empty (or partial) body rather than raise — on the request that costs
    credits. ``str``, ``bytes``, a dict/list of form fields, ``json=`` and a
    ``files=`` whose payloads are ``bytes``/``str`` can all be sent again, so a
    retry is safe.

    ``files=`` used to be listed among the safe shapes and was not inspected at
    all, which is the narrower claim that let a buyer mint a credential, burn
    credits, and retry with an empty multipart part — ``paid=True``, no error,
    nothing delivered.
    """
    body = request_kwargs.get("data")
    if body is not None and not isinstance(body, (dict, list, tuple)):
        if _is_one_shot_stream(body):
            return True
    return _files_hold_a_stream(request_kwargs.get("files"))


def _states_failure(receipt: Optional[MppReceipt]) -> bool:
    """Whether a decoded receipt states outright that the settlement did not
    happen."""
    if receipt is None or not isinstance(receipt.status, str):
        return False
    return receipt.status.strip().lower() in _EXPLICIT_FAILURE_RECEIPT_STATUSES


def _origin_of(url: str) -> str:
    """The origin of ``url``, or the raw value when it does not parse — used
    only to label a remote error."""
    try:
        parts = urlsplit(str(url))
        if parts.scheme and parts.netloc:
            return f"{parts.scheme}://{parts.netloc}"
    except ValueError:
        pass
    return str(url)


def _try_parse_challenge(header_value: str) -> Optional[MppChallenge]:
    """Parse a challenge header, swallowing any decode failure into ``None``.

    Used only to peek at a re-challenge's freshness inside the retry gate — a
    garbled re-challenge is simply "not a fresh challenge", which the gate
    already treats as terminal. The FIRST challenge of a 402 is never parsed
    this leniently: see the guard around :func:`parse_challenge_header` in
    :func:`mpp_fetch`, which raises a typed error instead, since minting against
    a challenge this function could not even parse would be worse.
    """
    try:
        return parse_challenge_header(header_value)
    except MppError:
        return None


def _assert_valid_challenge_request(challenge: MppChallenge, url: str) -> None:
    """Refuse a challenge whose ``credits`` is not a decimal string before it is
    ever minted against.

    :func:`parse_challenge_header` guarantees ``credits`` is a string OR a number
    and coerces the number, so what survives to here and still needs refusing is
    a string that is not a non-negative integer — ``'2.5'``, ``'-1'``, ``'1e3'``,
    ``'abc'``. Each of those would otherwise reach ``int()`` in the cap
    comparison as a raw ``ValueError``, or the mint as a price nothing can
    account for.

    ``plan_id`` is NOT re-checked here: the codec already rejects a non-string or
    empty ``planId`` outright, so a second guard for it would be unreachable code
    that reads as coverage.
    """
    credits = challenge.request.credits if challenge.request else None
    if not isinstance(credits, str) or not _DECIMAL_INTEGER_STRING.match(credits):
        raise MppError(
            f"The MPP challenge from {_origin_of(url)} names a non-decimal-string "
            f"credits value ({credits!r}); refusing to mint."
        )


def _parse_max_credits(value: Optional[Union[str, int]]) -> Optional[int]:
    """Validate ``options.max_credits`` at entry and normalize it to an ``int``.

    At entry, not at the comparison: ``max_credits`` is a caller argument, and a
    caller mistake must surface before the first request rather than mid-flight
    on whatever 402 happens to arrive — and as a :class:`PaymentsError`, which is
    what this module documents for bad arguments, rather than the raw
    ``ValueError`` that ``int('abc')`` raises.
    """
    if value is None:
        return None

    def refuse() -> PaymentsError:
        return PaymentsError.validation(
            "max_credits must be a non-negative integer (decimal string or int), "
            f"got {value!r}"
        )

    if isinstance(value, bool):
        raise refuse()
    if isinstance(value, int):
        if value < 0:
            raise refuse()
        return value
    if isinstance(value, str) and _DECIMAL_INTEGER_STRING.match(value.strip()):
        return int(value.strip())
    raise refuse()


def _read_bounded_text(response: requests.Response) -> str:
    """Read at most :data:`MAX_ERROR_BODY_BYTES` of a response body as text.

    Iterates the body and stops at the cap instead of touching ``.text``, so an
    endpoint answering a 402 with an endless body cannot be used to exhaust the
    buyer. See the note on :data:`MAX_ERROR_BODY_BYTES` for what the bound does
    and does not cover when the caller did not pass ``stream=True``.
    """
    chunks = bytearray()
    for chunk in response.iter_content(chunk_size=8192):
        if not chunk:
            continue
        # Truncate the chunk that crosses the cap rather than retaining it
        # whole: the transport chooses the chunk size, so "stop after the chunk
        # that crossed" would let one huge chunk defeat the bound entirely.
        room = MAX_ERROR_BODY_BYTES - len(chunks)
        if len(chunk) >= room:
            chunks.extend(chunk[:room])
            break
        chunks.extend(chunk)
    return chunks.decode(response.encoding or "utf-8", errors="replace")


def _read_mpp_error_code(response: requests.Response) -> Dict[str, Any]:
    """Read the error body of a challenged retry.

    A retry that comes back 402 is either "your credential was refused"
    (terminal) or "here is a fresh challenge" (retryable once). An unreadable or
    non-JSON body — an HTML WAF/CDN page, a truncated response — is neither: it
    is treated as terminal by the caller, since it is not evidence of anything
    retryable.

    A body that is EMPTY or whitespace-only is not in that class. It is an
    ordinary HTTP shape — the one the opening 402 is free to use — and carries no
    code, so it is reported as "no code" rather than as unreadable. Reported as
    unreadable it would suppress the documented fresh-challenge retry against a
    seller that did nothing wrong, and blame a WAF that is not there. Truncated
    bodies are non-empty by construction, so this cannot loosen that path.
    """
    try:
        raw = _read_bounded_text(response)
    except Exception as err:  # noqa: BLE001 — any transport fault is "unreadable"
        return {
            "message": f"MPP 402 body could not be read: {err}",
            "body_unreadable": True,
        }

    if raw.strip() == "":
        return {"message": "MPP 402 carried no body"}

    try:
        body = json.loads(raw)
    except ValueError:
        return {
            "message": (
                "MPP 402 was not JSON (likely a proxy or WAF page): " f"{raw[:200]}"
            ),
            "body_unreadable": True,
        }

    if not isinstance(body, dict):
        return {"message": "MPP request failed"}

    # A non-compliant seller can send a body shaped ``{"error": {"reason": …}}``
    # — no ``message``, and ``error`` itself an object rather than a string.
    # Coerced to a string here, once, so every caller of this function (in
    # particular the terminal raise's ``message[:200]``) can treat ``message`` as
    # always a string instead of risking a raw TypeError.
    raw_message = body.get("message", body.get("error"))
    message = raw_message if isinstance(raw_message, str) else "MPP request failed"
    # ``code`` is only a code when it is a non-empty string. ``{"code": null}``
    # is a routine way to serialize "no code", and taking it literally would both
    # store a ``None`` in a field typed ``Optional[str]`` and skip the
    # fresh-challenge fallback — which is gated on "no code" — so a legitimate
    # re-challenge from such a seller would read as terminal.
    raw_code = body.get("code")
    code = raw_code if isinstance(raw_code, str) and raw_code != "" else None
    return {"code": code, "message": message}


def _as_spend_aware_error(
    err: BaseException, spend: MppSpendReport, url: str
) -> BaseException:
    """Attach spend accounting to whatever is escaping, and wrap a raw transport
    failure that happened with a credential already on the wire.

    **Nothing is attached when nothing was presented.** A report of
    ``credentials_presented=0`` is still a truthy object, so annotating a
    first-turn argument failure would send a caller following the documented
    ``if mpp_spend_of(err):`` pattern into the "credits may already be burned, do
    not retry" branch on a plain validation error — making the field useless for
    the one decision it exists to inform.

    With that, three cases:

    - An :class:`MppError` (or the :class:`PaymentsError` a caller-constraint
      guard raises on the re-challenge turn) is annotated and re-raised AS-IS:
      the type a caller branches on must not change just because money is now
      reported.
    - Anything else with a credential already presented becomes an
      :class:`MppSpendOutcomeUnknownError`, so it reaches the ``except MppError``
      handler this module documents instead of escaping as a raw transport error.
    - Anything else with nothing presented is re-raised untouched — nothing was
      spent, and dressing up a plain network fault would only obscure it.
    """
    if spend.credentials_presented == 0:
        return err
    if isinstance(err, (MppError, PaymentsError)):
        try:
            err.spend = spend
            return err
        except AttributeError:
            # An error that cannot carry the report (``__slots__``) would
            # otherwise recreate exactly the invisible-spend failure this
            # boundary exists to close. Fall through to the wrapper below, which
            # holds the report in its own field.
            pass

    origin = _origin_of(url)
    if isinstance(err, (MppError, PaymentsError)):
        message = (
            f"The MPP credential was sent to {origin} and the call then failed with "
            f"an error that could not carry its own spend report ({err}), so "
            f"{spend.credits_presented} credits may or may not have been burned. "
            "Do not blindly retry."
        )
    else:
        message = (
            f"The MPP credential was sent to {origin} but the request failed before "
            f"any response was read ({err}), so {spend.credits_presented} credits "
            "may or may not have been burned. Do not blindly retry."
        )
    return MppSpendOutcomeUnknownError(message, err, spend)


def mpp_fetch(
    mint_token: MppTokenMinter,
    method: str,
    url: str,
    options: MppFetchOptions,
    **request_kwargs: Any,
) -> MppFetchResult:
    """Perform the request, paying an MPP challenge if one comes back.

    ``request_kwargs`` are handed to :func:`requests.request` unchanged
    (``headers``, ``json``, ``data``, ``params``, ``timeout``, ``stream``, …),
    so the call reads like the plain request it replaces.

    At most one re-challenge cycle is followed: a seller that keeps challenging
    a freshly paid credential is not going to be satisfied by looping, and a
    loop would burn a credential per turn.

    The default on a retry-turn 402 is to STOP, not to pay again. **A code, when
    present, decides alone**: one :func:`is_retryable_mpp_code` accepts
    (``BCK.MPP.0004`` expired, ``BCK.MPP.0005`` body-digest mismatch) is
    retried, every other code is terminal — including a non-``BCK.MPP.*`` one,
    e.g. the ``network_error``/``http_500``-shaped code ``MppAPI._post`` can
    synthesize and this repo's own seller forwards. The challenge id is not
    consulted on that path, so a retryable code replaying the identical id does
    re-mint; ``max_credits``, not id-freshness, is what bounds what that can
    cost.

    **With no code**, freshness is the whole signal: a challenge whose ``id``
    differs from the one just presented is a real re-challenge and is retried
    once, while the identical id replayed, an unparseable challenge or an
    unreadable body are terminal — a credential already proven invalid is never
    paid for twice.

    What raises and what comes back as a 402
    ----------------------------------------

    Only a rejection the remote NAMED raises. Three dead ends RETURN the 402
    instead, because the response is evidence the caller may need and raising
    would discard it:

    1. A 402 with no USABLE ``Payment`` challenge (either turn): no
       ``WWW-Authenticate``, another scheme, or a ``Payment`` challenge missing
       a required param — :func:`parse_challenge_header` yields nothing for all
       three, so a seller that announced ``Payment`` and then sent it malformed
       lands here too, not only one that does not speak MPP.
       ``credentials_presented=0``.
    2. A retry-turn 402 that IS retryable but carries no challenge to retry
       against, so the next turn finds nothing to mint for.
    3. The one re-challenge cycle spent: two credentials presented and the
       seller still answering 402.

    In cases 2 and 3 a credential WAS presented and may have been burned, so the
    result is ``paid=False`` with a non-zero ``credentials_presented`` and the
    last 402 as ``response``. Checking ``response.ok`` is therefore not optional
    — a returned result does not mean the request was paid for.

    Every error raised after a credential was presented carries the same
    accounting as :class:`MppSpendReport`, readable with ``mpp_spend_of(error)``,
    including a transport failure on the credential-bearing retry (wrapped as
    :class:`MppSpendOutcomeUnknownError` so ``except MppError`` catches it).
    """
    max_credits = _parse_max_credits(options.max_credits)
    max_challenges = 2
    response = requests.request(method, url, **request_kwargs)
    credentials_presented = 0
    credits_presented_total = 0
    last_challenge_id: Optional[str] = None

    def spend() -> MppSpendReport:
        """The accounting as it stands right now — reported identically on the
        return and the raise paths."""
        return MppSpendReport(
            credentials_presented=credentials_presented,
            credits_presented=(
                str(credits_presented_total) if credentials_presented > 0 else None
            ),
            challenge_id=last_challenge_id,
        )

    for _attempt in range(max_challenges):
        if response.status_code != 402:
            break

        challenge_header = response.headers.get("www-authenticate")
        if not challenge_header:
            break

        # Everything from here to the end of the turn can raise AFTER a
        # credential has been presented on an earlier turn — and, past the mint,
        # after one has been presented on this one. A single boundary attaches
        # the accounting to whatever comes out, so no exit from this function is
        # silent about money.
        try:
            try:
                challenge = parse_challenge_header(challenge_header)
            except MppError as err:
                raise MppError(
                    f"The 402 from {_origin_of(url)} carried a malformed MPP "
                    f"challenge ({err}). No payment was attempted."
                ) from err
            if challenge is None:
                break
            _assert_valid_challenge_request(challenge, url)

            plan_id = challenge.request.plan_id
            if options.plan_id and options.plan_id != plan_id:
                raise PaymentsError.validation(
                    f"MPP challenge names plan {plan_id}, but plan "
                    f"{options.plan_id} was pinned by the caller"
                )

            # The cap bounds the CALL: what this challenge asks for is added to
            # what earlier turns already committed. Bounding each turn
            # separately would let a seller collect max_credits twice by
            # re-challenging once.
            credits = int(challenge.request.credits)
            if (
                max_credits is not None
                and credits_presented_total + credits > max_credits
            ):
                already = (
                    f" ({credits_presented_total} already presented on "
                    f"{credentials_presented} credential(s))"
                    if credentials_presented > 0
                    else ""
                )
                raise PaymentsError.validation(
                    f"MPP challenge asks for {challenge.request.credits} credits, "
                    f"which would take this call to "
                    f"{credits_presented_total + credits}, above the caller's cap "
                    f"of {max_credits}{already}"
                )

            # A retry resends the body verbatim. A generator, iterator or
            # file-like body is single-read — the first request above already
            # consumed it — so replaying it now would silently send nothing.
            # Checked here, at the point a retry is actually about to happen,
            # not before the (harmless) first attempt: whether this endpoint
            # ever challenges is not known ahead of time, and a streaming body
            # against a non-challenging endpoint is fine.
            if _is_non_replayable_body(request_kwargs):
                raise PaymentsError.validation(
                    "payments.mpp.fetch cannot retry a single-read request body "
                    "(a generator, iterator or file object): it cannot be "
                    "replayed, so the 402 challenge from this endpoint cannot be "
                    "answered. Pass a replayable body instead — str, bytes, a "
                    "form dict, or json=."
                )

            minted = mint_token(
                plan_id,
                options.agent_id or challenge.request.agent_id,
                X402TokenOptions(delegation_config=options.delegation_config),
            )
            access_token = minted["accessToken"]

            headers = dict(request_kwargs.get("headers") or {})
            existing_auth = next(
                (v for k, v in headers.items() if k.lower() == "authorization"), None
            )
            credential = build_credential_header(
                challenge, {"accessToken": access_token}
            )
            # Append, not replace: a caller authenticating to the resource
            # server with its own Authorization (the normal shape for a metered
            # API) must not have that credential stripped on the request that
            # costs money. Our own seller's extract_payment_scheme was hardened
            # for exactly this multi-scheme shape.
            for key in [k for k in headers if k.lower() == "authorization"]:
                del headers[key]
            headers["Authorization"] = (
                f"{credential}, {existing_auth}" if existing_auth else credential
            )
            retry_kwargs = {**request_kwargs, "headers": headers}

            # Counted BEFORE the request, not after: the credential is on the
            # wire as soon as the request is issued, so a failure here
            # (disconnect, DNS, a read timeout) must not report zero credentials
            # presented. The seller may already have verified and burned it.
            credentials_presented += 1
            credits_presented_total += credits
            last_challenge_id = challenge.id
            response = requests.request(method, url, **retry_kwargs)

            if response.status_code == 402:
                error_body = _read_mpp_error_code(response)
                code = error_body.get("code")
                message = error_body.get("message", "MPP request failed")
                body_unreadable = error_body.get("body_unreadable", False)

                is_fresh_challenge = False
                if code is None and not body_unreadable:
                    next_header = response.headers.get("www-authenticate")
                    next_challenge = (
                        _try_parse_challenge(next_header) if next_header else None
                    )
                    is_fresh_challenge = (
                        next_challenge is not None and next_challenge.id != challenge.id
                    )

                if not is_retryable_mpp_code(code) and not is_fresh_challenge:
                    raise to_mpp_error(
                        code,
                        f"{_origin_of(url)} rejected the credential: {message[:200]}",
                    )
                # Otherwise the seller genuinely re-challenged (expired, a
                # digest mismatch, or — for a seller that sends no code,
                # including THIS SDK's middleware when verification fails for
                # infrastructure reasons — a fresh id); the loop takes one more
                # turn and mints a NEW credential against the fresh challenge —
                # the old one is not re-presented.
                continue
        except BaseException as err:
            raise _as_spend_aware_error(err, spend(), url) from err

        receipt_header = response.headers.get("payment-receipt")
        receipt: Optional[MppReceipt] = None
        if receipt_header:
            try:
                receipt = parse_receipt_header(receipt_header)
            except MppError as err:
                # The receipt is decorative ("unsigned by design, and carries no
                # balance" — see MppReceipt) and is optional precisely so it can
                # be absent. A failed decode must not destroy the response the
                # caller already paid for.
                logger.warning(
                    "[payments.mpp.fetch] payment may have succeeded but the "
                    "Payment-Receipt could not be decoded: %s",
                    err,
                )

        settled = receipt is not None and not _states_failure(receipt)
        return MppFetchResult(
            response=response,
            settled=settled,
            paid=response.ok and settled,
            credentials_presented=credentials_presented,
            credits_presented=(
                str(credits_presented_total) if credentials_presented > 0 else None
            ),
            receipt=receipt,
        )

    # Every dead end documented on this function lands here: no challenge to
    # pay, a retryable 402 with no challenge to retry against, or the
    # re-challenge budget spent. The accounting is what tells those apart — the
    # last two carry a non-zero credentials_presented.
    return MppFetchResult(
        response=response,
        settled=False,
        paid=False,
        credentials_presented=credentials_presented,
        credits_presented=(
            str(credits_presented_total) if credentials_presented > 0 else None
        ),
    )


__all__ = ["MppFetchOptions", "MppFetchResult", "MppTokenMinter", "mpp_fetch"]
