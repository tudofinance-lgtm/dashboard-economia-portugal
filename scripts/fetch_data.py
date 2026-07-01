"""
fetch_data.py — Cache layer for DashboardPortugal.pt
Runs daily via GitHub Actions. Fetches BPstat, Eurostat, ECB APIs
and writes data/cache.json consumed by the static frontend.

Usage: python scripts/fetch_data.py
"""

import json
import time
import logging
from datetime import datetime, timezone
from typing import Optional

import requests

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "DashboardPortugal/1.0 (cache bot)"})

def get(url, timeout=20, **kwargs):
    """GET with retry (3x) and exponential backoff."""
    for attempt in range(3):
        try:
            r = SESSION.get(url, timeout=timeout, **kwargs)
            r.raise_for_status()
            return r
        except Exception as e:
            if attempt == 2:
                raise
            wait = 2 ** attempt
            log.warning(f"Attempt {attempt+1} failed ({e}), retrying in {wait}s…")
            time.sleep(wait)

# ──────────────────────────────────────────────────────────
# BPSTAT
# ──────────────────────────────────────────────────────────
BPSTAT = "https://bpstat.bportugal.pt/data/v1"

# All series used by the frontend
BPSTAT_SERIES = [
    12518356,  # PIB anual preços correntes M€
    12518283,  # PIB trimestral vcsc M€
    12512877,  # Endividamento Particulares
    12710744,  # Prestação Habitação mediana
    12457924,  # Balança Corrente
    12645509,  # Saldo Orçamental AP % PIB
    88895,     # Saldo Seg. Social
    88873,     # Receita Estado
    88884,     # Despesa Estado
    12560943,  # Saldo mensal acumulado YTD
    12645918,  # Petróleo Brent EUR/bbl
    12099459,  # OT 10Y daily (spread)
    12561507,  # Dívida AP % PIB — Eurostat/EDP (mais actualizado)
    # Capacidade/Necessidade Financiamento por setor
    12414395, 12427901, 12439580, 12445096, 12456320,
    # Receitas AP por categoria
    12560971, 12560975, 12560979, 12560983, 12560955,
    # Despesas AP por categoria
    12560987, 12560988, 12560989, 12560990, 12560991, 12560992, 12560967,
    # Confiança
    12561508, 12561511, 12561512,
]

def fetch_bpstat_series(series_id: int) -> Optional[list]:
    """Fetch all observations for one BPstat series → [{date, value}]"""
    try:
        meta_r = get(f"{BPSTAT}/series/?series_ids={series_id}&lang=PT")
        meta = meta_r.json()[0]
        domain_id = meta["domain_ids"][0]
        dataset_id = meta["dataset_id"]

        # Filtered endpoint (fast path)
        url = f"{BPSTAT}/domains/{domain_id}/datasets/{dataset_id}/?lang=PT&series_ids={series_id}"
        ds_r = get(url)
        ds = ds_r.json()
        pts = extract_bpstat(ds, series_id)
        if pts:
            return pts

        # Full scan fallback
        page = 1
        while page <= 50:
            url = f"{BPSTAT}/domains/{domain_id}/datasets/{dataset_id}/?lang=PT&page={page}"
            ds = get(url).json()
            pts = extract_bpstat(ds, series_id)
            if pts is not None:
                return pts
            if not ds.get("extension", {}).get("next_page"):
                break
            page += 1
    except Exception as e:
        log.error(f"BPstat {series_id} failed: {e}")
    return None

def extract_bpstat(ds: dict, target_id: int) -> Optional[list]:
    """Extract [{date, value}] for target_id from a BPstat dataset page."""
    series_list = ds.get("extension", {}).get("series", [])
    target = next((s for s in series_list if s["id"] == target_id), None)
    if not target:
        return None

    dim_ids   = ds["id"]
    dim_sizes = ds["size"]
    dims      = ds["dimension"]
    values    = ds["value"]
    time_role = (ds.get("role", {}).get("time") or ["reference_date"])[0]
    time_idx  = dim_ids.index(time_role)

    strides = [1] * len(dim_ids)
    for i in range(len(dim_ids) - 2, -1, -1):
        strides[i] = strides[i + 1] * dim_sizes[i + 1]

    dim_cat = {str(dc["dimension_id"]): dc["category_id"]
               for dc in target["dimension_category"]}

    base = 0
    for i, did in enumerate(dim_ids):
        if did == time_role:
            continue
        cat_id  = dim_cat.get(str(did))
        cat_arr = dims[did]["category"]["index"]
        cat_idx = list(map(str, cat_arr)).index(str(cat_id)) if str(cat_id) in list(map(str, cat_arr)) else -1
        if cat_idx >= 0:
            base += cat_idx * strides[i]

    dates = dims[time_role]["category"]["index"]
    result = []
    for t, date in enumerate(dates):
        key = base + t * strides[time_idx]
        v = values[key] if isinstance(values, list) else values.get(str(key))
        if v is not None:
            result.append({"date": date, "value": v})
    return result if result else None

