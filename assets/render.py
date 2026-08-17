#!/usr/bin/env python3
"""Render every graphic on the profile README as light/dark SVG pairs.

    python3 assets/render.py

Live data (uptime, repo/star/commit/follower counts, recent contributions) is
pulled from the GitHub API and cached to assets/data.json. If the API is
unreachable or rate-limited, the cache is reused so the profile never renders
blank or zeroed — a failed refresh is a no-op, not a regression.

Set GITHUB_TOKEN to raise the rate limit (the workflow passes the built-in one).
Set SKIP_FETCH=1 to render purely from cache.

Outputs:
    dark_mode.svg, light_mode.svg          hero card + ASCII portrait
    assets/impact-{dark,light}.svg         headline metrics
    assets/stack-{dark,light}.svg          stack laid out along a request path
    assets/activity-{dark,light}.svg       recent contributions feed
"""

import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parent
ROOT = OUT.parent
CACHE = OUT / "data.json"

# --------------------------------------------------------------------------- #
# config — the only things worth hand-editing
# --------------------------------------------------------------------------- #

USER = os.environ.get("GITHUB_USER", "yxshwanth")
ANCHOR = datetime(2021, 6, 3, tzinfo=timezone.utc)  # uptime counts from here
ROLE = "Backend Engineer"
LOCATION = "Morgan Hill, CA"
LANGUAGES = "Go, Python, Java, TypeScript, SQL"
ACTIVITY_ROWS = 6

MONO = "ui-monospace,SFMono-Regular,'SF Mono',Menlo,Consolas,'Liberation Mono',monospace"
SANS = "-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif"
ART_MONO = "'Consolas', 'Menlo', 'DejaVu Sans Mono', monospace"

THEMES = {
    "dark": {
        "bg": "#0d1117",
        "panel": "#161b22",
        "chip": "#1c2128",
        "border": "#30363d",
        "rule": "#21262d",
        "text": "#e6edf3",
        "muted": "#8b949e",
        "faint": "#6e7681",
        "blue": "#58a6ff",
        "green": "#3fb950",
        "purple": "#bc8cff",
        "amber": "#ffa657",
        "red": "#f85149",
        # hero card keeps its original, slightly warmer palette
        "art": "#c9d1d9",
        "card_x": 540,
        "card_w": 1125,
        "hero_rule": "#3d444d",
        "hero_label": "#ffa657",
        "hero_dots": "#484f58",
        "hero_value": "#c9d1d9",
        "hero_num": "#79c0ff",
        "hero_head": "#58a6ff",
    },
    "light": {
        "bg": "#ffffff",
        "panel": "#f6f8fa",
        "chip": "#ffffff",
        "border": "#d0d7de",
        "rule": "#e4e8ec",
        "text": "#1f2328",
        "muted": "#59636e",
        "faint": "#818b98",
        "blue": "#0969da",
        "green": "#1a7f37",
        "purple": "#8250df",
        "amber": "#953800",
        "red": "#cf222e",
        "art": "#24292f",
        "card_x": 554.4,
        "card_w": 1139,
        "hero_rule": "#d0d7de",
        "hero_label": "#953800",
        "hero_dots": "#8c959f",
        "hero_value": "#24292f",
        "hero_num": "#0550ae",
        "hero_head": "#0969da",
    },
}

W = 1125


# --------------------------------------------------------------------------- #
# svg plumbing
# --------------------------------------------------------------------------- #


def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def text(x, y, s, fill, size=13, family=MONO, anchor="start", weight="normal", spacing=None):
    ls = f' letter-spacing="{spacing}"' if spacing else ""
    return (
        f'<text x="{x}" y="{y}" fill="{fill}" font-family="{family}" font-size="{size}" '
        f'font-weight="{weight}" text-anchor="{anchor}"{ls}>{esc(s)}</text>'
    )


def spans(x, y, parts, size=16, family=MONO):
    """One <text> made of coloured tspans — keeps monospace columns aligned."""
    inner = "".join(f'<tspan fill="{fill}">{esc(s)}</tspan>' for s, fill in parts)
    return (
        f'<text x="{x}" y="{y}" font-family="{family}" xml:space="preserve" '
        f'font-size="{size}">{inner}</text>'
    )


