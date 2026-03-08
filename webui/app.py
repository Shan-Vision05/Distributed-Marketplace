import os
import re
from pathlib import Path
from typing import Any

import requests
import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field


BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
BUYER_FRONTEND_URL = os.getenv("BUYER_FRONTEND_URL", "http://127.0.0.1:7003").rstrip("/")
SELLER_FRONTEND_URL = os.getenv("SELLER_FRONTEND_URL", "http://127.0.0.1:7004").rstrip("/")
WEBUI_HOST = os.getenv("WEBUI_HOST", "127.0.0.1")
WEBUI_PORT = int(os.getenv("WEBUI_PORT", "7010"))
REQUEST_TIMEOUT = float(os.getenv("MARKETPLACE_UI_TIMEOUT", "20"))

app = FastAPI(title="Distributed Marketplace UI")
app.mount("/assets", StaticFiles(directory=str(STATIC_DIR)), name="assets")

_http = requests.Session()


class AuthRequest(BaseModel):
    role: str
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


class LogoutRequest(BaseModel):
    role: str
    session_id: str = Field(min_length=1)


class CartItemRequest(BaseModel):
    session_id: str = Field(min_length=1)
    item_id: str = Field(min_length=1)
    quantity: int = Field(gt=0)


class CheckoutRequest(BaseModel):
    session_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    card_number: str = Field(min_length=12)
    exp_month: str = Field(min_length=1)
    exp_year: str = Field(min_length=2)
    cvv: str = Field(min_length=3)


class FeedbackRequest(BaseModel):
    session_id: str = Field(min_length=1)
    item_id: str = Field(min_length=1)
    feedback_type: str


class SellerItemCreateRequest(BaseModel):
    session_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    category: int = Field(gt=0)
    keywords: str = ""
    condition: str = Field(min_length=1)
    price: float = Field(gt=0)
    quantity: int = Field(gt=0)


class SellerItemPriceRequest(BaseModel):
    session_id: str = Field(min_length=1)
    item_id: str = Field(min_length=1)
    price: float = Field(gt=0)


class SellerItemQuantityRequest(BaseModel):
    session_id: str = Field(min_length=1)
    item_id: str = Field(min_length=1)
    quantity_delta: int


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/config")
def get_config() -> dict[str, Any]:
    return {
        "status": "ok",
        "session_timeout_seconds": 300,
        "roles": ["buyer", "seller"],
        "defaults": {
            "buyer_search_category": 0,
            "condition_options": ["new", "used"],
        },
        "services": {
            "buyer_frontend": BUYER_FRONTEND_URL,
            "seller_frontend": SELLER_FRONTEND_URL,
        },
    }


@app.post("/api/auth/register")
def register(payload: AuthRequest) -> dict[str, Any]:
    path = "/buyer/account" if payload.role == "buyer" else "/seller/account"
    return _request(_base_url(payload.role), "POST", path, json=payload.model_dump())


@app.post("/api/auth/login")
def login(payload: AuthRequest) -> dict[str, Any]:
    path = "/buyer/login" if payload.role == "buyer" else "/seller/login"
    result = _request(_base_url(payload.role), "POST", path, json=payload.model_dump())
    result["role"] = payload.role
    result["username"] = payload.username
    return result


@app.post("/api/auth/logout")
def logout(payload: LogoutRequest) -> dict[str, Any]:
    path = "/buyer/logout" if payload.role == "buyer" else "/seller/logout"
    return _request(_base_url(payload.role), "POST", path, json=payload.model_dump())


@app.get("/api/buyer/products")
def buyer_products(
    session_id: str = Query(...),
    category: int = Query(0),
    keywords: str = Query(default=""),
) -> dict[str, Any]:
    result = _request(
        BUYER_FRONTEND_URL,
        "GET",
        "/product/items/search",
        params={
            "session_id": session_id,
            "category": category,
            "keywords": _normalize_keywords_string(keywords),
        },
    )
    items = [_decorate_item(item) for item in result.get("items", [])]
    return {
        "status": "ok",
        "items": items,
        "count": len(items),
        "query": {"category": category, "keywords": _normalize_keywords_list(keywords)},
    }


