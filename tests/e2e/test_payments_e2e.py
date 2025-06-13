"""
End-to-end tests for the Payments class.
"""
import os
import time
import pytest
from payments_py.payments import Payments
from payments_py.common.types import (
    PlanMetadata,
    PlanPriceType,
    Address
)
from payments_py.environments import ZeroAddress
from payments_py.plans import (
    get_erc20_price_config,
    get_expirable_duration_config,
    get_fiat_price_config,
    get_fixed_credits_config,
    get_free_price_config,
    get_native_token_price_config,
    get_non_expirable_duration_config,
    ONE_DAY_DURATION
)

# Test configuration
TEST_TIMEOUT = 30
TEST_ENVIRONMENT = os.getenv('TEST_ENVIRONMENT', 'local')
SLEEP_DURATION = 3
ERC20_ADDRESS = '0x036CbD53842c5426634e7929541eC2318f3dCF7e'

# Test API keys (these should be replaced with test keys in a real environment)
SUBSCRIBER_API_KEY = os.getenv('TEST_SUBSCRIBER_API_KEY', 'eyJhbGciOiJFUzI1NksifQ.eyJpc3MiOiIweDA2OEVkMDBjRjA0NDFlNDgyOUQ5Nzg0ZkNCZTdiOWUyNkQ0QkQ4ZDAiLCJzdWIiOiIweGVBZDY4Mzk3MTI3QUYwRjg0ZjRhNGJENjBEYTg1ZTEzMTY5ZTIyQjEiLCJqdGkiOiIweDRiYjQwMTMwYmE3ZWNjNTI5M2NhMzUzMjVlYWNjNDU2ZTQ3NjMwNTNjNTlmYjVlNmI1MDQ3NTg3ZTc1NDNlNjciLCJleHAiOjE3ODEzNzM5MzN9.Cn1Hx_rPXrF2dnVVCwsJMf1MY9eVyJFPMvysVW-7RQABlKovSVFYfPc-qjwL_K4CVrGHb7GoTZnYaR28bE-PDxw')
BUILDER_API_KEY = os.getenv('TEST_BUILDER_API_KEY', 'eyJhbGciOiJFUzI1NksifQ.eyJpc3MiOiIweDA2OEVkMDBjRjA0NDFlNDgyOUQ5Nzg0ZkNCZTdiOWUyNkQ0QkQ4ZDAiLCJzdWIiOiIweEIyZWRCRjJhMjhEM0VkNDA2ZGM4ZDMyZDdFNTY2OWM2Mzc0NjBmMTgiLCJqdGkiOiIweGRkMjY1ZmNmOGVlNWEwZjQ4MjVmZGMyMjk0YTU2MTI3ZjVhZjA5YWFhMjg3NTQwMmNlMWIyNWU3MWE2YjNmYTYiLCJleHAiOjE3ODEzNjU0NTB9.fl1JrFshqH6ykwJl_fk9auRPXgRqwjJlz0yfPHEh295tRvVG0SX_QqDIawFjFQahCfa4qehxmyfEAE6HQOizdRw')

# Test endpoints
AGENT_ENDPOINTS = [
    {'POST': f'https://api.{TEST_ENVIRONMENT}.nevermined.app/api/v1/agents/(.*)/tasks'},
    {'GET': f'https://api.{TEST_ENVIRONMENT}.nevermined.app/api/v1/agents/(.*)/tasks/(.*)'}
]

# Test metadata
plan_metadata = PlanMetadata(
    name='E2E test Payments Plan PYTHON'
)

# Variables to store test IDs
credits_plan_id = None
expirable_plan_id = None
trial_plan_id = None
agent_id = None
builder_address = None

@pytest.fixture(scope="module")
def payments_subscriber():
    """Create a Payments instance for the subscriber."""
    return Payments({
        'nvm_api_key': SUBSCRIBER_API_KEY,
        'environment': TEST_ENVIRONMENT
    })

@pytest.fixture(scope="module")
def payments_builder():
    """Create a Payments instance for the builder."""
    return Payments({
        'nvm_api_key': BUILDER_API_KEY,
        'environment': TEST_ENVIRONMENT
    })

