"""Permit Radar: pull fresh building permits from city open-data feeds and
render static pages plus CSV downloads into ../permits.

Runs daily in GitHub Actions. Standard library only.
  python3 permits_engine/build.py            # fetch live data, then render
  python3 permits_engine/build.py --offline  # re-render from permits/data/*.json
"""
import csv, datetime as dt, html, io, json, os, re, sys, urllib.parse, urllib.request
from collections import Counter, defaultdict

from sources import SOURCES, TRADES

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "permits")
DATA = os.path.join(OUT, "data")
SITE = "https://loomenz.github.io/tradeledger"
DAYS = 30
ALERT_EMAIL = "tradeledger.tools@gmail.com"
TODAY = dt.date.today()
e = html.escape


# ---------------------------------------------------------------- fetch
def first(row, keys):
    for k in keys:
        if isinstance(k, list):
            v = " ".join(str(row.get(p, "")).strip() for p in k if row.get(p))
        else:
            v = row.get(k)
        if v not in (None, "", "N/A"):
            return str(v).strip()
    return ""


def money(v):
    try:
        return max(0.0, float(str(v).replace("$", "").replace(",", "")))
    except ValueError:
        return 0.0


def clean_contractor(name):
    name = re.sub(r"\s+", " ", name.strip().strip('"')).title()
    # Dallas-style "NAME 123 Street, City" strings: keep the business name only.
    name = re.split(r"\s\d{2,}\s", name)[0]
    # Publish business names only, so a homeowner pulling their own permit never shows up.
    if not BUSINESS.search(name):
        return ""
    return name[:60]


BUSINESS = re.compile(r"\b(llc|l\.l\.c|inc|corp|co|company|ltd|lp|group|construction|contract\w*|builders?|build|roof\w*|plumb\w*|electric\w*|mechanical|heating|air|hvac|solar|energy|homes?|services?|systems?|pools?|remodel\w*|restoration|exteriors?|windows?|doors?|fence|concrete|development|enterprises?|industries|design)\b", re.I)


def classify(text):
    t = f" {text.lower()} "
    found = [slug for slug, _, kws in TRADES if any(k in t for k in kws)]
    # "roof mount solar" is a solar job, not a roofing job.
    if "solar" in found and "roofing" in found and not any(k in t for k in ("reroof", "re-roof", "shingle", "roof replace")):
        found.remove("roofing")
    return found


def owner_pulled(src, row):
    """True when the permit holder is the property owner, not a contractor."""
    rule = src.get("owner_pulled")
    if not rule:
        return False
    if "field" in rule:
        return bool(re.search(rule["match"], str(row.get(rule["field"], "")), re.I))
    a, b = (re.sub(r"\W", "", str(row.get(k, "")).lower()) for k in rule["same"])
    return bool(a) and a == b


def fetch(src):
    since = (TODAY - dt.timedelta(days=DAYS + 3)).isoformat()
    q = urllib.parse.urlencode({
        "$where": f"{src['date']} >= '{since}T00:00:00'",
        "$order": f"{src['date']} DESC",
        "$limit": 50000,
    })
    url = f"https://{src['host']}/resource/{src['dataset']}.json?{q}"
    req = urllib.request.Request(url, headers={"User-Agent": "PermitRadar/1.0 (+%s/permits/)" % SITE})
    with urllib.request.urlopen(req, timeout=120) as r:
        rows = json.load(r)
    out, seen = [], set()
    for row in rows:
        date = (row.get(src["date"]) or "")[:10]
        if not date or date > TODAY.isoformat():
            continue
        desc = re.sub(r"\s+", " ", first(row, src["desc"]))
        ptype = first(row, src["type"])
        addr = re.sub(r"\s+", " ", first(row, src["address"])).title()
        if not addr:
            continue
        contractor = ""
        tkey = src.get("contractor_type_key")
        if not tkey or "CONTRACTOR" in str(row.get(tkey, "")).upper():
            contractor = clean_contractor(first(row, src["contractor"]))
        key = (date, addr, desc[:80])
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "date": date, "address": addr, "zip": first(row, src["zip"])[:5],
            "type": ptype[:80], "desc": desc[:400], "value": value if (value := round(money(first(row, src["value"])))) < 300_000_000 else 0,
            "contractor": contractor, "trades": classify(f"{desc} {ptype}"),
            "owner": owner_pulled(src, row),
        })
    return out, (sorted(rows[0].keys()) if rows else [])


