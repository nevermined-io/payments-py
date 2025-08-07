# E2E Tests for A2A Payment Integration

This directory contains end-to-end (E2E) tests for the A2A payment integration in Python, which verify complete functionality with real network requests.

## Test Structure

### `a2a_e2e_test.py`

Basic E2E tests covering:

- **Blocking flow**: Complete verification with credit burning
- **Invalid authentication**: Handling of incorrect bearer tokens
- **Non-blocking flow**: Asynchronous execution with polling

### `a2a_e2e_advanced_test.py`

Advanced E2E tests covering:

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

# Run only basic tests
pytest tests/e2e/a2a_e2e_test.py -v

# Run only advanced tests
pytest tests/e2e/a2a_e2e_advanced_test.py -v

# Run specific test
pytest tests/e2e/a2a_e2e_test.py::TestA2AE2EFlow::test_blocking_flow_with_credit_burning -v

# Skip E2E tests (if marked as 'slow')
pytest tests/ -m "not slow"

# Run with detailed logs
pytest tests/e2e/ -v -s --log-cli-level=INFO
```

## Verified Functionality

### ✅ Payment Flows

- [x] Bearer token validation
- [x] Credit burning on final events
- [x] Payment error handling (401/402)
- [x] Different credit amounts

### ✅ Execution Modes

- [x] Blocking: Waits until completion
- [x] Non-blocking: Returns immediately, polling for status
- [x] Streaming: Real-time Server-Sent Events

### ✅ Advanced Features

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
E2E_BUILDER_API_KEY=test-builder-key          # Builder API key
E2E_SUBSCRIBER_API_KEY=test-subscriber-key    # Subscriber API key
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
