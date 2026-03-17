from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, BackgroundTasks
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import Optional, List, Dict
from datetime import datetime, timezone, timedelta
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
    interests: Optional[List[str]] = None


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

    categories = await _db.stores.distinct("category", {"is_active": True})
    floors = await _db.stores.distinct("floor", {"is_active": True})

    return {"stores": stores, "categories": sorted(categories), "floors": floors}


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


# ==================== SEED DATA ====================

@consumer_router.post("/seed")
async def seed_consumer_data():
    """Seed initial data for the consumer app"""

    # Check if already seeded
    store_count = await _db.stores.count_documents({})
    if store_count > 0:
        return {"message": "Data already seeded", "stores": store_count}

    # Stores
    stores = [
        {"name": "Lifestyle", "category": "Fashion", "floor": "Ground Floor", "unit": "G-01", "timing": "11:00 AM - 9:30 PM",
         "description": "India's leading fashion destination with the latest trends in clothing, accessories, and beauty.",
         "tags": ["fashion", "clothing", "accessories", "beauty"], "is_featured": True,
         "cover_image": "https://images.unsplash.com/photo-1441986300917-64674bd600d8?w=600"},
        {"name": "GANT", "category": "Fashion", "floor": "First Floor", "unit": "F1-12", "timing": "11:00 AM - 9:00 PM",
         "description": "Premium American sportswear brand known for quality and effortless style.",
         "tags": ["fashion", "premium", "menswear", "casual"], "is_featured": True,
         "cover_image": "https://images.unsplash.com/photo-1490114538077-0a7f8cb49891?w=600"},
        {"name": "ONLY", "category": "Fashion", "floor": "First Floor", "unit": "F1-08", "timing": "11:00 AM - 9:00 PM",
         "description": "Trendy women's fashion brand with the latest collections.",
         "tags": ["fashion", "women", "trendy", "casual"], "is_featured": False,
         "cover_image": "https://images.unsplash.com/photo-1469334031218-e382a71b716b?w=600"},
        {"name": "KAZO", "category": "Fashion", "floor": "First Floor", "unit": "F1-15", "timing": "11:00 AM - 9:00 PM",
         "description": "Contemporary women's fashion brand offering chic and sophisticated designs.",
         "tags": ["fashion", "women", "contemporary", "chic"], "is_featured": True,
         "cover_image": "https://images.unsplash.com/photo-1558618666-fcd25c85f82e?w=600"},
        {"name": "Marks & Spencer", "category": "Fashion", "floor": "Ground Floor", "unit": "G-05", "timing": "11:00 AM - 9:30 PM",
         "description": "British multinational retailer known for quality clothing, food, and home products.",
         "tags": ["fashion", "food", "home", "british", "premium"], "is_featured": True,
         "cover_image": "https://images.unsplash.com/photo-1567401893414-76b7b1e5a7a5?w=600"},
        {"name": "Sephora", "category": "Beauty", "floor": "Ground Floor", "unit": "G-08", "timing": "11:00 AM - 9:30 PM",
         "description": "World's leading beauty retailer with premium cosmetics, skincare, and fragrances.",
         "tags": ["beauty", "cosmetics", "skincare", "premium"], "is_featured": True,
         "cover_image": "https://images.unsplash.com/photo-1596462502278-27bfdc403348?w=600"},
        {"name": "Bath & Body Works", "category": "Beauty", "floor": "Ground Floor", "unit": "G-10", "timing": "11:00 AM - 9:00 PM",
         "description": "Body care, hand soaps, candles and home fragrances.",
         "tags": ["beauty", "body care", "fragrances", "candles"], "is_featured": False,
         "cover_image": "https://images.unsplash.com/photo-1556228578-0d85b1a4d571?w=600"},
        {"name": "Starbucks", "category": "Food & Beverage", "floor": "Ground Floor", "unit": "G-15", "timing": "10:00 AM - 10:00 PM",
         "description": "World's favorite coffeehouse with premium coffee, teas, and snacks.",
         "tags": ["coffee", "beverages", "cafe", "snacks"], "is_featured": True,
         "cover_image": "https://images.unsplash.com/photo-1501339847302-ac426a4a7cbb?w=600"},
        {"name": "Nando's", "category": "Food & Beverage", "floor": "First Floor", "unit": "F1-22", "timing": "12:00 PM - 10:30 PM",
         "description": "Flame-grilled PERi-PERi chicken restaurant with Portuguese-African flavors.",
         "tags": ["restaurant", "chicken", "dining", "casual"], "is_featured": False,
         "cover_image": "https://images.unsplash.com/photo-1555939594-58d7cb561ad1?w=600"},
        {"name": "PVR INOX", "category": "Entertainment", "floor": "Third Floor", "unit": "F3-01", "timing": "9:00 AM - 12:00 AM",
         "description": "Premium multiplex cinema with the latest movies, IMAX, and 4DX experience.",
         "tags": ["cinema", "movies", "entertainment", "imax"], "is_featured": True,
         "cover_image": "https://images.unsplash.com/photo-1489599849927-2ee91cede3ba?w=600"},
        {"name": "Nike", "category": "Sports", "floor": "First Floor", "unit": "F1-05", "timing": "11:00 AM - 9:00 PM",
         "description": "World's leading athletic brand for shoes, clothing, and equipment.",
         "tags": ["sports", "shoes", "athletic", "fitness"], "is_featured": True,
         "cover_image": "https://images.unsplash.com/photo-1542291026-7eec264c27ff?w=600"},
        {"name": "Samsung", "category": "Electronics", "floor": "Ground Floor", "unit": "G-20", "timing": "11:00 AM - 9:00 PM",
         "description": "Experience zone with the latest Samsung smartphones, tablets, and wearables.",
         "tags": ["electronics", "phones", "gadgets", "tech"], "is_featured": False,
         "cover_image": "https://images.unsplash.com/photo-1610945415295-d9bbf067e59c?w=600"},
        {"name": "Titan", "category": "Accessories", "floor": "Ground Floor", "unit": "G-12", "timing": "11:00 AM - 9:00 PM",
         "description": "India's most trusted watch brand with a premium collection.",
         "tags": ["watches", "accessories", "luxury", "gifting"], "is_featured": False,
         "cover_image": "https://images.unsplash.com/photo-1524592094714-0f0654e20314?w=600"},
        {"name": "Forest Essentials", "category": "Beauty", "floor": "First Floor", "unit": "F1-18", "timing": "11:00 AM - 9:00 PM",
         "description": "Luxury Ayurvedic beauty brand with handcrafted, natural products.",
         "tags": ["beauty", "ayurvedic", "luxury", "natural"], "is_featured": False,
         "cover_image": "https://images.unsplash.com/photo-1571781926291-c477ebfd024b?w=600"},
        {"name": "Hamleys", "category": "Kids", "floor": "Second Floor", "unit": "F2-01", "timing": "11:00 AM - 9:00 PM",
         "description": "World's oldest and largest toy shop with the finest toys from around the world.",
         "tags": ["toys", "kids", "games", "gifting"], "is_featured": True,
         "cover_image": "https://images.unsplash.com/photo-1566576912321-d58ddd7a6088?w=600"},
        {"name": "Foodhall", "category": "Food & Beverage", "floor": "Ground Floor", "unit": "G-25", "timing": "10:00 AM - 10:00 PM",
         "description": "Premium gourmet food destination with artisan products from around the world.",
         "tags": ["gourmet", "food", "premium", "artisan"], "is_featured": False,
         "cover_image": "https://images.unsplash.com/photo-1414235077428-338989a2e8c0?w=600"},
    ]

    store_docs = []
    for s in stores:
        store_docs.append({
            "id": str(uuid.uuid4()),
            "name": s["name"],
            "category": s["category"],
            "floor": s["floor"],
            "unit_no": s["unit"],
            "description": s["description"],
            "cover_image": s["cover_image"],
            "timing": s["timing"],
            "tags": s["tags"],
            "is_featured": s["is_featured"],
            "is_active": True,
            "created_at": datetime.now(timezone.utc).isoformat()
        })

    await _db.stores.insert_many(store_docs)

    # Banners
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

    # Offers
    offer_templates = [
        {"store": "Lifestyle", "title": "Flat 40% Off on All Ethnicwear", "desc": "Get amazing discounts on the latest ethnic collection. Valid on MRP only.", "type": "percentage", "value": "40%"},
        {"store": "KAZO", "title": "Buy 2 Get 1 Free", "desc": "On select women's western wear. Limited period offer.", "type": "bogo", "value": "Buy 2 Get 1"},
        {"store": "Sephora", "title": "Free Makeover + 20% Off", "desc": "Get a complimentary makeover and 20% off on beauty purchases above Rs.3000.", "type": "percentage", "value": "20%"},
        {"store": "Starbucks", "title": "Happy Hour - BOGO", "desc": "Buy one get one free on all handcrafted beverages from 2-5 PM.", "type": "bogo", "value": "BOGO"},
        {"store": "Nike", "title": "End of Season Sale - Up to 50% Off", "desc": "Huge discounts on shoes, apparel, and accessories.", "type": "percentage", "value": "50%"},
        {"store": "PVR INOX", "title": "Movie Monday - Flat Rs.150", "desc": "Watch any movie for just Rs.150 every Monday.", "type": "flat", "value": "Rs.150"},
        {"store": "Marks & Spencer", "title": "3 for 2 on All Shirts", "desc": "Buy 3 shirts and pay for only 2. Mix and match!", "type": "bogo", "value": "3 for 2"},
        {"store": "GANT", "title": "Flat 30% Off New Collection", "desc": "Fresh arrivals at irresistible prices. Limited time only.", "type": "percentage", "value": "30%"},
    ]

    offer_docs = []
    for o in offer_templates:
        # Find store
        store_doc = next((s for s in store_docs if s["name"] == o["store"]), None)
        if store_doc:
            offer_docs.append({
                "id": str(uuid.uuid4()),
                "store_id": store_doc["id"],
                "store_name": o["store"],
                "category": store_doc["category"],
                "title": o["title"],
                "description": o["desc"],
                "offer_type": o["type"],
                "discount_value": o["value"],
                "image_url": store_doc["cover_image"],
                "valid_from": datetime.now(timezone.utc).isoformat(),
                "valid_until": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
                "terms": "T&C apply. Not valid on already discounted items.",
                "is_featured": True,
                "is_active": True,
                "created_at": datetime.now(timezone.utc).isoformat()
            })

    if offer_docs:
        await _db.offers.insert_many(offer_docs)

    # Events
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
            "venue": "Hamleys, Second Floor",
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
    await _db.stores.create_index("category")
    await _db.stores.create_index("is_featured")
    await _db.offers.create_index("store_id")
    await _db.offers.create_index("is_active")
    await _db.notifications.create_index([("user_id", 1), ("created_at", -1)])

    return {
        "success": True,
        "seeded": {
            "stores": len(store_docs),
            "banners": len(banner_docs),
            "offers": len(offer_docs),
            "events": len(event_docs)
        }
    }
