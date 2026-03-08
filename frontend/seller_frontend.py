import grpc
from common import marketplace_pb2, marketplace_pb2_grpc
from fastapi import FastAPI, HTTPException
import uvicorn
import anyio
from contextlib import asynccontextmanager


CUSTOMER_DB_ADDR = ("10.128.0.4", 7001)
PRODUCT_DB_ADDR = ("10.128.0.5", 7002)


@asynccontextmanager
async def lifespan(app):
    limiter = anyio.to_thread.current_default_thread_limiter()
    limiter.total_tokens = 200
    yield

app = FastAPI(lifespan=lifespan)

channel_options = [
    ('grpc.max_concurrent_streams', 200),
    ('grpc.keepalive_time_ms', 10000),
    ('grpc.keepalive_timeout_ms', 5000),
]

customer_channel = grpc.insecure_channel(
    f"{CUSTOMER_DB_ADDR[0]}:{CUSTOMER_DB_ADDR[1]}",
    options=channel_options
)
customer_stub = marketplace_pb2_grpc.CustomerServiceStub(customer_channel)

product_channel = grpc.insecure_channel(
    f"{PRODUCT_DB_ADDR[0]}:{PRODUCT_DB_ADDR[1]}",
    options=channel_options
)
product_stub = marketplace_pb2_grpc.ProductServiceStub(product_channel)


def _grpc_error_to_http(e):
    code = e.code()
    detail = e.details()
    status_map = {
        grpc.StatusCode.INVALID_ARGUMENT: 400,
        grpc.StatusCode.UNAUTHENTICATED: 401,
        grpc.StatusCode.PERMISSION_DENIED: 403,
        grpc.StatusCode.NOT_FOUND: 404,
        grpc.StatusCode.ALREADY_EXISTS: 409,
        grpc.StatusCode.FAILED_PRECONDITION: 400,
    }
    http_status = status_map.get(code, 500)
    raise HTTPException(status_code=http_status, detail=detail)


def _item_to_dict(item):
    return {
        "item_id": [item.item_id.category, item.item_id.num],
        "name": item.name,
        "category": item.category,
        "keywords": list(item.keywords),
        "condition": item.condition,
        "price": item.price,
        "quantity": item.quantity,
        "seller_id": item.seller_id,
        "feedback": {"up": item.feedback.up, "down": item.feedback.down},
    }


def require_seller_auth(session_id):
    if not session_id:
        raise HTTPException(status_code=401, detail="Missing session_id")
    try:
        resp = customer_stub.ValidateSession(
            marketplace_pb2.SessionRequest(session_id=session_id)
        )
    except grpc.RpcError as e:
        code = e.code() if hasattr(e, 'code') else None
        if code in (grpc.StatusCode.UNAUTHENTICATED, grpc.StatusCode.PERMISSION_DENIED):
            raise HTTPException(status_code=401, detail=e.details())
        raise HTTPException(status_code=500, detail=f"Auth service error: {e.details()}")
    if resp.role != "seller":
        raise HTTPException(status_code=403, detail="Seller access required")
    return resp


def parse_item_id(item_id_str):
    parts = str(item_id_str).split(",")
    return [int(parts[0]), int(parts[1])]


@app.post("/seller/account")
def create_account(req: dict):
    try:
        resp = customer_stub.CreateAccount(
            marketplace_pb2.CreateAccountRequest(
                role="seller",
                username=req.get("username", ""),
                password=req.get("password", ""),
            )
        )
        return {"status": "ok", "seller_id": resp.user_id}
    except grpc.RpcError as e:
        _grpc_error_to_http(e)


@app.post("/seller/login")
def login(req: dict):
    try:
        resp = customer_stub.Login(
            marketplace_pb2.LoginRequest(
                role="seller",
                username=req.get("username", ""),
                password=req.get("password", ""),
            )
        )
        return {"status": "ok", "session_id": resp.session_id}
    except grpc.RpcError as e:
        _grpc_error_to_http(e)


@app.post("/seller/logout")
def logout(req: dict):
    try:
        customer_stub.Logout(
            marketplace_pb2.SessionRequest(session_id=req.get("session_id", ""))
        )
        return {"status": "ok"}
    except grpc.RpcError as e:
        _grpc_error_to_http(e)


@app.post("/seller/items")
def register_item(req: dict):
    session_id = req.get("session_id")
    auth = require_seller_auth(session_id)
    try:
        resp = product_stub.RegisterItemForSale(
            marketplace_pb2.RegisterItemRequest(
                seller_id=auth.user_id,
                name=req.get("name", ""),
                category=req.get("category", 0),
                keywords=req.get("keywords", []),
                condition=req.get("condition", ""),
                price=float(req.get("price", 0)),
                quantity=int(req.get("quantity", 0)),
            )
        )
        return {"status": "ok", "item_id": [resp.item_id.category, resp.item_id.num]}
    except grpc.RpcError as e:
        _grpc_error_to_http(e)


@app.put("/seller/items/price")
def change_price(req: dict):
    session_id = req.get("session_id")
    require_seller_auth(session_id)
    if not req.get("item_id"):
        raise HTTPException(status_code=400, detail="Missing item_id")
    parsed = parse_item_id(req["item_id"])
    try:
        product_stub.ChangeItemPrice(
            marketplace_pb2.ChangePriceRequest(
                item_id=marketplace_pb2.ItemId(category=parsed[0], num=parsed[1]),
                price=float(req.get("price", 0)),
            )
        )
        return {"status": "ok"}
    except grpc.RpcError as e:
        _grpc_error_to_http(e)


@app.put("/seller/items/quantity")
def update_units(req: dict):
    session_id = req.get("session_id")
    require_seller_auth(session_id)
    if not req.get("item_id"):
        raise HTTPException(status_code=400, detail="Missing item_id")
    parsed = parse_item_id(req["item_id"])
    try:
        product_stub.UpdateUnitsForSale(
            marketplace_pb2.UpdateUnitsRequest(
                item_id=marketplace_pb2.ItemId(category=parsed[0], num=parsed[1]),
                quantity=int(req.get("quantity", 0)),
            )
        )
        return {"status": "ok"}
    except grpc.RpcError as e:
        _grpc_error_to_http(e)


@app.get("/seller/items")
def display_items(session_id: str):
    auth = require_seller_auth(session_id)
    try:
        resp = product_stub.DisplayItemsForSale(
            marketplace_pb2.SellerItemsRequest(seller_id=auth.user_id)
        )
        return {"status": "ok", "items": [_item_to_dict(i) for i in resp.items]}
    except grpc.RpcError as e:
        _grpc_error_to_http(e)


@app.get("/seller/rating")
def get_seller_rating(session_id: str):
    auth = require_seller_auth(session_id)
    try:
        resp = customer_stub.GetSellerRating(
            marketplace_pb2.GetSellerRatingRequest(
                session_id=session_id,
                seller_id=auth.user_id,
            )
        )
        return {"status": "ok", "feedback": {"up": resp.feedback.up, "down": resp.feedback.down}}
    except grpc.RpcError as e:
        _grpc_error_to_http(e)


if __name__ == "__main__":
    print("Seller Frontend running on http://0.0.0.0:7004")
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=7004,
        timeout_keep_alive=120,
        limit_concurrency=300,
        backlog=2048,
        timeout_graceful_shutdown=10,
    )