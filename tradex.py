#!/usr/bin/env python3
"""Tradex: copiloto de trade por imagem.

Envia um print do gráfico para a API do Mistral (via HTTP, sem dependências) e recebe um
plano de trade estruturado (entrada, stop loss, alvos) com cálculo local
de risco/retorno, tamanho de posição, checklist de disciplina e diário
de trades.
"""

import argparse
import base64
import csv
import datetime
import json
import mimetypes
import os
import sys
import urllib.error
import urllib.request

PROMPT = """Você é um trader profissional sênior, com domínio completo de:
- Análise técnica: estrutura de topos/fundos, tendência, suportes e resistências, padrões gráficos e de candles, zonas de liquidez, indicadores (médias móveis, RSI, volume, momentum) e leitura de ação do preço.
- Análise fundamentalista e macroeconômica: fundamentos típicos do ativo identificado (resultados, juros, câmbio, setor), usados apenas como CONTEXTO — seus dados podem estar desatualizados e nunca substituem a leitura do gráfico.
- Gestão de risco: stop atrás de estrutura, risco por trade de no máximo 1-2% do capital, relação risco/retorno mínima de 2:1, realização parcial e ajuste de stop para o breakeven.
- Psicologia e disciplina: só sugerir entrada quando o checklist técnico confirma; paciência e "não operar" são decisões de trader também. Nunca force um cenário.
- Planejamento: sempre entregar plano A (cenário principal), plano B (cenário alternativo) e critérios objetivos de invalidação.

Analise o gráfico enviado considerando o ativo, o timeframe e a escala de preços visíveis na imagem.

Responda a análise em português e ESTRITAMENTE em JSON, com este formato:
{
  "ativo": "nome do ativo lido da imagem ou 'desconhecido'",
  "timeframe": "timeframe visível ou 'desconhecido'",
  "direcao": "compra" | "venda" | "aguardar",
  "contexto": {
    "tendencia": "resumo da tendência (alta/baixa/lateral) e da estrutura",
    "suportes": [preços legíveis na tela],
    "resistencias": [preços legíveis na tela],
    "padroes": ["padrões gráficos e de candles identificados"],
    "indicadores": "o que médias móveis, RSI, volume etc. sugerem",
    "fundamento_macro": "fatores fundamentalistas/macroeconômicos típicos deste ativo que podem influenciar (com aviso de que os dados podem estar desatualizados)"
  },
  "checklist": [
    {"criterio": "critério objetivo de confirmação", "confirmado": true}
  ],
  "entrada": null,
  "stop_loss": null,
  "alvo1": null,
  "alvo2": null,
  "gestao_da_operacao": {
    "parcial": "quando realizar parcial (ex: 50% no alvo1)",
    "ajuste_stop": "quando mover o stop para o breakeven ou trailing",
    "risco_maximo_percentual": 1
  },
  "justificativa": "por que esse gatilho, stop e alvos, citando a estrutura do gráfico",
  "cenario_alternativo": "plano B: o que fazer se o preço agir diferente",
  "invalidacao": "o que anula o cenário e indica sair",
  "confianca": "baixa" | "média" | "alta"
}

Regras obrigatórias:
- O checklist deve ter de 5 a 7 critérios objetivos (ex: tendência alinhada, preço em região relevante, padrão confirmado, volume, R:R >= 2) marcados true/false. Se a maioria NÃO estiver confirmada, use "direcao": "aguardar" e explique o que estaria faltando.
- Use SOMENTE preços que você consegue ler claramente na imagem. Nunca invente números.
- Alvos devem respeitar relação risco/retorno mínima de 2:1 em relação ao stop.
- Stop deve ficar atrás de uma estrutura (topo/fundo/pavio), não em distância arbitrária.
- Se a imagem estiver ilegível, sem preços claros ou o cenário for fraco, use "direcao": "aguardar" e explique o motivo em "justificativa".

Retorne APENAS o JSON, sem texto antes ou depois."""