def fetch_all_bpstat() -> dict:
    out = {}
    for sid in BPSTAT_SERIES:
        log.info(f"  BPstat {sid}…")
        pts = fetch_bpstat_series(sid)
        if pts:
            out[str(sid)] = pts
            log.info(f"    → {len(pts)} pts, last: {pts[-1]}")
        else:
            log.warning(f"    → EMPTY")
        time.sleep(0.3)  # be polite
    return out

# ──────────────────────────────────────────────────────────
# ECB
# ──────────────────────────────────────────────────────────
ECB = "https://data-api.ecb.europa.eu/service/data"

def parse_ecb_jsondata(json_data: dict) -> list:
    """Parse ECB SDMX-JSON → [{date, value}]"""
    time_dim = next(
        d for d in json_data["structure"]["dimensions"]["observation"]
        if d["id"] == "TIME_PERIOD"
    )
    dates = [v["id"] for v in time_dim["values"]]
    obs   = list(json_data["dataSets"][0]["series"].values())[0]["observations"]
    return [
        {"date": dates[i], "value": v[0]}
        for i, v in ((int(k), v) for k, v in obs.items())
        if v
    ]

def parse_ecb_hicp_csv(text: str) -> list:
    lines = text.strip().split("\n")
    headers = lines[0].split(",")
    di = headers.index("TIME_PERIOD")
    vi = headers.index("OBS_VALUE")
    pts = []
    for line in lines[1:]:
        cols = line.split(",")
        try:
            pts.append({"date": cols[di], "value": float(cols[vi])})
        except (ValueError, IndexError):
            pass
    return sorted(pts, key=lambda p: p["date"])

def fetch_ecb() -> dict:
    out = {}

    # Bund 10Y monthly
    log.info("  ECB Bund 10Y…")
    try:
        r = get(f"{ECB}/IRS/M.DE.L.L40.CI.0.EUR.N.Z?format=jsondata&detail=dataonly&startPeriod=1990-01")
        out["bund"] = parse_ecb_jsondata(r.json())
        log.info(f"    → {len(out['bund'])} pts")
    except Exception as e:
        log.error(f"    Bund failed: {e}")

    # Euribor 3M / 6M / 12M
    for label, key in [
        ("euribor3m",  "M.U2.EUR.RT.MM.EURIBOR3MD_.HSTA"),
        ("euribor6m",  "M.U2.EUR.RT.MM.EURIBOR6MD_.HSTA"),
        ("euribor12m", "M.U2.EUR.RT.MM.EURIBOR1YD_.HSTA"),
    ]:
        log.info(f"  ECB {label}…")
        try:
            r = get(f"{ECB}/FM/{key}?format=jsondata&detail=dataonly&startPeriod=1999-01")
            out[label] = parse_ecb_jsondata(r.json())
            log.info(f"    → {len(out[label])} pts")
        except Exception as e:
            log.error(f"    {label} failed: {e}")
        time.sleep(0.3)

    # HICP Portugal (total, core, food) — last 120 months
    BASE   = "https://data-api.ecb.europa.eu/service/data/HICP/M.PT.N."
    SUFFIX = ".4D0.ANR?format=csvdata&lastNObservations=120"
    for label, code in [("hicp", "000000"), ("hicpCore", "XEF000"), ("hicpFood", "010000")]:
        log.info(f"  ECB HICP {label}…")
        try:
            r = get(BASE + code + SUFFIX)
            out[label] = parse_ecb_hicp_csv(r.text)
            log.info(f"    → {len(out[label])} pts")
        except Exception as e:
            log.error(f"    HICP {label} failed: {e}")
        time.sleep(0.3)

    return out

# ──────────────────────────────────────────────────────────
# EUROSTAT
# ──────────────────────────────────────────────────────────
ESTAT = "https://ec.europa.eu/eurostat/api/dissemination"

def parse_eurostat_ts(data: dict, geo: str) -> list:
    """Extract time-series for a single geo from Eurostat SDMX-JSON."""
    dims    = data.get("dimension", {})
    time_d  = dims.get("time", {}).get("category", {})
    geo_d   = dims.get("geo",  {}).get("category", {})
    times   = sorted(time_d.get("index", {}).items(), key=lambda x: x[1])
    geo_idx = geo_d.get("index", {}).get(geo, 0)
    n_time  = len(times)
    values  = data.get("value", {})
    pts = []
    for t, (label, ti) in enumerate(times):
        v = values.get(str(geo_idx * n_time + t))
        if v is not None:
            pts.append({"date": label, "value": v})
    return pts

