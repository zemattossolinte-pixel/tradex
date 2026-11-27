#!/usr/bin/env python3
"""Tradex Ronda: ronda diária do mercado (fechamento da B3 + cripto).

A Ronda NÃO prevê o preço de amanhã — ninguém prevê. Ela faz o trabalho de
mesa de análise: olha o fechamento, separa empresas fundamentadamente
saudáveis em situações técnicas interessantes e devolve uma WATCHLIST
ranqueada de onde vale tirar o print diário e rodar no Tradex (aba Analisar).

Fluxo: Ronda aponta ONDE OLHAR → Tradex lê o gráfico e dá entrada/stop/alvo.

Fontes de dados (gratuitas):
  - B3 e índices: brapi.dev  (PETR4, VALE3, ITUB4 e MGLU3 funcionam sem token;
    para a lista completa crie um token gratuito em brapi.dev e coloque no .env:
    BRAPI_TOKEN=seu-token)
  - Cripto (BRL): API pública da OKX (sem chave)

Uso:  python ronda.py
      python ronda.py --token SEU_TOKEN
      python ronda.py --ativos "PETR4,VALE3,WEGE3" --cripto "BTC-BRL,XRP-BRL"
"""

import argparse
import json
import os
import urllib.error
import urllib.request
from datetime import datetime

import tradex

ATIVOS_PADRAO = ["PETR4", "VALE3", "ITUB4", "BBAS3", "B3SA3", "WEGE3", "ABEV3", "PRIO3"]
CRIPTO_PADRAO = ["BTC-BRL", "ETH-BRL", "XRP-BRL", "SOL-BRL"]
INDICES = ["IBOV", "USD-BRL"]

UA = {"User-Agent": "Mozilla/5.0 (Tradex)"}


def _get_json(url, cabecalhos_extra=None, timeout=20):
    cabecalhos = dict(UA)
    if cabecalhos_extra:
        cabecalhos.update(cabecalhos_extra)
    requisicao = urllib.request.Request(url, headers=cabecalhos)
    with urllib.request.urlopen(requisicao, timeout=timeout) as resposta:
        return json.loads(resposta.read().decode("utf-8"))


LOTE_MAXIMO = 5  # a brapi recusa lotes grandes (erro 400 QUOTES_PER_REQUEST_EXCEEDED)


def _erro_brapi(exc):
    try:
        corpo = json.loads(exc.read().decode("utf-8"))
        mensagem = corpo.get("message", "")
        codigo = corpo.get("code", "")
        return f"{mensagem} ({codigo})" if codigo else mensagem
    except Exception:
        return f"erro HTTP {exc.code}"


def _extrai_resultados(dados):
    resultado = {}
    for item in dados.get("results", []):
        conteudo = item.get("data") if isinstance(item.get("data"), dict) else item
        simbolo = (item.get("symbol") or conteudo.get("symbol") or "").upper()
        if simbolo:
            resultado[simbolo] = conteudo
    return resultado


def busca_brapi(tickers, token=None):
    """Busca cotações na brapi.dev (endpoint v2). Retorna (dict {ticker: dados}, avisos []).

    Envia o token no header Authorization (recomendação da brapi), divide em
    lotes de até 5 tickers e mostra a mensagem de erro original da API.
    """
    if not tickers:
        return {}, []
    token = (token or "").strip().strip('"').strip("'")
    cabecalhos = {"Authorization": f"Bearer {token}"} if token else {}
    avisos = []
    resultado = {}
    erros_400 = []

    for inicio in range(0, len(tickers), LOTE_MAXIMO):
        lote = tickers[inicio:inicio + LOTE_MAXIMO]
        url = "https://brapi.dev/api/v2/stocks/quote?symbols=" + ",".join(lote)
        try:
            dados = _get_json(url, cabecalhos)
            resultado.update(_extrai_resultados(dados))
            for erro in dados.get("errors") or []:
                avisos.append(f"brapi: {erro}")
        except urllib.error.HTTPError as exc:
            if exc.code == 401:
                avisos.append("brapi: token ausente ou inválido (401). Confira o BRAPI_TOKEN no .env "
                              "— copie a chave em https://brapi.dev/dashboard (sem aspas e sem espaços)")
            elif exc.code == 400:
                erros_400.append(_erro_brapi(exc))
            elif exc.code == 403:
                avisos.append(f"brapi: seu plano não inclui esses dados — {_erro_brapi(exc)}")
            elif exc.code == 429:
                avisos.append("brapi: limite de requisições atingido (429). Tente de novo em alguns minutos.")
            else:
                avisos.append(f"brapi: {_erro_brapi(exc)}")
        except urllib.error.URLError as exc:
            avisos.append(f"brapi: falha de conexão ({exc.reason})")

    if erros_400:
        avisos.append("brapi: chamada recusada (400) — " + "; ".join(dict.fromkeys(erros_400)))

    faltando = [t for t in tickers if t not in resultado]
    if faltando and not token:
        sem_token = []
        for ticker in faltando:
            try:
                dados = _get_json(f"https://brapi.dev/api/v2/stocks/quote?symbols={ticker}")
                resultado.update(_extrai_resultados(dados))
            except urllib.error.HTTPError as exc:
                if exc.code in (400, 401):
                    sem_token.append(ticker)
                elif exc.code == 429:
                    avisos.append("brapi: limite de requisições atingido (429). Tente de novo em alguns minutos.")
                    break
                else:
                    avisos.append(f"brapi: {_erro_brapi(exc)} em {ticker}")
            except urllib.error.URLError as exc:
                avisos.append(f"brapi: falha de conexão em {ticker} ({exc.reason})")
        if sem_token:
            avisos.append(
                "brapi: " + ", ".join(sem_token)
                + " exigem token. Crie um token gratuito em https://brapi.dev e coloque no .env: BRAPI_TOKEN=seu-token"
            )
    return resultado, avisos


