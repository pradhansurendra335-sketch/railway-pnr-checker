import os
import re
import json
import requests

from api.pnr_api import get_pnr_status
from api.train_status_api import get_live_train_status

PNR_PATTERN = re.compile(r"(?<!\d)\d{10}(?!\d)")  # exactly 10 digits, even if letters touch it (e.g. "2163956094is")
TRAIN_PATTERN = re.compile(r"\btrain\s*(?:no\.?|number)?\s*[:#]?\s*(\d{4,5})\b", re.IGNORECASE)

# Using Groq's free API (OpenAI-compatible format, extremely fast inference).
# Get a free key with no credit card at https://console.groq.com -> API Keys.
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")

SYSTEM_PROMPT = (
    "You are a friendly, concise help assistant embedded in an Indian Railways "
    "PNR status checker website. You can explain PNR status terms (CNF, WL, "
    "RAC, current status codes), how to use the site, and general Indian "
    "Railways FAQ. Keep answers short (2-4 sentences) and plain, "
    "non-technical language. Do NOT use markdown formatting (no **, no #, no "
    "bullet lists, no backticks) -- write in plain sentences only, since your "
    "reply is shown in a simple chat bubble that does not render markdown."
)

DATA_SYSTEM_PROMPT = (
    "You are the same railway help assistant, but the user's message included "
    "a PNR or train number, so the real app already looked it up for you. "
    "Below is the REAL, CURRENT data for that lookup, as JSON. Use ONLY this "
    "data to answer -- do not invent or guess any detail not present here. "
    "Give a FULL summary covering every relevant field present in the data, "
    "not just the narrow thing the user asked -- they want the complete "
    "picture in one go. For a PNR: mention the train name and number, source "
    "and destination stations, journey date, and for EACH passenger their "
    "booking status, current status, coach and berth. For a train running "
    "status: mention the train name and number, where it currently is (or "
    "its scheduled departure status if not yet departed), how many "
    "minutes late or on time it is, distance covered vs total distance, the "
    "next stopping station and its ETA, and whether a pantry car is "
    "available. Leave out only fields that are missing or null in the data. "
    "If success is false, apologize briefly and explain the message field in "
    "plain words, don't show raw JSON. Write in plain, clear sentences (a "
    "short paragraph is fine, it does not need to be ultra short), no "
    "markdown formatting (no **, no #, no bullet lists, no "
    "backticks).\n\nREAL DATA:\n{data}"
)


def _lookup_pnr(pnr):
    result = get_pnr_status(pnr)
    if not result.get("success"):
        return {"success": False, "message": result.get("message", "Could not fetch PNR status.")}

    d = result.get("data", {})
    passengers = d.get("passengerList", [])
    return {
        "success": True,
        "pnr": pnr,
        "train_name": d.get("trainName"),
        "train_number": d.get("trainNumber"),
        "from": d.get("sourceStation"),
        "to": d.get("destinationStation"),
        "date_of_journey": d.get("dateOfJourney"),
        "passengers": [
            {
                "passenger_number": p.get("passengerSerialNumber"),
                "booking_status": p.get("bookingStatus"),
                "current_status": p.get("currentStatus"),
                "coach": p.get("currentCoachId"),
                "berth": p.get("currentBerthNo"),
            }
            for p in passengers
        ],
    }


def _lookup_running_status(train_no):
    result = get_live_train_status(train_no, start_day="0")
    if not result.get("success"):
        return {"success": False, "message": result.get("message", "Could not fetch running status.")}

    d = result.get("data", {})
    if d.get("current_station_name"):
        return {
            "success": True,
            "train_number": train_no,
            "train_name": d.get("train_name"),
            "currently_near": d.get("current_station_name"),
            "delay_minutes": d.get("delay", 0),
            "distance_covered_km": d.get("distance_from_source"),
            "total_distance_km": d.get("total_distance"),
            "next_stop": (d.get("next_stoppage_info") or {}).get("next_stoppage"),
            "next_stop_eta": (d.get("next_stoppage_info") or {}).get("next_stoppage_time_diff"),
        }
    else:
        return {
            "success": True,
            "train_number": train_no,
            "train_name": d.get("train_name"),
            "status_note": d.get("title"),
            "status_detail": d.get("new_message"),
            "scheduled_departure": d.get("std"),
        }


def _find_number_in_text(text):
    """Returns ('pnr', value) or ('train', value) if found in this one text, else None."""
    pnr_match = PNR_PATTERN.search(text)
    if pnr_match:
        return ("pnr", pnr_match.group())

    train_match = TRAIN_PATTERN.search(text)
    if train_match:
        return ("train", train_match.group(1))

    return None


def _detect_and_fetch(message, history=None):
    """
    Deterministically checks for a PNR (10 digits) or train number (after the
    word 'train') and fetches real data directly -- rather than relying on
    the AI to decide to call a tool, which some models (including the one
    used here) can unreliably skip even when relevant.

    Checks the CURRENT message first. If that has no number (e.g. a follow-up
    question like "what train is it?" after already giving the PNR earlier),
    it looks back through the conversation history for the most recent PNR or
    train number the user mentioned, so follow-ups keep working.

    Returns None if no number was found anywhere.
    """
    found = _find_number_in_text(message)

    if found is None and history:
        for turn in reversed(history):
            if turn.get("role") == "user":
                found = _find_number_in_text(turn.get("content", ""))
                if found:
                    break

    if found is None:
        return None

    kind, value = found
    if kind == "pnr":
        return _lookup_pnr(value)
    return _lookup_running_status(value)


def _call_groq(messages):
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": GROQ_MODEL,
        "messages": messages,
        "max_tokens": 600,  # higher now since full-summary answers can run longer
        "temperature": 0.4,
    }
    return requests.post(GROQ_URL, headers=headers, json=payload, timeout=20)


def get_bot_reply(message, history=None):
    """
    history: optional list of {"role": "user"|"assistant", "content": "..."}
    from earlier turns in this chat session, oldest first.
    """
    if not GROQ_API_KEY:
        return (
            "Chat help isn't configured yet -- a GROQ_API_KEY environment "
            "variable needs to be set on the server for this feature to work. "
            "Get a free key at console.groq.com (no credit card needed)."
        )

    if not message or not message.strip():
        return "Please type a question."

    message = message.strip()
    real_data = _detect_and_fetch(message, history=history)

    if real_data is not None:
        system_prompt = DATA_SYSTEM_PROMPT.format(data=json.dumps(real_data))
    else:
        system_prompt = SYSTEM_PROMPT

    messages = [{"role": "system", "content": system_prompt}]
    if history:
        messages.extend(history[-10:])  # keep recent context only
    messages.append({"role": "user", "content": message})

    try:
        response = _call_groq(messages)
    except requests.exceptions.Timeout:
        return "The chat assistant took too long to respond. Please try again."
    except requests.exceptions.RequestException as e:
        return f"Could not reach the chat assistant: {e}"

    if not response.ok:
        try:
            detail = response.json().get("error", {}).get("message", response.text)
        except ValueError:
            detail = response.text
        return f"Chat assistant error (HTTP {response.status_code}): {detail}"

    try:
        data = response.json()
        content = data["choices"][0]["message"].get("content")
        return (content or "").strip() or "Sorry, I didn't get a response. Please try again."
    except (ValueError, KeyError, IndexError):
        return "Sorry, I couldn't understand the assistant's response. Please try again."
