# Arquitetura do projeto Webhook + Download Service

## Visão Geral

O projeto é composto por dois serviços Python independentes:

1. `webhookif.py`
   - Recebe eventos de webhook do governo.
   - Valida e grava o payload no Azure Blob Storage.
   - Dispara de forma assíncrona o serviço de download usando o campo `tiqueteDownload`.

2. `download_service.py`
   - Faz o download de arquivos JSON massivos da Receita Federal.
   - Usa streaming e lógica de range requests quando disponível.
   - Persiste o resultado no mesmo container Azure Blob Storage em outra pasta.

## Fluxo Completo

1. O governo chama o webhook público exposto via ngrok.
2. `webhookif.py` recebe o request em `/webhook`.
3. O payload é validado e armazenado em Blob Storage no caminho:
   - `beintegracoes/InteligenciaFiscal/Apuracao/Tiquete/{tiqueteSolicitacao}.json`
4. O webhook dispara um POST assíncrono para `download_service.py` com `tiqueteDownload`.
5. `download_service.py` consulta a API da Receita Federal e baixa o arquivo JSON.
6. O arquivo JSON grande é armazenado em Blob Storage no caminho:
   - `beintegracoes/downloads_cbs/{tiqueteDownload}.json`

## Diagrama da arquitetura

```
[Receita Federal] ---> [ngrok HTTPS] ---> [webhookif.py (FastAPI)]
                                 |             |
                                 |             +--> Azure Blob Storage (payload)
                                 |
                                 +--> [download_service.py (FastAPI)]
                                               |
                                               +--> Azure Blob Storage (download)
```

## Componentes principais

- `storage_client.py`
  - Abstrai operações de Blob Storage.
  - Isola upload JSON e upload por stream.

- `download_service.py`
  - Lida com downloads grandes, retry e verificação MD5 opcional.
  - Detecta suporte a `Accept-Ranges` e faz download em blocos se possível.

- `webhookif.py`
  - Controlador do webhook.
  - Usa `BackgroundTasks` do FastAPI para não bloquear o fluxo principal.

## Observabilidade e testes

- Logs detalhados são gravados em cada etapa do download.
- O download service retorna dados estruturados com `downloaded_bytes` e `duration_seconds`.
- Use `curl` ou Postman para validar os endpoints:
  - `POST /webhook`
  - `POST /download`

## Boas práticas aplicadas

- Tipagem forte com `Pydantic`.
- Componentização para facilitar testes e manutenção.
- Padrão REST simples e previsível.
- Upload direto para Blob Storage em vez de armazenamento local.
- Asynchronous fire-and-forget do webhook para evitar bloqueio.