def busca_estatisticas(tickers, token=None):
    """Busca P/L, dividend yield etc. em /api/v2/stocks/statistics.

    Opcional: se falhar (plano/limite), a Ronda segue sem leitura fundamentalista.
    """
    if not tickers:
        return {}
    token = (token or "").strip().strip('"').strip("'")
    cabecalhos = {"Authorization": f"Bearer {token}"} if token else {}
    resultado = {}
    for inicio in range(0, len(tickers), LOTE_MAXIMO):
        lote = tickers[inicio:inicio + LOTE_MAXIMO]
        url = "https://brapi.dev/api/v2/stocks/statistics?symbols=" + ",".join(lote)
        try:
            resultado.update(_extrai_resultados(_get_json(url, cabecalhos)))
        except Exception:
            continue
    return resultado


def busca_moeda(pares, token=None):
    """Busca câmbio (ex.: USD-BRL) em /api/v2/currency. Retorna (dict, avisos)."""
    if not pares:
        return {}, []
    token = (token or "").strip().strip('"').strip("'")
    cabecalhos = {"Authorization": f"Bearer {token}"} if token else {}
    url = "https://brapi.dev/api/v2/currency?currency=" + ",".join(pares)
    try:
        dados = _get_json(url, cabecalhos)
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            return {}, ["brapi: câmbio exige token válido (401). Confira o BRAPI_TOKEN no .env"]
        if exc.code == 403:
            return {}, ["brapi: seu plano não inclui câmbio (403) — " + _erro_brapi(exc)]
        return {}, [f"brapi: {_erro_brapi(exc)}"]
    except urllib.error.URLError as exc:
        return {}, [f"brapi: falha de conexão no câmbio ({exc.reason})"]
    resultado = {}
    for item in dados.get("currency", []):
        par = f"{item.get('fromCurrency', '')}-{item.get('toCurrency', '')}".upper()
        try:
            resultado[par] = {
                "preco": float(item.get("bidPrice")),
                "variacao": float(item.get("percentageChange")),
            }
        except (TypeError, ValueError):
            pass
    return resultado, []


def busca_okx(pares):
    """Busca cripto em BRL na API pública da OKX. Retorna (dict {par: dados}, erro ou None)."""
    resultado, erro = {}, None
    for par in pares:
        try:
            dados = _get_json(f"https://www.okx.com/api/v5/market/ticker?instId={par}")
            tick = dados["data"][0]
            ultimo, abertura = float(tick["last"]), float(tick["open24h"])
            resultado[par] = {
                "preco": ultimo,
                "variacao_dia": (ultimo / abertura - 1) * 100 if abertura else None,
                "max_24h": float(tick.get("high24h")) if tick.get("high24h") else None,
                "min_24h": float(tick.get("low24h")) if tick.get("low24h") else None,
                "volume_24h": float(tick.get("volCcy24h")) if tick.get("volCcy24h") else None,
            }
        except Exception as exc:
            erro = f"OKX: falha em {par} ({exc})"
    return resultado, erro


