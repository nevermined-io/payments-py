<!-- markdownlint-disable -->

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/mcp/index.py#L0"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

# <kbd>module</kbd> `mcp.index`
MCP integration entry-point for the Nevermined Payments Python SDK. 

This module exposes a class-based API (no dict-like compatibility): 


- ``MCPIntegration``: Main integration surface with methods 
  - ``configure(options)``: Set shared configuration such as agentId/serverName 
  - ``with_paywall(handler, options)``: Decorate a handler with paywall 
  - ``attach(server)``: Returns an object with ``registerTool``, ``registerResource``, ``registerPrompt`` 
  - ``authenticate_meta(extra, method)``: Authenticate meta operations like initialize/list 


- ``build_mcp_integration(payments_service)``: Factory returning an ``MCPIntegration`` instance. 


---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/mcp/index.py#L189"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

## <kbd>function</kbd> `build_mcp_integration`

```python
build_mcp_integration(payments_service: Any) → MCPIntegration
```

Factory that builds the class-based MCP integration. 



**Args:**
 
 - <b>`payments_service`</b>:  The initialized Payments client 



**Returns:**
 MCPIntegration instance 


---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/mcp/index.py#L52"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

## <kbd>class</kbd> `MCPIntegration`
Class-based MCP integration for Payments. 

Provides a clean methods API to configure paywall, decorate handlers and attach registrations to a server implementation. 

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/mcp/index.py#L59"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `__init__`

```python
__init__(payments_service: Any) → None
```

Initialize the integration with a Payments service instance. 



**Args:**
 
 - <b>`payments_service`</b>:  The initialized Payments client 




---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/mcp/index.py#L119"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `attach`

```python
attach(server: _AttachableServer)
```

Attach helpers to a server and return registration methods. 



**Args:**
 
 - <b>`server`</b>:  An object exposing registerTool/registerResource/registerPrompt 



**Returns:**
 An object with methods to register protected handlers on the server 

---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/mcp/index.py#L102"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `authenticate_meta`

```python
authenticate_meta(extra: Any, method: str) → Dict[str, Any]
```

Authenticate meta endpoints such as initialize/list. 



**Args:**
 
 - <b>`extra`</b>:  Extra request metadata containing headers 
 - <b>`method`</b>:  The meta method name 



**Returns:**
 Authentication result dict 

---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/mcp/index.py#L72"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `configure`

```python
configure(options: Dict[str, Any]) → None
```

Configure shared options such as ``agentId`` and ``serverName``. 



**Args:**
 
 - <b>`options`</b>:  Configuration dictionary with keys like ``agentId`` and ``serverName`` 

---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/mcp/index.py#L80"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `with_paywall`

```python
with_paywall(
    handler: Union[Callable[, Awaitable[Any]], Callable[, Any]],
    options: Optional[ToolOptions, PromptOptions, ResourceOptions] = None
) → Callable[, Awaitable[Any]]
```

Wrap a handler with the paywall protection. 

The handler can optionally receive a PaywallContext parameter containing authentication and credit information. Handlers without this parameter will continue to work for backward compatibility. 



**Args:**
 
 - <b>`handler`</b>:  The tool/resource/prompt handler to protect. Can optionally  accept a PaywallContext parameter as the last argument. 
 - <b>`options`</b>:  The paywall options including kind, name and credits 



**Returns:**
 An awaitable handler with paywall applied 




---

_This file was automatically generated via [lazydocs](https://github.com/ml-tooling/lazydocs)._
