import base64
import json
import logging
from typing import Iterable

from azure.storage.blob import BlobBlock, BlobServiceClient, ContentSettings

logger = logging.getLogger(__name__)


class BlobStorageClient:
    """Azure Blob Storage helper para upload de JSON e streams em containers.

    Este cliente abstrai a conexão com o Blob Storage e permite salvar arquivos
    JSON e conteúdo grande em streams de forma reusável.
    """

    def __init__(self, connection_string: str, container_name: str, create_container: bool = False):
        self._connection_string = connection_string
        self._container_name = container_name
        self._client = BlobServiceClient.from_connection_string(connection_string)
        self.container_client = self._client.get_container_client(container_name)

        if create_container:
            self.ensure_container_exists()

    def ensure_container_exists(self) -> None:
        """Cria o container no Azure Blob Storage caso ele ainda não exista."""
        try:
            if not self.container_client.exists():
                self.container_client.create_container()
                logger.info("Container criado: %s", self._container_name)
        except Exception as exc:
            logger.exception("Falha ao verificar/criar container %s: %s", self._container_name, exc)
            raise

    def upload_json(self, blob_path: str, payload: dict, overwrite: bool = True) -> None:
        """Faz upload de um objeto JSON para um blob no container."""
        json_text = json.dumps(payload, ensure_ascii=False, indent=2)
        blob_client = self.container_client.get_blob_client(blob_path)
        blob_client.upload_blob(
            json_text,
            overwrite=overwrite,
            content_settings=ContentSettings(content_type="application/json"),
        )
        logger.info("JSON salvo no blob %s", blob_path)

    def upload_stream(self, blob_path: str, data_stream: Iterable[bytes], overwrite: bool = True, content_type: str = "application/json") -> None:
        """Faz upload de um stream iterável de bytes para um blob."""
        blob_client = self.container_client.get_blob_client(blob_path)
        blob_client.upload_blob(
            data_stream,
            overwrite=overwrite,
            content_settings=ContentSettings(content_type=content_type),
        )
        logger.info("Stream salvo no blob %s", blob_path)

    def upload_block_blob(self, blob_path: str, block_iter: Iterable[bytes]) -> None:
        """Envia um blob em blocos usando stage_block + commit_block_list."""
        blob_client = self.container_client.get_blob_client(blob_path)
        block_list = []

        for index, chunk in enumerate(block_iter, start=1):
            block_id = base64.b64encode(f"{index:06d}".encode()).decode()
            blob_client.stage_block(block_id=block_id, data=chunk)
            block_list.append(BlobBlock(block_id=block_id))
            logger.debug("Bloco %s stageado (%d bytes)", block_id, len(chunk))

        blob_client.commit_block_list(block_list)
        logger.info("Blob em blocos commitado em %s (%d blocos)", blob_path, len(block_list))
