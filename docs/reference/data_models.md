# Data Models Reference

Type definitions and models used throughout the SDK.

## Core Types

### PaymentOptions

::: payments_py.common.types.PaymentOptions
    options:
      show_root_heading: true
      show_source: true

### AgentMetadata

::: payments_py.common.types.AgentMetadata
    options:
      show_root_heading: true
      show_source: true

### AgentAPIAttributes

::: payments_py.common.types.AgentAPIAttributes
    options:
      show_root_heading: true
      show_source: true

### PlanMetadata

::: payments_py.common.types.PlanMetadata
    options:
      show_root_heading: true
      show_source: true

### PlanPriceConfig

::: payments_py.common.types.PlanPriceConfig
    options:
      show_root_heading: true
      show_source: true

### PlanCreditsConfig

::: payments_py.common.types.PlanCreditsConfig
    options:
      show_root_heading: true
      show_source: true

### PlanBalance

::: payments_py.common.types.PlanBalance
    options:
      show_root_heading: true
      show_source: true

## Enums

### AuthType

::: payments_py.common.types.AuthType
    options:
      show_root_heading: true

### PlanPriceType

::: payments_py.common.types.PlanPriceType
    options:
      show_root_heading: true

### PlanCreditsType

::: payments_py.common.types.PlanCreditsType
    options:
      show_root_heading: true

### PlanRedemptionType

::: payments_py.common.types.PlanRedemptionType
    options:
      show_root_heading: true

### AgentTaskStatus

::: payments_py.common.types.AgentTaskStatus
    options:
      show_root_heading: true

## Utility Types

### PaginationOptions

::: payments_py.common.types.PaginationOptions
    options:
      show_root_heading: true
      show_source: true

### TrackAgentSubTaskDto

::: payments_py.common.types.TrackAgentSubTaskDto
    options:
      show_root_heading: true
      show_source: true

## Plan Helper Functions

::: payments_py.plans
    options:
      show_root_heading: true
      show_source: true
      members:
        - get_fiat_price_config
        - get_erc20_price_config
        - get_native_token_price_config
        - get_crypto_price_config
        - get_free_price_config
        - get_fixed_credits_config
        - get_dynamic_credits_config
        - get_expirable_duration_config
        - get_non_expirable_duration_config
        - set_redemption_type
        - set_proof_required
