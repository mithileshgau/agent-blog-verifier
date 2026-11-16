"""One good post, one post per planted trap, and the v3 regressions.

    python3 -m unittest discover -s tests -v
"""
import datetime, json, os, sys, tempfile, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import verify  # noqa: E402

NOW = datetime.datetime(2026, 11, 15)
U = {"mem": "https://news.test/memory", "tools": "https://news.test/tools",
     "evals": "https://news.test/evals", "dupe": "https://news.test/memory-2",
     "old": "https://news.test/old"}
FEED = [
    {"id": 1, "topic": "agent memory", "score": 90, "url": U["mem"],
     "published_at": "2026-11-13T00:00:00Z", "title": "Agent memory gets cheaper",
     "summary": "A memory store cut costs by 40%."},
    {"id": 2, "topic": "tool calling", "score": 80, "url": U["tools"],
     "published_at": "2026-11-12T00:00:00Z", "title": "Parallel tool calling ships",
     "summary": "Parallel calls land in the SDK.", "body": "Latency fell to 120 ms."},
    {"id": 3, "topic": "agent evals", "score": 70, "url": U["evals"],
     "published_at": "2026-11-11T00:00:00Z", "title": "An eval suite with 500 tasks",
     "summary": "The suite covers 500 tasks."},
    # trap: duplicate topic, lower score
    {"id": 4, "topic": "agent memory", "score": 60, "url": U["dupe"],
     "published_at": "2026-11-14T00:00:00Z", "title": "Memory, again",
     "summary": "Another memory post."},
    # trap: high score but older than 7 days; a fact lives outside title/summary
    {"id": 5, "topic": "agent funding", "score": 99, "url": U["old"],
     "published_at": "2026-10-01T00:00:00Z", "title": "A lab raised $210M",
     "summary": "Funding news.", "body": "It now serves 3400 customers."},
    # trap: no URL, and it shares a top-3 topic on purpose
    {"id": 6, "topic": "agent memory", "score": 95, "url": None,
     "published_at": "2026-11-14T00:00:00Z",
     "title": "Forum thread on memory leaks in long agent runs",
     "summary": "Users report leaks after 72 hours."},
    # trap: banned word in a feed title
    {"id": 7, "topic": "agent hype", "score": 10, "url": "https://news.test/hype",
     "published_at": "2026-11-13T00:00:00Z", "title": "A synergy of agents",
     "summary": "Low score."},
]
BANNED = "synergy\ndelve\n"
META = {"topics": ["agent memory", "tool calling", "agent evals"],
        "source_urls": [U["mem"], U["tools"], U["evals"]]}


def filler(tag, n):
    """n distinct words, so no 6-gram repeats."""
    return " ".join(f"{tag}{i}" for i in range(n))


def post(sections=None, intro=None, extra=""):
    sections = sections or [
        ("Agent memory", f"A memory store cut costs by 40% ([source]({U['mem']})). "),
        ("Tool calling", f"Parallel calls landed, and latency fell to 120 ms ([source]({U['tools']})). "),
        ("Agent evals", f"A new suite covers 500 tasks ([source]({U['evals']})). "),
    ]
    md = "# Three agent topics this week\n\n"
    md += (intro if intro is not None else "This week three topics led the feed by score. "
           + filler("intro", 30)) + "\n"
    for i, (head, text) in enumerate(sections):
        md += f"\n## {head}\n\n{text}{filler('s%d' % i, 190)}\n"
    return md + extra


