"""Lead Radar: distressed-property leads for Northwest Indiana and Chicagoland.

Pulls fresh distress signals (code violations, vacant-building reports, ...) from
official open-data feeds, resolves each property to its owner through the county
assessor's parcel records, scores the result and renders static pages plus CSV
downloads into ../leads. Standard library only; runs daily in GitHub Actions.

  python3 leads_engine/build.py            # fetch live data, then render
  python3 leads_engine/build.py --offline  # re-render from leads/data/*.json
"""
import csv, datetime as dt, html, io, json, os, re, sys, time, urllib.error, urllib.parse, urllib.request
from collections import Counter, defaultdict

from sources import MARKETS, ENTITY, RESIDENTIAL

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "leads")
DATA = os.path.join(OUT, "data")
SITE = "https://loomenz.github.io/tradeledger"
DAYS = 30            # how far back a signal counts as "fresh"
KEEP = 120           # how long a property stays in the file after its last signal
ALERT_EMAIL = "tradeledger.tools@gmail.com"
TODAY = dt.date.today()
UA = {"User-Agent": "LeadRadar/1.0 (+%s/leads/)" % SITE}
e = html.escape
ENTITY_RE = re.compile(ENTITY, re.I)
RES_RE = re.compile(RESIDENTIAL)


# ---------------------------------------------------------------- http
def get_json(url, timeout=120, tries=3):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
                return json.load(r)
        except urllib.error.HTTPError as ex:
            body = ex.read(400).decode("utf-8", "replace")
            if ex.code == 400 or i == tries - 1:
                raise RuntimeError(f"HTTP {ex.code}: {body}") from None
            print(f"  retry {i + 1}: HTTP {ex.code}")
            time.sleep(3 * (i + 1))
        except Exception as ex:
            if i == tries - 1:
                raise
            print(f"  retry {i + 1}: {ex}")
            time.sleep(3 * (i + 1))


def socrata(host, ds, **params):
    q = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    return get_json(f"https://{host}/resource/{ds}.json?{q}")


def norm_addr(a):
    """Normalize a street address enough to join city and county records."""
    a = re.sub(r"[^\w ]", " ", (a or "").upper())
    a = re.sub(r"\b(APT|UNIT|STE|SUITE|FL|FLOOR|#)\b.*$", "", a)
    reps = {"AVENUE": "AVE", "STREET": "ST", "BOULEVARD": "BLVD", "ROAD": "RD", "DRIVE": "DR", "PLACE": "PL",
            "COURT": "CT", "LANE": "LN", "TERRACE": "TER", "PARKWAY": "PKWY", "HIGHWAY": "HWY", "NORTH": "N",
            "SOUTH": "S", "EAST": "E", "WEST": "W", "CIRCLE": "CIR", "SQUARE": "SQ", "TRAIL": "TRL", "WAY": "WAY"}
    words = [reps.get(w, w) for w in a.split()]
    # "1234-36 W FOO ST" range addresses: keep the first number
    if words and "-" in (a.split() or [""])[0]:
        words[0] = words[0].split("-")[0]
    return " ".join(words)


def title(s):
    return re.sub(r"\s+", " ", (s or "")).strip().title()


# ---------------------------------------------------------------- fetch
def fetch_signals(sig):
    since = (TODAY - dt.timedelta(days=DAYS)).isoformat()
    where = f"{sig['date']} >= '{since}T00:00:00'"
    if sig.get("where"):
        where += f" AND ({sig['where']})"
    rows = socrata(sig["host"], sig["dataset"], **{"$where": where, "$select": sig["select"], "$order": f"{sig['date']} DESC", "$limit": 60000})
    out = []
    for r in rows:
        addr = norm_addr(r.get(sig["address"]))
        date = (r.get(sig["date"]) or "")[:10]
        if not addr or not addr[0].isdigit() or not date or date > TODAY.isoformat():
            continue
        out.append({"key": sig["key"], "date": date, "addr": addr, "desc": title(r.get(sig["desc"]))[:120], "city": sig["city"]})
    print(f"  {sig['key']}: {len(rows)} rows, {len(out)} usable")
    return out


