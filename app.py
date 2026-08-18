from flask import Flask, render_template, request
from api.pnr_api import get_pnr_status
from database.db import save_pnr_data

app = Flask(__name__)


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


if __name__ == '__main__':
    app.run(debug=True)