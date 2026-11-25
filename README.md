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

**2. Baixe o projeto** (uma vez só). No Terminal (macOS) ou PowerShell (Windows):

```
git clone https://github.com/zemattossolinte-pixel/tradex.git
cd tradex
pip install -r requirements.txt
```

Se o `git` não estiver instalado, baixe em [git-scm.com](https://git-scm.com/downloads)
(ou, alternativamente, baixe os arquivos em **Code → Download ZIP** e extraia).

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

Para configurar seu capital e risco por trade:

```
python tradex.py grafico.png --capital 5000 --risco 1.5
```

## Como funciona

1. O print do gráfico é enviado ao modelo de visão (`pixtral-large-latest` por padrão).
2. O modelo atua como analista técnico e responde em JSON estruturado:
   tendência, suportes/resistências, padrões, direção, entrada, stop, alvos,
   justificativa, invalidação e nível de confiança.
3. O Tradex **calcula localmente** o tamanho da posição a partir do seu capital
   e do risco por trade (`risco_financeiro / distância até o stop`), além do
   R:R real de cada alvo. Se a leitura da imagem for ruim, o agente responde
   `"direcao": "aguardar"` em vez de inventar números.

## Alternativa: chave só para o momento (sem criar arquivo)

Se preferir não criar o `.env`, dá para definir a chave direto no terminal
(vale só enquanto a janela estiver aberta):

```
# Linux/macOS
export MISTRAL_API_KEY=sua-chave

# Windows (PowerShell)
$env:MISTRAL_API_KEY="sua-chave"
```

## Dicas para melhores análises

- Capture o gráfico com candlesticks limpos e escala de preços legível.
- Inclua o nome do ativo e o timeframe no recorte.
- Evite marcações sobrepostas demais: elas confundem a leitura.

## Estrutura do projeto

```
tradex.py           CLI principal (visão + análise + gestão de risco)
requirements.txt    Dependências
.env.example        Modelo do arquivo .env
```