def columns(host, ds):
    try:
        meta = get_json(f"https://{host}/api/views/{ds}.json", timeout=60)
        return [c.get("fieldName") for c in meta.get("columns", [])]
    except Exception as ex:
        print(f"  columns of {ds}: {ex}")
        return []


def fetch_owners(owner, city, addrs):
    """Look up parcels for a set of normalized addresses, in batches, by address.
    Uses the current-year parcel universe; falls back to the all-years address table."""
    found = {}
    addrs = sorted(addrs)
    ds, extra = owner["dataset"], ""
    if owner.get("year_filter"):
        yr = socrata(owner["host"], ds, **{"$select": "max(year) as y"})[0]["y"]
        extra = f"year='{yr}' AND "
        print(f"  {ds}: using year {yr}")
    i = 0
    while i < len(addrs):
        batch = addrs[i:i + 40]
        inlist = ",".join("'" + a.replace("'", "''") + "'" for a in batch)
        where = f"{extra}{owner['city_field']}='{city}' AND {owner['addr_field']} in ({inlist})"
        try:
            rows = socrata(owner["host"], ds, **{"$where": where, "$limit": 2000})
        except Exception as ex:
            print(f"  owner batch {i // 40} on {ds} failed: {ex}")
            if ds != owner["fallback"]:
                ds = owner["fallback"]
                yr = socrata(owner["host"], ds, **{"$select": "max(year) as y"})[0]["y"]
                extra = f"year='{yr}' AND "
                print(f"  switching to {ds} (year {yr}); columns: {columns(owner['host'], ds)[:30]}")
                continue
            i += 40
            continue
        i += 40
        for r in rows:
            a = norm_addr(r.get(owner["addr_field"]))
            found.setdefault(a, []).append(r)
        if i % 400 == 0:
            print(f"  owners: {min(i, len(addrs))}/{len(addrs)} addresses, {len(found)} matched")
    return found


def pick_parcel(rows):
    """One address can be many PINs (condos). Prefer a residential, non-condo parcel."""
    def rank(r):
        c = str(r.get("class", ""))
        return (0 if RES_RE.match(c) and c != "299" else 1 if RES_RE.match(c) else 2, r.get("pin", ""))
    rows = sorted(rows, key=rank)
    return rows[0], len(rows)


def owner_fields(r):
    prop = norm_addr(r.get("prop_address_full"))
    mail = norm_addr(r.get("mail_address_full"))
    mail_city = title(r.get("mail_address_city_name"))
    mail_state = (r.get("mail_address_state") or "").upper()[:2]
    name = title(r.get("mail_address_name") or r.get("owner_address_name"))
    absentee = bool(mail) and mail != prop
    return {
        "pin": r.get("pin", ""), "class": str(r.get("class", "")),
        "owner": name, "entity": bool(ENTITY_RE.search(name)),
        "mail": f"{title(r.get('mail_address_full'))}, {mail_city}, {mail_state} {r.get('mail_address_zipcode_1', '')}".strip(", "),
        "mail_city": mail_city, "mail_state": mail_state,
        "absentee": absentee, "out_of_state": absentee and mail_state not in ("", "IL", "IN"),
        "zip": str(r.get("prop_address_zipcode_1") or "")[:5],
        "lat": r.get("lat"), "lon": r.get("lon"),
    }


# ---------------------------------------------------------------- scoring
def score(lead, weights):
    s, why = 0, []
    kinds = Counter(x["key"] for x in lead["signals"])
    for k, n in kinds.items():
        pts = min(weights[k] * n, weights[k] * 2 + 1)
        s += pts
        why.append(k)
    if lead["absentee"]:
        s += 2; why.append("absentee")
    if lead["out_of_state"]:
        s += 1; why.append("out-of-state")
    if lead["entity"]:
        s -= 1
    if len(kinds) >= 2:
        s += 2; why.append("multi-signal")
    fresh = max(x["date"] for x in lead["signals"])
    if fresh >= (TODAY - dt.timedelta(days=7)).isoformat():
        s += 1; why.append("this week")
    lead["score"], lead["why"] = s, why
    lead["grade"] = "A" if s >= 8 else "B" if s >= 5 else "C"
    return lead


