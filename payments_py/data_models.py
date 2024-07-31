from pydantic import BaseModel, ConfigDict, Field
from enum import Enum
from typing import Union

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

        