class VerifyTest(unittest.TestCase):
    def check(self, md, meta=META):
        d = tempfile.mkdtemp()
        out = os.path.join(d, "output"); os.makedirs(out)
        open(os.path.join(out, "blog.md"), "w").write(md)
        json.dump(meta, open(os.path.join(out, "meta.json"), "w"))
        json.dump(FEED, open(os.path.join(d, "feed.json"), "w"))
        open(os.path.join(d, "banned.txt"), "w").write(BANNED)
        r = verify.run(out, os.path.join(d, "feed.json"), os.path.join(d, "banned.txt"), NOW)
        return r.verdict, {c["id"] for c in r.rows if c["result"] == "fail"}

    def assertOutcome(self, md, verdict, failed=(), meta=META):
        got, fails = self.check(md, meta)
        self.assertEqual(got, verdict, fails)
        self.assertTrue(set(failed) <= fails, fails)
        return fails

    # good post -------------------------------------------------------------
    def test_good_post_passes(self):
        self.assertEqual(self.assertOutcome(post(), "pass"), set())

    # planted traps ---------------------------------------------------------
    def test_stale_post_cited(self):
        md = post(extra=f"\nOne lab also raised money ([source]({U['old']})).\n")
        self.assertOutcome(md, "fail", {"no_stale_sources"})

    def test_stale_fact_without_link(self):
        self.assertOutcome(post(extra="\nOne lab raised $210 million.\n"), "fail", {"no_stale_facts"})

    def test_stale_fact_outside_title_and_summary(self):
        self.assertOutcome(post(extra="\nIt serves 3,400 customers.\n"), "fail", {"no_stale_facts"})

    def test_duplicate_topic_not_merged(self):
        meta = dict(META, topics=["agent memory", "agent memory", "tool calling"])
        self.assertOutcome(post(), "fail", {"no_duplicate_topic"}, meta)

    def test_urlless_post_named_in_body(self):
        md = post(extra="\nSee the forum thread on memory leaks in long agent runs.\n")
        self.assertOutcome(md, "fail", {"no_urlless_source"})

    def test_urlless_post_fact_used(self):
        self.assertOutcome(post(extra="\nLeaks appear after 72 hours.\n"), "fail", {"no_urlless_source"})

    def test_urlless_post_cited_without_link(self):
        md = post(extra="\n- Memory leak thread (no link available)\n")
        self.assertOutcome(md, "fail", {"no_urlless_source"})

    def test_urlless_post_in_meta(self):
        meta = dict(META, sources=[{"id": 6, "title": "Forum thread"}])
        self.assertOutcome(post(), "fail", {"no_urlless_source"}, meta)

    def test_urlless_post_sharing_top_topic_is_not_flagged(self):
        got, fails = self.check(post())
        self.assertNotIn("no_urlless_source", fails)

    def test_banned_word_copied_from_feed(self):
        md = post(extra="\nThe week showed a synergy of agents.\n")
        self.assertOutcome(md, "fail", {"no_banned_words"})

    # v3: inline links and section classification ----------------------------
    def test_topic_section_without_link_fails(self):
        md = post([("Agent memory", "A memory store cut costs by 40%. "),
                   ("Tool calling", f"Parallel calls ([source]({U['tools']})). "),
                   ("Agent evals", f"500 tasks ([source]({U['evals']})). ")])
        self.assertOutcome(md, "fail", {"section_has_feed_link"})

    def test_sources_list_is_a_warning(self):
        md = post(extra=f"\n## Sources\n\n- [Memory]({U['mem']})\n")
        self.assertOutcome(md, "partial", {"no_sources_list"})

    def test_overview_and_summary_headings_are_topics(self):
        md = post([("Agent memory: an overview", f"Costs fell 40% ([source]({U['mem']})). "),
                   ("Tool calling summary", f"Parallel calls ([source]({U['tools']})). "),
                   ("Agent evals", f"500 tasks ([source]({U['evals']})). ")])
        self.assertOutcome(md, "pass")

    def test_closing_section_by_position_is_a_warning(self):
        secs = [("Agent memory", f"Costs fell 40% ([source]({U['mem']})). "),
                ("Tool calling", f"Parallel calls ([source]({U['tools']})). "),
                ("Agent evals", f"500 tasks ([source]({U['evals']})). ")]
        md = post(secs, extra="\n## The common thread\n\nAll three point the same way.\n")
        self.assertOutcome(md, "partial", {"no_extra_sections"})

    def test_intro_section_counts_as_intro(self):
        secs = [("Introduction", "This week three topics led the feed. " + filler("i", 30) + " "),
                ("Agent memory", f"Costs fell 40% ([source]({U['mem']})). "),
                ("Tool calling", f"Parallel calls ([source]({U['tools']})). "),
                ("Agent evals", f"500 tasks ([source]({U['evals']})). ")]
        got, fails = self.check(post(secs, intro=""))
        self.assertNotIn("has_intro", fails)
        self.assertNotIn("section_count", fails)
        self.assertIn("no_extra_sections", fails)

    def test_selftest_runs(self):
        verify.selftest()


if __name__ == "__main__":
    unittest.main()
