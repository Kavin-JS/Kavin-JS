#!/usr/bin/env python3
"""
Builds three live tiles for the profile README, in the same style as the rest of the page:

    assets/stats.svg      GitHub + LeetCode numbers, language mix
    assets/skyline.svg    3D contribution skyline from your real contribution calendar
    assets/activity.svg   your most recently pushed public repos

Standard library only. Run by .github/workflows/stats.yml twice a day; also safe to run locally:

    GITHUB_TOKEN=ghp_xxx python scripts/build_stats.py      # full data
    python scripts/build_stats.py                           # no token: calendar is scraped, the rest uses SNAPSHOT_*

Every data source falls back to something sensible instead of failing the run.
"""
import json, math, os, re, sys, datetime as dt, urllib.request
from html import escape

GH_USER = os.environ.get("GH_USER", "Kavin-JS")
LC_USER = os.environ.get("LC_USER", "kavinjs")
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets")
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

MONO = "ui-monospace, SFMono-Regular, Menlo, Consolas, 'Liberation Mono', monospace"
SANS = "'Segoe UI', system-ui, -apple-system, 'Helvetica Neue', Arial, sans-serif"
CYAN, VIOLET, PINK, GREEN, AMBER, BLUE = "#22d3ee", "#a78bfa", "#f472b6", "#34d399", "#fbbf24", "#3b82f6"


# ============================================================================================ fetching
def http(url, data=None, headers=None):
    h = {"User-Agent": UA, **(headers or {})}
    req = urllib.request.Request(url, data=data, headers=h)
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


# ============================================================================================ helpers
def hold(attr, zero, final, delay, dur):
    """Hold `zero` for `delay` s, then animate to `final` and freeze (element attr = final, so no-SMIL viewers see the end state)."""
    tot = delay + dur
    kt = f"0;{delay/tot:.4f};1" if delay > 0 else "0;0;1"
    return f'<animate attributeName="{attr}" values="{zero};{zero};{final}" keyTimes="{kt}" dur="{tot:.2f}s" fill="freeze"/>'


def tile_open(W, H, a1, a2, label_id="Live tile"):
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" aria-label="{escape(label_id)}">
<defs>
  <linearGradient id="tbg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#121b2e"/><stop offset="1" stop-color="#090e18"/></linearGradient>
  <radialGradient id="b1" cx="50%" cy="50%" r="50%"><stop offset="0" stop-color="{a1}" stop-opacity="0.3"/><stop offset="1" stop-color="{a1}" stop-opacity="0"/></radialGradient>
  <radialGradient id="b2" cx="50%" cy="50%" r="50%"><stop offset="0" stop-color="{a2}" stop-opacity="0.26"/><stop offset="1" stop-color="{a2}" stop-opacity="0"/></radialGradient>
  <pattern id="dots" width="22" height="22" patternUnits="userSpaceOnUse"><circle cx="2" cy="2" r="1" fill="#fff" fill-opacity="0.07"/></pattern>
  <clipPath id="clipT"><rect width="{W}" height="{H}" rx="22"/></clipPath>
</defs>
<g clip-path="url(#clipT)">
  <rect width="{W}" height="{H}" fill="url(#tbg)"/><rect width="{W}" height="{H}" fill="url(#dots)"/>
  <circle cx="{W-100}" cy="-20" r="300" fill="url(#b1)"/><circle cx="40" cy="{H+20}" r="260" fill="url(#b2)"/>'''


def tile_close(W, H):
    return f'''
