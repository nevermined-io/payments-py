<!-- markdownlint-disable -->

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/payments.py#L0"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

# <kbd>module</kbd> `payments`

---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/payments.py#L14"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

## <kbd>class</kbd> `Payments`

A class representing a payment system.

**Attributes:**

- <b>`nvm_api_key`</b> (str): The nvm api key for authentication.
- <b>`environment`</b> (Environment): The environment for the payment system.
- <b>`app_id`</b> (str, optional): The application ID.
- <b>`version`</b> (str, optional): The version of the payment system.
- <b>`headers`</b> (dict, optional): The headers for the payment system. Methods:
- <b>`register_credits_plan`</b>: Registers a new credits plan.
- <b>`register_time_plan`</b>: Registers a new time plan.
- <b>`register_credits_trial_plan`</b>: Registers a new credits trial plan.
- <b>`register_time_trial_plan`</b>: Registers a new time trial plan.
- <b>`register_agent`</b>: Registers a new agent
- <b>`register_agent_and_plan`</b>: Registers a new agent associated to a plan in one step
- <b>`order_plan`</b>: Orders the plan.
- <b>`get_asset_ddo`</b>: Gets the asset DDO.
- <b>`get_plan_balance`</b>: Gets the plan balance.
- <b>`get_service_token`</b>: Gets the service token.
- <b>`get_plan_associated_services`</b>: Gets the plan associated services.
- <b>`get_plan_associated_files`</b>: Gets the plan associated files.
- <b>`get_plan_details_url`</b>: Gets the plan details.
- <b>`get_service_details_url`</b>: Gets the service details.
- <b>`get_file_details_url`</b>: Gets the file details.
- <b>`get_checkout_plan`</b>: Gets the checkout plan.
- <b>`download_file`</b>: Downloads the file.
- <b>`mint_credits`</b>: Mints the credits associated to a plan and send to the receiver.
- <b>`burn_credits`</b>: Burns credits associated to a plan that you own.
- <b>`search_plans`</b>: Query for plans base on an input query options.
- <b>`search_agents`</b>: Query for agents base on an input query options.
- <b>`query`</b>: The AI Query API.

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/payments.py#L50"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `__init__`

```python
__init__(
    nvm_api_key: str,
    environment: Environment,
    app_id: Optional[str] = None,
    version: Optional[str] = None,
    headers: Optional[dict] = None
)
```

---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/payments.py#L736"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `burn_credits`

```python
burn_credits(plan_did: str, amount: str) → BurnResultDto
```

Burn credits for a given Payment Plan DID.

This method is only can be called by the owner of the Payment Plan.

**Args:**

- <b>`plan_did`</b> (str): The DID of the plan.
- <b>`amount`</b> (str): The amount of credits to burn.

**Returns:**

- <b>`BurnResultDto`</b>: The result of the burning operation.

**Raises:**

- <b>`HTTPError`</b>: If the API call fails.

**Example:**
response = your_instance.burn_credits(plan_did="did:nv:e405a91e3152be1430c5d0607ebdf9236c19f34bfba0320798d81ba5f5e3e3a5", amount="12") print(response)

---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/payments.py#L379"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `register_agent`

```python
register_agent(
    agent_metadata: AgentMetadata,
    agent_api: AgentAPIAttributes,
    payment_plans: List[str]
) → Dict[str, str]
```

Registers a new AI Agent on Nevermined. The agent must be associated to one or multiple Payment Plans. Users that are subscribers of a payment plan can access the agent. Depending on the Payment Plan and the configuration of the agent, the usage of the agent will consume credits. When the plan expires (because the time is over or the credits are consumed), the user needs to renew the plan to continue using the agent.

This method is oriented to AI Builders

https://docs.nevermined.app/docs/tutorials/builders/register-agent

**Args:**

- <b>`agent_metadata`</b> (AgentMetadata): Metadata for the agent.
- <b>`agent_api`</b> (AgentAPIAttributes): API attributes for the agent.
- <b>`payment_plans`</b> (List[str]): List of payment plan IDs that give access to the agent.

