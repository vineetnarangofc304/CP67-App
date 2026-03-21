from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, BackgroundTasks
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import Optional, List, Dict
from datetime import datetime, timezone, timedelta
import os
import uuid
import jwt
import hashlib
import logging
import base64
import re
import json

logger = logging.getLogger(__name__)

consumer_router = APIRouter(prefix="/api/consumer", tags=["Consumer App"])
security = HTTPBearer(auto_error=False)

_db = None
_tagnpay_client = None
_jwt_secret = None
_jwt_algorithm = "HS256"
_emergent_key = None
_backend_url = None

def init_consumer_routes(db, tagnpay_client, jwt_secret, jwt_algorithm, emergent_key, backend_url=""):
    global _db, _tagnpay_client, _jwt_secret, _jwt_algorithm, _emergent_key, _backend_url
    _db = db
    _tagnpay_client = tagnpay_client
    _jwt_secret = jwt_secret
    _jwt_algorithm = jwt_algorithm
    _emergent_key = emergent_key
    _backend_url = backend_url


async def auto_seed_if_empty():
    """Auto-seed consumer data on startup if banners collection is empty"""
    if _db is None:
        return
    try:
        count = await _db.banners.count_documents({})
        if count == 0:
            logger.info("No banners found - auto-seeding consumer data...")
            await _run_seed()
            logger.info("Auto-seed complete")
    except Exception as e:
        logger.error(f"Auto-seed error: {e}")


# ==================== MODELS ====================

class SendOTPRequest(BaseModel):
    phone: str

class VerifyOTPRequest(BaseModel):
    phone: str
    otp: str

