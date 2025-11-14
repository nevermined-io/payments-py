<!-- markdownlint-disable -->

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/environments.py#L0"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

# <kbd>module</kbd> `environments`




**Global Variables**
---------------
- **ZeroAddress**
- **Environments**

---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/environments.py#L71"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

## <kbd>function</kbd> `get_environment`

```python
get_environment(
    name: Literal['sandbox', 'live', 'staging_sandbox', 'staging_live', 'custom']
) → EnvironmentInfo
```

Get the environment configuration by name. 



**Args:**
 
 - <b>`name`</b>:  The name of the environment. 



**Returns:**
 
 - <b>`EnvironmentInfo`</b>:  The environment configuration. 



**Raises:**
 
 - <b>`ValueError`</b>:  If the environment name is not defined. 


---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/environments.py#L6"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

## <kbd>class</kbd> `EnvironmentInfo`
Data class to store environment information. 



**Attributes:**
 
 - <b>`frontend`</b> (str):  Frontend URL 
 - <b>`backend`</b> (str):  Backend URL 
 - <b>`proxy`</b> (str):  Proxy URL 
 - <b>`helicone_url`</b> (str):  Helicone URL 

<a href="https://github.com/nevermined-io/payments-py/blob/main/<string>"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `__init__`

```python
__init__(
    backend: str,
    proxy: str,
    helicone_url: str,
    frontend: str = None
) → None
```











---

_This file was automatically generated via [lazydocs](https://github.com/ml-tooling/lazydocs)._