@pytest.fixture(scope="module")
def plan_ids():
    return {
        'credits_plan_id': "23783594671162478839166992131645148945128197772132428481413737233633868783795",
        'expirable_plan_id': "1527202413796022397825315317349451752715275628443805851171874251479839190159",
        'agent_id': "did:nv:cae4c9ac10f2b298a91ee96afc72cecf4b466ef5c14c7811651d6624a249c255"
    }

def test_payments_setup(payments_subscriber, payments_builder):
    """Test that Payments instances can be initialized correctly."""
    assert payments_subscriber is not None
    assert payments_subscriber.query is not None
    assert payments_builder is not None
    assert payments_builder.query is not None
    assert payments_builder.account_address is not None
    global builder_address
    builder_address = payments_builder.account_address

def test_fiat_price_config(payments_builder):
    """Test FIAT price config setup."""
    global builder_address
    if not builder_address:
        builder_address = '0x0000000000000000000000000000000000000001'
    fiat_price_config = get_fiat_price_config(100, builder_address)
    assert fiat_price_config is not None
    assert fiat_price_config.price_type == PlanPriceType.FIXED_FIAT_PRICE
    assert fiat_price_config.amounts[0] == 100
    assert fiat_price_config.receivers[0] == builder_address

def test_crypto_price_config(payments_builder):
    """Test CRYPTO price config setup."""
    global builder_address
    if not builder_address:
        builder_address = '0x0000000000000000000000000000000000000001'
    crypto_price_config = get_native_token_price_config(100, builder_address)
    assert crypto_price_config is not None
    assert crypto_price_config.price_type == PlanPriceType.FIXED_PRICE
    assert crypto_price_config.amounts[0] == 100
    assert crypto_price_config.receivers[0] == builder_address
    assert crypto_price_config.token_address == ZeroAddress

@pytest.mark.timeout(TEST_TIMEOUT)
def test_create_credits_plan(payments_builder, plan_ids):
    """Test creating a credits plan."""
    global builder_address
    if not builder_address:
        builder_address = '0x0000000000000000000000000000000000000001'
    price_config = get_erc20_price_config(20, ERC20_ADDRESS, builder_address)
    credits_config = get_fixed_credits_config(100)
    response = payments_builder.register_credits_plan(plan_metadata, price_config, credits_config)
    assert response is not None
    plan_ids['credits_plan_id'] = response.get('planId', None)
    assert plan_ids['credits_plan_id'] is not None
    assert int(plan_ids['credits_plan_id']) > 0

@pytest.mark.timeout(TEST_TIMEOUT)
def test_create_time_plan(payments_builder, plan_ids):
    """Test creating a time plan."""
    global builder_address
    if not builder_address:
        builder_address = '0x0000000000000000000000000000000000000001'
    price_config = get_erc20_price_config(50, ERC20_ADDRESS, builder_address)
    credits_config = get_expirable_duration_config(ONE_DAY_DURATION)  # 1 day
    response = payments_builder.register_time_plan(plan_metadata, price_config, credits_config)
    assert response is not None
    plan_ids['expirable_plan_id'] = response.get('planId', None)
    assert plan_ids['expirable_plan_id'] is not None
    assert int(plan_ids['expirable_plan_id']) > 0

@pytest.mark.timeout(TEST_TIMEOUT)
def test_create_trial_plan(payments_builder, plan_ids):
    """Test creating a trial plan."""
    trial_plan_metadata = PlanMetadata(
        name='E2E test Trial Payments Plan PYTHON'
    )
    price_config = get_free_price_config()
    credits_config = get_expirable_duration_config(ONE_DAY_DURATION)
    response = payments_builder.register_time_trial_plan(trial_plan_metadata, price_config, credits_config)
    assert response is not None
    plan_ids['trial_plan_id'] = response.get('planId', None)
    assert plan_ids['trial_plan_id'] is not None
    assert int(plan_ids['trial_plan_id']) > 0

