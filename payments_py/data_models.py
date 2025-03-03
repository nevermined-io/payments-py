from pydantic import BaseModel, ConfigDict, Field
from enum import Enum
from typing import Dict, List, Optional, TypeVar, Union, Any
from datetime import datetime


class PlanType(str, Enum):
    CREDITS = "credits"
    TIME = "time"
    BOTH = "both"


class CreateCreditsPlanDto(BaseModel):
    name: str = Field(..., description="The name of the plan.")
    description: str = Field(..., description="The description of the plan.")
    price: int = Field(..., description="The price of the plan.")
    token_address: str = Field(..., description="The token address.")
    amount_of_credits: int = Field(
        ..., description="The amount of credits for the plan."
    )
    tags: List[str] = Field(None, description="The tags associated with the plan.")


class CreateTimePlanDto(BaseModel):
    name: str = Field(..., description="The name of the plan.")
    description: str = Field(..., description="The description of the plan.")
    price: int = Field(..., description="The price of the plan.")
    token_address: str = Field(..., description="The token address.")
    duration: int = Field(
        0,
        description="The duration of the plan in days. If not provided, the plan will be valid forever.",
    )
    tags: List[str] = Field(None, description="The tags associated with the plan.")


class CreateServiceDto(BaseModel):
    plan_did: str = Field(..., description="The DID of the plan.")
    service_type: str = Field(
        ...,
        description="The type of the service. Options: 'service', 'agent', 'assistant'",
    )
    name: str = Field(..., description="The name of the service.")
    description: str = Field(..., description="The description of the service.")
    service_charge_type: str = Field(
        ..., description="The charge type of the service. Options: 'fixed', 'dynamic'"
    )
    auth_type: str = Field(
        ...,
        description="The authentication type of the service. Options: 'none', 'basic', 'oauth'",
    )

    amount_of_credits: int = Field(
        1, description="The amount of credits for the service."
    )
    min_credits_to_charge: int = Field(
        1,
        description="The minimum credits to charge for the service. Only required for dynamic services.",
    )
    max_credits_to_charge: int = Field(
        1,
        description="The maximum credits to charge for the service. Only required for dynamic services.",
    )

    username: Optional[str] = Field(
        None, description="The username for authentication."
    )
    password: Optional[str] = Field(
        None, description="The password for authentication."
    )
    token: Optional[str] = Field(None, description="The token for authentication.")

    endpoints: List[Dict[str, str]] = Field(
        default_factory=list, description="The endpoints of the service."
    )
    open_endpoints: List[str] = Field(
        default_factory=list, description="The open endpoints of the service."
    )

    open_api_url: Optional[str] = Field(
        None, description="The OpenAPI URL of the service."
    )
    integration: Optional[str] = Field(
        None, description="The integration type of the service."
    )
    sample_link: Optional[str] = Field(
        None, description="The sample link of the service."
    )
    api_description: Optional[str] = Field(
        None, description="The API description of the service."
    )

    tags: List[str] = Field(
        default_factory=list, description="The tags associated with the service."
    )

    is_nevermined_hosted: bool = Field(
        False, description="Indicates if the service is hosted by Nevermined."
    )
    implements_query_protocol: bool = Field(
        False, description="Indicates if the service implements the query protocol."
    )

    query_protocol_version: Optional[str] = Field(
        None,
        description="The version of the query protocol implemented by the service.",
    )
    service_host: Optional[str] = Field(None, description="The host of the service.")


