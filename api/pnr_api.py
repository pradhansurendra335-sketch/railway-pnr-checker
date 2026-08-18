import requests
API_KEY = "c196734e4fmsh7b6888436a0d0c1p1e4b3djsn14beb37a811f"
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