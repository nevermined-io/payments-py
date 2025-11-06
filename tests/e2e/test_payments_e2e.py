"""
End-to-end tests for the Payments class.
"""

import os
import time
import pytest
import threading
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import requests
from payments_py.payments import Payments
from payments_py.common.types import PlanMetadata, PaymentOptions
from payments_py.environments import ZeroAddress
from payments_py.plans import (
    get_erc20_price_config,
    get_expirable_duration_config,
    get_fiat_price_config,
    get_crypto_price_config,
    get_fixed_credits_config,
    get_free_price_config,
    get_native_token_price_config,
    get_non_expirable_duration_config,
    ONE_DAY_DURATION,
)
from payments_py.utils import get_random_big_int
from tests.e2e.utils import retry_with_backoff, wait_for_condition

# Test configuration
TEST_TIMEOUT = 30
TEST_ENVIRONMENT = os.getenv("TEST_ENVIRONMENT", "staging_sandbox")
SLEEP_DURATION = 3
ERC20_ADDRESS = "0x036CbD53842c5426634e7929541eC2318f3dCF7e"

# Test API keys (these should be replaced with test keys in a real environment)
SUBSCRIBER_API_KEY = os.getenv(
    "TEST_SUBSCRIBER_API_KEY",
    "sandbox-staging:eyJhbGciOiJFUzI1NksifQ.eyJpc3MiOiIweDU4MzhCNTUxMmNGOWYxMkZFOWYyYmVjY0IyMGViNDcyMTFGOUIwYmMiLCJzdWIiOiIweDMwNDExNzk1MTU1OTQ3QUFEZTljNjcxNjA5ZTM5OTkyNjFlNEIxQkIiLCJqdGkiOiIweGFmYmRhNWFmNjE2MDU0NDQ2ZGM3MTViOGUwMjYyZDY3NDVlNTFlNGMyYjM3NzgxZWQ2MmNlMTljYjhkOTA5ZDMiLCJleHAiOjE3OTA0NTcwNTYsIm8xMXkiOiJzay1oZWxpY29uZS13amUzYXdpLW5ud2V5M2EtdzdndnY3YS1oYmh3bm1pIn0.N-ugPJUCT2Addz39R-n9SDLahDbfGOcUuCNHz7opZKFdnyi_o4SXdNc4p3OgnI0bU2aENjaCqTGYcAlaZQrdoBs",
)
BUILDER_API_KEY = os.getenv(
    "TEST_BUILDER_API_KEY",
    "sandbox-staging:eyJhbGciOiJFUzI1NksifQ.eyJpc3MiOiIweDU4MzhCNTUxMmNGOWYxMkZFOWYyYmVjY0IyMGViNDcyMTFGOUIwYmMiLCJzdWIiOiIweDMwNDExNzk1MTU1OTQ3QUFEZTljNjcxNjA5ZTM5OTkyNjFlNEIxQkIiLCJqdGkiOiIweDY1MTY0MWRkMjlmY2JjOTUzY2VhMGJkN2ViNDcyNmIxYzQ5N2M1NmZjMmY1ODMwMzMwNmY5ZDM3MzQyMmVkNTgiLCJleHAiOjE3OTA0NTcxNDgsIm8xMXkiOiJzay1oZWxpY29uZS13amUzYXdpLW5ud2V5M2EtdzdndnY3YS1oYmh3bm1pIn0.i7L7UeHwzYtzYuomJajA3ye_CwYZKU2bMEw3NZl4yJlzJtRMXwIXU_fGrPvKlQKKGgCVk7Enk94RcBMM7D-zMxw",
)

# Test endpoints
AGENT_ENDPOINTS = [
    {"POST": "http://localhost:8889/test/:agentId/tasks"},
    {"GET": "http://localhost:8889/test/:agentId/tasks/:taskId"},
]

# Test metadata
plan_metadata = PlanMetadata(name="E2E test Payments Plan PYTHON")