# ---------------------------------------------------------------- helpers
def fmt_money(v):
    if v >= 1e9: return f"${v/1e9:.1f}B"
    if v >= 1e6: return f"${v/1e6:.1f}M"
    if v >= 1e3: return f"${v/1e3:.0f}K"
    return f"${v:,.0f}"


def nice_date(d):
    return dt.date.fromisoformat(d).strftime("%b %-d")


TRADE_NAME = {s: n for s, n, _ in TRADES}

ICONS = {
    "radar": '<path d="M19.07 4.93A10 10 0 0 0 6.99 3.34"/><path d="M4 6h.01"/><path d="M2.29 9.62A10 10 0 1 0 21.31 8.35"/><path d="M16.24 7.76A6 6 0 1 0 8.23 16.67"/><path d="M12 18h.01"/><path d="M17.99 11.66A6 6 0 0 1 15.77 16.67"/><circle cx="12" cy="12" r="2"/><path d="m13.41 10.59 5.66-5.66"/>',
    "arrow": '<path d="M5 12h14"/><path d="m12 5 7 7-7 7"/>',
    "download": '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m7 10 5 5 5-5"/><path d="M12 15V3"/>',
    "bell": '<path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/><path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"/>',
    "trophy": '<path d="M6 9H4.5a2.5 2.5 0 0 1 0-5H6"/><path d="M18 9h1.5a2.5 2.5 0 0 0 0-5H18"/><path d="M4 22h16"/><path d="M18 2H6v7a6 6 0 0 0 12 0V2Z"/>',
    "map": '<path d="M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0Z"/><circle cx="12" cy="10" r="3"/>',
    "zap": '<path d="M13 2 3 14h9l-1 8 10-12h-9l1-8z"/>',
    "db": '<ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M3 5v14a9 3 0 0 0 18 0V5"/><path d="M3 12a9 3 0 0 0 18 0"/>',
}


def icon(name, size=18):
    return (f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            f'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{ICONS[name]}</svg>')


def daily_counts(items):
    c = Counter(p["date"] for p in items)
    days = [(TODAY - dt.timedelta(days=i)).isoformat() for i in range(DAYS - 1, -1, -1)]
    return [(d, c.get(d, 0)) for d in days]


def bars(items, h=120):
    data = daily_counts(items)
    top = max([n for _, n in data] + [1])
    w = 10
    rects = []
    for i, (d, n) in enumerate(data):
        bh = max(2, round(n / top * (h - 4)))
        rects.append(f'<rect x="{i*(w+4)}" y="{h-bh}" width="{w}" height="{bh}" rx="3"><title>{nice_date(d)}: {n} permits</title></rect>')
    return (f'<svg class="bars" viewBox="0 0 {len(data)*(w+4)-4} {h}" preserveAspectRatio="none" role="img" '
            f'aria-label="Permits issued per day, last {DAYS} days">{"".join(rects)}</svg>')


def spark(items):
    data = daily_counts(items)
    top = max([n for _, n in data] + [1])
    pts = " ".join(f"{i*4},{30-round(n/top*28)}" for i, (_, n) in enumerate(data))
    return f'<svg class="spark" viewBox="0 0 {(len(data)-1)*4} 32" preserveAspectRatio="none" aria-hidden="true"><polyline points="{pts}"/></svg>'


def leaderboard(items, n=10):
    c, v = Counter(), defaultdict(float)
    for p in items:
        if p["contractor"]:
            c[p["contractor"]] += 1
            v[p["contractor"]] += p["value"]
    return [(name, cnt, v[name]) for name, cnt in c.most_common(n)]


