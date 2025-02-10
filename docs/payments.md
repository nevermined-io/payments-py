<!-- markdownlint-disable -->

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/payments.py#L0"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

# <kbd>module</kbd> `payments`






---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/payments.py#L13"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

## <kbd>class</kbd> `Payments`
A class representing a payment system. 



**Attributes:**
 
 - <b>`nvm_api_key`</b> (str):  The nvm api key for authentication. 
 - <b>`environment`</b> (Environment):  The environment for the payment system. 
 - <b>`app_id`</b> (str, optional):  The application ID. 
 - <b>`version`</b> (str, optional):  The version of the payment system. 
 - <b>`ai_protocol`</b> (bool):  Indicates if the AI protocol is enabled. 
 - <b>`headers`</b> (dict, optional):  The headers for the payment system. Methods: 
 - <b>`create_credits_plan`</b>:  Creates a new credits plan. 
 - <b>`create_time_plan`</b>:  Creates a new time plan. 
 - <b>`create_service`</b>:  Creates a new service. 
 - <b>`create_file`</b>:  Creates a new file. 
 - <b>`order_plan`</b>:  Orders the plan. 
 - <b>`get_asset_ddo`</b>:  Gets the asset DDO. 
 - <b>`get_plan_balance`</b>:  Gets the plan balance. 
 - <b>`get_service_token`</b>:  Gets the service token. 
 - <b>`get_plan_associated_services`</b>:  Gets the plan associated services. 
 - <b>`get_plan_associated_files`</b>:  Gets the plan associated files. 
 - <b>`get_plan_details`</b>:  Gets the plan details. 
 - <b>`get_service_details`</b>:  Gets the service details. 
 - <b>`get_file_details`</b>:  Gets the file details. 
 - <b>`get_checkout_plan`</b>:  Gets the checkout plan. 
 - <b>`download_file`</b>:  Downloads the file. 
 - <b>`mint_credits`</b>:  Mints the credits associated to a plan and send to the receiver. 
 - <b>`burn_credits`</b>:  Burns credits associated to a plan that you own.      
 - <b>`ai_protocol`</b>:  The AI Query API. 

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/payments.py#L45"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `__init__`

```python
__init__(
    nvm_api_key: str,
    environment: Environment,
    app_id: Optional[str] = None,
    version: Optional[str] = None,
    ai_protocol: bool = False,
    headers: Optional[dict] = None
)
```








---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/payments.py#L726"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `burn_credits`

```python
burn_credits(plan_did: str, amount: str) → BurnResultDto
```

Burn credits for a given Payment Plan DID. 

This method is only can be called by the owner of the Payment Plan. 



**Args:**
 
 - <b>`plan_did`</b> (str):  The DID of the plan. 
 - <b>`amount`</b> (str):  The amount of credits to burn. 



**Returns:**
 
 - <b>`BurnResultDto`</b>:  The result of the burning operation. 



**Raises:**
 
 - <b>`HTTPError`</b>:  If the API call fails. 



**Example:**
 response = your_instance.burn_credits(plan_did="did:nv:e405a91e3152be1430c5d0607ebdf9236c19f34bfba0320798d81ba5f5e3e3a5", amount="12") print(response) 

---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/payments.py#L369"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `create_agent`

```python
create_agent(createAgentDto: CreateAgentDto) → CreateAssetResultDto
```

It creates a new AI Agent on Nevermined. The agent must be associated to a Payment Plan. Users that are subscribers of a payment plan can access the agent. Depending on the Payment Plan and the configuration of the agent, the usage of the agent will consume credits. When the plan expires (because the time is over or the credits are consumed), the user needs to renew the plan to continue using the agent. 

This method is oriented to AI Builders 

https://docs.nevermined.app/docs/tutorials/builders/register-agent 



**Args:**
 


 - <b>`createAgentDto`</b>:  (CreateAgentDto):  Options for the agent creation. 

---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/payments.py#L418"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `create_agent_and_plan`

```python
create_agent_and_plan(
    createCreditsPlanDto: CreateCreditsPlanDto,
    createAgentDto: CreateAgentDto
) → CreateAgentAndPlanResultDto
```

It creates a new AI Agent and a Payment Plan on Nevermined. 

The agent must be associated to the Payment Plan. Users that are subscribers of a payment plan can access the agent. 

Depending on the Payment Plan and the configuration of the agent, the usage of the agent will consume credits. 