# Global variables to store test IDs - these will be shared between tests
credits_plan_id = None
expirable_plan_id = None
trial_plan_id = None
agent_id = None
builder_address = None
agent_access_params = None
# Global variables for mock server
mock_payments_builder = None
mock_agent_id = None


# Mock HTTP Server for Agent testing
class MockAgentHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        self._handle_request()

    def do_GET(self):
        self._handle_request()

    def _handle_request(self):
        global mock_payments_builder, mock_agent_id
        auth_header = self.headers.get("Authorization")
        requested_url = f"http://localhost:8889{self.path}"
        http_verb = self.command

        print(
            f"Received request: endpoint={requested_url}, httpVerb={http_verb}, authHeader={auth_header}"
        )

        try:
            if mock_payments_builder and mock_agent_id:
                # Validate the request using the real Nevermined logic
                result = mock_payments_builder.requests.start_processing_request(
                    mock_agent_id,
                    auth_header,
                    requested_url,
                    http_verb,
                )
                # If the request is valid and the user is a subscriber
                if result and result.balance.is_subscriber:
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    response = {"message": "Hello from the Agent!"}
                    self.wfile.write(json.dumps(response).encode())
                    return
        except Exception as e:
            print(f"Unauthorized access attempt: {auth_header}, error: {e}")

        # If the request is not valid or there is an exception, respond with 402
        self.send_response(402)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        response = {"error": "Unauthorized"}
        self.wfile.write(json.dumps(response).encode())


def create_mock_server(payments_builder, agent_id):
    """Create and start a mock HTTP server for agent testing."""
    global mock_payments_builder, mock_agent_id
    mock_payments_builder = payments_builder
    mock_agent_id = agent_id

    server = HTTPServer(("localhost", 8889), MockAgentHandler)

    def run_server():
        server.serve_forever()

    thread = threading.Thread(target=run_server, daemon=True)
    thread.start()

    # Wait a bit for server to start
    time.sleep(1)
    return server


@pytest.fixture(scope="module")
def payments_subscriber():
    """Create a Payments instance for the subscriber."""
    return Payments(
        PaymentOptions(nvm_api_key=SUBSCRIBER_API_KEY, environment=TEST_ENVIRONMENT)
    )


@pytest.fixture(scope="module")
def payments_builder():
    """Create a Payments instance for the builder."""
    return Payments(
        PaymentOptions(nvm_api_key=BUILDER_API_KEY, environment=TEST_ENVIRONMENT)
    )


def test_payments_setup(payments_subscriber, payments_builder):
    """Test that Payments instances can be initialized correctly."""
    global builder_address
    assert payments_subscriber is not None
    assert payments_subscriber.query is not None
    assert payments_builder is not None
    assert payments_builder.query is not None
    assert payments_builder.account_address is not None
    builder_address = payments_builder.account_address


def test_fiat_price_config(payments_builder):
    """Test FIAT price config setup."""
    global builder_address
    if not builder_address:
        builder_address = "0x0000000000000000000000000000000000000001"
    fiat_price_config = get_fiat_price_config(100, builder_address)
    assert fiat_price_config is not None
    assert fiat_price_config.token_address == ZeroAddress
    assert fiat_price_config.is_crypto is False
    assert fiat_price_config.amounts[0] == 100
    assert fiat_price_config.receivers[0] == builder_address


def test_crypto_price_config(payments_builder):
    """Test CRYPTO price config setup."""
    global builder_address
    if not builder_address:
        builder_address = "0x0000000000000000000000000000000000000001"
    crypto_price_config = get_native_token_price_config(100, builder_address)
    assert crypto_price_config is not None
    assert crypto_price_config.is_crypto is True
    assert crypto_price_config.amounts[0] == 100
    assert crypto_price_config.receivers[0] == builder_address
    assert crypto_price_config.token_address == ZeroAddress


