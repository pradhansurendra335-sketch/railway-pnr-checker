import os
from dotenv import load_dotenv

load_dotenv()  # reads .env in local development; no-op if the file doesn't exist (e.g. on Vercel)

from flask import Flask, render_template, request, session, jsonify, redirect, url_for

from api.pnr_api import get_pnr_status
from api.train_status_api import get_live_train_status
from database.db import (
    save_pnr_data,
    update_pnr_data,
    delete_pnr_data
)
from i18n import get_text, SUPPORTED_LANGUAGES, DEFAULT_LANGUAGE
from chatbot.bot import get_bot_reply

app = Flask(__name__)


def enrich_running_status(data):
    """
    Adds a few human-readable fields the template uses. The API returns two
    different shapes depending on the train's state:
      - "Not yet departed" shape: has 'title' / 'new_message'.
      - "En route" shape: has 'current_station_name', 'delay', 'distance_from_source', etc.
    """
    if not data.get("success") or not data.get("data"):
        return data

    d = data["data"]

    if d.get("journey_time"):
        total_minutes = d["journey_time"]
        d["journey_time_display"] = f"{total_minutes // 60}h {total_minutes % 60}m"

    if d.get("current_station_name"):
        # En route -- build a progress percentage and a plain-English delay line.
        if d.get("total_distance"):
            d["progress_percent"] = round(
                min(100, (d.get("distance_from_source", 0) / d["total_distance"]) * 100)
            )

        delay = d.get("delay", 0)
        if delay and delay > 0:
            d["delay_text"] = f"Running {delay} min late"
        else:
            d["delay_text"] = "Running on time"

        # Only keep real upcoming stops (API includes some blank placeholder
        # entries and deeply nested 'non_stops' we don't want to show).
        upcoming = [
            s for s in d.get("upcoming_stations", [])
            if s.get("station_name") and s.get("sta")
        ][:5]
        d["upcoming_stations_clean"] = upcoming

    return data

# Needed for session (used to remember the selected language per visitor).
# Set FLASK_SECRET_KEY in your environment for production; this fallback is
# only fine for local development.
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-change-me")


# ---------- Language handling ----------

@app.context_processor
def inject_i18n():
    """Makes t(key), current_lang, and SUPPORTED_LANGUAGES available in every template."""
    lang = session.get("lang", DEFAULT_LANGUAGE)
    return {
        "t": lambda key: get_text(lang, key),
        "current_lang": lang,
        "supported_languages": SUPPORTED_LANGUAGES,
    }


@app.route('/set-language/<lang_code>')
def set_language(lang_code):
    if lang_code in SUPPORTED_LANGUAGES:
        session["lang"] = lang_code

    # /result and /running-status/result only accept POST (they need a PNR or
    # train number submitted via a form), so we can't just redirect back to
    # them with a plain GET -- that would 405. Instead, re-run the same
    # lookup (remembered in the session) under the new language.
    referrer = request.referrer or ""

    if "/result" in referrer and "/running-status" not in referrer and session.get("last_pnr"):
        data = get_pnr_status(session["last_pnr"])
        return render_template('result.html', data=data, pnr=session["last_pnr"])

    if "/running-status/result" in referrer and session.get("last_train_no"):
        data = get_live_train_status(session["last_train_no"], start_day=session.get("last_start_day", "0"))
        data = enrich_running_status(data)
        return render_template('running_status.html', data=data, train_no=session["last_train_no"])

    return redirect(url_for('home'))


# ---------- PNR status ----------

@app.route('/')
def home():
    return render_template('index.html')


@app.route('/result', methods=['POST'])
def result():
    pnr = request.form['pnr']

    print("API CALLED")

    data = get_pnr_status(pnr)

    print("API RESPONSE:")
    print(data)

    session["last_pnr"] = pnr  # remembered so language-switching can redisplay this result

    # Save successful real PNR searches to MySQL
    if data.get("success"):
        try:
            save_pnr_data(pnr, data)
            print("PNR SAVED TO DATABASE")
        except Exception as e:
            print("DATABASE ERROR:", e)

    return render_template(
        'result.html',
        data=data,
        pnr=pnr
    )


@app.route('/update', methods=['POST'])
def update():
    pnr = request.form['pnr']
    current_status = request.form['current_status']

    try:
        update_pnr_data(pnr, current_status)
        print("PNR UPDATED SUCCESSFULLY")

        return "PNR updated successfully!"

    except Exception as e:
        print("UPDATE ERROR:", e)
        return "Error updating PNR."


@app.route('/delete', methods=['POST'])
def delete():
    pnr = request.form['pnr']

    try:
        delete_pnr_data(pnr)
        print("PNR DELETED SUCCESSFULLY")

        return "PNR deleted successfully!"

    except Exception as e:
        print("DELETE ERROR:", e)
        return "Error deleting PNR."


# ---------- Live train running status ----------

@app.route('/running-status')
def running_status_form():
    return render_template('running_status.html', data=None, train_no=None)


@app.route('/running-status/result', methods=['POST'])
def running_status_result():
    train_no = request.form['train_no']
    start_day = request.form.get('start_day', '0')

    print("RUNNING STATUS API CALLED")

    data = get_live_train_status(train_no, start_day=start_day)

    print("RUNNING STATUS API RESPONSE:")
    print(data)

    session["last_train_no"] = train_no  # remembered so language-switching can redisplay this result
    session["last_start_day"] = start_day

    data = enrich_running_status(data)

    return render_template(
        'running_status.html',
        data=data,
        train_no=train_no
    )


# ---------- Chatbot ----------

@app.route('/chat')
def chat_page():
    return render_template('chat.html')


@app.route('/api/chat', methods=['POST'])
def chat_api():
    payload = request.get_json(silent=True) or {}
    message = payload.get("message", "")
    history = payload.get("history", [])

    reply = get_bot_reply(message, history=history)

    return jsonify({"reply": reply})


if __name__ == '__main__':
    # threaded=True lets the dev server handle more than one request at once
    # (e.g. the chatbot and another page load, or two chat messages sent close
    # together) instead of queuing them one-by-one, which can cause timeouts.
    app.run(debug=True, threaded=True)
