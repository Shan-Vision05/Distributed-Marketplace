import time
import uuid
import threading
import sqlite3
import os
from concurrent import futures

import grpc
from common import marketplace_pb2, marketplace_pb2_grpc


DB_PATH = os.path.join(os.path.dirname(__file__), "customer.db")

product_channel = grpc.insecure_channel("10.128.0.5:7002")
product_stub = marketplace_pb2_grpc.ProductServiceStub(product_channel)


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS buyers (
            buyer_id   INTEGER PRIMARY KEY AUTOINCREMENT,
            username   TEXT NOT NULL UNIQUE,
            password   TEXT NOT NULL,
            saved_cart INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS sellers (
            seller_id     INTEGER PRIMARY KEY AUTOINCREMENT,
            username      TEXT NOT NULL UNIQUE,
            password      TEXT NOT NULL,
            items_sold    INTEGER NOT NULL DEFAULT 0,
            feedback_up   INTEGER NOT NULL DEFAULT 0,
            feedback_down INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS cart_items (
            buyer_id      INTEGER NOT NULL,
            item_category INTEGER NOT NULL,
            item_num      INTEGER NOT NULL,
            quantity      INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (buyer_id, item_category, item_num),
            FOREIGN KEY (buyer_id) REFERENCES buyers(buyer_id)
        );

        CREATE TABLE IF NOT EXISTS purchase_history (
            purchase_id   INTEGER PRIMARY KEY AUTOINCREMENT,
            buyer_id      INTEGER NOT NULL,
            item_category INTEGER NOT NULL,
            item_num      INTEGER NOT NULL,
            item_name     TEXT,
            quantity      INTEGER NOT NULL,
            price         REAL NOT NULL,
            purchased_at  TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (buyer_id) REFERENCES buyers(buyer_id)
        );
    """)
    conn.commit()
    conn.close()


init_db()

_tls = threading.local()
sessions = {}
session_lock = threading.Lock()
SESSION_TIMEOUT = 300  # 5 minutes


def get_db():
    if not hasattr(_tls, 'conn') or _tls.conn is None:
        conn = sqlite3.connect(DB_PATH, timeout=30)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA cache_size=-64000")
        conn.execute("PRAGMA temp_store=MEMORY")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.row_factory = sqlite3.Row
        _tls.conn = conn
    return _tls.conn


class CustomerServiceServicer(marketplace_pb2_grpc.CustomerServiceServicer):


    def _require_buyer_session(self, session_id, context):
        if not session_id:
            context.abort(grpc.StatusCode.UNAUTHENTICATED, "Missing session_id")
        with session_lock:
            session = sessions.get(session_id)
            if not session or session["role"] != "buyer":
                context.abort(grpc.StatusCode.UNAUTHENTICATED, "Invalid session")
            if time.time() - session.get("last_activity", 0) > SESSION_TIMEOUT:
                del sessions[session_id]
                context.abort(grpc.StatusCode.UNAUTHENTICATED, "Session expired")
            session["last_activity"] = time.time()
            return session["user_id"]


    def CreateAccount(self, request, context):
        role = request.role
        username = request.username
        password = request.password

        if not role or not username or not password:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Missing fields")

        db = get_db()
        try:
            if role == "buyer":
                cursor = db.execute(
                    "INSERT INTO buyers (username, password) VALUES (?, ?)",
                    (username, password),
                )
                db.commit()
                return marketplace_pb2.CreateAccountResponse(user_id=cursor.lastrowid)
            elif role == "seller":
                cursor = db.execute(
                    "INSERT INTO sellers (username, password) VALUES (?, ?)",
                    (username, password),
                )
                db.commit()
                return marketplace_pb2.CreateAccountResponse(user_id=cursor.lastrowid)
        except sqlite3.IntegrityError:
            context.abort(grpc.StatusCode.ALREADY_EXISTS, f"{role.capitalize()} already exists")

        context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Invalid role")

    def Login(self, request, context):
        role = request.role
        username = request.username
        password = request.password

        if not role or not username or not password:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Missing fields")

        db = get_db()
        if role == "buyer":
            row = db.execute(
                "SELECT buyer_id, password FROM buyers WHERE username = ?",
                (username,),
            ).fetchone()
            if not row or row["password"] != password:
                context.abort(grpc.StatusCode.UNAUTHENTICATED, "Invalid credentials")
            session_id = str(uuid.uuid4())
            with session_lock:
                sessions[session_id] = {
                    "role": "buyer",
                    "user_id": row["buyer_id"],
                    "username": username,
                    "last_activity": time.time(),
                }
            return marketplace_pb2.LoginResponse(session_id=session_id)

        elif role == "seller":
            row = db.execute(
                "SELECT seller_id, password FROM sellers WHERE username = ?",
                (username,),
            ).fetchone()
            if not row or row["password"] != password:
                context.abort(grpc.StatusCode.UNAUTHENTICATED, "Invalid credentials")
            session_id = str(uuid.uuid4())
            with session_lock:
                sessions[session_id] = {
                    "role": "seller",
                    "user_id": row["seller_id"],
                    "username": username,
                    "last_activity": time.time(),
                }
            return marketplace_pb2.LoginResponse(session_id=session_id)

        context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Invalid role")

    def ValidateSession(self, request, context):
        session_id = request.session_id
        if not session_id:
            context.abort(grpc.StatusCode.UNAUTHENTICATED, "Missing session_id")

        now = time.time()
        with session_lock:
            session = sessions.get(session_id)
            if not session:
                context.abort(grpc.StatusCode.UNAUTHENTICATED, "Invalid session")
            if now - session.get("last_activity", 0) > SESSION_TIMEOUT:
                del sessions[session_id]
                context.abort(grpc.StatusCode.UNAUTHENTICATED, "Session expired")
            session["last_activity"] = now
            return marketplace_pb2.ValidateSessionResponse(
                role=session["role"],
                user_id=session["user_id"],
                username=session.get("username", ""),
            )

    def Logout(self, request, context):
        session_id = request.session_id
        if not session_id:
            context.abort(grpc.StatusCode.UNAUTHENTICATED, "Missing session_id")

        with session_lock:
            session = sessions.get(session_id)
            if not session:
                context.abort(grpc.StatusCode.UNAUTHENTICATED, "Invalid session")
            role = session["role"]
            user_id = session["user_id"]
            del sessions[session_id]

        if role == "buyer":
            db = get_db()
            row = db.execute(
                "SELECT saved_cart FROM buyers WHERE buyer_id = ?", (user_id,)
            ).fetchone()
            if row is not None and not row["saved_cart"]:
                db.execute("DELETE FROM cart_items WHERE buyer_id = ?", (user_id,))
                db.commit()

        return marketplace_pb2.LogoutResponse()


    def AddItemToCart(self, request, context):
        session_id = request.session_id
        item_id = request.item_id
        quantity = request.quantity

        buyer_id = self._require_buyer_session(session_id, context)
        db = get_db()
        cat, num = item_id.category, item_id.num
        db.execute(
            """
            INSERT INTO cart_items (buyer_id, item_category, item_num, quantity)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(buyer_id, item_category, item_num)
            DO UPDATE SET quantity = quantity + excluded.quantity
            """,
            (buyer_id, cat, num, quantity),
        )
        db.commit()
        return marketplace_pb2.CartModifyResponse()

    def RemoveFromCart(self, request, context):
        session_id = request.session_id
        item_id = request.item_id
        quantity = request.quantity

        buyer_id = self._require_buyer_session(session_id, context)
        db = get_db()
        cat, num = item_id.category, item_id.num
        row = db.execute(
            "SELECT quantity FROM cart_items WHERE buyer_id=? AND item_category=? AND item_num=?",
            (buyer_id, cat, num),
        ).fetchone()
        if not row:
            context.abort(grpc.StatusCode.NOT_FOUND, "Item not in cart")
        if row["quantity"] <= quantity:
            db.execute(
                "DELETE FROM cart_items WHERE buyer_id=? AND item_category=? AND item_num=?",
                (buyer_id, cat, num),
            )
        else:
            db.execute(
                "UPDATE cart_items SET quantity = quantity - ? WHERE buyer_id=? AND item_category=? AND item_num=?",
                (quantity, buyer_id, cat, num),
            )
        db.commit()
        return marketplace_pb2.CartModifyResponse()

    def ClearCart(self, request, context):
        session_id = request.session_id
        buyer_id = self._require_buyer_session(session_id, context)
        db = get_db()
        db.execute("DELETE FROM cart_items WHERE buyer_id = ?", (buyer_id,))
        db.execute("UPDATE buyers SET saved_cart = 0 WHERE buyer_id = ?", (buyer_id,))
        db.commit()
        return marketplace_pb2.CartModifyResponse()

    def SaveCart(self, request, context):
        session_id = request.session_id
        buyer_id = self._require_buyer_session(session_id, context)
        db = get_db()
        db.execute("UPDATE buyers SET saved_cart = 1 WHERE buyer_id = ?", (buyer_id,))
        db.commit()
        return marketplace_pb2.CartModifyResponse()

    def GetCart(self, request, context):
        session_id = request.session_id
        buyer_id = self._require_buyer_session(session_id, context)
        db = get_db()
        rows = db.execute(
            "SELECT item_category, item_num, quantity FROM cart_items WHERE buyer_id = ?",
            (buyer_id,),
        ).fetchall()
        entries = []
        for row in rows:
            entries.append(
                marketplace_pb2.CartEntry(
                    item_id=marketplace_pb2.ItemId(
                        category=row["item_category"], num=row["item_num"]
                    ),
                    quantity=row["quantity"],
                )
            )
        return marketplace_pb2.GetCartResponse(items=entries)


    def UpdateSellerFeedback(self, request, context):
        seller_id = request.seller_id
        feedback_type = request.feedback_type

        if seller_id == 0 or feedback_type not in ("up", "down"):
            context.abort(
                grpc.StatusCode.INVALID_ARGUMENT,
                "Missing seller_id or invalid feedback_type",
            )

        db = get_db()
        if feedback_type == "up":
            cursor = db.execute(
                "UPDATE sellers SET feedback_up = feedback_up + 1 WHERE seller_id = ?",
                (seller_id,),
            )
        else:
            cursor = db.execute(
                "UPDATE sellers SET feedback_down = feedback_down + 1 WHERE seller_id = ?",
                (seller_id,),
            )
        if cursor.rowcount == 0:
            context.abort(grpc.StatusCode.NOT_FOUND, "Seller not found")
        db.commit()
        return marketplace_pb2.UpdateSellerFeedbackResponse()


    def GetBuyerPurchases(self, request, context):
        session_id = request.session_id
        buyer_id = self._require_buyer_session(session_id, context)
        db = get_db()
        rows = db.execute(
            "SELECT item_category, item_num, item_name, quantity, price, purchased_at "
            "FROM purchase_history WHERE buyer_id = ? ORDER BY purchased_at",
            (buyer_id,),
        ).fetchall()
        purchases = []
        for row in rows:
            purchases.append(
                marketplace_pb2.PurchaseRecord(
                    item_id=marketplace_pb2.ItemId(
                        category=row["item_category"], num=row["item_num"]
                    ),
                    item_name=row["item_name"],
                    quantity=row["quantity"],
                    price=float(row["price"]),
                    purchased_at=row["purchased_at"],
                )
            )
        return marketplace_pb2.GetBuyerPurchasesResponse(purchases=purchases)

    def GetSellerRating(self, request, context):
        session_id = request.session_id
        seller_id = request.seller_id

        if not session_id:
            context.abort(grpc.StatusCode.UNAUTHENTICATED, "Missing session_id")

        with session_lock:
            session = sessions.get(session_id)
            if not session:
                context.abort(grpc.StatusCode.UNAUTHENTICATED, "Invalid session")
            session["last_activity"] = time.time()
            session_role = session["role"]
            session_user_id = session["user_id"]

        db = get_db()
        if seller_id > 0:
            row = db.execute(
                "SELECT feedback_up, feedback_down FROM sellers WHERE seller_id = ?",
                (seller_id,),
            ).fetchone()
        elif session_role == "seller":
            row = db.execute(
                "SELECT feedback_up, feedback_down FROM sellers WHERE seller_id = ?",
                (session_user_id,),
            ).fetchone()
        else:
            context.abort(
                grpc.StatusCode.PERMISSION_DENIED,
                "Seller access required or provide seller_id",
            )
            return

        if not row:
            context.abort(grpc.StatusCode.NOT_FOUND, "Seller not found")

        return marketplace_pb2.GetSellerRatingResponse(
            feedback=marketplace_pb2.Feedback(
                up=row["feedback_up"], down=row["feedback_down"]
            )
        )

    def MakePurchase(self, request, context):
        session_id = request.session_id
        if not session_id:
            context.abort(grpc.StatusCode.UNAUTHENTICATED, "Missing session_id")

        with session_lock:
            session = sessions.get(session_id)
            if not session or session["role"] != "buyer":
                context.abort(grpc.StatusCode.UNAUTHENTICATED, "Invalid session")
            buyer_id = session["user_id"]
            session["last_activity"] = time.time()

        db = get_db()
        if not db.execute(
            "SELECT 1 FROM buyers WHERE buyer_id = ?", (buyer_id,)
        ).fetchone():
            context.abort(grpc.StatusCode.NOT_FOUND, "Buyer not found")

        cart_rows = db.execute(
            "SELECT item_category, item_num, quantity FROM cart_items WHERE buyer_id = ?",
            (buyer_id,),
        ).fetchall()

        if not cart_rows:
            context.abort(grpc.StatusCode.FAILED_PRECONDITION, "Cart is empty")

        cart_items = []
        for row in cart_rows:
            cat, num, qty = row["item_category"], row["item_num"], row["quantity"]
            try:
                item_resp = product_stub.GetItem(
                    marketplace_pb2.GetItemRequest(
                        item_id=marketplace_pb2.ItemId(category=cat, num=num)
                    )
                )
            except grpc.RpcError:
                context.abort(
                    grpc.StatusCode.NOT_FOUND,
                    f"Item {cat}-{num} not found",
                )
            item = item_resp.item
            if item.quantity < qty:
                context.abort(
                    grpc.StatusCode.FAILED_PRECONDITION,
                    f"Not enough stock for item {cat}-{num}",
                )
            cart_items.append(
                {
                    "category": cat,
                    "num": num,
                    "quantity": qty,
                    "name": item.name,
                    "price": item.price,
                }
            )

        for ci in cart_items:
            try:
                product_stub.UpdateUnitsForSale(
                    marketplace_pb2.UpdateUnitsRequest(
                        item_id=marketplace_pb2.ItemId(
                            category=ci["category"], num=ci["num"]
                        ),
                        quantity=-ci["quantity"],
                    )
                )
            except grpc.RpcError:
                context.abort(
                    grpc.StatusCode.INTERNAL,
                    f"Error updating stock for item {ci['category']}-{ci['num']}",
                )
            db.execute(
                """INSERT INTO purchase_history
                   (buyer_id, item_category, item_num, item_name, quantity, price)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    buyer_id,
                    ci["category"],
                    ci["num"],
                    ci["name"],
                    ci["quantity"],
                    ci["price"],
                ),
            )

        db.execute("DELETE FROM cart_items WHERE buyer_id = ?", (buyer_id,))
        db.execute(
            "UPDATE buyers SET saved_cart = 0 WHERE buyer_id = ?", (buyer_id,)
        )
        db.commit()
        return marketplace_pb2.MakePurchaseResponse(message="Purchase successful")


if __name__ == "__main__":
    server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=100),
        options=[
            ('grpc.max_concurrent_streams', 200),
            ('grpc.max_receive_message_length', 16 * 1024 * 1024),
        ]
    )
    marketplace_pb2_grpc.add_CustomerServiceServicer_to_server(
        CustomerServiceServicer(), server
    )
    server.add_insecure_port("0.0.0.0:7001")
    server.start()
    print("Customer DB gRPC Server on port 7001")
    server.wait_for_termination()