# ---------------------------------------------------------------- templates
def page(title, desc, path, body, depth, noindex=False):
    up = "../" * depth
    robots = '<meta name="robots" content="noindex,follow">' if noindex else ""
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(title)}</title><meta name="description" content="{e(desc)}">{robots}
<link rel="canonical" href="{SITE}/{path}">
<meta property="og:title" content="{e(title)}"><meta property="og:description" content="{e(desc)}">
<meta property="og:image" content="{SITE}/cover.png"><meta name="theme-color" content="#070b14">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@500&display=swap" rel="stylesheet">
<link rel="stylesheet" href="{up}permits/radar.css"></head><body>
<header class="nav"><div class="wrap navin"><a class="brand" href="{up}permits/index.html"><span class="logo">{icon('radar', 18)}</span><span>Permit Radar</span><em>by TradeLedger</em></a>
<nav><a href="{up}permits/index.html#cities">Cities</a><a href="{up}permits/index.html#how">How it works</a><a href="{up}index.html">Tools</a></nav>
<a class="btn sm" href="#alerts">{icon('bell', 15)} Get alerts</a></div></header>
<main>{body}</main>
<footer class="foot"><div class="wrap"><div><b>Permit Radar</b> turns public building-permit records into daily leads for contractors. Data comes from each city's official open-data portal and is refreshed every morning. Updated {TODAY.strftime('%B %-d, %Y')}.</div>
<div class="fl"><a href="{up}permits/index.html">All cities</a><a href="{up}index.html">TradeLedger tools</a><a href="mailto:{ALERT_EMAIL}">Contact</a></div></div></footer>
<script>
const io=new IntersectionObserver(es=>es.forEach(x=>{{if(x.isIntersecting){{x.target.classList.add('in');io.unobserve(x.target)}}}}),{{threshold:.12}});
document.querySelectorAll('.reveal').forEach(el=>io.observe(el));
document.querySelectorAll('[data-count]').forEach(el=>{{const end=+el.dataset.count,pre=el.dataset.pre||'',suf=el.dataset.suf||'';
if(matchMedia('(prefers-reduced-motion: reduce)').matches){{return}}let t0=null;const f=t=>{{t0??=t;const k=Math.min(1,(t-t0)/1100);
el.textContent=pre+Math.round(end*(1-Math.pow(1-k,3))).toLocaleString()+suf;if(k<1)requestAnimationFrame(f)}};requestAnimationFrame(f)}});
const q=document.getElementById('q');if(q)q.addEventListener('input',()=>{{const v=q.value.toLowerCase();
document.querySelectorAll('#ptable tbody tr').forEach(r=>r.hidden=!r.textContent.toLowerCase().includes(v))}});
</script></body></html>"""


def alerts_box(city="", trade=""):
    label = " ".join(x for x in [TRADE_NAME.get(trade, ""), "permits in", city] if x) if city else "permits in your city"
    return f"""<section class="alerts reveal" id="alerts"><div class="wrap"><div class="abox">
