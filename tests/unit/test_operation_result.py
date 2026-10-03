import unittest
from classes.operation_result import OperationResult

class OperationResultTests(unittest.TestCase):
    def test_result_boolean_value_matches_status(self):
        self.assertTrue(OperationResult.success())
        self.assertFalse(OperationResult.failure(
            "TEST_ERROR",
            "Test Error",
            "Test failure",
        ))
