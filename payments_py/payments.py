from typing import List, Optional
import requests

from payments_py.environments import Environment
from payments_py.utils import snake_to_camel


class Payments:
    """
    A class representing a payment system.

    Attributes:
        nvm_api_key (str): The nvm api key for authentication.
        environment (Environment): The environment for the payment system.
        app_id (str, optional): The application ID.
        version (str, optional): The version of the payment system.

    Methods:
        create_ubscription: Creates a new subscription.
        create_service: Creates a new service.
        create_file: Creates a new file.
        order_subscription: Orders the subscription.
        get_asset_ddo: Gets the asset DDO.
        get_subscription_balance: Gets the subscription balance.
        get_service_token: Gets the service token.
        get_subscription_associated_services: Gets the subscription associated services.
        get_subscription_associated_files: Gets the subscription associated files.
        get_subscription_details: Gets the subscription details.
        get_service_details: Gets the service details.
        get_file_details: Gets the file details.
        get_checkout_subscription: Gets the checkout subscription.
        download_file: Downloads the file.
        mint_credits: Mints the credits associated to a subscription and send to the receiver.
        burn_credits: Burns credits associated to a subscription that you own.     
        """

    def __init__(self, nvm_api_key: str, environment: Environment,
                 app_id: Optional[str] = None, version: Optional[str] = None):
        self.nvm_api_key = nvm_api_key
        self.environment = environment
        self.app_id = app_id
        self.version = version

    def create_subscription(self, name: str, description: str, price: int, token_address: str,
                            amount_of_credits: Optional[int], duration: Optional[int], tags: Optional[List[str]]):
        """
        Creates a new subscription.

        Args:
            name (str): The name of the subscription.
            description (str): The description of the subscription.
            price (int): The price of the subscription.
            token_address (str): The token address.
            amount_of_credits (int, optional): The amount of credits for the subscription.
            duration (int, optional): The duration of the subscription.
            tags (List[str], optional): The tags associated with the subscription.

        Returns:
            Response: The response from the API call.
        """
        body = {
            "name": name,
            "description": description,
            "price": price,
            "tokenAddress": token_address,
            "amountOfCredits": amount_of_credits,
            "duration": duration,
            "tags": tags
        }
        headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'Authorization': f'''Bearer {self.nvm_api_key}'''
        }
        url = f"{self.environment.value['backend']}/api/v1/payments/subscription"
        response = requests.post(url, headers=headers, json=body)
        return response

    def create_service(self, subscription_did: str, name: str, description: str,
                       service_charge_type: str, auth_type: str, amount_of_credits: Optional[int] = None,
                       min_credits_to_charge: Optional[int] = None, max_credits_to_charge: Optional[int] = None,
                       username: Optional[str] = None, password: Optional[str] = None, token: Optional[str] = None,
                       endpoints: Optional[List[dict]] = None,
                       open_endpoints: Optional[List[str]] = None, open_api_url: Optional[str] = None,
                       integration: Optional[str] = None, sample_link: Optional[str] = None,
                       api_description: Optional[str] = None, curation: Optional[dict] = None,
                       duration: Optional[int] = None, tags: Optional[List[str]] = None):
        """
        Creates a new service.

        Args:
            subscription_did (str): The DID of the subscription.
            name (str): The name of the service.
            description (str): The description of the service.
            service_charge_type (str): The charge type of the service. ->  'fixed' | 'dynamic'
            auth_type (str): The authentication type of the service. -> 'none' | 'basic' | 'oauth'
            amount_of_credits (int, optional): The amount of credits for the service.
            min_credits_to_charge (int, optional): The minimum credits to charge for the service.
            max_credits_to_charge (int, optional): The maximum credits to charge for the service.
            username (str, optional): The username for authentication.
            password (str, optional): The password for authentication.
            token (str, optional): The token for authentication.
            endpoints (List[dict], optional): The endpoints of the service.
            open_endpoints (List[str], optional): The open endpoints of the service. -> [{"post": "https://api.example.app/api/v1/example"}]
            open_api_url (str, optional): The OpenAPI URL of the service.
            integration (str, optional): The integration type of the service.
            sample_link (str, optional): The sample link of the service.
            api_description (str, optional): The API description of the service.
            curation (dict, optional): The curation information of the service.
            duration (int, optional): The duration of the service.
            tags (List[str], optional): The tags associated with the service.

        Returns:
            Response: The response from the API call.
        """
        body = {
            "subscriptionDid": subscription_did,
            "name": name,
            "description": description,
            "serviceChargeType": service_charge_type,
            "authType": auth_type,
            **{snake_to_camel(k): v for k, v in locals().items() if v is not None and k != 'self'}
        }
        headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.nvm_api_key}'
        }
        url = f"{self.environment.value['backend']}/api/v1/payments/service"
        response = requests.post(url, headers=headers, json=body)
        return response

    def create_file(self, subscription_did: str, asset_type: str, name: str, description: str, files: List[dict],
                    data_schema: Optional[str] = None,
                    sample_code: Optional[str] = None,
                    files_format: Optional[str] = None, usage_example: Optional[str] = None,
                    programming_language: Optional[str] = None, framework: Optional[str] = None,
                    task: Optional[str] = None, training_details: Optional[str] = None,
                    variations: Optional[str] = None,
                    fine_tunable: Optional[bool] = None, amount_of_credits: Optional[int] = None,
                    min_credits_to_charge: Optional[int] = None, max_credits_to_charge: Optional[int] = None,
                    curation: Optional[dict] = None, duration: Optional[int] = None, tags: Optional[List[str]] = None):
        """
        Creates a new file.

        Args:
            subscription_did (str): The DID of the subscription.
            asset_type (str): The type of the asset. -> 'algorithm' | 'model' | 'dataset' | 'file'
            name (str): The name of the file.
            description (str): The description of the file.
            files (List[dict]): The files of the file.
            data_schema (str, optional): The data schema of the file.
            sample_code (str, optional): The sample code of the file.
            files_format (str, optional): The files format of the file.
            usage_example (str, optional): The usage example of the file.
            programming_language (str, optional): The programming language of the file.
            framework (str, optional): The framework of the file.
            task (str, optional): The task of the file.
            training_details (str, optional): The training details of the file.
            variations (str, optional): The variations of the file.
            fine_tunable (bool, optional): The fine tunable of the file.
            amount_of_credits (int, optional): The amount of credits for the file.
            min_credits_to_charge (int, optional): The minimum credits to charge for the file.
            max_credits_to_charge (int, optional): The maximum credits to charge for the file.
            curation (dict, optional): The curation information of the file.
            duration (int, optional): The duration of the file.
            tags (List[str], optional): The tags associated with the file.

        Returns:
            Response: The response from the API call.
        """
        body = {
            "subscriptionDid": subscription_did,
            "assetType": asset_type,
            "name": name,
            "description": description,
            "files": files,
            **{snake_to_camel(k): v for k, v in locals().items() if v is not None and k != 'self'}
        }
        headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.nvm_api_key}'

        }
        url = f"{self.environment.value['backend']}/api/v1/payments/file"
        response = requests.post(url, headers=headers, json=body)
        return response

    def order_subscription(self, subscription_did: str, agreementId: Optional[str] = None):
        """
        Orders the subscription.

        Args:
            subscription_did (str): The DID of the subscription.
            agreementId (str, optional): The agreement ID.

        Returns:
            Response: The response from the API call.
        """
        body = {
            "subscriptionDid": subscription_did,
            **{snake_to_camel(k): v for k, v in locals().items() if v is not None and k != 'self'}
        }
        headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.nvm_api_key}'
        }
        url = f"{self.environment.value['backend']}/api/v1/payments/subscription/order"
        response = requests.post(url, headers=headers, json=body)
        return response

    def get_asset_ddo(self, did: str):
        """
        Gets the asset DDO.

        Args:
            did (str): The DID of the asset.

        Returns:
            Response: The response from the API call.
        """
        headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        }
        url = f"{self.environment.value['backend']}/api/v1/payments/asset/ddo/{did}"
        response = requests.get(url, headers=headers)
        return response

    def get_subscription_balance(self, subscription_did: str, account_address: str):
        """
        Gets the subscription balance.

        Args:
            subscription_did (str): The DID of the subscription.
            account_address (str): The account address.

        Returns:
            Response: The response from the API call.
        """
        body = {
            **{snake_to_camel(k): v for k, v in locals().items() if v is not None and k != 'self'}
        }
        headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.nvm_api_key}'
        }
        url = (f"{self.environment.value['backend']}/api/v1/payments/subscription/balance")
        response = requests.post(url, headers=headers, json=body)
        return response

    def get_service_token(self, service_did: str):
        """
        Gets the service token.

        Args:
            service_did (str): The DID of the service.

        Returns:
            Response: The response from the API call.
        """
        headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.nvm_api_key}'
        }
        url = f"{self.environment.value['backend']}/api/v1/payments/service/token/{service_did}"
        response = requests.get(url, headers=headers)
        return response

    def get_subscription_associated_services(self, subscription_did: str):
        """
        Gets the subscription associated services.

        Args:
            subscription_did (str): The DID of the subscription.

        Returns:
            Response: List of DIDs of the associated services.
        """
        headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        }
        url = f"{self.environment.value['backend']}/api/v1/payments/subscription/services/{subscription_did}"
        response = requests.get(url, headers=headers)
        return response
    
    def get_subscription_associated_files(self, subscription_did: str):
        """
        Gets the subscription associated files.

        Args:
            subscription_did (str): The DID of the subscription.

        Returns:
            Response: List of DIDs of the associated files.
        """
        headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        }
        url = f"{self.environment.value['backend']}/api/v1/payments/subscription/files/{subscription_did}"
        response = requests.get(url, headers=headers)
        return response

    def get_subscription_details(self, subscription_did: str):
        """
        Gets the subscription details.

        Args:
            subscription_did (str): The DID of the subscription.

        Returns:
            Response: The url of the subscription details.
        """
        url = f"{self.environment.value['frontend']}/en/subscription/${subscription_did}"
        return url

    def get_service_details(self, service_did: str):
        """
        Gets the service details.

        Args:
            service_did (str): The DID of the service.

        Returns:
            Response: The url of the service details.
        """
        url = f"{self.environment.value['frontend']}/en/webservice/${service_did}"
        return url

    def get_file_details(self, file_did: str):
        """
        Gets the file details.

        Args:
            file_did (str): The DID of the file.

        Returns:
            Response: The url of the file details.
        """
        url = f"{self.environment.value['frontend']}/en/file/${file_did}"
        return url

    def get_checkout_subscription(self, subscription_did: str):
        """
        Gets the checkout subscription.

        Args:
            subscription_did (str): The DID of the subscription.

        Returns:
            Response: The url of the checkout subscription.
        """
        url = f"{self.environment.value['frontend']}/en/subscription/checkout/${subscription_did}"
        return url
    
    def download_file(self, file_did: str, agreement_id: Optional[str] = None, destination: Optional[str] = None):
        """
        Downloads the file.

        Args:
            file_did (str): The DID of the file.

        Returns:
            Response: The url of the file.
        """
        body = {
            "fileDid": file_did,
            **{snake_to_camel(k): v for k, v in locals().items() if v is not None and k != 'self'}
        }
        headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.nvm_api_key}'
        }
        url = f"{self.environment.value['backend']}/api/v1/payments/file/download/{file_did}"
        response = requests.post(url, headers=headers, json=body)
        return response

    def mint_credits(self, subscription_did: str, amount: str, receiver: str):
        """
        Mints the credits associated to a subscription and send to the receiver.

        Args:
            subscription_did (str): The DID of the subscription.
            amount (int): The amount of credits to mint.
            receiver (str): The receiver address of the credits.

        Returns:
            Response: The response from the API call.
        """
        body = {
            "did": subscription_did,
            "nftAmount": amount,
            "receiver": receiver
        }
        headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.nvm_api_key}'
        }
        url = f"{self.environment.value['backend']}/api/v1/payments/credits/mint"
        response = requests.post(url, headers=headers, json=body)
        print(body)
        print(url)
        print(response)
        return response
    
    def burn_credits(self, subscription_did: str, amount: str):
        """
        Burns credits associated to a subscription that you own.

        Args:
            subscription_did (str): The DID of the subscription.
            amount (int): The amount of credits to burn.

        Returns:
            Response: The response from the API call.
        """
        body = {
            "did": subscription_did,
            "nftAmount": amount
        }
        headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.nvm_api_key}'
        }
        url = f"{self.environment.value['backend']}/api/v1/payments/credits/burn"
        response = requests.post(url, headers=headers, json=body)
        return response