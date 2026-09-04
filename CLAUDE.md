# DashboardPortugal — Notas para Claude

## Regra obrigatória: séries novas → fetch_data.py

**Sempre que adicionar um gráfico novo com dados do BPstat:**
1. Identificar os IDs das séries usadas (ex: `12560943`)
2. Adicionar ao array `BPSTAT_SERIES` em `scripts/fetch_data.py`
3. Fazer commit de ambos os ficheiros (`index.html` + `fetch_data.py`) juntos

Se não fizer o passo 2, o gráfico funciona mas todos os utilizadores fazem chamadas diretas à API do BPstat em vez de usar a cache — mais lento e mais carga.

Para séries ECB/Eurostat: atualizar  as funções `fetch_ecb()` / `fetch_eurostat()` no mesmo ficheiro.

## Séries BPstat atualmente em cache (scripts/fetch_data.py)

| ID | Descrição |
|---|---|
| 12518356 | PIB anual preços correntes M€ |
| 12518283 | PIB trimestral vcsc M€ |
| 12512877 | Endividamento Particulares |
| 12710744 | Prestação Habitação mediana |
| 12457924 | Balança Corrente |
| 12645509 | Saldo AP anual M€ (Contas Nacionais) |
| 12645516 | Despesas de capital AP anual (investimento público) |
| 12645530 | Despesas totais AP anual |
| 12645533 | Receitas de capital AP anual |
| 12706759 | Deflator PIB — taxa variação anual (INE) |
| 12704650 | Taxa inflação IPC total anual (INE) |
| 88873 | Receita Estado |
| 88884 | Despesa Estado |
| 12560943 | Saldo mensal acumulado YTD |
| 12645918 | Petróleo Brent EUR/bbl |
| 12099459 | OT 10Y daily (spread) |
| 12561507 | Dívida AP % PIB (Eurostat/EDP) |
| 12414395–12456320 | Capacidade/Necessidade Financiamento por setor |
| 12560947 | Receitas totais AP (execução orçamental) |
| 12560951 | Receitas correntes AP |
| 12560959 | Despesas totais AP |
| 12560963 | Despesas correntes AP |
| 12560971–12560983 | Receitas AP por categoria (impostos diretos, indiretos, contribuições, outras) |
| 12560967, 12560987–12560992 | Despesas AP por categoria (capital, pessoal, transferências, etc.) |
| 88875 | Receitas correntes Estado |
| 88877 | Receitas IVA Estado |
| 88886 | Despesas correntes Estado |
| 88894 | Saldo Estado |
| 88898 | Impostos diretos Estado |
| 88899 | IRS Estado |
| 88900 | IRC Estado |
| 88901 | Impostos indiretos Estado |
| 88910 | Juros e encargos Estado |
| 12561508–12561512 | Confiança |

## Chaves Eurostat em cache (eurostat.*)

| Chave | Dataset | Descrição |
|---|---|---|
| `eurostat.unemp` | une_rt_q | Taxa desemprego PT trimestral |
| `eurostat.pibEU` | nama_10_pc | PIB per capita EU27 anual |
| `eurostat.salarios` | earn_nt_net | Salários PT + EU27 |
| `eurostat.ss.tr` | gov_10a_main / S1314 | SS Receitas totais anuais M€ |
| `eurostat.ss.te` | gov_10a_main / S1314 | SS Despesas totais anuais M€ |
| `eurostat.ss.b9` | gov_10a_main / S1314 | SS Saldo (net lending) anuais M€ |

*Nota: séries BPstat 88895/88896/88881/88885 (SS mensais) foram removidas do BPstat → substituídas por Eurostat gov_10a_main S.1314.*

## Arquitetura geral

- Site estático GitHub Pages + Cloudflare CDN
- Cache: `data/cache.json` gerado diariamente pelo GitHub Actions (07:00 UTC)
- Frontend: `getSeriesData(id)` → tenta cache primeiro, fallback direto à API
- AdSense: slots ocultos (`display:none`) até aprovação — uncommentar show-code em `loadAds()` nos 3 ficheiros (`index.html`, `euribor.html`, `inflacao-hicp.html`)
- CORS: site não funciona via `file://` — usar `python -m http.server 8000` para teste local
- git lock: se `git commit` falhar com "lock file exists", apagar `DashboardPortugal\.git\index.lock` manualmente
