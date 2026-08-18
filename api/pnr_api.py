import requests
from config import API_KEY
API_HOST = "irctc-indian-railway-pnr-status.p.rapidapi.com"


def get_pnr_status(pnr):
    url = f"https://{API_HOST}/getPNRStatus/{pnr}"

    headers = {
        "x-rapidapi-key": API_KEY,
        "x-rapidapi-host": API_HOST,
        "Content-Type": "application/json"
    }

    response = requests.get(url, headers=headers)

    return response.json()