**Returns:**

- <b>`Dict[str, str]`</b>: Dictionary containing the `agentId` of the newly created agent.

**Example:**

```python
from payments_py.common.types import AgentMetadata, AgentAPIAttributes

agent_metadata = AgentMetadata(
    name="My AI Agent",
    description="A helpful AI agent",
    tags=["ai", "assistant"]
)
agent_api = AgentAPIAttributes(
    endpoints=[{"POST": "https://example.com/api/v1/agents/:agentId/tasks"}]
)
payment_plans = [plan_id_1, plan_id_2]

result = payments.agents.register_agent(agent_metadata, agent_api, payment_plans)
print(f"Agent ID: {result['agentId']}")
```

---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/payments.py#L428"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `register_agent_and_plan`

```python
register_agent_and_plan(
    agent_metadata: AgentMetadata,
    agent_api: AgentAPIAttributes,
    plan_metadata: PlanMetadata,
    price_config: PlanPriceConfig,
    credits_config: PlanCreditsConfig,
    access_limit: Optional[Literal["credits", "time"]] = None
) → Dict[str, str]
```

Registers a new AI Agent and a Payment Plan on Nevermined in one step.

The agent is automatically associated to the Payment Plan. Users that are subscribers of a payment plan can access the agent.

Depending on the Payment Plan and the configuration of the agent, the usage of the agent will consume credits.

When the plan expires (because the time is over or the credits are consumed), the user needs to renew the plan to continue using the agent.

This method is oriented to AI Builders

https://docs.nevermined.app/docs/tutorials/builders/register-agent

**Args:**

- <b>`agent_metadata`</b> (AgentMetadata): Metadata for the agent.
- <b>`agent_api`</b> (AgentAPIAttributes): API attributes for the agent.
- <b>`plan_metadata`</b> (PlanMetadata): Metadata for the payment plan.
- <b>`price_config`</b> (PlanPriceConfig): Price configuration for the plan. Use helper functions from `payments_py.plans` to create this.
- <b>`credits_config`</b> (PlanCreditsConfig): Credits configuration for the plan. Use helper functions from `payments_py.plans` to create this.
- <b>`access_limit`</b> (Optional[Literal["credits", "time"]]): Type of access limit. Can be `"credits"` or `"time"`. If not specified, it is automatically inferred based on `credits_config.duration_secs`.

**Returns:**

- <b>`Dict[str, str]`</b>: Dictionary containing `agentId`, `planId`, and `txHash`.

**Example:**

```python
from payments_py.common.types import AgentMetadata, AgentAPIAttributes, PlanMetadata
from payments_py.plans import get_erc20_price_config, get_fixed_credits_config

agent_metadata = AgentMetadata(name="My AI Agent", tags=["ai"])
agent_api = AgentAPIAttributes(
    endpoints=[{"POST": "https://example.com/api/v1/agents/:agentId/tasks"}]
)
plan_metadata = PlanMetadata(name="Basic Plan")
price_config = get_erc20_price_config(20, ERC20_ADDRESS, builder_address)
credits_config = get_fixed_credits_config(100)

result = payments.agents.register_agent_and_plan(
    agent_metadata, agent_api, plan_metadata, price_config, credits_config
)
print(f"Agent ID: {result['agentId']}, Plan ID: {result['planId']}")
```

**Note:** The `access_limit` parameter is optional. If not specified, it is automatically inferred based on `credits_config.duration_secs`:

- `"credits"` if `duration_secs == 0` (non-expirable plans)
- `"time"` if `duration_secs > 0` (expirable plans)

You can explicitly set it if needed:

```python
# Explicitly set access limit to 'time'
result = payments.agents.register_agent_and_plan(
    agent_metadata, agent_api, plan_metadata, price_config, credits_config,
    access_limit="time"
)
```

---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/payments.py#L68"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `register_credits_plan`

```python
register_credits_plan(
    plan_metadata: PlanMetadata,
    price_config: PlanPriceConfig,
    credits_config: PlanCreditsConfig
) → Dict[str, str]
```

