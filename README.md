# Tradex 📈

Copiloto de trade por imagem: você envia um **print do gráfico** e o Tradex
analisa com um modelo de visão do Mistral, devolvendo um plano de trade
estruturado com **entrada, stop loss, alvos, risco/retorno e tamanho de posição**.

> ⚠️ A análise é gerada por IA a partir de uma imagem e pode errar leitura de
> preços. Confira todos os níveis no seu gráfico antes de operar. Isto não é
> recomendação de investimento.

## Passo a passo para iniciantes

**1. Instale o Python** — baixe em [python.org/downloads](https://www.python.org/downloads/)
e, na instalação no Windows, marque a opção **"Add Python to PATH"**.

**2. Baixe o projeto** (uma vez só):

- Abra [github.com/zemattossolinte-pixel/tradex](https://github.com/zemattossolinte-pixel/tradex)
- Botão verde **Code** → **Download ZIP** → extraia
- **NÃO precisa instalar bibliotecas** o Tradex usa apenas o Python padrão
  (o `pip install` de versões antigas não é mais necessário)

**3. Pegue sua chave da Mistral** — crie uma conta grátis em
[console.mistral.ai](https://console.mistral.ai), vá em **API Keys → Create new key**,
copie a chave e **guarde-a em segredo** (nunca publique nem mande para ninguém).

**4. Coloque a chave no arquivo `.env`** (a chave NÃO vai no código):
na pasta `tradex`, crie um arquivo de texto chamado `.env` com esta linha
(usando a SUA chave, copiada do passo 3):

```
MISTRAL_API_KEY=cole-aqui-a-chave-que-voce-copiou
```

Salve. Pronto — o Tradex encontra a chave sozinho a partir daí.

**5. Use:**

```
python tradex.py grafico.png
```

Onde `grafico.png` é o print do gráfico que você quer analisar (o arquivo
precisa estar na mesma pasta, ou use o caminho completo).

### Modo web (recomendado)

Interface no navegador: arraste o print, informe capital/risco e veja o plano
em cartões organizados:

```
python servidor.py
```

O navegador abre sozinho em http://127.0.0.1:8765. O servidor roda apenas na
sua máquina (127.0.0.1) e hospeda o servidor local — a chave fica no `.env` e
nunca vai para o navegador.

Para configurar seu capital e risco por trade:

```
python tradex.py grafico.png --capital 5000 --risco 1.5
```

Opções extras:

```
python tradex.py grafico.png --multiplicador 0.2      # valor por ponto de mini-futuros
python tradex.py grafico.png --sem-diario             # não gravar no diário de trades
python tradex.py grafico.png --saida plano.json       # salvar o plano em JSON
```

- `--multiplicador 0.2`: valor financeiro por ponto de movimento (default: 1.0).
- `--sem-diario`: desativa o registro automático no `tradex_diario.csv`.

## Como funciona

1. O Tradex pergunta à API do Mistral quais modelos de visão estão disponíveis
   e escolhe automaticamente o melhor (`--modelo` permite forçar outro).
2. O modelo atua como analista técnico e responde em JSON estruturado:
   tendência, suportes/resistências, padrões, direção, entrada, stop, alvos,
   justificativa, invalidação e nível de confiança.
3. O Tradex **calcula localmente** o tamanho da posição a partir do seu capital
   e do risco por trade (`risco_financeiro / distância até o stop`), além do
   R:R real de cada alvo. Se a leitura da imagem for ruim, o agente responde
   `"direcao": "aguardar"` em vez de inventar números.
4. **Checklist de disciplina**: o agente marca critérios objetivos de
   confirmação (tendência alinhada, padrão confirmado, R:R >= 2, volume ...).
   Se a maioria não confirmar, a resposta é `AGUARDAR` — paciência também é
   decisão de trader.
5. **Diário de trades**: toda análise (inclusive os "aguardar") é gravada
   automaticamente em `tradex_diario.csv`, para você revisar depois o que
   funcionou e o que não funcionou.

## O que vem na análise

- Contexto da tendência, suportes, resistências, padrões e indicadores
- Fundamentos/macro do ativo (como contexto, já que os dados do modelo podem
  estar desatualizados)
- Checklist de disciplina com critérios confirmados/não confirmados
- Direção (compra/venda/aguardar), entrada, stop (atrás da estrutura), alvos
  (R:R mínimo 2:1)
- Gestão da operação: quando realizar parcial e mover o stop para breakeven
- Plano B (cenário alternativo) e critérios de invalidação
- Tamanho da posição e R:R calculados localmente (independente da IA)

Abrindo o diário depois:

```
notepad tradex_diario.csv
```

## Alternativa: chave só para o momento (sem criar arquivo)

Se preferir não criar o `.env`, dá para definir a chave direto no terminal
(vale só enquanto a janela estiver aberta):

```
# Linux/macOS
export MISTRAL_API_KEY=sua-chave

# Windows (PowerShell)
$env:MISTRAL_API_KEY="sua-chave"
```

## Ronda diária (onde olhar hoje)

A Ronda olha o fechamento do dia da B3 e das cripto e devolve uma **watchlist**
ranqueada: empresas fundamentadamente saudáveis em situações técnicas
interessantes. Ela **não prevê o preço de amanhã** — aponta onde vale tirar o
print do gráfico diário e rodar no Tradex para ter entrada, stop e alvos.

**Modo web:** abra o Tradex e clique na aba **🔍 Ronda diária** → "Rodar a
ronda de hoje".

**No terminal:**

```
python ronda.py
```

O resultado também é salvo em `ronda_hoje.json`.

### Token da brapi (opcional, mas recomendado)

A Ronda usa a API gratuita [brapi.dev](https://brapi.dev) para cotações da B3.
Sem token, funcionam apenas PETR4, VALE3, ITUB4, MGLU3 e as cripto (via OKX).
Para ver **todas** as ações da watchlist e o IBOV/dólar:

1. Crie uma conta gratuita em https://brapi.dev e copie seu token.
2. Adicione uma linha no arquivo `.env` (mesma pasta do Tradex):

```
BRAPI_TOKEN=seu-token-da-brapi
```

Nada mais muda: sem token a Ronda segue funcionando com o que for gratuito.

### Como usar a watchlist no dia a dia

1. Rode a Ronda depois do fechamento da B3 (a partir das 18h).
2. Pegue os 2-3 primeiros da watchlist e tire o print do gráfico **diário** de cada um.
3. Rode cada print na aba **Analisar** (ou `python tradex.py grafico.png`).
4. Só entre nos planos com COMPRA/VENDA e R:R ≥ 2 — AGUARDAR é uma decisão válida.

## Dicas para melhores análises

- Capture o gráfico com candlesticks limpos e escala de preços legível.
- Inclua o nome do ativo e o timeframe no recorte.
- Evite marcações sobrepostas demais: elas confundem a leitura.

## Estrutura do projeto

```
tradex.py           Motor de análise (visão + gestão de risco + diário) — usado pelo CLI e pela web
servidor.py         Servidor local do modo web (abre o navegador em 127.0.0.1:8765)
index.html          Página do modo web (arrastar e soltar o gráfico + aba Ronda)
ronda.py            Ronda diária: fechamentos da B3/cripto e watchlist ranqueada
requirements.txt    sem dependências (Python padrão)
.env.example        Modelo do arquivo .env
```
