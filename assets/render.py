#!/usr/bin/env python3
"""Render the profile README graphics as light/dark SVG pairs.

    python3 assets/render.py

All text is IBM Plex. GitHub allows no CSS in a README and blocks external
requests from an <img>-loaded SVG, so each SVG embeds its own subset of the
typeface as a base64 woff2, only the glyphs that file actually draws, which
keeps the payload to a few KB per panel. Fonts are vendored in assets/fonts
(SIL OFL 1.1, see assets/fonts/LICENSE.txt) so CI can re-render offline.

Because the fonts are on hand, line breaking measures real glyph advances
rather than guessing at an average character width.

Live data (uptime, repo/star/commit/follower counts, recent contributions) is
pulled from the GitHub API and cached to assets/data.json. If the API is
unreachable or rate-limited, the cache is reused so the profile never renders
blank or zeroed. A failed refresh is a no-op, not a regression.

Set GITHUB_TOKEN to raise the rate limit (the workflow passes the built-in one).
Set SKIP_FETCH=1 to render purely from cache.
"""

import base64
import io
import json
import os
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

OUT = Path(__file__).resolve().parent
ROOT = OUT.parent
CACHE = OUT / "data.json"
FONT_DIR = OUT / "fonts"

# --------------------------------------------------------------------------- #
# config: the only things worth hand-editing
# --------------------------------------------------------------------------- #

USER = os.environ.get("GITHUB_USER", "yxshwanth")
ANCHOR = datetime(2021, 6, 3, tzinfo=timezone.utc)  # uptime counts from here
ROLE = "Backend Engineer"
LOCATION = "San Jose, CA"
LANGUAGES = "Go, Python, Java, TypeScript, SQL"
LINKEDIN = "linkedin.com/in/yashwanth-mali"
EMAIL = "me@yashwanthreddymali.com"
ACTIVITY_ROWS = 5
CANDIDATES = 40  # events kept in the cache; the feed picks from these at render time

W = 846  # GitHub renders the profile README into an 846px column; author 1:1

FACES = {
    "mono": ("IBM Plex Mono", 400, "IBMPlexMono-Regular.woff2", "monospace"),
    "mono6": ("IBM Plex Mono", 600, "IBMPlexMono-SemiBold.woff2", "monospace"),
    "sans": ("IBM Plex Sans", 400, "IBMPlexSans-Regular.woff2", "sans-serif"),
    "sans6": ("IBM Plex Sans", 600, "IBMPlexSans-SemiBold.woff2", "sans-serif"),
}

THEMES = {
    "dark": {
        "bg": "#0d1117", "panel": "#161b22", "chip": "#1c2128",
        "border": "#30363d", "rule": "#21262d",
        "text": "#e6edf3", "muted": "#8b949e", "faint": "#6e7681",
        "blue": "#58a6ff", "green": "#3fb950", "purple": "#bc8cff", "amber": "#ffa657",
        "art": "#c9d1d9", "card_x": 540, "card_w": 1125,
        "hero_rule": "#3d444d", "hero_label": "#ffa657", "hero_dots": "#484f58",
        "hero_value": "#c9d1d9", "hero_num": "#79c0ff", "hero_head": "#58a6ff",
    },
    "light": {
        "bg": "#ffffff", "panel": "#f6f8fa", "chip": "#ffffff",
        "border": "#d0d7de", "rule": "#e4e8ec",
        "text": "#1f2328", "muted": "#59636e", "faint": "#818b98",
        "blue": "#0969da", "green": "#1a7f37", "purple": "#8250df", "amber": "#953800",
        "art": "#24292f", "card_x": 554.4, "card_w": 1139,
        "hero_rule": "#d0d7de", "hero_label": "#953800", "hero_dots": "#8c959f",
        "hero_value": "#24292f", "hero_num": "#0550ae", "hero_head": "#0969da",
    },
}


# --------------------------------------------------------------------------- #
# type: real metrics, and a subset embedded per file
# --------------------------------------------------------------------------- #