def _num(valor):
    try:
        return float(valor)
    except (TypeError, ValueError):
        return None


def classifica(ativo, dados):
    """Regras transparentes de leitura. Nada de 'IA mágica': cada critério é explicável."""
    preco = _num(dados.get("regularMarketPrice"))
    variacao = _num(dados.get("regularMarketChangePercent"))
    pl = _num(dados.get("priceEarnings") or dados.get("trailingPE"))
    dy = _num(dados.get("dividendYield"))
    min52 = _num(dados.get("fiftyTwoWeekLow"))
    max52 = _num(dados.get("fiftyTwoWeekHigh"))
    volume = _num(dados.get("regularMarketVolume"))

    etiquetas, pontos = [], 0.0
    if pl is not None:
        dy_txt = f", DY {dy * 100:.1f}%" if dy is not None and dy > 0 else ""
        if pl > 0:
            etiquetas.append(f"lucrativa (P/L {pl:.1f}{dy_txt})")
            pontos += 2
        else:
            etiquetas.append(f"no prejuízo (P/L {pl:.1f})")
            pontos -= 1

    if variacao is not None:
        if variacao <= -4:
            etiquetas.append(f"queda forte ({variacao:+.1f}% — pode ter notícia ruim atrás)")
        elif -4 < variacao < -1 and pl is not None and pl > 0:
            etiquetas.append(f"recuo do dia ({variacao:+.1f}%) em empresa lucrativa")
            pontos += 1
        elif variacao > 3:
            etiquetas.append(f"alta forte ({variacao:+.1f}%) — cuidado para não perseguir preço")
        else:
            etiquetas.append(f"dia lateral ({variacao:+.1f}%)")
            if pl is not None and pl > 0:
                pontos += 0.5

    if preco and min52 and max52 and max52 > min52:
        posicao = (preco - min52) / (max52 - min52) * 100
        if 5 <= posicao <= 30:
            etiquetas.append(f"perto do fundo de 52 semanas (faixa {min52:.2f}–{max52:.2f})")
            pontos += 1
        elif posicao >= 70:
            etiquetas.append("perto do topo de 52 semanas")

    return {"etiquetas": etiquetas, "pontos": pontos, "preco": preco,
            "variacao": variacao, "volume": volume}


def monta_ronda(ativos, cripto, indices, token=None):
    ativos = ativos or ATIVOS_PADRAO
    cripto = cripto or CRIPTO_PADRAO
    relatorio = {"gerado_em": datetime.now().strftime("%d/%m/%Y %H:%M"),
                 "contexto": [], "acoes": [], "cripto": [], "watchlist": [],
                 "avisos": []}

    if indices:
        indices_b3 = [i for i in indices if "-" not in i]
        moedas = [i for i in indices if "-" in i]
        if indices_b3:
            dados_indices, avisos_indices = busca_brapi(indices_b3, token)
            relatorio["avisos"].extend(avisos_indices)
            for nome, dados in dados_indices.items():
                relatorio["contexto"].append({
                    "nome": nome,
                    "preco": _num(dados.get("regularMarketPrice")),
                    "variacao": _num(dados.get("regularMarketChangePercent")),
                })
        if moedas:
            dados_moedas, avisos_moedas = busca_moeda(moedas, token)
            relatorio["avisos"].extend(avisos_moedas)
            for par, dados in dados_moedas.items():
                relatorio["contexto"].append({
                    "nome": par,
                    "preco": dados.get("preco"),
                    "variacao": dados.get("variacao"),
                })

    dados_acoes, avisos_acoes = busca_brapi(ativos, token)
    relatorio["avisos"].extend(avisos_acoes)
    obtidas = [t for t in ativos if t in dados_acoes]
    for ticker, stats in busca_estatisticas(obtidas, token).items():
        if ticker in dados_acoes:
            dados_acoes[ticker].update({k: v for k, v in stats.items() if v is not None})
    analisados = []
    for ticker in ativos:
        dados = dados_acoes.get(ticker)
        if not dados:
            if not any(ticker in aviso for aviso in relatorio["avisos"]):
                relatorio["avisos"].append(f"{ticker}: sem dados (confira o ticker ou o token da brapi)")
            continue
        leitura = classifica(ticker, dados)
        item = {"ticker": ticker,
                "nome": dados.get("longName") or dados.get("shortName") or ticker,
                "preco": leitura["preco"],
                "variacao_dia": leitura["variacao"],
                "etiquetas": leitura["etiquetas"],
                "pontos": leitura["pontos"]}
        analisados.append(item)
        relatorio["acoes"].append(item)

    dados_cripto, erro = busca_okx(cripto)
    if erro:
        relatorio["avisos"].append(erro)
    for par, dados in dados_cripto.items():
        item = {"ticker": par, "preco": dados["preco"],
                "variacao_dia": dados["variacao_dia"],
                "etiquetas": [f"24h {dados['variacao_dia']:+.1f}%" if dados["variacao_dia"] is not None else "sem variação",
                              "sem leitura fundamentalista — decidir só pelo gráfico no Tradex"]}
        relatorio["cripto"].append(item)

    watchlist = sorted([a for a in relatorio["acoes"] if a["etiquetas"]],
                       key=lambda a: a["pontos"], reverse=True)
    relatorio["watchlist"] = [
        {**a, "motivo": "; ".join(a["etiquetas"])}
        for a in watchlist[:5] if a["etiquetas"]
    ]
    return relatorio


