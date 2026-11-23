"""Provider-neutral contract tests for RT-06P."""
from __future__ import annotations

import unittest

from runtime.lab.enterprise_range.harness import EnterpriseLiveRangeHarness
from runtime.lab.range_provider import (
    RangeProviderError,
    validate_provider_contract,
)


class TestRangeProviderContract(unittest.TestCase):
    def test_existing_loopback_harness_satisfies_contract(self) -> None:
        provider = EnterpriseLiveRangeHarness()
        validate_provider_contract(provider)
        self.assertFalse(provider.capabilities.external_infrastructure)

    def test_incomplete_provider_fails_closed(self) -> None:
        class IncompleteProvider:
            pass

        with self.assertRaises(RangeProviderError) as ctx:
            validate_provider_contract(IncompleteProvider())
        self.assertEqual(ctx.exception.code, "RANGE_PROVIDER_CONTRACT_INVALID")

    def test_capabilities_are_mandatory(self) -> None:
        class MethodsOnly:
            start = stop = reset_all = health_check_all = lambda self: None
            block_route = unblock_route = lambda self, *args: None
            dispatch_bounded_request = lambda self, *args, **kwargs: {}

        with self.assertRaises(RangeProviderError) as ctx:
            validate_provider_contract(MethodsOnly())
        self.assertEqual(ctx.exception.code, "RANGE_PROVIDER_CAPABILITIES_MISSING")


if __name__ == "__main__":
    unittest.main()