@pytest.mark.timeout(TEST_TIMEOUT)
def test_create_credits_plan(payments_builder):
    """Test creating a credits plan."""
    global builder_address, credits_plan_id
    if not builder_address:
        builder_address = "0x0000000000000000000000000000000000000001"
    price_config = get_erc20_price_config(20, ERC20_ADDRESS, builder_address)
    credits_config = get_fixed_credits_config(100)
    print(" **** PRICE CONFIG ***", price_config)
    response = retry_with_backoff(
        lambda: payments_builder.plans.register_credits_plan(
            plan_metadata, price_config, credits_config
        ),
        label="Credits Plan Registration",
        attempts=6,
    )
    assert response is not None
    credits_plan_id = response.get("planId", None)
    assert credits_plan_id is not None
    assert int(credits_plan_id) > 0
    print("Credits Plan ID", credits_plan_id)


@pytest.mark.timeout(TEST_TIMEOUT)
def test_create_time_plan(payments_builder):
    """Test creating a time plan."""
    global builder_address, expirable_plan_id
    if not builder_address:
        builder_address = "0x0000000000000000000000000000000000000001"
    price_config = get_erc20_price_config(50, ERC20_ADDRESS, builder_address)
    credits_config = get_expirable_duration_config(ONE_DAY_DURATION)  # 1 day
    response = retry_with_backoff(
        lambda: payments_builder.plans.register_time_plan(
            plan_metadata, price_config, credits_config
        ),
        label="Expirable Plan Registration",
        attempts=6,
    )
    assert response is not None
    expirable_plan_id = response.get("planId", None)
    assert expirable_plan_id is not None
    assert int(expirable_plan_id) > 0
    print("Expirable Plan ID", expirable_plan_id)


@pytest.mark.timeout(TEST_TIMEOUT)
def test_create_trial_plan(payments_builder):
    """Test creating a trial plan."""
    global trial_plan_id
    trial_plan_metadata = PlanMetadata(name="E2E test Trial Payments Plan PYTHON")
    price_config = get_free_price_config()
    credits_config = get_expirable_duration_config(ONE_DAY_DURATION)
    print(" **** PRICE CONFIG ***", price_config)
    response = retry_with_backoff(
        lambda: payments_builder.plans.register_time_trial_plan(
            trial_plan_metadata, price_config, credits_config
        ),
        label="Trial Plan Registration",
        attempts=6,
    )
    assert response is not None
    trial_plan_id = response.get("planId", None)
    assert trial_plan_id is not None
    assert int(trial_plan_id) > 0
    print("Trial Plan ID", trial_plan_id)


@pytest.mark.timeout(TEST_TIMEOUT)
def test_create_agent(payments_builder):
    """Test creating an agent with associated plans."""
    global agent_id, credits_plan_id, expirable_plan_id
    assert credits_plan_id is not None, "credits_plan_id must be set by previous test"
    assert (
        expirable_plan_id is not None
    ), "expirable_plan_id must be set by previous test"

    agent_metadata = {
        "name": "E2E Payments Agent PYTHON",
        "tags": ["test"],
        "dateCreated": datetime.now().isoformat(),
        "description": "E2E Payments Agent PYTHON",
    }
    agent_api = {"endpoints": AGENT_ENDPOINTS}
    payment_plans = [credits_plan_id, expirable_plan_id]
    payment_plans = [pid for pid in payment_plans if pid]
    result = retry_with_backoff(
        lambda: payments_builder.agents.register_agent(
            agent_metadata, agent_api, payment_plans
        ),
        label="Agent Registration",
        attempts=5,
    )
    print("RESULT", result)
    agent_id = result.get("agentId", None)
    assert agent_id is not None
    print("Agent ID", agent_id)