@app.get("/api/buyer/cart")
def buyer_cart(session_id: str = Query(...)) -> dict[str, Any]:
    result = _request(
        BUYER_FRONTEND_URL,
        "GET",
        "/buyer/cart",
        params={"session_id": session_id},
    )
    items = []
    total_quantity = 0
    total_price = 0.0

    for raw_item_id, quantity in result.get("cart", {}).items():
        item_id = _normalize_item_id(raw_item_id)
        item = _safe_get_item(session_id, item_id)
        subtotal = round(quantity * float(item.get("price", 0)), 2) if item else 0.0
        total_quantity += int(quantity)
        total_price += subtotal
        items.append(
            {
                "item_id": item_id,
                "quantity": int(quantity),
                "subtotal": subtotal,
                "item": _decorate_item(item) if item else {
                    "item_key": item_id,
                    "name": "Unavailable item",
                    "price": 0,
                    "quantity": 0,
                    "condition": "unknown",
                    "keywords": [],
                    "seller_id": None,
                    "feedback": {"up": 0, "down": 0},
                    "unavailable": True,
                },
            }
        )

    return {
        "status": "ok",
        "items": items,
        "summary": {
            "line_items": len(items),
            "total_quantity": total_quantity,
            "total_price": round(total_price, 2),
        },
    }


@app.post("/api/buyer/cart/add")
def add_to_cart(payload: CartItemRequest) -> dict[str, Any]:
    return _request(
        BUYER_FRONTEND_URL,
        "POST",
        "/buyer/cart/add",
        json={
            "session_id": payload.session_id,
            "item_id": _normalize_item_id(payload.item_id),
            "quantity": payload.quantity,
        },
    )


@app.post("/api/buyer/cart/remove")
def remove_from_cart(payload: CartItemRequest) -> dict[str, Any]:
    return _request(
        BUYER_FRONTEND_URL,
        "DELETE",
        "/buyer/cart/remove",
        params={
            "session_id": payload.session_id,
            "item_id": _normalize_item_id(payload.item_id),
            "quantity": payload.quantity,
        },
    )


@app.post("/api/buyer/cart/clear")
def clear_cart(payload: LogoutRequest) -> dict[str, Any]:
    return _request(
        BUYER_FRONTEND_URL,
        "DELETE",
        "/buyer/cart/clear",
        params={"session_id": payload.session_id},
    )


@app.post("/api/buyer/cart/save")
def save_cart(payload: LogoutRequest) -> dict[str, Any]:
    return _request(
        BUYER_FRONTEND_URL,
        "POST",
        "/buyer/cart/save",
        json={"session_id": payload.session_id},
    )


@app.post("/api/buyer/checkout")
def checkout(payload: CheckoutRequest) -> dict[str, Any]:
    return _request(
        BUYER_FRONTEND_URL,
        "POST",
        "/buyer/purchase",
        json=payload.model_dump(),
    )


@app.get("/api/buyer/orders")
def buyer_orders(session_id: str = Query(...)) -> dict[str, Any]:
    result = _request(
        BUYER_FRONTEND_URL,
        "GET",
        "/buyer/purchases",
        params={"session_id": session_id},
    )
    history = []
    for purchase in result.get("purchase_history", []):
        category, num = purchase.get("item_id", [0, 0])
        history.append(
            {
                **purchase,
                "item_key": f"{category},{num}",
                "total": round(float(purchase.get("price", 0)) * int(purchase.get("quantity", 0)), 2),
            }
        )
    return {"status": "ok", "purchase_history": history, "count": len(history)}


@app.post("/api/buyer/feedback")
def buyer_feedback(payload: FeedbackRequest) -> dict[str, Any]:
    feedback_type = payload.feedback_type.lower().strip()
    if feedback_type not in {"up", "down"}:
        raise HTTPException(status_code=400, detail="Feedback must be 'up' or 'down'")
    return _request(
        BUYER_FRONTEND_URL,
        "POST",
        "/buyer/feedback",
        json={
            "session_id": payload.session_id,
            "item_id": _normalize_item_id(payload.item_id),
            "feedback_type": feedback_type,
        },
    )


@app.get("/api/seller/items")
def seller_items(session_id: str = Query(...)) -> dict[str, Any]:
    result = _request(
        SELLER_FRONTEND_URL,
        "GET",
        "/seller/items",
        params={"session_id": session_id},
    )
    items = [_decorate_item(item) for item in result.get("items", [])]
    return {"status": "ok", "items": items, "count": len(items)}