<div><span class="eyebrow">{icon('bell', 14)} Daily alerts</span><h2>Get new {e(label if city else label.lower()).replace(TRADE_NAME.get(trade, "~"), TRADE_NAME.get(trade, "").lower())} in your inbox every morning.</h2>
<p>Pick your city and trade. Every new permit lands in your inbox with the address, scope, job value and contractor, so you know which streets to work before anyone else does. Free while in early access.</p></div>
<form action="https://formsubmit.co/{ALERT_EMAIL}" method="POST" class="aform">
<input type="hidden" name="_subject" value="Permit Radar alert signup"><input type="hidden" name="_template" value="table">
<input type="hidden" name="_next" value="{SITE}/permits/thanks.html"><input type="text" name="_honey" style="display:none" tabindex="-1" autocomplete="off">
<label>Work email<input type="email" name="email" required placeholder="you@yourcompany.com"></label>
<label>City<input type="text" name="city" value="{e(city)}" placeholder="Austin, TX" required></label>
<label>Trade<input type="text" name="trade" value="{e(TRADE_NAME.get(trade, ''))}" placeholder="Roofing"></label>
<button class="btn full" type="submit">{icon('zap', 16)} Start my free alerts</button>
<small>No spam. One email a day, unsubscribe any time.</small></form></div></div></section>"""


def stat(n, label, pre="", suf=""):
    shown = f"{pre}{n:,}{suf}"
    return f'<div><b data-count="{n}" data-pre="{pre}" data-suf="{suf}">{shown}</b><span>{label}</span></div>'


def value_stat(v, label):
    return f"<div><b>{fmt_money(v)}</b><span>{label}</span></div>"


def permit_table(items, show_trade=True, limit=300):
    rows = []
    for p in items[:limit]:
        tags = "".join(f'<i class="tag">{e(TRADE_NAME[t])}</i>' for t in p["trades"][:2]) if show_trade else ""
        val = fmt_money(p["value"]) if p["value"] else '<span class="mute">n/a</span>'
        con = e(p["contractor"]) if p["contractor"] else ('<i class="tag own">Owner-pulled</i>' if p.get("owner") else '<span class="mute">Not listed</span>')
        rows.append(f'<tr><td class="mono">{nice_date(p["date"])}</td><td><b>{e(p["address"])}</b>{tags}<div class="d">{e(p["desc"][:220]) or e(p["type"])}</div></td>'
                    f'<td class="mono r">{val}</td><td>{con}</td></tr>')
    more = f'<p class="mute small">Showing the {limit} most recent of {len(items):,}. Download the CSV for all of them.</p>' if len(items) > limit else ""
    return f"""<div class="tbl reveal"><div class="tblhead"><input id="q" type="search" placeholder="Filter by street, zip, contractor or keyword" aria-label="Filter permits"></div>
<div class="scroll"><table id="ptable"><thead><tr><th>Issued</th><th>Address and scope</th><th class="r">Job value</th><th>Contractor</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table></div></div>{more}"""


def board_html(items, title):
    lb = leaderboard(items)
    if len(lb) < 3:
        return ""
    li = "".join(f'<li><span class="rk">{i}</span><span class="nm">{e(n)}</span><span class="ct">{c} permit{"s" if c != 1 else ""}</span><span class="vl">{fmt_money(v) if v else ""}</span></li>'
                 for i, (n, c, v) in enumerate(lb, 1))
    return f'<div class="board reveal"><h3>{icon("trophy")} {e(title)}</h3><ol>{li}</ol></div>'


def write(rel, text):
    path = os.path.join(OUT, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def write_csv(rel, items):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["issued", "address", "zip", "permit_type", "description", "job_value", "contractor", "owner_pulled", "trades"])
    for p in items:
        w.writerow([p["date"], p["address"], p["zip"], p["type"], p["desc"], p["value"] or "", p["contractor"], "yes" if p.get("owner") else "", "; ".join(TRADE_NAME[t] for t in p["trades"])])
    write(rel, buf.getvalue())


# ---------------------------------------------------------------- pages
def render_trade(src, trade, items):
    name, city = TRADE_NAME[trade], src["city"]
    total = sum(p["value"] for p in items)
    week = sum(1 for p in items if p["date"] >= (TODAY - dt.timedelta(days=7)).isoformat())
    title = f"New {name} Permits in {city}, {src['state']} (Last {DAYS} Days) | Permit Radar"
    desc = f"{len(items):,} {name.lower()} permits issued in {city} in the last {DAYS} days, worth {fmt_money(total)}. Addresses, job values and contractors, updated daily."
    body = f"""<section class="hero sm"><div class="glow"></div><div class="wrap">
