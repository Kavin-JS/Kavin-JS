#!/usr/bin/env python3
"""
Builds assets/stats.svg: a live stats tile (GitHub + LeetCode) in the same style as the rest of the README.
Standard library only. Run by .github/workflows/stats.yml every day; safe to run locally:

    GITHUB_TOKEN=ghp_xxx python scripts/build_stats.py

If a data source is unreachable the script falls back to the SNAPSHOT values below instead of failing.
"""
import json, math, os, sys, datetime, urllib.request
from html import escape

GH_USER = os.environ.get("GH_USER", "Kavin-JS")
LC_USER = os.environ.get("LC_USER", "kavinjs")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets", "stats.svg")

# ---- edit these if you like: shown when a live fetch fails -----------------------------------------
SNAPSHOT_GH = dict(repos=22, stars=1, followers=2, contribs=None, streak=None, longest=None,
                   langs=[("HTML", 3, "#e34c26"), ("JavaScript", 1, "#f1e05a"), ("C", 1, "#9aa5b1")])
SNAPSHOT_LC = dict(total=100, easy=None, medium=None, hard=None, streak=None)   # README says 100+
# -----------------------------------------------------------------------------------------------------

MONO = "ui-monospace, SFMono-Regular, Menlo, Consolas, 'Liberation Mono', monospace"
SANS = "'Segoe UI', system-ui, -apple-system, 'Helvetica Neue', Arial, sans-serif"
CYAN, VIOLET, PINK, GREEN, AMBER = "#22d3ee", "#a78bfa", "#f472b6", "#34d399", "#fbbf24"


