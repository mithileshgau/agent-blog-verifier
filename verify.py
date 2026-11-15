#!/usr/bin/env python3
"""Deterministic checks for a blog-writing agent run.

Frozen once the sprint starts. Measures only - never tells an agent how to pass.

  python3 verify.py --output ./output --feed feed.json --banned banned_words.txt
  python3 verify.py --selftest          # prove it runs, no agent needed

Every check carries a failure tag so a FAIL localises the break, not just
lowers a score.
Exit 0 pass, 1 partial, 2 fail.
"""
import argparse, json, os, re, sys, datetime, collections

WORD_MIN, WORD_MAX, SECTIONS, TOPICS = 600, 800, 3, 3
FRESH_DAYS = 7

TAGS = ["misread_instruction", "wrong_tool_or_args", "lost_context",
        "looped_or_quit_early", "file_or_state_error", "auth_error",
        "said_done_but_failed", "framework_limitation"]

class R:
    def __init__(s): s.rows = []
    def add(s, cid, hard, tag, ok, detail=""):
        assert tag in TAGS, tag
        s.rows.append(dict(id=cid, hard=hard, tag=tag,
                           result="pass" if ok else "fail", detail=detail))
    @property
    def verdict(s):
        if any(r["result"] == "fail" and r["hard"] for r in s.rows): return "fail"
        if any(r["result"] == "fail" for r in s.rows): return "partial"
        return "pass"

def words(md):
    body = re.sub(r"```.*?```", " ", md, flags=re.S)
    body = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", body)
    body = re.sub(r"^#{1,6}\s*", "", body, flags=re.M)
    body = re.sub(r"[#*`>|_-]", " ", body)
    return [w for w in body.split() if any(c.isalnum() for c in w)]

def urls(md):
    out = set(re.findall(r"\]\((https?://[^)\s]+)\)", md))
    out |= set(re.findall(r"(?<![\(\]])\bhttps?://[^\s)<>\]]+", md))
    return {u.rstrip(".,;)") for u in out}

def norm(u):
    u = re.sub(r"^https?://(www\.)?", "", u.strip()).rstrip("/")
    return u.split("?")[0].lower()

def fresh(feed, now):
    out = []
    for p in feed:
        try: d = datetime.datetime.fromisoformat(p["published_at"].replace("Z", "+00:00"))
        except Exception: continue
        if (now - d.replace(tzinfo=None)).days <= FRESH_DAYS: out.append(p)
    return out

def expected_topics(feed, now):
    """Top 3 by score among posts that are fresh, have a URL, deduped by topic."""
    ok = [p for p in fresh(feed, now) if p.get("url")]
    best = {}
    for p in sorted(ok, key=lambda x: -x.get("score", 0)):
        t = p["topic"].strip().lower()
        if t not in best: best[t] = p
    return list(best.values())[:TOPICS]