def imprime(relatorio):
    print(f"\n=== TRANDEX RONDA · {relatorio['gerado_em']} ===")
    for aviso in relatorio["avisos"]:
        print(f"*** AVISO: {aviso} ***")

    print("\n-- Contexto do dia --")
    for ctx in relatorio["contexto"]:
        variacao = f"{ctx['variacao']:+.2f}%" if ctx["variacao"] is not None else "—"
        preco = f"{ctx['preco']:,.2f}" if ctx["preco"] is not None else "—"
        print(f"  {ctx['nome']:<8} {preco:>14}  {variacao}")
    if not relatorio["contexto"]:
        print("  (índices exigem token brapi — veja os avisos acima)")

    print("\n-- Ações --")
    for acao in relatorio["acoes"]:
        variacao = f"{acao['variacao_dia']:+.2f}%" if acao["variacao_dia"] is not None else "—"
        preco = f"{acao['preco']:.2f}" if acao["preco"] is not None else "—"
        print(f"  {acao['ticker']:<7} {preco:>10}  {variacao:>8}  {' · '.join(acao['etiquetas'])}")

    print("\n-- Cripto (OKX) --")
    for c in relatorio["cripto"]:
        preco = f"{c['preco']:,.2f}" if c["preco"] is not None else "—"
        print(f"  {c['ticker']:<10} {preco:>12}  {' · '.join(c['etiquetas'])}")

    print("\n-- WATCHLIST de hoje (onde vale tirar o print diário) --")
    for i, a in enumerate(relatorio["watchlist"], 1):
        print(f"  {i}. {a['ticker']:<7} {a['motivo']}")
    print("\nA Ronda aponta ONDE OLHAR — não é recomendação de compra.")
    print("Próximo passo: print do gráfico DIÁRIO de cada candidato → Tradex → COMPRA/VENDA/AGUARDAR.")
    print()


def salva_json(relatorio, caminho):
    with open(caminho, "w", encoding="utf-8") as arquivo:
        json.dump(relatorio, arquivo, ensure_ascii=False, indent=2)


def main():
    parser = argparse.ArgumentParser(description="Tradex Ronda (ronda diária do mercado)")
    parser.add_argument("--ativos", help='ações da B3 separadas por vírgula (ex.: "PETR4,VALE3")')
    parser.add_argument("--cripto", help='pares cripto separados por vírgula (ex.: "BTC-BRL,XRP-BRL")')
    parser.add_argument("--token", help="token da brapi.dev (ou coloque BRAPI_TOKEN no .env)")
    parser.add_argument("--sem-indices", action="store_true", help="não buscar IBOV/dólar")
    parser.add_argument("--sem-json", action="store_true", help="não salvar ronda_hoje.json")
    args = parser.parse_args()

    tradex.carrega_env(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
    token = args.token or os.environ.get("BRAPI_TOKEN")

    ativos = [a.strip().upper() for a in args.ativos.split(",")] if args.ativos else None
    cripto = [c.strip().upper() for c in args.cripto.split(",")] if args.cripto else None
    indices = None if args.sem_indices else INDICES

    relatorio = monta_ronda(ativos, cripto, indices, token)
    imprime(relatorio)
    if not args.sem_json:
        caminho = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ronda_hoje.json")
        salva_json(relatorio, caminho)
        print(f"Relatório salvo em: {caminho}")
    return relatorio


if __name__ == "__main__":
    main()
