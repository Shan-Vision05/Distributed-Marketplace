import sys
from common.rest_client import RESTClient


def read_str(prompt: str) -> str:
    return input(prompt).strip()


def read_int(prompt: str) -> int:
    while True:
        try:
            return int(input(prompt).strip())
        except ValueError:
            print("Please enter a valid integer.")


def read_float(prompt: str) -> float:
    while True:
        try:
            return float(input(prompt).strip())
        except ValueError:
            print("Please enter a valid number.")


def print_menu():
    print("\nBuyer Menu")
    print("1. Create Account")
    print("2. Login")
    print("3. Search Items")
    print("4. Get Item")
    print("5. Add Item to Cart")
    print("6. Remove Item from Cart")
    print("7. View Cart")
    print("8. Clear Cart")
    print("9. View Purchases")
    print("10. Get Seller Rating")
    print("11. Provide Feedback")
    print("12. Logout")
    print("13. Save Cart")
    print("14. Make Purchase")
    print("0. Exit")


def main(host='127.0.0.1', port=7003):
    client = RESTClient(host, port)
    session_id = None

    print(f"Buyer CLI connecting to {host}:{port}")

    while True:
        print_menu()
        choice = read_int("Choose an option: ")

        if choice == 0:
            print("Exiting")
            break

        if choice == 1:
            username = read_str("Username: ")
            password = read_str("Password: ")
            resp = client.post("buyer/account", {
                "username": username,
                "password": password
            })
            print(resp)
            continue

        if choice == 2:
            username = read_str("Username: ")
            password = read_str("Password: ")
            resp = client.post("buyer/login", {
                "username": username,
                "password": password
            })
            print(resp)
            if resp and resp.get("status") == "ok":
                session_id = resp.get("session_id")
                print("Logged in, session_id stored")
            continue

        if choice == 3:
            category = read_int("Category: ")
            keywords = read_str("Keywords (space separated): ").split()
            resp = client.get("product/items/search", params={
                "category": category,
                "keywords": ",".join(keywords),
                "session_id": session_id
            })
            print(resp)
            continue

        if choice == 4:
            category = read_int("Item category: ")
            num = read_int("Item number: ")
            resp = client.get("product/items/get", params={
                "item_id": f"{category},{num}",
                "session_id": session_id
            })
            print(resp)
            continue

        if choice == 5:
            category = read_int("Item category: ")
            num = read_int("Item number: ")
            qty = read_int("Quantity: ")
            resp = client.post("buyer/cart/add", {
                "item_id": f"{category},{num}",
                "quantity": qty,
                "session_id": session_id
            })
            print(resp)
            continue

        if choice == 6:
            category = read_int("Item category: ")
            num = read_int("Item number: ")
            qty = read_int("Quantity: ")
            resp = client.delete("buyer/cart/remove", params={
                "item_id": f"{category},{num}",
                "quantity": qty,
                "session_id": session_id
            })
            print(resp)
            continue

        if choice == 7:
            resp = client.get("buyer/cart", params={
                "session_id": session_id
            })
            print(resp)
            continue

        if choice == 8:
            resp = client.delete("buyer/cart/clear", params={
                "session_id": session_id
            })
            print(resp)
            continue

        if choice == 9:
            resp = client.get("buyer/purchases", params={
                "session_id": session_id
            })
            print(resp)
            continue

        if choice == 10:
            seller_id = read_int("Seller ID: ")
            resp = client.get("seller/rating", params={
                "seller_id": seller_id,
                "session_id": session_id
            })
            print(resp)
            continue

        if choice == 11:
            category = read_int("Item category: ")
            num = read_int("Item number: ")
            feedback_type = read_str("Feedback (up/down): ")
            resp = client.post("buyer/feedback", {
                "item_id": f"{category},{num}",
                "feedback_type": feedback_type,
                "session_id": session_id
            })
            print(resp)
            continue

        if choice == 12:
            if session_id:
                resp = client.post("buyer/logout", {
                    "session_id": session_id
                })
                print(resp)
                session_id = None
            else:
                print("Not logged in")
            continue

        if choice == 13:
            resp = client.post("buyer/cart/save", {
                "session_id": session_id
            })
            print(resp)
            continue

        if choice == 14:
            name = read_str("Cardholder name: ")
            card_number = read_str("Card number (16 digits): ")
            exp_month = read_str("Expiration month (1-12): ")
            exp_year = read_str("Expiration year (e.g. 2026): ")
            cvv = read_str("CVV (3 digits): ")
            resp = client.post("buyer/purchase", {
                "session_id": session_id,
                "name": name,
                "card_number": card_number,
                "exp_month": exp_month,
                "exp_year": exp_year,
                "cvv": cvv,
            })
            print(resp)
            continue

        print("Unknown option")


if __name__ == '__main__':
    host = '34.71.160.216'
    port = 7003
    if len(sys.argv) >= 2:
        host = sys.argv[1]
    if len(sys.argv) >= 3:
        port = int(sys.argv[2])
    main(host, port)