When the plan expires (because the time is over or the credits are consumed), the user needs to renew the plan to continue using the agent. 

This method is oriented to AI Builders 

https://docs.nevermined.app/docs/tutorials/builders/register-agent 



**Args:**
 


 - <b>`createTimePlanDto`</b>:  (CreateTimePlanDto):  Options for the plan creation 
 - <b>`createAgentDto`</b>:  (CreateAgentDto):  Options for the agent creation.       

---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/payments.py#L58"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `create_credits_plan`

```python
create_credits_plan(
    createCreditsPlanDto: CreateCreditsPlanDto
) → CreateAssetResultDto
```

It allows to an AI Builder to create a Payment Plan on Nevermined based on Credits. A Nevermined Credits Plan limits the access by the access/usage of the Plan. With them, AI Builders control the number of requests that can be made to an agent or service. Every time a user accesses any resource associated to the Payment Plan, the usage consumes from a capped amount of credits. When the user consumes all the credits, the plan automatically expires and the user needs to top up to continue using the service. 

This method is oriented to AI Builders. 

https://docs.nevermined.app/docs/tutorials/builders/create-plan 



**Args:**
 
 - <b>`createCreditsPlanDto`</b> (CreateCreditsPlanDto):  Options for the plan creation 



**Returns:**
 
 - <b>`CreateAssetResultDto`</b>:  The result of the creation operation. 



**Raises:**
 
 - <b>`HTTPError`</b>:  If the API call fails. 



**Example:**
 response = your_instance.create_credits_plan(CreateCreditsPlanDto(name="Basic Plan", description="100 credits plan", price=1, token_address="0x1234", amount_of_credits=100, tags=["basic"])) print(response) 

---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/payments.py#L294"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `create_file`

```python
create_file(createFileDto: CreateFileDto) → CreateAssetResultDto
```

It creates a new asset with file associated to it. The file asset must be associated to a Payment Plan. Users that are subscribers of a payment plan can download the files attached to it. Depending on the Payment Plan and the configuration of the file asset, the download will consume credits. When the plan expires (because the time is over or the credits are consumed), the user needs to renew the plan to continue downloading the files. 

This method is oriented to AI Builders 

https://docs.nevermined.app/docs/tutorials/builders/register-file-asset 



**Args:**
 
 - <b>`createFileDto`</b>:  (CreateFileDto):  Options for the file creation. 



**Returns:**
 
 - <b>`CreateAssetResultDto`</b>:  The result of the creation operation. 



**Raises:**
 
 - <b>`HTTPError`</b>:  If the API call fails. 



**Example:**
 response = your_instance.create_file(plan_did="did:nv:xyz789", asset_type="dataset", name="Sample Dataset", description="A sample dataset", files=[{"name": "file1.csv", "url": "https://example.com/file1.csv"}]) print(response) 

---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/payments.py#L196"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `create_service`

```python
create_service(createServiceDto: CreateServiceDto) → CreateAssetResultDto
```

It creates a new AI Agent or Service on Nevermined. The agent/service must be associated to a Payment Plan. Users that are subscribers of a payment plan can access the agent/service. Depending on the Payment Plan and the configuration of the agent/service, the usage of the agent/service will consume credits. When the plan expires (because the time is over or the credits are consumed), the user needs to renew the plan to continue using the agent/service. 

This method is oriented to AI Builders 

https://docs.nevermined.app/docs/tutorials/builders/register-agent 



**Args:**
 
 - <b>`createServiceDto`</b>:  (CreateServiceDto):  Options for the service creation 



**Returns:**
 
 - <b>`CreateAssetResultDto`</b>:  The result of the creation operation. 



**Raises:**
 
 - <b>`HTTPError`</b>:  If the API call fails. 



**Example:**
 response = your_instance.create_service(plan_did="did:nv:abc123", service_type="service", name="My Service", description="A sample service", service_charge_type="fixed", auth_type="none") print(response) 

---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/payments.py#L127"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `create_time_plan`

```python
create_time_plan(createTimePlanDto: CreateTimePlanDto) → CreateAssetResultDto
```

It allows to an AI Builder to create a Payment Plan on Nevermined based on Time. A Nevermined Time Plan limits the access by the a specific amount of time. With them, AI Builders can specify the duration of the Payment Plan (1 month, 1 year, etc.). When the time period is over, the plan automatically expires and the user needs to renew it. 

This method is oriented to AI Builders 

https://docs.nevermined.app/docs/tutorials/builders/create-plan 



