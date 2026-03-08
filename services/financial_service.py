import random
import time
from spyne import Application, rpc, ServiceBase, Unicode
from spyne.protocol.soap import Soap11
from spyne.server.wsgi import WsgiApplication
from wsgiref.simple_server import make_server


REQUIRED_FIELDS = ['username', 'card_number', 'exp_month', 'exp_year', 'cvv', 'name']


def validate_payment_request(request):

    if not isinstance(request, dict):
        return False, "Request must be a JSON object"

    for field in REQUIRED_FIELDS:
        if field not in request or request[field] is None or str(request[field]).strip() == "":
            return False, f"Missing or empty required field: {field}"

    card_number = str(request["card_number"])
    if len(card_number) != 16 or not card_number.isdigit():
        return False, "Invalid card number: must be exactly 16 digits"

    cvv = str(request["cvv"])
    if len(cvv) != 3 or not cvv.isdigit():
        return False, "Invalid CVV: must be exactly 3 digits"

    try:
        exp_month = int(request["exp_month"])
        exp_year = int(request["exp_year"])
    except (ValueError, TypeError):
        return False, "Invalid expiration date: month and year must be integers"

    if not (1 <= exp_month <= 12):
        return False, "Invalid expiration month: must be between 1 and 12"

    current = time.localtime()
    if exp_year < current.tm_year or \
       (exp_year == current.tm_year and exp_month < current.tm_mon):
        return False, "Card expired or invalid expiration date"

    name = request.get("name")
    if not name or not str(name).strip():
        return False, "Missing cardholder name"

    return True, None


def simulate_payment_processing():
    return "approved" if random.random() < 0.9 else "declined"


class FinancialTransactionService(ServiceBase):
    @rpc(Unicode, Unicode, Unicode, Unicode, Unicode, Unicode, _returns=Unicode)
    def process_payment(ctx, username, card_number, exp_month, exp_year, cvv, name):
        request = {
            "username": username,
            "card_number": card_number,
            "exp_month": exp_month,
            "exp_year": exp_year,
            "cvv": cvv,
            "name": name
        }
        is_valid, error_message = validate_payment_request(request)

        if not is_valid:
            return f"error: {error_message}"

        payment_status = simulate_payment_processing()
        return payment_status

app = Application(
    [FinancialTransactionService],
    tns = "financial.transaction.service",
    in_protocol = Soap11(),
    out_protocol = Soap11()
)

wsgi_app = WsgiApplication(app)


if __name__ == "__main__":
    server = make_server("0.0.0.0", 7005, wsgi_app)
    print("Financial service running on port 7005")
    server.serve_forever()