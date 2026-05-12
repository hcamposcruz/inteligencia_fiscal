import json
import logging
import os
import time
from typing import Optional

import httpx
from fastapi import BackgroundTasks, FastAPI, HTTPException
from pydantic import BaseModel, Field, validator

from storage_client import BlobStorageClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("webhookif")

app = FastAPI(
    title="Webhook Inteligência Fiscal",
    description="Recebe eventos, grava metadata no Blob Storage e dispara o serviço de download de forma assíncrona.",
)


class WebhookPayload(BaseModel):
    """Payload do webhook que contém o tiquete de solicitação e o tiquete de download."""

    tiqueteSolicitacao: str = Field(..., description="Tiquete de solicitação retornado pela Receita Federal.")
    tiqueteDownload: str = Field(..., description="Tiquete válido para baixar o JSON massivo.")
    metadata: Optional[dict] = Field(None, description="Dados adicionais opcionais do evento.")

    @validator("tiqueteSolicitacao", "tiqueteDownload")
    def non_empty_text(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("Campo obrigatório e não pode ser vazio")
        return value.strip()


AZURE_STORAGE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
CONTAINER_NAME = os.getenv("BLOB_CONTAINER_NAME", "beintegracoes")
DOWNLOAD_SERVICE_URL = os.getenv("DOWNLOAD_SERVICE_URL", "http://127.0.0.1:8001/download")

if not AZURE_STORAGE_CONNECTION_STRING:
    raise RuntimeError(
        "Variável de ambiente AZURE_STORAGE_CONNECTION_STRING não definida. "
        "Defina a connection string do Azure Storage antes de executar o webhook."
    )

storage_client = BlobStorageClient(
    connection_string=AZURE_STORAGE_CONNECTION_STRING,
    container_name=CONTAINER_NAME,
    create_container=False,
)


def dispatch_download(tiquete_download: str, tiquete_solicitacao: str) -> None:
    """Dispara o serviço de download de forma assíncrona com retry automático."""
    logger.info(
        "Disparando download para tiqueteSolicitacao=%s tiqueteDownload=%s",
        tiquete_solicitacao,
        tiquete_download,
    )

    max_retries = 3
    retry_delay = 2.0

    for attempt in range(1, max_retries + 1):
        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.post(
                    DOWNLOAD_SERVICE_URL,
                    json={"tiqueteDownload": tiquete_download},
                    timeout=120.0,
                )
                if response.status_code >= 300:
                    logger.warning(
                        "Download service retornou status %s para tiqueteSolicitacao=%s (tentativa %d/%d): %s",
                        response.status_code,
                        tiquete_solicitacao,
                        attempt,
                        max_retries,
                        response.text,
                    )
                    if attempt < max_retries:
                        time.sleep(retry_delay)
                        continue
                    else:
                        logger.error(
                            "Falha definitiva no download após %d tentativas para tiqueteSolicitacao=%s",
                            max_retries,
                            tiquete_solicitacao,
                        )
                        return
                else:
                    logger.info(
                        "Download service aceitou a requisição para tiqueteSolicitacao=%s (tentativa %d)",
                        tiquete_solicitacao,
                        attempt,
                    )
                    return
        except Exception as exc:
            logger.warning(
                "Falha ao chamar serviço de download para tiqueteSolicitacao=%s (tentativa %d/%d): %s",
                tiquete_solicitacao,
                attempt,
                max_retries,
                str(exc),
            )
            if attempt < max_retries:
                time.sleep(retry_delay)
                continue
            else:
                logger.exception(
                    "Falha definitiva no download após %d tentativas para tiqueteSolicitacao=%s",
                    max_retries,
                    tiquete_solicitacao,
                )


@app.head("/webhook")
async def webhook_health_check() -> None:
    """Endpoint HEAD para validar que o webhook está ativo. Retorna 200 OK."""
    logger.info("Verificação de saúde do webhook (HEAD) realizada")
    return


@app.post("/webhook")
async def receive_webhook(payload: WebhookPayload, background_tasks: BackgroundTasks) -> dict:
    """Recebe o webhook, valida o payload e agenda o download."""
    try:
        logger.info(
            "Webhook recebido - tiqueteSolicitacao=%s tiqueteDownload=%s",
            payload.tiqueteSolicitacao,
            payload.tiqueteDownload,
        )

        background_tasks.add_task(dispatch_download, payload.tiqueteDownload, payload.tiqueteSolicitacao)

        return {
            "message": "Webhook recebido com sucesso e download agendado.",
            "tiqueteSolicitacao": payload.tiqueteSolicitacao,
            "download_service_url": DOWNLOAD_SERVICE_URL,
        }
    except Exception as exc:
        logger.exception("Erro ao processar webhook para tiqueteSolicitacao=%s", payload.tiqueteSolicitacao)
        raise HTTPException(status_code=500, detail=f"Erro ao processar webhook: {str(exc)}")



@app.get("/")
async def root() -> dict:
    return {"message": "Webhook Inteligência Fiscal está rodando"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)