def build_market(m, offline):
    cache = os.path.join(DATA, f"{m['slug']}.json")
    prev = {x["pin"]: x for x in json.load(open(cache))} if os.path.exists(cache) else {}
    weights = {s["key"]: s["weight"] for s in m["signals"]}
    if offline:
        leads = list(prev.values())
    else:
        signals = []
        for sig in m["signals"]:
            try:
                signals += fetch_signals(sig)
            except Exception as ex:
                print(f"  {sig['key']}: FAILED {ex}")
        by_addr = defaultdict(list)
        for s in signals:
            by_addr[(s["city"], s["addr"])].append(s)
        print(f"  {len(signals)} signals on {len(by_addr)} addresses")
        # Only resolve owners for addresses with enough going on to matter, or already known
        known = {(x["city"].upper(), x["addr"]) for x in prev.values()}
        wanted = {k for k, v in by_addr.items() if len(v) >= 2 or any(s["key"] != "nuisance" for s in v) or k in known}
        owners = {}
        for city in {c for c, _ in wanted}:
            owners.update({(city, a): rows for a, rows in fetch_owners(m["owner"], city, [a for c, a in wanted if c == city]).items()})
        print(f"  resolved {len(owners)}/{len(wanted)} addresses to parcels")
        missed = sorted(a for k in wanted if k not in owners for a in [k[1]])
        print(f"  unmatched sample: {missed[:12]}")
        leads = {}
        for key, rows in owners.items():
            parcel, units = pick_parcel(rows)
            lead = owner_fields(parcel)
            if not RES_RE.match(lead["class"]) and lead["class"]:
                continue  # commercial, exempt, vacant land: not this product
            city, addr = key
            old = prev.get(lead["pin"], {})
            seen = {(s["key"], s["date"], s["desc"]) for s in old.get("signals", [])}
            sigs = old.get("signals", []) + [s for s in by_addr[key] if (s["key"], s["date"], s["desc"]) not in seen]
            lead.update({
                "address": title(addr), "city": title(city), "units": units,
                "signals": sorted(sigs, key=lambda s: s["date"], reverse=True)[:40],
                "first_seen": old.get("first_seen", TODAY.isoformat()), "last_seen": TODAY.isoformat(),
            })
            leads[lead["pin"]] = lead
        # carry forward properties that had no new signal today
        for pin, old in prev.items():
            leads.setdefault(pin, old)
        leads = list(leads.values())
    cutoff = (TODAY - dt.timedelta(days=KEEP)).isoformat()
    leads = [score(x, weights) for x in leads if x["signals"] and max(s["date"] for s in x["signals"]) >= cutoff]
    leads.sort(key=lambda x: (-x["score"], max(s["date"] for s in x["signals"])), reverse=False)
    leads.sort(key=lambda x: -x["score"])
    os.makedirs(DATA, exist_ok=True)
    with open(cache, "w") as f:
        json.dump(leads, f, separators=(",", ":"))
    print(f"{m['slug']}: {len(leads)} leads, {sum(1 for x in leads if x['grade'] == 'A')} grade A, "
          f"{sum(1 for x in leads if x['absentee'])} absentee, {sum(1 for x in leads if x['out_of_state'])} out of state")
    return leads


# ---------------------------------------------------------------- render
ICONS = {
    "radar": '<path d="M19.07 4.93A10 10 0 0 0 6.99 3.34"/><path d="M4 6h.01"/><path d="M2.29 9.62A10 10 0 1 0 21.31 8.35"/><path d="M16.24 7.76A6 6 0 1 0 8.23 16.67"/><path d="M12 18h.01"/><path d="M17.99 11.66A6 6 0 0 1 15.77 16.67"/><circle cx="12" cy="12" r="2"/><path d="m13.41 10.59 5.66-5.66"/>',
    "arrow": '<path d="M5 12h14"/><path d="m12 5 7 7-7 7"/>',
    "download": '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m7 10 5 5 5-5"/><path d="M12 15V3"/>',
    "bell": '<path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/><path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"/>',
    "home": '<path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><path d="M9 22V12h6v10"/>',
    "zap": '<path d="M13 2 3 14h9l-1 8 10-12h-9l1-8z"/>',
    "db": '<ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M3 5v14a9 3 0 0 0 18 0V5"/><path d="M3 12a9 3 0 0 0 18 0"/>',
    "shield": '<path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/><path d="m9 12 2 2 4-4"/>',
    "map": '<path d="M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0Z"/><circle cx="12" cy="10" r="3"/>',
}


