import unittest
from pathlib import Path


class AlembicPostgresCompatibilityTests(unittest.TestCase):
    def test_boolean_defaults_use_postgres_boolean_literals(self):
        root = Path(__file__).resolve().parents[1]
        for relative_path in (
            "alembic/versions/0002_algorithm_v2.py",
            "alembic/versions/0003_content_type.py",
        ):
            contents = (root / relative_path).read_text(encoding="utf-8")
            self.assertNotIn('sa.Boolean(), nullable=False, server_default=sa.text("0")', contents)
            self.assertNotIn('sa.Boolean(), nullable=False, server_default="0"', contents)


if __name__ == "__main__":
    unittest.main()
