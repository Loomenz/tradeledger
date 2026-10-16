"""Check which county parcel layers respond from CI and list their fields plus one sample row."""
import json, urllib.request, urllib.parse

def get(url, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": "lead-probe/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))

LAYERS = {
    "will": "https://gis.willcountyillinois.com/server/rest/services/Basemap/Parcels_20/MapServer/0",
    "dupage": "https://gis.dupageco.org/arcgis/rest/services/DuPage_County_IL/ParcelsWithRealEstateCC/FeatureServer/0",
    "dupage-open": "https://gis.dupageco.org/arcgis/rest/services/OpenData/Parcels/MapServer/0",
    "indiana": "https://gisdata.in.gov/server/rest/services/Hosted/Parcels_2023/FeatureServer/0",
    "indiana-boundaries": "https://gisdata.in.gov/server/rest/services/Hosted/Parcel_Boundaries_of_Indiana_Current/FeatureServer/0",
}
for k, u in LAYERS.items():
    print(f"\n===== {k}: {u}")
    try:
        meta = get(u + "?f=pjson")
        print("name:", meta.get("name"), "| maxRecordCount:", meta.get("maxRecordCount"))
        print("fields:", [f["name"] for f in meta.get("fields", [])])
        q = urllib.parse.urlencode({"where": "1=1", "outFields": "*", "resultRecordCount": 2, "returnGeometry": "false", "f": "json"})
        rows = get(u + "/query?" + q).get("features", [])
        for r in rows:
            print("sample:", json.dumps(r.get("attributes"))[:700])
    except Exception as e:
        print("FAIL", e)
