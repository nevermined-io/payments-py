import pytest
from unittest.mock import patch, Mock
from pydantic import ValidationError

from payments_py import Environment
from payments_py import Payments
import os

from payments_py.data_models import BalanceResultDto, BurnResultDto, CreateAssetResultDto, DownloadFileResultDto, MintResultDto, OrderSubscriptionResultDto, ServiceTokenResultDto


nvm_api_key = os.getenv('NVM_API_KEY')

@pytest.fixture
def payment():
    return Payments(nvm_api_key=nvm_api_key, environment=Environment.local, app_id="your_app_id", version="1.0.0")


def test_payment_creation(payment):
    assert payment.environment == Environment.local
    assert payment.app_id == "your_app_id"
    assert payment.version == "1.0.0"
    assert payment.nvm_api_key == nvm_api_key

def test_create_time_subscription(payment):
    response = payment.create_time_subscription(
        name="test-py",
        description="test",
        price=1000000,
        token_address="0x75faf114eafb1BDbe2F0316DF893fd58CE46AA4d",
        duration=30,
        tags=["test"]
    )
    assert isinstance(response, CreateAssetResultDto)
    assert response.did.startswith("did:")

def test_create_credits_subscription(payment):
    response = payment.create_credits_subscription(
        name="test-py",
        description="test",
        price=1000000,
        token_address="0x75faf114eafb1BDbe2F0316DF893fd58CE46AA4d",
        amount_of_credits=100,
        tags=["test"]
    )
    assert isinstance(response, CreateAssetResultDto)
    assert response.did.startswith("did:")

def test_create_service(payment):
    response = payment.create_service(
        subscription_did='did:nv:a0079b517e580d430916924f1940b764e17c31e368c509483426f8c2ac2e7116',
        name="webservice-py",
        description="test",
        amount_of_credits=1,
        service_charge_type="fixed",
        auth_type="none"
    )
    assert isinstance(response, CreateAssetResultDto)
    assert response.did.startswith("did:")

def test_create_file(payment):
    response = payment.create_file(
        subscription_did='did:nv:a0079b517e580d430916924f1940b764e17c31e368c509483426f8c2ac2e7116',
        asset_type='model',
        name="file-py",
        description="test",
        amount_of_credits=1,
        tags=["test"],
        files=[
            {
                "index": 0,
                "contentType": "text/markdown",
                "name": "test-py",
                "url": "https://raw.githubusercontent.com/nevermined-io/tutorials/main/README.md",
            }
        ]
    )
    assert isinstance(response, CreateAssetResultDto)
    assert response.did.startswith("did:")

def test_get_asset_ddo(payment):
    response = payment.get_asset_ddo(did='did:nv:a0079b517e580d430916924f1940b764e17c31e368c509483426f8c2ac2e7116')
    assert response.status_code == 200

def test_get_service_token(payment):
    response = payment.get_service_token(service_did='did:nv:349b6ec01dc8cfdc160d2b71bbfb7e6e93963206e7ab682128733360c0d92ac6')
    assert isinstance(response, ServiceTokenResultDto)

def test_order_subscription(payment):
    response = payment.order_subscription(subscription_did='did:nv:debe46f1c0f3e36c853a9f093717c46eaa94df9b302731b9d06e7e07e5fd0c8b')
    assert isinstance(response, OrderSubscriptionResultDto)

def test_download_file(payment):
    response = payment.download_file(file_did='did:nv:7e38d39405445ab3e5435d8c1c6653a00ddc425ba629789f58fbefccaa5e5a5d')
    assert isinstance(response, DownloadFileResultDto)


def test_get_subscription_balance(payment):
    response = payment.get_subscription_balance(subscription_did='did:nv:a0079b517e580d430916924f1940b764e17c31e368c509483426f8c2ac2e7116', account_address='0x4fe3e7d42fA83be4E8cF03451Ac3F25980a73fF6')
    assert isinstance(response, BalanceResultDto)


def test_mint_credits(payment):
    response = payment.mint_credits(subscription_did='did:nv:e405a91e3152be1430c5d0607ebdf9236c19f34bfba0320798d81ba5f5e3e3a5', amount="12", receiver='0x4fe3e7d42fA83be4E8cF03451Ac3F25980a73fF6')
    assert isinstance(response, MintResultDto)

def test_burn_credits(payment):
    response = payment.burn_credits(subscription_did='did:nv:e405a91e3152be1430c5d0607ebdf9236c19f34bfba0320798d81ba5f5e3e3a5', amount="12")
    assert isinstance(response, BurnResultDto)


# Mocking the requests.post method. We need to follow this pattern to mock the requests.post method of the rest of tests.

def test_get_subscription_balance(payment):
    mock_response = Mock()
    mock_response.status_code = 201
    mock_response.json.return_value = {
        "subscriptionType": "credits",
        "isOwner": True,
        "isSubscriptor": True,
        "balance": "10000000"
    }
    
    with patch('requests.post', return_value=mock_response):
        response = payment.get_subscription_balance(subscription_did='did:nv:a0079b517e580d430916924f1940b764e17c31e368c509483426f8c2ac2e7116', account_address='0x4fe3e7d42fA83be4E8cF03451Ac3F25980a73fF6')
        
        assert response.subscriptionType == "credits"
        assert response.isOwner is True
        assert response.isSubscriptor is True
        assert response.balance == "10000000"

def test_get_subscription_balance_invalid_response(payment):
    mock_response = Mock()
    mock_response.status_code = 201
    mock_response.json.return_value = {
        "subscriptionType": "invalid",  # Assuming "invalid" is not a valid SubscriptionType
        "isOwner": True,
        "isSubscriptor": True,
        "balance": 10000000
    }
    
    with patch('requests.post', return_value=mock_response):
        with pytest.raises(ValidationError):
            payment.get_subscription_balance(subscription_did='did:nv:a0079b517e580d430916924f1940b764e17c31e368c509483426f8c2ac2e7116', account_address='0x4fe3e7d42fA83be4E8cF03451Ac3F25980a73fF6')

def test_mint_credits(payment):
    mock_response = Mock()
    mock_response.status_code = 201
    mock_response.json.return_value = {
        "userOpHash": "tx123456",
        "success": True,
        "amount": "12"
    }
    
    with patch('requests.post', return_value=mock_response):
        response = payment.mint_credits(subscription_did='did:nv:e405a91e3152be1430c5d0607ebdf9236c19f34bfba0320798d81ba5f5e3e3a5', amount="12", receiver='0x4fe3e7d42fA83be4E8cF03451Ac3F25980a73fF6')
        
        assert response.userOpHash == "tx123456"
        assert response.success == True
        assert response.amount == "12"

def test_burn_credits(payment):
    mock_response = Mock()
    mock_response.status_code = 201
    mock_response.json.return_value = {
        "userOpHash": "tx123456",
        "success": True,
        "amount": "12"
    }
    
    with patch('requests.post', return_value=mock_response):
        response = payment.burn_credits(subscription_did='did:nv:e405a91e3152be1430c5d0607ebdf9236c19f34bfba0320798d81ba5f5e3e3a5', amount="12")
        
        assert response.userOpHash == "tx123456"
        assert response.success == True
        assert response.amount == "12"



