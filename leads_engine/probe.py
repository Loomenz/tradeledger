"""Can CI read SRI's tax-sale listings (Lake/Porter IN)? Print what comes back."""
import re, urllib.request

def get(url, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 lead-probe/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.headers.get("content-type"), r.read().decode("utf-8", "replace")

for u in ["https://sriservices.com/properties?state=IN&county=Lake&saleType=tax",
          "https://sriservices.com/properties?state=IN&county=Porter&saleType=tax",
          "https://cloud.taxsaleresources.com/public/sales/indiana/lake/foreclosure/09-04-2026--xyZSoZX5"]:
    print("\n=====", u)
    try:
        st, ct, body = get(u)
        print(st, ct, len(body))
        print(re.sub(r"\s+", " ", body)[:1500])
        print("script srcs:", re.findall(r'<script[^>]+src="([^"]+)"', body)[:12])
        print("api-ish:", sorted(set(re.findall(r'https?://[^"\'\s]*(?:api|graphql|properties)[^"\'\s]*', body)))[:15])
    except Exception as e:
        print("FAIL", e)
