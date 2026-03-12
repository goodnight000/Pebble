import unittest


class TestArxivCybersecurity(unittest.TestCase):
    def test_cs_cr_in_arxiv_cats(self):
        from app.ingestion.arxiv import ARXIV_CATS
        self.assertIn("cs.CR", ARXIV_CATS)

    def test_original_cats_preserved(self):
        from app.ingestion.arxiv import ARXIV_CATS
        for cat in ["cs.LG", "cs.CL", "cs.AI", "cs.RO", "stat.ML", "cs.CV", "cs.SE", "eess.AS"]:
            self.assertIn(cat, ARXIV_CATS)


class TestHackerNewsCybersecurity(unittest.TestCase):
    def test_hn_queries_module_constant(self):
        from app.ingestion.hackernews import HN_QUERIES
        self.assertIsInstance(HN_QUERIES, list)

    def test_cybersecurity_queries_present(self):
        from app.ingestion.hackernews import HN_QUERIES
        for term in ["cybersecurity", "vulnerability", "CVE", "zero-day", "ransomware"]:
            self.assertIn(term, HN_QUERIES)

    def test_original_queries_preserved(self):
        from app.ingestion.hackernews import HN_QUERIES
        for term in ["AI", "LLM", "GPT", "machine learning", "OpenAI", "Anthropic", "Claude"]:
            self.assertIn(term, HN_QUERIES)


class TestRedditCybersecurity(unittest.TestCase):
    def test_netsec_in_subreddits(self):
        from app.ingestion.reddit import SUBREDDITS
        self.assertIn("netsec", SUBREDDITS)

    def test_cybersecurity_in_subreddits(self):
        from app.ingestion.reddit import SUBREDDITS
        self.assertIn("cybersecurity", SUBREDDITS)

    def test_original_subreddits_preserved(self):
        from app.ingestion.reddit import SUBREDDITS
        for sub in ["MachineLearning", "LocalLLaMA", "OpenAI", "singularity", "artificial", "StableDiffusion", "ChatGPT", "ClaudeAI"]:
            self.assertIn(sub, SUBREDDITS)


if __name__ == "__main__":
    unittest.main()