def fetch_eurostat() -> dict:
    out = {}

    # Unemployment PT quarterly
    log.info("  Eurostat unemployment…")
    try:
        url = (f"{ESTAT}/sdmx/2.1/data/une_rt_q"
               "?geo=PT&age=Y15-74&sex=T&unit=PC_ACT&s_adj=NSA&format=JSON&startPeriod=2011-Q1")
        r = get(url)
        d = r.json()
        dims = d["dimension"]
        dim_order = ["freq","s_adj","age","unit","sex","geo","time"]
        sizes   = [len(dims[k]["category"]["index"]) for k in dim_order]
        strides = [1] * len(dim_order)
        for i in range(len(dim_order) - 2, -1, -1):
            strides[i] = strides[i+1] * sizes[i+1]
        def get_idx(k, v):
            return list(dims[k]["category"]["index"].keys()).index(v)
        fi = [0, get_idx("s_adj","NSA"), get_idx("age","Y15-74"), get_idx("unit","PC_ACT"),
              get_idx("sex","T"), get_idx("geo","PT"), 0]
        base = sum(fi[i] * strides[i] for i in range(len(fi)))
        time_keys = sorted(dims["time"]["category"]["index"].keys(),
                           key=lambda t: dims["time"]["category"]["index"][t])
        pts = [{"date": t, "value": d["value"].get(str(base + ti))}
               for ti, t in enumerate(time_keys)]
        out["unemp"] = [p for p in pts if p["value"] is not None]
        log.info(f"    → {len(out['unemp'])} pts")
    except Exception as e:
        log.error(f"    Unemployment failed: {e}")
    time.sleep(0.3)

    # GDP per capita EU27 (EUR, current prices)
    log.info("  Eurostat GDP EU27…")
    try:
        url = (f"{ESTAT}/sdmx/2.1/data/nama_10_pc"
               "?na_item=B1GQ&format=JSON&startPeriod=2000&lang=pt"
               "&geo=EU27_2020&unit=CP_EUR_HAB")
        r = get(url)
        data = r.json()
        times = sorted(data["dimension"]["time"]["category"]["index"].items(), key=lambda x: x[1])
        vals  = data.get("value", {})
        pts   = [{"date": t, "value": vals.get(str(i))} for i, (t, _) in enumerate(times)]
        out["pibEU"] = [p for p in pts if p["value"] is not None]
        log.info(f"    → {len(out['pibEU'])} pts")
    except Exception as e:
        log.error(f"    GDP EU27 failed: {e}")
    time.sleep(0.3)

    # Salaries earn_nt_net PT + EU27
    log.info("  Eurostat salaries…")
    try:
        url = (f"{ESTAT}/statistics/1.0/data/earn_nt_net"
               "?format=JSON&currency=EUR&estruct=GRS&ecase=P1_NCH_AW100"
               "&geo=PT&geo=EU27_2020")
        r = get(url)
        data = r.json()
        dims   = data.get("dimension", {})
        time_d = dims.get("time", {}).get("category", {})
        geo_d  = dims.get("geo",  {}).get("category", {})
        times  = sorted(time_d.get("index", {}).items(), key=lambda x: x[1])
        n_time = len(times)
        geo_keys = sorted(geo_d.get("index", {}).items(), key=lambda x: x[1])
        vals = data.get("value", {})
        geo_map = {g: i for g, i in geo_keys}
        def extract_geo(geo_code):
            idx = geo_map.get(geo_code, 0)
            return [{"date": t, "value": vals.get(str(idx * n_time + ti))}
                    for ti, (t, _) in enumerate(times)]
        pt = [p for p in extract_geo("PT") if p["value"] is not None]
        eu = [p for p in extract_geo("EU27_2020") if p["value"] is not None]
        out["salarios"] = {"pt": pt, "eu": eu}
        log.info(f"    → PT {len(pt)} pts, EU {len(eu)} pts")
    except Exception as e:
        log.error(f"    Salaries failed: {e}")

    return out

# ──────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────
def main():
    log.info("=== fetch_data.py starting ===")
    cache = {
        "updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "bpstat":   {},
        "eurostat": {},
        "ecb":      {},
    }

    log.info("--- BPstat ---")
    cache["bpstat"] = fetch_all_bpstat()

    log.info("--- ECB ---")
    cache["ecb"] = fetch_ecb()

    log.info("--- Eurostat ---")
    cache["eurostat"] = fetch_eurostat()

    out_path = "data/cache.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, separators=(",", ":"))

    size_kb = len(json.dumps(cache)) / 1024
    log.info(f"=== Done. {out_path} written ({size_kb:.0f} KB) ===")
    log.info(f"  BPstat series: {len(cache['bpstat'])}")
    log.info(f"  ECB keys:      {list(cache['ecb'].keys())}")
    log.info(f"  Eurostat keys: {list(cache['eurostat'].keys())}")

if __name__ == "__main__":
    main()
