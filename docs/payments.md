<!-- markdownlint-disable -->

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/payments.py#L0"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

# <kbd>module</kbd> `payments`






---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/payments.py#L8"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

## <kbd>class</kbd> `Payments`
A class representing a payment system. 



**Attributes:**
 
 - <b>`session_key`</b> (str):  The session key for authentication. 
 - <b>`environment`</b> (Environment):  The environment for the payment system. 
 - <b>`marketplace_auth_token`</b> (str, optional):  The marketplace authentication token. 
 - <b>`app_id`</b> (str, optional):  The application ID. 
 - <b>`version`</b> (str, optional):  The version of the payment system. 

Methods: 
 - <b>`create_ubscription`</b>:  Creates a new subscription. 
 - <b>`create_service`</b>:  Creates a new service. 
 - <b>`create_file`</b>:  Creates a new file. 
 - <b>`get_asset_ddo`</b>:  Gets the asset DDO. 
 - <b>`get_subscription_balance`</b>:  Gets the subscription balance. 
 - <b>`get_service_token`</b>:  Gets the service token. 
 - <b>`get_subscription_details`</b>:  Gets the subscription details. 
 - <b>`get_service_details`</b>:  Gets the service details. 
 - <b>`get_file_details`</b>:  Gets the file details. 
 - <b>`get_checkout_subscription`</b>:  Gets the checkout subscription.      



<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/payments.py#L32"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `__init__`

```python
__init__(
    session_key: str,
    environment: Environment,
    marketplace_auth_token: Optional[str] = None,
    app_id: Optional[str] = None,
    version: Optional[str] = None
)
```








---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/payments.py#L133"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `create_file`

```python
create_file(
    subscription_did: str,
    asset_type: str,
    name: str,
    description: str,
    files: List[dict],
    price: int,
    token_address: str,
    data_schema: Optional[str] = None,
    sample_code: Optional[str] = None,
    files_format: Optional[str] = None,
    usage_example: Optional[str] = None,
    programming_language: Optional[str] = None,
    framework: Optional[str] = None,
    task: Optional[str] = None,
    training_details: Optional[str] = None,
    variations: Optional[str] = None,
    fine_tunable: Optional[bool] = None,
    amount_of_credits: Optional[int] = None,
    min_credits_to_charge: Optional[int] = None,
    max_credits_to_charge: Optional[int] = None,
    curation: Optional[dict] = None,
    duration: Optional[int] = None,
    tags: Optional[List[str]] = None
)
```

Creates a new file. 



**Args:**
 
 - <b>`subscription_did`</b> (str):  The DID of the subscription. 
 - <b>`asset_type`</b> (str):  The type of the asset. -> 'algorithm' | 'model' | 'dataset' | 'file' 
 - <b>`name`</b> (str):  The name of the file. 
 - <b>`description`</b> (str):  The description of the file. 
 - <b>`files`</b> (List[dict]):  The files of the file. 
 - <b>`price`</b> (int):  The price of the file. 
 - <b>`token_address`</b> (str):  The token address. 
 - <b>`data_schema`</b> (str, optional):  The data schema of the file. 
 - <b>`sample_code`</b> (str, optional):  The sample code of the file. 
 - <b>`files_format`</b> (str, optional):  The files format of the file. 
 - <b>`usage_example`</b> (str, optional):  The usage example of the file. 
 - <b>`programming_language`</b> (str, optional):  The programming language of the file. 
 - <b>`framework`</b> (str, optional):  The framework of the file. 
 - <b>`task`</b> (str, optional):  The task of the file. 
 - <b>`training_details`</b> (str, optional):  The training details of the file. 
 - <b>`variations`</b> (str, optional):  The variations of the file. 
 - <b>`fine_tunable`</b> (bool, optional):  The fine tunable of the file. 
 - <b>`amount_of_credits`</b> (int, optional):  The amount of credits for the file. 
 - <b>`min_credits_to_charge`</b> (int, optional):  The minimum credits to charge for the file. 
 - <b>`max_credits_to_charge`</b> (int, optional):  The maximum credits to charge for the file. 
 - <b>`curation`</b> (dict, optional):  The curation information of the file. 
 - <b>`duration`</b> (int, optional):  The duration of the file. 
 - <b>`tags`</b> (List[str], optional):  The tags associated with the file. 



**Returns:**
 
 - <b>`Response`</b>:  The response from the API call. 

---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/payments.py#L75"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `create_service`

```python
create_service(
    subscription_did: str,
    name: str,
    description: str,
    price: int,
    token_address: str,
    service_charge_type: str,
    auth_type: str,
    amount_of_credits: Optional[int] = None,
    min_credits_to_charge: Optional[int] = None,
    max_credits_to_charge: Optional[int] = None,
    username: Optional[str] = None,
    password: Optional[str] = None,
    token: Optional[str] = None,
    endpoints: Optional[List[dict]] = None,
    open_endpoints: Optional[List[str]] = None,
    open_api_url: Optional[str] = None,
    integration: Optional[str] = None,
    sample_link: Optional[str] = None,
    api_description: Optional[str] = None,
    curation: Optional[dict] = None,
    duration: Optional[int] = None,
    tags: Optional[List[str]] = None
)
```

