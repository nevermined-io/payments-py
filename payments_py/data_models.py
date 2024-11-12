from pydantic import BaseModel, ConfigDict, Field
from enum import Enum
from typing import Dict, List, Optional, Union, Any
from datetime import datetime

class PlanType(str, Enum):
    CREDITS = 'credits'
    TIME = 'time'
    BOTH = 'both'

class BalanceResultDto(BaseModel):
    planType: PlanType = Field(..., description="Plan type.")
    isOwner: bool = Field(..., description="Is the account owner of the plan.")
    isSubscriptor: bool = Field(..., description="If the user is not the owner but has purchased the plan.")
    balance: Union[int, str] = Field(..., description="The balance of the account.")
    
    model_config = ConfigDict(
        json_schema_extra = {
            "example": {
                "planType": "credits",
                "isOwner": True,
                "isSubscriptor": True,
                "balance": 10000000
            }
        }
    )

class MintResultDto(BaseModel):
    userOpHash: str = Field(..., description="User operation hash.")
    success: bool = Field(..., description="True if the operation was successful.")
    amount: str = Field(..., description="The amount of credits minted.")
    
    model_config = ConfigDict(
        json_schema_extra = {
            "example": {
                "userOpHash": "0x326157ef72dccc8d6d41128a1039a10b30419b8f7891a3dd1d811b7414822aae",
                "success": True,
                "amount": "12"
            }
        }
    )

class BurnResultDto(BaseModel):
    userOpHash: str = Field(..., description="User operation hash.")
    success: bool = Field(..., description="True if the operation was successful.")
    amount: str = Field(..., description="The amount of credits burned.")

    model_config = ConfigDict(
        json_schema_extra = {
            "example": {
                "userOpHash": "0x326157ef72dccc8d6d41128a1039a10b30419b8f7891a3dd1d811b7414822aae",
                "success": True,
                "amount": "12"
            }
        }
    )

class CreateAssetResultDto(BaseModel):
    did: str = Field(..., description="The DID of the asset.")

    model_config = ConfigDict(
        json_schema_extra = {
            "example": {
                "did": "did:nv:f1a974ca211e855a89b9a2049900fec29cc79cd9ca4e8d791a27836009c5b215"
            }
        }
    )

class DownloadFileResultDto(BaseModel):
    success: bool = Field(..., description="True if the operation was successful.")

    model_config = ConfigDict(
        json_schema_extra = {
            "example": {
                "success": True
            }
        }
    )

class OrderPlanResultDto(BaseModel):
    agreementId: str = Field(..., description="The agreement ID.")
    success: bool = Field(..., description="True if the operation was successful.")

    model_config = ConfigDict(
        json_schema_extra = {
            "example": {
                "agreementId": "0x4fe3e7d42fA83be4E8cF03451Ac3F25980a73fF6209172408ad0f79012",
                "success": True
            }
        }
    )

class ServiceTokenResultDto(BaseModel):
    accessToken: str = Field(..., description="The service token.")
    neverminedProxyUri: str = Field(..., description="The nevermined proxy URI.")

    model_config = ConfigDict(
        json_schema_extra = {
            "example": { 
                "accessToken": "isudgfaahsfoasghfhasfuhasdfuishfihu",
                "neverminedProxyUri": "https://12312313.proxy.nevermined.app"
            }
        }
    )

class AgentExecutionStatus(str, Enum):
    Pending = "Pending"
    In_Progress = "In_Progress"
    Not_Ready = "Not_Ready"
    Completed = "Completed"
    Failed = "Failed"

class TaskLog(BaseModel):
    task_id: str = Field(..., description="The task ID.")
    message: str = Field(..., description="Message that will be logged.")
    level: str = Field(..., description="Log level. info, warn, debug, error.")
    step_id: Optional[str] = Field(None, description="The step ID.")
    task_status: Optional[AgentExecutionStatus] = Field(None, description="The status of the task.")

class SearchTasks(BaseModel):
    did: Optional[str] = None
    task_id: Optional[str] = None
    name: Optional[str] = None
    task_status: Optional[AgentExecutionStatus] = None
    page: Optional[int] = None
    offset: Optional[int] = None

class SearchSteps(BaseModel):
    step_id: Optional[str] = None
    task_id: Optional[str] = None
    did: Optional[str] = None
    name: Optional[str] = None
    step_status: Optional[AgentExecutionStatus] = None
    page: Optional[int] = None
    offset: Optional[int] = None

class Artifact(BaseModel):
    artifact_id: str
    url: str

class ExecutionInput(BaseModel):
    query: str
    additional_params: Optional[List[Dict[str, str]]] = None
    artifacts: Optional[List[Artifact]] = None

class ExecutionOutput(BaseModel):
    output: Any
    additional_output: Optional[List[Dict[str, Any]]] = None
    artifacts: Optional[List[str]] = None

class ExecutionOptions(BaseModel):
    input: ExecutionInput
    status: AgentExecutionStatus
    output: Optional[ExecutionOutput] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    retries: Optional[int] = None

class Step(ExecutionOptions):
    step_id: str
    task_id: str
    is_last: Optional[bool] = False
    name: Optional[str] = None

class Task(ExecutionOptions):
    task_id: str
    steps: List[Step]
    name: Optional[str] = None

# Constants for step names
FIRST_STEP_NAME = 'init'