@pytest.mark.timeout(TEST_TIMEOUT)
def test_create_agent(payments_builder, plan_ids):
    """Test creating an agent with associated plans."""
    agent_metadata = {
        'name': 'E2E Payments Agent PYTHON',
        'tags': ['test'],
        'dateCreated': time.time()
    }
    agent_api = {
        'endpoints': AGENT_ENDPOINTS
    }
    assert plan_ids['credits_plan_id'] is not None
    assert plan_ids['expirable_plan_id'] is not None
    payment_plans = [plan_ids['credits_plan_id'], plan_ids['expirable_plan_id']]
    payment_plans = [pid for pid in payment_plans if pid]
    result = payments_builder.register_agent(agent_metadata, agent_api, payment_plans)
    plan_ids['agent_id'] = result.get('agentId', None)
    assert plan_ids['agent_id'] is not None
    assert plan_ids['agent_id'].startswith('did:nv:')

@pytest.mark.timeout(TEST_TIMEOUT)
def test_create_agent_and_plan(payments_builder, plan_ids):
    """Test creating an agent and plan in one step."""
    global builder_address
    if not builder_address:
        builder_address = '0x0000000000000000000000000000000000000001'
    agent_metadata = {'name': 'My AI Payments Agent', 'tags': ['test2']}
    agent_api = {'endpoints': [{'POST': 'https://example.com/api/v1/agents/(.*)/tasks'}]}
    crypto_price_config = get_native_token_price_config(500, builder_address)
    non_expirable_config = get_non_expirable_duration_config()
    result = payments_builder.register_agent_and_plan(
        agent_metadata,
        agent_api,
        plan_metadata,
        crypto_price_config,
        non_expirable_config
    )
    plan_ids['agent_and_plan_agent_id'] = result.get('agentId', None)
    plan_ids['agent_and_plan_plan_id'] = result.get('planId', None)
    assert plan_ids['agent_and_plan_agent_id'] is not None
    assert plan_ids['agent_and_plan_plan_id'] is not None

@pytest.mark.timeout(TEST_TIMEOUT)
def test_get_plan(payments_builder, plan_ids):
    """Test getting a plan."""
    plan_id = plan_ids.get('credits_plan_id')
    assert plan_id is not None
    plan = payments_builder.get_plan(plan_id)
    assert plan is not None
    assert plan.get('id') == plan_id

@pytest.mark.timeout(TEST_TIMEOUT)
def test_get_agent(payments_builder, plan_ids):
    """Test getting an agent."""
    agent_id = plan_ids.get('agent_id')
    assert agent_id is not None
    agent = payments_builder.get_agent(agent_id)
    assert agent is not None
    assert agent.get('id') == agent_id

@pytest.mark.timeout(TEST_TIMEOUT * 2)
def test_order_plan(payments_subscriber, plan_ids):
    """Test ordering a plan."""
    plan_id = plan_ids.get('credits_plan_id')
    assert plan_id is not None
    order_result = payments_subscriber.order_plan(plan_id)
    assert order_result is not None
    assert getattr(order_result, 'success', False) is True

def test_get_plan_balance(payments_subscriber, plan_ids):
    """Test getting plan balance."""
    plan_id = plan_ids.get('credits_plan_id')
    assert plan_id is not None
    balance_result = payments_subscriber.get_plan_balance(plan_id)
    assert balance_result is not None
    assert int(balance_result.get('balance', 0)) > 0

@pytest.mark.skip(reason="Trial plan functionality not implemented yet")
def test_order_trial_plan(payments_subscriber):
    """Test ordering a trial plan."""
    order_result = payments_subscriber.order_plan(trial_plan_id)
    assert order_result is not None
    assert order_result.success is True

@pytest.mark.skip(reason="Trial plan functionality not implemented yet")
def test_order_trial_plan_twice(payments_subscriber):
    """Test that ordering a trial plan twice fails."""
    with pytest.raises(Exception):
        payments_subscriber.order_plan(trial_plan_id)

@pytest.mark.skip(reason="Error handling not implemented yet")
def test_get_nonexistent_plan(payments_builder):
    """Test getting a plan that does not exist."""
    result = payments_builder.get_plan('11111')
    assert result is None 