<a class="crumb" href="index.html">{icon('map', 14)} {e(city)}, {src['state']}</a>
<h1>{e(name)} permits in {e(city)}</h1>
<p class="lead">Every {e(name.lower())} permit {e(city)} issued in the last {DAYS} days, pulled from the city's official records and refreshed each morning.</p>
<div class="stats">{stat(len(items), f'permits, last {DAYS} days')}{stat(week, 'in the last 7 days')}{value_stat(total, 'total job value')}</div>
<div class="ctas"><a class="btn" href="#alerts">{icon('bell', 16)} Alert me to new ones</a><a class="btn ghost" href="data/{trade}.csv" download>{icon('download', 16)} Download CSV</a></div></div></section>
<section class="sec"><div class="wrap two">
<div class="chart reveal"><h3>Permits issued per day</h3>{bars(items)}<div class="axis"><span>{DAYS} days ago</span><span>Today</span></div></div>
{board_html(items, f'Most active {name.lower()} contractors') or '<div class="board reveal"><h3>' + icon('trophy') + ' Contractor rankings</h3><p class="mute">' + e(city) + ' does not publish contractor names for most permits, so rankings are not available here.</p></div>'}
</div></section>
<section class="sec alt"><div class="wrap"><h2>Latest {e(name.lower())} permits</h2>{permit_table(items, show_trade=False)}</div></section>
{alerts_box(f"{city}, {src['state']}", trade)}"""
    write(f"{src['slug']}/{trade}.html", page(title, desc, f"permits/{src['slug']}/{trade}.html", body, 2, noindex=len(items) < 5))
    write_csv(f"{src['slug']}/data/{trade}.csv", items)


def render_city(src, items, fields):
    by_trade = {slug: [p for p in items if slug in p["trades"]] for slug, _, _ in TRADES}
    total = sum(p["value"] for p in items)
    cards = []
    for slug, name, _ in sorted(TRADES, key=lambda t: -len(by_trade[t[0]])):
        ts = by_trade[slug]
        if not ts:
            continue
        render_trade(src, slug, ts)
        cards.append(f'<a class="tcard reveal" href="{slug}.html"><div class="tt"><h3>{e(name)}</h3><span class="n">{len(ts):,}</span></div>{spark(ts)}'
                     f'<div class="tf"><span>{fmt_money(sum(p["value"] for p in ts))} in jobs</span><span class="go">{icon("arrow", 15)}</span></div></a>')
    city = src["city"]
    title = f"New Building Permits in {city}, {src['state']} by Trade (Updated Daily) | Permit Radar"
    desc = f"{len(items):,} building permits issued in {city} in the last {DAYS} days. Browse by trade: roofing, HVAC, solar, plumbing, electrical and more."
    body = f"""<section class="hero sm"><div class="glow"></div><div class="wrap">
