# Tradex 📈

Copiloto de trade por imagem: você envia um **print do gráfico** e o Tradex
analisa com um modelo de visão do Mistral, devolvendo um plano de trade
estruturado com **entrada, stop loss, alvos, risco/retorno e tamanho de posição**.

> ⚠️ A análise é gerada por IA a partir de uma imagem e pode errar leitura de
> preços. Confira todos os níveis no seu gráfico antes de operar. Isto não é
> recomendação de investimento.

## Como funciona

1. O print do gráfico é enviado ao modelo de visão (`pixtral-large-latest` por padrão).
2. O modelo atua como analista técnico e responde em JSON estruturado:
   tendência, suportes/resistências, padrões, direção, entrada, stop, alvos,
   justificativa, invalidação e nível de confiança.
3. O Tradex **calcula localmente** o tamanho da posição a partir do seu capital
   e do risco por trade (`risco_financeiro / distância até o stop`), além do
   R:R real de cada alvo. Se a leitura da imagem for ruim, o agente responde
   `"direcao": "aguardar"` em vez de inventar números.

## Instalação

Requisitos: Python 3.9+

```bash
pip install -r requirements.txt
```

Crie uma chave de API em [console.mistral.ai](https://console.mistral.ai) e
exporte como variável de ambiente:

```bash
# Linux/macOS
export MISTRAL_API_KEY=sua-chave

# Windows (PowerShell)
$env:MISTRAL_API_KEY="sua-chave"
```

## Uso

```bash
python tradex.py grafico.png
```

Com seu capital e risco por trade (default: capital 10000, risco 1%):

```bash
python tradex.py grafico.png --capital 5000 --risco 1.5
```

Com outro modelo e salvando o plano em JSON:

```bash
python tradex.py grafico.png --modelo pixtral-12b-2409 --saida plano.json
```

Para operação de compra com capital 10000 e risco 1%: risco de 100 na moeda,
tamanho de posição `100 / |entrada - stop|`, calculado e impresso no terminal.

## Dicas para melhores análises

- Capture o gráfico com candlesticks limpos e escala de preços legível.
- Inclua o nome do ativo e o timeframe no recorte.
- Evite marcações sobrepostas demais: elas confundem a leitura.

## Estrutura do projeto

```
tradex.py           CLI principal (visão + análise + gestão de risco)
requirements.txt    Dependências
.env.example        Modelo de variáveis de ambiente
```