Creates a new service. 



**Args:**
 
 - <b>`subscription_did`</b> (str):  The DID of the subscription. 
 - <b>`name`</b> (str):  The name of the service. 
 - <b>`description`</b> (str):  The description of the service. 
 - <b>`price`</b> (int):  The price of the service. 
 - <b>`token_address`</b> (str): The token address. 
 - <b>`service_charge_type`</b> (str):  The charge type of the service. ->  'fixed' | 'dynamic' 
 - <b>`auth_type`</b> (str):  The authentication type of the service. -> 'none' | 'basic' | 'oauth' 
 - <b>`amount_of_credits`</b> (int, optional):  The amount of credits for the service. 
 - <b>`min_credits_to_charge`</b> (int, optional):  The minimum credits to charge for the service. 
 - <b>`max_credits_to_charge`</b> (int, optional):  The maximum credits to charge for the service. 
 - <b>`username`</b> (str, optional):  The username for authentication. 
 - <b>`password`</b> (str, optional):  The password for authentication. 
 - <b>`token`</b> (str, optional):  The token for authentication. 
 - <b>`endpoints`</b> (List[dict], optional):  The endpoints of the service. 
 - <b>`open_endpoints`</b> (List[str], optional):  The open endpoints of the service. -> [{"post": "https://api.example.app/api/v1/example"}] 
 - <b>`open_api_url`</b> (str, optional):  The OpenAPI URL of the service. 
 - <b>`integration`</b> (str, optional):  The integration type of the service. 
 - <b>`sample_link`</b> (str, optional):  The sample link of the service. 
 - <b>`api_description`</b> (str, optional):  The API description of the service. 
 - <b>`curation`</b> (dict, optional):  The curation information of the service. 
 - <b>`duration`</b> (int, optional):  The duration of the service. 
 - <b>`tags`</b> (List[str], optional):  The tags associated with the service. 



**Returns:**
 
 - <b>`Response`</b>:  The response from the API call. 

---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/payments.py#L40"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `create_subscription`

```python
create_subscription(
    name: str,
    description: str,
    price: int,
    token_address: str,
    amount_of_credits: Optional[int],
    duration: Optional[int],
    tags: Optional[List[str]]
)
```

Creates a new subscription. 



**Args:**
 
 - <b>`name`</b> (str):  The name of the subscription. 
 - <b>`description`</b> (str):  The description of the subscription. 
 - <b>`price`</b> (int):  The price of the subscription. 
 - <b>`token_address`</b> (str):  The token address. 
 - <b>`amount_of_credits`</b> (int, optional):  The amount of credits for the subscription. 
 - <b>`duration`</b> (int, optional):  The duration of the subscription. 
 - <b>`tags`</b> (List[str], optional):  The tags associated with the subscription. 



**Returns:**
 
 - <b>`Response`</b>:  The response from the API call. 

---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/payments.py#L193"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `get_asset_ddo`

```python
get_asset_ddo(did: str)
```

Gets the asset DDO. 



**Args:**
 
 - <b>`did`</b> (str):  The DID of the asset. 



**Returns:**
 
 - <b>`Response`</b>:  The response from the API call. 

---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/payments.py#L296"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `get_checkout_subscription`

```python
get_checkout_subscription(subscription_did: str)
```

Gets the checkout subscription. 



**Args:**
 
 - <b>`subscription_did`</b> (str):  The DID of the subscription. 



**Returns:**
 
 - <b>`Response`</b>:  The url of the checkout subscription. 

---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/payments.py#L283"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `get_file_details`

```python
get_file_details(file_did: str)
```

Gets the file details. 



**Args:**
 
 - <b>`file_did`</b> (str):  The DID of the file. 



**Returns:**
 
 - <b>`Response`</b>:  The url of the file details. 

---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/payments.py#L270"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `get_service_details`

```python
get_service_details(service_did: str)
```

Gets the service details. 



**Args:**
 
 - <b>`service_did`</b> (str):  The DID of the service. 



**Returns:**
 
 - <b>`Response`</b>:  The url of the service details. 

---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/payments.py#L235"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `get_service_token`

```python
get_service_token(service_did: str)
```

Gets the service token. 



**Args:**
 
 - <b>`service_did`</b> (str):  The DID of the service. 



**Returns:**
 
 - <b>`Response`</b>:  The response from the API call. 

---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/payments.py#L211"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `get_subscription_balance`

```python
get_subscription_balance(
    subscription_did: str,
    account_address: Optional[str] = None
)
```

Gets the subscription balance. 



**Args:**
 
 - <b>`subscription_did`</b> (str):  The DID of the subscription. 
 - <b>`account_address`</b>:  Optional[str]: The account address. 



**Returns:**
 
 - <b>`Response`</b>:  The response from the API call. 

---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/payments.py#L257"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `get_subscription_details`

```python
get_subscription_details(subscription_did: str)
```

Gets the subscription details. 



**Args:**
 
 - <b>`subscription_did`</b> (str):  The DID of the subscription. 



**Returns:**
 
 - <b>`Response`</b>:  The url of the subscription details. 




---

_This file was automatically generated via [lazydocs](https://github.com/ml-tooling/lazydocs)._
