"""Why do ~36% of Chicago addresses find no Cook parcel? Look at how the assessor stores a few of them."""
import json, urllib.request, urllib.parse

def get(url, timeout=90):
    req = urllib.request.Request(url, headers={"User-Agent": "lead-probe/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))

H = "https://datacatalog.cookcountyil.gov/resource/3723-97qp.json"
def q(where, n=4, sel="pin,year,prop_address_full,prop_address_city_name,prop_address_zipcode_1,mail_address_name"):
    try:
        return get(H + "?" + urllib.parse.urlencode({"$where": where, "$select": sel, "$order": "year DESC", "$limit": n}))
    except Exception as e:
        return f"FAIL {e}"

for num, street in [("100", "LEAMINGTON"), ("10048", "INDIANAPOLIS"), ("1019", "JACKSON"), ("102", "70TH"), ("10346", "WESTERN"), ("1042", "87TH")]:
    print(f"\n== {num} {street}: no city filter, any year")
    print(json.dumps(q(f"prop_address_full like '{num} %{street}%'"), indent=0)[:900])
print("\n== distinct cities for zip 60644")
print(q("prop_address_zipcode_1='60644' AND year='2025'", 3))
print("\n== distinct city names (sample, group)")
print(get(H + "?" + urllib.parse.urlencode({"$select": "prop_address_city_name,count(*)", "$where": "year='2025'", "$group": "prop_address_city_name", "$order": "count DESC", "$limit": 12})))
print("\n== rows per year")
print(get(H + "?" + urllib.parse.urlencode({"$select": "year,count(*)", "$group": "year", "$order": "year DESC", "$limit": 6})))
