"""Probe open-data feeds for distressed-property signals: tax delinquency,
foreclosure / sheriff sale, probate, code violations, vacancy."""
import json, urllib.request, urllib.parse

def get(url, timeout=40):
    req = urllib.request.Request(url, headers={"User-Agent": "lead-probe/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")

CANDIDATES = [
    # (name, kind, url)
    ("philly tax delinquencies", "carto", "https://phl.carto.com/api/v2/sql?q=SELECT%20*%20FROM%20real_estate_tax_delinquencies%20LIMIT%202"),
    ("philly tax delinq count", "carto", "https://phl.carto.com/api/v2/sql?q=SELECT%20count(*)%20FROM%20real_estate_tax_delinquencies"),
    ("philly L&I violations", "carto", "https://phl.carto.com/api/v2/sql?q=SELECT%20*%20FROM%20violations%20ORDER%20BY%20violationdate%20DESC%20LIMIT%202"),
    ("philly sheriff sales", "carto", "https://phl.carto.com/api/v2/sql?q=SELECT%20*%20FROM%20sheriff_sales%20LIMIT%202"),
    ("philly vacant", "carto", "https://phl.carto.com/api/v2/sql?q=SELECT%20*%20FROM%20vacant_indicators_points%20LIMIT%202"),
    ("philly opa properties", "carto", "https://phl.carto.com/api/v2/sql?q=SELECT%20*%20FROM%20opa_properties_public%20LIMIT%201"),
    ("cook county tax sale/delinq", "socrata", "https://datacatalog.cookcountyil.gov/api/views/metadata/v1?search=delinquent"),
    ("cook county catalog foreclosure", "socrata", "https://datacatalog.cookcountyil.gov/api/catalog/v1?q=foreclosure&domains=datacatalog.cookcountyil.gov&limit=5"),
    ("chicago vacant buildings", "socrata", "https://data.cityofchicago.org/resource/7nii-7srd.json?$limit=2&$order=date_service_request_was_received%20DESC"),
    ("chicago code violations", "socrata", "https://data.cityofchicago.org/resource/22u3-xenr.json?$limit=2&$order=violation_date%20DESC"),
    ("nyc catalog lis pendens", "socrata", "https://data.cityofnewyork.us/api/catalog/v1?q=lien%20sale&limit=5"),
    ("nyc tax lien sale list", "socrata", "https://data.cityofnewyork.us/resource/9rz4-mjek.json?$limit=2"),
    ("detroit tax foreclosure", "arcgis", "https://services2.arcgis.com/qvkbeam7Wirps6zC/arcgis/rest/services/Tax_Foreclosures/FeatureServer/0/query?where=1%3D1&outFields=*&resultRecordCount=2&f=json"),
    ("baltimore tax sale", "socrata", "https://data.baltimorecity.gov/api/catalog/v1?q=tax%20sale&limit=5"),
    ("kc catalog", "socrata", "https://data.kcmo.org/api/catalog/v1?q=delinquent&limit=5"),
    ("dallas catalog", "socrata", "https://www.dallasopendata.com/api/catalog/v1?q=code%20violation&limit=5"),
    ("austin code complaints", "socrata", "https://data.austintexas.gov/resource/4r4g-vcty.json?$limit=2"),
    ("new orleans code enforcement", "socrata", "https://data.nola.gov/resource/3ejt-4nbr.json?$limit=2"),
    ("new orleans catalog", "socrata", "https://data.nola.gov/api/catalog/v1?q=sheriff%20sale&limit=5"),
    ("la county assessor", "socrata", "https://data.lacounty.gov/api/catalog/v1?q=delinquent&limit=5"),
    ("socrata global search delinquent tax", "socrata", "https://api.us.socrata.com/api/catalog/v1?q=delinquent%20tax&only=datasets&limit=15"),
    ("socrata global search foreclosure", "socrata", "https://api.us.socrata.com/api/catalog/v1?q=foreclosure&only=datasets&limit=15"),
    ("socrata global search probate", "socrata", "https://api.us.socrata.com/api/catalog/v1?q=probate&only=datasets&limit=10"),
    ("socrata global search vacant property", "socrata", "https://api.us.socrata.com/api/catalog/v1?q=vacant%20property%20registration&only=datasets&limit=10"),
    ("socrata global search sheriff sale", "socrata", "https://api.us.socrata.com/api/catalog/v1?q=sheriff%20sale&only=datasets&limit=10"),
    ("socrata global search code violations", "socrata", "https://api.us.socrata.com/api/catalog/v1?q=code%20violations&only=datasets&limit=15"),
]

for name, kind, url in CANDIDATES:
    print(f"\n===== {name}")
    try:
        body = get(url)
        try:
            d = json.loads(body)
        except Exception:
            print(body[:800]); continue
        if isinstance(d, dict) and "results" in d:
            for r in d["results"]:
                res = r.get("resource", {})
                print("-", res.get("name"), "|", r.get("metadata", {}).get("domain"), "|", res.get("id"), "| updated", res.get("updatedAt"), "| rows", res.get("columns_name", [])[:8] if False else "")
        elif isinstance(d, dict) and "rows" in d:
            print(json.dumps(d["rows"])[:1500])
        else:
            print(json.dumps(d)[:1500])
    except Exception as e:
        print("FAIL", e)
