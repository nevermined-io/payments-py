"""
Nevermined Payments Protocol Python SDK.
"""

from payments_py.payments import Payments
from payments_py.common.types import (
    PaymentOptions,
    PlanMetadata,
    PlanPriceConfig,
    PlanCreditsConfig,
    AgentMetadata,
    AgentAPIAttributes,
    PlanBalance,
    TrackAgentSubTaskDto,
    AgentTaskStatus,
    StartAgentRequest,
    AgentAccessCredentials,
    NvmAPIResult,
    PaginationOptions,
)
from payments_py.common.payments_error import PaymentsError
from payments_py.api.query_api import AIQueryApi
from payments_py.api.plans_api import PlansAPI
from payments_py.api.agents_api import AgentsAPI
from payments_py.api.requests_api import AgentRequestsAPI
from payments_py.api.base_payments import BasePaymentsAPI
from payments_py.api.observability_api import ObservabilityAPI

# X402 Payment Protocol Module
from payments_py.x402 import (
    PaymentRequirements,
    NvmPaymentRequiredResponse,
    PaymentPayload,
    SessionKeyPayload,
    VerifyResponse,
    SettleResponse,
    SupportedNetworks,
    SupportedSchemes,
    NeverminedFacilitator,
    FacilitatorAPI,
    X402TokenAPI,
)

# Import utility functions
from payments_py.utils import (
    is_ethereum_address,
    generate_step_id,
    is_step_id_valid,
    sleep,
    json_replacer,
    get_random_big_int,
    get_query_protocol_endpoints,
    get_ai_hub_open_api_url,
    get_service_host_from_endpoints,
)
from payments_py.x402.token import decode_access_token

# Import plan utility functions
from payments_py.plans import (
    ONE_DAY_DURATION,
    ONE_WEEK_DURATION,
    ONE_MONTH_DURATION,
    ONE_YEAR_DURATION,
    get_fiat_price_config,
    get_crypto_price_config,
    get_erc20_price_config,
    get_free_price_config,
    get_native_token_price_config,
    get_expirable_duration_config,
    get_non_expirable_duration_config,
    get_fixed_credits_config,
    get_dynamic_credits_config,
    set_redemption_type,
    set_proof_required,
    # Pay As You Go functions
    get_pay_as_you_go_price_config,
    get_pay_as_you_go_credits_config,
)

# Import environment constants
from payments_py.environments import (
    ZeroAddress,
    EnvironmentInfo,
    EnvironmentName,
    Environments,
    get_environment,
)

__all__ = [
    # Core
    "Payments",
    "PaymentOptions",
    "PlanMetadata",
    "PlanPriceConfig",
    "PlanCreditsConfig",
    "AgentMetadata",
    "AgentAPIAttributes",
    "PlanBalance",
    "TrackAgentSubTaskDto",
    "AgentTaskStatus",
    "StartAgentRequest",
    "AgentAccessCredentials",
    "NvmAPIResult",
    "PaginationOptions",
    "PaymentsError",
    # APIs
    "AIQueryApi",
    "PlansAPI",
    "AgentsAPI",
    "AgentRequestsAPI",
    "BasePaymentsAPI",
    "ObservabilityAPI",
    # X402 APIs
    "FacilitatorAPI",
    "X402TokenAPI",
    # X402 Types
    "PaymentRequirements",
    "NvmPaymentRequiredResponse",
    "PaymentPayload",
    "SessionKeyPayload",
    "VerifyResponse",
    "SettleResponse",
    "SupportedNetworks",
    "SupportedSchemes",
    # X402 Facilitator
    "NeverminedFacilitator",
    # Utility functions
    "is_ethereum_address",
    "generate_step_id",
    "is_step_id_valid",
    "sleep",
    "json_replacer",
    "get_random_big_int",
    "decode_access_token",
    "get_query_protocol_endpoints",
    "get_ai_hub_open_api_url",
    "get_service_host_from_endpoints",
    # Plan constants and functions
    "ONE_DAY_DURATION",
    "ONE_WEEK_DURATION",
    "ONE_MONTH_DURATION",
    "ONE_YEAR_DURATION",
    "get_fiat_price_config",
    "get_crypto_price_config",
    "get_erc20_price_config",
    "get_free_price_config",
    "get_native_token_price_config",
    "get_expirable_duration_config",
    "get_non_expirable_duration_config",
    "get_fixed_credits_config",
    "get_dynamic_credits_config",
    "set_redemption_type",
    "set_proof_required",
    # Pay As You Go functions
    "get_pay_as_you_go_price_config",
    "get_pay_as_you_go_credits_config",
    # Environment constants
    "ZeroAddress",
    "EnvironmentInfo",
    "EnvironmentName",
    "Environments",
    "get_environment",
]
