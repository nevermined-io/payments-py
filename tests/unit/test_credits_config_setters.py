"""
Unit tests for credits configuration setter helpers.

Regression tests for https://github.com/nevermined-io/payments-py/issues/177:
``set_redemption_type`` and ``set_onchain_mirror`` previously referenced a
non-existent ``credits_type`` field, raising ``AttributeError`` on call.
"""

from payments_py.common.types import PlanRedemptionType
from payments_py.plans import (
    get_fixed_credits_config,
    get_dynamic_credits_config,
    set_redemption_type,
    set_onchain_mirror,
)


class TestSetRedemptionType:
    def test_updates_redemption_type_and_preserves_other_fields(self):
        original = get_fixed_credits_config(100, credits_per_request=2)
        assert original.redemption_type == PlanRedemptionType.ONLY_SUBSCRIBER

        updated = set_redemption_type(original, PlanRedemptionType.ONLY_OWNER)

        assert updated.redemption_type == PlanRedemptionType.ONLY_OWNER
        assert updated.is_redemption_amount_fixed == original.is_redemption_amount_fixed
        assert updated.onchain_mirror == original.onchain_mirror
        assert updated.duration_secs == original.duration_secs
        assert updated.amount == original.amount
        assert updated.min_amount == original.min_amount
        assert updated.max_amount == original.max_amount

    def test_returns_new_instance_without_mutating_input(self):
        original = get_fixed_credits_config(50)
        original_redemption = original.redemption_type

        updated = set_redemption_type(original, PlanRedemptionType.ONLY_OWNER)

        assert updated is not original
        assert original.redemption_type == original_redemption

    def test_preserves_nft_address(self):
        original = get_fixed_credits_config(100).model_copy(
            update={"nft_address": "0xdeadbeef"}
        )

        updated = set_redemption_type(original, PlanRedemptionType.ONLY_OWNER)

        assert updated.nft_address == "0xdeadbeef"


class TestSetOnchainMirror:
    def test_enables_mirror_by_default(self):
        original = get_dynamic_credits_config(
            credits_granted=100, min_credits_per_request=1, max_credits_per_request=5
        )
        assert original.onchain_mirror is False

        updated = set_onchain_mirror(original)

        assert updated.onchain_mirror is True

    def test_disables_mirror_when_explicit_false(self):
        original = get_fixed_credits_config(10)
        enabled = set_onchain_mirror(original, True)
        disabled = set_onchain_mirror(enabled, False)

        assert disabled.onchain_mirror is False

    def test_preserves_other_fields(self):
        original = get_dynamic_credits_config(
            credits_granted=200, min_credits_per_request=2, max_credits_per_request=8
        )

        updated = set_onchain_mirror(original, True)

        assert updated.is_redemption_amount_fixed == original.is_redemption_amount_fixed
        assert updated.redemption_type == original.redemption_type
        assert updated.duration_secs == original.duration_secs
        assert updated.amount == original.amount
        assert updated.min_amount == original.min_amount
        assert updated.max_amount == original.max_amount

    def test_returns_new_instance_without_mutating_input(self):
        original = get_fixed_credits_config(25)

        updated = set_onchain_mirror(original, True)

        assert updated is not original
        assert original.onchain_mirror is False

    def test_preserves_nft_address(self):
        original = get_fixed_credits_config(100).model_copy(
            update={"nft_address": "0xdeadbeef"}
        )

        updated = set_onchain_mirror(original, True)

        assert updated.nft_address == "0xdeadbeef"