Allows an AI Builder to register a Payment Plan on Nevermined based on Credits. A Nevermined Credits Plan limits the access by the access/usage of the Plan. With them, AI Builders control the number of requests that can be made to an agent or service. Every time a user accesses any resource associated to the Payment Plan, the usage consumes from a capped amount of credits. When the user consumes all the credits, the plan automatically expires and the user needs to top up to continue using the service.

This method is oriented to AI Builders.

https://docs.nevermined.app/docs/tutorials/builders/create-plan

**Args:**

- <b>`plan_metadata`</b> (PlanMetadata): Metadata for the payment plan.
- <b>`price_config`</b> (PlanPriceConfig): Price configuration for the plan. Use helper functions from `payments_py.plans` to create this (e.g., `get_erc20_price_config`, `get_fiat_price_config`).
- <b>`credits_config`</b> (PlanCreditsConfig): Credits configuration for the plan. Use helper functions from `payments_py.plans` to create this (e.g., `get_fixed_credits_config`, `get_dynamic_credits_config`).

**Returns:**

- <b>`Dict[str, str]`</b>: Dictionary containing the `planId` of the newly created plan.

**Raises:**

- <b>`PaymentsError`</b>: If the API call fails or if the credits configuration is invalid.

**Example:**

```python
from payments_py.common.types import PlanMetadata
from payments_py.plans import get_erc20_price_config, get_fixed_credits_config

plan_metadata = PlanMetadata(name="Basic Plan", description="100 credits plan")
price_config = get_erc20_price_config(20, ERC20_ADDRESS, builder_address)
credits_config = get_fixed_credits_config(100)

response = payments.plans.register_credits_plan(plan_metadata, price_config, credits_config)
print(f"Plan ID: {response['planId']}")
```

---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/payments.py#L304"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `create_file`

```python
create_file(createFileDto: CreateFileDto) → CreateAssetResultDto
```

It creates a new asset with file associated to it. The file asset must be associated to a Payment Plan. Users that are subscribers of a payment plan can download the files attached to it. Depending on the Payment Plan and the configuration of the file asset, the download will consume credits. When the plan expires (because the time is over or the credits are consumed), the user needs to renew the plan to continue downloading the files.

This method is oriented to AI Builders

https://docs.nevermined.app/docs/tutorials/builders/register-file-asset

**Args:**

- <b>`createFileDto`</b>: (CreateFileDto): Options for the file creation.

**Returns:**

- <b>`CreateAssetResultDto`</b>: The result of the creation operation.

**Raises:**

- <b>`HTTPError`</b>: If the API call fails.

**Example:**
response = your_instance.create_file(plan_did="did:nv:xyz789", asset_type="dataset", name="Sample Dataset", description="A sample dataset", files=[{"name": "file1.csv", "url": "https://example.com/file1.csv"}]) print(response)

---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/payments.py#L206"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `create_service`

```python
create_service(createServiceDto: CreateServiceDto) → CreateAssetResultDto
```

It creates a new AI Agent or Service on Nevermined. The agent/service must be associated to a Payment Plan. Users that are subscribers of a payment plan can access the agent/service. Depending on the Payment Plan and the configuration of the agent/service, the usage of the agent/service will consume credits. When the plan expires (because the time is over or the credits are consumed), the user needs to renew the plan to continue using the agent/service.

This method is oriented to AI Builders

https://docs.nevermined.app/docs/tutorials/builders/register-agent

**Args:**

- <b>`createServiceDto`</b>: (CreateServiceDto): Options for the service creation

**Returns:**

- <b>`CreateAssetResultDto`</b>: The result of the creation operation.

**Raises:**

- <b>`HTTPError`</b>: If the API call fails.

**Example:**
response = your_instance.create_service(plan_did="did:nv:abc123", service_type="service", name="My Service", description="A sample service", service_charge_type="fixed", auth_type="none") print(response)

---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/payments.py#L137"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `register_time_plan`

