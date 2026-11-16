"""The shipped feed.json holds every planted trap and a stable top 3."""
import datetime, json, os, sys, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import verify  # noqa: E402

FEED = json.load(open(os.path.join(ROOT, "feed.json")))
BANNED = [l.strip() for l in open(os.path.join(ROOT, "banned_words.txt"))
          if l.strip() and not l.startswith("#")]
REF = datetime.datetime(2026, 11, 16)
TOP3 = ["agent memory", "tool calling", "agent evals"]


class FeedTest(unittest.TestCase):
    def test_shape(self):
        self.assertEqual(len(FEED), 30)
        for p in FEED:
            self.assertEqual(set(p), {"id", "topic", "score", "url", "published_at", "title", "summary"})
            if p["url"]:
                self.assertTrue(p["url"].startswith("https://agentnews.example/"))
        self.assertEqual(len({p["url"] for p in FEED if p["url"]}), 29)

    def test_top3_stable_across_reference_dates(self):
        for day in (15, 16, 17, 18):
            got = [p["topic"] for p in verify.expected_topics(FEED, datetime.datetime(2026, 11, day))]
            self.assertEqual(got, TOP3, day)

    def test_top3_same_by_sum(self):
        sums = {}
        for p in verify.fresh(FEED, REF):
            if p["url"]:
                sums[p["topic"]] = sums.get(p["topic"], 0) + p["score"]
        self.assertEqual(sorted(sorted(sums, key=lambda t: -sums[t])[:3]), sorted(TOP3))

    def test_stale_high_scorers(self):
        fresh = verify.fresh(FEED, REF)
        stale = [p for p in FEED if p not in fresh]
        best_fresh = max(p["score"] for p in fresh if p["url"])
        self.assertEqual(len([p for p in stale if p["score"] > best_fresh]), 3)
        for p in stale:
            self.assertTrue(verify.numbers(verify.post_text(p))
                            - verify.numbers(" ".join(verify.post_text(q) for q in fresh)))

    def test_duplicate_topics_in_top3(self):
        for topic in ("agent memory", "tool calling"):
            self.assertGreater(len([p for p in FEED if p["topic"] == topic and p["url"]]), 1)

    def test_urlless_post_shares_top_topic(self):
        nourl = [p for p in FEED if not p["url"]]
        self.assertEqual(len(nourl), 1)
        p = nourl[0]
        self.assertIn(p["topic"], TOP3)
        self.assertEqual(p["score"], max(q["score"] for q in verify.fresh(FEED, REF)))
        linked = " ".join(verify.post_text(q) for q in FEED if q["url"])
        self.assertTrue(verify.numbers(verify.post_text(p)) - verify.numbers(linked))

    def test_banned_words_in_titles(self):
        hit = [p["id"] for p in FEED if any(w in p["title"].lower() for w in BANNED)]
        self.assertGreaterEqual(len(hit), 3)

    def test_top3_on_different_pages(self):
        pages = {}
        for i, p in enumerate(FEED):
            if p["topic"] in TOP3 and p["url"]:
                pages.setdefault(p["topic"], set()).add(i // 10 + 1)
        self.assertIn(3, pages["agent evals"])


if __name__ == "__main__":
    unittest.main()
