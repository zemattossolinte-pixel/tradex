#!/usr/bin/env python3
"""Tradex Web: interface no navegador para análise de gráficos.

Roda um servidor local (só na sua máquina) que serve a página web e
repassa as análises à API do Mistral. A chave fica no .env e nunca
chega ao navegador.

Uso:  python servidor.py   (abre o navegador em http://127.0.0.1:8765)
"""

import json
import os
import threading
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import tradex

PORTA = 8765
PASTA_SCRIPT = os.path.dirname(os.path.abspath(__file__))


class Handler(BaseHTTPRequestHandler):
    def _json(self, codigo, conteudo):
        dados = json.dumps(conteudo, ensure_ascii=False).encode("utf-8")
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(dados)))
        self.end_headers()
        self.wfile.write(dados)

    def do_GET(self):
        caminho = urllib.parse.urlparse(self.path).path
        if caminho in ("/", "/index.html"):
            arquivo = os.path.join(PASTA_SCRIPT, "index.html")
            with open(arquivo, "rb") as fh:
                conteudo = fh.read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(conteudo)))
            self.end_headers()
            self.wfile.write(conteudo)
        else:
            self._json(404, {"erro": "página não encontrada"})

    def do_POST(self):
        if urllib.parse.urlparse(self.path).path != "/analisar":
            self._json(404, {"erro": "rota não encontrada"})
            return
        try:
            tamanho = int(self.headers.get("Content-Length", 0))
            pedido = json.loads(self.rfile.read(tamanho).decode("utf-8"))
        except Exception as exc:
            self._json(400, {"erro": f"pedido inválido: {exc}"})
            return

        api_key = os.environ.get("MISTRAL_API_KEY")
        if not api_key:
            self._json(500, {"erro": "Chave não encontrada no arquivo .env. Crie o arquivo .env na pasta do projeto com MISTRAL_API_KEY=sua-chave"})
            return

        try:
            modelo = pedido.get("modelo") or tradex.resolve_modelo(api_key)
            if not modelo:
                self._json(500, {"erro": "Nenhum modelo de visão disponível na API do Mistral."})
                return

            mime = pedido.get("mime", "image/png")
            body = {
                "model": modelo,
                "temperature": 0.2,
                "messages": [{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": tradex.PROMPT},
                        {"type": "image_url", "image_url": f"data:{mime};base64,{pedido['imagem_b64']}"},
                    ],
                }],
                "response_format": {"type": "json_object"},
            }
            resposta = tradex.chama_api(body, api_key)
            if resposta is None:
                body.pop("response_format", None)
                resposta = tradex.chama_api(body, api_key)
            conteudo = resposta["choices"][0]["message"]["content"]
            plano = tradex.valida_plano(tradex.extract_json(conteudo))

            capital = float(pedido.get("capital") or 10000)
            risco = float(pedido.get("risco") or 1.0)
            multiplicador = float(pedido.get("multiplicador") or 1.0)
            gestao = tradex.calcula_gestao_risco(plano, capital, risco, multiplicador)

            if not pedido.get("sem_diario"):
                tradex.registra_diario(plano, gestao, os.path.join(PASTA_SCRIPT, "tradex_diario.csv"),
                                       pedido.get("nome_arquivo") or "upload")
            self._json(200, {"plano": plano, "gestao": gestao, "modelo": modelo})
        except SystemExit as exc:
            self._json(500, {"erro": str(exc)})
        except Exception as exc:
            self._json(500, {"erro": f"Falha na análise: {exc}"})

    def log_message(self, formato, *args):
        print(f"[{self.address_string()}] {formato % args}")


def ip_local():
    import socket
    soquete = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        soquete.connect(("8.8.8.8", 80))
        return soquete.getsockname()[0]
    except OSError:
        return None
    finally:
        soquete.close()


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Tradex Web (servidor local)")
    parser.add_argument("--porta", type=int, default=PORTA, help="porta do servidor (default: 8765)")
    parser.add_argument("--rede", action="store_true",
                        help="abrir o acesso para outros aparelhos da sua rede Wi-Fi (celular/tablet)")
    args = parser.parse_args()

    tradex.carrega_env(os.path.join(PASTA_SCRIPT, ".env"))
    if not os.environ.get("MISTRAL_API_KEY"):
        print("!! Chave não encontrada: crie o arquivo .env na pasta do projeto com MISTRAL_API_KEY=sua-chave")
        print("!! (o servidor vai subir, mas as análises vão falhar até a chave existir)")
    url = f"http://127.0.0.1:{PORTA}"
    servidor = ThreadingHTTPServer(("127.0.0.1", PORTA), Handler)
    threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    print(f"Tradex Web em {url}  (Ctrl+C para encerrar)")
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor encerrado.")


if __name__ == "__main__":
    main()
