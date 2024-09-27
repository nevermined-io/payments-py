import os
from typing import List, Optional
import requests

from payments_py.data_models import BalanceResultDto, BurnResultDto, CreateAssetResultDto, DownloadFileResultDto, MintResultDto, OrderSubscriptionResultDto, ServiceTokenResultDto
from payments_py.environments import Environment
from payments_py.nvm_backend import BackendApiOptions, NVMBackendApi
from payments_py.ai_query_api import AIQueryApi
from payments_py.utils import snake_to_camel


class Payments(NVMBackendApi):
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
                 app_id: Optional[str] = None, version: Optional[str] = None, ai_protocol: bool = False, headers: Optional[dict] = None, web_socket_options: Optional[dict] = None):
        super().__init__(BackendApiOptions(environment, api_key=nvm_api_key, headers=headers, web_socket_options=web_socket_options))
        self.nvm_api_key = nvm_api_key
        self.environment = environment
        self.app_id = app_id
        self.version = version
        if ai_protocol:
            self.ai_protocol = AIQueryApi(BackendApiOptions(environment))

    def create_credits_subscription(self, name: str, description: str, price: int, token_address: str,
                            amount_of_credits: int, tags: Optional[List[str]] = None) -> CreateAssetResultDto:
        """
        Creates a new credits subscription.

        Args:
            name (str): The name of the subscription.
            description (str): The description of the subscription.
            price (int): The price of the subscription.
            token_address (str): The token address.
            amount_of_credits (int): The amount of credits for the subscription.
            tags (List[str], optional): The tags associated with the subscription.

        Returns:
            CreateAssetResultDto: The result of the creation operation.

        Raises:
            HTTPError: If the API call fails.

        Example:
            response = your_instance.create_credits_subscription(name="Basic Plan", description="100 credits subscription", price=1, token_address="0x1234", amount_of_credits=100, tags=["basic"])
            print(response)
        """
        body = {
            "name": name,
            "description": description,
            "price": price,
            "tokenAddress": token_address,
            "amountOfCredits": amount_of_credits,
            "tags": tags if tags else [],
            "subscriptionType": "credits"
        }
        url = f"{self.environment.value['backend']}/api/v1/payments/subscription"
        response = self.post(url, body)
        response.raise_for_status()
        return CreateAssetResultDto.model_validate(response.json())

    def create_time_subscription(self, name: str, description: str, price: int, token_address: str,
                            duration: Optional[int] = 0, tags: Optional[List[str]] = None) -> CreateAssetResultDto:
        """
        Creates a new time subscription.

        Args:
            name (str): The name of the subscription.
            description (str): The description of the subscription.
            price (int): The price of the subscription.
            token_address (str): The token address.
            duration (int, optional): The duration of the subscription in days. If not provided, the subscription will be valid forever.
            tags (List[str], optional): The tags associated with the subscription.

        Returns:
            CreateAssetResultDto: The result of the creation operation.

        Raises:
            HTTPError: If the API call fails.

        Example:
            response = your_instance.create_time_subscription(name="Yearly Plan", description="Annual subscription", price=1200, token_address="0x5678", duration=365, tags=["yearly", "premium"])
            print(response)
        """
        body = {
            "name": name,
            "description": description,
            "price": price,
            "tokenAddress": token_address,
            "duration": duration,
            "tags": tags if tags else [],
            "subscriptionType": "time"

        }
        url = f"{self.environment.value['backend']}/api/v1/payments/subscription"
        response = self.post(url, body)
        response.raise_for_status()
        return CreateAssetResultDto.model_validate(response.json())
    
    def create_service(self, subscription_did: str, name: str, description: str,
                       service_charge_type: str, auth_type: str, amount_of_credits: int = 1,
                       min_credits_to_charge: Optional[int] = None, max_credits_to_charge: Optional[int] = None,
                       username: Optional[str] = None, password: Optional[str] = None, token: Optional[str] = None,
                       endpoints: Optional[List[dict]] = None,
                       open_endpoints: Optional[List[str]] = None, open_api_url: Optional[str] = None,
                       integration: Optional[str] = None, sample_link: Optional[str] = None,
                       api_description: Optional[str] = None, curation: Optional[dict] = None,
                       tags: Optional[List[str]] = None) -> CreateAssetResultDto:
        """
        Creates a new service.

        Args:
            subscription_did (str): The DID of the subscription.
            name (str): The name of the service.
            description (str): The description of the service.
            service_charge_type (str): The charge type of the service. Options: 'fixed', 'dynamic'
            auth_type (str): The authentication type of the service. Options: 'none', 'basic', 'oauth'
            amount_of_credits int: The amount of credits for the service.
            min_credits_to_charge (int, optional): The minimum credits to charge for the service. Only required for dynamic services.
            max_credits_to_charge (int, optional): The maximum credits to charge for the service. Only required for dynamic services.
            username (str, optional): The username for authentication.
            password (str, optional): The password for authentication.
            token (str, optional): The token for authentication.
            endpoints (List[Dict[str, str]], optional): The endpoints of the service.
            open_endpoints (List[str], optional): The open endpoints of the service.
            open_api_url (str, optional): The OpenAPI URL of the service.
            integration (str, optional): The integration type of the service.
            sample_link (str, optional): The sample link of the service.
            api_description (str, optional): The API description of the service.
            curation (dict, optional): The curation information of the service.
            tags (List[str], optional): The tags associated with the service.

        Returns:
            CreateAssetResultDto: The result of the creation operation.

        Raises:
            HTTPError: If the API call fails.

        Example:
            response = your_instance.create_service(subscription_did="did:nv:abc123", name="My Service", description="A sample service", service_charge_type="fixed", auth_type="none")
            print(response)
        """
        body = {
            "subscriptionDid": subscription_did,
            "name": name,
            "description": description,
            "serviceChargeType": service_charge_type,
            "authType": auth_type,
            **{snake_to_camel(k): v for k, v in locals().items() if v is not None and k != 'self'}
        }
        url = f"{self.environment.value['backend']}/api/v1/payments/service"
        response = self.post(url, data=body)
        response.raise_for_status()
        return CreateAssetResultDto.model_validate(response.json())
    
    def create_file(self, subscription_did: str, asset_type: str, name: str, description: str, files: List[dict],
                    data_schema: Optional[str] = None,
                    sample_code: Optional[str] = None,
                    files_format: Optional[str] = None, usage_example: Optional[str] = None,
                    programming_language: Optional[str] = None, framework: Optional[str] = None,
                    task: Optional[str] = None, training_details: Optional[str] = None,
                    variations: Optional[str] = None,
                    fine_tunable: Optional[bool] = None, amount_of_credits: Optional[int] = None,
                    min_credits_to_charge: Optional[int] = None, max_credits_to_charge: Optional[int] = None,
                    curation: Optional[dict] = None, tags: Optional[List[str]] = None) -> CreateAssetResultDto:
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
            tags (List[str], optional): The tags associated with the file.

        Returns:
            CreateAssetResultDto: The result of the creation operation.

        Raises:
            HTTPError: If the API call fails.

        Example:
            response = your_instance.create_file(subscription_did="did:nv:xyz789", asset_type="dataset", name="Sample Dataset", description="A sample dataset", files=[{"name": "file1.csv", "url": "https://example.com/file1.csv"}])
            print(response)
        """
        body = {
            "subscriptionDid": subscription_did,
            "assetType": asset_type,
            "name": name,
            "description": description,
            "files": files,
            **{snake_to_camel(k): v for k, v in locals().items() if v is not None and k != 'self'}
        }
        url = f"{self.environment.value['backend']}/api/v1/payments/file"
        response = self.post(url, data=body)
        response.raise_for_status()
        return CreateAssetResultDto.model_validate(response.json())
    
    def order_subscription(self, subscription_did: str, agreementId: Optional[str] = None) -> OrderSubscriptionResultDto:
        """
        Orders the subscription.

        Args:
            subscription_did (str): The DID of the subscription.
            agreementId (str, optional): The agreement ID.

        Returns:
            OrderSubscriptionResultDto: The result of the order operation, containing the agreement ID and success status.

        Raises:
            HTTPError: If the API call fails.

        Example:
            response = your_instance.order_subscription(subscription_did="did:nv:a0079b517e580d430916924f1940b764e17c31e368c509483426f8c2ac2e7116")
            print(response)
        """
        body = {
            "subscriptionDid": subscription_did,
            **{snake_to_camel(k): v for k, v in locals().items() if v is not None and k != 'self'}
        }
        url = f"{self.environment.value['backend']}/api/v1/payments/subscription/order"
        response = self.post(url, data=body)
        response.raise_for_status()
        return OrderSubscriptionResultDto.model_validate(response.json())

    def get_asset_ddo(self, did: str):
        """
        Gets the asset DDO.

        Args:
            did (str): The DID of the asset.

        Returns:
            Response: The response from the API call.
        """
        response = self.get(f"{self.environment.value['backend']}/api/v1/payments/asset/ddo/{did}")
        return response

    def get_subscription_balance(self, subscription_did: str, account_address: str) -> BalanceResultDto:
        """
        Gets the subscription balance.

        Args:
            subscription_did (str): The DID of the subscription.
            account_address (str): The account address.

        Returns:
            BalanceResultDto: The response from the API call formatted as a BalanceResultDto.

        Raises:
            HTTPError: If the API call fails.
            
        Example:
            response = your_instance.get_subscription_balance(subscription_did="did:example:123456", account_address="0xABC123")
            response.raise_for_status()
            balance = BalanceResultDto.model_validate(response.json())
            print(balance)

        Expected Response:
            {
                "subscriptionType": "credits",
                "isOwner": True,
                "isSubscriptor": True,
                "balance": 10000000
            }
        """
        body = {
            **{snake_to_camel(k): v for k, v in locals().items() if v is not None and k != 'self'}
        }
        url = (f"{self.environment.value['backend']}/api/v1/payments/subscription/balance")
        response = self.post(url, body)
        response.raise_for_status()
        return BalanceResultDto.model_validate(response.json())
    
    def get_service_token(self, service_did: str) -> ServiceTokenResultDto:
        """
        Gets the service token.

        Args:
            service_did (str): The DID of the service.

        Returns:
            ServiceTokenResultDto: The result of the creation operation.

        Raises:
            HTTPError: If the API call fails.

        Example:
            response = your_instance.get_service_token(service_did="did:nv:xyz789")
            print(response)
        """
        url = f"{self.environment.value['backend']}/api/v1/payments/service/token/{service_did}"
        response = self.get(url)
        response.raise_for_status() 
        return ServiceTokenResultDto.model_validate(response.json()['token'])
    
    def get_subscription_associated_services(self, subscription_did: str):
        """
        Gets the subscription associated services.

        Args:
            subscription_did (str): The DID of the subscription.

        Returns:
            Response: List of DIDs of the associated services.
        """
        url = f"{self.environment.value['backend']}/api/v1/payments/subscription/services/{subscription_did}"
        response = self.get(url)
        return response
    
    def get_subscription_associated_files(self, subscription_did: str):
        """
        Gets the subscription associated files.

        Args:
            subscription_did (str): The DID of the subscription.

        Returns:
            Response: List of DIDs of the associated files.
        """
        url = f"{self.environment.value['backend']}/api/v1/payments/subscription/files/{subscription_did}"
        response = self.get(url)
        return response

    def get_subscription_details_url(self, subscription_did: str):
        """
        Gets the subscription details.

        Args:
            subscription_did (str): The DID of the subscription.

        Returns:
            Response: The url of the subscription details.
        """
        url = f"{self.environment.value['frontend']}/en/subscription/{subscription_did}"
        return url

    def get_service_details_url(self, service_did: str):
        """
        Gets the service details.

        Args:
            service_did (str): The DID of the service.

        Returns:
            Response: The url of the service details.
        """
        url = f"{self.environment.value['frontend']}/en/webservice/{service_did}"
        return url

    def get_file_details_url(self, file_did: str):
        """
        Gets the file details.

        Args:
            file_did (str): The DID of the file.

        Returns:
            Response: The url of the file details.
        """
        url = f"{self.environment.value['frontend']}/en/file/{file_did}"
        return url

    def get_checkout_subscription(self, subscription_did: str):
        """
        Gets the checkout subscription.

        Args:
            subscription_did (str): The DID of the subscription.

        Returns:
            Response: The url of the checkout subscription.
        """
        url = f"{self.environment.value['frontend']}/en/subscription/checkout/{subscription_did}"
        return url
    
    def download_file(self, file_did: str, destination: str, agreement_id: Optional[str] = None) -> DownloadFileResultDto:
        """
        Downloads the file.

        Args:
            file_did (str): The DID of the file.
            agreement_id (str, optional): The agreement ID.
            destination str: The destination of the file.

        Returns:
            Response: The url of the file.
        Returns:
            DownloadFileResultDto: The result of the download operation.

        Raises:
            HTTPError: If the API call fails.

        Example:
            response = your_instance.download_file(file_did="did:nv:7e38d39405445ab3e5435d8c1c6653a00ddc425ba629789f58fbefccaa5e5a5d", destination="/tmp")
            print(response)

        """
        body = {
            "fileDid": file_did,
            "agreementId": agreement_id if agreement_id else '0x',
        }
        headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.nvm_api_key}'
        }
        url = f"{self.environment.value['backend']}/api/v1/payments/file/download"

        try:
            with requests.post(url, headers=headers, json=body, stream=True) as r:
                r.raise_for_status()
                content_disposition = r.headers.get('Content-Disposition')
                if content_disposition:
                    filename = content_disposition.split('filename=')[-1].strip('"')
                else:
                    filename = 'downloaded_file'

                if os.path.isdir(destination):
                    destination = os.path.join(destination, filename)

                with open(destination, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
        
            return DownloadFileResultDto.model_validate({"success": True })
        except requests.exceptions.HTTPError as e:
            return DownloadFileResultDto.model_validate({"success": False })

    def mint_credits(self, subscription_did: str, amount: str, receiver: str) -> MintResultDto:
        """
        Mints the credits associated with a subscription and sends them to the receiver.

        Args:
            subscription_did (str): The DID of the subscription.
            amount (str): The amount of credits to mint.
            receiver (str): The receiver address of the credits.

        Returns:
            MintResultDto: The result of the minting operation.

        Raises:
            HTTPError: If the API call fails.

        Example:
            response = your_instance.mint_credits(subscription_did="did:nv:e405a91e3152be1430c5d0607ebdf9236c19f34bfba0320798d81ba5f5e3e3a5", amount="12", receiver="0x4fe3e7d42fA83be4E8cF03451Ac3F25980a73fF6")
            print(response)
        """
        body = {
            "did": subscription_did,
            "nftAmount": amount,
            "receiver": receiver
        }
        url = f"{self.environment.value['backend']}/api/v1/payments/credits/mint"
        response = self.post(url, body)
        response.raise_for_status()
        return MintResultDto(userOpHash=response.json()['userOpHash'], success=response.json()['success'], amount=amount)
    
    def burn_credits(self, subscription_did: str, amount: str) -> BurnResultDto:
        """
        Burns credits associated with a subscription that you own.

        Args:
            subscription_did (str): The DID of the subscription.
            amount (str): The amount of credits to burn.

        Returns:
            BurnResultDto: The result of the burning operation.

        Raises:
            HTTPError: If the API call fails.

        Example:
            response = your_instance.burn_credits(subscription_did="did:nv:e405a91e3152be1430c5d0607ebdf9236c19f34bfba0320798d81ba5f5e3e3a5", amount="12")
            print(response)
        """
        body = {
            "did": subscription_did,
            "nftAmount": amount
        }
        url = f"{self.environment.value['backend']}/api/v1/payments/credits/burn"
        response = self.post(url, body)
        response.raise_for_status()
        return BurnResultDto(userOpHash=response.json()['userOpHash'], success=response.json()['success'], amount=amount)
    
    ## AI module

    # def get_owner_agents_tasks(self, status: Optional[str] = None):
    #     """
    #     Gets the tasks of the owner agents.

    #     Args:
    #         status (str): The status of the tasks. It could be 'Pending', 'In_Progress', 'Completed', 'Failed', 'Not_Ready'.

    #     Returns:
    #         Response: The response from the API call.
    #     Example:
    #         response = your_instance.get_owner_agents_tasks()
    #         print(response)
    #     """
    #     headers = {
    #         'Accept': 'application/json',
    #         'Content-Type': 'application/json',
    #         'Authorization': f'Bearer {self.nvm_api_key}'
    #     }
    #     url = f"{self.environment.value['backend']}/api/v1/agents"
    #     if status is not None:
    #         url += f"?status={status}"
    #     response = requests.get(url, headers=headers)
    #     return response
    
    # def get_agents_steps(self, dids: str, status: Optional[str] = None, ):
    #     """
    #     Gets the steps of the agents.

    #     Args:
    #         dids (str): Comma separated list of dids
    #         status (str): The status of the steps. It could be 'Pending', 'In_Progress', 'Completed', 'Failed', 'Not_Ready'.
    #     Returns:
    #         Response: The response from the API call.
    #     Example:
    #         response = your_instance.get_agents_steps(status="Completed", dids="did:nv:abc123")
    #         print(response)
    #     """
    #     headers = {
    #         'Accept': 'application/json',
    #         'Content-Type': 'application/json',
    #         'Authorization': f'Bearer {self.nvm_api_key}'
    #     }
    #     url = f"{self.environment.value['backend']}/api/v1/agents/steps?dids={dids}"
    #     if status is not None:
    #         url += f"&status={status}"
    #     response = requests.get(url, headers=headers)
    #     return response
    
    # def get_task_steps(self, did: str, task_id: str, status: Optional[str] = None):
    #     """
    #     Gets the steps of the task.

    #     Args:
    #         did (str): The DID of the task.
    #         task_id (str): The ID of the task.
    #         status (str): The status of the steps. It could be 'Pending', 'In_Progress', 'Completed', 'Failed', 'Not_Ready'.
    #     Returns:
    #         Response: The response from the API call.
    #     Example:
    #         response = your_instance.get_task_steps(did="did:nv:abc123", task_id="123456")
    #         print(response)
    #     """
    #     headers = {
    #         'Accept': 'application/json',
    #         'Content-Type': 'application/json',
    #         'Authorization': f'Bearer {self.nvm_api_key}'
    #     }
    #     url = f"{self.environment.value['backend']}/api/v1/agents/{did}/tasks/{task_id}/steps"
    #     if status is not None:
    #         url += f"?status={status}"
    #     response = requests.get(url, headers=headers)
    #     return response
    
    # def add_steps(self, did:str, task_id: str, steps: List[CreateStepsDto]):
    #     """
    #     Adds steps to the task.

    #     Args:
    #         did (str): The DID of the task.
    #         task_id (str): The ID of the task.
    #         steps (List[dict]): The steps to add.
    #     Returns:
    #         Response: The response from the API call.
    #     Example:
    #         response = your_instance.add_steps(did="did:nv:abc123", task_id="123456", steps=[{"name": "Step 1", "status": "Pending"}])
    #         print(response)
    #     """
    #     body = {
    #         "steps": steps
    #     }
    #     headers = {
    #         'Accept': 'application/json',
    #         'Content-Type': 'application/json',
    #         'Authorization': f'Bearer {self.nvm_api_key}'
    #     }
    #     url = f"{self.environment.value['backend']}/api/v1/agents/{did}/tasks/{task_id}/steps"
    #     response = requests.post(url, headers=headers, json=body)
    #     return response
    
    # def update_step(self, did:str, task_id: str, step_id: str, steps: List[UpdateStepDto]):
    #     """
    #     Updates the step.

    #     Args:
    #         did (str): The DID of the task.
    #         task_id (str): The ID of the task.
    #         step_id (str): The ID of the step.
    #         steps (List[dict]): The steps to add.
    #     Returns:
    #         Response: The response from the API call.
    #     Example:
    #         response = your_instance.update_step(did="did:nv:abc123", task_id="123456", step_id="654321", status="Completed")
    #         print(response)
    #     """
    #     body = {
    #         "steps": steps
    #     }
    #     headers = {
    #         'Accept': 'application/json',
    #         'Content-Type': 'application/json',
    #         'Authorization': f'Bearer {self.nvm_api_key}'
    #     }
    #     url = f"{self.environment.value['backend']}/api/v1/agents/{did}/tasks/{task_id}/step/{step_id}"
    #     response = requests.put(url, headers=headers, json=body)
    #     return response
    
    # def request_agent_task(self, did:str, input: CreateTaskDto):
    #     """
    #     Requests the agent task.

    #     Args:
    #         did (str): The DID of the task.
    #         input (CreateTaskDto): The input for the task.
    #     Returns:
    #         Response: The response from the API call.
    #     Example:
    #         response = your_instance.request_agent_task(did="did:nv:abc123", input={"query": "What's the weather in NY now?"})
    #         print(response)
    #     """
    #     body = {
    #         "input": input
    #     }
    #     headers = {
    #         'Accept': 'application/json',
    #         'Content-Type': 'application/json',
    #         'Authorization': f'Bearer {self.nvm_api_key}'
    #     }
    #     url = f"{self.environment.value['backend']}/api/v1/agents/{did}/tasks"
    #     response = requests.post(url, headers=headers, json=body)
    #     return response
    
    # def get_task(self, did: str, task_id: str, user_id: str):
        """
        Gets the task.

        Args:
            did (str): The DID of the task.
            task_id (str): The ID of the task.
            user_id (str): The ID of the user.
        Returns:
            Response: The response from the API call.
        Example:
            response = your_instance.get_task(did="did:nv:abc123", task_id="123456", user_id="123")
            print(response)
        """
        headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.nvm_api_key}',
            'NVM-User-id': user_id
        }
        url = f"{self.environment.value['backend']}/api/v1/agents/{did}/tasks/{task_id}"
        response = requests.get(url, headers=headers)
        return response