"""
observability_api.py
Provides reusable utilities for wrapping API calls with Helicone logging for AI agents
"""

import time
import math
import json
from typing import Dict, Any, Optional, Callable, Awaitable, TypeVar, Generic, Union
from dataclasses import dataclass
from urllib.parse import urljoin
from helicone_helpers import HeliconeManualLogger
from helicone_helpers.manual_logger import HeliconeResultRecorder

from payments_py.api.base_payments import BasePaymentsAPI
from payments_py.common.types import PaymentOptions, StartAgentRequest

# Type variables for generic functions
T = TypeVar("T")
R = TypeVar("R")

CustomProperties = Dict[str, str]


@dataclass
class HeliconePayloadConfig:
    """Configuration for creating a Helicone payload"""

    model: str
    input_data: Dict[str, Any]
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    frequency_penalty: Optional[float] = None
    presence_penalty: Optional[float] = None
    n: Optional[int] = None
    stream: Optional[bool] = None


@dataclass
class UsageDetails:
    """Token usage details"""

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    prompt_tokens_details: Optional[Dict[str, int]] = None
    completion_tokens_details: Optional[Dict[str, int]] = None


@dataclass
class HeliconeResponseConfig:
    """Configuration for creating a Helicone response"""

    id_prefix: str
    model: str
    result_data: Any
    usage: UsageDetails
    system_fingerprint: Optional[str] = None


@dataclass
class NeverminedHeliconeHeaders:
    """Nevermined-specific Helicone headers"""

    helicone_auth: str
    account_address: str
    consumer_address: str
    agent_id: str
    plan_id: str
    plan_type: str
    plan_name: str
    agent_name: str
    agent_request_id: str
    price_per_credit: str
    environment_name: str
    batch: str
    is_margin_based: str
    margin_percent: str


@dataclass
class ChatOpenAIConfiguration:
    """Configuration for ChatOpenAI with Helicone"""

    model: str
    api_key: str
    configuration: Dict[str, Any]


@dataclass
class OpenAIConfiguration:
    """Configuration for OpenAI client with Helicone"""

    api_key: str
    base_url: str
    default_headers: Dict[str, str]


def get_default_helicone_headers(
    helicone_api_key: str,
    account_address: str,
    environment_name: str,
    start_agent_request: StartAgentRequest,
    custom_properties: CustomProperties,
) -> Dict[str, str]:
    """Build default Helicone headers from StartAgentRequest object"""

    # Extract values from StartAgentRequest object
    consumer_address = start_agent_request.balance.holder_address
    agent_id = start_agent_request.agent_id
    plan_id = start_agent_request.balance.plan_id
    plan_type = start_agent_request.balance.plan_type
    plan_name = start_agent_request.balance.plan_name
    agent_name = start_agent_request.agent_name
    agent_request_id = start_agent_request.agent_request_id
    price_per_credit = start_agent_request.balance.price_per_credit
    batch = start_agent_request.batch

    # Build Nevermined headers
    nevermined_headers = {
        "Helicone-Auth": f"Bearer {helicone_api_key}",
        "Helicone-Property-accountAddress": account_address,
        "Helicone-Property-consumerAddress": consumer_address,
        "Helicone-Property-agentId": agent_id,
        "Helicone-Property-planId": plan_id,
        "Helicone-Property-planType": plan_type,
        "Helicone-Property-planName": plan_name,
        "Helicone-Property-agentName": agent_name,
        "Helicone-Property-agentRequestId": agent_request_id,
        "Helicone-Property-pricePerCredit": str(price_per_credit),
        "Helicone-Property-environmentName": environment_name,
        "Helicone-Property-batch": str(batch).lower(),
        "Helicone-Property-ismarginBased": "false",
        "Helicone-Property-marginPercent": "0",
    }

    # Add custom property headers
    custom_headers = {}
    for key, value in custom_properties.items():
        custom_headers[f"Helicone-Property-{key}"] = str(value)

    return {**nevermined_headers, **custom_headers}


def create_helicone_payload(config: HeliconePayloadConfig) -> Dict[str, Any]:
    """Creates a standardized Helicone payload for API logging"""
    return {
        "model": config.model,
        "temperature": config.temperature or 1.0,
        "top_p": config.top_p or 1.0,
        "frequency_penalty": config.frequency_penalty or 0.0,
        "presence_penalty": config.presence_penalty or 0.0,
        "n": config.n or 1,
        "stream": config.stream or False,
        "messages": [
            {
                "role": "user",
                "content": json.dumps(config.input_data),
            }
        ],
    }