<a class="crumb" href="../index.html">{icon('radar', 14)} All cities</a>
<h1>Building permits in <span class="grad">{e(city)}</span></h1>
<p class="lead">What {e(city)} is building right now, sorted by trade: the addresses, the job values and the contractors pulling the work.</p>
<div class="stats">{stat(len(items), f'permits, last {DAYS} days')}{value_stat(total, 'total job value')}{stat(len(cards), 'active trades')}{stat(sum(1 for p in items if p.get("owner")), 'pulled by the owner') if src.get("owner_pulled") else ''}</div>
<div class="ctas"><a class="btn" href="#alerts">{icon('bell', 16)} Get daily alerts</a><a class="btn ghost" href="data/all.csv" download>{icon('download', 16)} Download all ({len(items):,})</a></div></div></section>
<section class="sec"><div class="wrap"><h2>Browse by trade</h2><div class="tgrid">{''.join(cards)}</div></div></section>
<section class="sec alt"><div class="wrap two"><div class="chart reveal"><h3>All permits per day</h3>{bars(items)}<div class="axis"><span>{DAYS} days ago</span><span>Today</span></div></div>
{board_html(items, f'Most active contractors in {city}')}</div></section>
<section class="sec"><div class="wrap"><h2>Latest permits</h2>{permit_table(items, limit=150)}</div></section>
{alerts_box(f"{city}, {src['state']}")}"""
    write(f"{src['slug']}/index.html", page(title, desc, f"permits/{src['slug']}/index.html", body, 2))
    write_csv(f"{src['slug']}/data/all.csv", items)
    return by_trade


def render_hub(cities):
    allp = [p for _, items, _ in cities for p in items]
    total = sum(p["value"] for p in allp)
    trade_tot = Counter(t for p in allp for t in p["trades"])
    cards = "".join(
        f'<a class="ccard reveal" href="{s["slug"]}/index.html"><div class="tt"><div><h3>{e(s["city"])}</h3><span class="mute">{s["state"]}</span></div>'
        f'<span class="n">{len(items):,}</span></div>{spark(items)}<div class="tf"><span>{fmt_money(sum(p["value"] for p in items))} in new work</span><span class="go">{icon("arrow", 15)}</span></div></a>'
        for s, items, _ in sorted(cities, key=lambda c: -len(c[1])))
    pills = "".join(f'<span class="pill">{e(TRADE_NAME[t])} <b>{n:,}</b></span>' for t, n in trade_tot.most_common(8))
    sample = []
    for s, items, _ in cities:  # the biggest recent job per city keeps the feed varied
        recent = [p for p in items[:400] if 20000 <= p["value"] <= 20_000_000 and p["trades"]]
        if recent:
            sample.append(max(recent, key=lambda p: (p["date"], p["value"])) | {"city": s["city"]})
    sample = sorted(sample, key=lambda p: (p["date"], p["value"]), reverse=True)[:6]
    feed = "".join(f'<div class="fi"><span class="mono">{nice_date(p["date"])}</span><b>{e(TRADE_NAME[p["trades"][0]])}</b><span>{e(p["city"])}</span><span class="mono r">{fmt_money(p["value"])}</span></div>' for p in sample)
    title = "Permit Radar: New Building Permits as Daily Leads for Contractors"
    desc = f"Fresh building permits from {len(cities)} US cities, sorted by trade and refreshed every morning. Find roofing, HVAC, solar, plumbing and remodeling jobs the day they're permitted."
    body = f"""<section class="hero"><div class="glow"></div><div class="grid-bg"></div><div class="wrap herogrid">
