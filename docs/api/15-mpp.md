# MPP (Machine Payments Protocol)

MPP is a second payment framing over the unchanged Nevermined core: the **same
plan, the same delegation and the same credit burn** as [x402](11-x402.md),
negotiated with different HTTP headers.

| | x402 | MPP |
|---|---|---|
| Server asks for payment | `payment-required` header on a 402 | `WWW-Authenticate: Payment …` on a 402 |
| Client presents payment | `payment-signature` header | `Authorization: Payment …` |
| Server confirms | `payment-response` header | `Payment-Receipt` header |

Nothing else changes. A plan works on both, a delegation works on both, and the
credits burned for a request are identical either way.

!!! warning "Experimental"
    The MPP surface may change in a minor release. It is additive and default
    off — an application that does not opt in is unaffected.

---

## Seller: accept MPP on a route

Add `"mpp": True` to a route the FastAPI middleware already protects. With it
unset, the x402 path is untouched.

```python
from fastapi import FastAPI, Request
from payments_py import Payments, PaymentOptions
from payments_py.x402.fastapi import PaymentMiddleware

app = FastAPI()
payments = Payments.get_instance(PaymentOptions(nvm_api_key="nvm:..."))

app.add_middleware(
    PaymentMiddleware,
    payments=payments,
    routes={
        # Accepts BOTH protocols. The 402 advertises an MPP challenge and the
        # x402 payment-required header, so either buyer can pay it.
        "POST /ask": {"plan_id": PLAN_ID, "credits": 2, "mpp": True},
    },
)


@app.post("/ask")
async def ask(request: Request):
    context = request.state.payment_context
    # context.mpp is present only when the request was paid over MPP. It is an
    # MppPaymentFraming with three attributes: credential, resource, http_verb.
    return {"answer": "...", "paid_over": "mpp" if context.mpp else "x402"}
```

### Binding the challenge to the request body

`{"bind_body": True}` seals a `sha-256=<base64>` digest of the request body into
the challenge, so the paid retry must carry the same bytes:

```python
routes={"POST /ask": {"plan_id": PLAN_ID, "credits": 2, "mpp": {"bind_body": True}}}
```

`bind_body` is the only key the option accepts, and a typo raises at startup
rather than resolving to `False`: `{"bindBody": True}` would otherwise turn the
binding off silently, which is not a missing nicety — see the paragraph below for
what an unbound challenge lets a buyer do.

A request with **no body** binds the digest of zero bytes rather than nothing at
all. Leaving it unbound would let a buyer mint against an empty request and
attach any body they liked to the paid retry — the backend skips the comparison
when the challenge carries no digest, so "unbound" means the buyer decides
whether `bind_body` applies.

Reading the body in the middleware consumes the ASGI receive channel; the
middleware re-arms it, so your handler still sees exactly what the buyer sent.
No parser hook is needed (the TypeScript SDK's `captureRawBody` has no
counterpart here).

### What the middleware guarantees

- **Single use.** A credential buys exactly one response. A replay is answered
  with a 402 carrying `code: "BCK.MPP.0003"` and a *fresh* challenge, so the
  buyer can still make progress by paying again.
- **No concurrent double-spend within the process.** A second request presenting
  a credential already in flight gets `409 Conflict`. Verification burns
  nothing and settlement is idempotent, so without this guard N concurrent
  requests would each be served for a single burn.
- **Settlement only on a 2xx.** A handler that fails or refuses is never
  settled, and the credential stays unspent.

!!! danger "Both guards are process-local"
    They live in memory. A multi-worker `uvicorn`/`gunicorn` deployment is
    already several processes, so a credential can be replayed once per worker.
    Deployments that need a hard guarantee must add a shared store (e.g. Redis);
    this package does not provide one.

### Hooks

`PaymentMiddlewareOptions` works the same on both protocols, with one deliberate
difference: on MPP, `on_payment_error` **notifies** and the middleware keeps
ownership of the response, because a 402 without a fresh challenge leaves the
buyer unable to make progress. A hook that returns a `Response` still wins.

`on_payment_error` is **not** called for the credential-less opening request —
that is the first turn of every healthy payment cycle, and notifying there would
drown the rejections the hook exists to surface. It *is* called when an
`Authorization` header arrives carrying no `Payment` scheme, which means an
intermediary is rewriting it and the buyer is stuck in a silent retry loop.

`on_after_settle` receives what the backend says it **burned**, not what this
request would charge — and `0` for a settlement that failed. It fires for all
three settlement outcomes, so a ledger built on it can count them apart:

| Outcome | `credits` | Third argument |
|---|---|---|
| Settled | what the backend burned | the settlement response |
| Unknown — may have burned | the charged amount | `MppSettlementOutcomeUnknown` |
| Definitely not paid | `0` | `MppSettlementFailed` |

The third row is the one worth wiring: the resource was delivered and the seller
was not paid. Were it reported only as an absence, it would be indistinguishable
from a request that was never an MPP request at all.

---

## Buyer: pay an MPP endpoint

`payments.mpp.fetch` pays a challenged endpoint with the delegation you already
use for x402. No new plan, no new delegation, no new credential.