def create_helicone_response(config: HeliconeResponseConfig) -> Dict[str, Any]:
    """Creates a standardized Helicone response for API logging"""
    timestamp = int(time.time() * 1000)

    return {
        "id": f"{config.id_prefix}-{timestamp}",
        "object": "chat.completion",
        "created": int(timestamp / 1000),
        "model": config.model,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": json.dumps(config.result_data),
                    "refusal": None,
                    "annotations": [],
                },
                "logprobs": None,
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": config.usage.prompt_tokens,
            "completion_tokens": config.usage.completion_tokens,
            "total_tokens": config.usage.total_tokens,
            "prompt_tokens_details": config.usage.prompt_tokens_details
            or {
                "cached_tokens": 0,
                "audio_tokens": 0,
            },
            "completion_tokens_details": config.usage.completion_tokens_details
            or {
                "reasoning_tokens": 0,
                "audio_tokens": 0,
                "accepted_prediction_tokens": 0,
                "rejected_prediction_tokens": 0,
            },
        },
        "service_tier": "default",
        "system_fingerprint": config.system_fingerprint or f"fp_{timestamp}",
    }


async def with_manual_logging(
    agent_name: str,
    payload_config: HeliconePayloadConfig,
    operation: Callable[[], Awaitable[T]],
    result_extractor: Callable[[T], R],
    usage_calculator: Callable[[T], UsageDetails],
    response_id_prefix: str,
    helicone_api_key: str,
    helicone_manual_logging_url: str,
    account_address: str,
    environment_name: str,
    start_agent_request: StartAgentRequest,
    custom_properties: CustomProperties,
) -> R:
    """
    Wraps an async operation with manual logging
    """
    # Get default headers
    default_headers = get_default_helicone_headers(
        helicone_api_key,
        account_address,
        environment_name,
        start_agent_request,
        custom_properties,
    )

    # Initialize the official Helicone manual logger
    helicone_logger = HeliconeManualLogger(
        api_key=helicone_api_key,
        logging_endpoint=helicone_manual_logging_url,
        headers=default_headers,
    )

    helicone_payload = create_helicone_payload(payload_config)

    # Use the official Helicone manual logger pattern
    async def logging_operation(result_recorder: HeliconeResultRecorder) -> R:
        internal_result = await operation()
        usage = usage_calculator(internal_result)
        extracted_result = result_extractor(internal_result)

        helicone_response = create_helicone_response(
            HeliconeResponseConfig(
                id_prefix=response_id_prefix,
                model=payload_config.model,
                result_data=extracted_result,
                usage=usage,
                system_fingerprint=getattr(extracted_result, "job_id", None)
                and f'fp_{getattr(extracted_result, "job_id", "")}',
            )
        )

        result_recorder.append_results(helicone_response)
        return extracted_result

    return await helicone_logger.log_request(helicone_payload, logging_operation)


def calculate_image_usage(pixels: int) -> UsageDetails:
    """Helper function to calculate usage for image operations based on pixels"""
    return UsageDetails(
        prompt_tokens=0,
        completion_tokens=pixels,
        total_tokens=pixels,
        prompt_tokens_details={"cached_tokens": 0, "audio_tokens": 0},
        completion_tokens_details={
            "reasoning_tokens": 0,
            "audio_tokens": 0,
            "accepted_prediction_tokens": 0,
            "rejected_prediction_tokens": 0,
        },
    )


def calculate_video_usage() -> UsageDetails:
    """Helper function to calculate usage for video operations (typically 1 token)"""
    return UsageDetails(
        prompt_tokens=0,
        completion_tokens=1,
        total_tokens=1,
        prompt_tokens_details={"cached_tokens": 0, "audio_tokens": 0},
        completion_tokens_details={
            "reasoning_tokens": 0,
            "audio_tokens": 0,
            "accepted_prediction_tokens": 0,
            "rejected_prediction_tokens": 0,
        },
    )


def calculate_song_usage(tokens: int) -> UsageDetails:
    """Helper function to calculate usage for song operations based on tokens/quota"""
    return UsageDetails(
        prompt_tokens=0,
        completion_tokens=tokens,
        total_tokens=tokens,
        prompt_tokens_details={"cached_tokens": 0, "audio_tokens": 0},
        completion_tokens_details={
            "reasoning_tokens": 0,
            "audio_tokens": 0,
            "accepted_prediction_tokens": 0,
            "rejected_prediction_tokens": 0,
        },
    )


def calculate_dummy_song_usage() -> UsageDetails:
    """Helper function to calculate usage for dummy song operations"""
    return calculate_song_usage(6)  # Default dummy token count