```python
register_time_plan(
    plan_metadata: PlanMetadata,
    price_config: PlanPriceConfig,
    credits_config: PlanCreditsConfig
) → Dict[str, str]
```

Allows an AI Builder to register a Payment Plan on Nevermined limited by duration. A Nevermined Time Plan limits the access by a specific amount of time. With them, AI Builders can specify the duration of the Payment Plan (1 month, 1 year, etc.). When the time period is over, the plan automatically expires and the user needs to renew it.

This method is oriented to AI Builders

https://docs.nevermined.app/docs/tutorials/builders/create-plan

**Args:**

- <b>`plan_metadata`</b> (PlanMetadata): Metadata for the payment plan.
- <b>`price_config`</b> (PlanPriceConfig): Price configuration for the plan. Use helper functions from `payments_py.plans` to create this.
- <b>`credits_config`</b> (PlanCreditsConfig): Credits configuration for the plan. Use helper functions from `payments_py.plans` to create this (e.g., `get_expirable_duration_config`).

**Returns:**

- <b>`Dict[str, str]`</b>: Dictionary containing the `planId` of the newly created plan.

**Raises:**

- <b>`PaymentsError`</b>: If the API call fails or if the credits configuration is invalid.

**Example:**

```python
from payments_py.common.types import PlanMetadata
from payments_py.plans import get_erc20_price_config, get_expirable_duration_config, ONE_DAY_DURATION

plan_metadata = PlanMetadata(name="Daily Plan", description="1 day access")
price_config = get_erc20_price_config(50, ERC20_ADDRESS, builder_address)
credits_config = get_expirable_duration_config(ONE_DAY_DURATION)

response = payments.plans.register_time_plan(plan_metadata, price_config, credits_config)
print(f"Plan ID: {response['planId']}")
```

---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/api/plans_api.py#L175"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `register_credits_trial_plan`

```python
register_credits_trial_plan(
    plan_metadata: PlanMetadata,
    price_config: PlanPriceConfig,
    credits_config: PlanCreditsConfig
) → Dict[str, str]
```

Allows an AI Builder to register a Trial Payment Plan on Nevermined based on Credits. A Nevermined Trial Plan allows subscribers of that plan to test the Agents associated to it. A Trial plan is a plan that can only be purchased once by a user.

This method is oriented to AI Builders

https://docs.nevermined.app/docs/tutorials/builders/create-plan

**Args:**

- <b>`plan_metadata`</b> (PlanMetadata): Metadata for the payment plan.
- <b>`price_config`</b> (PlanPriceConfig): Price configuration for the plan. Use helper functions from `payments_py.plans` to create this (typically `get_free_price_config` for trial plans).
- <b>`credits_config`</b> (PlanCreditsConfig): Credits configuration for the plan. Use helper functions from `payments_py.plans` to create this (e.g., `get_fixed_credits_config`).

**Returns:**

- <b>`Dict[str, str]`</b>: Dictionary containing the `planId` of the newly created trial plan.

**Raises:**

- <b>`PaymentsError`</b>: If the API call fails or if the credits configuration is invalid.

**Example:**

```python
from payments_py.common.types import PlanMetadata
from payments_py.plans import get_free_price_config, get_fixed_credits_config

plan_metadata = PlanMetadata(name="Trial Plan", description="Free trial with 10 credits")
price_config = get_free_price_config()
credits_config = get_fixed_credits_config(10)

response = payments.plans.register_credits_trial_plan(plan_metadata, price_config, credits_config)
print(f"Trial Plan ID: {response['planId']}")
```

---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/api/plans_api.py#L197"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `register_time_trial_plan`

```python
register_time_trial_plan(
    plan_metadata: PlanMetadata,
    price_config: PlanPriceConfig,
    credits_config: PlanCreditsConfig
) → Dict[str, str]
```

Allows an AI Builder to register a Trial Payment Plan on Nevermined limited by duration. A Nevermined Trial Plan allows subscribers of that plan to test the Agents associated to it. A Trial plan is a plan that can only be purchased once by a user.

This method is oriented to AI Builders

