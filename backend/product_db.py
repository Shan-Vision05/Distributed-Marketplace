import threading
import sqlite3
import json
import os
from concurrent import futures

import grpc
from common import marketplace_pb2, marketplace_pb2_grpc


DB_PATH = os.path.join(os.path.dirname(__file__), "product.db")

customer_channel = grpc.insecure_channel("10.128.0.4:7001")
customer_stub = marketplace_pb2_grpc.CustomerServiceStub(customer_channel)


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS items (
            category      INTEGER NOT NULL,
            num           INTEGER NOT NULL,
            name          TEXT NOT NULL,
            keywords      TEXT NOT NULL DEFAULT '[]',
            condition     TEXT NOT NULL,
            price         REAL NOT NULL,
            quantity      INTEGER NOT NULL DEFAULT 0,
            seller_id     INTEGER NOT NULL,
            feedback_up   INTEGER NOT NULL DEFAULT 0,
            feedback_down INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (category, num)
        );

        CREATE INDEX IF NOT EXISTS idx_items_seller_id ON items(seller_id);

        CREATE TABLE IF NOT EXISTS item_id_counters (
            category  INTEGER PRIMARY KEY,
            next_num  INTEGER NOT NULL DEFAULT 1
        );
    """)
    conn.commit()
    conn.close()


init_db()

_tls = threading.local()


def get_db():
    if not hasattr(_tls, 'conn') or _tls.conn is None:
        conn = sqlite3.connect(DB_PATH, timeout=30)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA cache_size=-64000")
        conn.execute("PRAGMA temp_store=MEMORY")
        conn.row_factory = sqlite3.Row
        _tls.conn = conn
    return _tls.conn


def _row_to_item(row):
    return marketplace_pb2.Item(
        item_id=marketplace_pb2.ItemId(category=row["category"], num=row["num"]),
        name=row["name"],
        category=row["category"],
        keywords=json.loads(row["keywords"]),
        condition=row["condition"],
        price=float(row["price"]),
        quantity=int(row["quantity"]),
        seller_id=int(row["seller_id"]),
        feedback=marketplace_pb2.Feedback(
            up=int(row["feedback_up"]), down=int(row["feedback_down"])
        ),
    )


class ProductServiceServicer(marketplace_pb2_grpc.ProductServiceServicer):

    _counter_lock = threading.Lock()

    def RegisterItemForSale(self, request, context):
        seller_id = request.seller_id
        name = request.name
        category = request.category
        keywords = list(request.keywords)
        condition = request.condition
        price = request.price
        quantity = request.quantity

        if not all([seller_id, name, category, condition]):
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Missing fields")

        normalized = []
        for kw in keywords:
            if not isinstance(kw, str):
                continue
            k = kw.lower()[:8]
            if k:
                normalized.append(k)
            if len(normalized) >= 5:
                break
        keywords = normalized

        db = get_db()
        with self._counter_lock:
            row = db.execute(
                "SELECT next_num FROM item_id_counters WHERE category = ?",
                (category,),
            ).fetchone()

            if row:
                num = row["next_num"]
                db.execute(
                    "UPDATE item_id_counters SET next_num = ? WHERE category = ?",
                    (num + 1, category),
                )
            else:
                num = 1
                db.execute(
                    "INSERT INTO item_id_counters (category, next_num) VALUES (?, ?)",
                    (category, 2),
                )

            db.execute(
                """INSERT INTO items (category, num, name, keywords, condition, price, quantity, seller_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (category, num, name, json.dumps(keywords), condition, float(price), int(quantity), seller_id),
            )
            db.commit()
        return marketplace_pb2.RegisterItemResponse(
            item_id=marketplace_pb2.ItemId(category=category, num=num)
        )

    def ChangeItemPrice(self, request, context):
        item_id = request.item_id
        new_price = request.price

        db = get_db()
        cat, num = item_id.category, item_id.num
        cursor = db.execute(
            "UPDATE items SET price = ? WHERE category = ? AND num = ?",
            (float(new_price), cat, num),
        )
        if cursor.rowcount == 0:
            context.abort(grpc.StatusCode.NOT_FOUND, "Item not found")
        db.commit()
        return marketplace_pb2.ChangePriceResponse()

    def UpdateUnitsForSale(self, request, context):
        item_id = request.item_id
        quantity_change = request.quantity

        db = get_db()
        cat, num = item_id.category, item_id.num
        cursor = db.execute(
            "UPDATE items SET quantity = MAX(0, quantity + ?) WHERE category = ? AND num = ?",
            (int(quantity_change), cat, num),
        )
        if cursor.rowcount == 0:
            context.abort(grpc.StatusCode.NOT_FOUND, "Item not found")
        db.commit()
        return marketplace_pb2.UpdateUnitsResponse()

    def DisplayItemsForSale(self, request, context):
        seller_id = request.seller_id
        if seller_id == 0:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Missing seller_id")

        db = get_db()
        rows = db.execute(
            "SELECT * FROM items WHERE seller_id = ?", (seller_id,)
        ).fetchall()
        items = [_row_to_item(row) for row in rows]
        return marketplace_pb2.ItemListResponse(items=items)

    def GetItem(self, request, context):
        item_id = request.item_id

        db = get_db()
        cat, num = item_id.category, item_id.num
        row = db.execute(
            "SELECT * FROM items WHERE category = ? AND num = ?",
            (cat, num),
        ).fetchone()
        if not row:
            context.abort(grpc.StatusCode.NOT_FOUND, "Item not found")
        return marketplace_pb2.GetItemResponse(item=_row_to_item(row))

    def ProvideFeedback(self, request, context):
        item_id = request.item_id
        feedback_type = request.feedback_type

        if feedback_type not in ("up", "down"):
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Invalid feedback_type")

        db = get_db()
        cat, num = item_id.category, item_id.num
        col = "feedback_up" if feedback_type == "up" else "feedback_down"

        cursor = db.execute(
            f"UPDATE items SET {col} = {col} + 1 WHERE category = ? AND num = ?",
            (cat, num),
        )
        if cursor.rowcount == 0:
            context.abort(grpc.StatusCode.NOT_FOUND, "Item not found")

        row = db.execute(
            "SELECT seller_id FROM items WHERE category = ? AND num = ?",
            (cat, num),
        ).fetchone()
        seller_id = row["seller_id"]
        db.commit()

        seller_update_status = "ok"
        try:
            customer_stub.UpdateSellerFeedback(
                marketplace_pb2.UpdateSellerFeedbackRequest(
                    seller_id=seller_id,
                    feedback_type=feedback_type,
                )
            )
        except grpc.RpcError:
            seller_update_status = "error"

        return marketplace_pb2.ProvideFeedbackResponse(
            seller_update_status=seller_update_status
        )

    def SearchItemsForSale(self, request, context):
        category = request.category
        keywords = list(request.keywords)

        req_keywords = [k.lower() for k in keywords if isinstance(k, str)]

        db = get_db()
        if category > 0:
            rows = db.execute(
                "SELECT * FROM items WHERE category = ?", (category,)
            ).fetchall()
        else:
            rows = db.execute("SELECT * FROM items").fetchall()

        matched_items = []
        for row in rows:
            item_keywords = set(json.loads(row["keywords"]))
            keyword_hits = sum(1 for kw in req_keywords if kw in item_keywords)

            if keyword_hits == 0 and keywords:
                continue

            score = (keyword_hits, row["feedback_up"] - row["feedback_down"], -row["price"])
            matched_items.append((score, _row_to_item(row)))

        matched_items.sort(key=lambda x: x[0], reverse=True)
        return marketplace_pb2.ItemListResponse(
            items=[item for _, item in matched_items]
        )


if __name__ == "__main__":
    server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=100),
        options=[
            ('grpc.max_concurrent_streams', 200),
            ('grpc.max_receive_message_length', 16 * 1024 * 1024),
        ]
    )
    marketplace_pb2_grpc.add_ProductServiceServicer_to_server(
        ProductServiceServicer(), server
    )
    server.add_insecure_port("0.0.0.0:7002")
    server.start()
    print("Product DB gRPC Server on port 7002")
    server.wait_for_termination()