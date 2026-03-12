import os
import sys
import unittest

os.environ.setdefault('DATABASE_URL', 'sqlite:///./test-editorial-taxonomy.db')

sys.path.insert(0, os.path.abspath('ai_news'))

from app.api.card_taxonomy import build_topic_chips, category_for


class EditorialCardTaxonomyTests(unittest.TestCase):
    def test_model_release_maps_to_product(self):
        category = category_for(
            'MODEL_RELEASE',
            {
                'llms': 0.72,
                'enterprise_apps': 0.18,
            },
        )

        self.assertEqual(category, 'Product')

    def test_security_incident_maps_to_security(self):
        category = category_for(
            'SECURITY_INCIDENT',
            {
                'open_source': 0.52,
                'hardware_chips': 0.11,
            },
        )

        self.assertEqual(category, 'Security')

    def test_unclear_story_uses_general_instead_of_trend(self):
        category = category_for(
            'OTHER',
            {
                'llms': 0.14,
                'multimodal': 0.12,
            },
        )

        self.assertEqual(category, 'General')

    def test_build_tags_returns_four_semantic_topic_chips(self):
        tags = build_topic_chips(
            'Research',
            'RESEARCH_PAPER',
            {
                'llms': 0.44,
                'agents': 0.35,
                'enterprise_apps': 0.31,
                'research_methods': 0.29,
                'audio_speech': 0.24,
            },
            title='Conversational diagnostic AI in a real-world clinical study',
            summary='Google Research studies conversational diagnostic AI in a clinical setting with physician comparison data.',
            source_name='Google AI Blog',
        )

        self.assertEqual(tags, ['Healthcare', 'LLMs', 'Agents', 'Science'])

    def test_build_tags_does_not_repeat_category_meaning(self):
        tags = build_topic_chips(
            'Open Source',
            'OPEN_SOURCE_RELEASE',
            {
                'open_source': 0.73,
                'agents': 0.41,
                'enterprise_apps': 0.25,
            },
            title='Open-source coding agent framework adds eval harness',
            summary='The release targets developer workflows and repository automation.',
            source_name='GitHub Releases',
        )

        self.assertEqual(tags, ['Agents', 'Coding', 'Developer Tools', 'Enterprise'])


if __name__ == '__main__':
    unittest.main()