@pytest.mark.timeout(TEST_TIMEOUT)
def test_create_agent_and_plan(payments_builder):
    """Test creating an agent and plan in one step."""
    global builder_address
    if not builder_address:
        builder_address = payments_builder.account_address
    timestamp = datetime.now().isoformat()
    plan_metadata = {
        "name": f"E2E test Payments Plan PYTHON {timestamp}",
    }
    agent_metadata = {
        "name": "My AI FIAT Payments Agent",
        "description": "This is a test agent for the E2E Payments tests",
        "tags": ["fiat", "test2"],
    }
    agent_api = {"endpoints": [{"POST": "http://localhost:8889/test/:agentId/tasks"}]}
    crypto_price_config = get_crypto_price_config(
        10_000_000, builder_address, ERC20_ADDRESS
    )
    non_expirable_config = get_non_expirable_duration_config()
    # Force randomness of the plan by setting a random duration
    non_expirable_config.duration_secs = get_random_big_int()
    result = retry_with_backoff(
        lambda: payments_builder.agents.register_agent_and_plan(
            agent_metadata,
            agent_api,
            plan_metadata,
            crypto_price_config,
            non_expirable_config,
        ),
        label="Agent and Plan Registration",
        attempts=5,
    )
    agent_and_plan_agent_id = result.get("agentId", None)
    agent_and_plan_plan_id = result.get("planId", None)
    assert agent_and_plan_agent_id is not None
    assert agent_and_plan_plan_id is not None


@pytest.mark.timeout(TEST_TIMEOUT)
def test_get_plan(payments_builder):
    """Test getting a plan."""
    global credits_plan_id
    assert credits_plan_id is not None, "credits_plan_id must be set by previous test"
    plan = payments_builder.plans.get_plan(credits_plan_id)
    assert plan is not None
    assert plan.get("id") == credits_plan_id
    print("Plan", plan)


@pytest.mark.timeout(TEST_TIMEOUT)
def test_get_agent(payments_builder):
    """Test getting an agent."""
    global agent_id
    assert agent_id is not None, "agent_id must be set by previous test"
    agent = payments_builder.agents.get_agent(agent_id)
    assert agent is not None
    assert agent.get("id") == agent_id
    print("Agent", agent)


@pytest.mark.timeout(TEST_TIMEOUT * 2)
def test_order_plan(payments_subscriber):
    """Test ordering a plan."""
    global credits_plan_id
    assert credits_plan_id is not None, "credits_plan_id must be set by previous test"
    print(credits_plan_id)
    print(" SUBSCRIBER ADDRESS = ", payments_subscriber.account_address)
    order_result = retry_with_backoff(
        lambda: payments_subscriber.plans.order_plan(credits_plan_id),
        label="Plan Order",
        attempts=6,
    )
    assert order_result is not None
    print("Order Result", order_result)
    assert order_result.get("success") is True
    print("Order Result", order_result)


def test_get_plan_balance(payments_subscriber):
    """Test getting plan balance."""
    global credits_plan_id
    assert credits_plan_id is not None, "credits_plan_id must be set by previous test"

    # Poll balance briefly to account for backend latency
    def _poll_balance():
        result = payments_subscriber.plans.get_plan_balance(credits_plan_id)
        if not result:
            return None
        try:
            bal = int(result.balance)
        except Exception:
            bal = 0
        if bal > 0 and result.is_subscriber:
            return result
        return None

    final_balance = wait_for_condition(
        _poll_balance,
        label="Plan Balance Availability",
        timeout_secs=60.0,
        poll_interval_secs=2.0,
    )
    assert final_balance is not None
    assert int(final_balance.balance) > 0


@pytest.mark.timeout(TEST_TIMEOUT * 2)
def test_order_trial_plan(payments_subscriber):
    """Test ordering a trial plan."""
    global trial_plan_id
    assert trial_plan_id is not None, "trial_plan_id must be set by previous test"

    order_result = retry_with_backoff(
        lambda: payments_subscriber.plans.order_plan(trial_plan_id),
        label="Trial Plan Order",
        attempts=6,
    )
    assert order_result is not None
    assert order_result.get("success") is True
    print("Order Result", order_result)


@pytest.mark.timeout(TEST_TIMEOUT * 2)
def test_order_trial_plan_twice(payments_subscriber):
    """Test that ordering a trial plan twice fails."""
    global trial_plan_id
    assert trial_plan_id is not None, "trial_plan_id must be set by previous test"

    with pytest.raises(Exception):
        order_result = payments_subscriber.plans.order_plan(trial_plan_id)
        print("Order Result", order_result)
        assert order_result.get("success") is False