@lru_cache(maxsize=None)
def metrics(face):
    from fontTools.ttLib import TTFont

    f = TTFont(FONT_DIR / FACES[face][2])
    hmtx, upm = f["hmtx"], f["head"].unitsPerEm
    adv = {cp: hmtx[g][0] for cp, g in f.getBestCmap().items() if g in hmtx.metrics}
    return adv, upm, adv.get(0x20, upm * 0.6)


def width(s, size, face):
    adv, upm, space = metrics(face)
    return sum(adv.get(ord(c), space) for c in s) * size / upm


def wrap(s, maxw, size, face):
    lines, line = [], ""
    for word in s.split():
        trial = f"{line} {word}".strip()
        if line and width(trial, size, face) > maxw:
            lines.append(line)
            line = word
        else:
            line = trial
    if line:
        lines.append(line)
    return lines


@lru_cache(maxsize=None)
def subset_b64(face, chars):
    """Cut the face down to `chars` and return base64 woff2.

    Layout features are dropped so the browser applies plain advances, exactly
    what `width()` measured. With kerning left in, text would render slightly
    narrower than the layout assumes.
    """
    from fontTools import subset

    opts = subset.Options(flavor="woff2", layout_features=[], notdef_outline=False,
                          hinting=False, desubroutinize=True)
    font = subset.load_font(FONT_DIR / FACES[face][2], opts)
    sub = subset.Subsetter(options=opts)
    sub.populate(text=chars)
    sub.subset(font)
    buf = io.BytesIO()
    subset.save_font(font, buf, opts)
    return base64.b64encode(buf.getvalue()).decode()


def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


class Doc:
    """An SVG under construction, tracking which glyphs it needs."""

    def __init__(self, w, h, label):
        self.w, self.h, self.label = w, h, label
        self.parts, self.used = [], {}

    def _use(self, face, s):
        self.used.setdefault(face, set()).update(str(s))

    def _family(self, face):
        fam, weight, _, generic = FACES[face]
        return f"'{fam}',{generic}", weight

    def text(self, x, y, s, fill, size=13, face="mono", anchor="start", spacing=None):
        self._use(face, s)
        fam, weight = self._family(face)
        ls = f' letter-spacing="{spacing}"' if spacing else ""
        self.parts.append(
            f'<text x="{x}" y="{y}" fill="{fill}" font-family="{fam}" font-size="{size}" '
            f'font-weight="{weight}" text-anchor="{anchor}"{ls}>{esc(s)}</text>'
        )

    def spans(self, x, y, parts, size=16, face="mono"):
        """One <text> of coloured tspans, keeping monospace columns aligned."""
        fam, weight = self._family(face)
        inner = ""
        for s, fill in parts:
            self._use(face, s)
            inner += f'<tspan fill="{fill}">{esc(s)}</tspan>'
        self.parts.append(
            f'<text x="{x}" y="{y}" font-family="{fam}" font-size="{size}" '
            f'font-weight="{weight}" xml:space="preserve">{inner}</text>'
        )

    def rect(self, x, y, w, h, fill, stroke=None, r=6):
        s = f' stroke="{stroke}"' if stroke else ""
        self.parts.append(
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" fill="{fill}"{s}/>')

    def path(self, d, stroke, sw=1.5, fill="none", extra=""):
        self.parts.append(
            f'<path d="{d}" stroke="{stroke}" stroke-width="{sw}" fill="{fill}"{extra}/>')

    def render(self):
        faces = ""
        for face in sorted(self.used):
            fam, weight, _, _ = FACES[face]
            b64 = subset_b64(face, "".join(sorted(self.used[face])))
            faces += (f"@font-face{{font-family:'{fam}';font-style:normal;"
                      f"font-weight:{weight};src:url(data:font/woff2;base64,{b64}) "
                      f"format('woff2');}}")
        defs = f"<defs><style>{faces}</style></defs>\n  " if faces else ""
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w}" height="{self.h}" '
            f'viewBox="0 0 {self.w} {self.h}" role="img" aria-label="{esc(self.label)}">\n  '
            + defs + "\n  ".join(self.parts) + "\n</svg>\n"
        )


