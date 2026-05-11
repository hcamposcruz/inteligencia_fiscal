# Webhook Inteligência Fiscal

Este projeto implementa um conjunto de serviços Python que trabalham juntos para receber eventos do governo, persistir metadados em Azure Blob Storage e baixar arquivos JSON massivos da Receita Federal.

## 🚀 Serviços

- `webhookif.py` — serviço principal que recebe o webhook, valida o payload e dispara o download.
- `download_service.py` — serviço independente que baixa arquivos JSON grandes e salva no Blob Storage.
- `storage_client.py` — cliente de Blob Storage reutilizável.

## 📦 Funcionalidades

- Recebe requisições POST em `/webhook` com `tiqueteSolicitacao` e `tiqueteDownload`
- Persiste o payload do webhook em Azure Blob Storage
- Dispara o serviço de download de forma assíncrona para não bloquear o webhook
- Faz download streaming de arquivos grandes
- Usa logic de range requests quando suportado pela API de origem
- Salva os downloads em `beintegracoes/downloads_cbs/`
- Mantém logs de progresso e validação de integridade MD5 quando disponível

## 📋 Pré-requisitos

- Python 3.10+
- Conta Azure com Storage Account
- Container Azure Blob `beintegracoes`
- `ngrok` ou túnel equivalente para expor o webhook local

## ⚙️ Configuração

### Variáveis de ambiente necessárias

```powershell
$env:AZURE_STORAGE_CONNECTION_STRING = "DefaultEndpointsProtocol=https;AccountName=...;AccountKey=...;EndpointSuffix=core.windows.net"
```

### Variáveis de ambiente opcionais

```powershell
$env:BLOB_CONTAINER_NAME = "beintegracoes"
$env:DOWNLOAD_SERVICE_URL = "http://127.0.0.1:8001/download"
$env:DOWNLOAD_FOLDER = "downloads_cbs"
$env:RECEITA_DOWNLOAD_URL_TEMPLATE = "https://api.receita.fazenda.gov.br/download/{tiquete_download}"
```

## 📥 Instalar dependências

```powershell
python -m pip install -r requirements.txt
```

## ▶️ Como rodar

### 1. Iniciar o webhook

```powershell
python webhookif.py
```

O webhook ficará disponível em `http://localhost:8000`.

### 2. Iniciar o serviço de download

```powershell
python download_service.py
```

O serviço de download ficará disponível em `http://localhost:8001`.

### 3. Expor o webhook com ngrok

```powershell
ngrok http 8000
```

Use a URL HTTPS gerada pelo ngrok para registrar o webhook do governo.

## 📡 Endpoints

### Webhook

`POST http://localhost:8000/webhook`

**Payload esperado:**

```json
{
  "tiqueteSolicitacao": "665ca58a-bded-48f4-939e-8edfe892f1ee.AE7EAEFF",
  "tiqueteDownload": "25817fd7-406f-4bef-b9c9-1b2faebfabde.D9342197"
}
```

**Resposta de sucesso:**

```json
{
  "message": "Payload gravado com sucesso e download agendado.",
  "tiqueteSolicitacao": "665ca58a-bded-48f4-939e-8edfe892f1ee.AE7EAEFF",
  "download_service_url": "http://127.0.0.1:8001/download"
}
```

### Serviço de download

`POST http://localhost:8001/download`

**Payload esperado:**

```json
{
  "tiqueteDownload": "25817fd7-406f-4bef-b9c9-1b2faebfabde.D9342197"
}
```

## 📁 Estrutura esperada no Blob Storage

- `beintegracoes/InteligenciaFiscal/Apuracao/Tiquete/{tiqueteSolicitacao}.json`
- `beintegracoes/downloads_cbs/{tiqueteDownload}.json`

## 🧪 Exemplos de chamada

### Com curl

```powershell
curl -X POST "http://localhost:8000/webhook" -H "Content-Type: application/json" -d '{"tiqueteSolicitacao":"665ca58a-bded-48f4-939e-8edfe892f1ee.AE7EAEFF","tiqueteDownload":"25817fd7-406f-4bef-b9c9-1b2faebfabde.D9342197"}'
```

### Com Python requests

```python
import requests

payload = {
    "tiqueteSolicitacao": "665ca58a-bded-48f4-939e-8edfe892f1ee.AE7EAEFF",
    "tiqueteDownload": "25817fd7-406f-4bef-b9c9-1b2faebfabde.D9342197",
}

response = requests.post("http://localhost:8000/webhook", json=payload)
print(response.status_code, response.json())
```

## 📚 Documentação de arquitetura

Veja `ARCHITECTURE.md` para o diagrama completo, fluxo e explicações de design.

## 🛠️ Tecnologias

- **FastAPI** — API web moderna e assíncrona
- **Pydantic** — validação de payloads e tipagem forte
- **Azure Blob Storage** — persistência de JSON e downloads grandes
- **HTTPX** — cliente HTTP para streaming e retry
- **Uvicorn** — servidor ASGI para rodar os serviços
