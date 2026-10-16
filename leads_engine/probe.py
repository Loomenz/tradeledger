"""Round 2: sample rows, counts and freshness from the promising feeds."""
import json, urllib.request, urllib.parse

def get(url, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": "lead-probe/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")

SOCRATA = [
    ("MD foreclosure notices (statewide)", "opendata.maryland.gov", "w3bc-8mnv", None),
    ("Prince George's MD foreclosures", "data.princegeorgescountymd.gov", "cni6-nr5g", None),
    ("Prince George's MD foreclosures 2", "data.princegeorgescountymd.gov", "mnie-hrv7", None),
    ("Colorado foreclosure filings", "data.colorado.gov", "chpv-m4xq", None),
    ("Colorado foreclosure sales", "data.colorado.gov", "tn2f-pf3u", None),
    ("King County WA foreclosure parcels", "data.kingcounty.gov", "nx4x-daw6", None),
    ("Norfolk VA delinquent taxes", "data.norfolk.gov", "7qie-z5gv", None),
    ("Richmond VA delinquent taxes 6mo+", "data.richmondgov.com", "83t5-hbac", None),
    ("Sonoma CA defaulted tax", "data.sonomacounty.ca.gov", "bp8v-uax7", None),
    ("Clermont OH delinquent tax", "internal.opendata.clermontauditor.org", "q52y-wzm4", None),
    ("Cook County annual tax sale", "datacatalog.cookcountyil.gov", "55ju-2fs9", None),
    ("Santa Clara probate cases", "data.sccgov.org", "rh64-rgza", None),
    ("Cincinnati vacant/foreclosed registration", "data.cincinnati-oh.gov", "w3jp-dfxy", None),
    ("NYC tax lien sale 90-day list", "data.cityofnewyork.us", "9rz4-mjek", "month"),
    ("NYC housing code violations", "data.cityofnewyork.us", "wvxf-dwi5", "inspectiondate"),
    ("Montgomery MD housing violations", "data.montgomerycountymd.gov", "k9nj-z35d", None),
    ("Chicago building violations", "data.cityofchicago.org", "22u3-xenr", "violation_date"),
    ("CT monthly foreclosures", "data.ct.gov", "jfkq-xawu", None),
]

for name, host, ds, order in SOCRATA:
    print(f"\n===== {name} ({host}/{ds})")
    try:
        meta = json.loads(get(f"https://{host}/api/views/{ds}.json"))
        cols = [c.get("fieldName") for c in meta.get("columns", [])]
        print("updated", meta.get("rowsUpdatedAt"), "| cols:", cols[:40])
        cnt = json.loads(get(f"https://{host}/resource/{ds}.json?$select=count(*)"))
        print("rows", cnt)
        q = {"$limit": 2}
        if order: q["$order"] = f"{order} DESC"
        rows = json.loads(get(f"https://{host}/resource/{ds}.json?{urllib.parse.urlencode(q)}"))
        for r in rows: print(json.dumps(r)[:900])
    except Exception as e:
        print("FAIL", e)

CARTO = [
    ("philly tables", "SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND (table_name ILIKE '%tax%' OR table_name ILIKE '%sheriff%' OR table_name ILIKE '%vacant%' OR table_name ILIKE '%delinq%' OR table_name ILIKE '%foreclos%') LIMIT 40"),
    ("philly L&I recent violations count 30d", "SELECT count(*) FROM violations WHERE casecreateddate > now() - interval '30 days'"),
    ("philly opa absentee sample", "SELECT location, owner_1, mailing_street, mailing_city_state, market_value, sale_date, sale_price FROM opa_properties_public WHERE mailing_city_state NOT ILIKE 'PHILADELPHIA%' AND category_code='1' LIMIT 3"),
]
for name, sql in CARTO:
    print(f"\n===== {name}")
    try:
        d = json.loads(get("https://phl.carto.com/api/v2/sql?q=" + urllib.parse.quote(sql)))
        print(json.dumps(d.get("rows"))[:1500])
    except Exception as e:
        print("FAIL", e)