def icon(name, size=18):
    return (f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            f'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{ICONS[name]}</svg>')


EXTRA_CSS = """
.gr{display:inline-grid;place-items:center;width:30px;height:30px;border-radius:9px;font-weight:800;font-size:.85rem}
.gr.A{background:linear-gradient(135deg,var(--accent),var(--accent-2));color:#1a0f00}.gr.B{background:rgba(45,212,191,.18);color:var(--brand)}.gr.C{background:var(--panel-2);color:var(--mute)}
.sig{display:inline-block;font-size:.72rem;font-weight:700;padding:2px 8px;border-radius:999px;margin:2px 4px 0 0;white-space:nowrap}
.sig.violation{color:#fca5a5;background:rgba(239,68,68,.14)}.sig.vacant{color:#fdba74;background:rgba(251,146,60,.16)}.sig.nuisance{color:var(--ink-2);background:var(--panel-2)}
.sig.absentee{color:var(--brand);background:rgba(45,212,191,.12)}.sig.oos{color:#c4b5fd;background:rgba(139,92,246,.16)}.sig.entity{color:var(--mute);background:var(--panel)}
.lock{color:var(--mute);font-size:.82rem}.lock svg{vertical-align:-3px}
.why{display:grid;grid-template-columns:repeat(2,1fr);gap:16px;margin-top:26px}.why div{background:var(--panel);border:1px solid var(--line);border-radius:var(--r);padding:22px}.why b{display:block;margin-bottom:6px}
.price{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin-top:26px}.pc{background:var(--panel);border:1px solid var(--line);border-radius:var(--r);padding:26px}.pc.hot{border-color:rgba(245,158,11,.5);background:linear-gradient(180deg,rgba(245,158,11,.08),var(--panel))}
.pc .amt{font-size:2rem;font-weight:800;letter-spacing:-.03em}.pc .amt small{font-size:.9rem;color:var(--mute);font-weight:600}.pc ul{padding-left:18px;color:var(--ink-2);margin:12px 0 18px}
.two{grid-template-columns:1.7fr .7fr}.two>div{min-width:0}.lock{white-space:nowrap}
@media (max-width:960px){.price,.why,.two{grid-template-columns:1fr}}
@media (max-width:640px){th:nth-child(4),td:nth-child(4){display:table-cell}th:nth-child(5),td:nth-child(5){display:none}}
"""


def page(title_, desc, path, body, depth, noindex=False):
    up = "../" * depth
    robots = '<meta name="robots" content="noindex,follow">' if noindex else ""
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(title_)}</title><meta name="description" content="{e(desc)}">{robots}
<link rel="canonical" href="{SITE}/{path}">
<meta property="og:title" content="{e(title_)}"><meta property="og:description" content="{e(desc)}">
<meta property="og:image" content="{SITE}/cover.png"><meta name="theme-color" content="#070b14">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@500&display=swap" rel="stylesheet">
<link rel="stylesheet" href="{up}permits/radar.css"><style>{EXTRA_CSS}</style></head><body>
<header class="nav"><div class="wrap navin"><a class="brand" href="{up}leads/index.html"><span class="logo">{icon('home', 18)}</span><span>Lead Radar</span><em>by TradeLedger</em></a>
<nav><a href="{up}leads/index.html#markets">Markets</a><a href="{up}leads/index.html#how">How it works</a><a href="{up}leads/index.html#pricing">Pricing</a><a href="{up}index.html">Tools</a></nav>
<a class="btn sm" href="#alerts">{icon('bell', 15)} Get the list</a></div></header>
<main>{body}</main>
<footer class="foot"><div class="wrap"><div><b>Lead Radar</b> finds distressed and absentee-owned properties in Northwest Indiana and Chicagoland from official county and city records, refreshed every morning. Updated {TODAY.strftime('%B %-d, %Y')}. Public records only; no credit, phone or email data is shown on this site.</div>
<div class="fl"><a href="{up}leads/index.html">All markets</a><a href="{up}permits/index.html">Permit Radar</a><a href="{up}index.html">TradeLedger</a><a href="mailto:{ALERT_EMAIL}">Contact</a></div></div></footer>
<script>
const io=new IntersectionObserver(es=>es.forEach(x=>{{if(x.isIntersecting){{x.target.classList.add('in');io.unobserve(x.target)}}}}),{{threshold:.12}});
document.querySelectorAll('.reveal').forEach(el=>io.observe(el));
document.querySelectorAll('[data-count]').forEach(el=>{{const end=+el.dataset.count,pre=el.dataset.pre||'',suf=el.dataset.suf||'';
if(matchMedia('(prefers-reduced-motion: reduce)').matches){{return}}let t0=null;const f=t=>{{t0??=t;const k=Math.min(1,(t-t0)/1100);
el.textContent=pre+Math.round(end*(1-Math.pow(1-k,3))).toLocaleString()+suf;if(k<1)requestAnimationFrame(f)}};requestAnimationFrame(f)}});
const q=document.getElementById('q');if(q)q.addEventListener('input',()=>{{const v=q.value.toLowerCase();
document.querySelectorAll('#ptable tbody tr').forEach(r=>r.hidden=!r.textContent.toLowerCase().includes(v))}});
</script></body></html>"""


def stat(n, label, pre="", suf=""):
    return f'<div><b data-count="{n}" data-pre="{pre}" data-suf="{suf}">{pre}{n:,}{suf}</b><span>{label}</span></div>'


def nice_date(d):
    return dt.date.fromisoformat(d).strftime("%b %-d")


def alerts_box(m=None):
    where = m["name"] if m else "Northwest Indiana and Chicagoland"
    return f"""<section class="alerts reveal" id="alerts"><div class="wrap"><div class="abox">
