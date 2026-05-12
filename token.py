import base64
import json
import requests
from datetime import datetime, timedelta

TOKEN_URL = "https://api.receitafederal.gov.br/token"

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
    
    ##Realiza a chamada da API da Receita Federal para obter o token

    try:
        auth_header = generate_basic_auth(client_id, client_secret)
        headers = {
            "Content-Type": "application/json",
            "Authorization": auth_header
        }

        paylod = {
            "grant_type": "client_credentials"
        }

        response = requests.post(
            TOKEN_URL, 
            headers=headers, 
            json=paylod,
            timeout=30)
        
        ## Log 
        print(f"Status code: {response.status_code}")

        if response.status_code != 200:
            raise Exception(f"Erro ao obter token da Receita: {response.status_code} - {response.text}")
        
        token_data = response.json()
        token_data["generated_at"] = datetime.now().isoformat()
        return token_data
    
    except Exception as e:
        raise RuntimeError(f"Falha ao obter token da Receita: {str(e)}")
    


## Realizando chamada API Receita Federal e obtendo o Token
token_response = get_access_token()

print("Token obtido com sucesso:")
print(json.dumps(token_response, indent=2))

# Extrair o token de acesso
access_token = token_response.get("access_token")
if not access_token:
    raise RuntimeError("Token de acesso não encontrado na resposta.")

# URL da API de apuração CBS
APURACAO_URL = "https://api.receitafederal.gov.br/rtc/apuracao-cbs/v1/02558157"

# Headers para a chamada de apuração
headers_apuracao = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {access_token}"
}

# Payload para a chamada de apuração
payload_apuracao = {
    "urlRetorno": "https://colonize-relative-discuss.ngrok-free.dev/webhook"
}

# Fazer a chamada POST para a API de apuração
try:
    response_apuracao = requests.post(
        APURACAO_URL,
        headers=headers_apuracao,
        json=payload_apuracao,
        timeout=30
    )
    
    print(f"Status code da apuração: {response_apuracao.status_code}")
    
    if response_apuracao.status_code == 200:
        print("Apuração solicitada com sucesso.")
        print("Resposta:")
        print(json.dumps(response_apuracao.json(), indent=2))
    else:
        print(f"Erro na apuração: {response_apuracao.status_code} - {response_apuracao.text}")
        
except Exception as e:
    print(f"Falha ao chamar API de apuração: {str(e)}")

