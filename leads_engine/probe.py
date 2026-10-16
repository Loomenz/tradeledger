"""Round 3: Chicagoland + Northwest Indiana sources."""
import json, urllib.request, urllib.parse

def get(url, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": "lead-probe/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")

def socrata(name, host, ds, order=None):
    print(f"\n===== {name} ({host}/{ds})")
    try:
        meta = json.loads(get(f"https://{host}/api/views/{ds}.json"))
        print("updated", meta.get("rowsUpdatedAt"), "| cols:", [c.get("fieldName") for c in meta.get("columns", [])][:40])
        print("rows", json.loads(get(f"https://{host}/resource/{ds}.json?$select=count(*)")))
        q = {"$limit": 2}
        if order: q["$order"] = f"{order} DESC"
        for r in json.loads(get(f"https://{host}/resource/{ds}.json?{urllib.parse.urlencode(q)}")): print(json.dumps(r)[:900])
    except Exception as e:
        print("FAIL", e)

def catalog(name, host, q, limit=12):
    print(f"\n===== CATALOG {name}: {q}")
    try:
        d = json.loads(get(f"https://{host}/api/catalog/v1?q={urllib.parse.quote(q)}&only=datasets&limit={limit}" + ("" if host.startswith("api.") else f"&domains={host}")))
        for r in d.get("results", []):
            res = r["resource"]; print("-", res.get("name"), "|", r["metadata"].get("domain"), "|", res.get("id"), "|", res.get("updatedAt"))
    except Exception as e:
        print("FAIL", e)

def arcgis_hub(name, q):
    print(f"\n===== ARCGIS HUB {name}: {q}")
    try:
        d = json.loads(get(f"https://hub.arcgis.com/api/v3/datasets?q={urllib.parse.quote(q)}&page[size]=12"))
        for r in d.get("data", []):
            a = r["attributes"]; print("-", a.get("name"), "|", a.get("source"), "|", a.get("url", "")[:140], "|", a.get("modified"))
    except Exception as e:
        print("FAIL", e)

def raw(name, url, n=1200):
    print(f"\n===== RAW {name}")
    try:
        print(get(url)[:n])
    except Exception as e:
        print("FAIL", e)

# Cook County / Chicago
catalog("cook county", "datacatalog.cookcountyil.gov", "tax sale", 15)
catalog("cook county", "datacatalog.cookcountyil.gov", "delinquent", 10)
catalog("cook county", "datacatalog.cookcountyil.gov", "assessor parcel", 10)
catalog("cook county", "datacatalog.cookcountyil.gov", "sheriff", 10)
catalog("cook county", "datacatalog.cookcountyil.gov", "probate", 10)
catalog("cook county", "datacatalog.cookcountyil.gov", "recorder", 10)
socrata("Cook treasurer annual tax sale", "datacatalog.cookcountyil.gov", "55ju-2fs9")
socrata("Cook treasurer scavenger sale", "datacatalog.cookcountyil.gov", "ydgz-vkrp")
socrata("Cook assessor parcel universe", "datacatalog.cookcountyil.gov", "tx2p-k2g9")
socrata("Cook assessor addresses/mailing", "datacatalog.cookcountyil.gov", "3723-97qp")
socrata("Chicago building violations", "data.cityofchicago.org", "22u3-xenr", "violation_date")
socrata("Chicago vacant/abandoned 311", "data.cityofchicago.org", "v6vf-nfxy", "created_date")
catalog("chicago", "data.cityofchicago.org", "vacant building", 8)
catalog("chicago", "data.cityofchicago.org", "demolition court", 8)
catalog("chicago", "data.cityofchicago.org", "water shut", 6)
# Illinois statewide + collar counties
catalog("illinois", "data.illinois.gov", "foreclosure", 8)
catalog("illinois", "data.illinois.gov", "tax sale", 8)
catalog("all socrata", "api.us.socrata.com", "Will County", 10)
catalog("all socrata", "api.us.socrata.com", "DuPage", 10)
catalog("all socrata", "api.us.socrata.com", "Lake County Indiana", 10)
catalog("all socrata", "api.us.socrata.com", "Indiana tax sale", 10)
arcgis_hub("lake county in", "Lake County Indiana parcels")
arcgis_hub("porter county in", "Porter County Indiana parcels")
arcgis_hub("will county il", "Will County Illinois parcels")
arcgis_hub("dupage county il", "DuPage County parcels")
arcgis_hub("tax sale indiana", "tax sale Indiana")
arcgis_hub("gary indiana", "Gary Indiana vacant")
# SRI (runs Indiana county tax sales) and Cook sheriff
raw("SRI tax sale lake county IN", "https://www.sriservices.com/sri-tax-sale-auctions/")
raw("Cook sheriff foreclosure sales", "https://www.cookcountysheriffil.gov/departments/c-c-s-p-d/civil-process/foreclosure-sales/")
raw("Cook county clerk of court foreclosure", "https://www.cookcountyclerkofcourt.org/court-divisions/chancery-division/mortgage-foreclosure")
raw("Lake County IN treasurer", "https://www.lakecountyin.gov/departments/treasurer/tax-sale")
raw("Indiana gateway", "https://gateway.ifionline.org/")
raw("Illinois PACER-free: foreclosure listings (fisher)", "https://www.fisherbassett.com/illinois-foreclosure-listings/")