<div><span class="eyebrow">{icon('zap', 14)} Updated every morning</span>
<h1>See who's building <span class="grad">what, where</span>, every morning.</h1>
<p class="lead">Permit Radar reads the official permit records of {len(cities)} US cities each day and sorts them by trade. Spot the streets heating up, the new builds that will need a fence, a pool or a service plan next, and which contractors are pulling the most work.</p>
<div class="ctas"><a class="btn big" href="#cities">Browse cities {icon('arrow', 16)}</a><a class="btn ghost big" href="#alerts">{icon('bell', 16)} Get daily alerts</a></div>
<div class="pills">{pills}</div></div>
<div class="feed reveal"><div class="fh"><span class="dot"></span> Live feed <span class="mute">· jobs over $20K</span></div>{feed}</div></div>
<div class="wrap"><div class="stats big">{stat(len(allp), f'permits in {DAYS} days')}{value_stat(total, 'in permitted work')}{stat(len(cities), 'cities')}{stat(len(TRADES), 'trades tracked')}</div></div></section>
<section class="sec" id="cities"><div class="wrap"><h2>Pick a city</h2><p class="lead">Click through for trade-by-trade breakdowns, contractor rankings and CSV downloads.</p><div class="cgrid">{cards}</div></div></section>
<section class="sec alt" id="how"><div class="wrap"><h2>How it works</h2><div class="steps">
<div class="step reveal"><span class="ico">{icon('db', 20)}</span><h3>We pull the records</h3><p>Every morning a robot reads each city's official open-data permit feed. No scraping, no guesswork.</p></div>
<div class="step reveal"><span class="ico">{icon('radar', 20)}</span><h3>We sort them by trade</h3><p>Each permit is tagged roofing, HVAC, solar, plumbing, electrical, pools, remodeling and more, with job value and contractor.</p></div>
<div class="step reveal"><span class="ico">{icon('bell', 20)}</span><h3>You get the leads</h3><p>Browse here, download a CSV for your CRM, or get the new ones emailed to you each morning.</p></div></div>
<div class="faq"><details><summary>Is this legal to use?</summary><p>Yes. Building permits are public records, and every row here comes from the city's own open-data portal under its open-data terms. We only show business names for contractors, never homeowners' names.</p></details>
<details><summary>Who uses permit data?</summary><p>Fence, pool, landscaping, gutter and HVAC-service companies find new builds months before move-in. Roofers, solar and window installers canvass the streets where permits are clustering. Subcontractors and suppliers see which general contractors are busiest. Insurers, lenders and investors track where neighborhoods are being upgraded. The permit itself is usually already a contractor's job; the value is in everything around it.</p></details>
<details><summary>Can I find homeowners doing their own project?</summary><p>Some cities record who pulled the permit. Where they do, owner-pulled permits are flagged in the table and the CSV, since those owners may still be hiring subs.</p></details>
<details><summary>Why isn't my city here?</summary><p>We add cities that publish permits as open data. Tell us your city in the alert form and we'll prioritize it.</p></details></div></div></section>
{alerts_box()}"""
    write("index.html", page(title, desc, "permits/index.html", body, 1))
    write("thanks.html", page("You're on the list | Permit Radar", "Signup confirmed.", "permits/thanks.html",
          f'<section class="hero sm"><div class="glow"></div><div class="wrap"><h1>You\'re on the list.</h1><p class="lead">Your first alert arrives with the next morning\'s permits.</p><a class="btn" href="index.html">Back to Permit Radar</a></div></section>', 1, noindex=True))


def render_sitemap(cities):
    urls = [f"{SITE}/permits/index.html"]
    for s, items, by_trade in cities:
        urls.append(f"{SITE}/permits/{s['slug']}/index.html")
        urls += [f"{SITE}/permits/{s['slug']}/{t}.html" for t, ts in by_trade.items() if len(ts) >= 5]
    body = "".join(f"<url><loc>{u}</loc><lastmod>{TODAY.isoformat()}</lastmod><changefreq>daily</changefreq></url>" for u in urls)
    write("sitemap.xml", f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{body}</urlset>')


def main():
    offline = "--offline" in sys.argv
    os.makedirs(DATA, exist_ok=True)
    cities, fieldlog = [], {}
    for src in SOURCES:
        cache = os.path.join(DATA, f"{src['slug']}.json")
        try:
            if offline:
                raise RuntimeError("offline")
            items, fields = fetch(src)
            fieldlog[src["slug"]] = fields
            with open(cache, "w") as f:
                json.dump(items, f, separators=(",", ":"))
            print(f"{src['slug']}: {len(items)} permits, {sum(1 for p in items if p['contractor'])} with contractor, "
                  f"{sum(1 for p in items if p['owner'])} owner-pulled")
        except Exception as ex:
            if not os.path.exists(cache):
                print(f"{src['slug']}: skipped ({ex})")
                continue
            items = json.load(open(cache))
            print(f"{src['slug']}: using cached data ({ex})")
        cutoff = (TODAY - dt.timedelta(days=DAYS - 1)).isoformat()
        items = sorted((p for p in items if p["date"] >= cutoff), key=lambda p: (p["date"], p["value"]), reverse=True)
        if len(items) < 20:
            print(f"{src['slug']}: too few recent permits, left out")
            continue
        cities.append((src, items, render_city(src, items, fieldlog.get(src["slug"]))))
    if fieldlog:
        with open(os.path.join(DATA, "_fields.json"), "w") as f:
            json.dump(fieldlog, f, indent=1)
    if not cities:
        sys.exit("no cities rendered")
    render_hub(cities)
    render_sitemap(cities)


if __name__ == "__main__":
    main()
