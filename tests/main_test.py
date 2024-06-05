import pytest

from payments_py import Environment
from payments_py import Payments
import os


nvm_api_key = os.getenv('NVM_API_KEY')

@pytest.fixture
def payment():
    return Payments(nvm_api_key=nvm_api_key, environment=Environment.appStaging, app_id="your_app_id", version="1.0.0")


def test_payment_creation(payment):
    assert payment.environment == Environment.appStaging
    assert payment.app_id == "your_app_id"
    assert payment.version == "1.0.0"
    assert payment.nvm_api_key == nvm_api_key


def test_create_subscription(payment):
    response = payment.create_subscription(name="test-py", description="test", price=1000000, token_address="0x75faf114eafb1BDbe2F0316DF893fd58CE46AA4d", amount_of_credits=100, duration=30, tags=["test"])
    assert response.status_code == 201


def test_create_service(payment):
    response = payment.create_service(subscription_did='did:nv:a0079b517e580d430916924f1940b764e17c31e368c509483426f8c2ac2e7116', name="webservice-py", description="test", price=1000000, token_address="0x75faf114eafb1BDbe2F0316DF893fd58CE46AA4d", amount_of_credits=1, service_charge_type="fixed", auth_type="none")
    assert response.status_code == 201


def test_create_file(payment):
    response = payment.create_file(subscription_did='did:nv:a0079b517e580d430916924f1940b764e17c31e368c509483426f8c2ac2e7116', name="file-py", description="test", price=1000000, token_address="0x75faf114eafb1BDbe2F0316DF893fd58CE46AA4d", amount_of_credits=1, tags=["test"], asset_type='model', files=[
          {
            "index": 0,
            "contentType": "text/markdown",
            "name": "test-py",
            "url": "https://raw.githubusercontent.com/nevermined-io/tutorials/main/README.md",
          }])
    assert response.status_code == 201

def test_get_asset_ddo(payment):
    response = payment.get_asset_ddo(did='did:nv:a0079b517e580d430916924f1940b764e17c31e368c509483426f8c2ac2e7116')
    assert response.status_code == 200

def test_get_subscription_balance(payment):
    response = payment.get_subscription_balance(subscription_did='did:nv:a0079b517e580d430916924f1940b764e17c31e368c509483426f8c2ac2e7116', account_address='0x4fe3e7d42fA83be4E8cF03451Ac3F25980a73fF6')
    assert response.status_code == 201

def test_get_service_token(payment):
    response = payment.get_service_token(service_did='did:nv:349b6ec01dc8cfdc160d2b71bbfb7e6e93963206e7ab682128733360c0d92ac6')
    assert response.status_code == 200

def test_order_subscription(payment):
    response = payment.order_subscription(subscription_did='did:nv:debe46f1c0f3e36c853a9f093717c46eaa94df9b302731b9d06e7e07e5fd0c8b')
    assert response.status_code == 201

def test_download_file(payment):
    response = payment.download_file(file_did='did:nv:f1a974ca211e855a89b9a2049900fec29cc79cd9ca4e8d791a27836009c5b215')
    assert response.status_code == 200

def test_mint_credits(payment):
    response = payment.mint_credits(subscription_did='did:nv:e405a91e3152be1430c5d0607ebdf9236c19f34bfba0320798d81ba5f5e3e3a5', amount="12", receiver='0x4fe3e7d42fA83be4E8cF03451Ac3F25980a73fF6')
    assert response.status_code == 201

def test_burn_credits(payment):
    response = payment.burn_credits(subscription_did='did:nv:e405a91e3152be1430c5d0607ebdf9236c19f34bfba0320798d81ba5f5e3e3a5', amount="24")
    assert response.status_code == 201