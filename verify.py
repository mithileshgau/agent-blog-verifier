#!/usr/bin/env python3
"""Deterministic checks for a blog-writing agent run.

Frozen once the sprint starts. Measures only - never tells an agent how to pass.

  python3 verify.py --output ./output --feed feed.json --banned banned_words.txt
  python3 verify.py --selftest          # prove it runs, no agent needed

Every check carries a failure tag so a FAIL localises the break, not just
lowers a score.
Exit 0 pass, 1 partial, 2 fail.

v2 changes (proposed by the Pydantic AI owner from the first real runs; each is
marked "v2:" below):
  - meta_valid accepts source URLs anywhere in meta.json (e.g. nested per topic).
  - links_from_feed also checks the URLs in meta.json.
  - section_count counts topic sections only; a closing "Takeaways"/"Conclusion"
    section is a soft finding (no_extra_sections), not a hard fail. A sources
    heading may be longer ("Sources and further reading").
  - no_urlless_source checks the post itself: a source entry without a feed link,
    or meta.json naming a URL-less post. It no longer matches the topic label,
    which failed correct posts when that topic was also a top-3 topic.
  - no_stale_facts (new, hard): numbers that appear only in out-of-window posts.
  - fresh() compares the full timedelta (6.9 days was "6 days" before; 7.9 was fresh).
  - --reference-time freezes "today" for standalone runs.

v3 changes (prompt now asks for inline links instead of "sources at the end";
each is marked "v3:" below):
  - has_sources is removed. New hard check section_has_feed_link: every topic
    section carries at least one feed link. A trailing Sources list is a soft
    warning (no_sources_list), since the prompt no longer asks for one.
  - Sections are classified by position and links, not keywords. An intro or
    closing section is the first or last body section with no feed link; it is
    a soft warning (no_extra_sections). Topic headings containing "overview" or
    "summary" are no longer misread as extra sections.
  - no_urlless_source checks what the post and meta.json actually say: a URL-less
    post named by id or a 5-word run of its title, a number found only in
    URL-less posts, or a "no link available" style citation.
  - no_stale_facts reads every text field of a feed post, not just title and
    summary, and matches numbers by value ("$210M" matches "$210 million").
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
        # v2: compare the full interval. `.days` truncated, so a 7.9-day-old post was fresh.
        if now - d.replace(tzinfo=None) <= datetime.timedelta(days=FRESH_DAYS): out.append(p)
    return out

# v2 helpers -----------------------------------------------------------------
# v3: no keyword list for intro/closing sections; see split_sections().
SOURCES_H = re.compile(r"^(sources?|references?)\b", re.I)
NUM = re.compile(r"(?<![\w.])\d[\d,]*(?:\.\d+)?")  # not digits inside words (H100)
NOT_TEXT = {"url", "published_at", "id", "score"}

def post_text(p):
    """v3: every text field of a feed post, not only title and summary."""
    if not isinstance(p, dict): return ""
    return " ".join(s for k, v in p.items() if k not in NOT_TEXT
                    for s in meta_strings(v))

def split_sections(md):
    """v3: [(heading, text)] for each H2 except the sources heading."""
    parts = re.split(r"^##\s+", md, flags=re.M)[1:]
    out = []
    for sec in parts:
        head, _, text = sec.partition("\n")
        if not SOURCES_H.match(head.strip()):
            out.append((head.strip(), text))
    return out

def meta_strings(obj):
    if isinstance(obj, dict):
        for v in obj.values(): yield from meta_strings(v)
    elif isinstance(obj, list):
        for v in obj: yield from meta_strings(v)
    elif isinstance(obj, str):
        yield obj

def meta_topic_names(meta):
    out = []
    for t in (meta.get("topics") or []) if isinstance(meta, dict) else []:
        if isinstance(t, str): out.append(t)
        elif isinstance(t, dict):
            name = next((t[k] for k in ("topic", "name", "title", "label")
                         if isinstance(t.get(k), str)), None)
            if name: out.append(name)
    return out

def numbers(text):
    """v3: numeric values only ("$210M" -> "210"), so units and "million" spellings match."""
    out = set()
    for n in NUM.findall(text):
        n = n.replace(",", "").rstrip(".")
        if re.fullmatch(r"(19|20)\d\d", n): continue        # years
        if re.fullmatch(r"\d", n): continue                  # lone digits
        out.add(n)
    return out

def mentions_number(n, text):
    return n in numbers(text)

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
    meta_urls = set()
    if meta is not None:
        # v2: the prompt says "topics and source URLs" but names no keys. Accept URLs
        # wherever they are (top-level list or nested per topic); require both parts.
        meta_urls = {norm(s) for s in meta_strings(meta) if s.startswith("http")}
        good = (isinstance(meta, dict) and bool(meta_topic_names(meta))
                and bool(meta_urls))
        r.add("meta_valid", True, "file_or_state_error", good,
              f"keys={list(meta)[:6] if isinstance(meta, dict) else type(meta).__name__}; "
              f"{len(meta_topic_names(meta))} topics, {len(meta_urls)} URLs")

    w = len(words(md))
    r.add("word_count", True, "misread_instruction", WORD_MIN <= w <= WORD_MAX,
          f"{w} words, want {WORD_MIN}-{WORD_MAX}")

    feed_urls = {norm(p["url"]) for p in feed if p.get("url")}
    linked = lambda text: bool({norm(u) for u in urls(text)} & feed_urls)

    h1 = re.findall(r"^#\s+\S", md, flags=re.M)
    # v3: classify by position and links. The first or last body section with no
    # feed link is an intro/closing section; everything else is a topic section.
    secs = split_sections(md)
    framing = set()
    if len(secs) > SECTIONS:
        if not linked(secs[0][1]): framing.add(0)
        if not linked(secs[-1][1]): framing.add(len(secs) - 1)
    topic_secs = [s for i, s in enumerate(secs) if i not in framing]
    framing_h2 = [secs[i][0] for i in sorted(framing)]
    r.add("has_title", True, "misread_instruction", len(h1) == 1, f"{len(h1)} H1")
    # v2: hard = exactly one section per topic; an extra intro/closing section is soft.
    r.add("section_count", True, "misread_instruction", len(topic_secs) == SECTIONS,
          f"{len(topic_secs)} topic sections: {[h for h, _ in topic_secs][:5]}")
    r.add("no_extra_sections", False, "misread_instruction", not framing_h2,
          f"non-topic sections: {framing_h2[:3]}")
    # v3: the prompt asks for each fact to be linked where it is used.
    bare = [h[:30] for h, text in topic_secs if not linked(text)]
    r.add("section_has_feed_link", True, "misread_instruction", not bare,
          f"topic sections with no feed link: {bare[:3]}")

    first = md.find("\n##")
    intro = words(md[md.find("\n", md.find("# ")) : first if first > 0 else len(md)])
    if 0 in framing:  # v3: an "## Introduction" section counts as the intro
        intro += words(secs[0][1])
    r.add("has_intro", True, "misread_instruction", len(intro) >= 30,
          f"{len(intro)} intro words")

    used = {norm(u) for u in urls(md)}
    stray = sorted((used | meta_urls) - feed_urls)  # v2: meta.json URLs too
    r.add("links_from_feed", True, "said_done_but_failed", not stray,
          f"{len(stray)} off-feed: {stray[:3]}")
    # v3: the prompt no longer asks for a Sources list; one at the end is a warning.
    src_heads = [h for h in re.findall(r"^##\s+(.+)$", md, flags=re.M)
                 if SOURCES_H.match(h.strip())]
    r.add("no_sources_list", False, "misread_instruction", not src_heads,
          f"sources heading present: {src_heads[:1]}")

    low = md.lower()
    hits = [b for b in banned if re.search(rf"\b{re.escape(b)}\b", low)]
    r.add("no_banned_words", True, "misread_instruction", not hits, f"{hits[:5]}")

    stale = {norm(p["url"]) for p in feed
             if p.get("url") and p not in fresh(feed, now)}
    used_stale = sorted(used & stale)
    r.add("no_stale_sources", True, "lost_context", not used_stale,
          f"cited {len(used_stale)} post(s) older than {FRESH_DAYS}d")

    # v3: the URL-less post must not be used, wherever it shows up. Check what the
    # post and meta.json say: the post named by id (meta) or by a 5-word run of its
    # title, a number that exists only in URL-less posts, or a citation that admits
    # it has no link.
    flat = lambda text: " ".join(re.findall(r"[a-z0-9%$]+", text.lower()))
    nourl = [p for p in feed if not p.get("url")]
    meta_text = " ".join(meta_strings(meta)).lower() if meta is not None else ""
    blog_words, meta_words = flat(md), flat(meta_text)
    meta_ids = set()
    def collect_ids(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k in ("id", "post_id") and isinstance(v, (str, int)): meta_ids.add(str(v).lower())
                collect_ids(v)
        elif isinstance(obj, list):
            for v in obj: collect_ids(v)
    collect_ids(meta)
    linked_text = " ".join(post_text(p) for p in feed if p.get("url"))
    linked_nums = numbers(linked_text)
    blog_nums = numbers(re.sub(r"\(https?://[^)]*\)|https?://\S+", " ", md))  # not URL digits
    used_nourl = []
    for p in nourl:
        label = str(p.get("id") or p.get("title", "")[:40])
        title = flat(p.get("title", "")).split()
        runs = {" ".join(title[i:i + 5]) for i in range(max(len(title) - 4, 0))}
        hit = [w for w, text in (("blog", blog_words), ("meta", meta_words))
               if any(f" {run} " in f" {text} " for run in runs)]
        if p.get("id") is not None and str(p["id"]).lower() in meta_ids:
            hit.append("meta id")
        only_here = (numbers(post_text(p)) - linked_nums) & blog_nums
        if only_here: hit.append(f"numbers {sorted(only_here)[:2]}")
        if hit: used_nourl.append(f"{label}: {', '.join(hit)}")
    admits = re.findall(r"[^.\n]*\b(?:no (?:link|url)|link (?:not |un)available|"
                        r"without a (?:link|url))\b[^.\n]*", md, re.I)
    if nourl and admits: used_nourl.append(f"unlinked citation: {admits[0].strip()[:60]}")
    r.add("no_urlless_source", True, "wrong_tool_or_args", not used_nourl,
          f"URL-less post used: {used_nourl[:2]}")

    # v2: facts (numbers) that exist only in out-of-window posts must not be used.
    # v3: read every text field of each post, and match numbers by value.
    fresh_posts = fresh(feed, now)
    fresh_nums = numbers(" ".join(post_text(p) for p in fresh_posts))
    stale_hits = set()
    for p in feed:
        if p in fresh_posts: continue
        stale_hits |= (numbers(post_text(p)) - fresh_nums) & blog_nums
    r.add("no_stale_facts", True, "lost_context", not stale_hits,
          f"numbers found only in out-of-window posts: {sorted(stale_hits)[:4]}")

    exp = expected_topics(feed, now)
    matched = [p for p in exp if p["topic"].lower() in low
               or norm(p["url"]) in used]
    r.add("topics_match_feed", True, "wrong_tool_or_args", len(matched) == len(exp),
          f"{len(matched)}/{len(exp)}: expected {[p['topic'] for p in exp]}")

    if meta and isinstance(meta, dict) and isinstance(meta.get("topics"), list):
        seen = [t.strip().lower() for t in meta_topic_names(meta)]  # v2: topic objects too
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
    ap.add_argument("--reference-time",
                    help="v2: frozen 'today' as ISO 8601 with timezone; without it the "
                         "7-day window moves with the real clock")
    a = ap.parse_args()
    if a.selftest: selftest(); sys.exit(0)
    ref = None
    if a.reference_time:
        ref = datetime.datetime.fromisoformat(a.reference_time.replace("Z", "+00:00"))
        if ref.tzinfo is None: sys.exit("--reference-time needs a timezone")
        ref = ref.astimezone(datetime.timezone.utc).replace(tzinfo=None)
    else:
        print("warning: no --reference-time; using the current clock", file=sys.stderr)
    res = run(a.output, a.feed, a.banned, now=ref)
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
