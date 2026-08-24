from __future__ import annotations

import unittest
from routes.testing import (
    EvaluateRealDataRequest,
    EvaluateDbRequest,
    SyncLabelsRequest,
    _run_labeled_evaluation,
)


class TestingRouteTests(unittest.IsolatedAsyncioTestCase):
    def test_evaluate_real_data_request_optional_labels(self) -> None:
        # Default with no arguments should allow None
        req = EvaluateRealDataRequest()
        self.assertIsNone(req.labeled_addresses)

        # Custom explicit addresses
        req2 = EvaluateRealDataRequest(
            labeled_addresses=[
                {"address": "0x8589427373d6d84e98730d7795d8f6f8731fda16", "label": "BAD"},
                {"address": "0x28c6c06298d514db089934071355e5743bf21d60", "label": "CLEAN"},
            ]
        )
        self.assertEqual(len(req2.labeled_addresses), 2)

    def test_evaluate_db_request_defaults(self) -> None:
        req = EvaluateDbRequest()
        self.assertIsNone(req.label)
        self.assertIsNone(req.category)
        self.assertEqual(req.limit, 1000)

        req_filtered = EvaluateDbRequest(label="BAD", category="sanctioned_mixer", limit=50)
        self.assertEqual(req_filtered.label, "BAD")
        self.assertEqual(req_filtered.category, "sanctioned_mixer")
        self.assertEqual(req_filtered.limit, 50)


if __name__ == "__main__":
    unittest.main()
