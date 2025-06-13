"""
Type definitions for the Nevermined Payments protocol.
"""
from typing import Optional, List, Dict, Any, Union
from pydantic import BaseModel, Field
from enum import Enum

# Address type alias
Address = str

class PaymentOptions(BaseModel):
    """
    Options for initializing the Payments class.
    """
    environment: str
    nvm_api_key: Optional[str] = None
    return_url: Optional[str] = None
    app_id: Optional[str] = None
    version: Optional[str] = None
    headers: Optional[Dict[str, str]] = None

class Endpoint(BaseModel):
    """
    Endpoint for a service. Dict with HTTP verb as key and URL as value.
    """
    verb: str
    url: str

class AuthType(str, Enum):
    """
    Allowed authentication types for AgentAPIAttributes.
    """
    NONE = 'none'
    BASIC = 'basic'
    OAUTH = 'oauth'
    BEARER = 'bearer'

class AgentAPIAttributes(BaseModel):
    """
    API attributes for an agent.
    """
    endpoints: List[Endpoint]
    open_endpoints: Optional[List[str]] = None
    open_api_url: Optional[str] = None
    auth_type: Optional[AuthType] = AuthType.NONE
    username: Optional[str] = None
    password: Optional[str] = None
    token: Optional[str] = None
    api_key: Optional[str] = None
    headers: Optional[Dict[str, str]] = None

class AgentMetadata(BaseModel):
    """
    Metadata for an agent.
    """
    name: str
    description: Optional[str] = None
    author: Optional[str] = None
    license: Optional[str] = None
    tags: Optional[List[str]] = None
    integration: Optional[str] = None
    sample_link: Optional[str] = None
    api_description: Optional[str] = None
    date_created: Optional[str] = None

class PlanMetadata(AgentMetadata):
    """
    Metadata for a payment plan, extends AgentMetadata.
    """
    is_trial_plan: Optional[bool] = None

class PlanPriceType(Enum):
    """
    Different types of prices that can be configured for a plan.
    0 - FIXED_PRICE, 1 - FIXED_FIAT_PRICE, 2 - SMART_CONTRACT_PRICE
    """
    FIXED_PRICE = 0
    FIXED_FIAT_PRICE = 1
    SMART_CONTRACT_PRICE = 2

class PlanCreditsType(Enum):
    """
    Different types of credits that can be obtained when purchasing a plan.
    0 - EXPIRABLE, 1 - FIXED, 2 - DYNAMIC
    """
    EXPIRABLE = 0
    FIXED = 1
    DYNAMIC = 2

class PlanRedemptionType(Enum):
    """
    Different types of redemptions criterias that can be used when redeeming credits.
    0 - ONLY_GLOBAL_ROLE, 1 - ONLY_OWNER, 2 - ONLY_PLAN_ROLE
    """
    ONLY_GLOBAL_ROLE = 0
    ONLY_OWNER = 1
    ONLY_PLAN_ROLE = 2

class PlanPriceConfig(BaseModel):
    """
    Definition of the price configuration for a Payment Plan.
    """
    price_type: PlanPriceType
    token_address: Optional[str] = None
    amounts: List[int] = Field(default_factory=list)
    receivers: List[str] = Field(default_factory=list)
    contract_address: Optional[str] = None
    fee_controller: Optional[str] = None

class PlanCreditsConfig(BaseModel):
    """
    Definition of the credits configuration for a payment plan.
    """
    credits_type: PlanCreditsType
    redemption_type: PlanRedemptionType
    proof_required: bool
    duration_secs: int
    amount: int
    min_amount: int
    max_amount: int
    nft_address: Optional[str] = None

class PlanBalance(BaseModel):
    """
    Balance information for a payment plan.
    """
    plan_id: str
    holder_address: str
    balance: int
    credits_contract: str
    is_subscriber: bool