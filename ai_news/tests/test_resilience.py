import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.abspath("ai_news"))

from app.api import routes_api
from app.features.funding import parse_funding_amount


class ResilienceTests(unittest.TestCase):
    def test_funding_parser_ignores_trailing_punctuation(self):
        text = "Benchmark costs $2.29. Another broken token is $."
        self.assertEqual(parse_funding_amount(text), 2)

    def test_funding_parser_skips_invalid_amount_tokens(self):
        text = "Noise tokens like $. and USD . should not crash parsing."
        self.assertIsNone(parse_funding_amount(text))

    def test_decode_embedding_or_none_rejects_invalid_buffer(self):
        self.assertIsNone(routes_api._decode_embedding_or_none(b"."))

    def test_decode_embedding_or_none_returns_vector_for_valid_buffer(self):
        emb = np.ones(384, dtype=np.float32)
        decoded = routes_api._decode_embedding_or_none(emb.tobytes())
        self.assertIsNotNone(decoded)
        self.assertEqual(decoded.shape, (384,))


if __name__ == "__main__":
    unittest.main()