**Args:**
 
 - <b>`createTimePlanDto`</b>:  (CreateTimePlanDto):  Options for the plan creation 



**Returns:**
 
 - <b>`CreateAssetResultDto`</b>:  The result of the creation operation. 



**Raises:**
 
 - <b>`HTTPError`</b>:  If the API call fails. 



**Example:**
 response = your_instance.create_time_plan(CreateTimePlanDto(name="Yearly Plan", description="Annual plan", price=1200, token_address="0x5678", duration=365, tags=["yearly", "premium"])) print(response) 

---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/payments.py#L643"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `download_file`

```python
download_file(
    file_did: str,
    destination: str,
    agreement_id: Optional[str] = None
) → DownloadFileResultDto
```

Downloads the file. 



**Args:**
 
 - <b>`file_did`</b> (str):  The DID of the file. 
 - <b>`agreement_id`</b> (str, optional):  The agreement ID. 
 - <b>`destination str`</b>:  The destination of the file. 



**Returns:**
 
 - <b>`Response`</b>:  The url of the file. 

**Returns:**
 
 - <b>`DownloadFileResultDto`</b>:  The result of the download operation. 



**Raises:**
 
 - <b>`HTTPError`</b>:  If the API call fails. 



**Example:**
 response = your_instance.download_file(file_did="did:nv:7e38d39405445ab3e5435d8c1c6653a00ddc425ba629789f58fbefccaa5e5a5d", destination="/tmp") print(response) 

---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/payments.py#L471"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `get_asset_ddo`

```python
get_asset_ddo(did: str)
```

Get the Metadata (aka Decentralized Document or DDO) for a given asset identifier (DID). 

https://docs.nevermined.io/docs/architecture/specs/Spec-DID https://docs.nevermined.io/docs/architecture/specs/Spec-METADATA 



**Args:**
 
 - <b>`did`</b> (str):  The unique identifier (aka DID) of the asset (payment plan, agent, file, etc). 



**Returns:**
 
 - <b>`Response`</b>:  The response from the API call. 

---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/payments.py#L630"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `get_checkout_plan`

```python
get_checkout_plan(plan_did: str)
```

Gets the checkout plan. 



**Args:**
 
 - <b>`plan_did`</b> (str):  The DID of the plan. 



**Returns:**
 
 - <b>`Response`</b>:  The url of the checkout plan. 

---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/payments.py#L617"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `get_file_details_url`

```python
get_file_details_url(file_did: str)
```

Gets the file details. 



**Args:**
 
 - <b>`file_did`</b> (str):  The DID of the file. 



**Returns:**
 
 - <b>`Response`</b>:  The url of the file details. 

---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/payments.py#L577"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `get_plan_associated_files`

```python
get_plan_associated_files(plan_did: str)
```

Get array of files DIDs associated with a payment plan. 



**Args:**
 
 - <b>`plan_did`</b> (str):  The DID of the plan. 



**Returns:**
 
 - <b>`Response`</b>:  List of DIDs of the associated files. 

---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/payments.py#L563"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `get_plan_associated_services`

```python
get_plan_associated_services(plan_did: str)
```

Get array of services/agent DIDs associated with a payment plan. 



**Args:**
 
 - <b>`plan_did`</b> (str):  The DID of the plan. 



**Returns:**
 
 - <b>`Response`</b>:  List of DIDs of the associated services. 

---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/payments.py#L487"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `get_plan_balance`

```python
get_plan_balance(
    plan_did: str,
    account_address: Optional[str] = None
) → BalanceResultDto
```

Get the balance of an account for a Payment Plan. 



**Args:**
 
 - <b>`plan_did`</b> (str):  The DID of the plan. 
 - <b>`account_address`</b> (Optional[str]):  The account address. Defaults to `self.account_address` if not provided. 



**Returns:**
 
 - <b>`BalanceResultDto`</b>:  The response from the API call formatted as a BalanceResultDto. 



**Raises:**
 
 - <b>`HTTPError`</b>:  If the API call fails. 



**Example:**
 response = your_instance.get_plan_balance(plan_did="did:example:123456", account_address="0xABC123") response.raise_for_status() balance = BalanceResultDto.model_validate(response.json()) print(balance) 

Expected Response: {  "planType": "credits",  "isOwner": True,  "isSubscriptor": True,  "balance": 10000000 } 

---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/payments.py#L591"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `get_plan_details_url`

```python
get_plan_details_url(plan_did: str)
```

