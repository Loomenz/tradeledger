"""What does a taxsaleresources.com public sale page expose per parcel (owner? address? amount?)."""
import re, urllib.request, html

def get(url, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 lead-probe/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")

u = "https://cloud.taxsaleresources.com/public/sales/indiana/lake/foreclosure/09-04-2026--xyZSoZX5"
b = get(u)
t = re.sub(r"\s+", " ", html.unescape(re.sub(r"<script.*?</script>|<style.*?</style>", " ", b, flags=re.S)))
t = re.sub(r"<[^>]+>", " ", t)
t = re.sub(r"\s+", " ", t)
i = t.find("Parcel")
print("TEXT LEN", len(t))
print(t[i:i + 3500])
print("\nLINKS:", sorted(set(re.findall(r'href="([^"]*(?:parcel|propert|sale)[^"]*)"', b)))[:12])
print("\nJSON-ish keys:", sorted(set(re.findall(r'"(owner[a-z_]*|address[a-z_]*|parcel[a-z_]*|opening_bid[a-z_]*|amount[a-z_]*)"', b)))[:30])
