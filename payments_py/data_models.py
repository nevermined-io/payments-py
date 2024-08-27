from pydantic import BaseModel, ConfigDict, Field
from enum import Enum
from typing import Dict, List, Optional, Union

class SubscriptionType(str, Enum):
    CREDITS = 'credits'
    TIME = 'time'
    BOTH = 'both'

class BalanceResultDto(BaseModel):
    subscriptionType: SubscriptionType = Field(..., description="Subscription type.")
    isOwner: bool = Field(..., description="Is the account owner of the subscription.")
    isSubscriptor: bool = Field(..., description="If the user is not the owner but has purchased the subscription.")
    balance: Union[int, str] = Field(..., description="The balance of the account.")
    
    model_config = ConfigDict(
        json_schema_extra = {
            "example": {
                "subscriptionType": "credits",
                "isOwner": True,
                "isSubscriptor": True,
                "balance": 10000000
            }
    })

class MintResultDto(BaseModel):
    userOpHash: str = Field(..., description="User operation hash.")
    success: bool = Field(..., description="True if the operation was succesfull.")
    amount: str = Field(..., description="The amount of credits minted.")
    
    model_config = ConfigDict(
        json_schema_extra = {
            "example": {
                "userOpHash": "0x326157ef72dccc8d6d41128a1039a10b30419b8f7891a3dd1d811b7414822aae",
                "success": True,
                "amount": "12"
            }
        })

class BurnResultDto(BaseModel):
    userOpHash: str = Field(..., description="User operation hash.")
    success: bool = Field(..., description="True if the operation was succesfull.")
    amount: str = Field(..., description="The amount of credits minted.")

    model_config = ConfigDict(
        json_schema_extra = {
            "example": {
                "userOpHash": "0x326157ef72dccc8d6d41128a1039a10b30419b8f7891a3dd1d811b7414822aae",
                "success": True,
                "amount": "12"
            }
        })

class CreateAssetResultDto(BaseModel):
    did: str = Field(..., description="The DID of the asset.")

    model_config = ConfigDict(
        json_schema_extra = {
            "example": {
                "did": "did:nv:f1a974ca211e855a89b9a2049900fec29cc79cd9ca4e8d791a27836009c5b215"
            }
        })

class DownloadFileResultDto(BaseModel):
    success: bool = Field(..., description="True if the operation was succesfull.")

    model_config = ConfigDict(
        json_schema_extra = {
            "example": {
                "success": True
            }
        })

class OrderSubscriptionResultDto(BaseModel):
    agreementId: str = Field(..., description="The agreement ID.")
    success: bool = Field(..., description="True if the operation was succesfull.")

    model_config = ConfigDict(
        json_schema_extra = {
            "example": {
                "agreementId": "0x4fe3e7d42fA83be4E8cF03451Ac3F25980a73fF6209172408ad0f79012",
                "success": True
            }
        })

class ServiceTokenResultDto(BaseModel):
    accessToken: str = Field(..., description="The service token.")
    neverminedProxyUri: str = Field(..., description="The nevermined proxy URI.")

    model_config = ConfigDict(
        json_schema_extra = {
            "example": { 
                "accessToken": "isudgfaahsfoasghfhasfuhasdfuishfihu",
                "neverminedProxyUri": "https://12312313.proxy.nevermined.app"
            }
        })

        
class AgentStepEntity:
    @staticmethod
    def generateId():
        return "generated_id"  # Placeholder for actual ID generation logic

class AgentExecutionStatus(str):
    Not_Ready = "Not_Ready"
    Completed = "Completed"
    # Add other status options here

class Artifact(BaseModel):
    artifactId: str
    url: str

class BaseStepDto(BaseModel):
    task_id: str = Field(..., description="Id of the task")
    
    input_query: Optional[str] = Field(None, example="What's the weather in NY now?", description="Input for the task")
    
    input_params: Optional[List[Dict[str, str]]] = Field(None, example=[{'assistantId': '1234'}], description="List of additional key-value parameters required for the step")
    
    input_artifacts: Optional[List[Artifact]] = Field(None, example=[{'artifactId': 'art-aabb', 'url': 'https://nevermined.io/file.txt'}], description="Artifacts for the step")
    
    name: Optional[str] = Field(None, example="summarizer", description="Name of the step")
    
    order: Optional[int] = Field(None, example=1, description="Order of the execution of the step")
    
    cost: Optional[int] = Field(None, example=5, description="Cost in credits of executing the step")
    
    predecessor: Optional[str] = Field(None, example=AgentStepEntity.generateId(), description="Previous step id. If not given, the system will associate to the latest step (by order).")
    
    is_last: Optional[bool] = Field(None, example=True, description="Is the last step of the task?")

class NewStepDto(BaseStepDto):
    step_id: Optional[str] = Field(None, description="Id of the step. If not given or invalid, the system will auto-generate it", example=AgentStepEntity.generateId())
    
    step_status: Optional[AgentExecutionStatus] = Field(None, description="Status of the step", example=AgentExecutionStatus.Not_Ready)
    
    input_query: str = Field(..., example="What's the weather in NY now?", description="Input for the task")

class UpdateStepDto(BaseStepDto):
    step_id: str = Field(..., description="Id of the step. If not given or invalid, the system will auto-generate it", example=AgentStepEntity.generateId())
    
    step_status: AgentExecutionStatus = Field(..., description="New status of the step", example=AgentExecutionStatus.Completed)
    
    output: Optional[str] = Field(None, example="success", description="Output of the step")
    
    output_additional: Optional[List[Dict[str, str]]] = Field(None, example=[{'message': 'success'}], description="List of additional key-value output values generated by the step")
    
    output_artifacts: Optional[List[Artifact]] = Field(None, example=[{'artifactId': 'art-aabb', 'url': 'https://nevermined.io/file.txt'}], description="Artifacts generated by the execution of the step")

class CreateStepsDto(BaseModel):
    steps: Optional[List[NewStepDto]] = Field(None, example=[{
        'task_id': 'task-1234',
        'input_query': 'What is the weather in NY now?',
        'name': 'summarizer',
        'order': 2,
        'is_last': True
    }], description="List of new Steps to create")

class CreateTaskDto(BaseModel):
    query: str = Field(..., example="What's the weather in NY now?", description='Input for the task')
    name: Optional[str] = Field(None, example="summarizer", description='Name of the task')
    additional_params: Optional[List[Dict[str, str]]] = Field(None, example=[{"assistantId": "1234"}], description='List of additional key-value parameters required for the task')
    artifacts: Optional[List[Artifact]] = Field(None, example=[{"artifactId": "art-aabb", "url": "https://nevermined.io/file.txt"}], description='Artifacts for the task')    