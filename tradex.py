#!/usr/bin/env python3
"""Tradex: copiloto de trade por imagem.

Envia um print do gráfico para o modelo de visão do Mistral e recebe um
plano de trade estruturado (entrada, stop loss, alvos) com cálculo local
de risco/retorno e tamanho de posição.
"""

import argparse
import base64
import json
import mimetypes
import os
import sys

PROMPT = """Você é um analista técnico sênior de trading. Analise o gráfico enviado \
considerando o ativo, o timeframe e escala de preços visíveis na imagem.

Responda a análise em português e ESTRITAMENTE em JSON, com este formato:
{
  "ativo": "nome do ativo lido da imagem ou 'desconhecido'",
  "timeframe": "timeframe visível ou 'desconhecido'",
  "direcao": "compra" | "venda" | "aguardar",
  "contexto": {
    "tendencia": "resumo da tendência (alta/baixa/lateral)",
    "suportes": [preços legíveis na tela],
    "resistencias": [preços legíveis na tela],
    "padroes": ["padrões gráficos e candlesticks identificados"],
    "indicadores": "o que RSI, médias móveis, volume etc. sugerem"
  },
  "entrada": <número ou null se aguardar>,
  "stop_loss": <número ou null se aguardar>,
  "alvo1": <número ou null se aguardar>,
  "alvo2": <número ou null se aguardar>,
  "justificativa": "por que esse gatilho, stop e alvos, citando a estrutura do gráfico",
  "invalidacao": "o que anularia o cenário",
  "confianca": "baixa" | "média" | "alta"
}

Regras obrigatórias:
- Use SOMENTE preços que você consegue ler claramente na imagem. Nunca invente números.
- Alvos devem respeitar relação risco/retorno mínima de 2:1 em relação ao stop.
- Stop deve ficar atrás de uma estrutura (topo/fundo/pavio), não em distância arbitrária.
- Se a imagem estiver ilegível, sem preços claros ou o cenário for fraco, use
  "direcao": "aguardar" e explique o motivo em "justificativa".

Retorne APENAS o JSON, sem texto antes ou depois."""


def carrega_env(path):
    """Lê um arquivo .env simples (CHAVE=valor) e define variáveis não definidas."""
    if not os.path.isfile(path):
        return
    with open(path, encoding="utf-8-sig") as fh:
        for line in fh:
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


def analyze(path, model, api_key):
    from mistralai import Mistral

    mime, b64 = encode_image(path)
    client = Mistral(api_key=api_key)
    message = {
        "role": "user",
        "content": [
            {"type": "text", "text": PROMPT},
            {"type": "image_url", "image_url": f"data:{mime};base64,{b64}"},
        ],
    }
    try:
        response = client.chat.complete(
            model=model,
            messages=[message],
            response_format={"type": "json_object"},
            temperature=0.2,
        )
    except Exception:
        response = client.chat.complete(
            model=model,
            messages=[message],
            temperature=0.2,
        )
    return extract_json(response.choices[0].message.content)


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


def calcula_gestao_risco(plano, capital, risco_pct):
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
    risco_financeiro = capital * risco_pct / 100
    quantidade = risco_financeiro / distancia

    def rr(alvo):
        return round(abs(alvo - entrada) / distancia, 2) if isinstance(alvo, (int, float)) else None

    return {
        "risco_financeiro": round(risco_financeiro, 2),
        "distancia_entrada_stop": round(distancia, 6),
        "tamanho_posicao": round(quantidade, 6),
        "r_alvo1": rr(plano.get("alvo1")),
        "r_alvo2": rr(plano.get("alvo2")),
    }


def imprime(plano, capital, risco_pct):
    print("=" * 60)
    print(f"Ativo:      {plano.get('ativo', 'desconhecido')}")
    print(f"Timeframe:  {plano.get('timeframe', 'desconhecido')}")
    print(f"Decisão:    {plano.get('direcao', 'aguardar').upper()}")
    print("=" * 60)

    contexto = plano.get("contexto") or {}
    if contexto:
        print("\n--- Contexto ---")
        print(f"Tendência:   {contexto.get('tendencia', '-')}")
        print(f"Suportes:    {contexto.get('suportes', '-')}")
        print(f"Resistências:{contexto.get('resistencias', '-')}")
        print(f"Padrões:     {contexto.get('padroes', '-')}")
        print(f"Indicadores: {contexto.get('indicadores', '-')}")

    if plano.get("direcao") in ("compra", "venda") and plano.get("entrada") is not None:
        print("\n--- Plano operacional ---")
        print(f"Entrada:     {plano.get('entrada')}")
        print(f"Stop loss:   {plano.get('stop_loss')}")
        print(f"Alvo 1:      {plano.get('alvo1')}")
        print(f"Alvo 2:      {plano.get('alvo2')}")
    else:
        print("\nSem operação sugerida: aguarde.")

    print(f"\nJustificativa: {plano.get('justificativa', '-')}")
    print(f"Invalidação:   {plano.get('invalidacao', '-')}")
    print(f"Confiança:     {plano.get('confianca', '-')}")

    gestao = calcula_gestao_risco(plano, capital, risco_pct)
    if gestao:
        print("\n--- Gestão de risco (calculado localmente) ---")
        print(f"Risco por trade ({risco_pct}% de {capital}): {gestao['risco_financeiro']}")
        print(f"Distância entrada->stop: {gestao['distancia_entrada_stop']}")
        print(f"Tamanho da posição:      {gestao['tamanho_posicao']}")
        print(f"R:R alvo 1: {gestao['r_alvo1']} | R:R alvo 2: {gestao['r_alvo2']}")
    else:
        print(f"\nGestão de risco: não calculável fora de operações.\n")


def main():
    parser = argparse.ArgumentParser(
        description="Copiloto de trade: envie um print do gráfico e receba um plano de trade."
    )
    parser.add_argument("imagem", help="caminho do print do gráfico (PNG/JPEG/WEBP/GIF)")
    parser.add_argument("--capital", type=float, default=10000, help="saldo da conta (default: 10000)")
    parser.add_argument("--risco", type=float, default=1.0, help="risco por trade em %% (default: 1.0)")
    parser.add_argument("--modelo", default="pixtral-large-latest", help="modelo de visão do Mistral")
    parser.add_argument("--saida", help="salvar o plano em um arquivo JSON")
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

    print(f"Analisando {args.imagem} com {args.modelo} ...")
    plano = analyze(args.imagem, args.modelo, api_key)
    imprime(plano, args.capital, args.risco)

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
