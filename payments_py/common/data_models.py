"""
Data models for the Nevermined Payments protocol.
"""

from typing import Optional, List, Dict
from pydantic import BaseModel


class BalanceResultDto(BaseModel):
    """Balance result data transfer object."""

    plan_type: str
    is_owner: bool
    is_subscriptor: bool
    balance: int


class BurnResultDto(BaseModel):
    """Burn result data transfer object."""

    user_op_hash: str
    success: bool
    amount: str


class CreateAgentAndPlanResultDto(BaseModel):
    """Create agent and plan result data transfer object."""

    plan_did: str
    agent_did: str


class CreateAssetResultDto(BaseModel):
    """Create asset result data transfer object."""

    did: str
    success: bool


class CreateCreditsPlanDto(BaseModel):
    """Create credits plan data transfer object."""

    name: str
    description: str
    price: float
    token_address: str
    amount_of_credits: int
    tags: Optional[List[str]] = None


class CreateTimePlanDto(BaseModel):
    """Create time plan data transfer object."""

    name: str
    description: str
    price: float
    token_address: str
    duration: int
    tags: Optional[List[str]] = None


class CreateServiceDto(BaseModel):
    """Create service data transfer object."""

    plan_did: str
    service_type: str
    name: str
    description: str
    service_charge_type: str
    auth_type: Optional[str] = None
    amount_of_credits: Optional[int] = None
    min_credits_to_charge: Optional[int] = None
    max_credits_to_charge: Optional[int] = None
    username: Optional[str] = None
    password: Optional[str] = None
    token: Optional[str] = None
    endpoints: Optional[List[str]] = None
    open_endpoints: Optional[List[str]] = None
    open_api_url: Optional[str] = None
    integration: Optional[str] = None
    sample_link: Optional[str] = None
    api_description: Optional[str] = None
    tags: Optional[List[str]] = None
    use_ai_hub: Optional[bool] = None
    implements_query_protocol: Optional[bool] = None
    query_protocol_version: Optional[str] = None
    service_host: Optional[str] = None


class CreateFileDto(BaseModel):
    """Create file data transfer object."""

    plan_did: str
    asset_type: str
    name: str
    description: str
    files: List[Dict[str, str]]
    tags: Optional[List[str]] = None
    data_schema: Optional[str] = None
    sample_code: Optional[str] = None
    usage_example: Optional[str] = None
    files_format: Optional[str] = None
    programming_language: Optional[str] = None
    framework: Optional[str] = None
    task: Optional[str] = None
    architecture: Optional[str] = None
    training_details: Optional[str] = None
    variations: Optional[str] = None
    fine_tunable: Optional[bool] = None
    amount_of_credits: Optional[int] = None


class CreateAgentDto(BaseModel):
    """Create agent data transfer object."""

    plan_did: str
    name: str
    description: str
    service_charge_type: str
    auth_type: Optional[str] = None
    amount_of_credits: Optional[int] = None
    min_credits_to_charge: Optional[int] = None
    max_credits_to_charge: Optional[int] = None
    username: Optional[str] = None
    password: Optional[str] = None
    token: Optional[str] = None
    endpoints: Optional[List[str]] = None
    open_endpoints: Optional[List[str]] = None
    open_api_url: Optional[str] = None
    integration: Optional[str] = None
    sample_link: Optional[str] = None
    api_description: Optional[str] = None
    tags: Optional[List[str]] = None
    use_ai_hub: Optional[bool] = None
    implements_query_protocol: Optional[bool] = None
    query_protocol_version: Optional[str] = None
    service_host: Optional[str] = None


class DownloadFileResultDto(BaseModel):
    """Download file result data transfer object."""

    success: bool


class MintResultDto(BaseModel):
    """Mint result data transfer object."""

    user_op_hash: str
    success: bool
    amount: str


class OrderPlanResultDto(BaseModel):
    """Order plan result data transfer object."""

    agreement_id: str
    success: bool


class ServiceTokenResultDto(BaseModel):
    """Service token result data transfer object."""

    token: str
    proxy_url: str
