<!-- markdownlint-disable -->

# API Overview

## Modules

- [`environments`](./environments.md#module-environments)
- [`mcp`](./mcp.md#module-mcp): MCP integration for Nevermined Payments (Python).
- [`mcp.index`](./mcp.index.md#module-mcpindex): MCP integration entry-point for the Nevermined Payments Python SDK.
- [`mcp.types`](./mcp.types.md#module-mcptypes): Types for MCP paywall functionality.
- [`plans`](./plans.md#module-plans): Utility functions for creating and managing payment plans.
- [`utils`](./utils.md#module-utils): Utility functions for the payments library.

## Classes

- [`environments.EnvironmentInfo`](./environments.md#class-environmentinfo): Data class to store environment information.
- [`index.MCPIntegration`](./mcp.index.md#class-mcpintegration): Class-based MCP integration for Payments.
- [`types.AuthResult`](./mcp.types.md#class-authresult): Result returned by authentication routines.
- [`types.BasePaywallOptions`](./mcp.types.md#class-basepaywalloptions): Common paywall options shared by all handler kinds.
- [`types.PaywallContext`](./mcp.types.md#class-paywallcontext): Context provided to paywall-protected handlers.
- [`types.PromptOptions`](./mcp.types.md#class-promptoptions): Paywall options for a prompt handler.
- [`types.ResourceOptions`](./mcp.types.md#class-resourceoptions): Paywall options for a resource handler.
- [`types.ToolOptions`](./mcp.types.md#class-tooloptions): Paywall options for a tool handler.

## Functions

- [`environments.get_environment`](./environments.md#function-get_environment): Get the environment configuration by name.
- [`index.build_mcp_integration`](./mcp.index.md#function-build_mcp_integration): Factory that builds the class-based MCP integration.
- [`plans.get_crypto_price_config`](./plans.md#function-get_crypto_price_config): Get a fixed crypto price configuration for a plan.
- [`plans.get_dynamic_credits_config`](./plans.md#function-get_dynamic_credits_config): Get a dynamic credits configuration for a plan.
- [`plans.get_erc20_price_config`](./plans.md#function-get_erc20_price_config): Get a fixed ERC20 token price configuration for a plan.
- [`plans.get_expirable_duration_config`](./plans.md#function-get_expirable_duration_config): Get an expirable duration configuration for a plan.
- [`plans.get_fiat_price_config`](./plans.md#function-get_fiat_price_config): Get a fixed fiat price configuration for a plan.
- [`plans.get_fixed_credits_config`](./plans.md#function-get_fixed_credits_config): Get a fixed credits configuration for a plan.
- [`plans.get_free_price_config`](./plans.md#function-get_free_price_config): Get a free price configuration for a plan.
- [`plans.get_native_token_price_config`](./plans.md#function-get_native_token_price_config): Get a fixed native token price configuration for a plan.
- [`plans.get_non_expirable_duration_config`](./plans.md#function-get_non_expirable_duration_config): Get a non-expirable duration configuration for a plan.
- [`plans.set_proof_required`](./plans.md#function-set_proof_required): Set whether proof is required for a credits configuration.
- [`plans.set_redemption_type`](./plans.md#function-set_redemption_type): Set the redemption type for a credits configuration.
- [`utils.decode_access_token`](./utils.md#function-decode_access_token): Decode an access token to extract wallet address and plan ID.
- [`utils.generate_step_id`](./utils.md#function-generate_step_id): Generate a random step id.
- [`utils.get_ai_hub_open_api_url`](./utils.md#function-get_ai_hub_open_api_url): Returns the URL to the OpenAPI documentation of the AI Hub.
- [`utils.get_query_protocol_endpoints`](./utils.md#function-get_query_protocol_endpoints): Returns the list of endpoints that are used by agents/services implementing the Nevermined Query Protocol.
- [`utils.get_random_big_int`](./utils.md#function-get_random_big_int): Generate a random big integer with the specified number of bits.
- [`utils.get_service_host_from_endpoints`](./utils.md#function-get_service_host_from_endpoints): Extract the service host from a list of endpoints.
- [`utils.is_ethereum_address`](./utils.md#function-is_ethereum_address): Check if a string is a valid Ethereum address.
- [`utils.is_step_id_valid`](./utils.md#function-is_step_id_valid): Check if the step id has the right format.
- [`utils.json_replacer`](./utils.md#function-json_replacer): Custom JSON replacer function to handle special values.
- [`utils.sleep`](./utils.md#function-sleep): Sleep for the specified number of milliseconds.
- [`utils.snake_to_camel`](./utils.md#function-snake_to_camel): Convert snake_case to camelCase.


---

_This file was automatically generated via [lazydocs](https://github.com/ml-tooling/lazydocs)._