<div><span class="eyebrow">{icon('bell', 14)} Early access</span><h2>Get the full {e(where)} list with owner names and mailing addresses.</h2>
<p>Investors, wholesalers and agents: tell us your market and what you buy. We'll send the complete list, the daily new-lead feed, and a price. Skip-traced phone numbers come as an add-on, verified live before you pay for them.</p></div>
<form action="https://formsubmit.co/{ALERT_EMAIL}" method="POST" class="aform">
<input type="hidden" name="_subject" value="Lead Radar access request"><input type="hidden" name="_template" value="table">
<input type="hidden" name="_next" value="{SITE}/leads/thanks.html"><input type="text" name="_honey" style="display:none" tabindex="-1" autocomplete="off">
<label>Work email<input type="email" name="email" required placeholder="you@yourcompany.com"></label>
<label>Market<input type="text" name="market" value="{e(where)}" required></label>
<label>What do you buy?<input type="text" name="buys" placeholder="Fix and flip, buy and hold, wholesale, listings"></label>
<button class="btn full" type="submit">{icon('zap', 16)} Request the list</button>
<small>No spam. We reply personally within a day.</small></form></div></div></section>"""


def sig_tags(lead):
    kinds = Counter(x["key"] for x in lead["signals"])
    tags = "".join(f'<span class="sig {k}">{e(LABELS[k])}{" ×" + str(n) if n > 1 else ""}</span>' for k, n in kinds.most_common())
    if lead["absentee"]:
        tags += '<span class="sig absentee">Absentee owner</span>'
    if lead["out_of_state"]:
        tags += '<span class="sig oos">Out of state</span>'
    if lead["entity"]:
        tags += '<span class="sig entity">Company / trust</span>'
    return tags


def lead_table(leads, limit=400):
    rows = []
    for x in leads[:limit]:
        latest = x["signals"][0]
        owner_hint = ("Mail goes to " + e(f"{x['mail_city']}, {x['mail_state']}".strip(", "))) if x["absentee"] and x["mail_city"] else "Owner-occupied" if not x["absentee"] else ""
        rows.append(f'<tr><td><span class="gr {x["grade"]}">{x["grade"]}</span></td>'
                    f'<td><b>{e(x["address"])}</b>, {e(x["city"])} {e(x["zip"])}<div>{sig_tags(x)}</div><div class="d">{e(latest["desc"])}</div></td>'
                    f'<td class="mono">{nice_date(latest["date"])}</td>'
                    f'<td class="lock">{owner_hint}<br><span>{icon("shield", 13)} name in full list</span></td>'
                    f'<td class="mono r">{x["score"]}</td></tr>')
    more = f'<p class="mute small">Showing the top {limit} of {len(leads):,}. The full list, with owner names and mailing addresses, is in the download.</p>' if len(leads) > limit else ""
    return f"""<div class="tbl reveal"><div class="tblhead"><input id="q" type="search" placeholder="Filter by street, zip, signal or owner state" aria-label="Filter leads"></div>
