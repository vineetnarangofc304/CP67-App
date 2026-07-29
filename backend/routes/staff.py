"""
Retailer Staff Incentive Program (Point 19)

Provides:
  - Data models: staff, staff_incentives, staff_attributions, staff_config
  - Admin endpoints: onboard staff, list, edit, assign QR, tune slabs
  - Staff endpoints: OTP login, dashboard, redeem request
  - Attribution engine: WhatsApp incoming message parsed for staff_id → create window / registration

MVP defaults (user-picked):
  - Slab-based incentives (registration + bill upload)
  - 15-minute attribution window for existing-customer bill uploads
  - Separate staff app served at /staff-app/*
"""
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from typing import Optional, List, Dict
from datetime import datetime, timezone, timedelta
import uuid
import jwt
import os
import re
import logging
import base64
import io

try:
    import qrcode
except ImportError:
    qrcode = None

logger = logging.getLogger(__name__)

staff_router = APIRouter(prefix="/api/staff")
staff_admin_router = APIRouter(prefix="/api/admin/staff")

_db = None
security = HTTPBearer(auto_error=False)

JWT_SECRET = os.environ.get('JWT_SECRET', 'cp67-secret-key-2025')

# ==================== SETUP ====================

def bind_db(db):
    global _db
    _db = db


DEFAULT_STAFF_CONFIG = {
    "id": "staff_config",
    "registration_slabs": [
        {"min": 0, "max": 10, "amount": 50},
        {"min": 11, "max": 25, "amount": 75},
        {"min": 26, "max": 50, "amount": 100},
        {"min": 51, "max": 999999, "amount": 150},
    ],
    "bill_upload_slabs": [
        {"min": 0, "max": 20, "amount": 20},
        {"min": 21, "max": 50, "amount": 30},
        {"min": 51, "max": 999999, "amount": 50},
    ],
    "attribution_window_minutes": 15,
    "registration_validity_days": 60,
}


async def get_staff_config() -> Dict:
    doc = await _db.staff_config.find_one({"id": "staff_config"}, {"_id": 0})
    if not doc:
        await _db.staff_config.insert_one(DEFAULT_STAFF_CONFIG)
        return DEFAULT_STAFF_CONFIG
    return doc


def _amount_for_slab(count: int, slabs: List[Dict]) -> int:
    for s in slabs:
        if s["min"] <= count <= s["max"]:
            return int(s["amount"])
    return int(slabs[-1]["amount"]) if slabs else 0


# ==================== AUTH ====================

def _make_staff_token(staff: Dict) -> str:
    return jwt.encode({
        "sub": staff["id"],
        "phone": staff["phone"],
        "role": "retail_staff",
        "exp": datetime.now(timezone.utc) + timedelta(days=30),
    }, JWT_SECRET, algorithm="HS256")