def post_json(url, payload, headers):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json", "User-Agent": "kjs-readme-stats", **headers})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def fetch_github():
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        raise RuntimeError("no GITHUB_TOKEN")
    q = """query($u:String!){ user(login:$u){
        followers{totalCount}
        repositories(privacy:PUBLIC, ownerAffiliations:OWNER, isFork:false, first:100){ totalCount nodes{ stargazerCount primaryLanguage{name color} } }
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
    langs = sorted(((k, v[0], v[1]) for k, v in langs.items()), key=lambda t: -t[1])
    cal = u["contributionsCollection"]["contributionCalendar"]
    days = [(x["date"], x["contributionCount"]) for w in cal["weeks"] for x in w["contributionDays"]]
    days.sort()
    cur = best = run = 0
    for _, c in days:
        run = run + 1 if c > 0 else 0
        best = max(best, run)
    i = len(days) - 1
    if i >= 0 and days[i][1] == 0:       # today may not have a contribution yet
        i -= 1
    while i >= 0 and days[i][1] > 0:
        cur += 1; i -= 1
    return dict(repos=u["repositories"]["totalCount"], stars=sum(r["stargazerCount"] for r in repos), followers=u["followers"]["totalCount"],
                contribs=cal["totalContributions"], streak=cur, longest=best, langs=langs)


def fetch_leetcode():
    q = "query($u:String!){ matchedUser(username:$u){ submitStats{ acSubmissionNum{ difficulty count } } userCalendar{ streak } } }"
    d = post_json("https://leetcode.com/graphql", {"query": q, "variables": {"u": LC_USER}}, {"Referer": "https://leetcode.com", "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"})
    m = d["data"]["matchedUser"]
    ac = {x["difficulty"]: x["count"] for x in m["submitStats"]["acSubmissionNum"]}
    return dict(total=ac.get("All", 0), easy=ac.get("Easy", 0), medium=ac.get("Medium", 0), hard=ac.get("Hard", 0), streak=(m.get("userCalendar") or {}).get("streak"))


def hold(attr, zero, final, delay, dur):
    tot = delay + dur
    kt = f"0;{delay/tot:.4f};1" if delay > 0 else "0;0;1"
    return f'<animate attributeName="{attr}" values="{zero};{zero};{final}" keyTimes="{kt}" dur="{tot:.2f}s" fill="freeze"/>'


def render(gh, lc, live):
    W, H = 1000, 340
    # ---------------- GitHub block
    metrics = [("REPOSITORIES", gh["repos"]), ("STARS", gh["stars"]), ("FOLLOWERS", gh["followers"]), ("CONTRIBUTIONS / YR", gh["contribs"])]
    metrics = [(k, v) for k, v in metrics if v is not None]
    left = []
    for i, (k, v) in enumerate(metrics):
        x, y = 40 + (i % 2) * 150, 118 + (i // 2) * 98
        left.append(f'<g transform="translate({x},{y})" opacity="1">{hold("opacity","0","1",0.2+i*0.15,0.5)}'
                    f'<text font-family="{SANS}" font-size="46" font-weight="800" fill="#f0f4ff">{v:,}</text>'
                    f'<text y="24" font-family="{MONO}" font-size="10" letter-spacing="1.5" fill="#7f8ea3">{k}</text></g>')
    streak_line = ""
    if gh.get("streak") is not None:
        streak_line = f'<text x="40" y="306" font-family="{MONO}" font-size="12" fill="{CYAN}">GitHub streak {gh["streak"]}d · longest {gh["longest"]}d</text>'
    # ---------------- LeetCode donut
    cx, cy, r, sw = 478, 176, 66, 20
    C = 2 * math.pi * r
    segs = []
    if lc.get("easy") is not None and lc["total"]:
        parts = [("Easy", lc["easy"], GREEN), ("Medium", lc["medium"], AMBER), ("Hard", lc["hard"], PINK)]
        tot = sum(p[1] for p in parts) or 1
        off, gap = 0.0, 4
        for i, (n, v, c) in enumerate(parts):
            ln = max(0, v / tot * C - gap)
            segs.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{c}" stroke-width="{sw}" stroke-linecap="butt" stroke-dasharray="{ln:.1f} {C-ln:.1f}" stroke-dashoffset="{-off:.1f}" transform="rotate(-90 {cx} {cy})">{hold("stroke-dasharray", "0 "+f"{C:.1f}", f"{ln:.1f} {C-ln:.1f}", 0.3+i*0.35, 0.9)}</circle>')
            off += v / tot * C
        legend = "".join(f'<g transform="translate(580,{138+i*34})"><circle r="5" cx="0" cy="-4" fill="{c}"/><text x="14" font-family="{SANS}" font-size="15" font-weight="700" fill="#e6edf3">{v}</text><text x="52" font-family="{MONO}" font-size="11" fill="#7f8ea3">{n.upper()}</text></g>' for i, (n, v, c) in enumerate(parts))
        total_txt = f'{lc["total"]}'
    else:
        segs.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{CYAN}" stroke-opacity="0.7" stroke-width="{sw}" stroke-dasharray="6 5"/>')
        legend = f'<text x="580" y="160" font-family="{MONO}" font-size="11" fill="#7f8ea3">difficulty split</text><text x="580" y="180" font-family="{MONO}" font-size="11" fill="#7f8ea3">appears after the</text><text x="580" y="200" font-family="{MONO}" font-size="11" fill="#7f8ea3">next Action run</text>'
        total_txt = f'{lc["total"]}+'
    lc_streak = f'<text x="400" y="306" font-family="{MONO}" font-size="12" fill="{AMBER}">LeetCode streak {lc["streak"]}d</text>' if lc.get("streak") is not None else ""
    # ---------------- languages
    langs = gh["langs"][:5]
    tot = sum(n for _, n, _ in langs) or 1
    bar, rows, x = [], [], 0.0
    for i, (n, cnt, col) in enumerate(langs):
        w = cnt / tot * 240
        bar.append(f'<rect x="{x:.1f}" y="0" width="{max(w-2,1):.1f}" height="12" fill="{col}">{hold("width","0",f"{max(w-2,1):.1f}",0.3+i*0.2,0.7)}</rect>')
        x += w
        rows.append(f'<g transform="translate(0,{44+i*30})"><circle cx="5" cy="-4" r="5" fill="{col}"/><text x="18" font-family="{SANS}" font-size="14" font-weight="600" fill="#e6edf3">{escape(n)}</text><text x="240" text-anchor="end" font-family="{MONO}" font-size="12" fill="#7f8ea3">{cnt/tot*100:.0f}%</text></g>')
    stamp = f'auto-updated {datetime.datetime.utcnow():%Y-%m-%d} UTC · GitHub Actions' if live else "snapshot · refreshes on the next Action run"
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" aria-label="Live GitHub and LeetCode stats">
<defs>
  <linearGradient id="tbg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#121b2e"/><stop offset="1" stop-color="#090e18"/></linearGradient>
  <radialGradient id="b1" cx="50%" cy="50%" r="50%"><stop offset="0" stop-color="{CYAN}" stop-opacity="0.3"/><stop offset="1" stop-color="{CYAN}" stop-opacity="0"/></radialGradient>
  <radialGradient id="b2" cx="50%" cy="50%" r="50%"><stop offset="0" stop-color="{VIOLET}" stop-opacity="0.26"/><stop offset="1" stop-color="{VIOLET}" stop-opacity="0"/></radialGradient>
  <pattern id="dots" width="22" height="22" patternUnits="userSpaceOnUse"><circle cx="2" cy="2" r="1" fill="#fff" fill-opacity="0.07"/></pattern>
  <clipPath id="clipT"><rect width="{W}" height="{H}" rx="22"/></clipPath>
</defs>
<g clip-path="url(#clipT)">
  <rect width="{W}" height="{H}" fill="url(#tbg)"/><rect width="{W}" height="{H}" fill="url(#dots)"/>
  <circle cx="900" cy="-20" r="300" fill="url(#b1)"/><circle cx="40" cy="360" r="260" fill="url(#b2)"/>
  <text x="40" y="52" font-family="{MONO}" font-size="12" letter-spacing="2" fill="{CYAN}">GITHUB</text>
  <text x="400" y="52" font-family="{MONO}" font-size="12" letter-spacing="2" fill="{AMBER}">LEETCODE</text>
  <text x="720" y="52" font-family="{MONO}" font-size="12" letter-spacing="2" fill="{VIOLET}">TOP LANGUAGES</text>
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
  <text x="{W-30}" y="{H-18}" text-anchor="end" font-family="{MONO}" font-size="10" fill="#566275">{stamp}</text>
</g>
<rect x="0.5" y="0.5" width="{W-1}" height="{H-1}" rx="22" fill="none" stroke="#fff" stroke-opacity="0.1"/>
</svg>'''


def main():
    live_any = False
    try:
        gh = fetch_github(); live_any = True
    except Exception as e:
        print("GitHub fetch failed, using snapshot:", e, file=sys.stderr); gh = SNAPSHOT_GH
    try:
        lc = fetch_leetcode(); live_any = True
    except Exception as e:
        print("LeetCode fetch failed, using snapshot:", e, file=sys.stderr); lc = SNAPSHOT_LC
    svg = render(gh, lc, live_any)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(svg)
    print("wrote", os.path.normpath(OUT))


if __name__ == "__main__":
    main()
