from flask import Flask, request, jsonify
import routeros_api
import random
import string

app = Flask(__name__)

ROUTER_IP = "10.120.0.1"
ROUTER_USER = "voucherbot"
ROUTER_PASS = "vsadikv+-72345"

def random_user():
    return ''.join(
        random.choices(
            string.ascii_uppercase + string.digits,
            k=8
        )
    )

def random_pass():
    return ''.join(
        random.choices(
            string.digits,
            k=6
        )
    )

def create_voucher(profile):

    connection = routeros_api.RouterOsApiPool(
        host=ROUTER_IP,
        username=ROUTER_USER,
        password=ROUTER_PASS,
        port=8728,
        plaintext_login=True
    )

    api = connection.get_api()

    hotspot = api.get_resource(
        '/ip/hotspot/user'
    )

    user = random_user()
    password = random_pass()

    hotspot.add(
        name=user,
        password=password,
        profile=profile
    )

    connection.disconnect()

    return {
        "username": user,
        "password": password,
        "profile": profile
    }

@app.route("/")
def home():
    return "WiFi Hat Backend OK"

@app.route("/voucher", methods=["POST"])
def voucher():

    data = request.json
    profile = data.get("profile")

    result = create_voucher(profile)

    return jsonify(result)

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5000
    )