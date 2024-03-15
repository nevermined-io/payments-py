import pytest

from payments_py import Environment
from payments_py import Payments
import os


session_key = os.getenv('SESSION_KEY')
marketplace_auth_token = os.getenv('MARKETPLACE_AUTH_TOKEN')
@pytest.fixture
def payment():
    return Payments(session_key=session_key, environment=Environment.appStaging, app_id="your_app_id", version="1.0.0", marketplace_auth_token=marketplace_auth_token)


def test_payment_creation(payment):
    assert payment.environment == Environment.appStaging
    assert payment.app_id == "your_app_id"
    assert payment.version == "1.0.0"
    assert payment.session_key == session_key


def test_create_subscription(payment):
    response = payment.create_subscription(name="test-py", description="test", price=1000000, token_address="0x75faf114eafb1BDbe2F0316DF893fd58CE46AA4d", amount_of_credits=100, duration=30, tags=["test"])
    assert response.status_code == 201


def test_create_service(payment):
    response = payment.create_service(subscription_did='did:nv:f5b85ff4d91d517059f86f3116d3e373c1e7930be4ee53757c3045fb3992a2ca', name="webservice-py", description="test", price=1000000, token_address="0x75faf114eafb1BDbe2F0316DF893fd58CE46AA4d", amount_of_credits=1, service_charge_type="fixed", auth_type="none")
    assert response.status_code == 201


def test_create_file(payment):
    response = payment.create_file(subscription_did='did:nv:f5b85ff4d91d517059f86f3116d3e373c1e7930be4ee53757c3045fb3992a2ca', name="file-py", description="test", price=1000000, token_address="0x75faf114eafb1BDbe2F0316DF893fd58CE46AA4d", amount_of_credits=1, tags=["test"], asset_type='model', files=[
          {
            "index": 0,
            "contentType": "text/markdown",
            "name": "test-py",
            "url": "https://raw.githubusercontent.com/nevermined-io/tutorials/main/README.md",
          }])
    print(response)
    assert response.status_code == 201

def test_get_asset_ddo(payment):
    response = payment.get_asset_ddo(did='did:nv:f5b85ff4d91d517059f86f3116d3e373c1e7930be4ee53757c3045fb3992a2ca')
    assert response.status_code == 200

def test_get_subscription_balance(payment):
    response = payment.get_subscription_balance(subscription_did='did:nv:6e898755372ac94dafd23aefbda2eae125889d03cdb7cc0eaeda0057e8e7b151')
    assert response.status_code == 201

# Needs the marketplace_auth_token
def test_get_service_token(payment):
    response = payment.get_service_token(service_did='did:nv:fe5d67842a507a1d22b9c9733b72cf7eb5b7a90835867e80bb18b72fd137a094')
    print(response.json())
    assert response.status_code == 201
