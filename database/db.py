import os
import mysql.connector


def get_connection():
    return mysql.connector.connect(
        host=os.environ.get("DB_HOST"),
        user=os.environ.get("DB_USER"),
        password=os.environ.get("DB_PASSWORD"),
        database=os.environ.get("DB_NAME"),
        port=int(os.environ.get("DB_PORT", 3306)),
        ssl_disabled=False,
        use_pure=True
    )


def save_pnr_data(pnr, data):
    conn = get_connection()
    cursor = conn.cursor()

    query = """
    INSERT INTO pnr_data
    (pnr_number, train_number, train_name, from_station, to_station,
     journey_date, booking_status, current_status)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """

    train = data["data"]

    passenger_list = train.get("passengerList")

    if passenger_list is None:
        passenger_list = train.get("passengerStatus")

    if not passenger_list:
        raise ValueError("No passenger data found for PNR")

    passenger = passenger_list[0]

    values = (
        pnr,
        train.get("trainNo"),
        train.get("trainName"),
        train.get("sourceStation"),
        train.get("destinationStation"),
        train.get("journeyDate"),
        passenger.get("bookingStatus"),
        passenger.get("currentStatus")
    )

    cursor.execute(query, values)
    conn.commit()

    cursor.close()
    conn.close()