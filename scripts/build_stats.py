#!/usr/bin/env python3
"""
Builds the live tiles for the profile README, in light and dark variants:

    assets/{dark,light}/stats.svg      GitHub + LeetCode numbers, language mix
    assets/{dark,light}/skyline.svg    contribution skyline from your real calendar
    assets/{dark,light}/activity.svg   most recently pushed public repos

Standard library only. Run by .github/workflows/stats.yml twice a day; also safe to run locally:

    GITHUB_TOKEN=ghp_xxx python scripts/build_stats.py      # full data
    python scripts/build_stats.py                           # no token: calendar is scraped, the rest uses SNAPSHOT_*

Every data source falls back to something sensible instead of failing the run.
"""
import json, math, os, re, sys, datetime as dt, urllib.request
from html import escape

GH_USER = os.environ.get("GH_USER", "Kavin-JS")
LC_USER = os.environ.get("LC_USER", "kavinjs")
ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets")
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"

# ---- shown when a live fetch fails (edit freely) ------------------------------------------------------
SNAPSHOT_GH = dict(
    repos=22, stars=1, followers=2, contribs=None, streak=None, longest=None,
    langs=[("HTML", 7, "#e34c26"), ("Python", 4, "#3572A5"), ("JavaScript", 3, "#f1e05a"), ("C", 2, "#8b949e"), ("Java", 1, "#b07219")],
    recent=[
        ("BLE-Classroom-Presence", "Multi-node BLE classroom presence verification using ESP32, RSSI observations and rule-based checks", "2026-09-29T04:43:36Z", "HTML", "#e34c26"),
        ("kavin-js.github.io", "Personal portfolio website: B.Tech CSE, Amrita Vishwa Vidyapeetham", "2026-09-27T16:51:00Z", "HTML", "#e34c26"),
        ("Real-Time-Recommendation-System", "Deep learning-based real-time recommendation system with heuristic ranking", "2026-09-27T07:09:42Z", None, "#8b949e"),
        ("AIKA", "AI Knowledge System: modular assistant for knowledge, tasks, reasoning and interaction", "2026-09-27T06:33:15Z", "JavaScript", "#f1e05a"),
        ("RagForge", "Production-grade RAG pipeline: hybrid retrieval, cross-encoder reranking, adaptive routing", "2026-09-27T05:53:13Z", "Python", "#3572A5"),
        ("AMLC26", "Business Entity Resolution: Unstop ML Challenge", "2026-09-26T13:37:24Z", "Python", "#3572A5"),
    ],
)
SNAPSHOT_LC = dict(total=100, easy=None, medium=None, hard=None, streak=None)   # README says 100+
# ----------------------------------------------------------------------------------------------------------

SANS = "-apple-system, BlinkMacSystemFont, 'Segoe UI', 'Noto Sans', Helvetica, Arial, sans-serif"
MONO = "ui-monospace, SFMono-Regular, 'SF Mono', Menlo, Consolas, 'Liberation Mono', monospace"

# One accent, neutral everything else. Matches GitHub's own light/dark palettes so the tiles sit naturally on the page.
DARK = dict(name="dark", bg="#161b22", border="#30363d", text="#e6edf3", sub="#9da7b3", mute="#6e7681", accent="#4493f8", good="#3fb950", line="#484f58", grid="#21262d",
            sky=["#222a36", "#1f4b82", "#2a6ac0", "#3b86ec", "#79b8ff"])
LIGHT = dict(name="light", bg="#f6f8fa", border="#d0d7de", text="#1f2328", sub="#59636e", mute="#818b98", accent="#0969da", good="#1a7f37", line="#afb8c1", grid="#eaeef2",
             sky=["#e1e7ee", "#b6d4fb", "#7fb2f5", "#3b86ec", "#0a4ea8"])
THEMES = (DARK, LIGHT)


