import os
import sys
import unittest

sys.path.insert(0, os.path.abspath('ai_news'))

from app.scoring.importance import GlobalScoreInputs, compute_global_score_v2


class ScoreCalibrationTests(unittest.TestCase):
    def test_official_model_release_scores_ninety_plus(self):
        score, _ = compute_global_score_v2(
            GlobalScoreInputs(
                source_authority=1.0,
                event_type='MODEL_RELEASE',
                entities={'OpenAI': 1.0},
                independent_sources=1,
                raw_item=type('Raw', (), {'social_hn_points': 0, 'social_reddit_upvotes': 0, 'social_github_stars': 0})(),
                age_hours=1.0,
                articles_in_cluster=1,
                cluster_age_hours=1.0,
                novelty_sim=0.0,
                recent_max_score=0.0,
                primary_entity='OpenAI',
                session=None,
                source_kind='rss',
                text='Frontier model with coding, reasoning, tool use, and 1M-token context.',
                funding_amount_usd=None,
                final_url='https://openai.com/index/gpt-5-4/',
                source_names=['OpenAI Blog'],
                content_type='news',
            )
        )
        self.assertGreaterEqual(score, 90.0)

    def test_generic_other_story_stays_well_below_official_release(self):
        score, _ = compute_global_score_v2(
            GlobalScoreInputs(
                source_authority=0.65,
                event_type='OTHER',
                entities={},
                independent_sources=1,
                raw_item=type('Raw', (), {'social_hn_points': 0, 'social_reddit_upvotes': 0, 'social_github_stars': 0})(),
                age_hours=2.0,
                articles_in_cluster=1,
                cluster_age_hours=2.0,
                novelty_sim=0.3,
                recent_max_score=0.0,
                primary_entity=None,
                session=None,
                source_kind='hn',
                text='An opinion post about AI trends.',
                funding_amount_usd=None,
                final_url='https://news.ycombinator.com/item?id=1',
                source_names=['Hacker News'],
                content_type='news',
            )
        )
        self.assertLess(score, 45.0)


if __name__ == '__main__':
    unittest.main()