def run(output_dir, feed_path, banned_path, now=None):
    now = now or datetime.datetime.utcnow()
    r = R()
    blog_p, meta_p = os.path.join(output_dir, "blog.md"), os.path.join(output_dir, "meta.json")

    have_blog, have_meta = os.path.isfile(blog_p), os.path.isfile(meta_p)
    r.add("files_exist", True, "file_or_state_error", have_blog and have_meta,
          f"blog.md={have_blog} meta.json={have_meta}")
    if not have_blog:
        return r
    md = open(blog_p, encoding="utf8", errors="ignore").read()
    feed = json.load(open(feed_path, encoding="utf8"))
    banned = [l.strip().lower() for l in open(banned_path, encoding="utf8")
              if l.strip() and not l.startswith("#")] if os.path.isfile(banned_path) else []

    meta = None
    if have_meta:
        try: meta = json.load(open(meta_p, encoding="utf8"))
        except Exception as e:
            r.add("meta_valid", True, "file_or_state_error", False, f"unparseable: {e}")
    if meta is not None:
        good = isinstance(meta, dict) and "topics" in meta and (
            "source_urls" in meta or "sources" in meta)
        r.add("meta_valid", True, "file_or_state_error", good,
              f"keys={list(meta)[:6]}")

    w = len(words(md))
    r.add("word_count", True, "misread_instruction", WORD_MIN <= w <= WORD_MAX,
          f"{w} words, want {WORD_MIN}-{WORD_MAX}")

    h1 = re.findall(r"^#\s+\S", md, flags=re.M)
    h2 = re.findall(r"^##\s+(.+)$", md, flags=re.M)
    body_h2 = [h for h in h2 if h.strip().lower() not in ("sources", "references")]
    r.add("has_title", True, "misread_instruction", len(h1) == 1, f"{len(h1)} H1")
    r.add("section_count", True, "misread_instruction", len(body_h2) == SECTIONS,
          f"{len(body_h2)} sections: {body_h2[:5]}")

    first = md.find("\n##")
    intro = words(md[md.find("\n", md.find("# ")) : first if first > 0 else len(md)])
    r.add("has_intro", True, "misread_instruction", len(intro) >= 30,
          f"{len(intro)} intro words")

    feed_urls = {norm(p["url"]) for p in feed if p.get("url")}
    used = {norm(u) for u in urls(md)}
    stray = sorted(used - feed_urls)
    r.add("links_from_feed", True, "said_done_but_failed", not stray,
          f"{len(stray)} off-feed: {stray[:3]}")
    r.add("has_sources", False, "misread_instruction",
          bool(re.search(r"^##\s*(sources|references)", md, re.I | re.M)), "")

    low = md.lower()
    hits = [b for b in banned if re.search(rf"\b{re.escape(b)}\b", low)]
    r.add("no_banned_words", True, "misread_instruction", not hits, f"{hits[:5]}")

    stale = {norm(p["url"]) for p in feed
             if p.get("url") and p not in fresh(feed, now)}
    used_stale = sorted(used & stale)
    r.add("no_stale_sources", True, "lost_context", not used_stale,
          f"cited {len(used_stale)} post(s) older than {FRESH_DAYS}d")

    nourl = [p for p in feed if not p.get("url")]
    r.add("no_urlless_source", True, "wrong_tool_or_args",
          not any(p["topic"].lower() in low for p in nourl),
          f"{len(nourl)} feed posts lack a URL")

    exp = expected_topics(feed, now)
    matched = [p for p in exp if p["topic"].lower() in low
               or norm(p["url"]) in used]
    r.add("topics_match_feed", True, "wrong_tool_or_args", len(matched) == len(exp),
          f"{len(matched)}/{len(exp)}: expected {[p['topic'] for p in exp]}")

    if meta and isinstance(meta.get("topics"), list):
        seen = [t.strip().lower() for t in meta["topics"] if isinstance(t, str)]
        r.add("no_duplicate_topic", True, "lost_context", len(set(seen)) == len(seen),
              f"meta topics={seen}")

    grams = collections.Counter()
    ws = [x.lower() for x in words(md)]
    for i in range(len(ws) - 5):
        grams[" ".join(ws[i:i + 6])] += 1
    dupes = [g for g, c in grams.items() if c > 1]
    r.add("no_repeated_6gram", False, "looped_or_quit_early", not dupes,
          f"{len(dupes)} repeated: {dupes[:2]}")

    extra = []
    for root, _, files in os.walk(output_dir):
        for f in files:
            if os.path.relpath(os.path.join(root, f), output_dir) not in ("blog.md", "meta.json"):
                extra.append(os.path.relpath(os.path.join(root, f), output_dir))
    r.add("scope_respected", False, "file_or_state_error", not extra,
          f"extra files in /output: {extra[:4]}")
    return r

# Aligned to the write-content skill's anti-slop list, which is the team
# standard. Add your own category terms to KEEP_WORDS so an anti-slop pass
# does not delete the vocabulary your product is named for.
TELL_WORDS = [
    "delve", "testament", "leverage", "utilize", "robust", "seamless",
    "pivotal", "multifaceted", "embark", "showcase", "streamline",
    "paramount", "culminate", "spearhead", "commence", "endeavor",
    "vibrant", "innovative",
]
TELL_PHRASES = [
    "it's worth noting", "it is worth noting", "in today's", "let's dive in",
    "in conclusion", "plays a crucial role", "plays a vital role",
    "plays a pivotal role", "it goes without saying", "in the realm of",
    "harness the power", "serves as", "the world of",
]
TRANSITIONS = ["moreover", "furthermore", "additionally", "in addition",
               "consequently", "notably", "importantly", "overall",
               "however", "essentially", "that said", "arguably"]
