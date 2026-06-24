#!/usr/bin/env python3
"""
update_ren.py — Actualiza os dados REN DataHub no index.html

Endpoints usados (servicebus.ren.pt/datahubapi/electricity/):
  • ElectricityConsumptionVariationYearly  → REN_CONSUMO_DATA
  • ElectricityMarketPricesMonthly         → REN_PRECO_DATA + REN_PRECO_HIST_DATA
  • ElectricityConsumptionSupplyMonthly    → REN_BALANCO_HIST_DATA + REN_RENOVAVEIS_LAST_DATA

Executar: python update_ren.py
"""

import json
import re
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

# ── Configuração ────────────────────────────────────────────────────────────────

BASE_URL  = "https://servicebus.ren.pt/datahubapi/electricity"
HTML_FILE = Path(__file__).parent / "index.html"
HEADERS   = {
    "Accept":     "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0",
}

MONTH_TO_NUM = {
    "January":"01","February":"02","March":"03","April":"04",
    "May":"05","June":"06","July":"07","August":"08",
    "September":"09","October":"10","November":"11","December":"12",
}

# ── Utilitários ─────────────────────────────────────────────────────────────────

def fetch_json(endpoint: str) -> object:
    year = datetime.now().year
    url  = f"{BASE_URL}/{endpoint}?culture=en-US&year={year}"
    req  = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode("utf-8"))


def extract_const(html: str, name: str) -> object:
    """Extrai o valor JSON de uma constante JS no HTML."""
    m = re.search(rf"const {name} = (.*?);", html, re.DOTALL)
    if not m:
        raise ValueError(f"Constante '{name}' não encontrada no HTML")
    return json.loads(m.group(1))


def replace_const(html: str, name: str, value: object) -> str:
    """Substitui o valor de uma constante JS no HTML."""
    json_str = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return re.sub(
        rf"(const {name} = ).*?;",
        lambda m: f"{m.group(1)}{json_str};",
        html,
        count=1,
        flags=re.DOTALL,
    )


def month_name_to_date(month_name: str) -> str:
    """Converte nome do mês (inglês) para YYYY-MM inferindo o ano."""
    num = MONTH_TO_NUM[month_name]
    now = datetime.now()
    # Se o mês da API é posterior ao mês actual → é do ano anterior
    year = now.year if int(num) <= now.month else now.year - 1
    return f"{year}-{num}"


# ── Lógica principal ─────────────────────────────────────────────────────────────