@app.post("/api/seller/items")
def create_seller_item(payload: SellerItemCreateRequest) -> dict[str, Any]:
    return _request(
        SELLER_FRONTEND_URL,
        "POST",
        "/seller/items",
        json={
            "session_id": payload.session_id,
            "name": payload.name,
            "category": payload.category,
            "keywords": _normalize_keywords_list(payload.keywords),
            "condition": payload.condition.strip().lower(),
            "price": payload.price,
            "quantity": payload.quantity,
        },
    )


@app.post("/api/seller/items/price")
def update_seller_item_price(payload: SellerItemPriceRequest) -> dict[str, Any]:
    return _request(
        SELLER_FRONTEND_URL,
        "PUT",
        "/seller/items/price",
        json={
            "session_id": payload.session_id,
            "item_id": _normalize_item_id(payload.item_id),
            "price": payload.price,
        },
    )


@app.post("/api/seller/items/quantity")
def update_seller_item_quantity(payload: SellerItemQuantityRequest) -> dict[str, Any]:
    if payload.quantity_delta == 0:
        raise HTTPException(status_code=400, detail="Quantity change cannot be 0")
    return _request(
        SELLER_FRONTEND_URL,
        "PUT",
        "/seller/items/quantity",
        json={
            "session_id": payload.session_id,
            "item_id": _normalize_item_id(payload.item_id),
            "quantity": payload.quantity_delta,
        },
    )


@app.get("/api/seller/rating")
def seller_rating(session_id: str = Query(...)) -> dict[str, Any]:
    return _request(
        SELLER_FRONTEND_URL,
        "GET",
        "/seller/rating",
        params={"session_id": session_id},
    )


def _base_url(role: str) -> str:
    normalized = role.strip().lower()
    if normalized == "buyer":
        return BUYER_FRONTEND_URL
    if normalized == "seller":
        return SELLER_FRONTEND_URL
    raise HTTPException(status_code=400, detail="Role must be 'buyer' or 'seller'")


def _request(base_url: str, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
    url = f"{base_url}/{path.lstrip('/')}"
    try:
        response = _http.request(method, url, timeout=REQUEST_TIMEOUT, **kwargs)
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"Unable to reach upstream service: {exc}") from exc

    data: dict[str, Any] | None = None
    if response.content:
        try:
            data = response.json()
        except ValueError:
            data = {"detail": response.text.strip() or "Upstream service returned invalid JSON"}

    if response.status_code >= 400:
        detail = "Upstream request failed"
        if isinstance(data, dict):
            detail = str(data.get("detail") or data.get("message") or detail)
        raise HTTPException(status_code=response.status_code, detail=detail)

    return data or {"status": "ok"}


def _normalize_item_id(raw_item_id: str) -> str:
    matches = re.findall(r"-?\d+", str(raw_item_id))
    if len(matches) < 2:
        raise HTTPException(status_code=400, detail="Invalid item_id format. Expected 'category,num'.")
    return f"{int(matches[0])},{int(matches[1])}"


def _normalize_keywords_list(keywords: str) -> list[str]:
    if not keywords:
        return []
    if isinstance(keywords, str):
        tokens = re.split(r"[\s,]+", keywords.strip())
    else:
        tokens = [str(value).strip() for value in keywords]
    return [token for token in tokens if token]


def _normalize_keywords_string(keywords: str) -> str:
    return ",".join(_normalize_keywords_list(keywords))


def _safe_get_item(session_id: str, item_id: str) -> dict[str, Any] | None:
    try:
        result = _request(
            BUYER_FRONTEND_URL,
            "GET",
            "/product/items/get",
            params={"session_id": session_id, "item_id": item_id},
        )
    except HTTPException as exc:
        if exc.status_code == 404:
            return None
        raise
    return result.get("item")


def _decorate_item(item: dict[str, Any] | None) -> dict[str, Any] | None:
    if item is None:
        return None
    category, num = item.get("item_id", [0, 0])
    decorated = dict(item)
    decorated["item_key"] = f"{category},{num}"
    decorated["feedback_score"] = int(item.get("feedback", {}).get("up", 0)) - int(item.get("feedback", {}).get("down", 0))
    decorated["is_in_stock"] = int(item.get("quantity", 0)) > 0
    return decorated


if __name__ == "__main__":
    print(f"Marketplace UI running on http://{WEBUI_HOST}:{WEBUI_PORT}")
    uvicorn.run("webui.app:app", host=WEBUI_HOST, port=WEBUI_PORT, reload=False)