def trunc(s, n):
    s = " ".join(str(s).split())
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def chip(d, x, y, label, colour, c, size=12, face="mono", pad=11, h=24):
    """Pill sized to its own text. Returns the width consumed."""
    w = width(label, size, face) + pad * 2
    d.rect(x, y, w, h, c["chip"], c["border"], r=h / 2)
    d.text(x + pad, y + h / 2 + size * 0.36, label, colour, size, face)
    return w


# --------------------------------------------------------------------------- #
# github data: fetched, cached, and never allowed to break the render
# --------------------------------------------------------------------------- #


def api(path, params=""):
    req = urllib.request.Request(f"https://api.github.com{path}{params}", headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": f"{USER}-profile-renderer",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=20) as r:
        raw = r.read()
    return json.loads(raw) if raw.strip() else []  # 204 on empty repos


def fetch_stats():
    user = api(f"/users/{USER}")
    repos, page = [], 1
    while page <= 4:
        batch = api(f"/users/{USER}/repos", f"?per_page=100&type=owner&page={page}")
        repos += batch
        if len(batch) < 100:
            break
        page += 1

    commits = 0
    for r in repos:
        if r["fork"]:
            continue
        try:
            for con in api(f"/repos/{r['full_name']}/contributors", "?per_page=100&anon=0"):
                if con.get("login", "").lower() == USER.lower():
                    commits += con.get("contributions", 0)
        except Exception:
            continue  # unreadable repo; one bad repo must not sink the refresh

    return {
        "repos": user["public_repos"],
        "followers": user["followers"],
        "stars": sum(r["stargazers_count"] for r in repos if not r["fork"]),
        "commits": commits,
    }


def describe(ev):
    """Collapse one GitHub event into (kind, repo, detail)."""
    kind, repo, p = ev["type"], ev["repo"]["name"], ev.get("payload", {})

    if kind == "PushEvent":
        # payload.commits is often absent on the public events feed, and
        # distinct_size is 0 for merges and re-pushes, so degrade to the branch
        n = p.get("distinct_size") or p.get("size") or 0
        msgs = p.get("commits") or []
        head = next((c["message"].splitlines()[0] for c in reversed(msgs) if c.get("message")), "")
        branch = (p.get("ref") or "").rsplit("/", 1)[-1]
        bits = []
        if n:
            bits.append(f"{n} commit{'s' if n != 1 else ''}")
        if head:
            bits.append(head)
        elif branch:
            bits.append(f"pushed to {branch}")
        return "commit", repo, " · ".join(bits) or "pushed"

    # the events feed frequently omits pull_request.title, so lead with the
    # action verb: "opened #3248" beats a bare "#3248"
    if kind == "PullRequestEvent":
        pr = p.get("pull_request", {})
        num = p.get("number") or pr.get("number", "?")
        title, action = pr.get("title") or "", p.get("action", "")
        if action == "closed" and pr.get("merged"):
            return "merged", repo, f"#{num} {title}"
        return "pr", repo, f"{action or 'opened'} #{num} {title}"

    if kind in ("PullRequestReviewEvent", "PullRequestReviewCommentEvent"):
        pr = p.get("pull_request", {})
        return "review", repo, f"reviewed #{pr.get('number', '?')} {pr.get('title') or ''}"

    if kind == "IssuesEvent":
        i = p.get("issue", {})
        return "issue", repo, f"{p.get('action', '')} #{i.get('number', '?')} {i.get('title', '')}"

    if kind == "IssueCommentEvent":
        i = p.get("issue", {})
        return "comment", repo, f"#{i.get('number', '?')} {i.get('title', '')}"

    if kind == "ReleaseEvent":
        return "release", repo, p.get("release", {}).get("tag_name", "")

    if kind == "CreateEvent":
        rt = p.get("ref_type", "")
        return "create", repo, f"new {rt}" + (f" {p.get('ref')}" if p.get("ref") else "")

    if kind == "ForkEvent":
        return "fork", repo, "forked"
    if kind == "WatchEvent":
        return "star", repo, "starred"
    return None


def fetch_activity():
    events, page = [], 1
    while page <= 3:
        batch = api(f"/users/{USER}/events/public", f"?per_page=100&page={page}")
        events += batch
        if len(batch) < 100:
            break
        page += 1

    rows, tally = [], {}
    for ev in events:
        got = describe(ev)
        if not got:
            continue
        kind, repo, detail = got
        tally[kind] = tally.get(kind, 0) + 1
        if rows and rows[-1]["kind"] == kind == "commit" and rows[-1]["repo"] == repo:
            continue  # collapse a run of pushes to the same repo
        if len(rows) < CANDIDATES:
            rows.append({"kind": kind, "repo": repo, "detail": detail, "at": ev["created_at"]})

    return {"rows": rows, "tally": tally}


def load_data():
    cached = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    if os.environ.get("SKIP_FETCH"):
        return cached
    data = dict(cached)
    for name, fn in (("stats", fetch_stats), ("activity", fetch_activity),
                     ("post", fetch_latest_post)):
        try:
            data[name] = fn()
        except Exception as e:  # a failed refresh must be a no-op, never a regression
            print(f"  ! {name} fetch failed ({e.__class__.__name__}: {e}), keeping cache")
    data["updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    CACHE.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    return data


def uptime(now=None):
    now = now or datetime.now(timezone.utc)
    years, months, days = now.year - ANCHOR.year, now.month - ANCHOR.month, now.day - ANCHOR.day
    if days < 0:
        months -= 1
        prev = (now.month - 1) or 12
        yr = now.year if now.month > 1 else now.year - 1
        days += [31, 29 if yr % 4 == 0 and (yr % 100 or yr % 400 == 0) else 28,
                 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][prev - 1]
    if months < 0:
        years, months = years - 1, months + 12
    return (f"{years} year{'s' * (years != 1)}, {months} month{'s' * (months != 1)}, "
            f"{days} day{'s' * (days != 1)}")


def ago(iso, now=None):
    now = now or datetime.now(timezone.utc)
    secs = max(0, (now - datetime.fromisoformat(iso.replace("Z", "+00:00"))).total_seconds())
    for div, unit in ((86400 * 365, "y"), (86400 * 30, "mo"), (86400 * 7, "w"),
                      (86400, "d"), (3600, "h"), (60, "m")):
        if secs >= div:
            return f"{int(secs // div)}{unit}"
    return "now"



# --------------------------------------------------------------------------- #
# the pinned post, read from the live blog index so it stays current
# --------------------------------------------------------------------------- #

BLOG = "https://yashwanthreddymali.com/blog/"


def fetch_latest_post():
    req = urllib.request.Request(BLOG, headers={"User-Agent": f"{USER}-profile-renderer"})
    with urllib.request.urlopen(req, timeout=20) as r:
        html = r.read().decode("utf-8", "replace")

    # entries are listed newest first: <a href="/blog/slug/"> DATE  TITLE </a>
    m = re.search(r'<a[^>]+href="(/blog/[^"]+/)"[^>]*>(.*?)</a>', html, re.S)
    if not m:
        raise ValueError("no post found on the blog index")
    inner = re.sub(r"<[^>]+>", "\n", m.group(2))
    lines = [x.strip() for x in inner.split("\n") if x.strip()]
    date = next((x for x in lines if re.match(r"^\d{1,2} \w+ 20\d\d", x)), "")
    title = next((x for x in lines if x != date), "")
    return {
        "url": "https://yashwanthreddymali.com" + m.group(1),
        "title": " ".join(title.split()),
        "date": date,
    }


# --------------------------------------------------------------------------- #
# header: who, where, what with, and how to reach me
# --------------------------------------------------------------------------- #

NAME = "Yashwanth Reddy Mali"
TAGLINE = ("Backend engineer. I build production systems and care about the unglamorous parts: "
           "latency budgets, consistency edges, and what breaks at 10x traffic.")
STACK_LINE = "Go · Python · Java · TypeScript · Rust · SQL"
TOOLS_LINE = "gRPC · Kafka · Redis · Postgres · CockroachDB · Kubernetes · eBPF · OpenTelemetry"


def header(c, data):
    s = data.get("stats", {})
    lines = wrap(TAGLINE, W - 64, 14, "sans")
    h = 150 + (len(lines) - 1) * 20
    d = Doc(W, h, f"{NAME}. {ROLE} in {LOCATION}. {TAGLINE}")

    d.text(32, 44, NAME, c["text"], 22, "sans6")
    d.text(32, 66, f"{ROLE}  ·  {LOCATION}", c["muted"], 12.5, "mono")

    y = 96
    for line in lines:
        d.text(32, y, line, c["muted"], 14, "sans")
        y += 20

    d.text(32, y + 12, STACK_LINE, c["text"], 12.5, "mono")
    d.text(32, y + 30, TOOLS_LINE, c["faint"], 12.5, "mono")

    stats = [(s.get("repos", 0), "repos"), (s.get("commits", 0), "commits"),
             (s.get("stars", 0), "stars"), (s.get("followers", 0), "followers")]
    x = W - 32
    for value, label in reversed(stats):
        lw = width(label, 11.5, "mono")
        d.text(x, 44, label, c["faint"], 11.5, "mono", "end")
        d.text(x - lw / 2, 26, str(value), c["blue"], 16, "mono6", "middle")
        x -= lw + 26
    return d.render()


# --------------------------------------------------------------------------- #
# the pinned post
# --------------------------------------------------------------------------- #


def latest(c, data):
    post = data.get("post") or {}
    title = post.get("title", "")
    if not title:
        return None
    lines = wrap(title, W - 200, 16.5, "sans6")[:2]
    h = 76 + (len(lines) - 1) * 22
    d = Doc(W, h, f"Latest post: {title} ({post.get('date','')})")
    d.rect(0.5, 0.5, W - 1, h - 1, c["panel"], c["border"], r=6)
    d.path(f"M1 8 v{h - 16}", c["blue"], 3, extra=' stroke-linecap="round"')

    d.text(28, 28, "LATEST POST", c["blue"], 10, "mono6", spacing="1.6")
    d.text(W - 28, 28, post.get("date", ""), c["faint"], 11.5, "mono", "end")
    y = 52
    for line in lines:
        d.text(28, y, line, c["text"], 16.5, "sans6")
        y += 22
    d.text(W - 28, h - 20, "read it →", c["blue"], 12.5, "mono", "end")
    return d.render()


# --------------------------------------------------------------------------- #
# contributions
# --------------------------------------------------------------------------- #

KINDS = {
    "merged": ("merged", "purple"), "pr": ("pull request", "purple"),
    "review": ("review", "blue"), "issue": ("issue", "green"),
    "comment": ("comment", "green"), "commit": ("push", "blue"),
    "release": ("release", "amber"), "create": ("created", "amber"),
    "fork": ("fork", "muted"), "star": ("star", "muted"),
}

TALLY_ORDER = [("merged", "merged", "merged"), ("pr", "PR", "PRs"),
               ("review", "review", "reviews"), ("issue", "issue", "issues"),
               ("commit", "push", "pushes"), ("release", "release", "releases")]

PRIORITY = ["merged", "pr", "review", "issue", "release", "commit", "create", "comment"]
FILLER = ["star", "fork"]


def select_rows(rows, limit=ACTIVITY_ROWS):
    """Guarantee one of each contribution type before filling by recency.

    Events arrive newest-first. Taken strictly in order, a burst of pushes
    buries the pull requests and reviews that are the point of the panel.
    """
    picked = []
    for kind in PRIORITY:
        newest = next((i for i, r in enumerate(rows) if r["kind"] == kind), None)
        if newest is not None and len(picked) < limit:
            picked.append(newest)
    for pool in (PRIORITY, FILLER):
        for i, r in enumerate(rows):
            if len(picked) >= limit:
                break
            if i not in picked and r["kind"] in pool:
                picked.append(i)
    return sorted((rows[i] for i in picked), key=lambda r: r["at"], reverse=True)[:limit]


def contributions(c, data):
    act = data.get("activity", {})
    rows, tally = select_rows(act.get("rows", [])), act.get("tally", {})
    row_h, top = 28, 96
    h = top + max(1, len(rows)) * row_h + 12

    alt = "Recent contributions: " + "; ".join(
        f"{KINDS.get(r['kind'], ('activity',))[0]} in {r['repo']}" for r in rows)
    d = Doc(W, h, alt or "Recent contributions")
    d.text(32, 34, "contributions", c["muted"], 13, "sans")
    d.text(W - 32, 34, f"public events · refreshed {data.get('updated', '')}",
           c["faint"], 11, "mono", "end")

    x = 32
    for key, one, many in TALLY_ORDER:
        n = tally.get(key, 0)
        if not n:
            continue
        label = one if n == 1 else many
        hue = KINDS[key][1]
        colour = c[hue] if hue != "muted" else c["muted"]
        w = width(f"{n} {label}", 12, "mono") + 24
        d.rect(x, 52, w, 26, c["panel"], c["border"], r=13)
        d.text(x + 12, 69, str(n), colour, 12, "mono6")
        d.text(x + 12 + width(f"{n} ", 12, "mono6"), 69, label, c["muted"], 12, "mono")
        x += w + 7

    for i, r in enumerate(rows):
        y = top + i * row_h
        label, hue = KINDS.get(r["kind"], ("activity", "muted"))
        colour = c[hue] if hue != "muted" else c["muted"]
        d.text(32, y + 16, label, colour, 11, "mono6")
        d.text(140, y + 16, trunc(r["repo"], 30), c["text"], 12, "mono")
        d.text(370, y + 16, trunc(r["detail"], 46), c["muted"], 12, "mono")
        d.text(W - 32, y + 16, ago(r["at"]), c["faint"], 11, "mono", "end")
        if i:
            d.path(f"M32 {y - 1} H{W - 32}", c["rule"], 1)
    return d.render()


# --------------------------------------------------------------------------- #
# selected work, one linked card each
# --------------------------------------------------------------------------- #

WORK = [
    ("Zenith", ["Go", "CockroachDB", "gRPC"],
     "Zanzibar-style ReBAC across 10K+ tenants.",
     "sub-10ms P95 · 10K+ RPS", "blue"),
    ("Dispatch", ["Go", "Kafka", "Postgres"],
     "Multi-tenant webhook delivery with honest circuit breakers.",
     "ingest p99 2.1ms", "green"),
    ("Interlock", ["Go", "eBPF", "Kubernetes"],
     "Runtime exfiltration firewall for AI agents.",
     "~0.5ms on sensitive reads", "purple"),
    ("LineageGraph", ["Python", "LangGraph", "Postgres"],
     "GraphRAG data lineage with hallucination guards.",
     "semantic search <200ms", "amber"),
]

CARD_WIDTH = 410


def work_card(c, name, techs, blurb, metric, hue):
    lines = wrap(blurb, CARD_WIDTH - 56, 13, "sans")
    h = 118 + (len(lines) - 1) * 18
    d = Doc(CARD_WIDTH, h, f"{name}: {blurb} {metric}")
    d.rect(0.5, 0.5, CARD_WIDTH - 1, h - 1, c["panel"], c["border"], r=6)

    d.text(24, 34, name, c[hue], 15.5, "sans6")
    d.text(CARD_WIDTH - 24, 34, " · ".join(techs), c["faint"], 11, "mono", "end")

    y = 62
    for line in lines:
        d.text(24, y, line, c["muted"], 13, "sans")
        y += 18
    d.text(24, h - 22, metric, c["text"], 12, "mono")
    return d.render()


# --------------------------------------------------------------------------- #

CONTACT = [
    ("blog", "yashwanthreddymali.com/blog", "blue"),
    ("email", EMAIL, "purple"),
    ("linkedin", "in/yashwanth-mali", "blue"),
]


def contact_button(c, label, value, hue):
    w = width(f"{label}  {value}", 12, "mono") + 40
    d = Doc(round(w), 32, f"{label}: {value}")
    d.rect(0.5, 0.5, w - 1, 31, c["panel"], c["border"], r=6)
    d.parts.append(f'<circle cx="17" cy="16" r="3.5" fill="{c[hue]}"/>')
    d.text(28, 20.5, label, c[hue], 12, "mono6")
    d.text(28 + width(label + "  ", 12, "mono6"), 20.5, value, c["text"], 12, "mono")
    return d.render()


def readme(data):
    """Emit README.md so the pinned card and its link can never disagree."""
    post = data.get("post") or {}

    def pic(name, alt, size='width="100%"', indent=""):
        i = indent
        return (f'{i}<picture>\n'
                f'{i}  <source media="(prefers-color-scheme: dark)" srcset="assets/{name}-dark.svg" />\n'
                f'{i}  <source media="(prefers-color-scheme: light)" srcset="assets/{name}-light.svg" />\n'
                f'{i}  <img alt="{alt}" src="assets/{name}-dark.svg" {size} />\n'
                f'{i}</picture>')

    out = [pic("header", f"{NAME}, {ROLE} in {LOCATION}. {TAGLINE}"), ""]

    out.append('<p align="left">')
    for label, value, url in (("blog", "yashwanthreddymali.com/blog", BLOG),
                              ("email", EMAIL, f"mailto:{EMAIL}"),
                              ("linkedin", "in/yashwanth-mali", f"https://{LINKEDIN}")):
        card = pic(f"btn-{label}", f"{label}: {value}", 'height="32"', indent="  ")
        out.append(f'  <a href="{url}">{card.lstrip()}</a>')
    out += ["</p>", ""]

    if post.get("title"):
        card = pic("latest", f"Latest post, {post['date']}: {post['title']}", indent="  ")
        out += [f'<a href="{post["url"]}">', card, "</a>", ""]

    out += [pic("contributions", "Recent public GitHub contributions"), ""]

    cells = []
    for name, techs, blurb, metric, _ in WORK:
        alt = f"{name}: {blurb} {', '.join(techs)}. {metric}"
        card = pic(f"work-{name.lower()}", alt, indent="  ")
        cells.append(f'<td width="50%"><a href="{REPO_URLS[name]}">\n{card}\n</a></td>')
    out += ["<table>", "<tr>", cells[0], cells[1], "</tr>",
            "<tr>", cells[2], cells[3], "</tr>", "</table>", ""]

    (ROOT / "README.md").write_text("\n".join(out))


REPO_URLS = {
    "Zenith": "https://github.com/yxshwanth/zenith",
    "Dispatch": "https://github.com/yxshwanth/Dispatch",
    "Interlock": "https://github.com/yxshwanth/Interlock",
    "LineageGraph": "https://github.com/yxshwanth/LineageGraph",
}


def main():
    data = load_data()
    for theme, c in THEMES.items():
        (OUT / f"header-{theme}.svg").write_text(header(c, data))
        (OUT / f"contributions-{theme}.svg").write_text(contributions(c, data))
        post = latest(c, data)
        if post:
            (OUT / f"latest-{theme}.svg").write_text(post)
        for label, value, hue in CONTACT:
            (OUT / f"btn-{label}-{theme}.svg").write_text(contact_button(c, label, value, hue))
        for name, techs, blurb, metric, hue in WORK:
            (OUT / f"work-{name.lower()}-{theme}.svg").write_text(
                work_card(c, name, techs, blurb, metric, hue))
        print(f"  rendered {theme}")
    readme(data)

    s, p = data.get("stats", {}), data.get("post", {})
    print(f"  {s.get('repos', 0)} repos · {s.get('commits', 0)} commits · "
          f"{s.get('followers', 0)} followers")
    print(f"  pinned post: {p.get('title', 'NONE')[:60]}")
    total = sum(f.stat().st_size for f in OUT.glob("*.svg"))
    print(f"  {total / 1024:.0f} KB of SVG")


if __name__ == "__main__":
    main()
