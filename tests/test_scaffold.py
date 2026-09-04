import unittest

from scripts.validation.validate_scaffold import validate


class ScaffoldIntegrationTests(unittest.TestCase):
    def test_validator_passes(self):
        self.assertEqual(validate(), [])


if __name__ == "__main__":
    unittest.main()