<div class="scroll"><table id="ptable"><thead><tr><th>Grade</th><th>Property and signals</th><th>Latest</th><th>Owner</th><th class="r">Score</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table></div></div>{more}"""


def write(rel, text):
    path = os.path.join(OUT, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def write_csv(rel, leads, full):
    buf = io.StringIO()
    w = csv.writer(buf)
    head = ["grade", "score", "address", "city", "zip", "pin", "property_class", "units_at_address", "signals", "latest_signal", "latest_detail",
            "first_seen", "absentee", "out_of_state", "owner_is_entity", "owner_mail_city", "owner_mail_state"]
    if full:
        head += ["owner_name", "owner_mail_address"]
    w.writerow(head)
    for x in leads:
        row = [x["grade"], x["score"], x["address"], x["city"], x["zip"], x["pin"], x["class"], x["units"],
               "; ".join(f"{LABELS[k]} x{n}" for k, n in Counter(s["key"] for s in x["signals"]).items()),
               x["signals"][0]["date"], x["signals"][0]["desc"], x["first_seen"],
               "yes" if x["absentee"] else "", "yes" if x["out_of_state"] else "", "yes" if x["entity"] else "", x["mail_city"], x["mail_state"]]
        if full:
            row += [x["owner"], x["mail"]]
        w.writerow(row)
    write(rel, buf.getvalue())


def render_market(m, leads):
    a = [x for x in leads if x["grade"] == "A"]
    absentee = [x for x in leads if x["absentee"]]
    kinds = Counter(k for x in leads for k in {s["key"] for s in x["signals"]})
    pills = "".join(f'<span class="pill">{e(LABELS[k])} <b>{n:,}</b></span>' for k, n in kinds.most_common())
    zips = Counter(x["zip"] for x in a if x["zip"]).most_common(8)
    zip_html = "".join(f'<li><span class="rk">{i}</span><span class="nm">{z}</span><span class="ct">{n} grade-A lead{"s" if n != 1 else ""}</span></li>' for i, (z, n) in enumerate(zips, 1))
    title_ = f"{m['name']} Distressed Property Leads: Code Violations, Vacant Buildings, Absentee Owners"
    desc = f"{len(leads):,} properties in {m['short']} with fresh distress signals from official records, scored and refreshed daily. {len(absentee):,} are absentee-owned."
    body = f"""<section class="hero sm"><div class="glow"></div><div class="grid-bg"></div><div class="wrap">