HEDGE_STACKS = [r"may\s+potentially", r"could\s+possibly", r"might\s+perhaps",
                r"can\s+potentially", r"seems?\s+to\s+suggest\s+that"]
BINARY = [r"it(?:'s| is) not (?:just )?\w+[,.]? it(?:'s| is)",
          r"not only \w+ but also"]


def run_tells(r, md):
    """Proxies for machine-written prose. All SOFT.

    These do NOT measure "was a human involved" - that is not verifiable. They
    measure the specific tells that make text read as generated. A human can
    fail them; a careful model can pass them. Read them as prose-quality
    signals, never as authorship evidence.
    """
    body = re.sub(r"```.*?```", " ", md, flags=re.S)
    body = re.sub(r"^#{1,6}.*$", "", body, flags=re.M)
    low = body.lower()
    wc = max(len(words(md)), 1)

    sents = [x for x in re.split(r"(?<=[.!?])\s+", body) if len(x.split()) >= 3]
    lens = [len(x.split()) for x in sents]
    if len(lens) >= 5:
        mean = sum(lens) / len(lens)
        sd = (sum((l - mean) ** 2 for l in lens) / len(lens)) ** 0.5
        r.add("tell_sentence_variance", False, "framework_limitation", sd >= 5.0,
              f"stdev {sd:.1f} words (want >=5; uniform length reads generated)")

    paras = [x for x in body.split("\n\n") if len(x.split()) >= 15]
    if len(paras) >= 3:
        pl = [len(x.split()) for x in paras]
        pm = sum(pl) / len(pl)
        psd = (sum((l - pm) ** 2 for l in pl) / len(pl)) ** 0.5
        r.add("tell_para_variance", False, "framework_limitation", psd >= 12.0,
              f"stdev {psd:.1f} words across {len(paras)} paragraphs")

    hits = [t for t in TELL_PHRASES if t in low]
    hits += [w for w in TELL_WORDS if re.search(rf"\b{w}\b", low)]
    r.add("tell_banned_vocab", False, "framework_limitation", len(hits) == 0,
          f"{len(hits)} found: {hits[:4]}")

    bin_hits = [b for b in BINARY if re.search(b, low)]
    r.add("tell_binary_contrast", False, "framework_limitation", not bin_hits,
          f"{len(bin_hits)} 'it is not X, it is Y' constructions")

    emd = body.count("\u2014") + body.count("\u2013")
    r.add("tell_dash_chains", False, "framework_limitation",
          emd / max(wc, 1) * 1000 <= 2, f"{emd} dashes, {emd/max(wc,1)*1000:.1f}/1000 words")

    tr = sum(len(re.findall(rf"\b{t}\b", low)) for t in TRANSITIONS)
    per100 = tr / wc * 100
    r.add("tell_transition_density", False, "framework_limitation", per100 <= 0.6,
          f"{tr} connectives, {per100:.2f}/100 words (want <=0.6)")

    hedges = [h for h in HEDGE_STACKS if re.search(h, low)]
    r.add("tell_hedge_stacking", False, "framework_limitation", not hedges,
          f"{len(hedges)} stacked hedges")

    triads = re.findall(r"\b\w+,\s+\w+,?\s+and\s+\w+\b", low)
    r.add("tell_triad_overuse", False, "framework_limitation", len(triads) <= 2,
          f"{len(triads)} 'x, y and z' lists (want <=2)")
    return r


PRODUCT_RE = r"\b" + os.environ.get("PRODUCT_NAME", "yourproduct") + r"\b"


