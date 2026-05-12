import base64
import json
import logging
import requests
from datetime import datetime

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("token_service")

TOKEN_URL = "https://api.receitafederal.gov.br/token"
APURACAO_URL = "https://api.receitafederal.gov.br/rtc/apuracao-cbs/v1/02558157"

client_id = "gmX2kvgBXg4Ty3bco0MlCWY9xfyDwpS9"
client_secret = "T8NJ4rnhXwIxZE0qxwb3cvi9Do5KdhU8"

if not client_id or not client_secret:
    raise Exception("Please set your client_id and client_secret.")


def generate_basic_auth(client_id: str, client_secret: str) -> str:
    
    ##Gera o header Authorization Basic em Base64

    credentials = f"{client_id}:{client_secret}"
    encoded_credentials = base64.b64encode(credentials.encode("utf-8")).decode("utf-8")
    return f"Basic {encoded_credentials}"


def get_access_token() -> str:
    """Realiza a chamada da API da Receita Federal para obter o token de acesso."""

    try:
        auth_header = generate_basic_auth(client_id, client_secret)
        headers = {
            "Content-Type": "application/json",
            "Authorization": auth_header,
        }

        payload = {
            "grant_type": "client_credentials"
        }

        response = requests.post(TOKEN_URL, headers=headers, json=payload, timeout=30)
        logger.info(f"Status code do token: {response.status_code}")

        if response.status_code != 200:
            raise Exception(f"Erro ao obter token da Receita: {response.status_code} - {response.text}")

        token_data = response.json()
        access_token = token_data.get("access_token")
        if not access_token:
            raise RuntimeError("Token de acesso não encontrado na resposta da API de token.")

        logger.info("Token obtido com sucesso")
        return access_token
    except Exception as e:
        logger.exception(f"Falha ao obter token da Receita: {str(e)}")
        raise RuntimeError(f"Falha ao obter token da Receita: {str(e)}")
    


def request_apuracao(url_retorno: str) -> dict:
    """Faz a chamada à API de apuração usando o token de acesso."""
    try:
        access_token = get_access_token()
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {access_token}",
        }
        payload = {
            "urlRetorno": url_retorno
        }

        response = requests.post(APURACAO_URL, headers=headers, json=payload, timeout=30)
        logger.info(f"Status code da apuração: {response.status_code}")

        try:
            response_data = response.json()
        except ValueError:
            response_data = {"text": response.text}

        if response.status_code != 200:
            logger.error(f"Erro ao chamar API de apuração: {response.status_code} - {response.text}")
            raise RuntimeError(
                f"Erro ao chamar API de apuração: {response.status_code} - {response.text}"
            )

        logger.info("Apuração solicitada com sucesso")
        return response_data
    except Exception as e:
        logger.exception(f"Falha ao chamar API de apuração: {str(e)}")
        raise


if __name__ == "__main__":
    logger.info("Obtendo token de acesso...")
    try:
        token = get_access_token()
        logger.info("Token obtido com sucesso.")
        logger.info(json.dumps({"access_token": token}, indent=2))

        logger.info("Chamando API de apuração...")
        apuracao_result = request_apuracao("https://colonize-relative-discuss.ngrok-free.dev/webhook")
        logger.info("Resposta da apuração: %s", json.dumps(apuracao_result, indent=2))
    except Exception as e:
        logger.error(f"Erro na execução principal: {str(e)}")