<a class="crumb" href="../index.html">{icon('arrow', 14)} All markets</a>
<span class="eyebrow">{icon('map', 14)} {e(m['short'])}</span>
<h1>{e(m['name'])} <span class="grad">distressed property</span> leads</h1>
<p class="lead">{e(m['blurb'])} Every property below has at least one fresh distress signal from the last {DAYS} days. Grade A means several signals plus an owner who doesn't live there.</p>
<div class="ctas"><a class="btn big" href="#alerts">{icon('bell', 16)} Get the full list</a><a class="btn ghost big" href="sample.csv" download>{icon('download', 16)} Sample CSV</a></div>
<div class="pills">{pills}</div>
<div class="stats">{stat(len(leads), 'properties flagged')}{stat(len(a), 'grade A')}{stat(len(absentee), 'absentee owners')}{stat(sum(1 for x in leads if x['out_of_state']), 'out-of-state owners')}</div></div></section>
<section class="sec"><div class="wrap"><div class="two"><div><h2>Today's leads</h2><p class="lead">Sorted by score. Owner names and mailing addresses are held back on the public page and included in the full list.</p>{lead_table(leads)}</div>
<div><div class="board reveal"><h3>{icon('map')} Hottest zip codes</h3><ol>{zip_html}</ol></div>
<div class="board reveal" style="margin-top:16px"><h3>{icon('shield')} How scoring works</h3><p class="small" style="color:var(--ink-2)">Open code violation +2 each. Vacant-building report +3. Nuisance report +1. Absentee owner +2, out of state +1. Two different signal types +2. Activity this week +1. Company or trust owner −1. <b>A</b> is 8 or more, <b>B</b> is 5 to 7.</p></div></div></div></div></section>
{alerts_box(m)}"""
    write(f"{m['slug']}/index.html", page(title_, desc, f"leads/{m['slug']}/index.html", body, 2))
    write_csv(f"{m['slug']}/sample.csv", leads[:100], full=False)
    write_csv(f"data/{m['slug']}-full.csv", leads, full=True)   # not deployed; the product


def render_hub(markets):
    allv = [x for _, leads in markets for x in leads]
    cards = "".join(
        f'<a class="ccard reveal" href="{m["slug"]}/index.html"><div class="tt"><div><h3>{e(m["name"])}</h3><span class="mute">{e(m["short"])}</span></div>'
        f'<span class="n">{len(leads):,}</span></div><p class="small" style="color:var(--ink-2);margin:12px 0">{e(m["blurb"])}</p>'
        f'<div class="tf"><span>{sum(1 for x in leads if x["grade"] == "A"):,} grade A · {sum(1 for x in leads if x["absentee"]):,} absentee</span><span class="go">{icon("arrow", 15)}</span></div></a>'
        for m, leads in markets)
    coming = "".join(f'<div class="ccard" style="opacity:.55"><div class="tt"><div><h3>{n}</h3><span class="mute">{s}</span></div><span class="pill">Next</span></div></div>'
                     for n, s in [("Lake County", "Gary, Hammond, Crown Point, IN"), ("Porter County", "Valparaiso, Portage, IN"), ("Will County", "Joliet, Bolingbrook, IL"), ("DuPage County", "Naperville, Wheaton, IL")])
    top = sorted(allv, key=lambda x: -x["score"])[:6]
    feed = "".join(f'<div class="fi"><span class="gr {x["grade"]}">{x["grade"]}</span><b>{e(x["address"])}</b><span>{e(x["city"])}</span><span class="mono r">{x["score"]}</span></div>' for x in top)
    title_ = "Lead Radar: Distressed Property Leads for Northwest Indiana and Chicagoland"
    desc = "Fresh, local, scored distressed-property leads built from official county and city records: code violations, vacant buildings, absentee owners. Refreshed every morning."
    body = f"""<section class="hero"><div class="glow"></div><div class="grid-bg"></div><div class="wrap herogrid">