Gets the plan details. 



**Args:**
 
 - <b>`plan_did`</b> (str):  The DID of the plan. 



**Returns:**
 
 - <b>`Response`</b>:  The url of the plan details. 

---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/payments.py#L535"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `get_service_access_config`

```python
get_service_access_config(service_did: str) → ServiceTokenResultDto
```





---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/payments.py#L604"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `get_service_details_url`

```python
get_service_details_url(service_did: str)
```

Gets the service details. 



**Args:**
 
 - <b>`service_did`</b> (str):  The DID of the service. 



**Returns:**
 
 - <b>`Response`</b>:  The url of the service details. 

---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/payments.py#L538"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `get_service_token`

```python
get_service_token(service_did: str) → ServiceTokenResultDto
```

Get the required configuration for accessing a remote service agent. This configuration includes: 
    - The JWT access token 
    - The Proxy url that can be used to query the agent/service. 



**Args:**
 
 - <b>`service_did`</b> (str):  The DID of the service. 



**Returns:**
 
 - <b>`ServiceTokenResultDto`</b>:  The result of the creation operation. 



**Raises:**
 
 - <b>`HTTPError`</b>:  If the API call fails. 



**Example:**
 response = your_instance.get_service_token(service_did="did:nv:xyz789") print(response) 

---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/payments.py#L697"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `mint_credits`

```python
mint_credits(plan_did: str, amount: str, receiver: str) → MintResultDto
```

Mints the credits associated with a plan and sends them to the receiver. 



**Args:**
 
 - <b>`plan_did`</b> (str):  The DID of the plan. 
 - <b>`amount`</b> (str):  The amount of credits to mint. 
 - <b>`receiver`</b> (str):  The receiver address of the credits. 



**Returns:**
 
 - <b>`MintResultDto`</b>:  The result of the minting operation. 



**Raises:**
 
 - <b>`HTTPError`</b>:  If the API call fails. 



**Example:**
 response = your_instance.mint_credits(plan_did="did:nv:e405a91e3152be1430c5d0607ebdf9236c19f34bfba0320798d81ba5f5e3e3a5", amount="12", receiver="0x4fe3e7d42fA83be4E8cF03451Ac3F25980a73fF6") print(response) 

---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/payments.py#L442"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `order_plan`

```python
order_plan(
    plan_did: str,
    agreementId: Optional[str] = None
) → OrderPlanResultDto
```

Orders a Payment Plan. The user needs to have enough balance in the token selected by the owner of the Payment Plan. 

The payment is done using Crypto. Payments using Fiat can be done via the Nevermined App. 



**Args:**
 
 - <b>`plan_did`</b> (str):  The DID of the plan. 
 - <b>`agreementId`</b> (str, optional):  The agreement ID. 



**Returns:**
 
 - <b>`OrderPlanResultDto`</b>:  The result of the order operation, containing the agreement ID and success status. 



**Raises:**
 
 - <b>`HTTPError`</b>:  If the API call fails. 



**Example:**
 response = your_instance.order_plan(plan_did="did:nv:a0079b517e580d430916924f1940b764e17c31e368c509483426f8c2ac2e7116") print(response) 

---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/payments.py#L780"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `search_agents`

```python
search_agents(
    text: Optional[str] = None,
    page: Optional[int] = 1,
    offset: Optional[int] = 10
)
```

Search for agents. It will search for agents matching the text provided in their metadata. 



**Args:**
 
 - <b>`text`</b> (str):  The text to search for. 
 - <b>`page`</b> (int):  The page number. 
 - <b>`offset`</b> (int):  The offset. 



**Returns:**
 
 - <b>`Response`</b>:  The response from the API call. 



**Example:**
 response = your_instance.search_agents(text="My Agent") print(response) 

---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/payments.py#L755"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `search_plans`

```python
search_plans(
    text: Optional[str] = None,
    page: Optional[int] = 1,
    offset: Optional[int] = 10
)
```

Search for plans. It will search for plans matching the text provided in their metadata. 



**Args:**
 
 - <b>`text`</b> (str):  The text to search for. 
 - <b>`page`</b> (int):  The page number. 
 - <b>`offset`</b> (int):  The offset. 



**Returns:**
 
 - <b>`Response`</b>:  The response from the API call. 



**Example:**
 response = your_instance.search_plans(text="Basic") print(response) 




---

_This file was automatically generated via [lazydocs](https://github.com/ml-tooling/lazydocs)._
