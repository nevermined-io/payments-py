<!-- markdownlint-disable -->

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/utils.py#L0"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

# <kbd>module</kbd> `utils`
Utility functions for the payments library. 


---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/utils.py#L13"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

## <kbd>function</kbd> `snake_to_camel`

```python
snake_to_camel(name)
```

Convert snake_case to camelCase. 

:param name: str :return: str 


---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/utils.py#L24"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

## <kbd>function</kbd> `is_ethereum_address`

```python
is_ethereum_address(address: str) → bool
```

Check if a string is a valid Ethereum address. 



**Args:**
 
 - <b>`address`</b>:  The address to validate 



**Returns:**
 True if the address is valid, False otherwise 


---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/utils.py#L51"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

## <kbd>function</kbd> `get_random_big_int`

```python
get_random_big_int(bits: int = 128) → int
```

Generate a random big integer with the specified number of bits. 



**Args:**
 
 - <b>`bits`</b>:  The number of bits for the random integer (default: 128) 



**Returns:**
 A random big integer 


---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/utils.py#L73"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

## <kbd>function</kbd> `generate_step_id`

```python
generate_step_id() → str
```

Generate a random step id. 

:return: str 


---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/utils.py#L82"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

## <kbd>function</kbd> `is_step_id_valid`

```python
is_step_id_valid(step_id: str) → bool
```

Check if the step id has the right format. 

:param step_id: str :return: bool 


---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/utils.py#L98"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

## <kbd>function</kbd> `sleep`

```python
sleep(ms: int) → None
```

Sleep for the specified number of milliseconds. 



**Args:**
 
 - <b>`ms`</b>:  The number of milliseconds to sleep 


---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/utils.py#L108"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

## <kbd>function</kbd> `json_replacer`

```python
json_replacer(key: str, value: Any) → Any
```

Custom JSON replacer function to handle special values. 



**Args:**
 
 - <b>`key`</b>:  The key being serialized 
 - <b>`value`</b>:  The value being serialized 



**Returns:**
 The value to serialize, or None to exclude the key-value pair 


---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/utils.py#L124"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

## <kbd>function</kbd> `decode_access_token`

```python
decode_access_token(access_token: str) → Optional[Dict[str, Any]]
```

Decode an access token to extract wallet address and plan ID. 



**Args:**
 
 - <b>`access_token`</b>:  The access token to decode 



**Returns:**
 The decoded token data or None if invalid 


---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/utils.py#L142"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

## <kbd>function</kbd> `get_query_protocol_endpoints`

```python
get_query_protocol_endpoints(server_host: str)
```

Returns the list of endpoints that are used by agents/services implementing the Nevermined Query Protocol. 

:param server_host: str :return: list 


---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/utils.py#L157"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

## <kbd>function</kbd> `get_ai_hub_open_api_url`

```python
get_ai_hub_open_api_url(server_host: str) → str
```

Returns the URL to the OpenAPI documentation of the AI Hub. 

:param server_host: str :return: str 


---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/utils.py#L169"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

## <kbd>function</kbd> `get_service_host_from_endpoints`

```python
get_service_host_from_endpoints(endpoints: List[Dict[str, str]]) → Optional[str]
```

Extract the service host from a list of endpoints. 



**Args:**
 
 - <b>`endpoints`</b>:  List of endpoint dictionaries 



**Returns:**
 The service host URL or None if not found 




---

_This file was automatically generated via [lazydocs](https://github.com/ml-tooling/lazydocs)._