async def _verify_staff(auth: HTTPAuthorizationCredentials = Depends(security)) -> Dict:
    if not auth:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(auth.credentials, JWT_SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
    if payload.get("role") != "retail_staff":
        raise HTTPException(status_code=403, detail="Not a staff account")
    staff = await _db.retail_staff.find_one({"id": payload["sub"]}, {"_id": 0})
    if not staff:
        raise HTTPException(status_code=401, detail="Staff not found")
    if not staff.get("is_active"):
        raise HTTPException(status_code=403, detail="Staff account inactive")
    return staff


async def _verify_admin(auth: HTTPAuthorizationCredentials = Depends(security)) -> Dict:
    if not auth:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(auth.credentials, JWT_SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
    if payload.get("role") == "retail_staff":
        raise HTTPException(status_code=403, detail="Admin only")
    return payload


# ==================== ADMIN: STAFF CRUD ====================

class StaffCreate(BaseModel):
    name: str
    phone: str  # 10 digits, will be normalised
    brand_name: str
    store_location: Optional[str] = None
    email: Optional[str] = None


class StaffUpdate(BaseModel):
    name: Optional[str] = None
    brand_name: Optional[str] = None
    store_location: Optional[str] = None
    email: Optional[str] = None
    is_active: Optional[bool] = None


def _normalise_phone(p: str) -> str:
    d = re.sub(r"\D", "", p or "")
    if len(d) >= 10:
        return d[-10:]
    return d


@staff_admin_router.post("")
async def admin_create_staff(payload: StaffCreate, auth=Depends(_verify_admin)):
    phone = _normalise_phone(payload.phone)
    if len(phone) != 10:
        raise HTTPException(status_code=400, detail="Phone must be 10 digits")

    existing = await _db.retail_staff.find_one({"phone": phone}, {"_id": 0, "id": 1})
    if existing:
        raise HTTPException(status_code=400, detail="Staff with this phone already exists")

    staff_id = str(uuid.uuid4())
    # Human-readable staff code
    seq = await _db.retail_staff.count_documents({}) + 1
    staff_code = f"HL-{seq:04d}"

    doc = {
        "id": staff_id,
        "staff_code": staff_code,
        "name": payload.name.strip(),
        "phone": phone,
        "brand_name": payload.brand_name.strip(),
        "store_location": (payload.store_location or "").strip(),
        "email": (payload.email or "").strip(),
        "is_active": True,
        # QR contains an encrypted-ish token, but for MVP we use staff_id itself
        # since the QR is derived from staff_id and only distributed to that staff.
        "qr_token": f"HL{staff_id[:12].replace('-','').upper()}",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await _db.retail_staff.insert_one(doc)
    return {"success": True, "staff": doc}


@staff_admin_router.get("")
async def admin_list_staff(active_only: bool = False, brand: Optional[str] = None,
                            auth=Depends(_verify_admin)):
    q = {}
    if active_only:
        q["is_active"] = True
    if brand:
        q["brand_name"] = brand
    staff = []
    async for s in _db.retail_staff.find(q, {"_id": 0}).sort("created_at", -1):
        staff.append(s)
    return {"staff": staff, "total": len(staff)}


@staff_admin_router.patch("/{staff_id}")
async def admin_update_staff(staff_id: str, patch: StaffUpdate, auth=Depends(_verify_admin)):
    updates = {k: v for k, v in patch.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="Nothing to update")
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    r = await _db.retail_staff.update_one({"id": staff_id}, {"$set": updates})
    if r.matched_count == 0:
        raise HTTPException(status_code=404, detail="Staff not found")
    doc = await _db.retail_staff.find_one({"id": staff_id}, {"_id": 0})
    return {"success": True, "staff": doc}


@staff_admin_router.get("/{staff_id}/qr")
async def admin_get_staff_qr(staff_id: str, auth=Depends(_verify_admin)):
    """Return the WhatsApp deep-link URL + a QR image (base64 PNG)."""
    staff = await _db.retail_staff.find_one({"id": staff_id}, {"_id": 0})
    if not staff:
        raise HTTPException(status_code=404, detail="Staff not found")
    wa_phone = os.environ.get("WA_BUSINESS_PHONE") or "917988077663"
    msg = f"Hi CP67! I'm registering via staff {staff['staff_code']} ({staff['brand_name']}). #STAFF:{staff['qr_token']}"
    wa_url = f"https://wa.me/{wa_phone}?text={_url_encode(msg)}"

    qr_b64 = None
    if qrcode is not None:
        img = qrcode.make(wa_url)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        qr_b64 = base64.b64encode(buf.getvalue()).decode()
    return {
        "staff_id": staff["id"],
        "staff_code": staff["staff_code"],
        "qr_token": staff["qr_token"],
        "whatsapp_url": wa_url,
        "prefilled_message": msg,
        "qr_image_base64": qr_b64,
    }


def _url_encode(s: str) -> str:
    from urllib.parse import quote
    return quote(s, safe="")


# ==================== ADMIN: CONFIG ====================

class StaffConfigUpdate(BaseModel):
    registration_slabs: Optional[List[Dict]] = None
    bill_upload_slabs: Optional[List[Dict]] = None
    attribution_window_minutes: Optional[int] = None
    registration_validity_days: Optional[int] = None


@staff_admin_router.get("/config/current")
async def admin_get_staff_config(auth=Depends(_verify_admin)):
    cfg = await get_staff_config()
    return {"config": cfg}


@staff_admin_router.put("/config/current")
async def admin_update_staff_config(update: StaffConfigUpdate, auth=Depends(_verify_admin)):
    patch = {k: v for k, v in update.model_dump().items() if v is not None}
    if not patch:
        raise HTTPException(status_code=400, detail="Nothing to update")
    if "attribution_window_minutes" in patch:
        patch["attribution_window_minutes"] = max(1, min(240, int(patch["attribution_window_minutes"])))
    patch["updated_at"] = datetime.now(timezone.utc).isoformat()
    await _db.staff_config.update_one({"id": "staff_config"}, {"$set": patch}, upsert=True)
    cfg = await get_staff_config()
    return {"success": True, "config": cfg}


# ==================== ADMIN: METRICS ====================

@staff_admin_router.get("/metrics/overview")
async def admin_metrics_overview(auth=Depends(_verify_admin)):
    total_staff = await _db.retail_staff.count_documents({})
    active_staff = await _db.retail_staff.count_documents({"is_active": True})

    pipe = [{"$group": {
        "_id": "$status",
        "count": {"$sum": 1},
        "total_amount": {"$sum": "$amount"}
    }}]
    inc_agg = {}
    async for row in _db.staff_incentives.aggregate(pipe):
        inc_agg[row["_id"]] = {"count": row["count"], "amount": row["total_amount"]}

    return {
        "total_staff": total_staff,
        "active_staff": active_staff,
        "incentives_by_status": inc_agg,
    }


@staff_admin_router.get("/leaderboard")
async def admin_leaderboard(period: str = "monthly", auth=Depends(_verify_admin)):
    """period: daily | weekly | monthly | all"""
    days_back = {"daily": 1, "weekly": 7, "monthly": 30, "all": 365 * 5}.get(period, 30)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days_back)).isoformat()
    pipe = [
        {"$match": {"created_at": {"$gte": cutoff}, "status": {"$in": ["approved", "redeemable", "redeemed", "pending"]}}},
        {"$group": {
            "_id": "$staff_id",
            "total_amount": {"$sum": "$amount"},
            "registrations": {"$sum": {"$cond": [{"$eq": ["$type", "registration"]}, 1, 0]}},
            "bill_uploads": {"$sum": {"$cond": [{"$eq": ["$type", "bill_upload"]}, 1, 0]}},
        }},
        {"$sort": {"total_amount": -1}},
        {"$limit": 50},
    ]
    rows = []
    async for r in _db.staff_incentives.aggregate(pipe):
        staff = await _db.retail_staff.find_one({"id": r["_id"]}, {"_id": 0, "name": 1, "brand_name": 1, "staff_code": 1})
        if not staff:
            continue
        rows.append({
            **staff,
            "total_amount": r["total_amount"],
            "registrations": r["registrations"],
            "bill_uploads": r["bill_uploads"],
        })
    return {"period": period, "leaderboard": rows}


# ==================== STAFF: LOGIN + DASHBOARD ====================

class StaffOTPRequest(BaseModel):
    phone: str


class StaffOTPVerify(BaseModel):
    phone: str
    otp: str


@staff_router.post("/auth/send-otp")
async def staff_send_otp(payload: StaffOTPRequest):
    phone = _normalise_phone(payload.phone)
    staff = await _db.retail_staff.find_one({"phone": phone, "is_active": True}, {"_id": 0})
    if not staff:
        # Silent success — don't leak which numbers are registered
        return {"success": True, "message": "OTP sent if number is registered"}
    otp = "1234"  # Dev bypass; will be replaced by real SMS integration
    await _db.staff_otps.update_one(
        {"phone": phone},
        {"$set": {"otp": otp, "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()}},
        upsert=True,
    )
    logger.info(f"Staff OTP for {phone}: {otp}")
    return {"success": True, "message": "OTP sent"}


@staff_router.post("/auth/verify-otp")
async def staff_verify_otp(payload: StaffOTPVerify):
    phone = _normalise_phone(payload.phone)
    # Dev bypass
    if payload.otp != "1234":
        rec = await _db.staff_otps.find_one({"phone": phone}, {"_id": 0})
        if not rec or rec.get("otp") != payload.otp:
            raise HTTPException(status_code=401, detail="Invalid OTP")
    staff = await _db.retail_staff.find_one({"phone": phone, "is_active": True}, {"_id": 0})
    if not staff:
        raise HTTPException(status_code=401, detail="Staff not registered or inactive")
    token = _make_staff_token(staff)
    return {"success": True, "token": token, "staff": {
        "id": staff["id"], "name": staff["name"], "staff_code": staff["staff_code"],
        "brand_name": staff["brand_name"], "phone": staff["phone"],
    }}


@staff_router.get("/me")
async def staff_me(staff=Depends(_verify_staff)):
    return {"staff": {k: v for k, v in staff.items() if k not in ("qr_token",)}}


@staff_router.get("/dashboard")
async def staff_dashboard(staff=Depends(_verify_staff)):
    sid = staff["id"]
    # Aggregate incentives by status
    pipe = [
        {"$match": {"staff_id": sid}},
        {"$group": {
            "_id": "$status",
            "total_amount": {"$sum": "$amount"},
            "count": {"$sum": 1}
        }}
    ]
    by_status = {row["_id"]: {"amount": row["total_amount"], "count": row["count"]} async for row in _db.staff_incentives.aggregate(pipe)}
    earned = sum(v["amount"] for k, v in by_status.items() if k in ("approved", "redeemable", "redeemed"))
    redeemable = sum(v["amount"] for k, v in by_status.items() if k == "redeemable")
    on_hold = sum(v["amount"] for k, v in by_status.items() if k in ("pending", "pending_verification"))
    redeemed = by_status.get("redeemed", {}).get("amount", 0)

    reg_count = await _db.staff_incentives.count_documents({"staff_id": sid, "type": "registration"})
    upload_count = await _db.staff_incentives.count_documents({"staff_id": sid, "type": "bill_upload"})

    cfg = await get_staff_config()
    current_reg_slab = _amount_for_slab(reg_count, cfg["registration_slabs"])
    current_upload_slab = _amount_for_slab(upload_count, cfg["bill_upload_slabs"])

    return {
        "summary": {
            "total_earned": earned,
            "redeemable": redeemable,
            "on_hold": on_hold,
            "redeemed": redeemed,
        },
        "performance": {
            "registrations": reg_count,
            "bill_uploads": upload_count,
            "current_registration_rate": current_reg_slab,
            "current_upload_rate": current_upload_slab,
        },
        "config_snapshot": {
            "registration_slabs": cfg["registration_slabs"],
            "bill_upload_slabs": cfg["bill_upload_slabs"],
            "attribution_window_minutes": cfg["attribution_window_minutes"],
        },
    }


@staff_router.get("/incentives")
async def staff_incentives_list(limit: int = 50, staff=Depends(_verify_staff)):
    rows = []
    async for i in _db.staff_incentives.find(
        {"staff_id": staff["id"]}, {"_id": 0}
    ).sort("created_at", -1).limit(limit):
        # NEVER expose customer PII on staff dashboard
        rows.append({
            "id": i.get("id"),
            "type": i.get("type"),
            "status": i.get("status"),
            "amount": i.get("amount"),
            "created_at": i.get("created_at"),
            "approved_at": i.get("approved_at"),
            "reason": i.get("reason"),
        })
    return {"incentives": rows}


# ==================== STAFF: QR (self view) ====================

@staff_router.get("/qr")
async def staff_own_qr(staff=Depends(_verify_staff)):
    wa_phone = os.environ.get("WA_BUSINESS_PHONE") or "917988077663"
    msg = f"Hi CP67! I'm registering via staff {staff['staff_code']} ({staff['brand_name']}). #STAFF:{staff['qr_token']}"
    wa_url = f"https://wa.me/{wa_phone}?text={_url_encode(msg)}"
    qr_b64 = None
    if qrcode is not None:
        img = qrcode.make(wa_url)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        qr_b64 = base64.b64encode(buf.getvalue()).decode()
    return {
        "staff_code": staff["staff_code"],
        "brand_name": staff["brand_name"],
        "whatsapp_url": wa_url,
        "qr_image_base64": qr_b64,
    }


# ==================== ATTRIBUTION ENGINE ====================

STAFF_MSG_PATTERN = re.compile(r"#STAFF:([A-Z0-9]+)")


async def parse_staff_token_from_message(message_text: str) -> Optional[Dict]:
    """Return staff doc if message contains a valid #STAFF:token marker."""
    if not message_text:
        return None
    m = STAFF_MSG_PATTERN.search(message_text.upper())
    if not m:
        return None
    token = m.group(1)
    staff = await _db.retail_staff.find_one(
        {"qr_token": token, "is_active": True}, {"_id": 0}
    )
    return staff


async def open_attribution_window(customer_phone: str, staff: Dict) -> Dict:
    """Called from WhatsApp handler when a QR-scan message arrives. Opens a
    15-min attribution window for the customer_phone → staff. If customer is
    already registered, a subsequent bill upload within this window is
    credited to the staff. If not registered, the WhatsApp registration flow
    triggers create_registration_incentive() when it completes."""
    cfg = await get_staff_config()
    window_min = int(cfg.get("attribution_window_minutes") or 15)
    now = datetime.now(timezone.utc)
    expires = now + timedelta(minutes=window_min)
    doc = {
        "id": str(uuid.uuid4()),
        "customer_phone": customer_phone,
        "staff_id": staff["id"],
        "staff_code": staff["staff_code"],
        "created_at": now.isoformat(),
        "expires_at": expires.isoformat(),
        "used": False,
    }
    await _db.staff_attributions.insert_one(doc)
    return doc


async def find_active_attribution(customer_phone: str) -> Optional[Dict]:
    """Return the most-recent active (unexpired, unused) attribution for this customer."""
    now_iso = datetime.now(timezone.utc).isoformat()
    return await _db.staff_attributions.find_one({
        "customer_phone": customer_phone,
        "expires_at": {"$gte": now_iso},
        "used": False,
    }, {"_id": 0}, sort=[("created_at", -1)])


async def create_registration_incentive(customer_phone: str, staff: Dict):
    """Called when a new customer completes registration and their attribution
    is present. Creates a 'pending' registration incentive that becomes
    redeemable only after the customer uploads a bill."""
    cfg = await get_staff_config()
    count_so_far = await _db.staff_incentives.count_documents({"staff_id": staff["id"], "type": "registration"})
    amount = _amount_for_slab(count_so_far, cfg["registration_slabs"])
    validity_days = int(cfg.get("registration_validity_days") or 60)
    expires_at = (datetime.now(timezone.utc) + timedelta(days=validity_days)).isoformat()
    doc = {
        "id": str(uuid.uuid4()),
        "staff_id": staff["id"],
        "staff_code": staff["staff_code"],
        "customer_phone": customer_phone,
        "type": "registration",
        "status": "pending",       # → redeemable when customer uploads first bill
        "amount": amount,
        "expires_at": expires_at,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await _db.staff_incentives.insert_one(doc)
    return doc


async def create_or_activate_bill_incentive(bill_id: str, customer_phone: str, bill_status: str):
    """Called from the bill-upload pipeline after each bill status change.
      - If a matching active attribution exists → create a bill_upload incentive.
      - Additionally, if the customer has a pending registration incentive → activate it.
      - Status mapping: approved→approved(redeemable), pending/manual→pending_verification, rejected→cancelled."""
    # 1. Try to find an active attribution
    attribution = await find_active_attribution(customer_phone)
    cfg = await get_staff_config()

    if attribution:
        # Check we haven't already credited this exact bill
        already = await _db.staff_incentives.find_one({
            "type": "bill_upload", "bill_id": bill_id,
        }, {"_id": 0, "id": 1})
        if not already:
            staff_id = attribution["staff_id"]
            count_so_far = await _db.staff_incentives.count_documents({"staff_id": staff_id, "type": "bill_upload"})
            amount = _amount_for_slab(count_so_far, cfg["bill_upload_slabs"])
            status = _status_from_bill(bill_status)
            await _db.staff_incentives.insert_one({
                "id": str(uuid.uuid4()),
                "staff_id": staff_id,
                "staff_code": attribution["staff_code"],
                "customer_phone": customer_phone,
                "type": "bill_upload",
                "status": status,
                "amount": amount,
                "bill_id": bill_id,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "approved_at": datetime.now(timezone.utc).isoformat() if status == "redeemable" else None,
            })
            # Mark attribution as used
            await _db.staff_attributions.update_one({"id": attribution["id"]}, {"$set": {"used": True}})

    # 2. If bill approved, activate any pending registration incentive for this customer
    if bill_status in ("auto_approved", "approved"):
        pending_reg = await _db.staff_incentives.find_one({
            "customer_phone": customer_phone,
            "type": "registration",
            "status": "pending",
        }, {"_id": 0, "id": 1})
        if pending_reg:
            await _db.staff_incentives.update_one(
                {"id": pending_reg["id"]},
                {"$set": {"status": "redeemable", "approved_at": datetime.now(timezone.utc).isoformat()}}
            )


def _status_from_bill(bill_status: str) -> str:
    if bill_status in ("auto_approved", "approved"):
        return "redeemable"
    if bill_status in ("pending_review", "manual_review", "processing"):
        return "pending_verification"
    if bill_status == "rejected":
        return "cancelled"
    return "pending_verification"


async def sync_incentive_on_bill_status_change(bill_id: str, new_bill_status: str):
    """Called when a bill's status changes (approved by admin, force-credit, rejected).
    Updates any bill_upload incentive attached to this bill."""
    new_status = _status_from_bill(new_bill_status)
    r = await _db.staff_incentives.update_many(
        {"bill_id": bill_id, "type": "bill_upload", "status": {"$ne": new_status}},
        {"$set": {
            "status": new_status,
            "approved_at": datetime.now(timezone.utc).isoformat() if new_status == "redeemable" else None,
        }}
    )
    return r.modified_count


# ==================== STAFF: REDEEM (simple stub — deferred details) ====================

class StaffRedeemRequest(BaseModel):
    amount: float


@staff_router.post("/redeem")
async def staff_redeem(payload: StaffRedeemRequest, staff=Depends(_verify_staff)):
    # Sum current redeemable
    pipe = [
        {"$match": {"staff_id": staff["id"], "status": "redeemable"}},
        {"$group": {"_id": None, "total": {"$sum": "$amount"}}}
    ]
    total = 0
    async for r in _db.staff_incentives.aggregate(pipe):
        total = r["total"]
    if payload.amount <= 0 or payload.amount > total:
        raise HTTPException(status_code=400, detail=f"Amount exceeds redeemable balance (₹{total})")
    # Simple FIFO redemption
    ref = f"RDM-{uuid.uuid4().hex[:8].upper()}"
    remaining = payload.amount
    async for inc in _db.staff_incentives.find(
        {"staff_id": staff["id"], "status": "redeemable"}, {"_id": 0}
    ).sort("created_at", 1):
        if remaining <= 0:
            break
        take = min(inc["amount"], remaining)
        # For MVP: mark full incentive as redeemed if fully consumed, else create adjustment
        if take >= inc["amount"]:
            await _db.staff_incentives.update_one(
                {"id": inc["id"]},
                {"$set": {"status": "redeemed", "redeemed_at": datetime.now(timezone.utc).isoformat(),
                          "redemption_ref": ref}}
            )
            remaining -= inc["amount"]
    await _db.staff_redemptions.insert_one({
        "id": str(uuid.uuid4()),
        "reference": ref,
        "staff_id": staff["id"],
        "amount": payload.amount,
        "status": "requested",
        "requested_at": datetime.now(timezone.utc).isoformat(),
    })
    return {"success": True, "reference": ref, "amount": payload.amount}


@staff_router.get("/redemptions")
async def staff_redemption_history(staff=Depends(_verify_staff)):
    rows = []
    async for r in _db.staff_redemptions.find({"staff_id": staff["id"]}, {"_id": 0}).sort("requested_at", -1):
        rows.append(r)
    return {"redemptions": rows}
