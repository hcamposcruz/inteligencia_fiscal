import base64
import hashlib
import logging
import os
import time
from typing import Dict, Iterable, Optional

import httpx
from azure.storage.blob import BlobBlock
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, validator

from storage_client import BlobStorageClient
from token_service import get_access_token

logger = logging.getLogger("download_service")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


class DownloadRequest(BaseModel):
    """Payload que inicia o download de um arquivo JSON massivo."""

    tiqueteDownload: str = Field(..., description="Ticket de download fornecido pela Receita Federal.")

    @validator("tiqueteDownload")
    def validate_tiquete_download(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("tiqueteDownload deve ser uma string não vazia")
        return value.strip()


class DownloadResponse(BaseModel):
    """Resposta retornada pelo serviço de download."""

    status: str
    message: str
    blob_path: str
    downloaded_bytes: int
    content_md5: Optional[str] = None
    duration_seconds: float


class DownloadWorker:
    """Responsável por baixar arquivos grandes e persistir no Azure Blob Storage."""

    CHUNK_SIZE = 4 * 1024 * 1024
    MAX_RETRIES = 3
    RETRY_WAIT_SECONDS = 5.0

    def __init__(self, storage_client: BlobStorageClient, download_url_template: str, container_folder: str):
        self.storage_client = storage_client
        self.download_url_template = download_url_template
        self.container_folder = container_folder

    def build_download_url(self, tiquete_download: str) -> str:
        """Monta a URL de download da Receita Federal a partir do ticket."""
        return self.download_url_template.format(tiquete_download=tiquete_download)

    def fetch_metadata(self, client: httpx.Client, url: str, headers: Dict[str, str]) -> Dict[str, Optional[str]]:
        """Tenta descobrir se o servidor suporta downloads em range e o tamanho total."""
        try:
            response = client.head(url, headers=headers, timeout=60.0)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in {405, 501}:
                logger.warning("HEAD não suportado pela API de origem; usando GET para metadados")
            else:
                raise
        except Exception:
            logger.warning("Falha no HEAD; fallback para GET simples de metadados")
        else:
            return {
                "content_length": response.headers.get("content-length"),
                "accept_ranges": response.headers.get("accept-ranges"),
                "content_md5": response.headers.get("content-md5"),
            }

        with client.stream("GET", url, headers=headers, timeout=60.0) as response:
            response.raise_for_status()
            return {
                "content_length": response.headers.get("content-length"),
                "accept_ranges": response.headers.get("accept-ranges"),
                "content_md5": response.headers.get("content-md5"),
            }

    def download_file(self, tiquete_download: str) -> DownloadResponse:
        """Baixa o arquivo JSON e grava no Blob Storage usando streaming."""
        url = self.build_download_url(tiquete_download)
        blob_path = f"{self.container_folder}/{tiquete_download}.json"
        logger.info("Iniciando download para ticket %s -> %s", tiquete_download, blob_path)

        start_time = time.time()
        access_token = get_access_token()
        auth_headers = {"Authorization": f"Bearer {access_token}"}

        client = httpx.Client(follow_redirects=True)
        try:
            metadata = self.fetch_metadata(client, url, auth_headers)
            content_length = int(metadata["content_length"]) if metadata.get("content_length") else None
            accept_ranges = metadata.get("accept_ranges") or "none"
            expected_md5 = metadata.get("content_md5")

            if accept_ranges.lower() == "bytes" and content_length and content_length > self.CHUNK_SIZE:
                logger.info("Servidor suporta Range downloads; usando lógica chunked")
                downloaded_bytes, computed_md5 = self.download_with_range(client, url, blob_path, content_length, auth_headers)
            else:
                logger.info("Fazendo download em streaming sem Range")
                downloaded_bytes, computed_md5 = self.download_stream(client, url, blob_path, auth_headers)

            duration = time.time() - start_time
            logger.info("Download concluído para %s (%d bytes, %.2f s)", tiquete_download, downloaded_bytes, duration)

            if expected_md5:
                logger.info("Hash MD5 esperado: %s", expected_md5)
                if computed_md5 and computed_md5 != expected_md5:
                    raise ValueError("Validação MD5 falhou: conteúdo baixado não confere com cabeçalho esperado")

            return DownloadResponse(
                status="completed",
                message="Download concluído com sucesso",
                blob_path=blob_path,
                downloaded_bytes=downloaded_bytes,
                content_md5=computed_md5,
                duration_seconds=duration,
            )
        finally:
            client.close()

    def download_stream(self, client: httpx.Client, url: str, blob_path: str, headers: Dict[str, str]) -> tuple[int, Optional[str]]:
        blob_client = self.storage_client.container_client.get_blob_client(blob_path)
        hasher = hashlib.md5()
        total_bytes = 0

        def content_generator() -> Iterable[bytes]:
            nonlocal total_bytes
            with client.stream("GET", url, headers=headers, timeout=120.0) as response:
                response.raise_for_status()
                for chunk in response.iter_bytes(self.CHUNK_SIZE):
                    if not chunk:
                        continue
                    hasher.update(chunk)
                    total_bytes += len(chunk)
                    yield chunk
                    if total_bytes % (self.CHUNK_SIZE * 4) == 0:
                        logger.info("Progresso do stream: %d bytes baixados", total_bytes)

        self.storage_client.upload_stream(blob_path, content_generator())
        return total_bytes, hasher.hexdigest()

    def download_with_range(self, client: httpx.Client, url: str, blob_path: str, content_length: int, headers: Dict[str, str]) -> tuple[int, Optional[str]]:
        blob_client = self.storage_client.container_client.get_blob_client(blob_path)
        hasher = hashlib.md5()
        block_ids = []
        downloaded_bytes = 0
        block_index = 0

        for start in range(0, content_length, self.CHUNK_SIZE):
            end = min(start + self.CHUNK_SIZE - 1, content_length - 1)
            range_header = {"Range": f"bytes={start}-{end}"}
            logger.debug("Solicitando range %s", range_header["Range"])
            request_headers = {**headers, **range_header}
            with client.stream("GET", url, headers=request_headers, timeout=120.0) as response:
                if response.status_code not in {200, 206}:
                    raise httpx.HTTPStatusError("Resposta inesperada para range", request=response.request, response=response)

                chunk_data = b""
                for chunk in response.iter_bytes(self.CHUNK_SIZE):
                    if not chunk:
                        continue
                    chunk_data += chunk
                if not chunk_data:
                    break

                block_index += 1
                block_id = base64.b64encode(f"{block_index:06d}".encode()).decode()
                blob_client.stage_block(block_id=block_id, data=chunk_data)
                block_ids.append(block_id)
                hasher.update(chunk_data)
                downloaded_bytes += len(chunk_data)
                logger.info("Bloco %d stageado com %d bytes (total %d)", block_index, len(chunk_data), downloaded_bytes)

        blob_client.commit_block_list([BlobBlock(block_id=b) for b in block_ids])
        return downloaded_bytes, hasher.hexdigest()


def create_download_worker() -> DownloadWorker:
    connection_string = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
    container_name = os.getenv("DOWNLOAD_CONTAINER_NAME", "beintegracoes")
    container_folder = os.getenv("DOWNLOAD_FOLDER", "downloads_cbs")

    if not connection_string:
        raise RuntimeError("AZURE_STORAGE_CONNECTION_STRING não definido para download_service")

    storage_client = BlobStorageClient(
        connection_string=connection_string,
        container_name=container_name,
        create_container=True,
    )

    url_template = os.getenv(
        "RECEITA_DOWNLOAD_URL_TEMPLATE",
        "https://api.receita.fazenda.gov.br/download/{tiquete_download}",
    )

    return DownloadWorker(storage_client=storage_client, download_url_template=url_template, container_folder=container_folder)


app = FastAPI(title="Download Service", description="Serviço independente para baixar arquivos JSON massivos da Receita Federal")
worker = create_download_worker()


@app.post("/download", response_model=DownloadResponse)
def download_endpoint(payload: DownloadRequest) -> DownloadResponse:
    try:
        return worker.download_file(payload.tiqueteDownload)
    except Exception as exc:
        logger.exception("Falha ao processar download para ticket %s", payload.tiqueteDownload)
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/")
def health_check() -> Dict[str, str]:
    return {"status": "running", "service": "download_service"}