</g>
<rect x="0.5" y="0.5" width="{W-1}" height="{H-1}" rx="22" fill="none" stroke="#fff" stroke-opacity="0.1"/>
</svg>'''


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


# ============================================================================================ stats tile
def render_stats(gh, lc, live):
    W, H = 1000, 340
    metrics = [("REPOSITORIES", gh["repos"]), ("STARS", gh["stars"]), ("FOLLOWERS", gh["followers"]), ("CONTRIBUTIONS / YR", gh.get("contribs"))]
    metrics = [(k, v) for k, v in metrics if v is not None]
    left = []
    for i, (k, v) in enumerate(metrics):
        x, y = 40 + (i % 2) * 150, 118 + (i // 2) * 98
        left.append(f'<g transform="translate({x},{y})">{hold("opacity","0","1",0.2+i*0.15,0.5)}'
                    f'<text font-family="{SANS}" font-size="46" font-weight="800" fill="#f0f4ff">{v:,}</text>'
                    f'<text y="24" font-family="{MONO}" font-size="10" letter-spacing="1.5" fill="#7f8ea3">{k}</text></g>')
    streak_line = ""
    if gh.get("streak") is not None:
        streak_line = f'<text x="40" y="306" font-family="{MONO}" font-size="12" fill="{CYAN}">GitHub streak {gh["streak"]}d · longest {gh["longest"]}d</text>'
    cx, cy, r, sw = 478, 176, 66, 20
    C = 2 * math.pi * r
    segs = []
    if lc.get("easy") is not None and lc["total"]:
        parts = [("Easy", lc["easy"], GREEN), ("Medium", lc["medium"], AMBER), ("Hard", lc["hard"], PINK)]
        tot = sum(p[1] for p in parts) or 1
        off, gap = 0.0, 4
        for i, (n, v, c) in enumerate(parts):
            ln = max(0, v / tot * C - gap)
            segs.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{c}" stroke-width="{sw}" stroke-dasharray="{ln:.1f} {C-ln:.1f}" stroke-dashoffset="{-off:.1f}" transform="rotate(-90 {cx} {cy})">{hold("stroke-dasharray", "0 "+f"{C:.1f}", f"{ln:.1f} {C-ln:.1f}", 0.3+i*0.35, 0.9)}</circle>')
            off += v / tot * C
        legend = "".join(f'<g transform="translate(580,{138+i*34})"><circle r="5" cx="0" cy="-4" fill="{c}"/><text x="14" font-family="{SANS}" font-size="15" font-weight="700" fill="#e6edf3">{v}</text><text x="52" font-family="{MONO}" font-size="11" fill="#7f8ea3">{n.upper()}</text></g>' for i, (n, v, c) in enumerate(parts))
        total_txt = f'{lc["total"]}'
    else:
        segs.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{CYAN}" stroke-opacity="0.7" stroke-width="{sw}" stroke-dasharray="6 5"/>')
        legend = "".join(f'<text x="580" y="{160+i*20}" font-family="{MONO}" font-size="11" fill="#7f8ea3">{t}</text>' for i, t in enumerate(["difficulty split", "appears after the", "next Action run"]))
        total_txt = f'{lc["total"]}+'
    lc_streak = f'<text x="400" y="306" font-family="{MONO}" font-size="12" fill="{AMBER}">LeetCode streak {lc["streak"]}d</text>' if lc.get("streak") is not None else ""
    langs = gh["langs"][:5]
    tot = sum(n for _, n, _ in langs) or 1
    bar, rows, x = [], [], 0.0
    for i, (n, cnt, col) in enumerate(langs):
        w = cnt / tot * 240
        bar.append(f'<rect x="{x:.1f}" y="0" width="{max(w-2,1):.1f}" height="12" fill="{col}">{hold("width","0",f"{max(w-2,1):.1f}",0.3+i*0.2,0.7)}</rect>')
        x += w
        rows.append(f'<g transform="translate(0,{44+i*30})"><circle cx="5" cy="-4" r="5" fill="{col}"/><text x="18" font-family="{SANS}" font-size="14" font-weight="600" fill="#e6edf3">{escape(n)}</text><text x="240" text-anchor="end" font-family="{MONO}" font-size="12" fill="#7f8ea3">{cnt/tot*100:.0f}%</text></g>')
    return (tile_open(W, H, CYAN, VIOLET, "Live GitHub and LeetCode stats") + f'''
  <text x="40" y="52" font-family="{MONO}" font-size="12" letter-spacing="2" fill="{CYAN}">GITHUB</text>
  <text x="400" y="52" font-family="{MONO}" font-size="12" letter-spacing="2" fill="{AMBER}">LEETCODE</text>
  <text x="720" y="52" font-family="{MONO}" font-size="12" letter-spacing="2" fill="{VIOLET}">TOP LANGUAGES (BY REPO)</text>
  <line x1="370" y1="40" x2="370" y2="300" stroke="#fff" stroke-opacity="0.08"/><line x1="690" y1="40" x2="690" y2="300" stroke="#fff" stroke-opacity="0.08"/>
  {"".join(left)}
  <circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="#fff" stroke-opacity="0.06" stroke-width="{sw}"/>
  {"".join(segs)}
  <text x="{cx}" y="{cy+10}" text-anchor="middle" font-family="{SANS}" font-size="34" font-weight="800" fill="#f0f4ff">{total_txt}</text>
  <text x="{cx}" y="{cy+30}" text-anchor="middle" font-family="{MONO}" font-size="10" letter-spacing="2" fill="#7f8ea3">SOLVED</text>
  {legend}
  <g transform="translate(720,84)">{"".join(bar)}</g>
  <g transform="translate(720,92)">{"".join(rows)}</g>
  {streak_line}{lc_streak}
  <text x="{W-30}" y="{H-18}" text-anchor="end" font-family="{MONO}" font-size="10" fill="#566275">{stamp_text(live)}</text>''' + tile_close(W, H))


# ============================================================================================ skyline tile
def _shade(hexc, f):
    r, g, b = (int(hexc[i:i + 2], 16) for i in (1, 3, 5))
    return "#%02x%02x%02x" % (min(255, int(r * f)), min(255, int(g * f)), min(255, int(b * f)))


def render_skyline(days, live):
    W = 1000
    first = dt.date.fromisoformat(days[0][0])
    first_sun = first - dt.timedelta(days=(first.weekday() + 1) % 7)
    cells = []
    for ds, n in days:
        d = dt.date.fromisoformat(ds)
        cells.append(((d - first_sun).days // 7, (d.weekday() + 1) % 7, n))
    nweeks = max(c[0] for c in cells) + 1
    counts = [c[2] for c in cells]
    nz = sorted(n for n in counts if n > 0)
    maxn = max(counts) if counts else 0
    if nz:
        t1, t2, t3 = nz[len(nz) // 4], nz[len(nz) // 2], nz[(3 * len(nz)) // 4]
    level = lambda n: 0 if n == 0 else (1 if n <= t1 else 2 if n <= t2 else 3 if n <= t3 else 4)
    pal = {1: "#3b82f6", 2: "#22d3ee", 3: "#a78bfa", 4: "#f472b6"}
    ax, ay, bx, by, f, HMAX = 16.4, 3.0, -5.2, 8.2, 0.84, 78
    # bounding box -> centre horizontally, fixed header/footer
    minx = min(0, 6 * bx); maxx = (nweeks - 1) * ax + ax * f
    ox = (W - (maxx - minx)) / 2 - minx
    top, foot = 70, 56
    oy = top + HMAX + 4
    H = int(oy + (nweeks - 1) * ay + 6 * by + by * f + foot)
    weeks = {}
    for w, d, n in cells:
        weeks.setdefault(w, []).append((d, n))
    out = []
    for w in sorted(weeks):
        g = []
        for d, n in sorted(weeks[w]):
            px, py = ox + w * ax + d * bx, oy + w * ay + d * by
            a1x, a1y, b1x, b1y = ax * f, ay * f, bx * f, by * f
            P = [(px, py), (px + a1x, py + a1y), (px + a1x + b1x, py + a1y + b1y), (px + b1x, py + b1y)]
            pts = lambda L: " ".join(f"{x:.1f},{y:.1f}" for x, y in L)
            lv = level(n)
            if lv == 0:
                g.append(f'<polygon points="{pts(P)}" fill="#1a2539"/>')
                continue
            h = 5 + (n / maxn) ** 0.65 * HMAX
            c = pal[lv]
            top_f = [(x, y - h) for x, y in P]
            front = [P[3], P[2], (P[2][0], P[2][1] - h), (P[3][0], P[3][1] - h)]
            right = [P[1], P[2], (P[2][0], P[2][1] - h), (P[1][0], P[1][1] - h)]
            g.append(f'<polygon points="{pts(front)}" fill="{_shade(c, 0.62)}"/><polygon points="{pts(right)}" fill="{_shade(c, 0.42)}"/><polygon points="{pts(top_f)}" fill="{c}"/>')
        delay = w * 0.035
        tot = delay + 0.7
        kt = f"0;{delay/tot:.4f};1"
        anim = (f'<animateTransform attributeName="transform" type="translate" values="0 -40;0 -40;0 0" keyTimes="{kt}" dur="{tot:.2f}s" fill="freeze"/>'
                + hold("opacity", "0", "1", delay, 0.7))
        out.append(f"<g>{anim}{''.join(g)}</g>")
    total = sum(counts)
    active = sum(1 for n in counts if n)
    cur, best = streaks(days)
    legend = "".join(f'<rect x="{W-168+i*18}" y="{H-36}" width="12" height="12" rx="3" fill="{c}"/>' for i, c in enumerate(["#1a2539", "#3b82f6", "#22d3ee", "#a78bfa", "#f472b6"]))
    return (tile_open(W, H, VIOLET, PINK, "Contribution skyline") + f'''
  <text x="40" y="52" font-family="{MONO}" font-size="12" letter-spacing="2" fill="{VIOLET}">CONTRIBUTION SKYLINE</text>
  <text x="{W-40}" y="52" text-anchor="end" font-family="{SANS}" font-size="13" fill="#8ea0b8">contributions in the last year</text>
  <text x="{W-244}" y="53" text-anchor="end" font-family="{SANS}" font-size="22" font-weight="800" fill="#f0f4ff">{total:,}</text>
  {"".join(out)}
  <text x="40" y="{H-24}" font-family="{MONO}" font-size="12" fill="#8ea0b8">{active} active days · best day {maxn} · current streak {cur}d · longest {best}d</text>
  <text x="{W-178}" y="{H-26}" text-anchor="end" font-family="{MONO}" font-size="10" fill="#566275">less</text>
  {legend}
  <text x="{W-30}" y="{H-8}" text-anchor="end" font-family="{MONO}" font-size="9" fill="#566275">{stamp_text(live)}</text>''' + tile_close(W, H)), dict(total=total, active=active, best=maxn, cur=cur, longest=best)


# ============================================================================================ activity tile
def render_activity(recent, live):
    W, H = 1000, 352
    items = recent[:6]
    out = []
    for i, (name, desc, pushed, lang, col) in enumerate(items):
        cx_, cy_ = 40 + (i % 2) * 470, 98 + (i // 2) * 84
        lang_txt = f'<circle cx="5" cy="{48}" r="4.5" fill="{col}"/><text x="16" y="52" font-family="{MONO}" font-size="11" fill="#8ea0b8">{escape(lang)}</text>' if lang else ""
        out.append(f'''<g transform="translate({cx_},{cy_})">{hold("opacity","0","1",0.2+i*0.18,0.5)}
    <rect x="-14" y="-4" width="3" height="52" rx="1.5" fill="{col}"/>
    <text font-family="{SANS}" font-size="16.5" font-weight="800" fill="#f0f4ff">{escape(trunc(name, 32))}</text>
    <text x="430" text-anchor="end" font-family="{MONO}" font-size="11" fill="{CYAN}">{rel_time(pushed)}</text>
    <text y="22" font-family="{SANS}" font-size="13" fill="#a8b8cd">{escape(trunc(desc, 66))}</text>
    {lang_txt}</g>''')
    return (tile_open(W, H, CYAN, GREEN, "Latest activity") + f'''
  <text x="40" y="52" font-family="{MONO}" font-size="12" letter-spacing="2" fill="{CYAN}">LATEST ACTIVITY</text>
  <circle cx="{W-44}" cy="48" r="5" fill="{GREEN}"><animate attributeName="opacity" values="1;0.2;1" dur="1.4s" repeatCount="indefinite"/></circle>
  <text x="{W-58}" y="52" text-anchor="end" font-family="{MONO}" font-size="11" fill="#8ea0b8">most recently pushed public repos</text>
  {"".join(out)}
  <text x="{W-30}" y="{H-18}" text-anchor="end" font-family="{MONO}" font-size="10" fill="#566275">{stamp_text(live)}</text>''' + tile_close(W, H))


# ============================================================================================ main
def main():
    live_gh = False
    days = None
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
        lc = fetch_leetcode(); live_lc = True
    except Exception as e:
        print("LeetCode unavailable, using snapshot:", e, file=sys.stderr)
        lc, live_lc = SNAPSHOT_LC, False

    os.makedirs(OUT_DIR, exist_ok=True)
    def write(name, text):
        with open(os.path.join(OUT_DIR, name), "w", encoding="utf-8") as f:
            f.write(text)
        print("wrote", name)

    if days:
        sky, summary = render_skyline(days, live_cal)
        gh["contribs"] = summary["total"]
        gh["streak"], gh["longest"] = streaks(days)
        write("skyline.svg", sky)
    write("stats.svg", render_stats(gh, lc, live_gh or live_lc or live_cal))
    write("activity.svg", render_activity(gh["recent"], live_gh))


if __name__ == "__main__":
    main()