def run_tier2(r, md, feed, meta, sheet_path, now):
    """Prompt v2 additions: title/SEO shape, section relevance, product-mention discipline.

    Only the scriptable half. Answer-first openings and two-source attribution
    are judgement calls and live in rubric.md.
    """
    title_m = re.search(r"^#\s+(.+)$", md, flags=re.M)
    title = title_m.group(1).strip() if title_m else ""
    r.add("t2_title_len", True, "misread_instruction", 0 < len(title) <= 60,
          f"{len(title)} chars: {title[:46]}")
    r.add("t2_title_not_question", True, "misread_instruction",
          bool(title) and not title.rstrip().endswith("?"), title[:46])

    exp = expected_topics(feed, now)
    top = exp[0]["topic"].lower() if exp else ""
    r.add("t2_title_has_top_topic", True, "lost_context",
          bool(top) and top in title.lower(), f"want '{top}' in title")

    h2 = [h.strip() for h in re.findall(r"^##\s+(.+)$", md, flags=re.M)
          if h.strip().lower() not in ("sources", "references")]
    want = {p["topic"].strip().lower() for p in exp}
    got = {h.lower() for h in h2}
    r.add("t2_h2_are_topics", False, "misread_instruction",
          bool(want) and want == got, f"h2={sorted(got)} want={sorted(want)}")

    # each topic section carries at least one feed link
    parts = re.split(r"^##\s+", md, flags=re.M)[1:]
    feed_urls = {norm(x["url"]) for x in feed if x.get("url")}
    bare = []
    for sec in parts:
        head = sec.split("\n", 1)[0].strip().lower()
        if head in ("sources", "references"):
            continue
        if not ({norm(u) for u in urls(sec)} & feed_urls):
            bare.append(head[:24])
    r.add("t2_section_has_link", True, "said_done_but_failed", not bare,
          f"sections with no feed link: {bare}")

    # product-mention discipline
    rr = len(re.findall(PRODUCT_RE, md, flags=re.I))
    r.add("t2_product_present", True, "misread_instruction", rr >= 1, f"{rr} mentions")
    intro_end = md.find("\n##")
    head_zone = md[:intro_end if intro_end > 0 else len(md)]
    r.add("t2_product_placement", True, "misread_instruction",
          not re.search(PRODUCT_RE, head_zone, flags=re.I),
          "product named in title or intro" if re.search(
              PRODUCT_RE, head_zone, flags=re.I) else "")
    last = parts[-1] if parts else ""
    if last.split("\n", 1)[0].strip().lower() in ("sources", "references") and len(parts) > 1:
        last = parts[-2]
    in_last = len(re.findall(PRODUCT_RE, last, flags=re.I))
    r.add("t2_product_confined", False, "lost_context", rr > 0 and in_last == rr,
          f"{in_last}/{rr} mentions in the final topic section")

    # every product sentence must be supported by the fact sheet
    if os.path.isfile(sheet_path):
        sheet = open(sheet_path, encoding="utf8", errors="ignore").read().lower()
        sheet_words = set(re.findall(r"[a-z]{5,}", sheet))
        claims = [sn for sn in re.split(r"(?<=[.!?])\s+", last)
                  if re.search(PRODUCT_RE, sn, flags=re.I)]
        unsupported = []
        for c in claims:
            toks = set(re.findall(r"[a-z]{5,}", c.lower())) - {os.environ.get("PRODUCT_NAME", "yourproduct")}
            if toks and len(toks & sheet_words) / len(toks) < 0.4:
                unsupported.append(c.strip()[:48])
        r.add("t2_product_grounded", True, "said_done_but_failed", not unsupported,
              f"{len(unsupported)} unsupported: {unsupported[:1]}")
    return r


def report(r, as_json=False):
    if as_json:
        print(json.dumps(dict(verdict=r.verdict, checks=r.rows), indent=1)); return
    print(f"\n{'CHECK':<22}{'':2}{'HARD':<6}{'RESULT':<8}{'TAG':<22}DETAIL")
    print("-" * 104)
    for c in r.rows:
        mark = "ok " if c["result"] == "pass" else "FAIL"
        print(f"{c['id']:<22}{'':2}{'hard' if c['hard'] else 'soft':<6}"
              f"{mark:<8}{c['tag']:<22}{c['detail'][:40]}")
    nf = sum(1 for c in r.rows if c["result"] == "fail")
    print("-" * 104)
    print(f"VERDICT: {r.verdict.upper()}   ({len(r.rows)-nf}/{len(r.rows)} passed)")
    tags = collections.Counter(c["tag"] for c in r.rows if c["result"] == "fail")
    if tags: print("failure tags:", dict(tags))

