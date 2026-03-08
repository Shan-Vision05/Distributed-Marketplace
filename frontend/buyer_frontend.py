import grpc
from common import marketplace_pb2, marketplace_pb2_grpc
from fastapi import FastAPI, HTTPException
import uvicorn
import anyio
from contextlib import asynccontextmanager

from zeep import Client as ZeepClient

CUSTOMER_DB_ADDR = ("10.128.0.4", 7001)
PRODUCT_DB_ADDR = ("10.128.0.5", 7002)
FINANCIAL_SVC_ADDR = ("127.0.0.1", 7005)


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


def send_to_financial_svc(req):
    wsdl_url = f"http://{FINANCIAL_SVC_ADDR[0]}:{FINANCIAL_SVC_ADDR[1]}/?wsdl"
    zeep_client = ZeepClient(wsdl_url)
    response = zeep_client.service.process_payment(
        username=req.get("username", ""),
        card_number=req.get("card_number", ""),
        exp_month=req.get("exp_month", ""),
        exp_year=req.get("exp_year", ""),
        cvv=req.get("cvv", ""),
        name=req.get("name", "")
    )
    parts = response.split(":", 1)
    return {
        "status": parts[0].strip(),
        "message": parts[1].strip() if len(parts) > 1 else ""
    }


def require_buyer_auth(session_id):
    if not session_id:
        raise HTTPException(status_code=401, detail="Missing session_id")
    try:
        resp = customer_stub.ValidateSession(
            marketplace_pb2.SessionRequest(session_id=session_id)
        )
    except grpc.RpcError:
        raise HTTPException(status_code=401, detail="Authentication failed")
    if resp.role != "buyer":
        raise HTTPException(status_code=403, detail="Buyer access required")
    return resp


def parse_item_id(item_id_str):
    parts = str(item_id_str).split(",")
    return [int(parts[0]), int(parts[1])]


@app.post("/buyer/account")
def create_account(req: dict):
    try:
        resp = customer_stub.CreateAccount(
            marketplace_pb2.CreateAccountRequest(
                role="buyer",
                username=req.get("username", ""),
                password=req.get("password", ""),
            )
        )
        return {"status": "ok", "buyer_id": resp.user_id}
    except grpc.RpcError as e:
        _grpc_error_to_http(e)
    except Exception as e:
        print(f"Unexpected error in create_account: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/buyer/login")
def login(req: dict):
    try:
        resp = customer_stub.Login(
            marketplace_pb2.LoginRequest(
                role="buyer",
                username=req.get("username", ""),
                password=req.get("password", ""),
            )
        )
        return {"status": "ok", "session_id": resp.session_id}
    except grpc.RpcError as e:
        _grpc_error_to_http(e)


@app.post("/buyer/logout")
def logout(req: dict):
    try:
        customer_stub.Logout(
            marketplace_pb2.SessionRequest(session_id=req.get("session_id", ""))
        )
        return {"status": "ok"}
    except grpc.RpcError as e:
        _grpc_error_to_http(e)



@app.get("/buyer/purchases")
def get_purchases(session_id: str):
    require_buyer_auth(session_id)
    try:
        resp = customer_stub.GetBuyerPurchases(
            marketplace_pb2.SessionRequest(session_id=session_id)
        )
        history = []
        for p in resp.purchases:
            history.append({
                "item_id": [p.item_id.category, p.item_id.num],
                "item_name": p.item_name,
                "quantity": p.quantity,
                "price": p.price,
                "purchased_at": p.purchased_at,
            })
        return {"status": "ok", "purchase_history": history}
    except grpc.RpcError as e:
        _grpc_error_to_http(e)


@app.post("/buyer/purchase")
def make_purchase(req: dict):
    session_id = req.get("session_id")
    auth = require_buyer_auth(session_id)

    try:
        fin_resp = send_to_financial_svc({
            "username":    auth.username or req.get("username", ""),
            "name":        req.get("name", ""),
            "card_number": req.get("card_number", ""),
            "exp_month":   req.get("exp_month", ""),
            "exp_year":    req.get("exp_year", ""),
            "cvv":         req.get("cvv", ""),
        })
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Financial service unreachable: {str(e)}")

    if not fin_resp:
        raise HTTPException(status_code=502, detail="Financial service returned no response")

    if fin_resp.get("status") == "error":
        raise HTTPException(status_code=400, detail=fin_resp.get("message", "Payment validation failed"))

    if fin_resp.get("status") == "declined":
        raise HTTPException(status_code=402, detail="Payment declined by financial service")

    if fin_resp.get("status") != "approved":
        raise HTTPException(status_code=502, detail="Unexpected financial service response")

    try:
        resp = customer_stub.MakePurchase(
            marketplace_pb2.SessionRequest(session_id=session_id)
        )
        return {"status": "ok", "message": resp.message}
    except grpc.RpcError as e:
        _grpc_error_to_http(e)