def main():
    if not HTML_FILE.exists():
        print(f"❌ Ficheiro não encontrado: {HTML_FILE}")
        sys.exit(1)

    print(f"📖 A ler {HTML_FILE.name} …")
    html = HTML_FILE.read_text(encoding="utf-8")

    # ── 1. Buscar dados da API ──────────────────────────────────────────────────

    print("\n🌐 A ligar à API REN DataHub …")

    consumo_api, preco_api, supply_api = None, None, None

    try:
        consumo_api = fetch_json("ElectricityConsumptionVariationYearly")
        print(f"  ✅ ElectricityConsumptionVariationYearly — {len(consumo_api)} meses")
    except Exception as e:
        print(f"  ❌ ElectricityConsumptionVariationYearly — {e}")

    try:
        preco_api = fetch_json("ElectricityMarketPricesMonthly")
        month_key = list(preco_api.keys())[0]
        print(f"  ✅ ElectricityMarketPricesMonthly — {month_key}")
    except Exception as e:
        print(f"  ❌ ElectricityMarketPricesMonthly — {e}")

    try:
        supply_api = fetch_json("ElectricityConsumptionSupplyMonthly")
        print(f"  ✅ ElectricityConsumptionSupplyMonthly — {len(supply_api)} tipos")
    except Exception as e:
        print(f"  ❌ ElectricityConsumptionSupplyMonthly — {e}")

    if not any([consumo_api, preco_api, supply_api]):
        print("\n❌ Nenhum dado obtido da API. A abortar.")
        sys.exit(1)

    # Determinar a data do mês mais recente
    if preco_api:
        month_key  = list(preco_api.keys())[0]
        api_date   = month_name_to_date(month_key)
        print(f"\n📅 Mês detectado pela API: {api_date} ({month_key})")
    elif supply_api:
        # Fallback: inferir a partir do consumo cruzando com os dados anuais
        supply_map  = {d["type"]: d["monthly_Accumulation"] for d in supply_api}
        consumption = supply_map.get("CONSUMPTION")
        if consumo_api and consumption:
            match = next((m for m in consumo_api if m.get("consumption") == consumption), None)
            if match:
                month_key = match["type"]
                api_date  = month_name_to_date(month_key)
                print(f"\n📅 Mês inferido por consumo: {api_date} ({month_key})")
            else:
                print("\n⚠️  Não foi possível determinar o mês. A abortar.")
                sys.exit(1)
        else:
            print("\n⚠️  Não foi possível determinar o mês. A abortar.")
            sys.exit(1)
    else:
        print("\n⚠️  Não foi possível determinar o mês. A abortar.")
        sys.exit(1)

    updated = []

    # ── 2. REN_CONSUMO_DATA ─────────────────────────────────────────────────────
    if consumo_api:
        html = replace_const(html, "REN_CONSUMO_DATA", consumo_api)
        non_null = sum(1 for m in consumo_api if m.get("yearEvol") is not None)
        updated.append(f"REN_CONSUMO_DATA ({non_null} meses com dados)")

    # ── 3. REN_PRECO_DATA e REN_PRECO_HIST_DATA ─────────────────────────────────
    if preco_api:
        # Verificar se a data da API é mais recente do que o último registo histórico
        preco_hist = extract_const(html, "REN_PRECO_HIST_DATA")
        last_hist_date = preco_hist[-1]["date"] if preco_hist else "0000-00"

        if api_date > last_hist_date:
            # Adicionar ao histórico
            avg_price = preco_api[month_key]["PT"]["Average Price"]
            preco_hist.append({"date": api_date, "value": avg_price})
            preco_hist.sort(key=lambda x: x["date"])
            html = replace_const(html, "REN_PRECO_HIST_DATA", preco_hist)
            updated.append(f"REN_PRECO_HIST_DATA (+ {api_date} = {avg_price} €/MWh)")

            # Actualizar REN_PRECO_DATA com o mês mais recente
            html = replace_const(html, "REN_PRECO_DATA", preco_api)
            updated.append(f"REN_PRECO_DATA → {month_key}")
        elif api_date == last_hist_date:
            # Actualizar o valor existente (pode ter mudado) e REN_PRECO_DATA
            avg_price = preco_api[month_key]["PT"]["Average Price"]
            old_val = preco_hist[-1]["value"]
            if old_val != avg_price:
                preco_hist[-1]["value"] = avg_price
                html = replace_const(html, "REN_PRECO_HIST_DATA", preco_hist)
                updated.append(f"REN_PRECO_HIST_DATA (actualizado {api_date}: {old_val}→{avg_price})")
            html = replace_const(html, "REN_PRECO_DATA", preco_api)
            updated.append(f"REN_PRECO_DATA → {month_key}")
        else:
            print(f"  ℹ️  Preço: API ({api_date}) ≤ histórico ({last_hist_date}) — sem alteração")

    # ── 4. REN_BALANCO_HIST_DATA e REN_RENOVAVEIS_LAST_DATA ─────────────────────
    if supply_api:
        s = {d["type"]: d["monthly_Accumulation"] for d in supply_api}

        total_gen  = s.get("TOTAL_GENERATION")
        renewable  = s.get("RENEWABLE_GENERATION")
        import_bal = s.get("IMPORT_BALANCE")
        consumption= s.get("CONSUMPTION")
        hydro      = s.get("HYDRO", 0)
        wind       = s.get("WIND", 0)
        solar      = s.get("SOLAR", 0)
        biomass    = s.get("BIOMASS", 0)

        # ── REN_BALANCO_HIST_DATA
        balanco_hist    = extract_const(html, "REN_BALANCO_HIST_DATA")
        last_bal_date   = balanco_hist[-1]["date"] if balanco_hist else "0000-00"
        existing_dates  = {b["date"] for b in balanco_hist}

        if api_date > last_bal_date and api_date not in existing_dates:
            if total_gen is not None and consumption is not None:
                balanco_hist.append({
                    "date":        api_date,
                    "total_gen":   int(total_gen),
                    "renewable":   int(renewable or 0),
                    "import_bal":  int(import_bal or 0),
                    "consumption": int(consumption),
                })
                balanco_hist.sort(key=lambda x: x["date"])
                html = replace_const(html, "REN_BALANCO_HIST_DATA", balanco_hist)
                updated.append(f"REN_BALANCO_HIST_DATA (+ {api_date})")
        elif api_date == last_bal_date:
            # Actualizar registo existente se os valores mudaram
            entry = next((b for b in balanco_hist if b["date"] == api_date), None)
            if entry and total_gen is not None:
                new_entry = {
                    "date": api_date, "total_gen": int(total_gen),
                    "renewable": int(renewable or 0), "import_bal": int(import_bal or 0),
                    "consumption": int(consumption),
                }
                if entry != new_entry:
                    balanco_hist[balanco_hist.index(entry)] = new_entry
                    html = replace_const(html, "REN_BALANCO_HIST_DATA", balanco_hist)
                    updated.append(f"REN_BALANCO_HIST_DATA (actualizado {api_date})")
        else:
            print(f"  ℹ️  Balanço: API ({api_date}) ≤ histórico ({last_bal_date}) — sem alteração")

        # ── REN_RENOVAVEIS_LAST_DATA
        reno_current = extract_const(html, "REN_RENOVAVEIS_LAST_DATA")
        reno_new     = {"date": api_date, "hydro": hydro, "wind": wind,
                        "solar": solar, "biomass": biomass}
        if reno_new != reno_current:
            html = replace_const(html, "REN_RENOVAVEIS_LAST_DATA", reno_new)
            updated.append(f"REN_RENOVAVEIS_LAST_DATA → {api_date} "
                           f"(hídrica={hydro} eólica={wind} solar={solar} biomassa={biomass})")

    # ── 5. Guardar ──────────────────────────────────────────────────────────────
    if updated:
        HTML_FILE.write_text(html, encoding="utf-8")
        print(f"\n✅ index.html guardado. Alterações:")
        for u in updated:
            print(f"   • {u}")
    else:
        print("\n✅ Já actualizado — nenhuma alteração necessária.")


if __name__ == "__main__":
    main()