https://docs.nevermined.app/docs/tutorials/builders/create-plan

**Args:**

- <b>`plan_metadata`</b> (PlanMetadata): Metadata for the payment plan.
- <b>`price_config`</b> (PlanPriceConfig): Price configuration for the plan. Use helper functions from `payments_py.plans` to create this (typically `get_free_price_config` for trial plans).
- <b>`credits_config`</b> (PlanCreditsConfig): Credits configuration for the plan. Use helper functions from `payments_py.plans` to create this (e.g., `get_expirable_duration_config`).

**Returns:**

- <b>`Dict[str, str]`</b>: Dictionary containing the `planId` of the newly created trial plan.

**Raises:**

- <b>`PaymentsError`</b>: If the API call fails or if the credits configuration is invalid.

**Example:**

```python
from payments_py.common.types import PlanMetadata
from payments_py.plans import get_free_price_config, get_expirable_duration_config, ONE_DAY_DURATION

plan_metadata = PlanMetadata(name="Trial Plan", description="Free 1-day trial")
price_config = get_free_price_config()
credits_config = get_expirable_duration_config(ONE_DAY_DURATION)

response = payments.plans.register_time_trial_plan(plan_metadata, price_config, credits_config)
print(f"Trial Plan ID: {response['planId']}")
```

---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/payments.py#L653"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

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

- <b>`file_did`</b> (str): The DID of the file.
- <b>`agreement_id`</b> (str, optional): The agreement ID.
- <b>`destination str`</b>: The destination of the file.

**Returns:**

- <b>`Response`</b>: The url of the file.

**Returns:**

- <b>`DownloadFileResultDto`</b>: The result of the download operation.

**Raises:**

- <b>`HTTPError`</b>: If the API call fails.

**Example:**
response = your_instance.download_file(file_did="did:nv:7e38d39405445ab3e5435d8c1c6653a00ddc425ba629789f58fbefccaa5e5a5d", destination="/tmp") print(response)

---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/payments.py#L481"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `get_asset_ddo`

```python
get_asset_ddo(did: str)
```

Get the Metadata (aka Decentralized Document or DDO) for a given asset identifier (DID).

https://docs.nevermined.io/docs/architecture/specs/Spec-DID https://docs.nevermined.io/docs/architecture/specs/Spec-METADATA

**Args:**

- <b>`did`</b> (str): The unique identifier (aka DID) of the asset (payment plan, agent, file, etc).

**Returns:**

- <b>`Response`</b>: The response from the API call.

---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/payments.py#L640"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `get_checkout_plan`

```python
get_checkout_plan(plan_did: str)
```

Gets the checkout plan.

**Args:**

- <b>`plan_did`</b> (str): The DID of the plan.

**Returns:**

- <b>`Response`</b>: The url of the checkout plan.

---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/payments.py#L627"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `get_file_details_url`

```python
get_file_details_url(file_did: str)
```

Gets the file details.

**Args:**

- <b>`file_did`</b> (str): The DID of the file.

**Returns:**

- <b>`Response`</b>: The url of the file details.

---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/payments.py#L587"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `get_plan_associated_files`

```python
get_plan_associated_files(plan_did: str)
```

Get array of files DIDs associated with a payment plan.

**Args:**

- <b>`plan_did`</b> (str): The DID of the plan.

**Returns:**

- <b>`Response`</b>: List of DIDs of the associated files.

---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/payments.py#L573"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `get_plan_associated_services`

```python
get_plan_associated_services(plan_did: str)
```

Get array of services/agent DIDs associated with a payment plan.

**Args:**

- <b>`plan_did`</b> (str): The DID of the plan.

**Returns:**

- <b>`Response`</b>: List of DIDs of the associated services.

---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/payments.py#L497"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `get_plan_balance`

```python
get_plan_balance(
    plan_did: str,
    account_address: Optional[str] = None
) → BalanceResultDto
```

Get the balance of an account for a Payment Plan.

**Args:**

- <b>`plan_did`</b> (str): The DID of the plan.
- <b>`account_address`</b> (Optional[str]): The account address. Defaults to `self.account_address` if not provided.