class CreateFileDto(BaseModel):
    plan_did: str = Field(..., description="The DID of the plan.")
    asset_type: str = Field(
        ...,
        description="The type of the asset. Options: 'algorithm', 'model', 'dataset', 'file'",
    )
    name: str = Field(..., description="The name of the file.")
    description: str = Field(..., description="The description of the file.")
    files: List[Dict] = Field(..., description="The files of the file.")

    data_schema: Optional[str] = Field(None, description="The data schema of the file.")
    sample_code: Optional[str] = Field(None, description="The sample code of the file.")
    files_format: Optional[str] = Field(
        None, description="The files format of the file."
    )
    usage_example: Optional[str] = Field(
        None, description="The usage example of the file."
    )
    programming_language: Optional[str] = Field(
        None, description="The programming language of the file."
    )
    framework: Optional[str] = Field(None, description="The framework of the file.")
    task: Optional[str] = Field(None, description="The task of the file.")
    training_details: Optional[str] = Field(
        None, description="The training details of the file."
    )
    variations: Optional[str] = Field(None, description="The variations of the file.")

    fine_tunable: bool = Field(
        False, description="Indicates whether the file is fine-tunable."
    )
    amount_of_credits: int = Field(0, description="The amount of credits for the file.")

    tags: List[str] = Field(
        default_factory=list, description="The tags associated with the file."
    )


class CreateAgentDto(BaseModel):
    plan_did: Optional[str] = Field(None, description="The DID of the plan.")
    name: str = Field(..., description="The name of the agent.")
    description: str = Field(..., description="The description of the agent.")

    service_charge_type: str = Field(
        ..., description="The charge type of the agent. Options: 'fixed', 'dynamic'"
    )
    auth_type: str = Field(
        ...,
        description="The authentication type of the agent. Options: 'none', 'basic', 'oauth'",
    )

    amount_of_credits: int = Field(
        1, description="The amount of credits for the agent."
    )
    min_credits_to_charge: int = Field(
        1,
        description="The minimum credits to charge for the agent. Only required for dynamic agents.",
    )
    max_credits_to_charge: int = Field(
        1,
        description="The maximum credits to charge for the agent. Only required for dynamic agents.",
    )

    username: Optional[str] = Field(
        None, description="The username for authentication."
    )
    password: Optional[str] = Field(
        None, description="The password for authentication."
    )
    token: Optional[str] = Field(None, description="The token for authentication.")

    endpoints: List[Dict[str, str]] = Field(
        default_factory=list, description="The endpoints of the agent."
    )
    open_endpoints: List[str] = Field(
        default_factory=list, description="The open endpoints of the agent."
    )

    open_api_url: Optional[str] = Field(
        None, description="The OpenAPI URL of the agent."
    )
    integration: Optional[str] = Field(
        None, description="The integration type of the agent."
    )
    sample_link: Optional[str] = Field(
        None, description="The sample link of the agent."
    )
    api_description: Optional[str] = Field(
        None, description="The API description of the agent."
    )

    tags: List[str] = Field(
        default_factory=list, description="The tags associated with the agent."
    )

    use_ai_hub: bool = Field(
        False,
        description="If true, the agent will be configured to use the AI Hub endpoints.",
    )
    implements_query_protocol: bool = Field(
        False, description="Indicates if the agent implements the query protocol."
    )
    query_protocol_version: Optional[str] = Field(
        None, description="The version of the query protocol implemented by the agent."
    )
    service_host: Optional[str] = Field(None, description="The host of the agent.")


class BalanceResultDto(BaseModel):
    planType: PlanType = Field(..., description="Plan type.")
    isOwner: bool = Field(..., description="Is the account owner of the plan.")
    isSubscriptor: bool = Field(
        ..., description="If the user is not the owner but has purchased the plan."
    )
    balance: Union[int, str] = Field(..., description="The balance of the account.")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "planType": "credits",
                "isOwner": True,
                "isSubscriptor": True,
                "balance": 10000000,
            }
        }
    )


class MintResultDto(BaseModel):
    userOpHash: str = Field(..., description="User operation hash.")
    success: bool = Field(..., description="True if the operation was successful.")
    amount: str = Field(..., description="The amount of credits minted.")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "userOpHash": "0x326157ef72dccc8d6d41128a1039a10b30419b8f7891a3dd1d811b7414822aae",
                "success": True,
                "amount": "12",
            }
        }
    )


class BurnResultDto(BaseModel):
    userOpHash: str = Field(..., description="User operation hash.")
    success: bool = Field(..., description="True if the operation was successful.")
    amount: str = Field(..., description="The amount of credits burned.")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "userOpHash": "0x326157ef72dccc8d6d41128a1039a10b30419b8f7891a3dd1d811b7414822aae",
                "success": True,
                "amount": "12",
            }
        }
    )