def lista_modelos(api_key):
    req = urllib.request.Request(
        "https://api.mistral.ai/v1/models",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8")).get("data", [])
    except Exception:
        return []


def escolhe_modelo(api_key):
    """Escolhe o melhor modelo com capacidade de visão disponível hoje."""
    visao = []
    for modelo in lista_modelos(api_key):
        mid = modelo.get("id", "")
        caps = modelo.get("capabilities") or {}
        if not caps.get("vision"):
            continue
        if any(x in mid for x in ("voxtral", "ocr", "embed", "shieldstral", "moderation")):
            continue
        visao.append(mid)
    for preferencia in ("large", "medium", "small", "ministral"):
        for mid in visao:
            if preferencia in mid:
                return mid
    return visao[0] if visao else None


def carrega_env(path):
    """Lê um arquivo .env simples (CHAVE=valor) e define variáveis não definidas."""
    if not os.path.isfile(path):
        return
    try:
        with open(path, encoding="utf-8-sig") as fh:
            texto = fh.read()
    except UnicodeDecodeError:
        with open(path, encoding="utf-16") as fh:
            texto = fh.read()
    for line in texto.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        chave, valor = line.split("=", 1)
        os.environ.setdefault(chave.strip(), valor.strip().strip('"').strip("'"))


def encode_image(path):
    mime, _ = mimetypes.guess_type(path)
    if mime not in ("image/png", "image/jpeg", "image/webp", "image/gif"):
        sys.exit(f"Formato de imagem não suportado: {path} (use PNG, JPEG, WEBP ou GIF)")
    with open(path, "rb") as fh:
        return mime, base64.b64encode(fh.read()).decode("utf-8")


def chama_api(body, api_key):
    req = urllib.request.Request(
        "https://api.mistral.ai/v1/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detalhe = exc.read().decode("utf-8", "replace")
        if exc.code == 401:
            sys.exit("Chave recusada pela API (erro 401). Confira a MISTRAL_API_KEY no arquivo .env.")
        if exc.code == 429:
            sys.exit("Limite de uso atingido (erro 429). Aguarde alguns minutos e tente de novo.")
        if exc.code == 400 and body.get("response_format"):
            return None
        sys.exit(f"Erro HTTP {exc.code} na API do Mistral:\n{detalhe}")
    except urllib.error.URLError as exc:
        sys.exit(f"Erro de conexão com api.mistral.ai: {exc}")


def analyze(path, model, api_key):
    mime, b64 = encode_image(path)
    body = {
        "model": model,
        "temperature": 0.2,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": PROMPT},
                {"type": "image_url", "image_url": f"data:{mime};base64,{b64}"},
            ],
        }],
        "response_format": {"type": "json_object"},
    }
    resposta = chama_api(body, api_key)
    if resposta is None:
        body.pop("response_format", None)
        resposta = chama_api(body, api_key)
    try:
        conteudo = resposta["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        sys.exit(f"Resposta inesperada da API:\n{resposta}")
    return extract_json(conteudo)


def extract_json(raw):
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
    text = text.strip().strip("`")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        sys.exit(f"O modelo não devolveu um JSON válido: {exc}\nResposta bruta:\n{raw}")


def calcula_gestao_risco(plano, capital, risco_pct, multiplicador=1.0):
    direcao = plano.get("direcao")
    entrada = plano.get("entrada")
    stop = plano.get("stop_loss")
    if direcao not in ("compra", "venda"):
        return None
    if not all(isinstance(v, (int, float)) for v in (entrada, stop)):
        return None
    distancia = abs(entrada - stop)
    if distancia <= 0:
        return None

    def rr(alvo):
        return round(abs(alvo - entrada) / distancia, 2) if isinstance(alvo, (int, float)) else None

    risco_financeiro = capital * risco_pct / 100
    quantidade = risco_financeiro / (distancia * multiplicador)
    return {
        "risco_financeiro": round(risco_financeiro, 2),
        "distancia_entrada_stop": round(distancia, 6),
        "tamanho_posicao": round(quantidade, 6),
        "r_alvo1": rr(plano.get("alvo1")),
        "r_alvo2": rr(plano.get("alvo2")),
    }


def registra_diario(plano, gestao, caminho_csv, imagem):
    campos = [
        "data_hora", "arquivo", "ativo", "timeframe", "direcao",
        "entrada", "stop_loss", "alvo1", "alvo2",
        "risco_financeiro", "tamanho_posicao", "r_alvo1", "r_alvo2",
        "confianca",
    ]
    linha = {
        "data_hora": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "arquivo": os.path.basename(imagem),
        "ativo": plano.get("ativo"),
        "timeframe": plano.get("timeframe"),
        "direcao": plano.get("direcao"),
        "entrada": plano.get("entrada"),
        "stop_loss": plano.get("stop_loss"),
        "alvo1": plano.get("alvo1"),
        "alvo2": plano.get("alvo2"),
        "risco_financeiro": gestao["risco_financeiro"] if gestao else None,
        "tamanho_posicao": gestao["tamanho_posicao"] if gestao else None,
        "r_alvo1": gestao["r_alvo1"] if gestao else None,
        "r_alvo2": gestao["r_alvo2"] if gestao else None,
        "confianca": plano.get("confianca"),
    }
    novo = not os.path.isfile(caminho_csv)
    with open(caminho_csv, "a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=campos)
        if novo:
            writer.writeheader()
        writer.writerow(linha)


def imprime(plano, capital, risco_pct, multiplicador):
    print("=" * 60)
    print(f"Ativo:      {plano.get('ativo', 'desconhecido')}")
    print(f"Timeframe:  {plano.get('timeframe', 'desconhecido')}")
    print(f"Decisão:    {plano.get('direcao', 'aguardar').upper()}")
    print("=" * 60)

    contexto = plano.get("contexto") or {}
    if contexto:
        print("\n--- Contexto ---")
        print(f"Tendência:    {contexto.get('tendencia', '-')}")
        print(f"Suportes:     {contexto.get('suportes', '-')}")
        print(f"Resistências: {contexto.get('resistencias', '-')}")
        print(f"Padrões:      {contexto.get('padroes', '-')}")
        print(f"Indicadores:  {contexto.get('indicadores', '-')}")
        print(f"Macro:        {contexto.get('fundamento_macro', '-')}")

    checklist = plano.get("checklist") or []
    if checklist:
        print("\n--- Checklist de disciplina ---")
        marcador = {True: "[x]", False: "[ ]", None: "[?]"}
        for item in checklist:
            estado = marcador.get(item.get("confirmado"), "[?]")
            print(f" {estado} {item.get('criterio', '-')}")
        confirmados = sum(1 for item in checklist if item.get("confirmado") is True)
        print(f"Critérios confirmados: {confirmados}/{len(checklist)}")

    if plano.get("direcao") in ("compra", "venda") and plano.get("entrada") is not None:
        print("\n--- Plano operacional ---")
        print(f"Entrada:     {plano.get('entrada')}")
        print(f"Stop loss:   {plano.get('stop_loss')}")
        print(f"Alvo 1:      {plano.get('alvo1')}")
        print(f"Alvo 2:      {plano.get('alvo2')}")
    else:
        print("\nSem operação sugerida: aguarde. Paciência também é uma decisão de trader.")

    gestao_operacao = plano.get("gestao_da_operacao") or {}
    if gestao_operacao:
        print("\n--- Gestão da operação ---")
        print(f"Parcial:      {gestao_operacao.get('parcial', '-')}")
        print(f"Ajuste stop:  {gestao_operacao.get('ajuste_stop', '-')}")
        print(f"Risco máx.:   {gestao_operacao.get('risco_maximo_percentual', '-')}%")

    print(f"\nJustificativa:       {plano.get('justificativa', '-')}")
    print(f"Cenário alternativo: {plano.get('cenario_alternativo', '-')}")
    print(f"Invalidação:         {plano.get('invalidacao', '-')}")
    confianca = str(plano.get("confianca", "-")).lower()
    print(f"Confiança:           {confianca}")

    gestao = calcula_gestao_risco(plano, capital, risco_pct, multiplicador)
    if gestao:
        print("\n--- Gestão de risco (calculado localmente) ---")
        print(f"Risco por trade ({risco_pct}% de {capital}): {gestao['risco_financeiro']}")
        print(f"Distância entrada->stop: {gestao['distancia_entrada_stop']}")
        tamanho = f"{gestao['tamanho_posicao']}"
        if multiplicador != 1.0:
            tamanho += f" (unidades de {multiplicador} por ponto/contrato)"
        print(f"Tamanho da posição:      {tamanho}")
        print(f"R:R alvo 1: {gestao['r_alvo1']} | R:R alvo 2: {gestao['r_alvo2']}")
        if confianca == "baixa":
            print("Disciplina: confiança baixa — considere reduzir o risco ou aguardar um cenário melhor.")
    else:
        print("\nGestão de risco: não calculável sem operação.")


def main():
    parser = argparse.ArgumentParser(
        description="Copiloto de trade: envie um print do gráfico e receba um plano de trade."
    )
    parser.add_argument("imagem", help="caminho do print do gráfico (PNG/JPEG/WEBP/GIF)")
    parser.add_argument("--capital", type=float, default=10000, help="saldo da conta (default: 10000)")
    parser.add_argument("--risco", type=float, default=1.0, help="risco por trade em %% (default: 1.0)")
    parser.add_argument("--multiplicador", type=float, default=1.0,
                        help="valor do ponto/contrato (ex: 0.2 para mini-índice); default: 1.0")
    parser.add_argument("--modelo", default="auto",
                        help="modelo de visão do Mistral; \"auto\" escolhe o melhor disponível")
    parser.add_argument("--saida", help="salvar o plano em um arquivo JSON")
    parser.add_argument("--sem-diario", action="store_true",
                        help="não registrar a análise no tradex_diario.csv")
    args = parser.parse_args()

    pasta_script = os.path.dirname(os.path.abspath(__file__))
    carrega_env(os.path.join(pasta_script, ".env"))
    carrega_env(".env")

    api_key = os.environ.get("MISTRAL_API_KEY")
    if not api_key:
        sys.exit(
            "Chave não encontrada. Escolha uma das opções:\n"
            "  1) Crie o arquivo .env na pasta do projeto com a linha:\n"
            "       MISTRAL_API_KEY=sua-chave\n"
            "  2) Ou no terminal:  export MISTRAL_API_KEY=sua-chave   (Linux/macOS)\n"
            "  3) Ou no PowerShell: $env:MISTRAL_API_KEY=\"sua-chave\""
        )

    if not os.path.isfile(args.imagem):
        sys.exit(f"Arquivo não encontrado: {args.imagem}")

    modelo = args.modelo
    if modelo == "auto":
        print("Descobrindo o melhor modelo de visão disponível ...")
        modelo = escolhe_modelo(api_key)
        if not modelo:
            sys.exit(
                "Não consegui descobrir um modelo de visão automaticamente.\n"
                "Rode com --modelo <nome>, por exemplo:\n"
                "  python tradex.py grafico.png --modelo mistral-medium-latest"
            )
        print(f"Modelo escolhido: {modelo}")
    print(f"Analisando {args.imagem} com {modelo} ...")
    plano = analyze(args.imagem, modelo, api_key)
    imprime(plano, args.capital, args.risco, args.multiplicador)

    if not args.sem_diario:
        caminho_diario = os.path.join(pasta_script, "tradex_diario.csv")
        gestao = calcula_gestao_risco(plano, args.capital, args.risco, args.multiplicador)
        registra_diario(plano, gestao, caminho_diario, args.imagem)
        print(f"\nAnálise registrada no diário: {caminho_diario}")

    if args.saida:
        with open(args.saida, "w", encoding="utf-8") as fh:
            json.dump(plano, fh, ensure_ascii=False, indent=2)
        print(f"Plano salvo em {args.saida}")

    print(
        "\nAviso: análise gerada por IA a partir de uma imagem. Confira todos os níveis "
        "no seu gráfico antes de operar. Isto não é recomendação de investimento."
    )


if __name__ == "__main__":
    main()
