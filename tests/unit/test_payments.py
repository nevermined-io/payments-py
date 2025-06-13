"""
Unit tests for the Payments class.
"""
import os
import pytest
from payments_py.payments import Payments
from payments_py.common.payments_error import PaymentsError
from payments_py.common.helper import snake_to_camel, is_ethereum_address, get_service_host_from_endpoints

# Test API key (this should be replaced with a test key in a real environment)
TEST_API_KEY = os.getenv('TEST_PROXY_BEARER_TOKEN', 'eyJhbGciOiJFUzI1NksifQ.eyJpc3MiOiIweDA2OEVkMDBjRjA0NDFlNDgyOUQ5Nzg0ZkNCZTdiOWUyNkQ0QkQ4ZDAiLCJzdWIiOiIweGUyNjQ4MTNjOGZmY2NkMjBmNTMyNDZhYWI2YzMxMTEyZWYyZjQyMGM3YjYxNzU1NjUyOGM3ZWMwNzc3NGVmOTAiLCJleHAiOjE3NTg4MTYwNzQsImlhdCI6MTcyNzI1ODQ3NX0.Wa64furZZZpuKBva3nlAyfblU5CHCMEhz7jyEBkVow8QVuwcwznN-7eXrdfy_5E4W3xVxLXToZmFENd6cmRz1Bw')

def test_payments_initialization():
    """Test that Payments can be initialized correctly."""
    payments = Payments({
        'nvm_api_key': TEST_API_KEY,
        'environment': 'staging'
    })
    assert payments is not None
    assert payments.query is not None
    assert payments.is_browser_instance is False

def test_payments_initialization_browser():
    """Test that Payments can be initialized in browser mode and methods raise error."""
    payments = Payments({
        'nvm_api_key': TEST_API_KEY,
        'environment': 'staging'
    }, is_browser_instance=True)
    assert payments.is_browser_instance is True
    for method in [payments.connect, payments.init, payments.logout]:
        try:
            method()
            assert False, "Should have raised PaymentsError"
        except PaymentsError:
            pass

def test_payments_initialization_without_api_key():
    """Test that Payments cannot be initialized without an API key."""
    with pytest.raises(PaymentsError):
        Payments({
            'environment': 'staging'
        })

def test_is_ethereum_address():
    """Test the is_ethereum_address helper function."""
    assert is_ethereum_address('0x75faf114eafb1BDbe2F0316DF893fd58CE46AA4d') == True
    assert is_ethereum_address('0x75faf114eafb1BDbe2F0316DF893fd58CE46') == False
    assert is_ethereum_address(None) == False

def test_snake_to_camel():
    """Test the snake_to_camel helper function."""
    assert snake_to_camel('test_case') == 'testCase'
    assert snake_to_camel('test_case_with_multiple_words') == 'testCaseWithMultipleWords'
    assert snake_to_camel('alreadyCamelCase') == 'alreadyCamelCase'

def test_get_service_host_from_endpoints():
    """Test getting service host from endpoints."""
    endpoints = [
        {'POST': 'https://one-backend.testing.nevermined.app/api/v1/agents/(.*)/tasks'},
        {'GET': 'https://one-backend.testing.nevermined.app/api/v1/agents/(.*)/tasks/(.*)'}
    ]
    service_host = get_service_host_from_endpoints(endpoints)
    assert service_host == 'https://one-backend.testing.nevermined.app'