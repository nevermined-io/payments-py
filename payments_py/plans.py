"""
Utility functions for creating and managing payment plans.
"""

from payments_py.common.types import (
    PlanCreditsConfig,
    PlanPriceConfig,
    PlanRedemptionType,
    Address,
)
from payments_py.environments import ZeroAddress
from payments_py.utils import is_ethereum_address

# Duration constants in seconds
ONE_DAY_DURATION = 86_400  # 24 * 60 * 60 seconds
ONE_WEEK_DURATION = 604_800  # 7 * 24 * 60 * 60 seconds
ONE_MONTH_DURATION = (
    2_629_746  # (365.25 days/year ÷ 12 months/year) × 24 × 60 × 60 ≈ 2,629,746 seconds
)
ONE_YEAR_DURATION = 31_557_600  # 365.25 * 24 * 60 * 60 seconds


def get_fiat_price_config(amount: int, receiver: Address) -> PlanPriceConfig:
    """
    Get a fixed fiat price configuration for a plan.

    Args:
        amount: The amount in the smallest unit of the fiat currency
        receiver: The address that will receive the payment

    Returns:
        A PlanPriceConfig object configured for fiat payments

    Raises:
        ValueError: If the receiver address is not a valid Ethereum address
    """
    if not is_ethereum_address(receiver):
        raise ValueError(f"Receiver address {receiver} is not a valid Ethereum address")
    return PlanPriceConfig(
        token_address=ZeroAddress,
        amounts=[amount],
        receivers=[receiver],
        contract_address=ZeroAddress,
        fee_controller=ZeroAddress,
        external_price_address=ZeroAddress,
        template_address=ZeroAddress,
        is_crypto=False,
    )


def get_crypto_price_config(
    amount: int, receiver: Address, token_address: Address = ZeroAddress
) -> PlanPriceConfig:
    """
    Get a fixed crypto price configuration for a plan.

    Args:
        amount: The amount in the smallest unit of the token
        receiver: The address that will receive the payment
        token_address: The address of the token to use for payment (defaults to native token)

    Returns:
        A PlanPriceConfig object configured for crypto payments

    Raises:
        ValueError: If the receiver address is not a valid Ethereum address
    """
    if not is_ethereum_address(receiver):
        raise ValueError(f"Receiver address {receiver} is not a valid Ethereum address")
    return PlanPriceConfig(
        token_address=token_address,
        amounts=[amount],
        receivers=[receiver],
        contract_address=ZeroAddress,
        fee_controller=ZeroAddress,
        external_price_address=ZeroAddress,
        template_address=ZeroAddress,
        is_crypto=True,
    )


def get_erc20_price_config(
    amount: int, token_address: Address, receiver: Address
) -> PlanPriceConfig:
    """
    Get a fixed ERC20 token price configuration for a plan.

    Args:
        amount: The amount in the smallest unit of the ERC20 token
        token_address: The address of the ERC20 token
        receiver: The address that will receive the payment

    Returns:
        A PlanPriceConfig object configured for ERC20 token payments
    """
    return get_crypto_price_config(amount, receiver, token_address)


def get_free_price_config() -> PlanPriceConfig:
    """
    Get a free price configuration for a plan.

    Returns:
        A PlanPriceConfig object configured for free plans
    """
    return PlanPriceConfig(
        token_address=ZeroAddress,
        amounts=[],
        receivers=[],
        contract_address=ZeroAddress,
        fee_controller=ZeroAddress,
        external_price_address=ZeroAddress,
        template_address=ZeroAddress,
        is_crypto=True,
    )


def get_native_token_price_config(amount: int, receiver: Address) -> PlanPriceConfig:
    """
    Get a fixed native token price configuration for a plan.

    Args:
        amount: The amount in the smallest unit of the native token
        receiver: The address that will receive the payment

    Returns:
        A PlanPriceConfig object configured for native token payments
    """
    return get_crypto_price_config(amount, receiver, ZeroAddress)


def get_expirable_duration_config(duration_of_plan: int) -> PlanCreditsConfig:
    """
    Get an expirable duration configuration for a plan.

    Args:
        duration_of_plan: The duration of the plan in seconds

    Returns:
        A PlanCreditsConfig object configured for expirable duration
    """
    return PlanCreditsConfig(
        is_redemption_amount_fixed=False,
        redemption_type=PlanRedemptionType.ONLY_OWNER,
        proof_required=False,
        duration_secs=duration_of_plan,
        amount="1",
        min_amount=1,
        max_amount=1,
    )


def get_non_expirable_duration_config() -> PlanCreditsConfig:
    """
    Get a non-expirable duration configuration for a plan.

    Returns:
        A PlanCreditsConfig object configured for non-expirable duration
    """
    return get_expirable_duration_config(0)


def get_fixed_credits_config(
    credits_granted: int, credits_per_request: int = 1
) -> PlanCreditsConfig:
    """
    Get a fixed credits configuration for a plan.

    Args:
        credits_granted: The total number of credits granted
        credits_per_request: The number of credits consumed per request (default: 1)

    Returns:
        A PlanCreditsConfig object configured for fixed credits
    """
    return PlanCreditsConfig(
        is_redemption_amount_fixed=True,
        redemption_type=PlanRedemptionType.ONLY_OWNER,
        proof_required=False,
        duration_secs=0,
        amount=str(credits_granted),
        min_amount=credits_per_request,
        max_amount=credits_per_request,
    )


def get_dynamic_credits_config(
    credits_granted: int,
    min_credits_per_request: int = 1,
    max_credits_per_request: int = 1,
) -> PlanCreditsConfig:
    """
    Get a dynamic credits configuration for a plan.

    Args:
        credits_granted: The total number of credits granted
        min_credits_per_request: The minimum number of credits consumed per request (default: 1)
        max_credits_per_request: The maximum number of credits consumed per request (default: 1)

    Returns:
        A PlanCreditsConfig object configured for dynamic credits
    """
    return PlanCreditsConfig(
        is_redemption_amount_fixed=False,
        redemption_type=PlanRedemptionType.ONLY_OWNER,
        proof_required=False,
        duration_secs=0,
        amount=str(credits_granted),
        min_amount=min_credits_per_request,
        max_amount=max_credits_per_request,
    )


def set_redemption_type(
    credits_config: PlanCreditsConfig, redemption_type: PlanRedemptionType
) -> PlanCreditsConfig:
    """
    Set the redemption type for a credits configuration.

    Args:
        credits_config: The credits configuration to modify
        redemption_type: The new redemption type

    Returns:
        A new PlanCreditsConfig with the updated redemption type
    """
    return PlanCreditsConfig(
        credits_type=credits_config.credits_type,
        redemption_type=redemption_type,
        proof_required=credits_config.proof_required,
        duration_secs=credits_config.duration_secs,
        amount=credits_config.amount,
        min_amount=credits_config.min_amount,
        max_amount=credits_config.max_amount,
    )


def set_proof_required(
    credits_config: PlanCreditsConfig, proof_required: bool = True
) -> PlanCreditsConfig:
    """
    Set whether proof is required for a credits configuration.

    Args:
        credits_config: The credits configuration to modify
        proof_required: Whether proof is required (default: True)

    Returns:
        A new PlanCreditsConfig with the updated proof requirement
    """
    return PlanCreditsConfig(
        credits_type=credits_config.credits_type,
        redemption_type=credits_config.redemption_type,
        proof_required=proof_required,
        duration_secs=credits_config.duration_secs,
        amount=credits_config.amount,
        min_amount=credits_config.min_amount,
        max_amount=credits_config.max_amount,
    )
