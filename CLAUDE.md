# DashboardPortugal — Notas para Claude

## Regra obrigatória: séries novas → fetch_data.py

**Sempre que adicionar um gráfico novo com dados do BPstat:**
1. Identificar os IDs das séries usadas (ex: `88896`)
2. Adicionar ao array `BPSTAT_SERIES` em `scripts/fetch_data.py`
3. Fazer commit de ambos os ficheiros (`index.html` + `fetch_data.py`) juntos

Se não fizer o passo 2, o gráfico funciona mas todos os utilizadores fazem chamadas diretas à API do BPstat em vez de usar a cache — mais lento e mais carga.

Para séries ECB/Eurostat: atualizar as funções `fetch_ecb()` / `fetch_eurostat()` no mesmo ficheiro.

## Séries BPstat atualmente em cache (scripts/fetch_data.py)

| ID | Descrição |
|---|---|
| 12518356 | PIB anual preços correntes M€ |
| 12518283 | PIB trimestral vcsc M€ |
| 12512877 | Endividamento Particulares |
| 12710744 | Prestação Habitação mediana |
| 12457924 | Balança Corrente |
| 12645509 | Saldo Orçamental AP % PIB |
| 88895 | Saldo Seg. Social |
| 88896 | Receitas contribuições SS |
| 88885 | Despesas totais SS |
| 88873 | Receita Estado |
| 88884 | Despesa Estado |
| 12560943 | Saldo mensal acumulado YTD |
| 12645918 | Petróleo Brent EUR/bbl |
| 12099459 | OT 10Y daily (spread) |
| 12561507 | Dívida AP % PIB (Eurostat/EDP) |
| 12414395–12456320 | Capacidade/Necessidade Financiamento por setor |
| 12560971–12560967 | Receitas/Despesas AP por categoria |
| 12561508–12561512 | Confiança |

## Arquitetura geral

- Site estático GitHub Pages + Cloudflare CDN
- Cache: `data/cache.json` gerado diariamente pelo GitHub Actions (07:00 UTC)
- Frontend: `getSeriesData(id)` → tenta cache primeiro, fallback direto à API
- AdSense: slots ocultos (`display:none`) até aprovação — uncommentar show-code em `loadAds()` nos 3 ficheiros (`index.html`, `euribor.html`, `inflacao-hicp.html`)
- CORS: site não funciona via `file://` — usar `python -m http.server 8000` para teste local
- git lock: se `git commit` falhar com "lock file exists", apagar `DashboardPortugal\.git\index.lock` manualmente
