import os
import requests

API_KEY = os.environ.get("RAPIDAPI_KEY")
RUNNING_STATUS_HOST = "irctc1.p.rapidapi.com"


def get_live_train_status(train_no, start_day=0):
    """
    Fetch live running status for a train using the IRCTCAPI 'irctc1' product
    on RapidAPI (https://rapidapi.com/IRCTCAPI/api/irctc1/).

    NOTE: This is a *separate* RapidAPI listing from the PNR-status API already
    used in this project. Your existing RAPIDAPI_KEY (account key) will work,
    but you must separately subscribe to "irctc1" (IRCTCAPI) on RapidAPI first
    -- otherwise you'll get a 403. Free tier is limited to a small number of
    calls/month, so check your quota before relying on this in production.

    start_day: 0 = today, 1 = yesterday, -1 = tomorrow (per the train's
    scheduled departure date). Confirm exact parameter behaviour against the
    live "Test Endpoint" panel on RapidAPI, since providers occasionally
    change parameter names/behaviour without notice.
    """
    if not train_no or not train_no.isdigit():
        return {
            "success": False,
            "message": "Please enter a valid train number (digits only)."
        }

    url = f"https://{RUNNING_STATUS_HOST}/api/v1/liveTrainStatus"

    headers = {
        "x-rapidapi-key": API_KEY,
        "x-rapidapi-host": RUNNING_STATUS_HOST,
    }

    params = {
        "trainNo": train_no,
        "startDay": start_day,
    }

    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
    except requests.exceptions.Timeout:
        return {
            "success": False,
            "message": "The train status service took too long to respond. Please try again."
        }
    except requests.exceptions.RequestException as e:
        return {
            "success": False,
            "message": f"Could not reach the train status service: {e}"
        }

    if not response.ok:
        try:
            detail = response.json().get("message", response.text)
        except ValueError:
            detail = response.text

        return {
            "success": False,
            "message": f"Train status service returned an error (HTTP {response.status_code}): {detail}"
        }

    try:
        data = response.json()
    except ValueError:
        return {
            "success": False,
            "message": "Train status service returned an unreadable response."
        }

    if "success" not in data:
        data["success"] = bool(data.get("data"))

    return data
