"""Render the "By the numbers." stats card (light + dark SVG) from the GitHub GraphQL API.

Usage: GITHUB_TOKEN=... GH_LOGIN=... python stats.py <out_dir>
"""
import datetime as dt
import json
import os
import pathlib
import sys
import urllib.request

LOGIN = os.environ["GH_LOGIN"]
TOKEN = os.environ["GITHUB_TOKEN"]
OUT = pathlib.Path(sys.argv[1])

FONT = "-apple-system,BlinkMacSystemFont,'SF Pro Display','SF Pro Text','Inter','Segoe UI',Roboto,Helvetica,Arial,sans-serif"
THEMES = {
    "dark": dict(tile="#161617", text="#f5f5f7", sub="#86868b", hair="#ffffff", hair_op=0.12, track="#2c2c2e",
                 grad=("#2997ff", "#a855f7", "#ff375f")),
    "light": dict(tile="#f5f5f7", text="#1d1d1f", sub="#6e6e73", hair="#000000", hair_op=0.08, track="#e5e5ea",
                  grad=("#0071e3", "#8e44ec", "#e3245a")),
}


def gql(query, **variables):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={"Authorization": f"bearer {TOKEN}", "User-Agent": "profile-stats"},
    )
    with urllib.request.urlopen(req) as resp:
        body = json.load(resp)
    if "errors" in body:
        raise SystemExit(f"GraphQL error: {body['errors']}")
    return body["data"]


def collect():
    user = gql("""query($login: String!) { user(login: $login) {
        createdAt
        repositories(ownerAffiliations: OWNER, isFork: false, privacy: PUBLIC, first: 100) {
          totalCount
          nodes { name languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
            edges { size node { name color } } } }
        } } }""", login=LOGIN)["user"]

    now = dt.datetime.now(dt.timezone.utc)
    commits = contributions = 0
    days = {}
    for year in range(int(user["createdAt"][:4]), now.year + 1):
        start = dt.datetime(year, 1, 1, tzinfo=dt.timezone.utc)
        # Whole calendar years: GitHub buckets days in the user's timezone, so clipping to "now" in UTC drops today.
        end = dt.datetime(year, 12, 31, 23, 59, 59, tzinfo=dt.timezone.utc)
        cc = gql("""query($login: String!, $from: DateTime!, $to: DateTime!) { user(login: $login) {
            contributionsCollection(from: $from, to: $to) {
              totalCommitContributions
              contributionCalendar { totalContributions weeks { contributionDays { date contributionCount } } }
            } } }""", login=LOGIN, **{"from": start.isoformat(), "to": end.isoformat()})["user"]["contributionsCollection"]
        commits += cc["totalCommitContributions"]
        contributions += cc["contributionCalendar"]["totalContributions"]
        for week in cc["contributionCalendar"]["weeks"]:
            for d in week["contributionDays"]:
                days[d["date"]] = d["contributionCount"]

    longest = run = 0
    for date in sorted(days):
        run = run + 1 if days[date] else 0
        longest = max(longest, run)

    langs = {}
    for repo in user["repositories"]["nodes"]:
        for edge in repo["languages"]["edges"]:
            name = edge["node"]["name"]
            size, color = langs.get(name, (0, edge["node"]["color"]))
            langs[name] = (size + edge["size"], color or "#8e8e93")
    total = sum(s for s, _ in langs.values()) or 1
    top = sorted(langs.items(), key=lambda kv: -kv[1][0])[:5]

    return dict(
        metrics=[(contributions, "Contributions"), (commits, "Commits"),
                 (sum(1 for c in days.values() if c), "Active days"), (user["repositories"]["totalCount"], "Public repos")],
        langs=[(name, size / total, color) for name, (size, color) in top],
        updated=now.strftime("%b %-d, %Y"),
        longest=longest,
    )


def render(data, t):
    W, gap, th = 1280, 16, 176
    tw = (W - 8 - gap * 3) / 4
    out = [
        '<text x="4" y="78" font-size="54" font-weight="700" letter-spacing="-1.6" class="t">By the numbers.</text>',
        f'<text x="4" y="124" font-size="25" class="s">Live from GitHub · updated {data["updated"]}</text>',
    ]
    y0 = 168
    for i, (value, label) in enumerate(data["metrics"]):
        x = 4 + i * (tw + gap)
        out.append(f'<rect x="{x:.1f}" y="{y0}" width="{tw:.1f}" height="{th}" rx="28" fill="{t["tile"]}" '
                   f'stroke="{t["hair"]}" stroke-opacity="{t["hair_op"]}"/>'
                   f'<text x="{x + 32:.1f}" y="{y0 + 100}" font-size="66" font-weight="700" letter-spacing="-2" fill="url(#g)">{value:,}</text>'
                   f'<text x="{x + 32:.1f}" y="{y0 + 142}" font-size="21" font-weight="500" class="s">{label}</text>')

    y = y0 + th + 64
    out.append(f'<text x="4" y="{y}" font-size="21" font-weight="600" class="t">Languages</text>')
    bar_y, bar_w = y + 24, W - 8
    out.append(f'<clipPath id="bar"><rect x="4" y="{bar_y}" width="{bar_w}" height="14" rx="7"/></clipPath>'
               f'<rect x="4" y="{bar_y}" width="{bar_w}" height="14" rx="7" fill="{t["track"]}"/><g clip-path="url(#bar)">')
    x = 4.0
    for _, share, color in data["langs"]:
        w = share * bar_w
        out.append(f'<rect x="{x:.1f}" y="{bar_y}" width="{w + 0.5:.1f}" height="14" fill="{color}"/>')
        x += w
    out.append("</g>")
    x = 4.0
    for name, share, color in data["langs"]:
        label = f"{name} {share * 100:.1f}%"
        out.append(f'<circle cx="{x + 7:.1f}" cy="{bar_y + 52}" r="7" fill="{color}"/>'
                   f'<text x="{x + 22:.1f}" y="{bar_y + 59}" font-size="20" class="s">'
                   f'<tspan class="t" font-weight="600">{name}</tspan> {share * 100:.1f}%</text>')
        x += 22 + len(label) * 11 + 36
    H = bar_y + 80

    stops = "".join(f'<stop offset="{i / 2}" stop-color="{c}"/>' for i, c in enumerate(t["grad"]))
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" '
            f'aria-label="GitHub stats: ' + ", ".join(f"{v} {l.lower()}" for v, l in data["metrics"]) + '" fill="none">'
            f"<style>text{{font-family:{FONT}}}.t{{fill:{t['text']}}}.s{{fill:{t['sub']}}}</style>"
            f'<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="0">{stops}</linearGradient></defs>'
            + "".join(out) + "</svg>\n")


if __name__ == "__main__":
    data = collect()
    OUT.mkdir(parents=True, exist_ok=True)
    for mode, theme in THEMES.items():
        (OUT / f"stats-{mode}.svg").write_text(render(data, theme))
    print(json.dumps(data, indent=2))