def selftest():
    import tempfile, shutil
    d = tempfile.mkdtemp(); out = os.path.join(d, "output"); os.makedirs(out)
    now = datetime.datetime.utcnow()
    iso = lambda n: (now - datetime.timedelta(days=n)).isoformat() + "Z"
    feed = [
        {"id": 1, "topic": "agent harness", "score": 90, "url": "https://a.dev/harness", "published_at": iso(2)},
        {"id": 2, "topic": "agent memory",  "score": 80, "url": "https://b.dev/memory",  "published_at": iso(3)},
        {"id": 3, "topic": "agent harness", "score": 75, "url": "https://c.dev/dupe",    "published_at": iso(1)},
        {"id": 4, "topic": "tool calling",  "score": 70, "url": "https://d.dev/tools",   "published_at": iso(4)},
        {"id": 5, "topic": "old but loud",  "score": 99, "url": "https://e.dev/old",     "published_at": iso(30)},
        {"id": 6, "topic": "no link here",  "score": 95, "url": None,                    "published_at": iso(1)},
    ]
    json.dump(feed, open(os.path.join(d, "feed.json"), "w"))
    open(os.path.join(d, "banned.txt"), "w").write("leverage\nsynergy\ndelve\n")
    filler = ("Teams building agents keep hitting the same operational wall this quarter "
              "and the reports describe it in similar terms. ") * 1
    body = [f"# Three Things In Agent Tooling\n\n{filler*3}\n"]
    for t, u in (("agent harness", "https://a.dev/harness"),
                 ("agent memory", "https://b.dev/memory"),
                 ("tool calling", "https://d.dev/tools")):
        body.append(f"\n## {t.title()}\n\n" + (f"Reports on {t} describe a shift in how teams "
                    f"scope and observe their runs, with specifics varying by stack. ") * 9
                    + f"[source]({u})\n")
    body.append("\n## Sources\n\n" + "\n".join(
        f"- [{t}]({u})" for t, u in (("agent harness", "https://a.dev/harness"),
                                     ("agent memory", "https://b.dev/memory"),
                                     ("tool calling", "https://d.dev/tools"))))
    open(os.path.join(out, "blog.md"), "w").write("".join(body))
    json.dump({"topics": ["agent harness", "agent memory", "tool calling"],
               "source_urls": ["https://a.dev/harness", "https://b.dev/memory",
                               "https://d.dev/tools"]},
              open(os.path.join(out, "meta.json"), "w"))
    print("SELFTEST - synthetic run with a planted stale post (e.dev/old),")
    print("a duplicate topic (c.dev/dupe) and a URL-less post (id 6).")
    report(run(out, os.path.join(d, "feed.json"), os.path.join(d, "banned.txt"), now))
    shutil.rmtree(d)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", default="./output")
    ap.add_argument("--feed", default="feed.json")
    ap.add_argument("--banned", default="banned_words.txt")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--tells", action="store_true",
                    help="also run machine-prose tells (all soft, proxies only)")
    ap.add_argument("--tier2", action="store_true",
                    help="also run prompt-v2 checks (SEO shape, product-mention discipline)")
    ap.add_argument("--product", default="input/product.md")
    a = ap.parse_args()
    if a.selftest: selftest(); sys.exit(0)
    res = run(a.output, a.feed, a.banned)
    if a.tier2:
        bp = os.path.join(a.output, "blog.md")
        if os.path.isfile(bp):
            mp = os.path.join(a.output, "meta.json")
            m = json.load(open(mp)) if os.path.isfile(mp) else None
            run_tier2(res, open(bp, encoding="utf8", errors="ignore").read(),
                      json.load(open(a.feed, encoding="utf8")), m, a.product,
                      datetime.datetime.utcnow())
    if a.tells:
        bp = os.path.join(a.output, "blog.md")
        if os.path.isfile(bp):
            run_tells(res, open(bp, encoding="utf8", errors="ignore").read())
    report(res, a.json)
    sys.exit({"pass": 0, "partial": 1, "fail": 2}[res.verdict])
