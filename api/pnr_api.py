import os
import requests

API_KEY = os.environ.get("RAPIDAPI_KEY")
API_HOST = "irctc-indian-railway-pnr-status.p.rapidapi.com"


def get_pnr_status(pnr):
    url = f"https://{API_HOST}/getPNRStatus/{pnr}"

    headers = {
        "x-rapidapi-key": API_KEY,
        "x-rapidapi-host": API_HOST,
        "Content-Type": "application/json"
    }

    try:
        response = requests.get(url, headers=headers, timeout=10)
    except requests.exceptions.Timeout:
        return {
            "success": False,
            "message": "The PNR status service took too long to respond. Please try again."
        }
    except requests.exceptions.RequestException as e:
        return {
            "success": False,
            "message": f"Could not reach the PNR status service: {e}"
        }

    # Non-2xx response (bad API key, rate limit, invalid PNR, service down, etc.)
    if not response.ok:
        try:
            detail = response.json().get("message", response.text)
        except ValueError:
            detail = response.text

        return {
            "success": False,
            "message": f"PNR status service returned an error (HTTP {response.status_code}): {detail}"
        }

    try:
        data = response.json()
    except ValueError:
        return {
            "success": False,
            "message": "PNR status service returned an unreadable response."
        }

    # Defensive: make sure the shape matches what app.py/result.html expect
    if "success" not in data:
        data["success"] = bool(data.get("data"))

    return data