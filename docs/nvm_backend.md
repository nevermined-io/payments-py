<!-- markdownlint-disable -->

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/nvm_backend.py#L0"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

# <kbd>module</kbd> `nvm_backend`






---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/nvm_backend.py#L14"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

## <kbd>class</kbd> `BackendApiOptions`




<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/nvm_backend.py#L15"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `__init__`

```python
__init__(
    environment: Environment,
    api_key: Optional[str] = None,
    headers: Optional[Dict[str, str]] = None,
    web_socket_options: Optional[Dict[str, Any]] = None
)
```









---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/nvm_backend.py#L28"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

## <kbd>class</kbd> `NVMBackendApi`




<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/nvm_backend.py#L29"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `__init__`

```python
__init__(opts: BackendApiOptions)
```








---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/nvm_backend.py#L72"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `connect_socket`

```python
connect_socket()
```





---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/nvm_backend.py#L180"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `delete`

```python
delete(url: str, data: Any)
```





---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/nvm_backend.py#L141"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `disconnect`

```python
disconnect()
```





---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/nvm_backend.py#L87"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `disconnect_socket`

```python
disconnect_socket()
```





---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/nvm_backend.py#L156"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `get`

```python
get(url: str)
```





---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/nvm_backend.py#L136"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `join_room`

```python
join_room(room_id)
```





---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/nvm_backend.py#L149"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `parse_url_to_backend`

```python
parse_url_to_backend(uri: str) → str
```





---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/nvm_backend.py#L145"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `parse_url_to_proxy`

```python
parse_url_to_proxy(uri: str) → str
```





---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/nvm_backend.py#L164"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `post`

```python
post(url: str, data: Any)
```





---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/nvm_backend.py#L172"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `put`

```python
put(url: str, data: Any)
```





---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/nvm_backend.py#L153"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `set_bearer_token`

```python
set_bearer_token(token: str)
```








---

_This file was automatically generated via [lazydocs](https://github.com/ml-tooling/lazydocs)._
