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
    print("\nSeller Menu")
    print("1. Create Account")
    print("2. Login")
    print("3. Register Item For Sale")
    print("4. Change Item Price")
    print("5. Update Units For Sale")
    print("6. Display Items For Sale")
    print("7. Get Seller Rating")
    print("8. Logout")
    print("0. Exit")


def main(host='127.0.0.1', port=7004):
    client = RESTClient(host, port)
    session_id = None

    print(f"Seller CLI connecting to {host}:{port}")

    while True:
        print_menu()
        choice = read_int("Choose an option: ")

        if choice == 0:
            print("Exiting")
            break

        if choice == 1:
            username = read_str("Username: ")
            password = read_str("Password: ")
            resp = client.post("seller/account", {
                "username": username,
                "password": password
            })
            print(resp)
            continue

        if choice == 2:
            username = read_str("Username: ")
            password = read_str("Password: ")
            resp = client.post("seller/login", {
                "username": username,
                "password": password
            })
            print(resp)
            if resp and resp.get("status") == "ok":
                session_id = resp.get("session_id")
                print("Logged in, session_id stored")
            continue

        if choice == 3:
            name = read_str("Item name: ")
            category = read_int("Category: ")
            keywords = read_str("Keywords (space separated): ").split()
            condition = read_str("Condition (new/used): ")
            price = read_float("Price: ")
            quantity = read_int("Quantity: ")
            resp = client.post("seller/items", {
                "session_id": session_id,
                "name": name,
                "category": category,
                "keywords": keywords,
                "condition": condition,
                "price": price,
                "quantity": quantity,
            })
            print(resp)
            continue

        if choice == 4:
            category = read_int("Item category: ")
            num = read_int("Item number: ")
            price = read_float("New price: ")
            resp = client.put("seller/items/price", {
                "session_id": session_id,
                "item_id": f"{category},{num}",
                "price": price
            })
            print(resp)
            continue

        if choice == 5:
            category = read_int("Item category: ")
            num = read_int("Item number: ")
            qty = read_int("Remove Quantity: ")
            resp = client.put("seller/items/quantity", {
                "session_id": session_id,
                "item_id": f"{category},{num}",
                "quantity": -1 * qty
            })
            print(resp)
            continue

        if choice == 6:
            resp = client.get("seller/items", params={
                "session_id": session_id
            })
            print(resp)
            continue

        if choice == 7:
            resp = client.get("seller/rating", params={
                "session_id": session_id
            })
            print(resp)
            continue

        if choice == 8:
            if session_id:
                resp = client.post("seller/logout", {
                    "session_id": session_id
                })
                print(resp)
                session_id = None
            else:
                print("Not logged in")
            continue

        print("Unknown option")


if __name__ == '__main__':
    host = '127.0.0.1'
    port = 7004
    if len(sys.argv) >= 2:
        host = sys.argv[1]
    if len(sys.argv) >= 3:
        port = int(sys.argv[2])
    main(host, port)