```python
from payments_py.mpp import MppFetchOptions
from payments_py.x402.types import DelegationConfig

result = payments.mpp.fetch(
    "POST",
    "https://agent.example/ask",
    MppFetchOptions(
        delegation_config=DelegationConfig(delegation_id=delegation_id),
        plan_id=plan_id,        # optional: refuse a challenge naming another plan
        max_credits="10",       # optional: budget for the WHOLE call
    ),
    json={"q": "hello"},
)

print(result.response.status_code, result.paid, result.receipt)
```

Keyword arguments beyond the options are handed to `requests.request`
unchanged (`headers`, `json`, `data`, `params`, `timeout`, `stream`, …).

### Reading the result honestly

| Field | Meaning |
|---|---|
| `response` | The final response — the paid one when a payment happened |
| `settled` | The endpoint returned a receipt that decoded and does not state failure |
| `paid` | `response.ok and settled` |
| `credentials_presented` | How many credentials went on the wire (0, 1 or 2) |
| `credits_presented` | Total credits the challenges named — an **upper bound** on what burned |
| `receipt` | The decoded `Payment-Receipt`, when there was one |

`ok=True, paid=False, credentials_presented=1` is a **routine** outcome, not an
exotic one: a seller whose handler streams has already sent its headers when
settlement runs, so no receipt can be attached. The credits were burned. Never
read that combination as "the payment did not happen" and retry.

`response.ok` is not optional either — a returned result does not mean the
request was paid for. Three dead ends return the 402 rather than raising: no
usable challenge on it, a retryable rejection with no challenge to retry
against, and the one re-challenge cycle spent.

### The retry contract

At most **one** re-challenge cycle is followed. On a retry-turn 402:

- **A code decides alone.** `BCK.MPP.0004` (expired) and `BCK.MPP.0005` (body
  digest mismatch) are retried against the fresh challenge; every other code —
  including a non-`BCK.MPP.*` one — is terminal.
- **With no code, freshness decides.** A challenge whose `id` differs from the
  one just presented is a real re-challenge and is retried once. The identical
  id replayed, an unparseable challenge, or an unreadable body are terminal.

Check `is_retryable_mpp_code(code)` rather than hardcoding that list.

### Errors, and knowing whether money left

```python
from payments_py.mpp import MppError, mpp_spend_of
from payments_py.common.payments_error import PaymentsError

try:
    result = payments.mpp.fetch(...)
except PaymentsError as err:
    # A guard refused to even attempt the call: a bad argument, a challenge
    # naming another plan, a body that cannot be replayed.
    ...
except MppError as err:
    # What the wire actually said: a rejected credential, a malformed
    # challenge, an MPP-disabled environment.
    spend = mpp_spend_of(err)
    if spend:
        # A credential was already on the wire. Do NOT blindly retry.
        log.warning("up to %s credits may have burned", spend.credits_presented)
```

`mpp_spend_of` returns a report **only** when at least one credential was
presented, so a non-`None` result always means money may have left. It reads the
report off `PaymentsError` too — a `max_credits` or `plan_id` guard can fire on
the re-challenge turn, after a credential has already gone out.

### Request bodies must be replayable

A generator, iterator or file-like `data=` cannot be resent, so it is refused
with a `PaymentsError` **at the point a retry would reuse it** — never before the
first request. An endpoint that never challenges sends such a body exactly once,
exactly like a plain `requests` call.

### `max_credits` is a budget for the call

A seller names the price, and a re-challenge names it again. `max_credits` caps
the **sum**, so a re-challenge cannot collect the cap twice.

---

## Lower-level API

`payments.mpp` also exposes the three backend routes directly, for a seller not
using the FastAPI middleware:

```python
from payments_py.mpp import IssueMppChallengeParams, RedeemMppParams

issued = payments.mpp.issue_challenge(
    IssueMppChallengeParams(
        plan_id=PLAN_ID, credits=2, resource="/ask", http_verb="POST"
    )
)
# → {"challenge": "Payment id=…", "id": "…"} — send as WWW-Authenticate

verification = payments.mpp.verify_credential(
    RedeemMppParams(credential=header, resource="/ask", http_verb="POST")
)   # burns nothing

settlement = payments.mpp.settle_credential(
    RedeemMppParams(credential=header, resource="/ask", http_verb="POST")
)   # burns; settling the same credential twice burns once
```

Each `issue_challenge` returns a distinct challenge even for identical inputs —
the id doubles as the burn idempotency key, so two requests sharing one would
settle as a single burn.

!!! danger "Settlement failures are not all the same"
    `settle_credential` raises `MppSettlementOutcomeUnknownError` when the call
    ended without a definite answer — a read timeout, a connection torn down
    after the request was written, a 5xx/408, or a 2xx whose body could not be
    read. **The burn may already have committed.** Treating it like a definite
    failure silently corrupts your own accounting. A connect timeout, a refused
    connection and any 4xx are definite: nothing burned.

    Settlement gets a longer read deadline (90s) than every other SDK call,
    because it waits on an on-chain burn — a settle exceeding the generic 30s
    default was measured on staging. If it times out anyway, the recovery is to
    settle the same credential again: the challenge id doubles as the burn key,
    so a repeat settles onto the same single burn rather than charging twice.

---

## What the SDK never holds

The MPP signing secret and receipt signing live **only in the Nevermined
backend**. The SDK renames headers and forwards opaque strings; it reads exactly
one field out of a credential — `challenge.id` — because enforcing single use
needs a stable identity and the header bytes are not one (they are
buyer-malleable, and the backend collapses every variant onto a single burn).
