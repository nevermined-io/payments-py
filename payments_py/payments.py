import os
from typing import Optional
import warnings
import requests
import jwt

from payments_py.data_models import (
    BalanceResultDto,
    BurnResultDto,
    CreateAgentAndPlanResultDto,
    CreateAgentDto,
    CreateAssetResultDto,
    CreateCreditsPlanDto,
    CreateFileDto,
    CreateServiceDto,
    DownloadFileResultDto,
    MintResultDto,
    OrderPlanResultDto,
    ServiceTokenResultDto,
    CreateTimePlanDto,
)
from payments_py.environments import Environment
from payments_py.nvm_backend import BackendApiOptions, NVMBackendApi
from payments_py.ai_query_api import AIQueryApi
from payments_py.utils import (
    get_ai_hub_open_api_url,
    get_query_protocol_endpoints,
    snake_to_camel,
)


class Payments(NVMBackendApi):
    """
    A class representing a payment system.

    Attributes:
        nvm_api_key (str): The nvm api key for authentication.
        environment (Environment): The environment for the payment system.
        app_id (str, optional): The application ID.
        version (str, optional): The version of the payment system.
        headers (dict, optional): The headers for the payment system.
    Methods:
        create_credits_plan: Creates a new credits plan.
        create_time_plan: Creates a new time plan.
        create_service: Creates a new service.
        create_file: Creates a new file.
        create_agent: Creates a new agent
        create_agent_and_plan: Creates a new agent associated to a plan in one step
        order_plan: Orders the plan.
        get_asset_ddo: Gets the asset DDO.
        get_plan_balance: Gets the plan balance.
        get_service_token: Gets the service token.
        get_plan_associated_services: Gets the plan associated services.
        get_plan_associated_files: Gets the plan associated files.
        get_plan_details_url: Gets the plan details.
        get_service_details_url: Gets the service details.
        get_file_details_url: Gets the file details.
        get_checkout_plan: Gets the checkout plan.
        download_file: Downloads the file.
        mint_credits: Mints the credits associated to a plan and send to the receiver.
        burn_credits: Burns credits associated to a plan that you own.
        search_plans: Query for plans base on an input query options.
        search_agents: Query for agents base on an input query options.
        query: The AI Query API.
        ai_protocol: The AI Query API. Deprecated
    """

    def __init__(
        self,
        nvm_api_key: str,
        environment: Environment,
        app_id: Optional[str] = None,
        version: Optional[str] = None,
        headers: Optional[dict] = None,
    ):
        self.backend_options = BackendApiOptions(
            environment, api_key=nvm_api_key, headers=headers
        )
        super().__init__(self.backend_options)
        self.nvm_api_key: str = nvm_api_key
        self.environment: Environment = environment
        self.app_id: Optional[str] = app_id
        self.version: Optional[str] = version
        decoded_jwt: dict = jwt.decode(
            self.nvm_api_key, options={"verify_signature": False}
        )
        self.account_address: str = decoded_jwt.get("sub")
        self.query: AIQueryApi = AIQueryApi(self.backend_options)
        warnings.warn(
            "`self.ai_protocol` is deprecated and will be removed in a future version. Use `self.query` instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        self.ai_protocol: AIQueryApi = self.query

    def create_credits_plan(
        self, createCreditsPlanDto: CreateCreditsPlanDto
    ) -> CreateAssetResultDto:
        """
        It allows to an AI Builder to create a Payment Plan on Nevermined based on Credits.
        A Nevermined Credits Plan limits the access by the access/usage of the Plan.
        With them, AI Builders control the number of requests that can be made to an agent or service.
        Every time a user accesses any resource associated to the Payment Plan, the usage consumes from a capped amount of credits.
        When the user consumes all the credits, the plan automatically expires and the user needs to top up to continue using the service.

        This method is oriented to AI Builders.

        https://docs.nevermined.app/docs/tutorials/builders/create-plan

        Args:
            createCreditsPlanDto (CreateCreditsPlanDto): Options for the plan creation

        Returns:
            CreateAssetResultDto: The result of the creation operation.

        Raises:
            HTTPError: If the API call fails.

        Example:
            response = your_instance.create_credits_plan(CreateCreditsPlanDto(name="Basic Plan", description="100 credits plan", price=1, token_address="0x1234", amount_of_credits=100, tags=["basic"]))
            print(response)
        """
        metadata = {
            "main": {
                "name": createCreditsPlanDto.name,
                "type": "subscription",
                "license": "No License Specified",
                "files": [],
                "ercType": 1155,
                "nftType": "nft1155-credit",
                "subscription": {
                    "subscriptionType": "credits",
                },
            },
            "additionalInformation": {
                "description": createCreditsPlanDto.description,
                "tags": createCreditsPlanDto.tags if createCreditsPlanDto.tags else [],
                "customData": {
                    "dateMeasure": "days",
                    "plan": "custom",
                    "subscriptionLimitType": "credits",
                },
            },
        }
        service_attributes = [
            {
                "serviceType": "nft-sales",
                "price": createCreditsPlanDto.price,
                "nft": {
                    "amount": createCreditsPlanDto.amount_of_credits,
                    "nftTransfer": False,
                },
            },
        ]

        body = {
            "price": createCreditsPlanDto.price,
            "tokenAddress": createCreditsPlanDto.token_address,
            "metadata": metadata,
            "serviceAttributes": service_attributes,
        }
        url = f"{self.environment.value['backend']}/api/v1/payments/subscription"
        response = self.post(url, body)
        response.raise_for_status()
        return CreateAssetResultDto.model_validate(response.json())

    def create_time_plan(
        self, createTimePlanDto: CreateTimePlanDto
    ) -> CreateAssetResultDto:
        """
        It allows to an AI Builder to create a Payment Plan on Nevermined based on Time.
        A Nevermined Time Plan limits the access by the a specific amount of time.
        With them, AI Builders can specify the duration of the Payment Plan (1 month, 1 year, etc.).
        When the time period is over, the plan automatically expires and the user needs to renew it.

        This method is oriented to AI Builders

        https://docs.nevermined.app/docs/tutorials/builders/create-plan

        Args:
            createTimePlanDto: (CreateTimePlanDto):  Options for the plan creation

        Returns:
            CreateAssetResultDto: The result of the creation operation.

        Raises:
            HTTPError: If the API call fails.

        Example:
            response = your_instance.create_time_plan(CreateTimePlanDto(name="Yearly Plan", description="Annual plan", price=1200, token_address="0x5678", duration=365, tags=["yearly", "premium"]))
            print(response)
        """
        metadata = {
            "main": {
                "name": createTimePlanDto.name,
                "type": "subscription",
                "license": "No License Specified",
                "files": [],
                "ercType": 1155,
                "nftType": "nft1155-credit",
                "subscription": {
                    "subscriptionType": "time",
                },
            },
            "additionalInformation": {
                "description": createTimePlanDto.description,
                "tags": createTimePlanDto.tags if createTimePlanDto.tags else [],
                "customData": {
                    "dateMeasure": "days",
                    "plan": "custom",
                    "subscriptionLimitType": "time",
                },
            },
        }

        service_attributes = [
            {
                "serviceType": "nft-sales",
                "price": createTimePlanDto.price,
                "nft": {
                    "duration": createTimePlanDto.duration,
                    "amount": 1,
                    "nftTransfer": False,
                },
            },
        ]
        body = {
            "metadata": metadata,
            "serviceAttributes": service_attributes,
            "price": createTimePlanDto.price,
            "tokenAddress": createTimePlanDto.token_address,
        }
        url = f"{self.environment.value['backend']}/api/v1/payments/subscription"
        response = self.post(url, body)
        response.raise_for_status()
        return CreateAssetResultDto.model_validate(response.json())

    def create_service(
        self, createServiceDto: CreateServiceDto
    ) -> CreateAssetResultDto:
        """
        It creates a new AI Agent or Service on Nevermined.
        The agent/service must be associated to a Payment Plan. Users that are subscribers of a payment plan can access the agent/service.
        Depending on the Payment Plan and the configuration of the agent/service, the usage of the agent/service will consume credits.
        When the plan expires (because the time is over or the credits are consumed), the user needs to renew the plan to continue using the agent/service.

        This method is oriented to AI Builders

        https://docs.nevermined.app/docs/tutorials/builders/register-agent

        Args:
            createServiceDto: (CreateServiceDto):  Options for the service creation

        Returns:
            CreateAssetResultDto: The result of the creation operation.

        Raises:
            HTTPError: If the API call fails.

        Example:
            response = your_instance.create_service(plan_did="did:nv:abc123", service_type="service", name="My Service", description="A sample service", service_charge_type="fixed", auth_type="none")
            print(response)
        """
        metadata = {
            "main": {
                "name": createServiceDto.name,
                "license": "No License Specified",
                "type": createServiceDto.service_type,
                "files": [],
                "ercType": "nft1155",
                "nftType": "nft1155Credit",
                "subscription": {
                    "timeMeasure": "days",
                    "subscriptionType": "credits",
                },
                "webService": {
                    "endpoints": createServiceDto.endpoints,
                    "openEndpoints": createServiceDto.open_endpoints,
                    "internalAttributes": {
                        "authentication": {
                            "type": (
                                createServiceDto.auth_type
                                if createServiceDto.auth_type
                                else "none"
                            ),
                            **(
                                {
                                    "username": createServiceDto.username,
                                    "password": createServiceDto.password,
                                }
                                if createServiceDto.auth_type == "basic"
                                else {}
                            ),
                            **(
                                {"token": createServiceDto.token}
                                if createServiceDto.auth_type == "oauth"
                                else {}
                            ),
                        },
                        **(
                            {
                                "headers": [
                                    {
                                        "Authorization": f"Bearer {createServiceDto.token}"
                                    }
                                ]
                            }
                            if createServiceDto.auth_type == "oauth"
                            and createServiceDto.token
                            else {}
                        ),
                    },
                    "chargeType": createServiceDto.service_charge_type,
                    "isNeverminedHosted": createServiceDto.is_nevermined_hosted,
                    "implementsQueryProtocol": createServiceDto.implements_query_protocol,
                    "queryProtocolVersion": createServiceDto.query_protocol_version,
                    "serviceHost": (
                        self.environment.value["backend"]
                        if createServiceDto.is_nevermined_hosted
                        else createServiceDto.service_host
                    ),
                },
            },
            "additionalInformation": {
                "description": createServiceDto.description,
                "tags": createServiceDto.tags if createServiceDto.tags else [],
                "customData": {
                    "openApiUrl": createServiceDto.open_api_url,
                    "integration": createServiceDto.integration,
                    "sampleLink": createServiceDto.sample_link,
                    "apiDescription": createServiceDto.api_description,
                    "plan": "custom",
                    "serviceChargeType": createServiceDto.service_charge_type,
                },
            },
        }
        service_attributes = [
            {
                "serviceType": "nft-access",
                "nft": {
                    "amount": (
                        createServiceDto.amount_of_credits
                        if createServiceDto.amount_of_credits
                        else None
                    ),
                    "tokenId": createServiceDto.plan_did,
                    "minCreditsToCharge": createServiceDto.min_credits_to_charge,
                    "minCreditsRequired": createServiceDto.min_credits_to_charge,
                    "maxCreditsToCharge": createServiceDto.max_credits_to_charge,
                    "nftTransfer": False,
                },
            },
        ]
        body = {
            "metadata": metadata,
            "serviceAttributes": service_attributes,
            "subscriptionDid": createServiceDto.plan_did,
        }
        url = f"{self.environment.value['backend']}/api/v1/payments/service"
        response = self.post(url, data=body)
        response.raise_for_status()
        return CreateAssetResultDto.model_validate(response.json())

    def create_file(self, createFileDto: CreateFileDto) -> CreateAssetResultDto:
        """
        It creates a new asset with file associated to it.
        The file asset must be associated to a Payment Plan. Users that are subscribers of a payment plan can download the files attached to it.
        Depending on the Payment Plan and the configuration of the file asset, the download will consume credits.
        When the plan expires (because the time is over or the credits are consumed), the user needs to renew the plan to continue downloading the files.

        This method is oriented to AI Builders

        https://docs.nevermined.app/docs/tutorials/builders/register-file-asset

        Args:
            createFileDto: (CreateFileDto):  Options for the file creation.

        Returns:
            CreateAssetResultDto: The result of the creation operation.

        Raises:
            HTTPError: If the API call fails.

        Example:
            response = your_instance.create_file(plan_did="did:nv:xyz789", asset_type="dataset", name="Sample Dataset", description="A sample dataset", files=[{"name": "file1.csv", "url": "https://example.com/file1.csv"}])
            print(response)
        """
        metadata = {
            "main": {
                "name": createFileDto.name,
                "license": "No License Specified",
                "type": createFileDto.asset_type,
                "files": createFileDto.files,
                "ercType": "nft1155",
                "nftType": "nft1155Credit",
            },
            "additionalInformation": {
                "description": createFileDto.description,
                "tags": createFileDto.tags if createFileDto.tags else [],
                "customData": {
                    # coverFile: coverFile?.[0],
                    # conditionsFile: conditionsFile?.[0],
                    # sampleData: sampleData?.[0],
                    "dataSchema": createFileDto.data_schema,
                    "sampleCode": createFileDto.sample_code,
                    "usageExample": createFileDto.usage_example,
                    "filesFormat": createFileDto.files_format,
                    "programmingLanguage": createFileDto.programming_language,
                    "framework": createFileDto.framework,
                    "task": createFileDto.task,
                    "architecture": createFileDto.task,
                    "trainingDetails": createFileDto.training_details,
                    "variations": createFileDto.variations,
                    "fineTunable": createFileDto.fine_tunable,
                    "plan": "custom",
                },
            },
        }
        service_attributes = [
            {
                "serviceType": "nft-access",
                "nft": {
                    "tokenId": createFileDto.plan_did,
                    "amount": (
                        createFileDto.amount_of_credits
                        if createFileDto.amount_of_credits
                        else None
                    ),
                    "nftTransfer": False,
                },
            },
        ]
        body = {
            "metadata": metadata,
            "serviceAttributes": service_attributes,
            "subscriptionDid": createFileDto.plan_did,
        }
        url = f"{self.environment.value['backend']}/api/v1/payments/file"
        response = self.post(url, data=body)
        response.raise_for_status()
        return CreateAssetResultDto.model_validate(response.json())

    def create_agent(self, createAgentDto: CreateAgentDto) -> CreateAssetResultDto:
        """
        It creates a new AI Agent on Nevermined.
        The agent must be associated to a Payment Plan. Users that are subscribers of a payment plan can access the agent.
        Depending on the Payment Plan and the configuration of the agent, the usage of the agent will consume credits.
        When the plan expires (because the time is over or the credits are consumed), the user needs to renew the plan to continue using the agent.

        This method is oriented to AI Builders

        https://docs.nevermined.app/docs/tutorials/builders/register-agent

        Args:

            createAgentDto: (CreateAgentDto):  Options for the agent creation.


        """
        if createAgentDto.use_ai_hub:
            createAgentDto.service_host = self.environment.value["backend"]
            createAgentDto.implements_query_protocol = True
            createAgentDto.open_api_url = get_ai_hub_open_api_url(
                createAgentDto.service_host
            )
            createAgentDto.endpoints = get_query_protocol_endpoints(
                createAgentDto.service_host
            )

        return self.create_service(
            createServiceDto=CreateServiceDto(
                plan_did=createAgentDto.plan_did,
                service_type="agent",
                name=createAgentDto.name,
                description=createAgentDto.description,
                service_charge_type=createAgentDto.service_charge_type,
                auth_type=createAgentDto.auth_type,
                amount_of_credits=createAgentDto.amount_of_credits,
                min_credits_to_charge=createAgentDto.min_credits_to_charge,
                max_credits_to_charge=createAgentDto.max_credits_to_charge,
                username=createAgentDto.username,
                password=createAgentDto.password,
                token=createAgentDto.token,
                endpoints=createAgentDto.endpoints,
                open_endpoints=createAgentDto.open_endpoints,
                open_api_url=createAgentDto.open_api_url,
                integration=createAgentDto.integration,
                sample_link=createAgentDto.sample_link,
                api_description=createAgentDto.api_description,
                tags=createAgentDto.tags,
                use_ai_hub=createAgentDto.use_ai_hub,
                implements_query_protocol=createAgentDto.implements_query_protocol,
                query_protocol_version=createAgentDto.query_protocol_version,
                service_host=createAgentDto.service_host,
            )
        )

    def create_agent_and_plan(
        self, createCreditsPlanDto: CreateCreditsPlanDto, createAgentDto: CreateAgentDto
    ) -> CreateAgentAndPlanResultDto:
        """
        It creates a new AI Agent and a Payment Plan on Nevermined.

        The agent must be associated to the Payment Plan. Users that are subscribers of a payment plan can access the agent.

        Depending on the Payment Plan and the configuration of the agent, the usage of the agent will consume credits.

        When the plan expires (because the time is over or the credits are consumed), the user needs to renew the plan to continue using the agent.

        This method is oriented to AI Builders

        https://docs.nevermined.app/docs/tutorials/builders/register-agent

        Args:

            createTimePlanDto: (CreateTimePlanDto):  Options for the plan creation
            createAgentDto: (CreateAgentDto):  Options for the agent creation.
        """
        plan = self.create_credits_plan(createCreditsPlanDto)
        createAgentDto.plan_did = plan.did
        agent = self.create_agent(createAgentDto)
        return CreateAgentAndPlanResultDto.model_validate(
            {"planDID": plan.did, "agentDID": agent.did}
        )

    def order_plan(
        self, plan_did: str, agreementId: Optional[str] = None
    ) -> OrderPlanResultDto:
        """
        Orders a Payment Plan. The user needs to have enough balance in the token selected by the owner of the Payment Plan.

        The payment is done using Crypto. Payments using Fiat can be done via the Nevermined App.

        Args:
            plan_did (str): The DID of the plan.
            agreementId (str, optional): The agreement ID.

        Returns:
            OrderPlanResultDto: The result of the order operation, containing the agreement ID and success status.

        Raises:
            HTTPError: If the API call fails.

        Example:
            response = your_instance.order_plan(plan_did="did:nv:a0079b517e580d430916924f1940b764e17c31e368c509483426f8c2ac2e7116")
            print(response)
        """
        body = {
            "subscriptionDid": plan_did,
            **{
                snake_to_camel(k): v
                for k, v in locals().items()
                if v is not None and k != "self"
            },
        }
        url = f"{self.environment.value['backend']}/api/v1/payments/subscription/order"
        response = self.post(url, data=body)
        response.raise_for_status()
        return OrderPlanResultDto.model_validate(response.json())

    def get_asset_ddo(self, did: str):
        """
        Get the Metadata (aka Decentralized Document or DDO) for a given asset identifier (DID).

        https://docs.nevermined.io/docs/architecture/specs/Spec-DID
        https://docs.nevermined.io/docs/architecture/specs/Spec-METADATA

        Args:
            did (str): The unique identifier (aka DID) of the asset (payment plan, agent, file, etc).

        Returns:
            Response: The response from the API call.
        """
        response = self.get(
            f"{self.environment.value['backend']}/api/v1/payments/asset/ddo/{did}"
        )
        return response

    def get_plan_balance(
        self, plan_did: str, account_address: Optional[str] = None
    ) -> BalanceResultDto:
        """
        Get the balance of an account for a Payment Plan.

        Args:
            plan_did (str): The DID of the plan.
            account_address (Optional[str]): The account address. Defaults to `self.account_address` if not provided.

        Returns:
            BalanceResultDto: The response from the API call formatted as a BalanceResultDto.

        Raises:
            HTTPError: If the API call fails.

        Example:
            response = your_instance.get_plan_balance(plan_did="did:example:123456", account_address="0xABC123")
            response.raise_for_status()
            balance = BalanceResultDto.model_validate(response.json())
            print(balance)

        Expected Response:
            {
                "planType": "credits",
                "isOwner": True,
                "isSubscriptor": True,
                "balance": 10000000
            }
        """
        # Use self.account_address if account_address is not provided
        account_address = account_address or self.account_address

        body = {
            "subscriptionDid": plan_did,
            "accountAddress": account_address,
        }

        url = (
            f"{self.environment.value['backend']}/api/v1/payments/subscription/balance"
        )
        response = self.post(url, body)
        response.raise_for_status()

        balance = {
            "planType": response.json()["subscriptionType"],
            "isOwner": response.json()["isOwner"],
            "isSubscriptor": response.json()["isSubscriptor"],
            "balance": response.json()["balance"],
        }
        return BalanceResultDto.model_validate(balance)

    def get_service_access_config(self, service_did: str) -> ServiceTokenResultDto:
        return self.get_service_token(service_did)

    def get_service_token(self, service_did: str) -> ServiceTokenResultDto:
        """
        Get the required configuration for accessing a remote service agent.
        This configuration includes:
            - The JWT access token
            - The Proxy url that can be used to query the agent/service.

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
        return ServiceTokenResultDto.model_validate(response.json()["token"])

    def get_plan_associated_services(self, plan_did: str):
        """
        Get array of services/agent DIDs associated with a payment plan.

        Args:
            plan_did (str): The DID of the plan.

        Returns:
            Response: List of DIDs of the associated services.
        """
        url = f"{self.environment.value['backend']}/api/v1/payments/subscription/services/{plan_did}"
        response = self.get(url)
        return response

    def get_plan_associated_files(self, plan_did: str):
        """
        Get array of files DIDs associated with a payment plan.

        Args:
            plan_did (str): The DID of the plan.

        Returns:
            Response: List of DIDs of the associated files.
        """
        url = f"{self.environment.value['backend']}/api/v1/payments/subscription/files/{plan_did}"
        response = self.get(url)
        return response

    def get_plan_details_url(self, plan_did: str):
        """
        Gets the plan details.

        Args:
            plan_did (str): The DID of the plan.

        Returns:
            Response: The url of the plan details.
        """
        url = f"{self.environment.value['frontend']}/en/subscription/{plan_did}"
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

    def get_checkout_plan(self, plan_did: str):
        """
        Gets the checkout plan.

        Args:
            plan_did (str): The DID of the plan.

        Returns:
            Response: The url of the checkout plan.
        """
        url = (
            f"{self.environment.value['frontend']}/en/subscription/checkout/{plan_did}"
        )
        return url

    def download_file(
        self, file_did: str, destination: str, agreement_id: Optional[str] = None
    ) -> DownloadFileResultDto:
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
            "agreementId": agreement_id if agreement_id else "0x",
        }
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.nvm_api_key}",
        }
        url = f"{self.environment.value['backend']}/api/v1/payments/file/download"

        try:
            with requests.post(url, headers=headers, json=body, stream=True) as r:
                r.raise_for_status()
                content_disposition = r.headers.get("Content-Disposition")
                if content_disposition:
                    filename = content_disposition.split("filename=")[-1].strip('"')
                else:
                    filename = "downloaded_file"

                if os.path.isdir(destination):
                    destination = os.path.join(destination, filename)

                with open(destination, "wb") as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)

            return DownloadFileResultDto.model_validate({"success": True})
        except requests.exceptions.HTTPError as e:
            return DownloadFileResultDto.model_validate({"success": False})

    def mint_credits(self, plan_did: str, amount: str, receiver: str) -> MintResultDto:
        """
        Mints the credits associated with a plan and sends them to the receiver.

        Args:
            plan_did (str): The DID of the plan.
            amount (str): The amount of credits to mint.
            receiver (str): The receiver address of the credits.

        Returns:
            MintResultDto: The result of the minting operation.

        Raises:
            HTTPError: If the API call fails.

        Example:
            response = your_instance.mint_credits(plan_did="did:nv:e405a91e3152be1430c5d0607ebdf9236c19f34bfba0320798d81ba5f5e3e3a5", amount="12", receiver="0x4fe3e7d42fA83be4E8cF03451Ac3F25980a73fF6")
            print(response)
        """
        body = {"did": plan_did, "nftAmount": amount, "receiver": receiver}
        url = f"{self.environment.value['backend']}/api/v1/payments/credits/mint"
        response = self.post(url, body)
        response.raise_for_status()
        return MintResultDto(
            userOpHash=response.json()["userOpHash"],
            success=response.json()["success"],
            amount=amount,
        )

    def burn_credits(self, plan_did: str, amount: str) -> BurnResultDto:
        """
        Burn credits for a given Payment Plan DID.

        This method is only can be called by the owner of the Payment Plan.

        Args:
            plan_did (str): The DID of the plan.
            amount (str): The amount of credits to burn.

        Returns:
            BurnResultDto: The result of the burning operation.

        Raises:
            HTTPError: If the API call fails.

        Example:
            response = your_instance.burn_credits(plan_did="did:nv:e405a91e3152be1430c5d0607ebdf9236c19f34bfba0320798d81ba5f5e3e3a5", amount="12")
            print(response)
        """
        body = {"did": plan_did, "nftAmount": amount}
        url = f"{self.environment.value['backend']}/api/v1/payments/credits/burn"
        response = self.post(url, body)
        response.raise_for_status()
        return BurnResultDto(
            userOpHash=response.json()["userOpHash"],
            success=response.json()["success"],
            amount=amount,
        )

    def search_plans(
        self,
        text: Optional[str] = None,
        page: Optional[int] = 1,
        offset: Optional[int] = 10,
    ):
        """
        Search for plans. It will search for plans matching the text provided in their metadata.

        Args:
            text (str): The text to search for.
            page (int): The page number.
            offset (int): The offset.

        Returns:
            Response: The response from the API call.

        Example:
            response = your_instance.search_plans(text="Basic")
            print(response)
        """
        body = {"text": text, "page": page, "offset": offset}
        url = f"{self.environment.value['backend']}/api/v1/payments/search/plan"
        response = self.post(url, body)
        return response

    def search_agents(
        self,
        text: Optional[str] = None,
        page: Optional[int] = 1,
        offset: Optional[int] = 10,
    ):
        """
        Search for agents. It will search for agents matching the text provided in their metadata.

        Args:
            text (str): The text to search for.
            page (int): The page number.
            offset (int): The offset.

        Returns:
            Response: The response from the API call.

        Example:
            response = your_instance.search_agents(text="My Agent")
            print(response)
        """
        body = {"text": text, "page": page, "offset": offset}
        url = f"{self.environment.value['backend']}/api/v1/payments/search/agent"
        response = self.post(url, body)
        return response