def with_langchain(
    model: str,
    api_key: str,
    helicone_api_key: str,
    helicone_base_logging_url: str,
    account_address: str,
    environment_name: str,
    start_agent_request: StartAgentRequest,
    custom_properties: CustomProperties,
) -> ChatOpenAIConfiguration:
    """
    Creates a ChatOpenAI configuration with logging enabled
    """
    default_headers = get_default_helicone_headers(
        helicone_api_key,
        account_address,
        environment_name,
        start_agent_request,
        custom_properties,
    )

    return ChatOpenAIConfiguration(
        model=model,
        api_key=api_key,
        configuration={
            "base_url": helicone_base_logging_url,
            "default_headers": default_headers,
        },
    )


def with_openai(
    api_key: str,
    helicone_api_key: str,
    helicone_base_logging_url: str,
    account_address: str,
    environment_name: str,
    start_agent_request: StartAgentRequest,
    custom_properties: CustomProperties,
) -> OpenAIConfiguration:
    """
    Creates an OpenAI client configuration with logging enabled
    """
    default_headers = get_default_helicone_headers(
        helicone_api_key,
        account_address,
        environment_name,
        start_agent_request,
        custom_properties,
    )

    return OpenAIConfiguration(
        api_key=api_key,
        base_url=helicone_base_logging_url,
        default_headers=default_headers,
    )


class ObservabilityAPI(BasePaymentsAPI):
    """
    The ObservabilityAPI class provides methods to wrap API calls with Helicone logging
    """

    def __init__(self, options: PaymentOptions):
        super().__init__(options)

        # TODO: For testing purposes only. Remove once helicone is deployed to staging
        # Get Helicone API key from environment variable and override the base class property
        import os

        self.helicone_api_key = os.getenv("HELICONE_API_KEY") or self.helicone_api_key

        self.helicone_base_logging_url = urljoin(
            self.environment.helicone_url, "jawn/v1/gateway/oai/v1"
        )
        self.helicone_manual_logging_url = urljoin(
            self.environment.helicone_url, "jawn/v1/trace/custom/v1/log"
        )

    @classmethod
    def get_instance(cls, options: PaymentOptions) -> "ObservabilityAPI":
        """
        This method is used to create a singleton instance of the ObservabilityAPI class.
        """
        return cls(options)

    async def with_manual_logging(
        self,
        agent_name: str,
        payload_config: HeliconePayloadConfig,
        operation: Callable[[], Awaitable[T]],
        result_extractor: Callable[[T], R],
        usage_calculator: Callable[[T], UsageDetails],
        response_id_prefix: str,
        start_agent_request: StartAgentRequest,
        custom_properties: CustomProperties,
    ) -> R:
        """
        Wraps an async operation with manual logging
        """
        return await with_manual_logging(
            agent_name,
            payload_config,
            operation,
            result_extractor,
            usage_calculator,
            response_id_prefix,
            self.helicone_api_key,
            self.helicone_manual_logging_url,
            self.account_address,
            self.environment_name,
            start_agent_request,
            custom_properties,
        )

    def with_langchain(
        self,
        model: str,
        api_key: str,
        start_agent_request: StartAgentRequest,
        custom_properties: CustomProperties,
    ) -> ChatOpenAIConfiguration:
        """
        Creates a ChatOpenAI configuration with logging enabled
        """
        return with_langchain(
            model,
            api_key,
            self.helicone_api_key,
            self.helicone_base_logging_url,
            self.account_address,
            self.environment_name,
            start_agent_request,
            custom_properties,
        )

    def with_openai(
        self,
        api_key: str,
        start_agent_request: StartAgentRequest,
        custom_properties: CustomProperties,
    ) -> OpenAIConfiguration:
        """
        Creates an OpenAI client configuration with logging enabled
        """
        return with_openai(
            api_key,
            self.helicone_api_key,
            self.helicone_base_logging_url,
            self.account_address,
            self.environment_name,
            start_agent_request,
            custom_properties,
        )

    def calculate_image_usage(self, pixels: int) -> UsageDetails:
        """Helper function to calculate usage for image operations based on pixels"""
        return calculate_image_usage(pixels)

    def calculate_video_usage(self) -> UsageDetails:
        """Helper function to calculate usage for video operations (typically 1 token)"""
        return calculate_video_usage()

    def calculate_song_usage(self, tokens: int) -> UsageDetails:
        """Helper function to calculate usage for song operations based on tokens/quota"""
        return calculate_song_usage(tokens)

    def calculate_dummy_song_usage(self) -> UsageDetails:
        """Helper function to calculate usage for dummy song operations"""
        return calculate_dummy_song_usage()

    def create_helicone_payload(self, config: HeliconePayloadConfig) -> Dict[str, Any]:
        """Creates a standardized Helicone payload for API logging"""
        return create_helicone_payload(config)

    def create_helicone_response(
        self, config: HeliconeResponseConfig
    ) -> Dict[str, Any]:
        """Creates a standardized Helicone response for API logging"""
        return create_helicone_response(config)