class TestE2ESubscriberAgentFlow:
    """Test E2E Subscriber/Agent flow with mock HTTP server."""

    @pytest.fixture(autouse=True)
    def setup_server(self, payments_builder):
        """Setup mock HTTP server for agent testing."""
        global agent_id
        assert agent_id is not None, "agent_id must be set by previous test"
        self.server = create_mock_server(payments_builder, agent_id)
        yield
        self.server.shutdown()
        self.server.server_close()

    @pytest.mark.timeout(TEST_TIMEOUT)
    def test_generate_agent_access_token(self, payments_subscriber):
        """Test generating agent access token."""
        global agent_access_params, credits_plan_id, agent_id
        assert (
            credits_plan_id is not None
        ), "credits_plan_id must be set by previous test"
        assert agent_id is not None, "agent_id must be set by previous test"

        agent_access_params = retry_with_backoff(
            lambda: payments_subscriber.agents.get_agent_access_token(
                credits_plan_id, agent_id
            ),
            label="Access Token Generation",
            attempts=5,
        )
        assert agent_access_params is not None
        print("Agent Access Params", agent_access_params)
        assert len(agent_access_params.get("accessToken", "")) > 0

    @pytest.mark.timeout(TEST_TIMEOUT)
    def test_send_request_to_agent(self):
        """Test sending a request directly to the agent."""
        global agent_access_params
        assert (
            agent_access_params is not None
        ), "agent_access_params must be set by previous test"

        agent_url = "http://localhost:8889/test/12345/tasks"
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {agent_access_params.get('accessToken')}",
        }

        response = requests.post(agent_url, headers=headers)
        assert response is not None
        print(response.json())
        assert response.status_code == 200

    @pytest.mark.timeout(TEST_TIMEOUT)
    def test_invalid_agent_request(self):
        """Test that invalid agent requests are rejected."""
        agent_url = "http://localhost:8889/test/12345/tasks"
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": "Bearer INVALID_TOKEN",
        }

        response = requests.post(agent_url, headers=headers)
        assert response is not None
        assert response.status_code == 402

    @pytest.mark.timeout(TEST_TIMEOUT)
    def test_wrong_endpoint_agent_request(self):
        """Test that querying an agent using the wrong endpoint fails with 402."""
        global agent_access_params
        assert (
            agent_access_params is not None
        ), "agent_access_params must be set by previous test"

        # Use an incorrect endpoint
        wrong_agent_url = "http://localhost:8889/wrong/endpoint"
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {agent_access_params.get('accessToken')}",
        }

        response = requests.post(wrong_agent_url, headers=headers)
        assert response is not None
        print(f"Wrong endpoint response: {response.status_code} {response.text}")
        assert response.status_code == 402

    @pytest.mark.timeout(TEST_TIMEOUT)
    def test_fix_agent_endpoints(self, payments_builder):
        """Test that agent endpoints can be updated (fix endpoints)."""
        global agent_id
        assert agent_id is not None, "agent_id must be set by previous test"

        agent_metadata = {
            "name": "E2E Payments Agent Updated",
            "description": "This is a test agent for the E2E Payments tests",
            "tags": ["test"],
        }
        agent_api = {"endpoints": [{"POST": "http://localhost:8889/test/12345/tasks"}]}

        result = retry_with_backoff(
            lambda: payments_builder.agents.update_agent_metadata(
                agent_id, agent_metadata, agent_api
            ),
            label="Agent Metadata Update",
            attempts=5,
        )
        assert result is not None
        print(f"Update agent result: {result}")
        assert result.get("success", True)  # Accept True or missing (legacy)


@pytest.mark.timeout(TEST_TIMEOUT)
def test_get_nonexistent_plan(payments_builder):
    """Test getting a plan that does not exist."""
    with pytest.raises(Exception):
        result = payments_builder.plans.get_plan("11111")
        assert result is None
