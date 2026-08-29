#!/usr/bin/env python3
"""Render every graphic on the profile README as light/dark SVG pairs.

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
ACTIVITY_ROWS = 6
CANDIDATES = 40  # events kept in the cache; the feed picks from these at render time

W = 1125  # full-width panels
CARD_W = 58  # characters per hero card line, so every dot leader shares a column

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


# Contribution types, most interesting first. Stars and forks are not
# contributions; they only fill space left over once these run out.
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


def load_data():
    cached = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    if os.environ.get("SKIP_FETCH"):
        return cached
    data = dict(cached)
    for name, fn in (("stats", fetch_stats), ("activity", fetch_activity)):
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
# hero: ASCII portrait + neofetch-style card
# --------------------------------------------------------------------------- #


def dot_row(label, value, width_chars=CARD_W):
    head, tail = f". {label}: ", f" {value}"
    return head, "." * max(1, width_chars - len(head) - len(tail)), tail


def hero(theme, c, data):
    art = (OUT / f"portrait-{theme}.txt").read_text().rstrip("\n").split("\n")
    s = data.get("stats", {})
    x = c["card_x"]
    d = Doc(c["card_w"], 536, f"ASCII GitHub profile card for {USER}")
    d.rect(0.5, 0.5, c["card_w"] - 1, 535, c["bg"], c["border"], r=8)

    for i, line in enumerate(art):
        d._use("mono", line)
        d.parts.append(
            f'<text x="28" y="{round(34.6 + i * 9.6, 1)}" fill="{c["art"]}" '
            f"font-family=\"'IBM Plex Mono',monospace\" font-size=\"8\" "
            f'xml:space="preserve">{esc(line)}</text>'
        )

    def field(y, label, value):
        head, mid, tail = dot_row(label, value)
        d.spans(x, y, [(head, c["hero_label"]), (mid, c["hero_dots"]), (tail, c["hero_value"])])

    def rule(y, title):
        body = f" {title} "
        d.spans(x, y, [("─", c["hero_rule"]), (body, c["hero_head"]),
                       ("─" * max(1, CARD_W - 1 - len(body)), c["hero_rule"])])

    def pair(y, left, lval, right, rval):
        lh, lm, lt = dot_row(left, lval, 27)
        rh, rm, rt = dot_row(right, rval, 28)
        d.spans(x, y, [(lh, c["hero_label"]), (lm, c["hero_dots"]), (lt, c["hero_num"]),
                       (" | ", c["hero_rule"]),
                       (rh, c["hero_label"]), (rm, c["hero_dots"]), (rt, c["hero_num"])])

    rule(173, f"{USER}@github")
    field(193, "Role", ROLE)
    field(213, "Uptime", uptime())
    field(233, "Location", LOCATION)
    field(253, "Languages", LANGUAGES)
    rule(293, "Contact")
    field(313, "GitHub", f"github.com/{USER}")
    field(333, "LinkedIn", LINKEDIN)
    rule(373, "GitHub Stats")
    pair(393, "Repos", s.get("repos", 0), "Stars", s.get("stars", 0))
    pair(413, "Commits", s.get("commits", 0), "Followers", s.get("followers", 0))
    return d.render()


# --------------------------------------------------------------------------- #
# intro + contact
# --------------------------------------------------------------------------- #

HEADLINE = "Backend engineer building production systems in Go, Python, Java, and TypeScript."
SUBLINE = ("I care about the unglamorous parts: latency budgets, consistency edges, "
           "and what breaks at 10× traffic.")
STATUS = ["MS CS @ CU Boulder", "GPA 3.9", "Open to full-time backend / systems roles"]

CONTACT = [
    ("email", EMAIL, "blue"),
    ("linkedin", LINKEDIN, "blue"),
    ("github", f"github.com/{USER}", "purple"),
]


def intro(c, _data=None):
    d = Doc(W, 150, f"{HEADLINE} {SUBLINE}")
    d.rect(0.5, 0.5, W - 1, 149, c["bg"], c["border"], r=8)
    y = 46
    for line in wrap(HEADLINE, W - 64, 21, "sans6"):
        d.text(32, y, line, c["text"], 21, "sans6")
        y += 28
    for line in wrap(SUBLINE, W - 64, 14.5, "sans"):
        d.text(32, y, line, c["muted"], 14.5, "sans")
        y += 21
    x = 32
    for label in STATUS:
        x += chip(d, x, y + 2, label, c["blue"], c, 12.5) + 8
    return d.render()


def contact_button(c, label, value, hue):
    text_s = f"{label}  {value}"
    w = width(text_s, 12.5, "mono") + 44
    d = Doc(round(w), 34, f"{label}: {value}")
    d.rect(0.5, 0.5, w - 1, 33, c["panel"], c["border"], r=8)
    d.parts.append(f'<circle cx="18" cy="17" r="4" fill="{c[hue]}"/>')
    d.text(30, 21.5, label, c[hue], 12.5, "mono6")
    d.text(30 + width(label + "  ", 12.5, "mono6"), 21.5, value, c["text"], 12.5, "mono")
    return d.render()


# --------------------------------------------------------------------------- #
# impact strip: the four numbers worth reading first
# --------------------------------------------------------------------------- #

IMPACT = [
    ("1.2s → 480ms", "API P95, production", "Credible Data · pools + indexes", "blue"),
    ("10K+ RPS", "authorization checks", "Zenith · sub-10ms P95", "green"),
    ("p99 2.1ms", "webhook ingest", "Dispatch · Kafka + Postgres", "purple"),
    ("100K+ /mo", "transactions monitored", "IntelleWings · sub-200ms", "amber"),
]


def impact(c, _data=None):
    alt = "Impact: " + " · ".join(f"{n} {l}" for n, l, _, _ in IMPACT)
    d = Doc(W, 128, alt)
    d.rect(0.5, 0.5, W - 1, 127, c["bg"], c["border"], r=8)
    tw, gap, x0 = 254, 15, 32
    for i, (num, label, sub, hue) in enumerate(IMPACT):
        x = x0 + i * (tw + gap)
        cx = x + tw / 2
        d.rect(x, 16, tw, 96, c["panel"], c["border"])
        d.path(f"M{x + 6} 17 h{tw - 12}", c[hue], 3, extra=' stroke-linecap="round"')
        d.text(cx, 58, num, c[hue], 26, "mono6", "middle")
        d.text(cx, 80, label, c["text"], 13, "sans", "middle")
        d.text(cx, 98, sub, c["faint"], 11, "mono", "middle")
    return d.render()


# --------------------------------------------------------------------------- #
# stack map: the same skills, placed on the path a request actually takes
# --------------------------------------------------------------------------- #

COLUMNS = [
    ("EDGE", "accept", [["gRPC", "REST"], ["SSE", "HMAC"], ["OAuth2 / JWT"], ["rate limiting"]]),
    ("SERVICES", "decide", [["Go", "Python"], ["Java", "Rust"], ["TypeScript"], ["C · eBPF"]]),
    ("CACHE", "absorb", [["Redis"], ["singleflight"], ["LRU + TTL"], ["idempotency"]]),
    ("STATE", "persist", [["Postgres"], ["CockroachDB"], ["Neo4j", "DuckDB"], ["BigQuery"]]),
]

RAILS = [
    ("PLATFORM", "Kubernetes · Docker · AWS · GCP · Terraform · GitHub Actions", "blue"),
    ("OBSERVABILITY", "OpenTelemetry · Prometheus · Grafana · Jaeger", "purple"),
]


def stack(c, _data=None):
    alt = "Stack along a request path: " + " | ".join(
        f"{n} ({', '.join(i for r in rows for i in r)})" for n, _, rows in COLUMNS)
    d = Doc(W, 372, alt)
    d.rect(0.5, 0.5, W - 1, 371, c["bg"], c["border"], r=8)
    d.text(32, 40, "how a request moves through what i build", c["muted"], 13, "sans")
    d.text(W - 32, 40, "left to right, one request", c["faint"], 11, "mono", "end")

    colw, gap, x0, panel_y, panel_h = 230, 42, 40, 78, 152
    for i, (name, verb, rows) in enumerate(COLUMNS):
        x = x0 + i * (colw + gap)
        d.text(x + 2, 66, name, c["blue"], 11, "mono6", spacing="1.6")
        d.text(x + colw - 2, 66, verb, c["faint"], 11, "mono", "end")
        d.rect(x, panel_y, colw, panel_h, c["panel"], c["border"])

        cy = panel_y + 14
        for row in rows:
            if len(row) == 2:
                half = (colw - 32) / 2
                for j, item in enumerate(row):
                    cxx = x + 12 + j * (half + 8)
                    d.rect(cxx, cy, half, 28, c["chip"], c["border"], r=5)
                    d.text(cxx + half / 2, cy + 19, item, c["text"], 13, "mono", "middle")
            else:
                d.rect(x + 12, cy, colw - 24, 28, c["chip"], c["border"], r=5)
                d.text(x + colw / 2, cy + 19, row[0], c["text"], 13, "mono", "middle")
            cy += 34

        if i < len(COLUMNS) - 1:
            ax, ay = x + colw + gap / 2, panel_y + panel_h / 2
            d.path(f"M{ax - 13} {ay} h20 m-7 -6 l7 6 l-7 6", c["faint"], 1.6,
                   extra=' stroke-linecap="round" stroke-linejoin="round"')

    bus_y = 244
    d.rect(32, bus_y, W - 64, 36, c["panel"], c["border"])
    d.path(f"M44 {bus_y + 18} h{W - 88}", c["rule"], 1, extra=' stroke-dasharray="3 5"')
    d.rect(44, bus_y + 6, 168, 24, c["bg"], c["border"], r=5)
    d.text(128, bus_y + 23, "Kafka · event bus", c["green"], 13, "mono", "middle")
    d.text(W - 44, bus_y + 23, "outbox · DLQ · exponential backoff · circuit breakers",
           c["muted"], 12, "mono", "end")

    rail_y, rail_w = 296, (W - 78) / 2
    for i, (name, items, hue) in enumerate(RAILS):
        x = 32 + i * (rail_w + 14)
        d.rect(x, rail_y, rail_w, 46, c["panel"], c["border"])
        d.text(x + 16, rail_y + 20, name, c[hue], 11, "mono6", spacing="1.6")
        d.text(x + 16, rail_y + 36, items, c["muted"], 12, "mono")
    return d.render()


# --------------------------------------------------------------------------- #
# activity: the latest public contributions, every type, colour-coded
# --------------------------------------------------------------------------- #

KINDS = {
    "merged": ("merged PR", "purple"), "pr": ("pull request", "purple"),
    "review": ("review", "blue"), "issue": ("issue", "green"),
    "comment": ("comment", "green"), "commit": ("push", "blue"),
    "release": ("release", "amber"), "create": ("created", "amber"),
    "fork": ("fork", "muted"), "star": ("star", "muted"),
}

TALLY_ORDER = [("merged", "merged", "merged"), ("pr", "PR", "PRs"),
               ("review", "review", "reviews"), ("issue", "issue", "issues"),
               ("commit", "push", "pushes"), ("release", "release", "releases")]


def activity(c, data):
    act = data.get("activity", {})
    rows, tally = select_rows(act.get("rows", [])), act.get("tally", {})
    row_h, top = 32, 118
    h = top + max(1, len(rows)) * row_h + 16

    alt = "Recent GitHub contributions: " + "; ".join(
        f"{KINDS.get(r['kind'], ('activity',))[0]} in {r['repo']}: {trunc(r['detail'], 72)}"
        for r in rows) if rows else "Recent GitHub contributions"
    d = Doc(W, h, alt)
    d.rect(0.5, 0.5, W - 1, h - 1, c["bg"], c["border"], r=8)
    d.text(32, 40, "recent contributions", c["muted"], 13, "sans")
    d.text(W - 32, 40, f"refreshed {data.get('updated', 'unknown')} · public events, last 90 days",
           c["faint"], 11, "mono", "end")

    x = 32
    for key, one, many in TALLY_ORDER:
        n = tally.get(key, 0)
        if not n:
            continue
        label = one if n == 1 else many
        hue = KINDS[key][1]
        colour = c[hue] if hue != "muted" else c["muted"]
        w = width(f"{n} {label}", 13, "mono") + 28
        d.rect(x, 56, w, 30, c["panel"], c["border"], r=15)
        d.text(x + 14, 76, str(n), colour, 13, "mono6")
        d.text(x + 14 + width(f"{n} ", 13, "mono6"), 76, label, c["muted"], 13, "mono")
        x += w + 8

    if not rows:
        d.text(W / 2, top + 24, "no public activity in the last 90 days",
               c["faint"], 13, "mono", "middle")
        return d.render()

    for i, r in enumerate(rows):
        y = top + i * row_h
        label, hue = KINDS.get(r["kind"], ("activity", "muted"))
        colour = c[hue] if hue != "muted" else c["muted"]
        d.rect(32, y, W - 64, row_h - 6, c["panel"], c["border"], r=5)
        d.rect(44, y + 5, 108, 16, c["bg"], colour, r=8)
        d.text(98, y + 16.5, label, colour, 10.5, "mono6", "middle")
        d.text(168, y + 18, trunc(r["repo"], 32), c["text"], 12.5, "mono")
        d.text(452, y + 18, trunc(r["detail"], 66), c["muted"], 12.5, "mono")
        d.text(W - 44, y + 18, ago(r["at"]), c["faint"], 11.5, "mono", "end")
    return d.render()


# --------------------------------------------------------------------------- #
# selected work: one SVG per card so each stays a clickable link
# --------------------------------------------------------------------------- #

WORK = [
    ("Zenith", ["Go", "CockroachDB", "gRPC"],
     "Zanzibar-style ReBAC across 10K+ tenants.",
     "sub-10ms P95 · 10K+ RPS under k6", "blue"),
    ("Dispatch", ["Go", "Kafka", "Postgres", "Redis"],
     "Multi-tenant webhook delivery with honest circuit breakers.",
     "ingest p99 2.1ms · delivery p99 ~2.5ms", "green"),
    ("Interlock", ["Go", "eBPF", "Kubernetes"],
     "Runtime exfiltration firewall for AI agents. MCP proxy plus syscall tracing.",
     "~0.5ms overhead on sensitive reads", "purple"),
    ("LineageGraph", ["Python", "LangGraph", "Postgres"],
     "GraphRAG data lineage with hallucination guards.",
     "semantic search <200ms · graph depth=3 <50ms", "amber"),
]

CARD_WIDTH = 552


def work_card(c, name, techs, blurb, metric, hue):
    d = Doc(CARD_WIDTH, 172, f"{name}: {blurb} {metric}")
    d.rect(0.5, 0.5, CARD_WIDTH - 1, 171, c["bg"], c["border"], r=8)
    d.path(f"M20 16 v140", c[hue], 3, extra=' stroke-linecap="round"')

    d.text(40, 44, name, c[hue], 19, "sans6")
    x = 40
    for t in techs:
        x += chip(d, x, 58, t, c["muted"], c, 11.5, "mono", 9, 22) + 6

    y = 106
    for line in wrap(blurb, CARD_WIDTH - 72, 14, "sans"):
        d.text(40, y, line, c["text"], 14, "sans")
        y += 20

    d.rect(40, 132, CARD_WIDTH - 80, 26, c["panel"], c["border"], r=5)
    d.text(52, 149, metric, c[hue], 12.5, "mono")
    return d.render()


# --------------------------------------------------------------------------- #
# experience
# --------------------------------------------------------------------------- #

EXPERIENCE = [
    ("Software Engineer, Credible Data", "Aug 2025 – May 2026 · Boulder, CO",
     "Express/Node backend for an AI-native data-discovery platform: SSE streaming, Auth0/JWT "
     "gateway, custom MCP server, Malloy over Postgres / Neo4j / BigQuery. Tuned pools and "
     "indexes to cut production P95 1.2s → 480ms. GCP + GitHub Actions with health-check "
     "rollbacks."),
    ("Software Engineer Intern, IntelleWings", "Feb 2023 – Jun 2024 · FinTech",
     "Owned a Spring Boot transaction-monitoring path at 100K+/mo, sub-200ms. Multi-tier Redis "
     "cache cut query latency 70%; Jenkins/Docker/K8s cut release cycles 5 days → 3."),
]

OPEN_SOURCE = ("Merged PRs in Auth0 OpenFGA and Google Malloy, including a Check API "
               "consistency-token fix.")


def experience(c, _data=None):
    body_w = W - 96
    blocks = [(role, meta, wrap(text_, body_w, 14, "sans")) for role, meta, text_ in EXPERIENCE]
    os_lines = wrap(OPEN_SOURCE, body_w - 130, 14, "sans")
    h = 78 + sum(46 + len(ls) * 21 for _, _, ls in blocks) + 20 + len(os_lines) * 21 + 30

    d = Doc(W, h, "Experience: " + " | ".join(f"{r} ({m})" for r, m, _ in EXPERIENCE))
    d.rect(0.5, 0.5, W - 1, h - 1, c["bg"], c["border"], r=8)
    d.text(32, 40, "experience", c["muted"], 13, "sans")

    y = 76
    for role, meta, lines in blocks:
        d.path(f"M32 {y - 14} v{len(lines) * 21 + 30}", c["border"], 2,
               extra=' stroke-linecap="round"')
        d.text(48, y, role, c["text"], 15.5, "sans6")
        d.text(48, y + 20, meta, c["faint"], 12, "mono")
        y += 46
        for line in lines:
            d.text(48, y, line, c["muted"], 14, "sans")
            y += 21
        y += 18

    d.rect(32, y - 16, W - 64, len(os_lines) * 21 + 26, c["panel"], c["border"])
    d.text(48, y + 2, "open source", c["green"], 11, "mono6", spacing="1.6")
    for i, line in enumerate(os_lines):
        d.text(178, y + 2 + i * 21, line, c["muted"], 14, "sans")
    return d.render()


# --------------------------------------------------------------------------- #
# footer
# --------------------------------------------------------------------------- #

TAGLINE = "latency is a feature · consistency is a contract · tests name what they don't catch"
COLOPHON = ("every panel above is generated by assets/render.py and redrawn daily "
            "by GitHub Actions · type is IBM Plex")


def footer(c, _data=None):
    d = Doc(W, 92, TAGLINE)
    d.rect(0.5, 0.5, W - 1, 91, c["bg"], c["border"], r=8)
    d.text(W / 2, 40, TAGLINE, c["muted"], 14, "sans", "middle")
    d.text(W / 2, 68, COLOPHON, c["faint"], 11, "mono", "middle")
    return d.render()


# --------------------------------------------------------------------------- #

PANELS = [("intro", intro), ("impact", impact), ("stack", stack),
          ("activity", activity), ("experience", experience), ("footer", footer)]


def main():
    data = load_data()
    for theme, c in THEMES.items():
        (ROOT / f"{theme}_mode.svg").write_text(hero(theme, c, data))
        for name, fn in PANELS:
            (OUT / f"{name}-{theme}.svg").write_text(fn(c, data))
        for label, value, hue in CONTACT:
            (OUT / f"btn-{label}-{theme}.svg").write_text(contact_button(c, label, value, hue))
        for name, techs, blurb, metric, hue in WORK:
            (OUT / f"work-{name.lower()}-{theme}.svg").write_text(
                work_card(c, name, techs, blurb, metric, hue))
        print(f"  rendered {theme}")

    s = data.get("stats", {})
    total = sum(p.stat().st_size for p in list(OUT.glob("*.svg")) + list(ROOT.glob("*_mode.svg")))
    print(f"  uptime {uptime()} · {s.get('repos', 0)} repos · {s.get('stars', 0)} stars · "
          f"{s.get('commits', 0)} commits · {s.get('followers', 0)} followers")
    print(f"  {total / 1024:.0f} KB of SVG (fonts embedded)")


if __name__ == "__main__":
    main()