class CreateAssetResultDto(BaseModel):
    did: str = Field(..., description="The DID of the asset.")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "did": "did:nv:f1a974ca211e855a89b9a2049900fec29cc79cd9ca4e8d791a27836009c5b215"
            }
        }
    )


class CreateAgentAndPlanResultDto(BaseModel):
    planDID: str = Field(..., description="The DID of the plan")
    agentDID: str = Field(..., description="The DID of the agent")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "planDID": "did:nv:f1a974ca211e855a89b9a2049900fec29cc79cd9ca4e8d791a27836009c5b215",
                "agentDID": "did:nv:f1a974ca211e855a89b9a2049900fec29cc79cd9ca4e8d791a27836009c5b213",
            }
        }
    )


class DownloadFileResultDto(BaseModel):
    success: bool = Field(..., description="True if the operation was successful.")

    model_config = ConfigDict(json_schema_extra={"example": {"success": True}})


class OrderPlanResultDto(BaseModel):
    agreementId: str = Field(..., description="The agreement ID.")
    success: bool = Field(..., description="True if the operation was successful.")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "agreementId": "0x4fe3e7d42fA83be4E8cF03451Ac3F25980a73fF6209172408ad0f79012",
                "success": True,
            }
        }
    )


class ServiceTokenResultDto(BaseModel):
    accessToken: str = Field(..., description="The service token.")
    neverminedProxyUri: str = Field(..., description="The nevermined proxy URI.")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "accessToken": "isudgfaahsfoasghfhasfuhasdfuishfihu",
                "neverminedProxyUri": "https://12312313.proxy.nevermined.app",
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
    task_status: Optional[AgentExecutionStatus] = Field(
        None, description="The status of the task."
    )


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
    artifact_id: str = Field(..., description="Unique identifier for the artifact")
    url: str = Field(..., description="URL of the artifact")


class ExecutionInput(BaseModel):
    input_query: str
    input_additional: Optional[Dict[str, Any]] = None
    input_artifacts: Optional[List[Artifact]] = None


class ExecutionOutput(BaseModel):
    output: str
    output_additional: Optional[Dict[str, Any]] = None
    output_artifacts: Optional[List[Artifact]] = None


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
FIRST_STEP_NAME = "init"


class CreateTaskDto(BaseModel):
    input_query: str = Field(
        ..., example="What's the weather in NY now?", description="Input for the task"
    )
    name: Optional[str] = Field(
        None, example="summarizer", description="Name of the task"
    )
    input_additional: Optional[Dict[str, Any]] = Field(
        None,
        example={"assistantId": "1234"},
        description="Additional key-value parameters required for the task",
    )
    input_artifacts: Optional[List[Artifact]] = Field(
        None,
        example=[{"artifactId": "art-aabb", "url": "https://nevermined.io/file.txt"}],
        description="Artifacts for the task",
    )


class BaseStepDto(BaseModel):
    task_id: str = Field(..., description="Id of the task")
    input_query: Optional[str] = Field(
        None, example="What's the weather in NY now?", description="Input for the task"
    )
    input_additional: Optional[Dict[str, Any]] = Field(
        None,
        example={"assistantId": "1234"},
        description="Additional key-value parameters required for the step",
    )
    input_artifacts: Optional[List[Artifact]] = Field(
        None,
        example=[{"artifactId": "art-aabb", "url": "https://nevermined.io/file.txt"}],
        description="Artifacts for the step",
    )
    name: Optional[str] = Field(
        None, example="summarizer", description="Name of the step"
    )
    order: Optional[int] = Field(
        None, example=1, description="Order of the execution of the step"
    )
    cost: Optional[int] = Field(
        None, example=5, description="Cost in credits of executing the step"
    )
    predecessor: Optional[str] = Field(
        None,
        description="Previous step id. If not given, the system will associate it with the latest step (by order).",
    )
    is_last: Optional[bool] = Field(
        None, example=True, description="Is the last step of the task?"
    )