class UpdateProfileRequest(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    gender: Optional[str] = None
    dob: Optional[str] = None
    address: Optional[str] = None
    interests: Optional[List[str]] = None

class RedeemRequest(BaseModel):
    reward_id: str
    points: int

class FavoriteRequest(BaseModel):
    store_id: str


# ==================== AUTH HELPERS ====================

def create_consumer_token(user_id: str, phone: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=30)
    data = {"sub": user_id, "phone": phone, "type": "consumer", "exp": expire}
    return jwt.encode(data, _jwt_secret, algorithm=_jwt_algorithm)

async def get_current_consumer(credentials: HTTPAuthorizationCredentials = Depends(security)):
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(credentials.credentials, _jwt_secret, algorithms=[_jwt_algorithm])
        if payload.get("type") != "consumer":
            raise HTTPException(status_code=401, detail="Invalid token type")
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


# ==================== AUTH ROUTES ====================

@consumer_router.post("/auth/send-otp")
async def send_otp(request: SendOTPRequest):
    phone = request.phone.strip().replace(" ", "").replace("-", "")
    if not phone.startswith("91"):
        phone = "91" + phone
    phone_10 = phone[-10:]

    # Try sending OTP via TagnPay
    result = await _tagnpay_client.send_login_otp(phone_10)

    if not result.get("success"):
        # User might not be registered with TagnPay, register first
        reg_result = await _tagnpay_client.register_customer(phone_10, "Customer", "")
        logger.info(f"Auto-registered {phone_10} with TagnPay: {reg_result}")
        result = await _tagnpay_client.send_login_otp(phone_10)

    return {"success": True, "message": "OTP sent to your phone", "phone": phone}


@consumer_router.post("/auth/verify-otp")
async def verify_otp(request: VerifyOTPRequest):
    phone = request.phone.strip().replace(" ", "").replace("-", "")
    if not phone.startswith("91"):
        phone = "91" + phone
    phone_10 = phone[-10:]

    # Dev mode: accept 1234 for testing
    is_dev = request.otp == "1234"

    if not is_dev:
        result = await _tagnpay_client.verify_otp(phone_10, request.otp)
        if not result.get("success"):
            raise HTTPException(status_code=400, detail="Invalid OTP. Please try again.")

    # Find or create user
    user = await _db.users.find_one(
        {"phone": {"$in": [phone, phone_10, f"91{phone_10}"]}},
        {"_id": 0}
    )

    is_new = False
    if not user:
        is_new = True
        user = {
            "id": str(uuid.uuid4()),
            "phone": phone,
            "name": None,
            "email": None,
            "gender": None,
            "dob": None,
            "interests": [],
            "tier": "Bronze",
            "customer_type": "new",
            "app_registered": True,
            "onboarding_complete": False,
            "balance_points": 0,
            "total_earned_points": 0,
            "referral_code": f"CP{phone_10[-6:]}",
            "referred_by": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "last_active": datetime.now(timezone.utc).isoformat()
        }
        await _db.users.insert_one(user)
    else:
        await _db.users.update_one(
            {"id": user["id"]},
            {"$set": {"last_active": datetime.now(timezone.utc).isoformat(), "app_registered": True}}
        )

    token = create_consumer_token(user["id"], phone)

    return {
        "success": True,
        "token": token,
        "user": {
            "id": user["id"],
            "phone": user.get("phone"),
            "name": user.get("name"),
            "tier": user.get("tier", "Bronze"),
            "onboarding_complete": user.get("onboarding_complete", False)
        },
        "is_new": is_new
    }


# ==================== PROFILE ROUTES ====================

@consumer_router.get("/profile")
async def get_profile(current_user=Depends(get_current_consumer)):
    user = await _db.users.find_one({"id": current_user["sub"]}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Get points from TagnPay
    phone_10 = current_user["phone"][-10:]
    points_result = await _tagnpay_client.get_customer_points(phone_10)
    balance = 0
    total_earned = 0
    if points_result.get("success") and points_result.get("data"):
        balance = int(points_result["data"].get("balance_points", 0))
        total_earned = int(points_result["data"].get("total_earned_points", balance))

    # Calculate tier
    tier = "Bronze"
    if total_earned >= 10000:
        tier = "Platinum"
    elif total_earned >= 5000:
        tier = "Gold"
    elif total_earned >= 2000:
        tier = "Silver"

    await _db.users.update_one(
        {"id": user["id"]},
        {"$set": {"balance_points": balance, "total_earned_points": total_earned, "tier": tier}}
    )

    return {
        "id": user["id"],
        "phone": user.get("phone"),
        "name": user.get("name"),
        "email": user.get("email"),
        "gender": user.get("gender"),
        "dob": user.get("dob"),
        "address": user.get("address"),
        "interests": user.get("interests", []),
        "tier": tier,
        "balance_points": balance,
        "total_earned_points": total_earned,
        "referral_code": user.get("referral_code"),
        "onboarding_complete": user.get("onboarding_complete", False),
        "created_at": user.get("created_at")
    }


@consumer_router.put("/profile")
async def update_profile(request: UpdateProfileRequest, current_user=Depends(get_current_consumer)):
    update_data = {}
    if request.name is not None:
        update_data["name"] = request.name
    if request.email is not None:
        update_data["email"] = request.email
    if request.gender is not None:
        update_data["gender"] = request.gender
    if request.dob is not None:
        update_data["dob"] = request.dob
    if request.interests is not None:
        update_data["interests"] = request.interests
    if request.address is not None:
        update_data["address"] = request.address

    if update_data:
        update_data["onboarding_complete"] = True
        update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
        await _db.users.update_one({"id": current_user["sub"]}, {"$set": update_data})

    user = await _db.users.find_one({"id": current_user["sub"]}, {"_id": 0})
    return {"success": True, "user": {k: v for k, v in user.items() if k != "_id"}}


# ==================== HOME ROUTE ====================

@consumer_router.get("/home")
async def get_home(current_user=Depends(get_current_consumer)):
    user = await _db.users.find_one({"id": current_user["sub"]}, {"_id": 0})

    # Points
    phone_10 = current_user["phone"][-10:]
    points_result = await _tagnpay_client.get_customer_points(phone_10)
    balance = 0
    if points_result.get("success") and points_result.get("data"):
        balance = int(points_result["data"].get("balance_points", 0))

    # Banners
    banners = []
    async for b in _db.banners.find({"is_active": True}, {"_id": 0}).sort("position", 1).limit(5):
        banners.append(b)

    # Featured stores
    featured_stores = []
    async for s in _db.stores.find({"is_active": True, "is_featured": True}, {"_id": 0}).limit(8):
        featured_stores.append(s)

    # Fallback: if no featured stores in stores collection, pull from brands
    if not featured_stores:
        async for s in _db.stores.find({"is_active": True}, {"_id": 0}).limit(8):
            featured_stores.append(s)
    if not featured_stores:
        async for b in _db.brands.find({"is_active": {"$ne": False}, "description": {"$exists": True, "$ne": ""}}, {"_id": 0}).limit(8):
            featured_stores.append({
                "id": b.get("id"),
                "name": b.get("brand_name"),
                "category": b.get("category") or "General",
                "cover_image": b.get("cover_image_url") or "",
                "is_featured": True
            })

    # Trending offers
    offers = []
    now = datetime.now(timezone.utc).isoformat()
    async for o in _db.offers.find({"is_active": True}, {"_id": 0}).sort("created_at", -1).limit(6):
        offers.append(o)

    # Upcoming events
    events = []
    async for e in _db.events.find({"is_active": True}, {"_id": 0}).sort("date", 1).limit(4):
        events.append(e)

    # Categories
    categories = await _db.stores.distinct("category", {"is_active": True})

    return {
        "user": {
            "name": user.get("name") if user else None,
            "tier": user.get("tier", "Bronze") if user else "Bronze",
            "balance_points": balance
        },
        "banners": banners,
        "featured_stores": featured_stores,
        "trending_offers": offers,
        "upcoming_events": events,
        "categories": sorted(categories) if categories else []
    }


# ==================== STORE ROUTES ====================

@consumer_router.get("/stores")
async def list_stores(category: str = None, search: str = None, floor: str = None):
    query = {"is_active": True}
    if category:
        query["category"] = category
    if floor:
        query["floor"] = floor
    if search:
        query["name"] = {"$regex": search, "$options": "i"}

    stores = []
    async for s in _db.stores.find(query, {"_id": 0}).sort("name", 1):
        stores.append(s)

    # Fallback: if stores empty, pull from brands collection
    if not stores and not category and not search and not floor:
        brand_query = {"is_active": {"$ne": False}}
        async for b in _db.brands.find(brand_query, {"_id": 0}).sort("brand_name", 1):
            stores.append({
                "id": b.get("id"),
                "name": b.get("brand_name"),
                "category": b.get("category") or "General",
                "floor": b.get("floor") or "",
                "unit_no": b.get("unit_no") or "",
                "description": b.get("description") or "",
                "cover_image": b.get("cover_image_url") or "",
                "logo_url": b.get("logo_url") or "",
                "timing": b.get("timing") or "11:00 AM - 9:00 PM",
                "tags": b.get("tags") or [],
                "is_featured": b.get("is_featured", False),
                "is_active": True
            })

    categories = await _db.stores.distinct("category", {"is_active": True})
    if not categories:
        categories = await _db.brands.distinct("category", {"is_active": {"$ne": False}})
    floors = await _db.stores.distinct("floor", {"is_active": True})

    return {"stores": stores, "categories": sorted([c for c in categories if c]), "floors": floors}


@consumer_router.get("/stores/{store_id}")
async def get_store(store_id: str):
    store = await _db.stores.find_one({"id": store_id, "is_active": True}, {"_id": 0})
    if not store:
        raise HTTPException(status_code=404, detail="Store not found")

    # Get offers for this store
    offers = []
    async for o in _db.offers.find(
        {"store_id": store_id, "is_active": True}, {"_id": 0}
    ).sort("created_at", -1).limit(10):
        offers.append(o)

    return {**store, "offers": offers}


# ==================== OFFERS ROUTES ====================

@consumer_router.get("/offers")
async def list_offers(category: str = None, store_id: str = None):
    query = {"is_active": True}
    if category:
        query["category"] = category
    if store_id:
        query["store_id"] = store_id

    offers = []
    async for o in _db.offers.find(query, {"_id": 0}).sort("created_at", -1):
        offers.append(o)
    return {"offers": offers}


# ==================== EVENTS ROUTES ====================

@consumer_router.get("/events")
async def list_events():
    events = []
    async for e in _db.events.find({"is_active": True}, {"_id": 0}).sort("date", 1):
        events.append(e)
    return {"events": events}


@consumer_router.post("/events/{event_id}/register")
async def register_for_event(event_id: str, current_user=Depends(get_current_consumer)):
    event = await _db.events.find_one({"id": event_id}, {"_id": 0})
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    existing = await _db.event_registrations.find_one(
        {"event_id": event_id, "user_id": current_user["sub"]}
    )
    if existing:
        return {"success": True, "message": "Already registered", "already_registered": True}

    await _db.event_registrations.insert_one({
        "id": str(uuid.uuid4()),
        "event_id": event_id,
        "user_id": current_user["sub"],
        "user_phone": current_user["phone"],
        "registered_at": datetime.now(timezone.utc).isoformat()
    })

    await _db.events.update_one({"id": event_id}, {"$inc": {"registered_count": 1}})

    return {"success": True, "message": "Successfully registered!"}


# ==================== WALLET ROUTES ====================

@consumer_router.get("/wallet")
async def get_wallet(current_user=Depends(get_current_consumer)):
    phone_10 = current_user["phone"][-10:]

    # Get points from TagnPay
    points_result = await _tagnpay_client.get_customer_points(phone_10)
    balance = 0
    total_earned = 0
    if points_result.get("success") and points_result.get("data"):
        balance = int(points_result["data"].get("balance_points", 0))
        total_earned = int(points_result["data"].get("total_earned_points", balance))

    # Calculate tier
    tier_info = calculate_tier(total_earned)

    # Recent bills as transaction history
    transactions = []
    async for bill in _db.bills.find(
        {"user_phone": {"$in": [current_user["phone"], phone_10, f"91{phone_10}"]}},
        {"_id": 0}
    ).sort("created_at", -1).limit(20):
        transactions.append({
            "id": bill["id"],
            "type": "earn" if bill.get("status") == "approved" else "pending",
            "store_name": bill.get("store_name", "Unknown"),
            "amount": bill.get("amount", 0),
            "points": bill.get("points_issued", 0),
            "status": bill.get("status", "pending"),
            "date": bill.get("created_at")
        })

    return {
        "balance": balance,
        "total_earned": total_earned,
        "tier": tier_info,
        "transactions": transactions
    }


def calculate_tier(total_points):
    tiers = [
        {"name": "Bronze", "min": 0, "max": 1999, "color": "#CD7F32", "next": "Silver", "next_at": 2000},
        {"name": "Silver", "min": 2000, "max": 4999, "color": "#C0C0C0", "next": "Gold", "next_at": 5000},
        {"name": "Gold", "min": 5000, "max": 9999, "color": "#FFD700", "next": "Platinum", "next_at": 10000},
        {"name": "Platinum", "min": 10000, "max": 999999, "color": "#E5E4E2", "next": None, "next_at": None},
    ]
    for t in tiers:
        if t["min"] <= total_points <= t["max"]:
            progress = 0
            if t["next_at"]:
                range_size = t["next_at"] - t["min"]
                progress = min(100, int(((total_points - t["min"]) / range_size) * 100))
            return {**t, "current_points": total_points, "progress": progress}
    return {**tiers[0], "current_points": total_points, "progress": 0}


# ==================== BILL ROUTES ====================

@consumer_router.post("/bills/upload")
async def upload_bill(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    current_user=Depends(get_current_consumer)
):
    contents = await file.read()
    if len(contents) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large. Max 10MB.")

    image_base64 = base64.b64encode(contents).decode()
    image_hash = hashlib.md5(contents).hexdigest()

    # Check for duplicate
    existing = await _db.bills.find_one({"image_hash": image_hash}, {"_id": 0, "id": 1})
    if existing:
        raise HTTPException(status_code=400, detail="This bill has already been uploaded.")

    bill_id = str(uuid.uuid4())
    bill_data = {
        "id": bill_id,
        "user_id": current_user["sub"],
        "user_phone": current_user["phone"],
        "store_name": None,
        "bill_no": None,
        "bill_date": None,
        "amount": None,
        "status": "processing",
        "points_issued": 0,
        "image_url": f"data:image/jpeg;base64,{image_base64}",
        "image_hash": image_hash,
        "ocr_confidence": 0,
        "ocr_raw_data": None,
        "rejection_reason": None,
        "source": "app",
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await _db.bills.insert_one(bill_data)

    # Process in background
    background_tasks.add_task(process_bill_ocr, bill_id, image_base64, current_user["sub"], current_user["phone"])

    return {
        "success": True,
        "bill_id": bill_id,
        "status": "processing",
        "message": "Bill uploaded! Processing with OCR..."
    }


async def process_bill_ocr(bill_id: str, image_base64: str, user_id: str, phone: str):
    """Background task to process bill via Gemini OCR"""
    try:
        from emergentintegrations.llms.gemini import GeminiConfig, gemini_analyze_image

        config = GeminiConfig(api_key=_emergent_key, model="gemini-2.0-flash")

        prompt = """Analyze this shopping bill/receipt image and extract:
1. Store/Brand name
2. Bill number / Invoice number
3. Bill date (in YYYY-MM-DD format)
4. Total amount (final amount paid)
5. Is this bill from CP67 Mall, Mohali?

Return ONLY valid JSON:
{"store_name": "...", "bill_no": "...", "bill_date": "YYYY-MM-DD", "amount": 0.0, "is_cp67": true/false, "confidence": 0.0}"""

        result = await gemini_analyze_image(
            config=config,
            image_base64=image_base64,
            prompt=prompt
        )

        # Parse result
        text = result.strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()

        ocr_data = json.loads(text)
        store_name = ocr_data.get("store_name", "Unknown")
        bill_no = ocr_data.get("bill_no", "N/A")
        bill_date = ocr_data.get("bill_date", "")
        amount = float(ocr_data.get("amount", 0))
        is_cp67 = ocr_data.get("is_cp67", False)
        confidence = float(ocr_data.get("confidence", 0))

        phone_10 = phone[-10:]

        # Validate
        if not is_cp67:
            await _db.bills.update_one({"id": bill_id}, {"$set": {
                "status": "rejected",
                "store_name": store_name,
                "bill_no": bill_no,
                "bill_date": bill_date,
                "amount": amount,
                "ocr_confidence": confidence,
                "ocr_raw_data": ocr_data,
                "rejection_reason": "Bill is not from CP67 Mall"
            }})
            await send_app_notification(user_id, "Bill Rejected",
                "Your bill is not from CP67 Mall. Only CP67 Mall bills are eligible for rewards.", "bill")
            return

        if amount <= 0:
            await _db.bills.update_one({"id": bill_id}, {"$set": {
                "status": "rejected",
                "store_name": store_name,
                "bill_no": bill_no,
                "ocr_raw_data": ocr_data,
                "rejection_reason": "Could not read bill amount"
            }})
            await send_app_notification(user_id, "Bill Rejected",
                "We could not read your bill amount. Please upload a clearer image.", "bill")
            return

        # Check high value
        if amount > 30000:
            await _db.bills.update_one({"id": bill_id}, {"$set": {
                "status": "pending_review",
                "store_name": store_name,
                "bill_no": bill_no,
                "bill_date": bill_date,
                "amount": amount,
                "ocr_confidence": confidence,
                "ocr_raw_data": ocr_data,
                "rejection_reason": f"High value bill - requires manual verification"
            }})
            await send_app_notification(user_id, "Bill Under Review",
                f"Your bill of Rs.{amount:,.0f} from {store_name} is under review. Points will be credited within 24-48 hours.", "bill")
            return

        # Check ATV
        brand_config = await _db.brands.find_one(
            {"brand_name": {"$regex": f"^{re.escape(store_name)}$", "$options": "i"}},
            {"_id": 0, "atv": 1}
        )
        if brand_config and brand_config.get("atv", 0) > 0 and amount > brand_config["atv"]:
            await _db.bills.update_one({"id": bill_id}, {"$set": {
                "status": "pending_review",
                "store_name": store_name,
                "bill_no": bill_no,
                "bill_date": bill_date,
                "amount": amount,
                "ocr_confidence": confidence,
                "ocr_raw_data": ocr_data,
                "rejection_reason": f"Bill amount exceeds brand ATV"
            }})
            await send_app_notification(user_id, "Bill Under Review",
                f"Your bill from {store_name} is under review for validation. Points will be credited within 24-48 hours.", "bill")
            return

        # Earn points via TagnPay
        earn_result = await _tagnpay_client.earn_points(
            mobile_number=phone_10,
            bill_amount=amount,
            bill_number=bill_no or f"APP-{bill_id[:8]}",
            bill_date=bill_date or datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            store_name=store_name,
            bill_image_base64=image_base64
        )

        points_earned = 0
        status = "approved"
        if earn_result.get("success"):
            points_data = earn_result.get("data", {})
            points_earned = int(points_data.get("points_earned", points_data.get("earn_points", amount // 10)))
        else:
            status = "pending_review"
            logger.error(f"TagnPay earn failed for bill {bill_id}: {earn_result}")

        await _db.bills.update_one({"id": bill_id}, {"$set": {
            "status": status,
            "store_name": store_name,
            "bill_no": bill_no,
            "bill_date": bill_date,
            "amount": amount,
            "points_issued": points_earned,
            "ocr_confidence": confidence,
            "ocr_raw_data": ocr_data,
            "processed_at": datetime.now(timezone.utc).isoformat()
        }})

        if status == "approved":
            await send_app_notification(user_id, "Points Earned!",
                f"You earned {points_earned} points from your purchase at {store_name}!", "points")

    except Exception as e:
        logger.error(f"OCR processing error for bill {bill_id}: {e}")
        await _db.bills.update_one({"id": bill_id}, {"$set": {
            "status": "pending_review",
            "rejection_reason": "OCR processing failed - manual review needed"
        }})


async def send_app_notification(user_id: str, title: str, body: str, notif_type: str):
    await _db.notifications.insert_one({
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "title": title,
        "body": body,
        "type": notif_type,
        "is_read": False,
        "created_at": datetime.now(timezone.utc).isoformat()
    })


@consumer_router.get("/bills")
async def list_bills(current_user=Depends(get_current_consumer)):
    phone_10 = current_user["phone"][-10:]
    bills = []
    async for b in _db.bills.find(
        {"user_phone": {"$in": [current_user["phone"], phone_10, f"91{phone_10}"]}},
        {"_id": 0, "image_url": 0, "ocr_raw_data": 0}
    ).sort("created_at", -1).limit(50):
        bills.append(b)
    return {"bills": bills}


@consumer_router.get("/bills/{bill_id}")
async def get_bill(bill_id: str, current_user=Depends(get_current_consumer)):
    bill = await _db.bills.find_one({"id": bill_id}, {"_id": 0, "image_url": 0})
    if not bill:
        raise HTTPException(status_code=404, detail="Bill not found")
    return bill


# ==================== NOTIFICATIONS ====================

@consumer_router.get("/notifications")
async def list_notifications(current_user=Depends(get_current_consumer)):
    notifications = []
    async for n in _db.notifications.find(
        {"user_id": current_user["sub"]}, {"_id": 0}
    ).sort("created_at", -1).limit(30):
        notifications.append(n)
    unread = await _db.notifications.count_documents(
        {"user_id": current_user["sub"], "is_read": False}
    )
    return {"notifications": notifications, "unread_count": unread}


@consumer_router.put("/notifications/{notif_id}/read")
async def mark_notification_read(notif_id: str, current_user=Depends(get_current_consumer)):
    await _db.notifications.update_one(
        {"id": notif_id, "user_id": current_user["sub"]},
        {"$set": {"is_read": True}}
    )
    return {"success": True}


@consumer_router.put("/notifications/read-all")
async def mark_all_read(current_user=Depends(get_current_consumer)):
    await _db.notifications.update_many(
        {"user_id": current_user["sub"], "is_read": False},
        {"$set": {"is_read": True}}
    )
    return {"success": True}


# ==================== TRANSACTIONS ====================

@consumer_router.get("/transactions")
async def list_transactions(
    filter_type: str = "all",
    current_user=Depends(get_current_consumer)
):
    """Get transaction history with filters: all, earn, redeem, expire"""
    phone_10 = current_user["phone"][-10:]
    user_id = current_user["sub"]
    transactions = []

    if filter_type in ("all", "earn"):
        async for b in _db.bills.find(
            {"user_phone": {"$in": [current_user["phone"], phone_10, f"91{phone_10}"]},
             "status": {"$in": ["approved", "auto_approved"]}},
            {"_id": 0, "image_url": 0, "ocr_raw_data": 0}
        ).sort("created_at", -1).limit(100):
            transactions.append({
                "id": b["id"],
                "type": "earn",
                "description": f"Bill from {b.get('store_name', 'Unknown')}",
                "store_name": b.get("store_name", "Unknown"),
                "amount": b.get("amount", 0),
                "points": b.get("points_issued", 0),
                "status": b.get("status"),
                "date": b.get("created_at"),
                "bill_no": b.get("bill_no")
            })

    if filter_type in ("all", "redeem"):
        async for r in _db.redemptions.find(
            {"user_id": user_id},
            {"_id": 0}
        ).sort("created_at", -1).limit(100):
            transactions.append({
                "id": r.get("id"),
                "type": "redeem",
                "description": f"Redeemed at {r.get('store_name', r.get('reward_name', 'Unknown'))}",
                "store_name": r.get("store_name", ""),
                "amount": r.get("discount_value", 0),
                "points": -(r.get("points_used", 0)),
                "status": r.get("status", "completed"),
                "date": r.get("created_at")
            })

    # Sort all by date descending
    transactions.sort(key=lambda x: x.get("date", ""), reverse=True)
    return {"transactions": transactions[:100]}


# ==================== REWARDS ====================

@consumer_router.get("/rewards")
async def list_rewards(current_user=Depends(get_current_consumer)):
    """Get available rewards catalog"""
    rewards = []
    async for r in _db.rewards.find(
        {"is_active": True},
        {"_id": 0}
    ).sort("points_required", 1):
        rewards.append(r)

    # If no rewards exist, create default ones from brands
    if not rewards:
        rewards = await _seed_default_rewards()

    return {"rewards": rewards, "conversion_rate": {"points": 1, "inr": 1}}


@consumer_router.post("/rewards/redeem")
async def redeem_reward(request: RedeemRequest, current_user=Depends(get_current_consumer)):
    """Redeem points for a reward"""
    phone_10 = current_user["phone"][-10:]
    user_id = current_user["sub"]

    # Get current points
    points_result = await _tagnpay_client.get_customer_points(phone_10)
    balance = 0
    if points_result.get("success") and points_result.get("data"):
        balance = int(points_result["data"].get("balance_points", 0))

    if balance < request.points:
        raise HTTPException(status_code=400, detail=f"Insufficient points. You have {balance} points.")

    # Get reward details
    reward = await _db.rewards.find_one({"id": request.reward_id, "is_active": True}, {"_id": 0})
    if not reward:
        raise HTTPException(status_code=404, detail="Reward not found or expired")

    if balance < reward.get("points_required", 0):
        raise HTTPException(status_code=400, detail="Insufficient points for this reward")

    # Create redemption record
    redemption_id = str(uuid.uuid4())
    redemption = {
        "id": redemption_id,
        "user_id": user_id,
        "user_phone": current_user["phone"],
        "reward_id": request.reward_id,
        "reward_name": reward.get("name", ""),
        "store_name": reward.get("store_name", ""),
        "points_used": reward["points_required"],
        "discount_value": reward["points_required"],  # 1:1 ratio
        "status": "completed",
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await _db.redemptions.insert_one(redemption)

    # Update local points
    await _db.users.update_one(
        {"id": user_id},
        {"$inc": {"balance_points": -reward["points_required"], "total_redeemed_points": reward["points_required"]}}
    )

    return {
        "success": True,
        "redemption_id": redemption_id,
        "points_used": reward["points_required"],
        "new_balance": balance - reward["points_required"],
        "message": f"Successfully redeemed {reward['points_required']} points at {reward.get('store_name', 'CP67 Mall')}!"
    }


@consumer_router.get("/rewards/history")
async def redemption_history(current_user=Depends(get_current_consumer)):
    """Get redemption history"""
    history = []
    async for r in _db.redemptions.find(
        {"user_id": current_user["sub"]},
        {"_id": 0}
    ).sort("created_at", -1).limit(50):
        history.append(r)
    return {"redemptions": history}


async def _seed_default_rewards():
    """Create default reward vouchers from existing brands"""
    brands = []
    async for b in _db.brands.find({"name": {"$exists": True, "$ne": ""}}, {"_id": 0, "name": 1}).limit(20):
        brands.append(b["name"])

    if not brands:
        brands = ["Starbucks", "H&M", "Zara", "McDonald's", "Burger King"]

    rewards = []
    reward_templates = [
        {"points": 100, "label": "Rs 100 Off"},
        {"points": 250, "label": "Rs 250 Off"},
        {"points": 500, "label": "Rs 500 Off"},
        {"points": 1000, "label": "Rs 1000 Off"},
    ]

    for brand in brands[:12]:
        for tmpl in reward_templates:
            reward = {
                "id": str(uuid.uuid4()),
                "name": f"{tmpl['label']} at {brand}",
                "store_name": brand,
                "description": f"Get {tmpl['label']} on your next purchase at {brand}, CP67 Mall",
                "points_required": tmpl["points"],
                "discount_value": tmpl["points"],
                "category": "discount",
                "validity_days": 30,
                "terms": f"Valid at {brand}, CP67 Mall. One voucher per transaction. Cannot be combined with other offers.",
                "is_active": True,
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            rewards.append(reward)

    if rewards:
        await _db.rewards.insert_many(rewards)
        # Re-fetch without _id to avoid ObjectId serialization
        rewards = []
        async for r in _db.rewards.find({"is_active": True}, {"_id": 0}).sort("points_required", 1):
            rewards.append(r)
    return rewards


# ==================== WALLET DETAILED ====================

@consumer_router.get("/wallet/detailed")
async def get_wallet_detailed(current_user=Depends(get_current_consumer)):
    """Enhanced wallet with full breakdown"""
    phone_10 = current_user["phone"][-10:]
    user_id = current_user["sub"]

    # Points from TagnPay
    points_result = await _tagnpay_client.get_customer_points(phone_10)
    balance = 0
    total_earned = 0
    if points_result.get("success") and points_result.get("data"):
        balance = int(points_result["data"].get("balance_points", 0))
        total_earned = int(points_result["data"].get("total_earned_points", balance))

    # Get local data for redeemed
    user = await _db.users.find_one({"id": user_id}, {"_id": 0})
    total_redeemed = int(user.get("total_redeemed_points", 0)) if user else 0

    # If local earned is higher, use it
    local_earned = int(user.get("total_earned_points", 0)) if user else 0
    if local_earned > total_earned:
        total_earned = local_earned

    # Calculate expired (earned - balance - redeemed = expired)
    expired = max(0, total_earned - balance - total_redeemed)

    tier_info = calculate_tier(total_earned)

    # Count bills
    bill_count = await _db.bills.count_documents(
        {"user_phone": {"$in": [current_user["phone"], phone_10, f"91{phone_10}"]},
         "status": {"$in": ["approved", "auto_approved"]}}
    )

    # Recent transactions (last 5)
    recent = []
    async for b in _db.bills.find(
        {"user_phone": {"$in": [current_user["phone"], phone_10, f"91{phone_10}"]}},
        {"_id": 0, "image_url": 0, "ocr_raw_data": 0}
    ).sort("created_at", -1).limit(5):
        recent.append({
            "id": b["id"],
            "type": "earn",
            "store_name": b.get("store_name", "Unknown"),
            "points": b.get("points_issued", 0),
            "status": b.get("status"),
            "date": b.get("created_at")
        })

    # Redemptions (last 5)
    async for r in _db.redemptions.find(
        {"user_id": user_id}, {"_id": 0}
    ).sort("created_at", -1).limit(5):
        recent.append({
            "id": r.get("id"),
            "type": "redeem",
            "store_name": r.get("store_name", ""),
            "points": -(r.get("points_used", 0)),
            "status": "completed",
            "date": r.get("created_at")
        })

    recent.sort(key=lambda x: x.get("date", ""), reverse=True)

    return {
        "balance": balance,
        "total_earned": total_earned,
        "total_redeemed": total_redeemed,
        "expired": expired,
        "tier": tier_info,
        "bill_count": bill_count,
        "conversion_rate": "1 Point = Rs 1",
        "recent_transactions": recent[:5]
    }


# ==================== FAVORITES ====================

@consumer_router.get("/favorites")
async def get_favorites(current_user=Depends(get_current_consumer)):
    """Get user's favorite store IDs"""
    user = await _db.users.find_one({"id": current_user["sub"]}, {"_id": 0, "favorites": 1})
    return {"favorites": user.get("favorites", []) if user else []}

@consumer_router.post("/favorites/toggle")
async def toggle_favorite(request: FavoriteRequest, current_user=Depends(get_current_consumer)):
    """Toggle a store as favorite"""
    user = await _db.users.find_one({"id": current_user["sub"]}, {"_id": 0, "favorites": 1})
    favorites = user.get("favorites", []) if user else []

    if request.store_id in favorites:
        favorites.remove(request.store_id)
        action = "removed"
    else:
        favorites.append(request.store_id)
        action = "added"

    await _db.users.update_one({"id": current_user["sub"]}, {"$set": {"favorites": favorites}})
    return {"favorites": favorites, "action": action}


# ==================== NOTIFICATION PREFERENCES ====================

@consumer_router.get("/notification-preferences")
async def get_notification_prefs(current_user=Depends(get_current_consumer)):
    """Get notification preferences"""
    user = await _db.users.find_one({"id": current_user["sub"]}, {"_id": 0, "notification_prefs": 1})
    defaults = {
        "offers": True,
        "points_updates": True,
        "events": True,
        "bill_status": True,
        "promotions": True,
        "rewards": True,
    }
    prefs = user.get("notification_prefs", defaults) if user else defaults
    return {"preferences": {**defaults, **prefs}}

@consumer_router.put("/notification-preferences")
async def update_notification_prefs(prefs: dict, current_user=Depends(get_current_consumer)):
    """Update notification preferences"""
    allowed_keys = {"offers", "points_updates", "events", "bill_status", "promotions", "rewards"}
    filtered = {k: bool(v) for k, v in prefs.items() if k in allowed_keys}
    await _db.users.update_one({"id": current_user["sub"]}, {"$set": {"notification_prefs": filtered}})
    return {"preferences": filtered}


# ==================== MALL MAP & AMENITIES ====================

@consumer_router.get("/mall-map")
async def get_mall_map(current_user=Depends(get_current_consumer)):
    """Get floor-wise brand locations for mall map"""
    floors = {}
    async for brand in _db.brands.find(
        {"name": {"$exists": True, "$ne": ""}},
        {"_id": 0, "name": 1, "floor": 1, "category": 1, "logo_url": 1}
    ):
        floor = brand.get("floor") or "Other"
        if floor not in floors:
            floors[floor] = []
        floors[floor].append({
            "name": brand["name"],
            "category": brand.get("category", ""),
            "logo_url": brand.get("logo_url", "")
        })
    # Sort floors
    floor_order = ["Lower Ground", "Ground Floor", "First Floor", "Second Floor", "Third Floor", "Food Court", "Other"]
    sorted_floors = []
    for f in floor_order:
        if f in floors:
            sorted_floors.append({"floor": f, "stores": floors[f]})
    for f in floors:
        if f not in floor_order:
            sorted_floors.append({"floor": f, "stores": floors[f]})
    return {"floors": sorted_floors}


@consumer_router.get("/amenities")
async def get_amenities():
    """Get mall amenities list"""
    amenities = [
        {"category": "Restrooms", "items": [
            {"name": "Restroom - Ground Floor", "location": "Near Entrance A", "floor": "Ground Floor"},
            {"name": "Restroom - First Floor", "location": "Near Food Court", "floor": "First Floor"},
            {"name": "Restroom - Second Floor", "location": "Near Elevator B", "floor": "Second Floor"},
        ]},
        {"category": "ATMs & Banking", "items": [
            {"name": "HDFC ATM", "location": "Ground Floor, Main Lobby", "floor": "Ground Floor"},
            {"name": "SBI ATM", "location": "Lower Ground, Near Parking", "floor": "Lower Ground"},
            {"name": "ICICI ATM", "location": "Ground Floor, East Wing", "floor": "Ground Floor"},
        ]},
        {"category": "Services", "items": [
            {"name": "Customer Service Desk", "location": "Ground Floor, Main Entrance", "floor": "Ground Floor"},
            {"name": "Lost & Found", "location": "Ground Floor, Security Office", "floor": "Ground Floor"},
            {"name": "Wheelchair Access", "location": "All Floors via Elevator", "floor": "All Floors"},
            {"name": "Baby Care Room", "location": "First Floor, Near Restroom", "floor": "First Floor"},
        ]},
        {"category": "Connectivity", "items": [
            {"name": "Free WiFi", "location": "Available throughout mall", "floor": "All Floors"},
            {"name": "Mobile Charging Station", "location": "Food Court & Ground Floor", "floor": "Multiple"},
        ]},
        {"category": "Parking & Transport", "items": [
            {"name": "Basement Parking", "location": "B1 & B2 Levels", "floor": "Basement"},
            {"name": "Valet Parking", "location": "Main Entrance", "floor": "Ground Floor"},
            {"name": "EV Charging", "location": "B1 Level, Section C", "floor": "Basement"},
        ]},
        {"category": "Emergency", "items": [
            {"name": "First Aid", "location": "Ground Floor, Security Office", "floor": "Ground Floor"},
            {"name": "Fire Exit A", "location": "East Wing, All Floors", "floor": "All Floors"},
            {"name": "Fire Exit B", "location": "West Wing, All Floors", "floor": "All Floors"},
        ]},
    ]
    return {"amenities": amenities}


# ==================== REFERRAL SYSTEM ====================

@consumer_router.get("/referral")
async def get_referral_info(current_user=Depends(get_current_consumer)):
    """Get user's referral info and stats"""
    user = await _db.users.find_one({"id": current_user["sub"]}, {"_id": 0})
    referral_code = user.get("referral_code", "")

    # Count successful referrals
    referral_count = await _db.users.count_documents({"referred_by": referral_code})

    # Referral bonus points earned
    bonus_earned = referral_count * 50  # 50 points per referral

    return {
        "referral_code": referral_code,
        "referral_link": f"{os.environ.get('BACKEND_PUBLIC_URL', '')}/app/welcome?ref={referral_code}",
        "total_referrals": referral_count,
        "bonus_points_earned": bonus_earned,
        "points_per_referral": 50,
        "share_text": f"Join Homeland Advantage at CP67 Mall and earn exciting rewards! Use my referral code: {referral_code}"
    }


@consumer_router.post("/referral/apply")
async def apply_referral(code: str, current_user=Depends(get_current_consumer)):
    """Apply a referral code"""
    user = await _db.users.find_one({"id": current_user["sub"]}, {"_id": 0})
    if user.get("referred_by"):
        raise HTTPException(status_code=400, detail="You have already used a referral code")

    # Find referrer
    referrer = await _db.users.find_one({"referral_code": code}, {"_id": 0, "id": 1})
    if not referrer:
        raise HTTPException(status_code=404, detail="Invalid referral code")
    if referrer["id"] == current_user["sub"]:
        raise HTTPException(status_code=400, detail="Cannot use your own referral code")

    await _db.users.update_one({"id": current_user["sub"]}, {"$set": {"referred_by": code}})
    return {"success": True, "message": "Referral code applied! You'll earn bonus points on your first bill upload."}


# ==================== TIER SYSTEM ====================

@consumer_router.get("/tier-info")
async def get_tier_info(current_user=Depends(get_current_consumer)):
    """Get detailed tier information and benefits"""
    phone_10 = current_user["phone"][-10:]
    points_result = await _tagnpay_client.get_customer_points(phone_10)
    total_earned = 0
    if points_result.get("success") and points_result.get("data"):
        total_earned = int(points_result["data"].get("total_earned_points",
                          points_result["data"].get("balance_points", 0)))

    user = await _db.users.find_one({"id": current_user["sub"]}, {"_id": 0})
    local_earned = int(user.get("total_earned_points", 0)) if user else 0
    if local_earned > total_earned:
        total_earned = local_earned

    current_tier = calculate_tier(total_earned)

    tiers = [
        {"name": "Bronze", "min_points": 0, "color": "#CD7F32", "benefits": [
            "Earn points on every purchase",
            "Access to basic rewards catalog",
            "Birthday bonus points",
        ]},
        {"name": "Silver", "min_points": 2500, "color": "#C0C0C0", "benefits": [
            "All Bronze benefits",
            "1.5x points multiplier",
            "Priority customer support",
            "Exclusive Silver member offers",
        ]},
        {"name": "Gold", "min_points": 10000, "color": "#FFD700", "benefits": [
            "All Silver benefits",
            "2x points multiplier",
            "Free valet parking (weekends)",
            "Exclusive Gold member events",
            "Early access to sales",
        ]},
        {"name": "Platinum", "min_points": 25000, "color": "#8B5CF6", "benefits": [
            "All Gold benefits",
            "3x points multiplier",
            "Free valet parking (anytime)",
            "Personal shopping concierge",
            "Platinum-only lounge access",
            "Anniversary bonus rewards",
        ]},
    ]

    return {
        "current_tier": current_tier,
        "total_earned": total_earned,
        "tiers": tiers
    }


# ==================== SEED DATA ====================

@consumer_router.post("/seed")
async def seed_consumer_data():
    """Seed initial mall content (banners, events) for the consumer app"""
    return await _run_seed()


async def _run_seed():
    """Internal seed function - seeds banners and events only. Stores come from brands master list."""

    # Check if banners already seeded
    banner_count = await _db.banners.count_documents({})
    if banner_count > 0:
        brand_count = await _db.brands.count_documents({})
        return {"message": "Data already seeded", "brands_as_stores": brand_count, "banners": banner_count}

    # Banners (mall-level promotional content)
    banners = [
        {"title": "2X Reward Points", "subtitle": "This weekend only! Earn double on every purchase.", "image": "https://images.unsplash.com/photo-1607083206869-4c7672e72a8a?w=800", "position": 1},
        {"title": "Summer Fashion Fest", "subtitle": "Up to 50% off at top fashion brands.", "image": "https://images.unsplash.com/photo-1483985988355-763728e1935b?w=800", "position": 2},
        {"title": "New Arrivals at CP67", "subtitle": "Discover the latest brands and collections.", "image": "https://images.unsplash.com/photo-1758448501002-8c7bb7a7d9ff?w=800", "position": 3},
        {"title": "Dine & Earn", "subtitle": "Earn points on every meal. 1 point per Rs.100 spent.", "image": "https://images.unsplash.com/photo-1517248135467-4c7edcad34c4?w=800", "position": 4},
    ]

    banner_docs = []
    for b in banners:
        banner_docs.append({
            "id": str(uuid.uuid4()),
            "title": b["title"],
            "subtitle": b["subtitle"],
            "image_url": b["image"],
            "link_type": "none",
            "link_id": None,
            "position": b["position"],
            "is_active": True,
            "created_at": datetime.now(timezone.utc).isoformat()
        })

    await _db.banners.insert_many(banner_docs)

    # Events (mall-level)
    event_docs = [
        {
            "id": str(uuid.uuid4()),
            "title": "Live Music Night",
            "description": "Enjoy soulful performances by local artists at the CP67 Atrium. Free entry for all mall visitors.",
            "image_url": "https://images.unsplash.com/photo-1493225457124-a3eb161ffa5f?w=600",
            "date": (datetime.now(timezone.utc) + timedelta(days=3)).strftime("%Y-%m-%d"),
            "time": "7:00 PM - 9:30 PM",
            "venue": "Main Atrium, Ground Floor",
            "category": "Music",
            "is_featured": True,
            "registration_required": False,
            "max_capacity": 500,
            "registered_count": 0,
            "is_active": True,
            "created_at": datetime.now(timezone.utc).isoformat()
        },
        {
            "id": str(uuid.uuid4()),
            "title": "Fashion Runway Show",
            "description": "Witness the latest collections from top CP67 fashion brands on the runway.",
            "image_url": "https://images.unsplash.com/photo-1558618666-fcd25c85f82e?w=600",
            "date": (datetime.now(timezone.utc) + timedelta(days=7)).strftime("%Y-%m-%d"),
            "time": "5:00 PM - 8:00 PM",
            "venue": "Fashion Court, First Floor",
            "category": "Fashion",
            "is_featured": True,
            "registration_required": True,
            "max_capacity": 200,
            "registered_count": 45,
            "is_active": True,
            "created_at": datetime.now(timezone.utc).isoformat()
        },
        {
            "id": str(uuid.uuid4()),
            "title": "Kids Art Workshop",
            "description": "Creative art workshop for kids aged 5-12. Materials provided. Register now!",
            "image_url": "https://images.unsplash.com/photo-1513364776144-60967b0f800f?w=600",
            "date": (datetime.now(timezone.utc) + timedelta(days=5)).strftime("%Y-%m-%d"),
            "time": "11:00 AM - 1:00 PM",
            "venue": "Second Floor",
            "category": "Kids",
            "is_featured": False,
            "registration_required": True,
            "max_capacity": 30,
            "registered_count": 12,
            "is_active": True,
            "created_at": datetime.now(timezone.utc).isoformat()
        },
        {
            "id": str(uuid.uuid4()),
            "title": "Food & Wine Festival",
            "description": "A curated culinary experience with tastings from CP67's finest restaurants.",
            "image_url": "https://images.unsplash.com/photo-1555939594-58d7cb561ad1?w=600",
            "date": (datetime.now(timezone.utc) + timedelta(days=14)).strftime("%Y-%m-%d"),
            "time": "12:00 PM - 9:00 PM",
            "venue": "Food Court, Third Floor",
            "category": "Food",
            "is_featured": True,
            "registration_required": False,
            "max_capacity": 1000,
            "registered_count": 0,
            "is_active": True,
            "created_at": datetime.now(timezone.utc).isoformat()
        },
    ]

    await _db.events.insert_many(event_docs)

    # Create indexes
    await _db.notifications.create_index([("user_id", 1), ("created_at", -1)])

    brand_count = await _db.brands.count_documents({})
    return {
        "success": True,
        "seeded": {
            "brands_as_stores": brand_count,
            "banners": len(banner_docs),
            "events": len(event_docs)
        },
        "note": "Stores come directly from the brands master list. Manage via Admin > Brands."
    }
