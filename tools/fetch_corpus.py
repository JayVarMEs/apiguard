"""T1 -- download the preferred version of every API in the APIs.guru directory into corpus/<provider>/.
    python tools/fetch_corpus.py [--out corpus] [--max-mb 8]
Writes corpus/manifest.json (snapshot date, URL, size, status of every file) -- keep it: the report must state the snapshot date."""
import argparse, concurrent.futures as cf, json, time, urllib.request
from pathlib import Path
ap = argparse.ArgumentParser(); ap.add_argument("--out", default="corpus"); ap.add_argument("--max-mb", type=float, default=8.0)
ap.add_argument("--workers", type=int, default=8); a = ap.parse_args()
UA = {"User-Agent": "curl/8.5.0"}                      # the APIs.guru host refuses the default Python user agent
out = Path(a.out); out.mkdir(exist_ok=True); cap = int(a.max_mb * 1e6)
lst = json.load(urllib.request.urlopen(urllib.request.Request("https://api.apis.guru/v2/list.json", headers=UA), timeout=120))
print("directory lists", len(lst), "APIs")
def fetch(key):
    ver = lst[key]["versions"][lst[key]["preferred"]]; url = ver["swaggerUrl"]; prov = key.split(":")[0]
    dest = out / prov / (key.replace(":", "__").replace("/", "_") + ".json")
    if dest.exists(): return key, "cached", dest.stat().st_size, url, ver["openapiVer"]
    err = ""
    for t in range(3):
        try:
            data = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60).read(cap + 1)
            if len(data) > cap: return key, "too_big", len(data), url, ver["openapiVer"]
            dest.parent.mkdir(parents=True, exist_ok=True); dest.write_bytes(data); return key, "ok", len(data), url, ver["openapiVer"]
        except Exception as ex: err = repr(ex)[:80]; time.sleep(1 + t)
    return key, "error: " + err, 0, url, ver["openapiVer"]
rows = []
with cf.ThreadPoolExecutor(a.workers) as ex:
    for i, r in enumerate(ex.map(fetch, list(lst)), 1):
        rows.append(r); i % 250 == 0 and print(i)
manifest = {"snapshot_date": time.strftime("%Y-%m-%d"), "source": "https://api.apis.guru/v2/list.json", "n_listed": len(lst),
            "files": [dict(key=k, status=s, bytes=b, url=u, openapi=v) for k, s, b, u, v in rows]}
(out / "manifest.json").write_text(json.dumps(manifest)); 
from collections import Counter
print(Counter(s.split(":")[0] for _, s, *_ in rows), "snapshot", manifest["snapshot_date"])