**Returns:**

- <b>`BalanceResultDto`</b>: The response from the API call formatted as a BalanceResultDto.

**Raises:**

- <b>`HTTPError`</b>: If the API call fails.

**Example:**
response = your_instance.get_plan_balance(plan_did="did:example:123456", account_address="0xABC123") response.raise_for_status() balance = BalanceResultDto.model_validate(response.json()) print(balance)

Expected Response: { "planType": "credits", "isOwner": True, "isSubscriptor": True, "balance": 10000000 }

---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/payments.py#L601"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `get_plan_details_url`

```python
get_plan_details_url(plan_did: str)
```

Gets the plan details.

**Args:**

- <b>`plan_did`</b> (str): The DID of the plan.

**Returns:**

- <b>`Response`</b>: The url of the plan details.

---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/payments.py#L545"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `get_service_access_config`

```python
get_service_access_config(service_did: str) → ServiceTokenResultDto
```

---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/payments.py#L614"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `get_service_details_url`

```python
get_service_details_url(service_did: str)
```

Gets the service details.

**Args:**

- <b>`service_did`</b> (str): The DID of the service.

**Returns:**

- <b>`Response`</b>: The url of the service details.

---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/payments.py#L548"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `get_service_token`

```python
get_service_token(service_did: str) → ServiceTokenResultDto
```

Get the required configuration for accessing a remote service agent. This configuration includes: - The JWT access token - The Proxy url that can be used to query the agent/service.

**Args:**

- <b>`service_did`</b> (str): The DID of the service.

**Returns:**

- <b>`ServiceTokenResultDto`</b>: The result of the creation operation.

**Raises:**

- <b>`HTTPError`</b>: If the API call fails.

**Example:**
response = your_instance.get_service_token(service_did="did:nv:xyz789") print(response)

---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/payments.py#L707"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `mint_credits`

```python
mint_credits(plan_did: str, amount: str, receiver: str) → MintResultDto
```

Mints the credits associated with a plan and sends them to the receiver.

**Args:**

- <b>`plan_did`</b> (str): The DID of the plan.
- <b>`amount`</b> (str): The amount of credits to mint.
- <b>`receiver`</b> (str): The receiver address of the credits.

**Returns:**

- <b>`MintResultDto`</b>: The result of the minting operation.

**Raises:**

- <b>`HTTPError`</b>: If the API call fails.

**Example:**
response = your_instance.mint_credits(plan_did="did:nv:e405a91e3152be1430c5d0607ebdf9236c19f34bfba0320798d81ba5f5e3e3a5", amount="12", receiver="0x4fe3e7d42fA83be4E8cF03451Ac3F25980a73fF6") print(response)

---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/payments.py#L452"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

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

- <b>`plan_did`</b> (str): The DID of the plan.
- <b>`agreementId`</b> (str, optional): The agreement ID.

**Returns:**

- <b>`OrderPlanResultDto`</b>: The result of the order operation, containing the agreement ID and success status.

**Raises:**

- <b>`HTTPError`</b>: If the API call fails.

**Example:**
response = your_instance.order_plan(plan_did="did:nv:a0079b517e580d430916924f1940b764e17c31e368c509483426f8c2ac2e7116") print(response)

---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/payments.py#L790"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

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

- <b>`text`</b> (str): The text to search for.
- <b>`page`</b> (int): The page number.
- <b>`offset`</b> (int): The offset.

**Returns:**

- <b>`Response`</b>: The response from the API call.

**Example:**
response = your_instance.search_agents(text="My Agent") print(response)

---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/payments.py#L765"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

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

- <b>`text`</b> (str): The text to search for.
- <b>`page`</b> (int): The page number.
- <b>`offset`</b> (int): The offset.

**Returns:**

- <b>`Response`</b>: The response from the API call.

**Example:**
response = your_instance.search_plans(text="Basic") print(response)

---

_This file was automatically generated via [lazydocs](https://github.com/ml-tooling/lazydocs)._
