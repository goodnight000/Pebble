import os
import sys
import unittest

sys.path.insert(0, os.path.abspath('ai_news'))

from app.features.compute import build_features
from app.models import EventType


class OfficialReleaseDetectionTests(unittest.TestCase):
    def test_detects_official_model_release_without_title_release_keywords(self):
        event_type, topics, entities, _ = build_features(
            title='Introducing GPT-5.4',
            text=(
                'Introducing GPT-5.4, OpenAI\'s most capable and efficient frontier model '
                'for professional work, with state-of-the-art coding, computer use, '
                'tool search, and 1M-token context.'
            ),
            source_kind='rss',
            url='https://openai.com/index/gpt-5-4/',
            source_name='OpenAI Blog',
        )
        self.assertEqual(event_type, EventType.MODEL_RELEASE)
        self.assertGreaterEqual(topics.get('llms', 0.0), 0.5)
        self.assertIn('OpenAI', entities)

    def test_does_not_promote_generic_official_post_to_model_release(self):
        event_type, topics, entities, _ = build_features(
            title='Ensuring AI use in education leads to opportunity',
            text='OpenAI shares lessons learned from education deployments and adoption programs.',
            source_kind='rss',
            url='https://openai.com/index/education-opportunity/',
            source_name='OpenAI Blog',
        )
        self.assertNotEqual(event_type, EventType.MODEL_RELEASE)
        self.assertIn('OpenAI', entities)


if __name__ == '__main__':
    unittest.main()