def rect(x, y, w, h, fill, stroke=None, r=6):
    s = f' stroke="{stroke}"' if stroke else ""
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" fill="{fill}"{s}/>'


def svg(width, height, label, body):
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-label="{esc(label)}">\n  '
        + "\n  ".join(body)
        + "\n</svg>\n"
    )


def trunc(s, n):
    s = " ".join(str(s).split())
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


# --------------------------------------------------------------------------- #
# github data — fetched, cached, and never allowed to break the render
# --------------------------------------------------------------------------- #


def api(path, params=""):
    url = f"https://api.github.com{path}{params}"
    req = urllib.request.Request(url, headers={
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

    stars = sum(r["stargazers_count"] for r in repos if not r["fork"])

    commits = 0
    for r in repos:
        if r["fork"]:
            continue
        try:
            for c in api(f"/repos/{r['full_name']}/contributors", "?per_page=100&anon=0"):
                if c.get("login", "").lower() == USER.lower():
                    commits += c.get("contributions", 0)
        except Exception:
            continue  # unreadable repo — one bad repo must not sink the refresh

    return {
        "repos": user["public_repos"],
        "followers": user["followers"],
        "stars": stars,
        "commits": commits,
    }


def describe(ev):
    """Collapse one GitHub event into (kind, repo, detail)."""
    kind, repo, p = ev["type"], ev["repo"]["name"], ev.get("payload", {})

    if kind == "PushEvent":
        n = p.get("distinct_size") or p.get("size") or 0
        msgs = p.get("commits") or []
        head = msgs[-1]["message"].splitlines()[0] if msgs else "no message"
        return "commit", repo, f"{n} commit{'s' if n != 1 else ''} · {head}"

    if kind == "PullRequestEvent":
        pr = p.get("pull_request", {})
        num, title = p.get("number", "?"), pr.get("title", "")
        if p.get("action") == "closed" and pr.get("merged"):
            return "merged", repo, f"#{num} {title}"
        if p.get("action") == "closed":
            return "pr", repo, f"closed #{num} {title}"
        return "pr", repo, f"#{num} {title}"

    if kind in ("PullRequestReviewEvent", "PullRequestReviewCommentEvent"):
        return "review", repo, f"#{p.get('pull_request', {}).get('number', '?')} " \
                               f"{p.get('pull_request', {}).get('title', '')}"

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

        # collapse a run of pushes to the same repo into one row
        if rows and rows[-1]["kind"] == kind == "commit" and rows[-1]["repo"] == repo:
            continue
        if len(rows) < ACTIVITY_ROWS * 2:
            rows.append({"kind": kind, "repo": repo, "detail": detail, "at": ev["created_at"]})

    return {"rows": rows[:ACTIVITY_ROWS], "tally": tally}


def load_data():
    cached = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    if os.environ.get("SKIP_FETCH"):
        return cached

    data = dict(cached)
    for name, fn in (("stats", fetch_stats), ("activity", fetch_activity)):
        try:
            data[name] = fn()
        except Exception as e:  # a failed refresh must be a no-op, never a regression
            print(f"  ! {name} fetch failed ({e.__class__.__name__}: {e}) — keeping cached values")
    data["updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    CACHE.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    return data


def uptime(now=None):
    now = now or datetime.now(timezone.utc)
    years = now.year - ANCHOR.year
    months = now.month - ANCHOR.month
    days = now.day - ANCHOR.day
    if days < 0:
        months -= 1
        prev = (now.month - 1) or 12
        yr = now.year if now.month > 1 else now.year - 1
        days += [31, 29 if yr % 4 == 0 and (yr % 100 or yr % 400 == 0) else 28,
                 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][prev - 1]
    if months < 0:
        years -= 1
        months += 12
    return (f"{years} year{'s' * (years != 1)}, {months} month{'s' * (months != 1)}, "
            f"{days} day{'s' * (days != 1)}")


def ago(iso, now=None):
    now = now or datetime.now(timezone.utc)
    then = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    secs = max(0, (now - then).total_seconds())
    for div, unit in ((86400 * 365, "y"), (86400 * 30, "mo"), (86400 * 7, "w"),
                      (86400, "d"), (3600, "h"), (60, "m")):
        if secs >= div:
            return f"{int(secs // div)}{unit}"
    return "now"


# --------------------------------------------------------------------------- #
# hero — ASCII portrait + neofetch-style card, now with live values
# --------------------------------------------------------------------------- #

CARD_W = 58  # characters per card line, so every dot leader lands on the same column


def dots(label, value, width=CARD_W):
    head, tail = f". {label}: ", f" {value}"
    return head, "." * max(1, width - len(head) - len(tail)), tail


def field(x, y, label, value, c, value_color=None):
    head, mid, tail = dots(label, value)
    return spans(x, y, [(head, c["hero_label"]), (mid, c["hero_dots"]),
                        (tail, value_color or c["hero_value"])])


def rule(x, y, title, c):
    body = f" {title} "
    return spans(x, y, [("─", c["hero_rule"]), (body, c["hero_head"]),
                        ("─" * max(1, CARD_W - 1 - len(body)), c["hero_rule"])])


def stat_pair(x, y, left, lval, right, rval, c):
    lh, lm, lt = dots(left, lval, 27)
    rh, rm, rt = dots(right, rval, 28)
    return spans(x, y, [(lh, c["hero_label"]), (lm, c["hero_dots"]), (lt, c["hero_num"]),
                        (" | ", c["hero_rule"]),
                        (rh, c["hero_label"]), (rm, c["hero_dots"]), (rt, c["hero_num"])])


def hero(theme, c, data):
    art = (OUT / f"portrait-{theme}.txt").read_text().rstrip("\n").split("\n")
    s = data.get("stats", {})
    x, w, h = c["card_x"], c["card_w"], 536

    body = [rect(0.5, 0.5, w - 1, h - 1, c["bg"], c["border"], r=8)]
    for i, line in enumerate(art):
        body.append(
            f'<text x="28" y="{round(34.6 + i * 9.6, 1)}" fill="{c["art"]}" '
            f'font-family="{ART_MONO}" xml:space="preserve" font-size="8">{esc(line)}</text>'
        )

    body += [
        rule(x, 173, f"{USER}@github", c),
        field(x, 193, "Role", ROLE, c),
        field(x, 213, "Uptime", uptime(), c),
        field(x, 233, "Location", LOCATION, c),
        field(x, 253, "Languages", LANGUAGES, c),
        rule(x, 293, "Contact", c),
        field(x, 313, "GitHub", f"github.com/{USER}", c),
        field(x, 333, "LinkedIn", "linkedin.com/in/yashwanth-mali", c),
        rule(x, 373, "GitHub Stats", c),
        stat_pair(x, 393, "Repos", s.get("repos", 0), "Stars", s.get("stars", 0), c),
        stat_pair(x, 413, "Commits", s.get("commits", 0), "Followers", s.get("followers", 0), c),
    ]
    return svg(w, h, f"ASCII GitHub profile card for {USER}", body)


# --------------------------------------------------------------------------- #
# impact strip: the four numbers worth reading first
# --------------------------------------------------------------------------- #

IMPACT = [
    ("1.2s → 480ms", "API P95, production", "Credible Data · pools + indexes", "blue"),
    ("10K+ RPS", "authorization checks", "Zenith · sub-10ms P95", "green"),
    ("p99 2.1ms", "webhook ingest", "Dispatch · Kafka + Postgres", "purple"),
    ("100K+ /mo", "transactions monitored", "IntelleWings · sub-200ms", "amber"),
]

IMPACT_ALT = ("Impact metrics: API P95 1.2s to 480ms, 10K+ RPS authorization, p99 2.1ms ingest, "
              "100K+ monthly transactions")


def impact(c, _data=None):
    h = 128
    tw, gap, x0 = 254, 15, 32
    body = [rect(0.5, 0.5, W - 1, h - 1, c["bg"], c["border"], r=8)]
    for i, (num, label, sub, hue) in enumerate(IMPACT):
        x = x0 + i * (tw + gap)
        cx = x + tw / 2
        body += [
            rect(x, 16, tw, 96, c["panel"], c["border"]),
            f'<path d="M{x + 6} 17 h{tw - 12}" stroke="{c[hue]}" stroke-width="3" '
            f'stroke-linecap="round" fill="none"/>',
            text(cx, 58, num, c[hue], 27, MONO, "middle", "600"),
            text(cx, 80, label, c["text"], 13, SANS, "middle"),
            text(cx, 98, sub, c["faint"], 11, MONO, "middle"),
        ]
    return svg(W, h, IMPACT_ALT, body)


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

STACK_ALT = (
    "Stack map along a request path: edge (gRPC, REST, SSE, OAuth2/JWT), services (Go, Python, "
    "Java, Rust, TypeScript, eBPF), cache (Redis, singleflight, LRU), state (Postgres, CockroachDB, "
    "Neo4j, DuckDB, BigQuery), Kafka event bus, plus platform and observability tooling"
)


def stack(c, _data=None):
    h = 372
    colw, gap, x0 = 230, 42, 40
    panel_y, panel_h = 78, 152
    body = [rect(0.5, 0.5, W - 1, h - 1, c["bg"], c["border"], r=8)]

    body += [
        text(32, 40, "how a request moves through what i build", c["muted"], 13, SANS),
        text(W - 32, 40, "left to right, one request", c["faint"], 11, MONO, "end"),
    ]

    for i, (name, verb, rows) in enumerate(COLUMNS):
        x = x0 + i * (colw + gap)
        body += [
            text(x + 2, 66, name, c["blue"], 11, MONO, "start", "600", "1.6"),
            text(x + colw - 2, 66, verb, c["faint"], 11, MONO, "end"),
            rect(x, panel_y, colw, panel_h, c["panel"], c["border"]),
        ]

        cy = panel_y + 14
        for row in rows:
            if len(row) == 2:
                half = (colw - 24 - 8) / 2
                for j, item in enumerate(row):
                    cxx = x + 12 + j * (half + 8)
                    body += [
                        rect(cxx, cy, half, 28, c["chip"], c["border"], r=5),
                        text(cxx + half / 2, cy + 19, item, c["text"], 13, MONO, "middle"),
                    ]
            else:
                body += [
                    rect(x + 12, cy, colw - 24, 28, c["chip"], c["border"], r=5),
                    text(x + colw / 2, cy + 19, row[0], c["text"], 13, MONO, "middle"),
                ]
            cy += 34

        if i < len(COLUMNS) - 1:
            ax, ay = x + colw + gap / 2, panel_y + panel_h / 2
            body.append(
                f'<path d="M{ax - 13} {ay} h20 m-7 -6 l7 6 l-7 6" stroke="{c["faint"]}" '
                f'stroke-width="1.6" fill="none" stroke-linecap="round" stroke-linejoin="round"/>'
            )

    bus_y = 244
    body += [
        rect(32, bus_y, W - 64, 36, c["panel"], c["border"]),
        f'<path d="M44 {bus_y + 18} h{W - 88}" stroke="{c["rule"]}" stroke-width="1" '
        f'stroke-dasharray="3 5" fill="none"/>',
        rect(44, bus_y + 6, 168, 24, c["bg"], c["border"], r=5),
        text(128, bus_y + 23, "Kafka · event bus", c["green"], 13, MONO, "middle"),
        text(W - 44, bus_y + 23, "outbox · DLQ · exponential backoff · circuit breakers",
             c["muted"], 12, MONO, "end"),
    ]

    rail_y, rail_w = 296, (W - 64 - 14) / 2
    for i, (name, items, hue) in enumerate(RAILS):
        x = 32 + i * (rail_w + 14)
        body += [
            rect(x, rail_y, rail_w, 46, c["panel"], c["border"]),
            text(x + 16, rail_y + 20, name, c[hue], 11, MONO, "start", "600", "1.6"),
            text(x + 16, rail_y + 36, items, c["muted"], 12, MONO),
        ]

    return svg(W, h, STACK_ALT, body)


# --------------------------------------------------------------------------- #
# activity: the latest public contributions, every type, colour-coded
# --------------------------------------------------------------------------- #

KINDS = {
    "merged": ("merged PR", "purple"),
    "pr": ("pull request", "purple"),
    "review": ("review", "blue"),
    "issue": ("issue", "green"),
    "comment": ("comment", "green"),
    "commit": ("push", "blue"),
    "release": ("release", "amber"),
    "create": ("created", "amber"),
    "fork": ("fork", "muted"),
    "star": ("star", "muted"),
}

TALLY_ORDER = [("merged", "merged"), ("pr", "PRs"), ("review", "reviews"),
               ("issue", "issues"), ("commit", "pushes"), ("release", "releases")]


def activity(c, data):
    act = data.get("activity", {})
    rows, tally = act.get("rows", []), act.get("tally", {})
    row_h, top = 32, 118
    h = top + max(1, len(rows)) * row_h + 16

    body = [rect(0.5, 0.5, W - 1, h - 1, c["bg"], c["border"], r=8)]
    body += [
        text(32, 40, "recent contributions", c["muted"], 13, SANS),
        text(W - 32, 40, f"refreshed {data.get('updated', '—')} · public events, last 90 days",
             c["faint"], 11, MONO, "end"),
    ]

    # tally chips
    x = 32
    for key, label in TALLY_ORDER:
        n = tally.get(key, 0)
        if not n:
            continue
        hue = c[KINDS[key][1]] if KINDS[key][1] != "muted" else c["muted"]
        cw = 26 + (len(f"{n} {label}")) * 7.6
        body += [
            rect(x, 56, cw, 30, c["panel"], c["border"], r=15),
            text(x + 14, 76, f"{n} ", hue, 13, MONO, "start", "600"),
            text(x + 14 + len(str(n)) * 7.8 + 7.8, 76, label, c["muted"], 13, MONO),
        ]
        x += cw + 8

    if not rows:
        body.append(text(W / 2, top + 24, "no public activity in the last 90 days",
                         c["faint"], 13, MONO, "middle"))
        return svg(W, h, "Recent GitHub contributions", body)

    alt = ["Recent GitHub contributions:"]
    for i, r in enumerate(rows):
        y = top + i * row_h
        label, hue = KINDS.get(r["kind"], ("activity", "muted"))
        col = c[hue] if hue != "muted" else c["muted"]
        body += [
            rect(32, y, W - 64, row_h - 6, c["panel"], c["border"], r=5),
            rect(44, y + 5, 108, 16, c["bg"], col, r=8),
            text(98, y + 17, label, col, 10.5, MONO, "middle", "600"),
            text(168, y + 18, trunc(r["repo"], 34), c["text"], 12.5, MONO),
            text(444, y + 18, trunc(r["detail"], 72), c["muted"], 12.5, MONO),
            text(W - 44, y + 18, ago(r["at"]), c["faint"], 11.5, MONO, "end"),
        ]
        alt.append(f"{label} in {r['repo']} — {trunc(r['detail'], 72)} ({ago(r['at'])} ago)")

    return svg(W, h, " ".join(alt), body)


# --------------------------------------------------------------------------- #

def main():
    data = load_data()
    for theme, c in THEMES.items():
        (ROOT / f"{theme}_mode.svg").write_text(hero(theme, c, data))
        for name, fn in (("impact", impact), ("stack", stack), ("activity", activity)):
            (OUT / f"{name}-{theme}.svg").write_text(fn(c, data))
        print(f"  wrote {theme}_mode.svg + assets/{{impact,stack,activity}}-{theme}.svg")

    s = data.get("stats", {})
    print(f"  uptime {uptime()} · {s.get('repos', 0)} repos · {s.get('stars', 0)} stars · "
          f"{s.get('commits', 0)} commits · {s.get('followers', 0)} followers")


if __name__ == "__main__":
    main()
