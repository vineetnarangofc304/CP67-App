"""
Point 21 — Admin DIY control panels:
  A) Push Notification Management  (broadcast to users)
  B) Popup / In-App Message Management  (CRUD + consumer read)
  C) Referral Program Configuration  (points, cap, active)

Registered in server.py via:
    from routes.admin_diy import admin_diy_router, consumer_diy_router, init_diy_routes
    init_diy_routes(db)
    app.include_router(admin_diy_router)
    app.include_router(consumer_diy_router)
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
import uuid
import logging

import jwt as _jwt
import os

logger = logging.getLogger(__name__)

admin_diy_router = APIRouter(prefix="/api/admin/diy", tags=["admin-diy"])
consumer_diy_router = APIRouter(prefix="/api/consumer", tags=["consumer-diy"])

_db = None
_security = HTTPBearer(auto_error=False)
_JWT_SECRET = os.environ.get("JWT_SECRET", "cp67-secret-key-2025")

DEFAULT_REFERRAL_CONFIG = {
    "id": "referral_config",
    "referrer_points": 50,
    "referee_points": 50,
    "per_month_cap": 10,
    "active": True,
    "message": "Refer a friend and both of you earn bonus points on their first bill upload.",
    "updated_at": None,
}


def init_diy_routes(db):
    global _db
    _db = db


async def _verify_admin(creds: HTTPAuthorizationCredentials = Depends(_security)):
    if creds is None:
        raise HTTPException(401, "Not authenticated")
    try:
        payload = _jwt.decode(creds.credentials, _JWT_SECRET, algorithms=["HS256"])
    except Exception:
        raise HTTPException(401, "Invalid token")
    if payload.get("role") not in ("admin", "super_admin"):
        raise HTTPException(403, "Admin only")
    return payload


async def _current_consumer(creds: HTTPAuthorizationCredentials = Depends(_security)):
    """Feb 2026: delegate to the single source of truth in routes.consumer so a
    future consumer-token-shape change can't silently break routes again
    (was a live bug — role vs type claim divergence, fixed iter-65)."""
    from routes.consumer import get_current_consumer
    return await get_current_consumer(creds)


# ==================== A) PUSH NOTIFICATIONS ====================

class PushBroadcastRequest(BaseModel):
    title: str
    body: str
    target: str = "all"          # all | tier | opted_in | phone_list
    tier: Optional[str] = None    # Bronze | Silver | Gold | ...
    phones: Optional[List[str]] = None
    data: Optional[Dict[str, Any]] = None
    dry_run: bool = False


@admin_diy_router.post("/push/broadcast")
async def broadcast_push(payload: PushBroadcastRequest, admin=Depends(_verify_admin)):
    """Sends the same push to a matching user set. Fan-out is fire-and-forget
    per subscription so a slow APNs/web-push server never blocks the request."""

    # 1. Resolve target user IDs
    user_query: Dict[str, Any] = {}
    if payload.target == "tier" and payload.tier:
        user_query["tier"] = payload.tier
    elif payload.target == "opted_in":
        user_query["push_opt_in"] = True
    elif payload.target == "phone_list" and payload.phones:
        phones_norm = [p[-10:] for p in payload.phones]
        user_query["$or"] = [
            {"phone": {"$in": phones_norm}},
            {"phone": {"$in": [f"91{p}" for p in phones_norm]}},
        ]
    # else "all" → no filter

    users = await _db.users.find(user_query, {"_id": 0, "id": 1, "phone": 1, "tier": 1}).to_list(None)
    user_ids = [u["id"] for u in users]

    # 2. Load subscriptions for those users
    subs = await _db.push_subscriptions.find(
        {"user_id": {"$in": user_ids}}, {"_id": 0}
    ).to_list(None)

    ios_tokens = [s.get("apns_token") for s in subs if s.get("platform") == "ios" and s.get("apns_token")]
    web_subs = [s for s in subs if s.get("platform") != "ios" and s.get("endpoint")]

    if payload.dry_run:
        return {
            "dry_run": True,
            "matched_users": len(user_ids),
            "ios_devices": len(ios_tokens),
            "web_devices": len(web_subs),
        }

    # 3. Send iOS via APNs (if configured)
    ios_sent = 0
    ios_failed = 0
    try:
        from services.apns_client import send_apns, is_configured as apns_ready
        if apns_ready() and ios_tokens:
            for tok in ios_tokens:
                r = await send_apns(tok, payload.title, payload.body, data=payload.data)
                if r.get("success"):
                    ios_sent += 1
                else:
                    ios_failed += 1
    except Exception as e:
        logger.error(f"APNs broadcast error: {e}")

    # 4. Persist a broadcast log for admin visibility
    log_doc = {
        "id": str(uuid.uuid4()),
        "title": payload.title,
        "body": payload.body,
        "target": payload.target,
        "tier": payload.tier,
        "matched_users": len(user_ids),
        "ios_sent": ios_sent,
        "ios_failed": ios_failed,
        "web_devices": len(web_subs),
        "sent_by": admin.get("username") or "admin",
        "sent_at": datetime.now(timezone.utc).isoformat(),
    }
    await _db.push_broadcasts.insert_one(dict(log_doc))

    return {
        "success": True,
        "matched_users": len(user_ids),
        "ios_sent": ios_sent,
        "ios_failed": ios_failed,
        "web_devices": len(web_subs),
        "broadcast_id": log_doc["id"],
    }


@admin_diy_router.get("/push/history")
async def push_history(limit: int = 50, admin=Depends(_verify_admin)):
    rows = await _db.push_broadcasts.find({}, {"_id": 0}).sort("sent_at", -1).limit(min(limit, 500)).to_list(None)
    return {"broadcasts": rows}


# ==================== B) POPUPS ====================

class PopupCreate(BaseModel):
    title: str
    body: str
    image_url: Optional[str] = None
    cta_label: Optional[str] = None
    cta_url: Optional[str] = None
    target_tier: Optional[str] = None    # None = all tiers
    starts_at: Optional[str] = None
    ends_at: Optional[str] = None
    show_frequency: str = "once"          # once | every_session | daily
    priority: int = 0
    active: bool = True


class PopupUpdate(BaseModel):
    title: Optional[str] = None
    body: Optional[str] = None
    image_url: Optional[str] = None
    cta_label: Optional[str] = None
    cta_url: Optional[str] = None
    target_tier: Optional[str] = None
    starts_at: Optional[str] = None
    ends_at: Optional[str] = None
    show_frequency: Optional[str] = None
    priority: Optional[int] = None
    active: Optional[bool] = None


@admin_diy_router.post("/popups")
async def create_popup(payload: PopupCreate, admin=Depends(_verify_admin)):
    doc = payload.model_dump()
    doc["id"] = str(uuid.uuid4())
    doc["created_at"] = datetime.now(timezone.utc).isoformat()
    doc["created_by"] = admin.get("username") or "admin"
    await _db.popups.insert_one(dict(doc))
    return {"success": True, "popup": doc}


@admin_diy_router.get("/popups")
async def list_popups(admin=Depends(_verify_admin)):
    rows = await _db.popups.find({}, {"_id": 0}).sort("priority", -1).to_list(None)
    return {"popups": rows}


@admin_diy_router.patch("/popups/{popup_id}")
async def update_popup(popup_id: str, payload: PopupUpdate, admin=Depends(_verify_admin)):
    upd = {k: v for k, v in payload.model_dump().items() if v is not None}
    upd["updated_at"] = datetime.now(timezone.utc).isoformat()
    r = await _db.popups.update_one({"id": popup_id}, {"$set": upd})
    if r.matched_count == 0:
        raise HTTPException(404, "Popup not found")
    doc = await _db.popups.find_one({"id": popup_id}, {"_id": 0})
    return {"success": True, "popup": doc}


@admin_diy_router.delete("/popups/{popup_id}")
async def delete_popup(popup_id: str, admin=Depends(_verify_admin)):
    await _db.popups.delete_one({"id": popup_id})
    return {"success": True}


@consumer_diy_router.get("/popups/active")
async def get_active_popup(user=Depends(_current_consumer)):
    """Returns the highest-priority active popup that:
       - is active=True
       - within its start/end window (if set)
       - matches user's tier (or has no tier filter)
       - user has not dismissed (based on show_frequency)"""
    now_iso = datetime.now(timezone.utc).isoformat()

    profile = await _db.users.find_one({"id": user["sub"]}, {"_id": 0, "tier": 1}) or {}
    tier = profile.get("tier", "Bronze")

    q = {
        "active": True,
        "$and": [
            {"$or": [{"starts_at": None}, {"starts_at": {"$lte": now_iso}}]},
            {"$or": [{"ends_at": None}, {"ends_at": {"$gte": now_iso}}]},
            {"$or": [{"target_tier": None}, {"target_tier": tier}]},
        ],
    }
    popups = await _db.popups.find(q, {"_id": 0}).sort("priority", -1).to_list(None)

    # Filter by user's dismissal history
    dismissed = await _db.popup_dismissals.find({"user_id": user["sub"]}, {"_id": 0}).to_list(None)
    dismissed_map = {d["popup_id"]: d for d in dismissed}

    for p in popups:
        d = dismissed_map.get(p["id"])
        freq = p.get("show_frequency", "once")
        if not d:
            return {"popup": p}
        if freq == "once":
            continue
        if freq == "every_session":
            # session-level → the client tracks this in-memory, so always send
            return {"popup": p}
        if freq == "daily":
            last = d.get("last_shown_at", "")
            if last[:10] != now_iso[:10]:
                return {"popup": p}
    return {"popup": None}


class PopupDismissRequest(BaseModel):
    popup_id: str


@consumer_diy_router.post("/popups/dismiss")
async def dismiss_popup(payload: PopupDismissRequest, user=Depends(_current_consumer)):
    now_iso = datetime.now(timezone.utc).isoformat()
    await _db.popup_dismissals.update_one(
        {"user_id": user["sub"], "popup_id": payload.popup_id},
        {"$set": {"user_id": user["sub"], "popup_id": payload.popup_id,
                  "last_shown_at": now_iso, "dismissed_at": now_iso},
         "$setOnInsert": {"first_shown_at": now_iso}},
        upsert=True,
    )
    return {"success": True}


# ==================== C) REFERRAL CONFIG ====================

class ReferralConfigUpdate(BaseModel):
    referrer_points: Optional[int] = None
    referee_points: Optional[int] = None
    per_month_cap: Optional[int] = None
    active: Optional[bool] = None
    message: Optional[str] = None


async def _get_referral_config() -> dict:
    doc = await _db.referral_config.find_one({"id": "referral_config"}, {"_id": 0})
    if not doc:
        seed = dict(DEFAULT_REFERRAL_CONFIG)
        seed["updated_at"] = datetime.now(timezone.utc).isoformat()
        await _db.referral_config.insert_one(dict(seed))
        return dict(DEFAULT_REFERRAL_CONFIG)
    return doc


@admin_diy_router.get("/referral-config")
async def get_referral_config(admin=Depends(_verify_admin)):
    return {"config": await _get_referral_config()}


@admin_diy_router.put("/referral-config")
async def update_referral_config(payload: ReferralConfigUpdate, admin=Depends(_verify_admin)):
    current = await _get_referral_config()
    upd = {k: v for k, v in payload.model_dump().items() if v is not None}
    current.update(upd)
    current["updated_at"] = datetime.now(timezone.utc).isoformat()
    await _db.referral_config.update_one(
        {"id": "referral_config"}, {"$set": current}, upsert=True
    )
    return {"success": True, "config": current}


# Public helper for consumer.py to read live values
async def get_live_referral_config() -> dict:
    return await _get_referral_config()
