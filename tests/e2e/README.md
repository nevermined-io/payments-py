# E2E Tests for Payments Integration

This directory contains end-to-end (E2E) tests for payments integration in Python, which verify complete functionality with real network requests.

## Test Structure

### `test_payments_e2e.py`

Core payments E2E tests covering:

- **Plans**: Creating credits plans, time plans, and trial plans
- **Agents**: Registering agents and associating with payment plans
- **Subscriptions**: Ordering plans and checking balances
- **Agent Access**: Generating agent access tokens and validating requests

### `test_x402_e2e.py`

X402 Access Token E2E tests covering:

- **X402 Token Generation**: Creating X402 access tokens for delegated permissions
- **Permission Verification**: Verifying subscriber permissions without burning credits
- **Permission Settlement**: Settling (burning) credits on behalf of subscribers
- **ZeroDev Policies**: Testing delegated session key functionality
- **Credit Management**: Multiple verify/settle operations

### `a2a_e2e_test.py`

Basic A2A E2E tests covering:

- **Blocking flow**: Complete verification with credit burning
- **Invalid authentication**: Handling of incorrect bearer tokens
- **Non-blocking flow**: Asynchronous execution with polling

### `test_a2a_e2e.py`

Advanced A2A E2E tests covering:

- **Streaming**: Server-Sent Events with real-time updates
- **Webhooks**: Push notifications with authentication
- **Resubscription**: Reconnection to existing tasks
- **Cancellation**: Cancellation of tasks in progress
- **Credit scenarios**: Multiple credit burning test cases
- **Error handling**: Recovery from network failures

### `helpers/a2a_e2e_helpers.py`

Utilities and helpers for E2E tests:

- **A2AE2EUtils**: Utilities for HTTP requests and retries
- **A2AE2EFactory**: Factory for creating test objects
- **A2AE2EAssertions**: A2A-specific assertions
- **A2AE2EServerManager**: Test server management

## Running E2E Tests

### Prerequisites

```bash
# Install dependencies
pip install pytest pytest-asyncio httpx uvicorn

# Environment variables (optional)
export E2E_BUILDER_API_KEY="your-builder-key"
export E2E_SUBSCRIBER_API_KEY="your-subscriber-key"
```

### Execution Commands

```bash
# Run all E2E tests
pytest tests/e2e/ -v

# Run only payments tests
pytest tests/e2e/test_payments_e2e.py -v

# Run only X402 tests
pytest tests/e2e/test_x402_e2e.py -v

# Run only A2A tests
pytest tests/e2e/test_a2a_e2e.py -v

# Run specific test
pytest tests/e2e/test_x402_e2e.py::TestX402DelegationFlow::test_get_x402_access_token -v

# Skip E2E tests (if marked as 'slow')
pytest tests/ -m "not slow"

# Run with detailed logs
pytest tests/e2e/ -v -s --log-cli-level=INFO
```

## Verified Functionality

### ✅ Core Payment Flows

- [x] Plan creation (credits, time, trial)
- [x] Agent registration and management
- [x] Plan ordering and subscription
- [x] Balance checking and credit tracking
- [x] Agent access token generation

### ✅ X402 Delegated Permissions

- [x] X402 access token generation
- [x] Permission verification (dry-run)
- [x] Permission settlement (credit burning)
- [x] ZeroDev session key policies
- [x] Multiple verify operations without credit consumption
- [x] Sequential settlement operations

### ✅ A2A Payment Flows

- [x] Bearer token validation
- [x] Credit burning on final events
- [x] Payment error handling (401/402)
- [x] Different credit amounts

### ✅ A2A Execution Modes

- [x] Blocking: Waits until completion
- [x] Non-blocking: Returns immediately, polling for status
- [x] Streaming: Real-time Server-Sent Events

### ✅ A2A Advanced Features

- [x] Push notifications via webhooks
- [x] Webhook authentication (bearer, basic, custom)
- [x] Task resubscription
- [x] Task cancellation

### ✅ Robustness

- [x] Network timeout handling
- [x] Server failure recovery
- [x] Malformed JSON validation
- [x] Multiple load scenarios

## Test Configuration

### Environment Variables

```bash
TEST_ENVIRONMENT=staging_sandbox              # Test environment
TEST_SUBSCRIBER_API_KEY=your-subscriber-key   # Subscriber API key
TEST_BUILDER_API_KEY=your-builder-key         # Builder/Agent API key
E2E_BUILDER_API_KEY=test-builder-key          # A2A Builder API key
E2E_SUBSCRIBER_API_KEY=test-subscriber-key    # A2A Subscriber API key
```

### Test Ports

Tests use dynamic ports to avoid conflicts:

- **8001-8010**: Basic tests
- **8015-8025**: Advanced tests
- **Health checks**: Each server exposes `/health`

### Timeouts

- **Request timeout**: 15 seconds
- **Server startup**: 10 seconds
- **Polling interval**: 0.3 seconds
- **Max polling attempts**: 15

## Debugging

### Detailed Logs

```bash
# Run with full logs
pytest tests/e2e/ -v -s --log-cli-level=DEBUG

# See only payment logs
pytest tests/e2e/ -v -s --log-cli-level=INFO 2>&1 | grep -E "(E2E|Credits|Bearer)"
```

### Test Executors

Tests use mock executors that simulate real behavior:

- **E2ETestExecutor**: Basic behavior with configurable timing
- **E2EStreamingExecutor**: Multiple updates for streaming
- **MockE2EPaymentsService**: Mock payments service with realistic states

### Manual Verification

```bash
# Check server health (if running)
curl http://localhost:8001/health

# Check webhook server
curl http://localhost:8002/webhooks
```

## Limitations

