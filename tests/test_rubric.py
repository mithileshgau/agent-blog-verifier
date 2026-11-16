"""rubric.py builds the judge input without calling the API."""
import os, sys, types, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
try:
    import rubric  # needs anthropic + pydantic
except ImportError:  # pragma: no cover
    rubric = None


@unittest.skipIf(rubric is None, "anthropic/pydantic not installed")
class RubricTest(unittest.TestCase):
    def test_judge_is_frozen(self):
        self.assertEqual(rubric.JUDGE_MODEL, "claude-sonnet-5-5")
        self.assertEqual(rubric.JUDGE_RUNS, 3)

    def test_task_has_prompt_date_and_banned_words(self):
        task = rubric.task_text("2026-11-16T00:00:00Z")
        self.assertTrue(task.startswith("Today's date for this run: 2026-11-16"))
        self.assertIn("A topic's score is its highest-scoring post", task)
        self.assertIn("synergy", task)
        self.assertNotIn("[see banned_words.txt]", task)

    def test_judge_sees_feed_post_and_task(self):
        c = rubric.judge_content(rubric.judge_prompt(), "FEEDX", "POSTX", "TASKX")
        self.assertIn("(C) TASK", rubric.judge_prompt())
        for part in ("<feed>\nFEEDX", "<post>\nPOSTX", "<task>\nTASKX"):
            self.assertIn(part, c)

    def test_majority(self):
        self.assertEqual(rubric.majority([2, 2, 1]), 2)
        self.assertEqual(rubric.majority([0, 1, 2]), 1)


if __name__ == "__main__":
    unittest.main()