@app.post("/buyer/feedback")
def provide_feedback(req: dict):
    session_id = req.get("session_id")
    require_buyer_auth(session_id)
    if not req.get("item_id"):
        raise HTTPException(status_code=400, detail="Missing item_id")
    item_id = parse_item_id(req["item_id"])
    try:
        resp = product_stub.ProvideFeedback(
            marketplace_pb2.ProvideFeedbackRequest(
                item_id=marketplace_pb2.ItemId(category=item_id[0], num=item_id[1]),
                feedback_type=req.get("feedback_type", ""),
            )
        )
        return {"status": "ok", "seller_update": {"status": resp.seller_update_status}}
    except grpc.RpcError as e:
        _grpc_error_to_http(e)



@app.get("/buyer/cart")
def get_cart(session_id: str):
    require_buyer_auth(session_id)
    try:
        resp = customer_stub.GetCart(
            marketplace_pb2.SessionRequest(session_id=session_id)
        )
        cart = {}
        for entry in resp.items:
            key = str([entry.item_id.category, entry.item_id.num])
            cart[key] = entry.quantity
        return {"status": "ok", "cart": cart}
    except grpc.RpcError as e:
        _grpc_error_to_http(e)


@app.delete("/buyer/cart/clear")
def clear_cart(session_id: str):
    require_buyer_auth(session_id)
    try:
        customer_stub.ClearCart(
            marketplace_pb2.SessionRequest(session_id=session_id)
        )
        return {"status": "ok"}
    except grpc.RpcError as e:
        _grpc_error_to_http(e)


@app.delete("/buyer/cart/remove")
def remove_from_cart(session_id: str, item_id: str, quantity: int):
    require_buyer_auth(session_id)
    parsed = parse_item_id(item_id)
    try:
        customer_stub.RemoveFromCart(
            marketplace_pb2.CartItemRequest(
                session_id=session_id,
                item_id=marketplace_pb2.ItemId(category=parsed[0], num=parsed[1]),
                quantity=quantity,
            )
        )
        return {"status": "ok"}
    except grpc.RpcError as e:
        _grpc_error_to_http(e)


@app.post("/buyer/cart/add")
def add_item_to_cart(req: dict):
    session_id = req.get("session_id")
    require_buyer_auth(session_id)

    if req.get("item_id") is None:
        raise HTTPException(status_code=400, detail="Missing item_id")

    item_id = parse_item_id(req["item_id"])

    try:
        product_stub.GetItem(
            marketplace_pb2.GetItemRequest(
                item_id=marketplace_pb2.ItemId(category=item_id[0], num=item_id[1])
            )
        )
    except grpc.RpcError:
        raise HTTPException(status_code=404, detail="Item not found")

    try:
        customer_stub.AddItemToCart(
            marketplace_pb2.CartItemRequest(
                session_id=session_id,
                item_id=marketplace_pb2.ItemId(category=item_id[0], num=item_id[1]),
                quantity=req.get("quantity", 1),
            )
        )
        return {"status": "ok"}
    except grpc.RpcError as e:
        _grpc_error_to_http(e)


@app.post("/buyer/cart/save")
def save_cart(req: dict):
    session_id = req.get("session_id")
    require_buyer_auth(session_id)
    try:
        customer_stub.SaveCart(
            marketplace_pb2.SessionRequest(session_id=session_id)
        )
        return {"status": "ok"}
    except grpc.RpcError as e:
        _grpc_error_to_http(e)



@app.get("/product/items/search")
def search_items(session_id: str, category: int, keywords: str = ""):
    require_buyer_auth(session_id)
    kw_list = [k for k in keywords.split(",") if k]
    try:
        resp = product_stub.SearchItemsForSale(
            marketplace_pb2.SearchItemsRequest(
                category=category,
                keywords=kw_list,
            )
        )
        return {"status": "ok", "items": [_item_to_dict(i) for i in resp.items]}
    except grpc.RpcError as e:
        _grpc_error_to_http(e)


@app.get("/product/items/get")
def get_item(session_id: str, item_id: str):
    require_buyer_auth(session_id)
    parsed = parse_item_id(item_id)
    try:
        resp = product_stub.GetItem(
            marketplace_pb2.GetItemRequest(
                item_id=marketplace_pb2.ItemId(category=parsed[0], num=parsed[1])
            )
        )
        return {"status": "ok", "item": _item_to_dict(resp.item)}
    except grpc.RpcError as e:
        _grpc_error_to_http(e)


@app.get("/seller/rating")
def get_seller_rating(session_id: str, seller_id: int):
    require_buyer_auth(session_id)
    try:
        resp = customer_stub.GetSellerRating(
            marketplace_pb2.GetSellerRatingRequest(
                session_id=session_id,
                seller_id=seller_id,
            )
        )
        return {"status": "ok", "feedback": {"up": resp.feedback.up, "down": resp.feedback.down}}
    except grpc.RpcError as e:
        _grpc_error_to_http(e)


if __name__ == "__main__":
    print("Buyer Frontend running on http://0.0.0.0:7003")
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=7003,
        timeout_keep_alive=120,
        limit_concurrency=300,
        backlog=2048,
        timeout_graceful_shutdown=10,
    )