1. **Mock Servers**: Tests use mock services, not the real Nevermined backend
2. **Local Network**: All requests are local (localhost)
3. **Reduced Timeouts**: Timeouts optimized for tests, not production
4. **Parallelization**: Tests not optimized for parallel execution

## Troubleshooting

### Error: Port Already in Use

```bash
# Find process using the port
lsof -i :8001

# Kill process if necessary
kill -9 <PID>
```

### Error: Server Not Ready

- Increase `SERVER_STARTUP_TIMEOUT` in config
- Check for port conflicts
- Review server logs

### Error: Credit Burning Not Detected

- Verify executor publishes events with `metadata.creditsUsed`
- Check that `TaskStatusUpdateEvent` has `final=True`
- Review `PaymentsRequestHandler` logs

## Visa e2e fixture (local only, not for CI)

> **Do not enable this suite in CI.** The fixture is a real Visa Agentic delegation with a finite `durationSecs`, and refreshing it requires a manual browser flow. If CI ran it on every PR the delegation would eventually expire mid-week and start blocking unrelated work. The suite is gated by three env vars and is `pytest.mark.skipif`'d when any are missing or malformed, so the default CI behavior is "skipped, exit 0" — that's intentional.

The Visa Agentic-Tokens flow involves two browser-only steps that the SDK cannot perform programmatically:

1. **Card enrolment** — PAN entry through the VGS Collect iframe in the Nevermined webapp.
2. **Delegation creation** — WebAuthn/passkey device-binding ceremony embedded by Visa VTS, producing a single-use `assuranceData` blob.

The plan itself also has to exist beforehand: a Visa delegation is bound to a single plan at creation time (backend rejects with `BCK.VISA.0015` otherwise), so creating a fresh plan per run would mint the access token against a planId the delegation isn't bound to and the verify step would fail.

### What the suite asserts (and what it deliberately omits)

| Step | Asserted? | Notes |
|---|---|---|
| Plan creation | ❌ | Plan must pre-exist; see above |
| `list_payment_methods` returns the visa PM | ✅ | |
| `get_x402_access_token` mints against `delegation_id` + `plan_id` | ✅ | |
| `verify_permissions` returns `is_valid=True`, `network='visa'` | ✅ | Read-only — does not charge the card |
| `settle_permissions` returning `credits_redeemed='2'` | ❌ | Omitted on purpose — the sandbox card providers (Stripe sandbox, Visa sandbox CMP) do not actually charge. End-to-end settlement is validated separately at the platform level. |

### One-time provisioning

> All three of plan, card, and delegation are committed to a single `(subscriber, planId)` pair on the backend, so the accounts and ordering matter:
> - **Plan** must be created by the builder whose key is set as `TEST_BUILDER_API_KEY` in `conftest.py` (or via the env var override). That builder ends up as the seller of the plan and is also the account the e2e's `verify_permissions` runs as.
> - **Card + delegation** must be enrolled by the subscriber whose key is `TEST_SUBSCRIBER_API_KEY`.

1. **Create the plan** — as the builder, register a fiat credits plan (via the webapp builder UI or a one-shot script using `payments.plans.register_credits_plan({...}, get_fiat_price_config(1_000_000, builder_address), get_dynamic_credits_config(10, 1, 2))`). Capture the returned `planId` (long decimal uint256 string).

2. **Enrol the Visa card** — open the Nevermined webapp against staging (`https://nevermined.dev`) and sign in as the SDK test subscriber. On `/payment-methods`, click **Enroll with Visa** and enter a VTS-registered sandbox PAN — e.g. `4622943123121387`, CVC `123`, expiry `12/27`. Capture the `paymentMethodId` (`vat_…`) from `POST /api/v1/delegation/enroll-visa` in the network panel.

3. **Create the delegation** — from the same card row, click **Create delegation**, pick the plan from step 1, set any spending limit + a duration that matches how long you want the fixture alive, then complete the WebAuthn ceremony with sandbox OTP `456789`. Capture the `delegationId` (UUID).

4. **Export all three**:

   ```bash
   export NVM_TEST_VISA_PLAN_ID=…             # uint256 decimal string from step 1
   export NVM_TEST_VISA_DELEGATION_ID=…       # uuid from step 3
   export NVM_TEST_VISA_PAYMENT_METHOD_ID=…   # vat_… from step 2
   ```

### Running the suite locally

```bash
poetry run pytest tests/e2e/test_x402_card_delegation_visa_e2e.py -v
```

If any of the three env vars are unset (or malformed) the suite reports skipped with a reason that names the missing or invalid variable.

### Refreshing the fixture

The delegation expires after the configured `durationSecs`. When the suite starts failing with VGS rejections that mention an expired delegation, re-run **step 3** (the delegation-create with WebAuthn ceremony) — the plan from step 1 and the enrolled card from step 2 can be reused as long as they're still active.

## Contributing

To add new E2E tests:

1. **Basic tests**: Add to `a2a_e2e_test.py`
2. **Advanced tests**: Add to `a2a_e2e_advanced_test.py`
3. **Helpers**: Extend `helpers/a2a_e2e_helpers.py`
4. **Follow patterns**: Use `MockE2EPaymentsService` and `E2ETestExecutor`
5. **Document**: Update this README

### E2E Test Pattern

```python
@pytest.mark.asyncio
async def test_new_functionality(self):
    """E2E test for new functionality."""
    # 1. Setup: agent card, payment metadata, executor
    # 2. Start server: PaymentsA2AServer.start()
    # 3. HTTP request: A2AE2EUtils.send_http_request()
    # 4. Assertions: A2AE2EAssertions.assert_*()
    # 5. Verify: payment service calls, credit burning
```