# ============================================================================================ fetching
def http(url, data=None, headers=None):
    req = urllib.request.Request(url, data=data, headers={"User-Agent": UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.read().decode("utf-8", "replace")


def post_json(url, payload, headers):
    return json.loads(http(url, json.dumps(payload).encode(), {"Content-Type": "application/json", **headers}))


def scrape_calendar(user):
    """Public contribution calendar (no token needed)."""
    page = http(f"https://github.com/users/{user}/contributions")
    tips = dict(re.findall(r'<tool-tip\b[^>]*\bfor="([^"]+)"[^>]*>([^<]*)</tool-tip>', page))
    days = []
    for td in re.findall(r'<td\b[^>]*\bdata-date="[^"]+"[^>]*>', page):
        d = re.search(r'data-date="([^"]+)"', td).group(1)
        cid = re.search(r'\bid="(contribution-day-component-[^"]+)"', td)
        m = re.match(r"\s*(\d+)\s+contribution", tips.get(cid.group(1), "") if cid else "")
        days.append((d, int(m.group(1)) if m else 0))
    if not days:
        raise RuntimeError("calendar not found")
    return sorted(days)


def fetch_github():
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        raise RuntimeError("no GITHUB_TOKEN")
    q = """query($u:String!){ user(login:$u){
        followers{totalCount}
        repositories(privacy:PUBLIC, ownerAffiliations:OWNER, isFork:false, first:100){ totalCount nodes{ stargazerCount primaryLanguage{name color} } }
        recent: repositories(privacy:PUBLIC, ownerAffiliations:OWNER, isFork:false, first:20, orderBy:{field:PUSHED_AT, direction:DESC}){ nodes{ name description pushedAt primaryLanguage{name color} } }
        contributionsCollection{ contributionCalendar{ totalContributions weeks{ contributionDays{ contributionCount date } } } } } }"""
    d = post_json("https://api.github.com/graphql", {"query": q, "variables": {"u": GH_USER}}, {"Authorization": f"bearer {token}"})
    u = d["data"]["user"]
    repos = u["repositories"]["nodes"]
    langs = {}
    for r in repos:
        pl = r.get("primaryLanguage")
        if pl:
            n, c = langs.get(pl["name"], (0, pl["color"] or "#8b949e"))
            langs[pl["name"]] = (n + 1, c)
    langs = sorted(((k, v[0], v[1]) for k, v in langs.items()), key=lambda t: (-t[1], t[0]))
    recent = []
    for r in u["recent"]["nodes"]:
        if r["name"].lower() == GH_USER.lower() or not (r.get("description") or "").strip():
            continue
        pl = r.get("primaryLanguage") or {}
        recent.append((r["name"], r["description"], r["pushedAt"], pl.get("name"), pl.get("color") or "#8b949e"))
    cal = u["contributionsCollection"]["contributionCalendar"]
    days = sorted((x["date"], x["contributionCount"]) for w in cal["weeks"] for x in w["contributionDays"])
    gh = dict(repos=u["repositories"]["totalCount"], stars=sum(r["stargazerCount"] for r in repos), followers=u["followers"]["totalCount"],
              langs=langs, recent=recent[:6] or SNAPSHOT_GH["recent"])
    return gh, days


def fetch_leetcode():
    q = "query($u:String!){ matchedUser(username:$u){ submitStats{ acSubmissionNum{ difficulty count } } userCalendar{ streak } } }"
    d = post_json("https://leetcode.com/graphql", {"query": q, "variables": {"u": LC_USER}}, {"Referer": "https://leetcode.com"})
    m = d["data"]["matchedUser"]
    ac = {x["difficulty"]: x["count"] for x in m["submitStats"]["acSubmissionNum"]}
    return dict(total=ac.get("All", 0), easy=ac.get("Easy", 0), medium=ac.get("Medium", 0), hard=ac.get("Hard", 0), streak=(m.get("userCalendar") or {}).get("streak"))


def streaks(days):
    cur = best = run = 0
    for _, c in days:
        run = run + 1 if c > 0 else 0
        best = max(best, run)
    i = len(days) - 1
    if i >= 0 and days[i][1] == 0:       # today may not have a contribution yet
        i -= 1
    while i >= 0 and days[i][1] > 0:
        cur += 1; i -= 1
    return cur, best


# ============================================================================================ shared drawing helpers
def hold(attr, zero, final, delay, dur):
    """Hold `zero` for `delay` s, then animate to `final` and freeze. The element's own attribute is `final`,
    so viewers without SMIL support simply show the finished state."""
    tot = delay + dur
    kt = f"0;{delay/tot:.4f};1" if delay > 0 else "0;0;1"
    return f'<animate attributeName="{attr}" values="{zero};{zero};{final}" keyTimes="{kt}" dur="{tot:.2f}s" fill="freeze"/>'


def frame_open(W, H, P, label):
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" aria-label="{escape(label)}">
<defs><clipPath id="c"><rect width="{W}" height="{H}" rx="12"/></clipPath></defs>
<g clip-path="url(#c)">
<rect width="{W}" height="{H}" fill="{P["bg"]}"/>'''


def frame_close(W, H, P):
    return f'''
</g>
<rect x="0.5" y="0.5" width="{W-1}" height="{H-1}" rx="12" fill="none" stroke="{P["border"]}"/>
</svg>'''


def label(x, y, text, P, anchor="start"):
    return f'<text x="{x}" y="{y}" text-anchor="{anchor}" font-family="{MONO}" font-size="11" letter-spacing="1.4" fill="{P["mute"]}">{escape(text)}</text>'


def now_utc():
    return dt.datetime.now(dt.timezone.utc)


def rel_time(iso):
    t = dt.datetime.fromisoformat(iso.replace("Z", "+00:00"))
    s = max(0, (now_utc() - t).total_seconds())
    if s < 3600: return f"{int(s // 60)}m ago"
    if s < 86400: return f"{int(s // 3600)}h ago"
    if s < 86400 * 30: return f"{int(s // 86400)}d ago"
    if s < 86400 * 365: return f"{int(s // (86400 * 30))}mo ago"
    return f"{int(s // (86400 * 365))}y ago"


def trunc(s, n):
    s = " ".join((s or "").split())
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def stamp_text(live):
    if not live:
        return "snapshot · refreshes on the next Action run"
    where = "GitHub Actions" if os.environ.get("GITHUB_ACTIONS") else "built locally"
    return f"updated {now_utc():%Y-%m-%d} UTC · {where}"


def stamp(W, H, P, live):
    return f'<text x="{W-24}" y="{H-14}" text-anchor="end" font-family="{MONO}" font-size="10" fill="{P["mute"]}">{stamp_text(live)}</text>'


# ============================================================================================ stats tile
def render_stats(P, gh, lc, live):
    W, H = 1000, 292
    acc, txt, sub, mute, bd = P["accent"], P["text"], P["sub"], P["mute"], P["border"]
    metrics = [("Repositories", gh["repos"]), ("Stars", gh["stars"]), ("Followers", gh["followers"]), ("Contributions, 12 mo", gh.get("contribs"))]
    metrics = [(k, v) for k, v in metrics if v is not None]
    left = []
    for i, (k, v) in enumerate(metrics):
        x, y = 32 + (i % 2) * 160, 104 + (i // 2) * 84
        left.append(f'<g transform="translate({x},{y})">{hold("opacity","0","1",0.15+i*0.12,0.5)}'
                    f'<text font-family="{SANS}" font-size="36" font-weight="600" fill="{txt}">{v:,}</text>'
                    f'<text y="22" font-family="{SANS}" font-size="12" fill="{sub}">{k}</text></g>')
    extra = ""
    if gh.get("streak") is not None:
        extra = f'<text x="32" y="{H-40}" font-family="{SANS}" font-size="12" fill="{sub}">Streak <tspan fill="{txt}" font-weight="600">{gh["streak"]}d</tspan>  ·  longest <tspan fill="{txt}" font-weight="600">{gh["longest"]}d</tspan></text>'
    cx, cy, r, sw = 452, 142, 52, 10
    C = 2 * math.pi * r
    segs, legend = [], ""
    if lc.get("easy") is not None and lc["total"]:
        parts = [("Easy", lc["easy"], 0.38), ("Medium", lc["medium"], 0.68), ("Hard", lc["hard"], 1.0)]
        tot = sum(p[1] for p in parts) or 1
        off, gap = 0.0, 3
        for i, (n, v, op) in enumerate(parts):
            ln = max(0, v / tot * C - gap)
            segs.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{acc}" stroke-opacity="{op}" stroke-width="{sw}" stroke-dasharray="{ln:.1f} {C-ln:.1f}" stroke-dashoffset="{-off:.1f}" transform="rotate(-90 {cx} {cy})">{hold("stroke-dasharray", "0 "+f"{C:.1f}", f"{ln:.1f} {C-ln:.1f}", 0.3+i*0.3, 0.8)}</circle>')
            off += v / tot * C
        legend = "".join(f'<g transform="translate(548,{118+i*26})"><circle r="4" cy="-4" fill="{acc}" fill-opacity="{op}"/><text x="14" font-family="{SANS}" font-size="14" font-weight="600" fill="{txt}">{v}</text><text x="50" font-family="{SANS}" font-size="12" fill="{sub}">{n}</text></g>' for i, (n, v, op) in enumerate(parts))
        total_txt = f'{lc["total"]}'
    else:
        segs.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{acc}" stroke-opacity="0.35" stroke-width="{sw}"/>')
        legend = "".join(f'<text x="548" y="{128+i*18}" font-family="{SANS}" font-size="12" fill="{mute}">{t}</text>' for i, t in enumerate(["Difficulty split", "appears after the", "next scheduled run"]))
        total_txt = f'{lc["total"]}+'
    lc_streak = f'<text x="360" y="{H-40}" font-family="{SANS}" font-size="12" fill="{sub}">Streak <tspan fill="{txt}" font-weight="600">{lc["streak"]}d</tspan></text>' if lc.get("streak") is not None else ""
    langs = gh["langs"][:5]
    tot = sum(n for _, n, _ in langs) or 1
    bar, rows, x = [], [], 0.0
    for i, (n, cnt, col) in enumerate(langs):
        w = cnt / tot * 264
        bar.append(f'<rect x="{x:.1f}" y="0" width="{max(w-2,1):.1f}" height="8" rx="2" fill="{col}">{hold("width","0",f"{max(w-2,1):.1f}",0.3+i*0.15,0.6)}</rect>')
        x += w
        rows.append(f'<g transform="translate(0,{38+i*26})"><circle cx="5" cy="-4" r="4.5" fill="{col}"/><text x="18" font-family="{SANS}" font-size="13" fill="{txt}">{escape(n)}</text><text x="264" text-anchor="end" font-family="{SANS}" font-size="12" fill="{sub}">{cnt/tot*100:.0f}%</text></g>')
    return (frame_open(W, H, P, "GitHub and LeetCode statistics") + f'''
  {label(32, 44, "GITHUB", P)}{label(360, 44, "LEETCODE", P)}{label(704, 44, "LANGUAGES, BY REPOSITORY", P)}
  <line x1="332" y1="32" x2="332" y2="{H-32}" stroke="{bd}"/><line x1="676" y1="32" x2="676" y2="{H-32}" stroke="{bd}"/>
  {"".join(left)}
  <circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{bd}" stroke-width="{sw}"/>
  {"".join(segs)}
  <text x="{cx}" y="{cy+6}" text-anchor="middle" font-family="{SANS}" font-size="26" font-weight="600" fill="{txt}">{total_txt}</text>
  <text x="{cx}" y="{cy+24}" text-anchor="middle" font-family="{SANS}" font-size="11" fill="{mute}">solved</text>
  {legend}
  <g transform="translate(704,76)">{"".join(bar)}</g><g transform="translate(704,86)">{"".join(rows)}</g>
  {extra}{lc_streak}{stamp(W, H, P, live)}''' + frame_close(W, H, P))


# ============================================================================================ skyline tile
def _shade(hexc, f):
    r, g, b = (int(hexc[i:i + 2], 16) for i in (1, 3, 5))
    return "#%02x%02x%02x" % (min(255, int(r * f)), min(255, int(g * f)), min(255, int(b * f)))


def render_skyline(P, days, live):
    W = 1000
    acc, txt, sub, mute = P["accent"], P["text"], P["sub"], P["mute"]
    first = dt.date.fromisoformat(days[0][0])
    first_sun = first - dt.timedelta(days=(first.weekday() + 1) % 7)
    cells = [(((dt.date.fromisoformat(ds) - first_sun).days // 7), (dt.date.fromisoformat(ds).weekday() + 1) % 7, n) for ds, n in days]
    nweeks = max(c[0] for c in cells) + 1
    counts = [c[2] for c in cells]
    nz = sorted(n for n in counts if n > 0)
    maxn = max(counts) if counts else 0
    t1 = t2 = t3 = 0
    if nz:
        t1, t2, t3 = nz[len(nz) // 4], nz[len(nz) // 2], nz[(3 * len(nz)) // 4]
    level = lambda n: 0 if n == 0 else (1 if n <= t1 else 2 if n <= t2 else 3 if n <= t3 else 4)
    ax, ay, bx, by, f, HMAX = 16.4, 3.0, -5.2, 8.2, 0.84, 78
    minx = min(0, 6 * bx); maxx = (nweeks - 1) * ax + ax * f
    ox = (W - (maxx - minx)) / 2 - minx
    top, foot = 58, 60
    oy = top + HMAX + 4
    H = int(oy + (nweeks - 1) * ay + 6 * by + by * f + foot)
    weeks = {}
    for w, d, n in cells:
        weeks.setdefault(w, []).append((d, n))
    pts = lambda L: " ".join(f"{x:.1f},{y:.1f}" for x, y in L)
    out = []
    for w in sorted(weeks):
        g = []
        for d, n in sorted(weeks[w]):
            px, py = ox + w * ax + d * bx, oy + w * ay + d * by
            a1x, a1y, b1x, b1y = ax * f, ay * f, bx * f, by * f
            Q = [(px, py), (px + a1x, py + a1y), (px + a1x + b1x, py + a1y + b1y), (px + b1x, py + b1y)]
            lv = level(n)
            if lv == 0:
                g.append(f'<polygon points="{pts(Q)}" fill="{P["sky"][0]}"/>')
                continue
            h = 4 + (n / maxn) ** 0.65 * HMAX
            c = P["sky"][lv]
            sh = (0.80, 0.62) if P["name"] == "light" else (0.66, 0.46)
            front = [Q[3], Q[2], (Q[2][0], Q[2][1] - h), (Q[3][0], Q[3][1] - h)]
            right = [Q[1], Q[2], (Q[2][0], Q[2][1] - h), (Q[1][0], Q[1][1] - h)]
            topf = [(x, y - h) for x, y in Q]
            g.append(f'<polygon points="{pts(front)}" fill="{_shade(c, sh[0])}"/><polygon points="{pts(right)}" fill="{_shade(c, sh[1])}"/><polygon points="{pts(topf)}" fill="{c}"/>')
        delay = w * 0.03
        tot = delay + 0.6
        kt = f"0;{delay/tot:.4f};1"
        anim = (f'<animateTransform attributeName="transform" type="translate" values="0 -30;0 -30;0 0" keyTimes="{kt}" dur="{tot:.2f}s" fill="freeze"/>' + hold("opacity", "0", "1", delay, 0.6))
        out.append(f"<g>{anim}{''.join(g)}</g>")
    total = sum(counts)
    active = sum(1 for n in counts if n)
    cur, best = streaks(days)
    legend = "".join(f'<rect x="{W-146+i*16}" y="{H-40}" width="11" height="11" rx="2.5" fill="{c}"/>' for i, c in enumerate(P["sky"]))
    return (frame_open(W, H, P, "Contribution skyline for the last year") + f'''
  {label(32, 44, "CONTRIBUTIONS, LAST YEAR", P)}
  <text x="{W-32}" y="48" text-anchor="end" font-family="{SANS}" font-size="26" font-weight="600" fill="{txt}">{total:,}</text>
  {"".join(out)}
  <text x="32" y="{H-30}" font-family="{SANS}" font-size="12" fill="{sub}">{active} active days  ·  best day {maxn}  ·  current streak {cur}d  ·  longest {best}d</text>
  <text x="{W-154}" y="{H-31}" text-anchor="end" font-family="{SANS}" font-size="11" fill="{mute}">Less</text>
  <text x="{W-60+0}" y="{H-31}" font-family="{SANS}" font-size="11" fill="{mute}" dx="-4">More</text>
  {legend}
  {stamp(W, H, P, live)}''' + frame_close(W, H, P)), dict(total=total)


# ============================================================================================ activity tile
def render_activity(P, recent, live):
    W, H = 1000, 334
    acc, txt, sub, mute, bd = P["accent"], P["text"], P["sub"], P["mute"], P["border"]
    out = []
    for i, (name, desc, pushed, lang, col) in enumerate(recent[:6]):
        x, y = 32 + (i % 2) * 484, 80 + (i // 2) * 80
        lang_txt = f'<circle cx="5" cy="45" r="4.5" fill="{col}"/><text x="16" y="49" font-family="{SANS}" font-size="12" fill="{mute}">{escape(lang)}</text>' if lang else ""
        out.append(f'''<g transform="translate({x},{y})">{hold("opacity","0","1",0.15+i*0.12,0.5)}
    <text font-family="{SANS}" font-size="15" font-weight="600" fill="{acc}">{escape(trunc(name, 34))}</text>
    <text x="436" text-anchor="end" font-family="{SANS}" font-size="12" fill="{mute}">{rel_time(pushed)}</text>
    <text y="22" font-family="{SANS}" font-size="13" fill="{sub}">{escape(trunc(desc, 68))}</text>
    {lang_txt}</g>''')
    seps = "".join(f'<line x1="32" y1="{y}" x2="{W-32}" y2="{y}" stroke="{bd}"/>' for y in (142, 222))
    return (frame_open(W, H, P, "Most recently pushed repositories") + f'''
  {label(32, 44, "RECENTLY PUSHED", P)}
  <line x1="{W/2}" y1="64" x2="{W/2}" y2="{H-34}" stroke="{bd}"/>
  {seps}
  {"".join(out)}
  {stamp(W, H, P, live)}''' + frame_close(W, H, P))


# ============================================================================================ main
def main():
    live_gh, days = False, None
    try:
        gh, days = fetch_github(); live_gh = True
    except Exception as e:
        print("GitHub API unavailable, using snapshot + public calendar:", e, file=sys.stderr)
        gh = dict(SNAPSHOT_GH)
    live_cal = live_gh
    if days is None:
        try:
            days = scrape_calendar(GH_USER); live_cal = True
        except Exception as e:
            print("Calendar scrape failed:", e, file=sys.stderr)
    try:
        lc = fetch_leetcode()
    except Exception as e:
        print("LeetCode unavailable, using snapshot:", e, file=sys.stderr)
        lc = SNAPSHOT_LC
    if days:
        gh["contribs"] = sum(n for _, n in days)
        gh["streak"], gh["longest"] = streaks(days)
    for P in THEMES:
        d = os.path.join(ASSETS, P["name"])
        os.makedirs(d, exist_ok=True)
        files = {"stats.svg": render_stats(P, gh, lc, live_gh or live_cal), "activity.svg": render_activity(P, gh["recent"], live_gh)}
        if days:
            files["skyline.svg"] = render_skyline(P, days, live_cal)[0]
        for name, text in files.items():
            with open(os.path.join(d, name), "w", encoding="utf-8") as f:
                f.write(text)
            print("wrote", P["name"] + "/" + name)


if __name__ == "__main__":
    main()