<div><span class="eyebrow">{icon('zap', 14)} Refreshed every morning</span>
<h1>Motivated sellers, <span class="grad">found in the records</span> before anyone calls them.</h1>
<p class="lead">Lead Radar reads the official records of Chicagoland and Northwest Indiana counties every day: code violations, vacant-building reports, and who actually owns each property and where their mail goes. Then it scores every property so you work the best ones first.</p>
<div class="ctas"><a class="btn big" href="#markets">Browse markets {icon('arrow', 16)}</a><a class="btn ghost big" href="#alerts">{icon('bell', 16)} Get the list</a></div></div>
<div class="feed reveal"><div class="fh"><span class="dot"></span> Top leads today</div>{feed}</div></div>
<div class="wrap"><div class="stats big">{stat(len(allv), 'properties flagged')}{stat(sum(1 for x in allv if x['grade'] == 'A'), 'grade A leads')}{stat(sum(1 for x in allv if x['absentee']), 'absentee owners')}{stat(len(markets), 'counties live')}</div></div></section>
<section class="sec" id="markets"><div class="wrap"><h2>Pick a market</h2><p class="lead">Local only. Every lead is from the county you're buying in, with the record it came from.</p><div class="cgrid">{cards}{coming}</div></div></section>
<section class="sec alt" id="how"><div class="wrap"><h2>Why these leads are different</h2><div class="why">
<div class="reveal"><b>Fresh, not recycled.</b> National lead sites resell the same list for months. Ours is rebuilt from the source records every morning and shows the date of each signal.</div>
<div class="reveal"><b>Stacked signals, not one.</b> A violation alone is noise. A violation on a house whose owner's mail goes to Arizona, reported vacant last week, is a seller. We score the stack.</div>
<div class="reveal"><b>Owner resolved from the assessor.</b> Every property is matched to the county's own parcel record, so the owner name and mailing address are the official ones, not guessed.</div>
<div class="reveal"><b>Verified before you pay.</b> Phone numbers are an add-on, skip-traced on request and checked live. Disconnected numbers are credited, not charged.</div></div>
<div class="steps" style="margin-top:40px"><div class="step reveal"><span class="ico">{icon('db', 20)}</span><h3>Pull the records</h3><p>City violation and 311 feeds plus county assessor parcel data, all official open data.</p></div>
<div class="step reveal"><span class="ico">{icon('home', 20)}</span><h3>Match and score</h3><p>Each address is matched to its parcel and owner, then scored on signals, freshness and absentee status.</p></div>
<div class="step reveal"><span class="ico">{icon('bell', 20)}</span><h3>You get the list</h3><p>Daily CSV of new leads, the full owner mailing list for direct mail, and optional verified phones.</p></div></div></div></section>
<section class="sec" id="pricing"><div class="wrap"><h2>Pricing</h2><p class="lead">Early-access pricing for the first buyers in each county. Cancel any time.</p><div class="price">
<div class="pc reveal"><h3>County list</h3><div class="amt">$79<small>/mo</small></div><ul><li>One county, every lead with owner name and mailing address</li><li>Daily CSV of new leads</li><li>Grades, scores and source records</li></ul><a class="btn ghost full" href="#alerts">Request access</a></div>
<div class="pc hot reveal"><h3>All five counties</h3><div class="amt">$199<small>/mo</small></div><ul><li>Cook, Will, DuPage, Lake and Porter</li><li>Daily CSV plus a weekly grade-A digest</li><li>Priority on new signal types</li></ul><a class="btn full" href="#alerts">Request access</a></div>
<div class="pc reveal"><h3>Verified phones</h3><div class="amt">$0.45<small>/record</small></div><ul><li>Skip-traced owner phone and email, on request</li><li>Live carrier check before billing</li><li>Bounces credited back</li></ul><a class="btn ghost full" href="#alerts">Add to any plan</a></div></div>
<div class="faq" style="margin-top:30px"><details><summary>Is this legal?</summary><p>Yes. Violation records, 311 reports and assessor parcel records are public records published by the city and county. We do not publish owner names on this site; they are delivered to subscribers for lawful marketing. Buyers who call must follow TCPA and Do-Not-Call rules; we never cold-call anyone.</p></details>
<details><summary>What about tax sales, foreclosures and probate?</summary><p>Those lists exist for every county here but are not published as open data. We are adding them county by county as we can source them reliably. Subscribers get each new signal type as it lands.</p></details></div></div></section>
{alerts_box()}"""
    write("index.html", page(title_, desc, "leads/index.html", body, 1))
    write("thanks.html", page("Request received | Lead Radar", "We'll be in touch.", "leads/thanks.html",
          f'<section class="hero sm"><div class="glow"></div><div class="wrap"><h1>Got it.</h1><p class="lead">We\'ll reply personally within a day with the list and a price.</p><a class="btn" href="index.html">Back to Lead Radar</a></div></section>', 1, noindex=True))
    urls = [f"{SITE}/leads/index.html"] + [f"{SITE}/leads/{m['slug']}/index.html" for m, _ in markets]
    write("sitemap.xml", '<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' +
          "".join(f"<url><loc>{u}</loc><lastmod>{TODAY.isoformat()}</lastmod><changefreq>daily</changefreq></url>" for u in urls) + "</urlset>")


LABELS = {s["key"]: s["label"] for m in MARKETS for s in m["signals"]}


def main():
    offline = "--offline" in sys.argv
    os.makedirs(DATA, exist_ok=True)
    markets = []
    for m in MARKETS:
        print(f"== {m['name']}")
        try:
            leads = build_market(m, offline)
        except Exception as ex:
            print(f"{m['slug']}: FAILED {ex}")
            cache = os.path.join(DATA, f"{m['slug']}.json")
            if not os.path.exists(cache):
                continue
            leads = json.load(open(cache))
        if leads:
            render_market(m, leads)
            markets.append((m, leads))
    if not markets:
        sys.exit("no markets rendered")
    render_hub(markets)


if __name__ == "__main__":
    main()