class NewStepDto(BaseStepDto):
    step_id: Optional[str] = Field(
        None,
        description="Id of the step. If not given or invalid, the system will auto-generate it",
    )
    step_status: Optional[AgentExecutionStatus] = Field(
        None, example=AgentExecutionStatus.Not_Ready, description="Status of the step"
    )


class UpdateStepDto(BaseStepDto):
    step_id: str = Field(
        ...,
        description="Id of the step. If not given or invalid, the system will auto-generate it",
    )
    did: Optional[str] = Field(
        None,
        example="did:nv:1234",
        description="The id of the agent (DID) to which the step belongs",
    )
    step_status: AgentExecutionStatus = Field(
        ...,
        example=AgentExecutionStatus.Completed,
        description="New status of the step",
    )
    output: Optional[str] = Field(
        None, example="success", description="Output of the step"
    )
    output_additional: Optional[Dict[str, Any]] = Field(
        None,
        example={"message": "success"},
        description="Additional key-value output values generated by the step",
    )
    output_artifacts: Optional[List[Artifact]] = Field(
        None,
        example=[{"artifactId": "art-aabb", "url": "https://nevermined.io/file.txt"}],
        description="Artifacts generated by the execution of the step",
    )


class CreateStepsDto(BaseModel):
    steps: Optional[List[NewStepDto]] = Field(
        None, description="List of new Steps to create"
    )


class SearchStepsDtoResult(BaseModel):
    steps: List[UpdateStepDto] = Field(..., description="List of steps")
    totalResults: int = Field(..., description="Total number of results")
    page: int = Field(..., description="Current page")
    offset: int = Field(..., description="Page offset")


class TaskEntityDto(BaseModel):
    task_id: str = Field(..., description="Unique identifier for the task")
    did: str = Field(..., description="Decentralized identifier (DID) of the resource")
    user: str = Field(..., description="User's Ethereum address")
    task_status: str = Field(..., description="Current status of the task")
    name: str = Field(..., description="Name of the task")
    input_query: str = Field(..., description="Query associated with the task")
    input_additional: Any = Field(
        default_factory=dict, description="Additional input data"
    )
    input_artifacts: Any = Field(default_factory=dict, description="Input artifacts")
    output: str = Field(..., description="Output of the task")
    output_additional: Dict[str, Any] = Field(
        default_factory=dict, description="Additional output data"
    )
    output_artifacts: List[Any] = Field(
        default_factory=list, description="List of output artifacts"
    )
    cost: int = Field(..., description="Cost associated with the task")
    createdAt: datetime = Field(..., description="Task creation timestamp")
    updatedAt: datetime = Field(..., description="Task last update timestamp")
    owner: str = Field(..., description="Owner of the task")


class SearchTasksDtoResult(BaseModel):
    tasks: List[TaskEntityDto] = Field(..., description="List of tasks")
    totalResults: int = Field(..., description="Total number of results")
    page: int = Field(..., description="Current page")
    offset: int = Field(..., description="Page offset")


class GetStepsDtoResult(BaseModel):
    steps: Optional[List[UpdateStepDto]] = Field(None, description="List of steps")
    totalResults: int


class GetTasksDtoResult(BaseModel):
    tasks: Optional[List[TaskEntityDto]] = Field(None, description="List of tasks")
    totalResults: int


class FullTaskDto(BaseModel):
    task: TaskEntityDto
    steps: List[UpdateStepDto]
    logs: List[TaskLog]


T = TypeVar("T")


class ApiResponse(BaseModel):
    success: bool
    data: Optional[T] = None
    error: Optional[str] = None


class StepEvent(BaseModel):
    step_id: str = Field(..., description="Id of the step")
    task_id: str = Field(..., description="Id of the task")
    did: str = Field(..., description="Id of the agent")


class TaskEvent(BaseModel):
    task_id: str = Field(..., description="Id of the task")
    did: str = Field(..., description="Id of the agent")
    status: str = Field(..., description="Status of the task")
