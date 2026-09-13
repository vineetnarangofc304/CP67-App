from fastapi import FastAPI, APIRouter, HTTPException, Depends, UploadFile, File, Form, BackgroundTasks, Response, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
import asyncio
import csv
import random
import time
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict, Any, Tuple
import uuid
from datetime import datetime, timezone, timedelta

# IST timezone for display formatting
IST = timezone(timedelta(hours=5, minutes=30))
import hashlib
import jwt
import httpx
import base64
import io
import json
import re

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ.get('MONGO_URL')
# Feb 2026: explicit timeouts so pymongo fails fast on Atlas hiccups
# (default socketTimeoutMS=None = wait forever). Without these the request
# hangs past Cloudflare's edge timeout and the client sees a raw HTTP 500
# from the ingress before our top-level try/except can return a clean JSON.
client = AsyncIOMotorClient(
    mongo_url,
    serverSelectionTimeoutMS=5000,
    connectTimeoutMS=5000,
    socketTimeoutMS=20000,
    waitQueueTimeoutMS=5000,
    retryWrites=True,
    retryReads=True,
    # Feb 2026: zstd wire compression cuts the multi-MB inline base64
    # image payload 3-5x so a slow Atlas link is far less likely to trip
    # socketTimeoutMS on the /bills/{id}/image path. Falls back to zlib
    # if the server doesn't negotiate zstd.
    compressors="zstd,zlib",
    maxPoolSize=100,
    minPoolSize=10,
)
db = client[os.environ.get('DB_NAME', 'cp67_loyalty')]

# Create the main app
app = FastAPI(title="CP67 Loyalty System API")
api_router = APIRouter(prefix="/api")
security = HTTPBearer()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# JWT Secret
JWT_SECRET = os.environ.get('JWT_SECRET', 'cp67-secret-key-2025')
JWT_ALGORITHM = "HS256"

# TagnPay API Config
TAGNPAY_API_URL = os.environ.get('TAGNPAY_API_URL', 'https://cp67.fundlezone.com')
TAGNPAY_USERNAME = os.environ.get('TAGNPAY_USERNAME', '')
TAGNPAY_PASSWORD = os.environ.get('TAGNPAY_PASSWORD', '')
LOCATION_CODE = os.environ.get('LOCATION_CODE', 'WAPP001')

# Admin credentials
ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME', 'admin')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'admin123')
ADMIN_PHONE = os.environ.get('ADMIN_PHONE', '918527521294')  # Admin phone for SMS alerts

# Emergent LLM Key
EMERGENT_LLM_KEY = os.environ.get('EMERGENT_LLM_KEY', '')

# ======================== MODELS ========================

class QRCodeData(BaseModel):
    qr_code_id: str
    location: str
    source_code: str
    prefilled_message: str
    whatsapp_link: str
    scans: int = 0
    registrations: int = 0
    bill_uploads: int = 0
    created_at: str

class UserData(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    phone: str
    name: Optional[str] = None
    loyalty_id: Optional[str] = None
    first_touch_source: Optional[str] = None
    first_touch_qr: Optional[str] = None
    first_touch_message: Optional[str] = None
    registration_time: Optional[str] = None
    kyc_status: bool = False
    fundle_registered: bool = False
    customer_type: str = "new"  # "new" = registered via our system, "existing" = already in Fundle
    balance_points: float = 0.0
    total_earned_points: float = 0.0
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class BillData(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    user_phone: str
    store_name: Optional[str] = None
    bill_no: Optional[str] = None
    bill_no_normalized: Optional[str] = None  # Point 16 — punctuation-stripped for dedup
    bill_date: Optional[str] = None
    amount: Optional[float] = None
    tax: Optional[float] = None
    status: str = "pending"  # pending, auto_approved, manual_review, approved, rejected, duplicate
    points_issued: float = 0.0
    image_url: str
    image_hash: Optional[str] = None
    ocr_confidence: float = 0.0
    ocr_raw_data: Optional[Dict] = None
    rejection_reason: Optional[str] = None
    processed_at: Optional[str] = None
    processed_by: Optional[str] = None  # Admin username who processed this bill
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def model_dump(self, **kwargs):
        d = super().model_dump(**kwargs)
        # Auto-fill normalised bill number so every insert path benefits
        if d.get("bill_no") and not d.get("bill_no_normalized"):
            d["bill_no_normalized"] = normalize_bill_no(d["bill_no"])
        return d

class AdminUser(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    username: str
    password_hash: str
    name: str
    role: str = "admin"  # admin, super_admin, parking_staff
    gate: Optional[str] = None  # gate1, gate2 - for parking_staff only
    is_active: bool = True
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_login: Optional[str] = None

class ParkingSession(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_code: str  # Unique code for QR
    user_phone: str
    user_name: Optional[str] = None
    entry_time: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    exit_time: Optional[str] = None
    duration_minutes: Optional[int] = None
    status: str = "active"  # active, completed, expired
    scanned_by: Optional[str] = None  # Counter staff who scanned
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class BrandConfig(BaseModel):
    """Brand configuration with ATV (Average Transaction Value)"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    brand_name: str
    atv: float = 0.0  # Average Transaction Value
    category: Optional[str] = None  # e.g., "Food", "Fashion", "Electronics"
    is_active: bool = True
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: Optional[str] = None

class WhatsAppLog(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: Optional[str] = None
    user_phone: str
    direction: str  # inbound, outbound
    message_type: str  # text, image, button_click
    content: str
    source_code: Optional[str] = None
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class AdminLoginRequest(BaseModel):
    username: str
    password: str

class AdminLoginResponse(BaseModel):
    token: str
    username: str

class WhatsAppMessageRequest(BaseModel):
    phone: str
    message: str
    message_type: str = "text"

class BillProcessRequest(BaseModel):
    bill_id: str
    action: str  # approve, reject
    rejection_reason: Optional[str] = None  # Admin's reason to send to user
    admin_notes: Optional[str] = None  # Internal admin notes
    points_override: Optional[float] = None
    send_whatsapp: bool = True  # Whether to send WhatsApp message to user

class CampaignCreate(BaseModel):
    name: str
    description: Optional[str] = ""
    campaign_type: str  # multiplier, bonus, first_visit, spend_threshold
    multiplier: float = 1.0  # e.g., 2.0 for 2X, 3.0 for 3X
    bonus_points: int = 0  # flat bonus points
    min_spend: float = 0  # minimum spend to qualify
    applicable_floors: Optional[List[str]] = None  # null = all floors
    applicable_categories: Optional[List[str]] = None  # null = all categories
    applicable_brand_ids: Optional[List[str]] = None  # null = all brands
    start_date: str  # ISO date
    end_date: str  # ISO date
    is_active: bool = True

# ======================== HELPER FUNCTIONS ========================

def create_jwt_token(data: dict) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=24)
    data["exp"] = expire
    return jwt.encode(data, JWT_SECRET, algorithm=JWT_ALGORITHM)

def verify_jwt_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

def calculate_image_hash(image_data: bytes) -> str:
    return hashlib.md5(image_data).hexdigest()

def parse_source_code(message: str) -> Optional[str]:
    """Extract source code from WhatsApp message (format: message | SRC_CODE)"""
    if '|' in message:
        parts = message.split('|')
        if len(parts) >= 2:
            source = parts[-1].strip()
            if source.startswith('SRC_'):
                return source
    return None

# ======================== TAGNPAY API CLIENT ========================

class TagnPayClient:
    def __init__(self):
        self.base_url = TAGNPAY_API_URL
        self.username = TAGNPAY_USERNAME
        self.password = TAGNPAY_PASSWORD
        self.access_token = None
        self.token_expires = None
    
    async def get_token(self, mobile_number: str, retries: int = 2) -> Optional[str]:
        """Generate access token from TagnPay API with retry logic"""
        for attempt in range(retries + 1):
            try:
                logger.info(f"TagnPay get_token called for mobile: {mobile_number} (attempt {attempt + 1})")
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.post(
                        f"{self.base_url}/api/generate-token/",
                        headers={
                            "Username": self.username,
                            "Password": self.password,
                            "Content-Type": "application/json"
                        },
                        json={"mobileno": mobile_number}
                    )
                    logger.info(f"TagnPay token response: {response.status_code} - {response.text[:200]}")
                    if response.status_code == 200:
                        data = response.json()
                        self.access_token = data.get("access_token")
                        return self.access_token
                    logger.error(f"TagnPay token error: {response.status_code} - {response.text}")
            except httpx.TimeoutException as e:
                logger.error(f"TagnPay token TIMEOUT (attempt {attempt + 1}): {e}")
            except httpx.ConnectError as e:
                logger.error(f"TagnPay token CONNECTION ERROR (attempt {attempt + 1}): {e}")
            except Exception as e:
                logger.error(f"TagnPay token exception (attempt {attempt + 1}): {e}")
                import traceback
                logger.error(traceback.format_exc())
            
            if attempt < retries:
                import asyncio
                await asyncio.sleep(1)  # Wait 1 second before retry
        
        return None
    
    async def register_customer(self, mobile_number: str, name: str, pan_number: str, source: str = "WhatsApp", location_code: str = None) -> Dict:
        """Register new customer"""
        token = await self.get_token(mobile_number)
        if not token:
            return {"success": False, "error": "Failed to get token"}
        
        try:
            # Strip emojis and special unicode characters from name (TagnPay doesn't support them)
            import re
            clean_name = re.sub(r'[^\x00-\x7F]+', '', name or "Customer").strip()
            if not clean_name:
                clean_name = "Customer"
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                # TagnPay API - use empty strings for optional text fields, null for optional others
                payload = {
                    "mobileno": mobile_number,
                    "customer_name": clean_name,
                    "loc_id": location_code or LOCATION_CODE,
                    "email": "",
                    "gender": "O",
                    "reg_source": source,
                    "dob": None,
                    "doa": None,
                    "address1": "",
                    "address2": "",
                    "city": "",
                    "state": "",
                    "district": "",
                    "pincode": "",
                    "zipcode": "",
                    "country": "",
                    "landmark": "",
                    "alt_mobile": "",
                    "referral_code": "",
                    "pan_number": "",
                    "aadhar_number": ""
                }
                logger.info(f"TagnPay registration request: {payload}")
                response = await client.post(
                    f"{self.base_url}/api/customer-registration/",
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {token}"
                    },
                    json=payload
                )
                logger.info(f"TagnPay registration response: {response.status_code} - {response.text[:500]}")
                
                # Check if response indicates actual success
                resp_data = response.json() if response.status_code in [200, 201] else None
                is_success = response.status_code in [200, 201] and resp_data and "error" not in resp_data.get("message", "").lower()
                
                return {"success": is_success, "data": resp_data, "error": response.text if not is_success else None}
        except Exception as e:
            logger.error(f"TagnPay registration error: {e}")
            return {"success": False, "error": str(e)}
    
    async def get_customer_points(self, mobile_number: str) -> Dict:
        """Get customer points balance"""
        token = await self.get_token(mobile_number)
        if not token:
            return {"success": False, "error": "Failed to get token"}
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                payload = {"mobile_number": mobile_number}  # API expects 'mobile_number' for this endpoint
                logger.info(f"TagnPay get-customer-points request: {payload}")
                response = await client.post(
                    f"{self.base_url}/api/get-customer-points/",
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {token}"
                    },
                    json=payload
                )
                logger.info(f"TagnPay get-customer-points response: {response.status_code} - {response.text[:500]}")
                if response.status_code in [200, 201]:
                    return {"success": True, "data": response.json()}
                return {"success": False, "error": response.text}
        except Exception as e:
            logger.error(f"TagnPay points error: {e}")
            return {"success": False, "error": str(e)}
    
    async def send_login_otp(self, mobile_number: str) -> Dict:
        """Send OTP for login verification"""
        token = await self.get_token(mobile_number)
        if not token:
            return {"success": False, "error": "Failed to get token"}
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.base_url}/api/validate-cust-send-otp/",
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {token}"
                    },
                    json={
                        "mobile_number": mobile_number,
                        "location_code": LOCATION_CODE,
                        "reg_source": "WhatsApp"
                    }
                )
                return {"success": response.status_code == 200, "data": response.json() if response.status_code == 200 else None}
        except Exception as e:
            logger.error(f"TagnPay OTP error: {e}")
            return {"success": False, "error": str(e)}
    
    async def verify_otp(self, mobile_number: str, otp: str) -> Dict:
        """Verify OTP and get customer access token"""
        token = await self.get_token(mobile_number)
        if not token:
            return {"success": False, "error": "Failed to get token"}
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.base_url}/api/verify-cust-cred/",
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {token}"
                    },
                    json={
                        "mobile_number": mobile_number,
                        "otp": otp,
                        "location_code": LOCATION_CODE,
                        "reg_source": "WhatsApp"
                    }
                )
                return {"success": response.status_code == 200, "data": response.json() if response.status_code == 200 else None}
        except Exception as e:
            logger.error(f"TagnPay verify error: {e}")
            return {"success": False, "error": str(e)}
    
    async def earn_points(self, mobile_number: str, bill_amount: float, bill_number: str, 
                          bill_date: str, store_name: str, bill_image_base64: str = None) -> Dict:
        """Submit bill and earn points"""
        token = await self.get_token(mobile_number)
        if not token:
            return {"success": False, "error": "Failed to get token"}
        
        try:
            import tempfile
            import os
            
            # Create temp file for bill image if provided
            temp_file_path = None
            if bill_image_base64:
                # Decode base64 and save to temp file
                # Point 38: defensive — strip data:/base64: prefix if caller
                # forgot to strip it, and gracefully skip on decode failure
                # instead of exploding with "Incorrect padding".
                try:
                    b64 = bill_image_base64
                    if b64.startswith("data:"):
                        b64 = b64.split(",", 1)[1] if "," in b64 else ""
                    elif b64.startswith("base64:"):
                        b64 = b64[7:]
                    if b64:
                        # Add padding if needed (Karix sometimes strips it)
                        pad_len = (-len(b64)) % 4
                        if pad_len:
                            b64 = b64 + ("=" * pad_len)
                        image_data = base64.b64decode(b64, validate=False)
                    else:
                        image_data = None
                except Exception as e:
                    logger.warning(f"earn_points: bill image not decodable, skipping attachment. err={e}")
                    image_data = None
                if image_data:
                    temp_file = tempfile.NamedTemporaryFile(suffix='.jpg', delete=False)
                    temp_file.write(image_data)
                    temp_file.close()
                    temp_file_path = temp_file.name
            
            async with httpx.AsyncClient(timeout=25.0) as client:
                # Build form data - pass store name from bill OCR to both brand fields
                brand_name = store_name or "CP67 Mall"
                # Point 49: Fundle's earn_points can reject if `category` sent doesn't match
                # the brand's category in Fundle's master (e.g. sending "Shopping" for a
                # restaurant brand like Sagar Ratna). Look up the actual category from our
                # local brands mirror so Fundle accepts the transaction after an admin
                # Fix-Brand action.
                resolved_category = "Shopping"
                try:
                    brand_doc = await db.brands.find_one(
                        {"brand_name": {"$regex": f"^{re.escape(brand_name)}$", "$options": "i"}},
                        {"_id": 0, "category": 1},
                        max_time_ms=3000,
                    )
                    if brand_doc and (brand_doc.get("category") or "").strip():
                        resolved_category = brand_doc["category"].strip()
                    else:
                        logger.info(f"earn_points: brand '{brand_name}' not in local brands mirror — defaulting category='Shopping'")
                except Exception as _bce:
                    logger.warning(f"earn_points: brand category lookup failed for '{brand_name}': {_bce}")
                data = {
                    "mobile_number": mobile_number,
                    "bill_amount": str(bill_amount),
                    "bill_number": bill_number,
                    "bill_date": bill_date,
                    "brand": brand_name,  # Store name from bill OCR
                    "brand_text": brand_name,  # Store name from bill OCR
                    "category": resolved_category,
                    "location": LOCATION_CODE
                }
                
                logger.info(f"TagnPay earn-points request: mobile={mobile_number}, amount={bill_amount}, brand={brand_name}, category={resolved_category}")
                
                files = {}
                if temp_file_path:
                    files = {"bill_file": open(temp_file_path, "rb")}
                
                response = await client.post(
                    f"{self.base_url}/api/earn-points/",
                    headers={
                        "Authorization": f"Bearer {token}"
                    },
                    data=data,
                    files=files
                )
                
                # Clean up temp file
                if temp_file_path and os.path.exists(temp_file_path):
                    os.unlink(temp_file_path)
                
                result = response.json()
                logger.info(f"TagnPay earn-points response: {result}")
                return {"success": True, "data": result}
        except Exception as e:
            logger.error(f"TagnPay earn points error: {e}")
            return {"success": False, "error": str(e)}

    async def log_rejected_bill(self, mobile_number: str, bill_number: str, bill_amount: float,
                                 bill_date: str, store_name: str, rejection_reason: str) -> Dict:
        """Log a rejected bill to TagnPay for tracking purposes"""
        token = await self.get_token(mobile_number)
        if not token:
            return {"success": False, "error": "Failed to get token"}
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                payload = {
                    "mobile_number": mobile_number,
                    "bill_number": bill_number or "N/A",
                    "bill_amount": str(bill_amount or 0),
                    "bill_date": bill_date or datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                    "store_name": store_name or "Unknown",
                    "status": "rejected",
                    "rejection_reason": rejection_reason or "Bill could not be verified"
                }
                logger.info(f"TagnPay log-rejected-bill request: {payload}")
                response = await client.post(
                    f"{self.base_url}/api/log-rejected-bill/",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json"
                    },
                    json=payload
                )
                logger.info(f"TagnPay log-rejected-bill response: {response.status_code} - {response.text[:300]}")
                
                if response.status_code in [200, 201]:
                    return {"success": True, "data": response.json()}
                return {"success": False, "error": response.text}
        except Exception as e:
            logger.error(f"TagnPay log rejected bill error: {e}")
            return {"success": False, "error": str(e)}

tagnpay_client = TagnPayClient()


async def _resolve_bill_image_base64(bill: dict) -> Optional[str]:
    """Point 38 (Feb 2026): Robustly turn a bill's image reference into pure base64
    that TagnPay's earn_points endpoint can decode. Handles all four storage
    variants we've used:
      - `data:image/*;base64,<payload>` (new admin uploads)
      - `base64:<payload>` (legacy prefix)
      - `http(s)://...` (Karix media URL — download with Karix auth, then encode)
      - `objstore:<path>` (Session-20 Emergent Object Storage — fetch bytes, encode)
    Returns None when there's no usable image so the caller can gracefully skip.
    """
    image_url = (bill.get("image_url") or "").strip()
    if not image_url:
        return None
    if image_url.startswith("objstore:"):
        try:
            from storage import aresolve_objstore_url
            fetched = await aresolve_objstore_url(image_url)
            if fetched:
                data, _ctype = fetched
                return base64.b64encode(data).decode()
        except Exception as e:
            logger.warning(f"_resolve_bill_image_base64 objstore fetch failed for {bill.get('id')}: {e}")
        return None
    if image_url.startswith("data:"):
        try:
            return image_url.split(",", 1)[1]
        except Exception:
            return None
    if image_url.startswith("base64:"):
        return image_url[7:]
    if image_url.startswith("http"):
        try:
            async with httpx.AsyncClient(timeout=25.0) as cx:
                headers = {}
                key = os.environ.get("WHATSAPP_API_KEY", "")
                if key:
                    headers = {
                        "Authentication": f"Bearer {key}",
                        "Authorization": f"Bearer {key}",
                    }
                r = await cx.get(image_url, headers=headers)
                if r.status_code != 200 and headers:
                    r = await cx.get(image_url)
                if r.status_code == 200 and r.content:
                    return base64.b64encode(r.content).decode()
        except Exception as e:
            logger.warning(f"_resolve_bill_image_base64 fetch failed for {bill.get('id')}: {e}")
    return None


# ======================== CAMPAIGN ENGINE ========================

async def apply_campaign_bonus(
    bill_amount: float,
    base_points: int,
    store_name: Optional[str] = None,
    is_first_bill: bool = False,
) -> Dict:
    """
    Apply active campaign multipliers/bonuses to base_points earned from Fundle.

    Matching rules per campaign:
      - is_active=True, and now is within [start_date, end_date]
      - min_spend <= bill_amount (0 = no min)
      - applicable_categories: matches brand.category (case-insensitive) OR null=all
      - applicable_brand_ids: matches brand.id OR null=all
      - applicable_floors: currently ignored (no floor mapping) unless null (which = all)
      - campaign_type=first_visit only applies if is_first_bill=True

    Returns:
      { "final_points": int, "bonus_points": int, "applied_campaigns": [{name, type, effect}] }
    """
    if base_points <= 0 and not is_first_bill:
        return {"final_points": base_points, "bonus_points": 0, "applied_campaigns": []}

    now_iso = datetime.now(timezone.utc).isoformat()
    brand = None
    brand_category = None
    brand_id = None
    if store_name:
        brand = await db.brands.find_one(
            {"brand_name": {"$regex": f"^{re.escape(store_name)}$", "$options": "i"}, "is_active": True},
            {"_id": 0, "id": 1, "category": 1},
        )
        if brand:
            brand_category = (brand.get("category") or "").strip().lower()
            brand_id = brand.get("id")

    applied = []
    total_bonus = 0
    multiplier_extra = 0

    async for c in db.campaigns.find({"is_active": True}, {"_id": 0}):
        # Date-range check (start/end may be ISO date or full ISO)
        start = c.get("start_date") or ""
        end = c.get("end_date") or ""
        # Normalise end_date to end-of-day (23:59:59) if only a date
        end_check = end + "T23:59:59" if len(end) == 10 else end
        start_check = start + "T00:00:00" if len(start) == 10 else start
        if start_check and start_check > now_iso:
            continue
        if end_check and end_check < now_iso:
            continue

        # Min spend
        if bill_amount < (c.get("min_spend") or 0):
            continue

        # Category filter
        cats = c.get("applicable_categories")
        if cats:
            if not brand_category or brand_category not in [x.strip().lower() for x in cats]:
                continue

        # Brand-id filter
        brands = c.get("applicable_brand_ids")
        if brands:
            if not brand_id or brand_id not in brands:
                continue

        ctype = c.get("campaign_type")
        if ctype == "first_visit" and not is_first_bill:
            continue

        # Apply campaign
        if ctype == "multiplier":
            mult = float(c.get("multiplier") or 1.0)
            extra = int(round(base_points * (mult - 1.0)))
            if extra > 0:
                multiplier_extra += extra
                applied.append({"name": c.get("name"), "type": "multiplier", "effect": f"{mult}X (+{extra})"})
        elif ctype in ("bonus", "first_visit", "spend_threshold"):
            bonus = int(c.get("bonus_points") or 0)
            if bonus > 0:
                total_bonus += bonus
                applied.append({"name": c.get("name"), "type": ctype, "effect": f"+{bonus} pts"})

    final_points = base_points + multiplier_extra + total_bonus
    return {
        "final_points": int(final_points),
        "bonus_points": int(multiplier_extra + total_bonus),
        "applied_campaigns": applied,
    }

# ======================== BILL OCR SERVICE ========================

async def analyze_bill_image(image_base64: str) -> Dict:
    """Use Gemini Vision to analyze bill image and extract data"""
    logger.info(f"Starting bill OCR analysis, image length: {len(image_base64)}")
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent
        
        logger.info("Imported emergentintegrations successfully")
        
        # Get current date for context
        current_date = datetime.now().strftime("%Y-%m-%d")
        current_year = datetime.now().year
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"bill-ocr-{uuid.uuid4()}",
            system_message=f"""You are a bill/receipt OCR specialist for CP67 Mall loyalty program. Analyze the provided bill image and extract ALL information accurately.

IMPORTANT CONTEXT:
- Today's date is {current_date}
- Current year is {current_year}
- DO NOT invalidate bills based on date - old bills are acceptable
- DO NOT flag past dates as issues - October 2024, December 2024, etc. are all valid
- The backend system will handle date validation separately

IMPORTANT: Look for "CP67" or "CP 67" anywhere in the bill to verify it's from CP67 Mall.

Return a JSON response with the following fields:
{{
    "store_name": "Name of the store/merchant (exact as printed)",
    "bill_no": "Bill/Invoice number",
    "bill_date": "Date on the bill (format: YYYY-MM-DD if possible)",
    "amount": "Total/Grand total amount (number only, no currency symbol)",
    "tax": "Tax amount if visible (number only, 0 if not found)",
    "customer_mobile": "Customer mobile number if printed on bill (10 digits, null if not found)",
    "items": [
        {{"name": "Item name", "qty": 1, "price": 100.00}},
        ...
    ],
    "raw_text": "ALL text visible on the bill including headers, footers, addresses",
    "contains_cp67": true/false,
    "image_quality": "good/fair/poor",
    "confidence_score": 0.0-1.0,
    "is_valid_bill": true/false,
    "tampering_detected": true/false,
    "tampering_indicators": [],
    "extraction_notes": "Any notes about the extraction"
}}

For items array:
- Extract EVERY line item with name, quantity, and price
- If quantity not shown, assume 1
- Include all items even if prices are zero (like free items or carry bags)

VALIDATION RULES - A bill is VALID (is_valid_bill: true) if it has:
1. Store name visible
2. Any date (even old dates from 2024 or earlier are VALID)
3. Total amount visible
That's it. Do NOT invalidate bills for any other reason.

TAMPERING DETECTION - ONLY flag these as tampering:
- Inconsistent fonts within the same bill (different font styles mixed)
- Obviously edited/photoshopped areas
- Digital manipulation artifacts
- Text that appears pasted or overlaid

DO NOT flag as tampering or invalid:
- Old dates (2024, 2023, etc.)
- Tax/GST calculations
- Free items with ₹0 price
- Carry bag charges
- Minor formatting differences"""
        ).with_model("gemini", "gemini-2.5-flash")
        
        logger.info("Created LlmChat instance")
        
        image_content = ImageContent(image_base64=image_base64)
        user_message = UserMessage(
            text=f"Please analyze this bill/receipt image and extract ALL information including every line item. Today is {current_date}. Check if 'CP67' appears anywhere. IMPORTANT: Old dates (2024, 2023) are perfectly valid - do not flag them as issues. Extract all visible text.",
            file_contents=[image_content]
        )
        
        logger.info("Sending message to Gemini...")
        response = await chat.send_message(user_message)
        logger.info(f"Gemini response received: {response[:500] if response else 'None'}...")
        
        # Parse JSON from response
        json_match = re.search(r'\{[\s\S]*\}', response)
        if json_match:
            result = json.loads(json_match.group())
            logger.info(f"OCR result parsed: store={result.get('store_name')}, amount={result.get('amount')}, confidence={result.get('confidence_score')}")
            return {"success": True, "data": result}
        
        logger.error(f"Could not parse JSON from response: {response}")
        return {"success": False, "error": "Could not parse OCR response"}
    except Exception as e:
        logger.error(f"Bill OCR error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return {"success": False, "error": str(e)}

def normalize_bill_no(bill_no: Optional[str]) -> str:
    """Point 16: Normalise OCR'd bill/invoice numbers so that trivial
    punctuation/spacing differences don't create duplicate accepted bills.
    e.g. 'INV: 12345' and 'INV12345' and 'inv12345' all collapse to 'inv12345'.
    """
    if not bill_no:
        return ""
    return re.sub(r"[^A-Za-z0-9]+", "", str(bill_no)).lower()


async def check_duplicate_bill(image_hash: str, bill_no: Optional[str], store_name: Optional[str]) -> bool:
    """Check if bill already exists in database. Timeouts fail-open (return False)
    so an occasional Atlas latency doesn't block a legit bill upload — worst case
    we double-store an image; force-dedup by admin later."""
    try:
        # Check by image hash — indexed via ensure_db_indexes
        existing = await db.bills.find_one(
            {"image_hash": image_hash, "status": {"$ne": "rejected"}},
            max_time_ms=5000,
        )
        if existing:
            return True
    except Exception as e:
        logger.warning(f"dedup image_hash lookup failed: {e}")

    # Check by bill number and store — use normalised form so punctuation
    # differences (e.g. colon in the invoice number) don't slip past.
    if bill_no and store_name:
        norm = normalize_bill_no(bill_no)
        if norm:
            try:
                existing = await db.bills.find_one(
                    {
                        "$or": [
                            {"bill_no_normalized": norm, "store_name": store_name, "status": {"$ne": "rejected"}},
                            # Legacy bills without the normalised field — fall back to exact match
                            {"bill_no": bill_no, "store_name": store_name, "status": {"$ne": "rejected"}}
                        ]
                    },
                    max_time_ms=5000,
                )
                if existing:
                    return True
            except Exception as e:
                logger.warning(f"dedup bill_no lookup failed: {e}")
    return False

# ======================== QR CODE DEFINITIONS ========================

# Main Loyalty QR Codes (affect main system counts)
QR_CODES = [
    {
        "qr_code_id": "QR0124001",
        "location": "Retailer",
        "source_code": "SRC_BRANDS",
        "prefilled_message": "Hi! I want to join CP67 Loyalty Program",
        "category": "loyalty"
    },
    {
        "qr_code_id": "QR0124002",
        "location": "Food Court",
        "source_code": "SRC_FOODCOURT",
        "prefilled_message": "Hi! Register me for CP67 Loyalty",
        "category": "loyalty"
    },
    {
        "qr_code_id": "QR0124003",
        "location": "Parking",
        "source_code": "SRC_PARKING",
        "prefilled_message": "Hi! Sign me up for CP67 Rewards",
        "category": "loyalty"
    },
    {
        "qr_code_id": "QR0124004",
        "location": "Digital Screens",
        "source_code": "SRC_DIGITAL",
        "prefilled_message": "Hi! Add me to CP67 Rewards Program",
        "category": "loyalty"
    },
    {
        "qr_code_id": "QR0124005",
        "location": "Social",
        "source_code": "SRC_SOCIAL",
        "prefilled_message": "Hi! Enroll me in CP67 Loyalty",
        "category": "loyalty"
    },
    {
        "qr_code_id": "QR0124006",
        "location": "Website",
        "source_code": "SRC_WEBSITE",
        "prefilled_message": "Hi! I want to join CP67 Loyalty from Website",
        "category": "loyalty"
    },
    {
        "qr_code_id": "QR0124007",
        "location": "Parking Payment",
        "source_code": "SRC_PARKING_PAY",
        "prefilled_message": "Hi! I need parking validation",
        "category": "parking",
        "description": "Scan at parking entry for exit validation QR"
    },
    {
        "qr_code_id": "QR0124008",
        "location": "Marketing Campaign",
        "source_code": "SRC_MARKETING",
        "prefilled_message": "I want to register in CP 67 Loyalty Program Homeland Advantage",
        "category": "loyalty",
        "description": "For external marketing campaigns (Insta/FB/print ads)",
        "clean_text": True
    },
    {
        "qr_code_id": "QR0124009",
        "location": "App / Direct",
        "source_code": "SRC_APP",
        "prefilled_message": "(App / direct registration — no QR scan)",
        "category": "loyalty",
        "description": "Default source for users who register directly on the mobile App (without scanning a QR)",
        "internal": True
    },
    {
        "qr_code_id": "QR0124010",
        "location": "RWA",
        "source_code": "SRC_RWA",
        "prefilled_message": "Hi! Register me for CP67 Loyalty — RWA",
        "category": "loyalty",
        "description": "For Resident Welfare Association distribution — captures RWA as registration source for reporting"
    },
    {
        "qr_code_id": "QR0124011",
        "location": "Offices",
        "source_code": "SRC_OFFICE",
        "prefilled_message": "Hi! Register me for CP67 Loyalty — Office",
        "category": "loyalty",
        "description": "For office building distribution — captures Office as registration source for reporting"
    }
]

# Message to source mapping (for tracking without visible source code)
MESSAGE_TO_SOURCE = {qr["prefilled_message"].lower(): qr for qr in QR_CODES}


def _build_wa_link(qr: dict) -> str:
    """Build the wa.me link for a QR. If qr['clean_text'] is true, drop the
    visible ' | SRC_XXX' tracking suffix (attribution still works via the
    MESSAGE_TO_SOURCE map)."""
    from urllib.parse import quote
    msg = qr["prefilled_message"]
    if not qr.get("clean_text"):
        msg = f"{msg} | {qr['source_code']}"
    return f"https://wa.me/{WHATSAPP_NUMBER}?text={quote(msg)}"


WHATSAPP_NUMBER = os.environ.get('WHATSAPP_NUMBER', '917347576767')

# ======================== ADMIN AUTH ROUTES ========================

def hash_password(password: str) -> str:
    """Simple password hashing"""
    return hashlib.sha256(password.encode()).hexdigest()

async def ensure_default_admin():
    """Create default admin if no admins exist"""
    admin_count = await db.admins.count_documents({})
    if admin_count == 0:
        default_admin = AdminUser(
            username=ADMIN_USERNAME,
            password_hash=hash_password(ADMIN_PASSWORD),
            name="Super Admin",
            role="super_admin"
        )
        await db.admins.insert_one(default_admin.model_dump())
        logger.info(f"Created default admin user: {ADMIN_USERNAME}")
    
    # Ensure parking staff users exist for both gates
    for gate_num, gate_label in [("1", "gate1"), ("2", "gate2")]:
        username = f"parking{gate_num}"
        parking_user = await db.admins.find_one({"username": username})
        if not parking_user:
            parking_admin = AdminUser(
                username=username,
                password_hash=hash_password(f"Parking{gate_num}@2025"),
                name=f"Parking Gate {gate_num}",
                role="parking_staff",
                gate=gate_label
            )
            await db.admins.insert_one(parking_admin.model_dump())
            logger.info(f"Created parking staff user: {username} ({gate_label})")
        elif not parking_user.get("gate"):
            await db.admins.update_one({"username": username}, {"$set": {"gate": gate_label}})
    
    # Remove old single 'parking' user if it exists (replaced by parking1/parking2)
    old_parking = await db.admins.find_one({"username": "parking", "gate": None})
    if old_parking:
        await db.admins.delete_one({"username": "parking", "gate": None})

@api_router.post("/admin/login", response_model=AdminLoginResponse)
async def admin_login(request: AdminLoginRequest):
    # First ensure default admin exists
    await ensure_default_admin()
    
    # Check in database
    admin = await db.admins.find_one({
        "username": request.username,
        "password_hash": hash_password(request.password),
        "is_active": True
    })
    
    if admin:
        # Update last login
        await db.admins.update_one(
            {"id": admin["id"]},
            {"$set": {"last_login": datetime.now(timezone.utc).isoformat()}}
        )
        token = create_jwt_token({
            "username": admin["username"],
            "name": admin.get("name", admin["username"]),
            "role": admin.get("role", "admin"),
            "admin_id": admin["id"],
            "gate": admin.get("gate")
        })
        return AdminLoginResponse(token=token, username=admin["username"])
    
    # Fallback to env credentials for backward compatibility
    if request.username == ADMIN_USERNAME and request.password == ADMIN_PASSWORD:
        token = create_jwt_token({"username": request.username, "name": "Admin", "role": "super_admin"})
        return AdminLoginResponse(token=token, username=request.username)
    
    raise HTTPException(status_code=401, detail="Invalid credentials")

@api_router.get("/admin/me")
async def get_admin_profile(payload: dict = Depends(verify_jwt_token)):
    result = {
        "username": payload.get("username"),
        "name": payload.get("name", payload.get("username")),
        "role": payload.get("role")
    }
    if payload.get("gate"):
        result["gate"] = payload["gate"]
    return result

@api_router.get("/admin/users")
async def get_admin_users(payload: dict = Depends(verify_jwt_token)):
    """Get all admin users (super_admin only)"""
    if payload.get("role") != "super_admin":
        raise HTTPException(status_code=403, detail="Only super admins can view admin users")
    
    admins = await db.admins.find({}, {"_id": 0, "password_hash": 0}).to_list(100)
    return admins

@api_router.post("/admin/users")
async def create_admin_user(
    username: str = Form(...),
    password: str = Form(...),
    name: str = Form(...),
    role: str = Form("admin"),
    payload: dict = Depends(verify_jwt_token)
):
    """Create a new admin user (super_admin only)"""
    if payload.get("role") != "super_admin":
        raise HTTPException(status_code=403, detail="Only super admins can create admin users")
    
    # Check if username exists
    existing = await db.admins.find_one({"username": username})
    if existing:
        raise HTTPException(status_code=400, detail="Username already exists")
    
    new_admin = AdminUser(
        username=username,
        password_hash=hash_password(password),
        name=name,
        role=role
    )
    await db.admins.insert_one(new_admin.model_dump())
    return {"success": True, "message": f"Admin user {username} created"}

@api_router.delete("/admin/users/{admin_id}")
async def delete_admin_user(admin_id: str, payload: dict = Depends(verify_jwt_token)):
    """Delete/deactivate an admin user (super_admin only)"""
    if payload.get("role") != "super_admin":
        raise HTTPException(status_code=403, detail="Only super admins can delete admin users")
    
    result = await db.admins.update_one(
        {"id": admin_id},
        {"$set": {"is_active": False}}
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Admin user not found")
    return {"success": True, "message": "Admin user deactivated"}

# ======================== QR CODE ROUTES ========================

@api_router.get("/qr-codes")
async def get_qr_codes(category: Optional[str] = None, payload: dict = Depends(verify_jwt_token)):
    """Get all QR codes with stats"""
    qr_list = []
    for qr in QR_CODES:
        # Skip internal-only QRs (e.g. SRC_APP — not a real printable QR)
        if qr.get("internal"):
            continue
        # Filter by category if specified
        if category and qr.get("category") != category:
            continue
            
        # Get stats from database
        if qr.get("category") == "parking":
            # For parking QR, get stats from parking_sessions
            parking_stats = await db.parking_sessions.aggregate([
                {"$group": {
                    "_id": None,
                    "total_sessions": {"$sum": 1},
                    "active": {"$sum": {"$cond": [{"$eq": ["$status", "active"]}, 1, 0]}},
                    "completed": {"$sum": {"$cond": [{"$eq": ["$status", "completed"]}, 1, 0]}}
                }}
            ]).to_list(1)
            stats_data = parking_stats[0] if parking_stats else {}
            qr_data = {
                **qr,
                "whatsapp_link": _build_wa_link(qr),
                "scans": stats_data.get("total_sessions", 0),
                "registrations": 0,  # Parking doesn't affect registrations
                "bill_uploads": 0,   # Parking doesn't affect bill uploads
                "parking_active": stats_data.get("active", 0),
                "parking_completed": stats_data.get("completed", 0)
            }
        else:
            # Regular loyalty QR codes
            stats = await db.qr_analytics.find_one({"qr_code_id": qr["qr_code_id"]}, {"_id": 0})
            whatsapp_link = _build_wa_link(qr)
            qr_data = {
                **qr,
                "whatsapp_link": whatsapp_link,
                "scans": stats.get("scans", 0) if stats else 0,
                "registrations": stats.get("registrations", 0) if stats else 0,
                "bill_uploads": stats.get("bill_uploads", 0) if stats else 0
            }
        qr_list.append(qr_data)
    return qr_list

@api_router.get("/qr-links")
async def get_qr_links():
    """Get WhatsApp links for all QR codes - PUBLIC endpoint for website integration"""
    links = []
    for qr in QR_CODES:
        if qr.get("internal"):
            continue
        whatsapp_link = _build_wa_link(qr)
        links.append({
            "location": qr["location"],
            "source_code": qr["source_code"],
            "category": qr.get("category", "loyalty"),
            "whatsapp_link": whatsapp_link,
            "prefilled_message": qr["prefilled_message"]
        })
    return {
        "whatsapp_number": WHATSAPP_NUMBER,
        "links": links
    }

@api_router.get("/qr-codes/{qr_code_id}/generate")
async def generate_qr_image(qr_code_id: str):
    """Generate QR code image"""
    import qrcode
    import io
    import base64
    
    qr_data = next((qr for qr in QR_CODES if qr["qr_code_id"] == qr_code_id), None)
    if not qr_data:
        raise HTTPException(status_code=404, detail="QR code not found")
    
    whatsapp_link = _build_wa_link(qr_data)
    
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(whatsapp_link)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    
    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    img_str = base64.b64encode(buffer.getvalue()).decode()
    
    return {
        "qr_code_id": qr_code_id,
        "location": qr_data["location"],
        "whatsapp_link": whatsapp_link,
        "image_base64": f"data:image/png;base64,{img_str}"
    }

# ======================== USER ROUTES ========================

@api_router.get("/admin/users/sources")
async def list_user_sources(payload: dict = Depends(verify_jwt_token)):
    """Point 37: Return every distinct first_touch_source value in the users
    collection with its user count so the Admin → Users source dropdown can
    reflect the real data instead of a hardcoded shortlist. Also returns any
    curated / well-known source codes even if they currently have zero users,
    so admins can pre-filter for freshly rolled-out sources (e.g. SRC_OFFICE).
    """
    # 1. Distinct values actually present on users
    counts: Dict[str, int] = {}
    pipeline = [
        {"$match": {"first_touch_source": {"$exists": True, "$nin": [None, ""]}}},
        {"$group": {"_id": "$first_touch_source", "count": {"$sum": 1}}},
    ]
    async for row in db.users.aggregate(pipeline):
        code = str(row["_id"] or "").strip()
        if code:
            counts[code] = int(row.get("count") or 0)

    # 2. Curated shortlist so admins can filter for known sources even when unused
    curated = [
        "SRC_APP", "SRC_BRANDS", "SRC_FOODCOURT", "SRC_PARKING",
        "SRC_DIGITAL", "SRC_SOCIAL", "SRC_WEBSITE", "SRC_RWA",
        "SRC_OFFICE", "SRC_WHATSAPP", "SRC_MARKETING", "SRC_REFERRAL",
    ]
    for c in curated:
        counts.setdefault(c, 0)

    # 3. Human-friendly labels — falls back to trimmed code otherwise
    LABELS = {
        "SRC_APP": "App", "SRC_BRANDS": "Retailer", "SRC_FOODCOURT": "Food Court",
        "SRC_PARKING": "Parking", "SRC_DIGITAL": "Digital Screens", "SRC_SOCIAL": "Social",
        "SRC_WEBSITE": "Website", "SRC_RWA": "RWA", "SRC_OFFICE": "Office",
        "SRC_WHATSAPP": "WhatsApp", "SRC_MARKETING": "Marketing", "SRC_REFERRAL": "Referral",
    }
    sources = [
        {"code": code, "label": LABELS.get(code, code.replace("SRC_", "").title()), "count": cnt}
        for code, cnt in counts.items()
    ]
    sources.sort(key=lambda x: (-x["count"], x["code"]))
    return {"sources": sources, "total": len(sources)}


@api_router.get("/users")
async def get_users(
    skip: int = 0, 
    limit: int = 50,
    search: Optional[str] = None,
    source: Optional[str] = None,
    customer_type: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    payload: dict = Depends(verify_jwt_token)
):
    """Get all users with pagination and filters - points shown only in detail view"""
    query = {}
    if search:
        query["$or"] = [
            {"phone": {"$regex": search, "$options": "i"}},
            {"name": {"$regex": search, "$options": "i"}}
        ]
    if source:
        query["first_touch_source"] = source
    if customer_type and customer_type in ["new", "existing"]:
        query["customer_type"] = customer_type
    
    # Date range filter
    if from_date or to_date:
        date_query = {}
        if from_date:
            date_query["$gte"] = f"{from_date}T00:00:00"
        if to_date:
            date_query["$lte"] = f"{to_date}T23:59:59"
        if date_query:
            query["$or"] = query.get("$or", []) + [
                {"created_at": date_query},
                {"registration_time": date_query}
            ]
            # If we had a search $or, merge properly
            if search:
                search_or = [
                    {"phone": {"$regex": search, "$options": "i"}},
                    {"name": {"$regex": search, "$options": "i"}}
                ]
                del query["$or"]
                query["$and"] = [
                    {"$or": search_or},
                    {"$or": [{"created_at": date_query}, {"registration_time": date_query}]}
                ]
    
    total = await db.users.count_documents(query)
    users = await db.users.find(query, {"_id": 0}).skip(skip).limit(limit).sort("created_at", -1).to_list(limit)
    
    # NOTE: Points are fetched only in detail view to avoid slow list loading
    # Set balance_points to 0 for list view display
    for user in users:
        user["balance_points"] = 0  # Will be fetched from Fundle in detail view
    
    return {"users": users, "total": total, "skip": skip, "limit": limit}

@api_router.get("/users/{user_id}")
async def get_user(user_id: str, payload: dict = Depends(verify_jwt_token)):
    """Get single user details with real-time points from Fundle"""
    user = await db.users.find_one({"id": user_id}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Always fetch real-time points from Fundle API (don't store locally)
    phone = user.get("phone", "")
    if phone:
        mobile_10 = phone[-10:] if len(phone) >= 10 else phone
        points_result = await tagnpay_client.get_customer_points(mobile_10)
        if points_result.get("success") and points_result.get("data"):
            user["balance_points"] = points_result["data"].get("balance_points", 0)
            user["total_customer_spend"] = points_result["data"].get("total_customer_spend", 0)
            user["next_tier_name"] = points_result["data"].get("next_tier_name")
            user["fundle_synced"] = True
        else:
            user["balance_points"] = 0
            user["fundle_synced"] = False
            user["fundle_error"] = points_result.get("error", "Not registered in Fundle")
    
    # Get user's bills
    bills = await db.bills.find({"user_id": user_id}, {"_id": 0}).sort("created_at", -1).to_list(100)
    
    # Get user's whatsapp logs
    logs = await db.whatsapp_logs.find({"user_id": user_id}, {"_id": 0}).sort("timestamp", -1).to_list(50)
    
    return {"user": user, "bills": bills, "whatsapp_logs": logs}

@api_router.get("/users/phone/{phone}")
async def get_user_by_phone(phone: str, payload: dict = Depends(verify_jwt_token)):
    """Get user by phone number with real-time Fundle points"""
    user = await db.users.find_one({"phone": phone}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Fetch real-time points from Fundle
    mobile_10 = phone[-10:] if len(phone) >= 10 else phone
    try:
        points_result = await tagnpay_client.get_customer_points(mobile_10)
        if points_result.get("success") and points_result.get("data"):
            user["balance_points"] = points_result["data"].get("balance_points", 0)
            user["total_customer_spend"] = points_result["data"].get("total_customer_spend", 0)
        else:
            user["balance_points"] = 0
    except Exception:
        user["balance_points"] = 0
    
    return user

@api_router.post("/admin/migrate-customer-types")
async def migrate_customer_types(payload: dict = Depends(verify_jwt_token)):
    """One-time migration: Check Fundle for all users and mark pre-existing ones as 'existing'
    
    Logic: If a user exists in Fundle AND was registered in our system AFTER Jan 24, 2026,
    they were likely a Fundle customer before our WhatsApp system went live.
    """
    cutoff_date = "2026-01-24T00:00:00"
    updated_count = 0
    checked_count = 0
    errors = []
    
    # Get all users
    users = await db.users.find({}, {"_id": 0, "id": 1, "phone": 1, "customer_type": 1, "created_at": 1, "registration_time": 1}).to_list(1000)
    
    for user in users:
        checked_count += 1
        phone = user.get("phone", "")
        mobile_10 = phone[2:] if phone.startswith("91") and len(phone) == 12 else phone
        
        # Skip if already marked as existing
        if user.get("customer_type") == "existing":
            continue
        
        # Check registration date - if before cutoff, they're from before our system
        reg_date = user.get("registration_time") or user.get("created_at")
        if reg_date and reg_date < cutoff_date:
            # User was registered before our cutoff - mark as existing
            await db.users.update_one(
                {"id": user["id"]},
                {"$set": {"customer_type": "existing"}}
            )
            updated_count += 1
            continue
        
        # For users after cutoff, check if they existed in Fundle
        try:
            points_result = await tagnpay_client.get_customer_points(mobile_10)
            if points_result.get("success") and points_result.get("data"):
                # User exists in Fundle - check if they have spending history
                # If they have total_customer_spend > 0, they were active before
                total_spend = points_result["data"].get("total_customer_spend", 0)
                if total_spend > 0:
                    # Has spending history - likely existed before our system
                    await db.users.update_one(
                        {"id": user["id"]},
                        {"$set": {"customer_type": "existing"}}
                    )
                    updated_count += 1
        except Exception as e:
            errors.append(f"{phone}: {str(e)}")
    
    return {
        "message": f"Migration complete. Checked {checked_count} users, updated {updated_count} to 'existing' status.",
        "checked": checked_count,
        "updated": updated_count,
        "errors": errors[:10] if errors else []
    }

@api_router.post("/admin/force-existing-before-date")
async def force_existing_before_date(
    cutoff_date: str = "2026-01-24",
    payload: dict = Depends(verify_jwt_token)
):
    """Force mark all users registered before a specific date as 'existing'"""
    cutoff_datetime = f"{cutoff_date}T00:00:00"
    
    # Update users registered before cutoff
    result = await db.users.update_many(
        {
            "$or": [
                {"registration_time": {"$lt": cutoff_datetime}},
                {"created_at": {"$lt": cutoff_datetime}}
            ],
            "customer_type": {"$ne": "existing"}
        },
        {"$set": {"customer_type": "existing"}}
    )
    
    return {
        "message": f"Updated {result.modified_count} users to 'existing' status (registered before {cutoff_date})",
        "matched": result.matched_count,
        "modified": result.modified_count
    }

@api_router.post("/admin/set-default-customer-type")
async def set_default_customer_type(
    default_type: str = "new",
    payload: dict = Depends(verify_jwt_token)
):
    """Set customer_type for users who don't have it or have 'unknown'"""
    if default_type not in ["new", "existing"]:
        raise HTTPException(status_code=400, detail="default_type must be 'new' or 'existing'")
    
    result = await db.users.update_many(
        {
            "$or": [
                {"customer_type": {"$exists": False}},
                {"customer_type": None},
                {"customer_type": ""},
                {"customer_type": "unknown"}
            ]
        },
        {"$set": {"customer_type": default_type}}
    )
    
    return {
        "message": f"Updated {result.modified_count} users to '{default_type}' status",
        "matched": result.matched_count,
        "modified": result.modified_count
    }

@api_router.post("/admin/bulk-mark-existing")
async def bulk_mark_existing(
    phone_numbers: List[str],
    payload: dict = Depends(verify_jwt_token)
):
    """Bulk mark phone numbers as 'existing' customers from Fundle export"""
    updated_count = 0

    for phone in phone_numbers:
        # Normalize phone - add 91 prefix if needed
        clean_phone = ''.join(filter(str.isdigit, phone))
        if len(clean_phone) == 10:
            full_phone = f"91{clean_phone}"
        elif len(clean_phone) == 12 and clean_phone.startswith('91'):
            full_phone = clean_phone
        else:
            continue
        
        # Update user if exists in our system
        result = await db.users.update_one(
            {"phone": full_phone},
            {"$set": {"customer_type": "existing", "fundle_existing": True}}
        )
        
        if result.modified_count > 0:
            updated_count += 1
        elif result.matched_count == 0:
            # User not in our system - we can optionally add them
            pass
    
    return {
        "message": f"Marked {updated_count} users as 'existing'",
        "updated": updated_count,
        "total_phones_provided": len(phone_numbers)
    }

@api_router.post("/admin/import-fundle-customers")
async def import_fundle_customers(
    phone_numbers: List[str],
    payload: dict = Depends(verify_jwt_token)
):
    """Import Fundle customer phone numbers for future reference.
    These numbers will be used to identify existing customers when they scan our QR.
    """
    # Store in a separate collection for reference
    inserted_count = 0
    
    for phone in phone_numbers:
        clean_phone = ''.join(filter(str.isdigit, phone))
        if len(clean_phone) == 10:
            try:
                await db.fundle_customers.update_one(
                    {"phone_10": clean_phone},
                    {"$set": {"phone_10": clean_phone, "imported_at": datetime.now(timezone.utc).isoformat()}},
                    upsert=True
                )
                inserted_count += 1
            except Exception:
                pass
    
    return {
        "message": f"Imported {inserted_count} Fundle customer phone numbers",
        "imported": inserted_count,
        "total_provided": len(phone_numbers)
    }

@api_router.post("/admin/upload-fundle-excel")
async def upload_fundle_excel(
    file: UploadFile = File(...),
    payload: dict = Depends(verify_jwt_token)
):
    """Upload Excel file with Fundle customer phone numbers.
    Scans ALL columns for phone numbers (10-digit or 12-digit starting with 91).
    Accepts .xlsx, .xls, or .csv files.
    """
    import openpyxl
    import csv
    
    logger.info(f"Uploading Fundle customer Excel: {file.filename}, size: {file.size if hasattr(file, 'size') else 'unknown'}")
    
    # Read file content
    content = await file.read()
    logger.info(f"Read {len(content)} bytes from file")
    
    phone_numbers = []
    sample_values = []  # For debugging
    
    def extract_phone(value):
        """Extract phone number from any value"""
        if value is None:
            return None
        
        # Convert to string
        val_str = str(value).strip()
        
        # Handle scientific notation (e.g., 9.65005e+09)
        if 'e+' in val_str.lower() or 'e-' in val_str.lower():
            try:
                val_str = str(int(float(val_str)))
            except Exception:
                pass
        
        # Remove common prefixes/suffixes
        val_str = val_str.replace('+91', '').replace('+', '').replace('-', '').replace(' ', '').replace('.0', '')
        
        # Extract digits only
        clean_phone = ''.join(filter(str.isdigit, val_str))
        
        # Check valid phone formats
        if len(clean_phone) == 10 and clean_phone[0] in '6789':
            return clean_phone
        elif len(clean_phone) == 12 and clean_phone.startswith('91') and clean_phone[2] in '6789':
            return clean_phone[2:]
        elif len(clean_phone) == 11 and clean_phone.startswith('0') and clean_phone[1] in '6789':
            return clean_phone[1:]
        
        return None
    
    try:
        if file.filename.lower().endswith('.xlsx') or file.filename.lower().endswith('.xls'):
            # Excel file
            logger.info("Processing as Excel file...")
            workbook = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
            sheet = workbook.active
            
            row_count = 0
            for row in sheet.iter_rows(values_only=True):
                row_count += 1
                if row:
                    # Check ALL columns in the row
                    for cell_value in row:
                        if cell_value is not None:
                            # Store sample for debugging (first 10)
                            if len(sample_values) < 10:
                                sample_values.append(str(cell_value)[:30])
                            
                            phone = extract_phone(cell_value)
                            if phone:
                                phone_numbers.append(phone)
            
            workbook.close()
            logger.info(f"Processed {row_count} rows from Excel")
        
        elif file.filename.lower().endswith('.csv'):
            # CSV file
            logger.info("Processing as CSV file...")
            try:
                content_str = content.decode('utf-8')
            except Exception:
                content_str = content.decode('latin-1')
            
            reader = csv.reader(io.StringIO(content_str))
            
            row_count = 0
            for row in reader:
                row_count += 1
                for cell_value in row:
                    if cell_value:
                        if len(sample_values) < 10:
                            sample_values.append(str(cell_value)[:30])
                        
                        phone = extract_phone(cell_value)
                        if phone:
                            phone_numbers.append(phone)
            
            logger.info(f"Processed {row_count} rows from CSV")
        else:
            raise HTTPException(status_code=400, detail="Unsupported file format. Use .xlsx, .xls, or .csv")
        
        logger.info(f"Sample values from file: {sample_values}")
        logger.info(f"Extracted {len(phone_numbers)} phone numbers from file")
        
        # Remove duplicates
        phone_numbers = list(set(phone_numbers))
        logger.info(f"Unique phone numbers: {len(phone_numbers)}")
        
        if len(phone_numbers) == 0:
            return {
                "success": False,
                "message": "No valid phone numbers found in the file",
                "phones_in_file": 0,
                "imported": 0,
                "total_in_database": await db.fundle_customers.count_documents({}),
                "sample_values": sample_values,
                "hint": "Make sure phone numbers are 10 digits (starting with 6,7,8,9) or 12 digits starting with 91"
            }
        
        # Insert into database
        inserted_count = 0
        for phone in phone_numbers:
            try:
                await db.fundle_customers.update_one(
                    {"phone_10": phone},
                    {"$set": {"phone_10": phone, "imported_at": datetime.now(timezone.utc).isoformat()}},
                    upsert=True
                )
                inserted_count += 1
            except Exception as e:
                logger.error(f"Error inserting phone {phone}: {e}")
        
        # Get total count in collection
        total_in_db = await db.fundle_customers.count_documents({})
        
        return {
            "success": True,
            "message": f"Successfully imported {inserted_count} phone numbers",
            "phones_in_file": len(phone_numbers),
            "imported": inserted_count,
            "total_in_database": total_in_db,
            "sample_phones": phone_numbers[:5] if phone_numbers else []
        }
        
    except Exception as e:
        logger.error(f"Error processing Excel file: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error processing file: {str(e)}")

@api_router.get("/admin/check-fundle-customer/{phone}")
async def check_fundle_customer(phone: str, payload: dict = Depends(verify_jwt_token)):
    """Check if a phone number is in the imported Fundle customer list"""
    clean_phone = ''.join(filter(str.isdigit, phone))
    if len(clean_phone) == 12 and clean_phone.startswith('91'):
        clean_phone = clean_phone[2:]
    
    existing = await db.fundle_customers.find_one({"phone_10": clean_phone})
    return {"phone": phone, "is_fundle_customer": existing is not None}

@api_router.post("/admin/upload-fundle-chunk")
async def upload_fundle_chunk(
    data: dict,
    payload: dict = Depends(verify_jwt_token)
):
    """Upload a chunk of phone numbers (for large file uploads).
    Accepts JSON with phone_numbers array.
    """
    phone_numbers = data.get("phone_numbers", [])
    
    if not phone_numbers:
        return {"success": False, "imported": 0, "message": "No phone numbers provided"}
    
    logger.info(f"Uploading chunk of {len(phone_numbers)} phone numbers...")
    
    # Bulk insert using unordered bulk write for speed
    from pymongo import UpdateOne
    
    operations = []
    for phone in phone_numbers:
        clean_phone = ''.join(filter(str.isdigit, str(phone)))
        if len(clean_phone) == 10 and clean_phone[0] in '6789':
            operations.append(
                UpdateOne(
                    {"phone_10": clean_phone},
                    {"$set": {"phone_10": clean_phone, "imported_at": datetime.now(timezone.utc).isoformat()}},
                    upsert=True
                )
            )
        elif len(clean_phone) == 12 and clean_phone.startswith('91') and clean_phone[2] in '6789':
            operations.append(
                UpdateOne(
                    {"phone_10": clean_phone[2:]},
                    {"$set": {"phone_10": clean_phone[2:], "imported_at": datetime.now(timezone.utc).isoformat()}},
                    upsert=True
                )
            )
    
    imported = 0
    if operations:
        try:
            result = await db.fundle_customers.bulk_write(operations, ordered=False)
            imported = result.upserted_count + result.modified_count
        except Exception as e:
            logger.error(f"Bulk write error: {e}")
            # Fallback to individual inserts
            for phone in phone_numbers:
                try:
                    clean_phone = ''.join(filter(str.isdigit, str(phone)))
                    if len(clean_phone) == 12 and clean_phone.startswith('91'):
                        clean_phone = clean_phone[2:]
                    if len(clean_phone) == 10 and clean_phone[0] in '6789':
                        await db.fundle_customers.update_one(
                            {"phone_10": clean_phone},
                            {"$set": {"phone_10": clean_phone, "imported_at": datetime.now(timezone.utc).isoformat()}},
                            upsert=True
                        )
                        imported += 1
                except Exception:
                    pass
    
    logger.info(f"Chunk imported: {imported} numbers")
    return {"success": True, "imported": imported}

@api_router.get("/admin/fundle-count")
async def get_fundle_count(payload: dict = Depends(verify_jwt_token)):
    """Get total count of phone numbers in fundle_customers collection"""
    count = await db.fundle_customers.count_documents({})
    return {"count": count}



# ============ BLOCKED USERS MANAGEMENT ============

@api_router.get("/admin/blocked-users")
async def get_blocked_users(
    skip: int = 0, limit: int = 50, search: str = "",
    payload: dict = Depends(verify_jwt_token)
):
    query = {}
    if search:
        query["$or"] = [
            {"phone": {"$regex": search, "$options": "i"}},
            {"brand": {"$regex": search, "$options": "i"}},
            {"staff_name": {"$regex": search, "$options": "i"}},
        ]
    total = await db.blocked_phones.count_documents(query)
    blocked = await db.blocked_phones.find(query, {"_id": 0}).skip(skip).limit(limit).sort("blocked_at", -1).to_list(limit)
    return {"blocked_users": blocked, "total": total}

@api_router.post("/admin/block-user")
async def block_user(request: Request, payload: dict = Depends(verify_jwt_token)):
    data = await request.json()
    phone = data.get("phone", "").strip()
    reason = data.get("reason", "Blocked by admin")
    if not phone:
        raise HTTPException(status_code=400, detail="Phone number required")
    # Normalize to 10 digits
    if phone.startswith("91") and len(phone) == 12:
        phone = phone[2:]
    if phone.startswith("+91"):
        phone = phone[3:]
    
    existing = await db.blocked_phones.find_one({"phone": phone})
    if existing:
        raise HTTPException(status_code=400, detail="Number already blocked")
    
    doc = {
        "phone": phone,
        "reason": reason,
        "blocked_by": payload.get("username", "admin"),
        "blocked_at": datetime.now(timezone.utc).isoformat()
    }
    await db.blocked_phones.insert_one(doc)
    logger.info(f"Admin {payload.get('username')} blocked phone {phone}: {reason}")
    return {"success": True, "message": f"{phone} has been blocked"}

@api_router.post("/admin/unblock-user")
async def unblock_user(request: Request, payload: dict = Depends(verify_jwt_token)):
    data = await request.json()
    phone = data.get("phone", "").strip()
    if not phone:
        raise HTTPException(status_code=400, detail="Phone number required")
    if phone.startswith("91") and len(phone) == 12:
        phone = phone[2:]
    if phone.startswith("+91"):
        phone = phone[3:]
    
    result = await db.blocked_phones.delete_one({"phone": phone})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Number not found in blocked list")
    
    logger.info(f"Admin {payload.get('username')} unblocked phone {phone}")
    return {"success": True, "message": f"{phone} has been activated"}


@api_router.post("/admin/blocked-users/bulk-upload")
async def bulk_block_users(
    file: UploadFile = File(...),
    payload: dict = Depends(verify_jwt_token)
):
    """Bulk-block phone numbers from an uploaded Excel/CSV file.

    Expected columns (case-insensitive, any of these per column):
      - Phone:       'contact no', 'contact', 'phone', 'mobile', 'mobile number'
      - Brand:       'brand', 'brand name', 'store', 'store name'
      - Staff Name:  'staff name', 'name'
      - Designation: 'designation', 'role', 'position'

    Only the phone column is required. Phones are normalised to last 10 digits.
    Existing entries are skipped (idempotent).
    """
    filename = (file.filename or "").lower()
    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Empty file")

    # Parse rows
    parsed_rows = []  # list of {phone, brand, name, designation}
    try:
        if filename.endswith((".xlsx", ".xlsm", ".xltx", ".xltm")):
            import openpyxl
            wb = openpyxl.load_workbook(io.BytesIO(contents), data_only=True)
            for sh in wb.sheetnames:
                ws = wb[sh]
                # Find header row
                rows_iter = ws.iter_rows(values_only=True)
                try:
                    headers = next(rows_iter)
                except StopIteration:
                    continue
                norm = [str(h).strip().lower() if h is not None else "" for h in headers]

                def find(*candidates):
                    for c in candidates:
                        for i, h in enumerate(norm):
                            if h == c:
                                return i
                    for c in candidates:
                        for i, h in enumerate(norm):
                            if c in h:
                                return i
                    return None

                phone_idx = find("contact no.", "contact no", "contact", "phone", "mobile number", "mobile")
                brand_idx = find("brand name", "brand", "store name", "store")
                name_idx = find("staff name", "name")
                desig_idx = find("designation", "role", "position")
                if phone_idx is None:
                    continue
                for row in rows_iter:
                    if not row:
                        continue
                    raw_phone = row[phone_idx] if phone_idx < len(row) else None
                    if raw_phone is None or str(raw_phone).strip() == "":
                        continue
                    if isinstance(raw_phone, float):
                        raw_phone = int(raw_phone)
                    digits = "".join(ch for ch in str(raw_phone) if ch.isdigit())
                    if len(digits) > 10:
                        digits = digits[-10:]
                    if len(digits) != 10:
                        continue
                    parsed_rows.append({
                        "phone": digits,
                        "brand": str(row[brand_idx]).strip() if brand_idx is not None and brand_idx < len(row) and row[brand_idx] else "",
                        "name": str(row[name_idx]).strip() if name_idx is not None and name_idx < len(row) and row[name_idx] else "",
                        "designation": str(row[desig_idx]).strip() if desig_idx is not None and desig_idx < len(row) and row[desig_idx] else "",
                    })
        elif filename.endswith(".csv"):
            text = contents.decode("utf-8-sig", errors="ignore")
            reader = csv.DictReader(io.StringIO(text))
            norm_keys = {(k or "").strip().lower(): k for k in (reader.fieldnames or [])}

            def col(*candidates):
                for c in candidates:
                    if c in norm_keys:
                        return norm_keys[c]
                for c in candidates:
                    for k in norm_keys:
                        if c in k:
                            return norm_keys[k]
                return None

            phone_col = col("contact no.", "contact no", "contact", "phone", "mobile number", "mobile")
            brand_col = col("brand name", "brand", "store name", "store")
            name_col = col("staff name", "name")
            desig_col = col("designation", "role", "position")
            if not phone_col:
                raise HTTPException(status_code=400, detail="Could not find a phone column in CSV. Expected 'Contact No.' / 'Phone' / 'Mobile'.")
            for row in reader:
                raw_phone = row.get(phone_col)
                if not raw_phone:
                    continue
                digits = "".join(ch for ch in str(raw_phone) if ch.isdigit())
                if len(digits) > 10:
                    digits = digits[-10:]
                if len(digits) != 10:
                    continue
                parsed_rows.append({
                    "phone": digits,
                    "brand": (row.get(brand_col) or "").strip() if brand_col else "",
                    "name": (row.get(name_col) or "").strip() if name_col else "",
                    "designation": (row.get(desig_col) or "").strip() if desig_col else "",
                })
        else:
            raise HTTPException(status_code=400, detail="Unsupported file type. Upload .xlsx or .csv.")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Bulk block parse failed")
        raise HTTPException(status_code=400, detail=f"Could not parse file: {e}")

    if not parsed_rows:
        raise HTTPException(status_code=400, detail="No valid 10-digit phone numbers found in the file.")

    # Dedupe within file
    by_phone = {}
    for r in parsed_rows:
        if r["phone"] not in by_phone:
            by_phone[r["phone"]] = r
    phones = list(by_phone.keys())

    # Find which already exist
    existing = set()
    async for d in db.blocked_phones.find({"phone": {"$in": phones}}, {"_id": 0, "phone": 1}):
        existing.add(d["phone"])

    new_rows = [by_phone[p] for p in phones if p not in existing]
    now = datetime.now(timezone.utc).isoformat()
    inserted = 0
    if new_rows:
        docs = []
        for s in new_rows:
            parts = ["Brand Staff"]
            if s.get("brand"):
                parts.append(s["brand"])
            if s.get("name"):
                parts.append(s["name"])
            if s.get("designation"):
                parts.append(s["designation"])
            docs.append({
                "phone": s["phone"],
                "reason": " - ".join(parts) if len(parts) > 1 else "Brand Staff",
                "blocked_by": payload.get("username", "admin"),
                "blocked_at": now,
                "source_file": file.filename,
                "brand": s.get("brand", ""),
                "staff_name": s.get("name", ""),
                "designation": s.get("designation", ""),
            })
        result = await db.blocked_phones.insert_many(docs, ordered=False)
        inserted = len(result.inserted_ids)

    # Optional metadata enrichment for already-existing rows that lack brand info
    enriched = 0
    for p in phones:
        if p in existing:
            r = by_phone[p]
            if r.get("brand") or r.get("name") or r.get("designation"):
                res = await db.blocked_phones.update_one(
                    {"phone": p, "$or": [{"brand": {"$exists": False}}, {"brand": ""}]},
                    {"$set": {
                        "brand": r.get("brand", ""),
                        "staff_name": r.get("name", ""),
                        "designation": r.get("designation", ""),
                        "source_file": file.filename,
                    }}
                )
                enriched += res.modified_count

    logger.info(
        f"Bulk-block by {payload.get('username')}: file={file.filename}, "
        f"parsed={len(parsed_rows)}, unique={len(phones)}, inserted={inserted}, "
        f"already_blocked={len(existing)}, enriched={enriched}"
    )
    return {
        "success": True,
        "file": file.filename,
        "parsed_rows": len(parsed_rows),
        "unique_phones": len(phones),
        "newly_blocked": inserted,
        "already_blocked": len(existing),
        "enriched_existing": enriched,
    }


# ============ HOT DEALS (OFFERS) MANAGEMENT ============

@api_router.get("/admin/offers")
async def get_admin_offers(payload: dict = Depends(verify_jwt_token)):
    offers = await db.offers.find({}, {"_id": 0}).sort("created_at", -1).to_list(100)
    return {"offers": offers}

@api_router.post("/admin/offers")
async def create_offer(request: Request, payload: dict = Depends(verify_jwt_token)):
    data = await request.json()
    offer = {
        "id": str(uuid.uuid4()),
        "title": data.get("title", ""),
        "description": data.get("description", ""),
        "store_name": data.get("store_name", ""),
        "store_id": data.get("store_id", ""),
        "image_url": data.get("image_url", ""),
        "discount_text": data.get("discount_text", ""),
        # Point 34: numeric percent used by the consumer Offers screen to render the badge; also drives the "Hot Deals" strip when is_hot_deal is true.
        "discount_value": data.get("discount_value") or data.get("discount_text", ""),
        "is_hot_deal": bool(data.get("is_hot_deal", False)),
        "valid_until": data.get("valid_until", ""),
        "is_active": data.get("is_active", True),
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.offers.insert_one(offer)
    return {"success": True, "offer": {k: v for k, v in offer.items() if k != "_id"}}

@api_router.post("/admin/offers/{offer_id}/upload-image")
async def upload_offer_image(offer_id: str, file: UploadFile = File(...), payload: dict = Depends(verify_jwt_token)):
    content = await file.read()
    import base64
    b64 = base64.b64encode(content).decode("utf-8")
    mime = file.content_type or "image/jpeg"
    data_url = f"data:{mime};base64,{b64}"
    await db.offers.update_one({"id": offer_id}, {"$set": {"image_url": data_url}})
    return {"success": True, "image_url": data_url}

@api_router.put("/admin/offers/{offer_id}")
async def update_offer(offer_id: str, request: Request, payload: dict = Depends(verify_jwt_token)):
    data = await request.json()
    update = {k: v for k, v in data.items() if k in ("title", "description", "store_name", "store_id", "discount_text", "discount_value", "image_url", "is_active", "is_hot_deal", "valid_until")}
    if "is_hot_deal" in update:
        update["is_hot_deal"] = bool(update["is_hot_deal"])
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.offers.update_one({"id": offer_id}, {"$set": update})
    return {"success": True}

@api_router.delete("/admin/offers/{offer_id}")
async def delete_offer(offer_id: str, payload: dict = Depends(verify_jwt_token)):
    await db.offers.delete_one({"id": offer_id})
    return {"success": True}


# ============ EVENTS MANAGEMENT ============

@api_router.get("/admin/events")
async def get_admin_events(payload: dict = Depends(verify_jwt_token)):
    events = await db.events.find({}, {"_id": 0}).sort("date", -1).to_list(100)
    return {"events": events}

@api_router.post("/admin/events")
async def create_event(request: Request, payload: dict = Depends(verify_jwt_token)):
    data = await request.json()
    event = {
        "id": str(uuid.uuid4()),
        "title": data.get("title", ""),
        "description": data.get("description", ""),
        "date": data.get("date", ""),
        "time": data.get("time", ""),
        "venue": data.get("venue", ""),
        "image_url": data.get("image_url", ""),
        "is_active": data.get("is_active", True),
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.events.insert_one(event)
    return {"success": True, "event": {k: v for k, v in event.items() if k != "_id"}}

@api_router.post("/admin/events/{event_id}/upload-image")
async def upload_event_image(event_id: str, file: UploadFile = File(...), payload: dict = Depends(verify_jwt_token)):
    content = await file.read()
    import base64
    b64 = base64.b64encode(content).decode("utf-8")
    mime = file.content_type or "image/jpeg"
    data_url = f"data:{mime};base64,{b64}"
    await db.events.update_one({"id": event_id}, {"$set": {"image_url": data_url}})
    return {"success": True, "image_url": data_url}

@api_router.put("/admin/events/{event_id}")
async def update_event(event_id: str, request: Request, payload: dict = Depends(verify_jwt_token)):
    data = await request.json()
    update = {k: v for k, v in data.items() if k in ("title", "description", "date", "time", "venue", "image_url", "is_active")}
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.events.update_one({"id": event_id}, {"$set": update})
    return {"success": True}

@api_router.delete("/admin/events/{event_id}")
async def delete_event(event_id: str, payload: dict = Depends(verify_jwt_token)):
    await db.events.delete_one({"id": event_id})
    return {"success": True}


# ============ BRAND MANAGEMENT ============

@api_router.get("/admin/brands")
async def get_brands(payload: dict = Depends(verify_jwt_token)):
    """Get all brands with their ATV configuration"""
    brands = await db.brands.find({}, {"_id": 0}).sort("brand_name", 1).to_list(500)
    return {"brands": brands, "total": len(brands)}

@api_router.post("/admin/brands")
async def create_brand(data: dict, payload: dict = Depends(verify_jwt_token)):
    """Create a new brand with ATV"""
    brand_name = data.get("brand_name", "").strip()
    atv = float(data.get("atv", 0))
    category = data.get("category", "").strip() or None
    
    if not brand_name:
        raise HTTPException(status_code=400, detail="Brand name is required")
    
    # Check if brand already exists
    existing = await db.brands.find_one({"brand_name": {"$regex": f"^{brand_name}$", "$options": "i"}})
    if existing:
        raise HTTPException(status_code=400, detail=f"Brand '{brand_name}' already exists")
    
    brand = BrandConfig(
        brand_name=brand_name,
        atv=atv,
        category=category
    )
    
    await db.brands.insert_one(brand.model_dump())
    logger.info(f"Created brand: {brand_name} with ATV: {atv}")
    
    return {"success": True, "brand": brand.model_dump()}

@api_router.put("/admin/brands/{brand_id}")
async def update_brand(brand_id: str, data: dict, payload: dict = Depends(verify_jwt_token)):
    """Update brand ATV, store details, and other info"""
    update_data = {
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    # Core fields
    for field in ["atv", "category", "is_active", "brand_name", "description",
                  "floor", "timing", "unit_no", "tags", "is_featured", "is_eligible", "contact_phone",
                  "contact_email", "website", "hidden_from_app"]:
        if field in data:
            if field == "atv":
                update_data[field] = float(data[field])
            elif field == "brand_name":
                update_data[field] = data[field].strip()
            else:
                update_data[field] = data[field]
    
    result = await db.brands.update_one(
        {"id": brand_id},
        {"$set": update_data}
    )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Brand not found")
    
    # Auto-sync to stores collection (unconditional — Point 33/30: featured flag and logos must reach app immediately)
    brand = await db.brands.find_one({"id": brand_id}, {"_id": 0})
    if brand:
        await _sync_brand_to_store(brand)
    
    return {"success": True, "message": "Brand updated"}


async def _sync_brand_to_store(brand: dict):
    """Sync a brand to the consumer stores collection.
    Point 33/30 (Feb 2026): sync is now unconditional so that is_featured toggles and logo updates propagate to the consumer /home + /stores endpoints immediately, not only when the admin has also written a description.
    """
    store_data = {
        "name": brand.get("brand_name"),
        "category": brand.get("category") or "General",
        "floor": brand.get("floor") or "",
        "unit_no": brand.get("unit_no") or "",
        "description": brand.get("description") or "",
        "cover_image": brand.get("cover_image_url") or "",
        "logo_url": brand.get("logo_url") or "",
        "timing": brand.get("timing") or "11:00 AM - 9:00 PM",
        "tags": brand.get("tags") or [],
        "is_featured": brand.get("is_featured", False),
        "is_active": brand.get("is_active", True) and not brand.get("hidden_from_app", False),
        "hidden_from_app": brand.get("hidden_from_app", False),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    existing = await db.stores.find_one({"name": {"$regex": f'^{re.escape(brand["brand_name"])}$', "$options": "i"}})
    if existing:
        await db.stores.update_one({"_id": existing["_id"]}, {"$set": store_data})
    else:
        store_data["id"] = brand.get("id", str(uuid.uuid4()))
        store_data["created_at"] = datetime.now(timezone.utc).isoformat()
        await db.stores.insert_one(store_data)


@api_router.post("/admin/brands/{brand_id}/upload-image")
async def upload_brand_image(
    brand_id: str,
    image_type: str = Form(...),
    file: UploadFile = File(...),
    payload: dict = Depends(verify_jwt_token)
):
    """Upload logo or cover image for a brand"""
    if image_type not in ("logo", "cover"):
        raise HTTPException(status_code=400, detail="image_type must be 'logo' or 'cover'")
    
    contents = await file.read()
    if len(contents) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Image too large. Max 5MB.")
    
    ext = file.filename.split(".")[-1].lower() if "." in file.filename else "jpg"
    if ext not in ("jpg", "jpeg", "png", "webp", "gif"):
        ext = "jpg"
    
    filename = f"{brand_id}_{image_type}.{ext}"
    # Feb 2026 (Point 43): move brand logo/cover uploads from pod-local disk
    # to Emergent Object Storage. Pod-local files are gone on every redeploy
    # and are inaccessible from the deployed app URL, which is why admin
    # uploads never showed up in the consumer PWA.
    from storage import aput_object, APP_NAME
    content_type = f"image/{'jpeg' if ext in ('jpg','jpeg') else ext}"
    objstore_path = f"{APP_NAME}/brands/{filename}"
    put_result = await aput_object(objstore_path, contents, content_type)
    if not put_result:
        raise HTTPException(status_code=502, detail="Object storage upload failed. Retry in ~10s.")

    backend_url = os.environ.get("BACKEND_PUBLIC_URL", "").rstrip("/")
    image_url = f"{backend_url}/api/uploaded-image/brands/{filename}"
    
    field = "logo_url" if image_type == "logo" else "cover_image_url"
    await db.brands.update_one({"id": brand_id}, {"$set": {field: image_url, "updated_at": datetime.now(timezone.utc).isoformat()}})
    
    # Auto-sync to stores (Point 30: logos must sync immediately regardless of description)
    brand = await db.brands.find_one({"id": brand_id}, {"_id": 0})
    if brand:
        await _sync_brand_to_store(brand)
    
    return {"success": True, "image_url": image_url, "field": field}


@api_router.post("/admin/brands/sync-to-stores")
async def sync_brands_to_stores(payload: dict = Depends(verify_jwt_token)):
    """Sync all brands with descriptions to the consumer stores collection"""
    brands = await db.brands.find({"description": {"$exists": True, "$ne": ""}}, {"_id": 0}).to_list(500)
    synced = 0
    for brand in brands:
        await _sync_brand_to_store(brand)
        synced += 1
    return {"success": True, "synced": synced}


@api_router.get("/app-download-qr")
async def get_app_download_qr():
    """Generate QR code image that points to a tracked scan redirect (Point 31)."""
    import qrcode
    import io
    backend_url = os.environ.get("BACKEND_PUBLIC_URL", "")
    # Point 31: QR now points to the tracked redirect endpoint below so admin can see scan counts.
    qr_target = f"{backend_url}/api/app-download-qr/scan"

    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_H, box_size=10, border=2)
    qr.add_data(qr_target)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#1a1a2e", back_color="white")

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)

    from fastapi.responses import StreamingResponse
    return StreamingResponse(buf, media_type="image/png", headers={
        "Content-Disposition": "inline; filename=cp67-app-qr.png",
        "Cache-Control": "public, max-age=86400"
    })


PLAY_STORE_URL = "https://play.google.com/store/apps/details?id=com.homelandadvantage.cp67&hl=en_IN"


@api_router.get("/app-download-qr/scan")
async def app_download_qr_scan(request: Request):
    """Tracked redirect for the App Install QR (Point 31). Logs each scan then 302s to Play Store."""
    from fastapi.responses import RedirectResponse
    ua = request.headers.get("user-agent", "")[:400]
    ip = (request.headers.get("x-forwarded-for") or request.client.host if request.client else "").split(",")[0].strip()
    now = datetime.now(timezone.utc)
    await db.app_qr_scans.insert_one({
        "id": str(uuid.uuid4()),
        "scanned_at": now.isoformat(),
        "day": now.strftime("%Y-%m-%d"),
        "user_agent": ua,
        "ip": ip,
    })
    return RedirectResponse(PLAY_STORE_URL, status_code=302)


@api_router.get("/admin/app-download-qr/stats")
async def app_download_qr_stats(payload: dict = Depends(verify_jwt_token)):
    """Admin: total scans + daily counts for the last 30 days (Point 31)."""
    total = await db.app_qr_scans.count_documents({})
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    today_count = await db.app_qr_scans.count_documents({"day": today})
    # Daily buckets for the last 30 days
    from datetime import timedelta
    since = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d")
    pipeline = [
        {"$match": {"day": {"$gte": since}}},
        {"$group": {"_id": "$day", "count": {"$sum": 1}}},
        {"$sort": {"_id": 1}},
    ]
    daily = [{"day": r["_id"], "count": r["count"]} async for r in db.app_qr_scans.aggregate(pipeline)]
    backend_url = os.environ.get("BACKEND_PUBLIC_URL", "")
    return {
        "total_scans": total,
        "today_scans": today_count,
        "daily": daily,
        "play_store_url": PLAY_STORE_URL,
        "qr_image_url": f"{backend_url}/api/app-download-qr",
        "scan_target_url": f"{backend_url}/api/app-download-qr/scan",
    }


@api_router.delete("/admin/brands/{brand_id}")
async def delete_brand(brand_id: str, payload: dict = Depends(verify_jwt_token)):
    """Delete a brand"""
    result = await db.brands.delete_one({"id": brand_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Brand not found")
    return {"success": True, "message": "Brand deleted"}


# ==================== ADMIN BANNER MANAGEMENT ====================

@api_router.get("/admin/banners")
async def get_admin_banners(payload: dict = Depends(verify_jwt_token)):
    """Get all banners for admin management"""
    banners = await db.banners.find({}, {"_id": 0}).sort("position", 1).to_list(50)
    return {"banners": banners}

@api_router.post("/admin/banners")
async def create_banner(data: dict, payload: dict = Depends(verify_jwt_token)):
    """Create a new banner"""
    banner = {
        "id": str(uuid.uuid4()),
        "title": data.get("title", ""),
        "subtitle": data.get("subtitle", ""),
        "image_url": data.get("image_url", ""),
        "link_type": data.get("link_type", "none"),
        "link_id": data.get("link_id"),
        "position": data.get("position", 99),
        "is_active": data.get("is_active", True),
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.banners.insert_one(banner)
    return {"success": True, "banner": {k: v for k, v in banner.items() if k != "_id"}}

@api_router.put("/admin/banners/{banner_id}")
async def update_banner(banner_id: str, data: dict, payload: dict = Depends(verify_jwt_token)):
    """Update a banner"""
    updates = {}
    for field in ["title", "subtitle", "image_url", "link_type", "link_id", "position", "is_active"]:
        if field in data:
            updates[field] = data[field]
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    result = await db.banners.update_one({"id": banner_id}, {"$set": updates})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Banner not found")
    return {"success": True, "message": "Banner updated"}

@api_router.delete("/admin/banners/{banner_id}")
async def delete_banner(banner_id: str, payload: dict = Depends(verify_jwt_token)):
    """Delete a banner"""
    result = await db.banners.delete_one({"id": banner_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Banner not found")
    return {"success": True, "message": "Banner deleted"}

@api_router.post("/admin/banners/{banner_id}/upload-image")
async def upload_banner_image(
    banner_id: str,
    file: UploadFile = File(...),
    payload: dict = Depends(verify_jwt_token)
):
    """Upload image for a banner"""
    contents = await file.read()
    if len(contents) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Image too large. Max 5MB.")
    ext = file.filename.split(".")[-1].lower() if "." in file.filename else "jpg"
    if ext not in ("jpg", "jpeg", "png", "webp", "gif"):
        ext = "jpg"
    filename = f"banner_{banner_id}.{ext}"
    # Feb 2026 (Point 43): banner uploads move to Emergent Object Storage.
    # Pod-local files are gone on every redeploy and inaccessible from the
    # deployed app URL — why admin banner uploads never showed up in-app.
    from storage import aput_object, APP_NAME
    content_type = f"image/{'jpeg' if ext in ('jpg','jpeg') else ext}"
    objstore_path = f"{APP_NAME}/banners/{filename}"
    put_result = await aput_object(objstore_path, contents, content_type)
    if not put_result:
        raise HTTPException(status_code=502, detail="Object storage upload failed. Retry in ~10s.")
    backend_url = os.environ.get("BACKEND_PUBLIC_URL", "").rstrip("/")
    image_url = f"{backend_url}/api/uploaded-image/banners/{filename}"
    await db.banners.update_one({"id": banner_id}, {"$set": {"image_url": image_url, "updated_at": datetime.now(timezone.utc).isoformat()}})
    return {"success": True, "image_url": image_url}


@api_router.get("/uploaded-image/{category}/{filename}")
async def serve_uploaded_image(category: str, filename: str):
    """Feb 2026 (Point 43): serve brand/banner uploads from Emergent Object
    Storage. Public endpoint (no auth) because these are marketing assets
    embedded in <img> tags across the consumer PWA. Backs the URL scheme
    written by upload_brand_image / upload_banner_image."""
    if category not in ("brands", "banners"):
        raise HTTPException(status_code=404, detail="Unknown asset category")
    # Simple filename allowlist to block path traversal
    if "/" in filename or ".." in filename or filename.startswith("."):
        raise HTTPException(status_code=400, detail="Invalid filename")
    from storage import aget_object, APP_NAME
    from fastapi.responses import Response as _StreamResp
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "jpg"
    fallback_ct = f"image/{'jpeg' if ext in ('jpg','jpeg') else ext}"
    fetched = await aget_object(f"{APP_NAME}/{category}/{filename}")
    if not fetched:
        raise HTTPException(status_code=404, detail="Image not found")
    data, ctype = fetched
    return _StreamResp(
        content=data,
        media_type=ctype or fallback_ct,
        headers={"Cache-Control": "public, max-age=86400"},
    )


@api_router.post("/admin/brands/import")
async def import_brands(data: dict, payload: dict = Depends(verify_jwt_token)):
    """Import brands with ATV from a list"""
    brands_data = data.get("brands", [])
    
    if not brands_data:
        raise HTTPException(status_code=400, detail="No brands provided")
    
    imported = 0
    updated = 0
    
    for item in brands_data:
        brand_name = str(item.get("brand_name", "")).strip()
        atv = float(item.get("atv", 0))
        
        if not brand_name or brand_name.lower() in ["", "nan", "none"]:
            continue
        
        # Check if brand exists
        existing = await db.brands.find_one({"brand_name": {"$regex": f"^{brand_name}$", "$options": "i"}})
        
        if existing:
            # Update ATV
            await db.brands.update_one(
                {"id": existing["id"]},
                {"$set": {"atv": atv, "updated_at": datetime.now(timezone.utc).isoformat()}}
            )
            updated += 1
        else:
            # Create new brand
            brand = BrandConfig(brand_name=brand_name, atv=atv)
            await db.brands.insert_one(brand.model_dump())
            imported += 1
    
    logger.info(f"Brand import complete: {imported} new, {updated} updated")
    return {"success": True, "imported": imported, "updated": updated}

@api_router.post("/admin/brands/upload-excel")
async def upload_brands_excel(
    file: UploadFile = File(...),
    payload: dict = Depends(verify_jwt_token)
):
    """Upload Excel/CSV file with brand names and ATV values.
    Expected columns: Brand Name, ATV (can be in any order)
    """
    import openpyxl
    
    logger.info(f"Uploading brands Excel: {file.filename}")
    
    content = await file.read()
    brands_data = []
    
    try:
        if file.filename.lower().endswith('.csv'):
            # Parse CSV
            content_str = content.decode('utf-8', errors='ignore')
            lines = content_str.strip().split('\n')
            
            # Find header row
            header = None
            brand_col = -1
            atv_col = -1
            
            for i, line in enumerate(lines):
                cols = [c.strip().lower() for c in line.split(',')]
                for j, col in enumerate(cols):
                    if 'brand' in col or 'name' in col:
                        brand_col = j
                    if 'atv' in col or 'average' in col or 'value' in col:
                        atv_col = j
                if brand_col >= 0:
                    header = i
                    break
            
            if brand_col < 0:
                brand_col = 0  # Default to first column
            if atv_col < 0:
                atv_col = 1  # Default to second column
            
            # Parse data rows
            for line in lines[header+1 if header is not None else 1:]:
                cols = line.split(',')
                if len(cols) > max(brand_col, atv_col):
                    brand_name = cols[brand_col].strip().strip('"')
                    try:
                        atv = float(cols[atv_col].strip().strip('"').replace(',', ''))
                    except Exception:
                        atv = 0
                    if brand_name and brand_name.lower() not in ['', 'nan', 'none', 'brand', 'brand name']:
                        brands_data.append({"brand_name": brand_name, "atv": atv})
        
        else:
            # Parse Excel
            workbook = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
            sheet = workbook.active
            
            # Find header row and columns
            header_row = None
            brand_col = -1
            atv_col = -1
            
            for row_idx, row in enumerate(sheet.iter_rows(values_only=True), 1):
                if row:
                    for col_idx, cell in enumerate(row):
                        if cell:
                            cell_str = str(cell).lower()
                            if 'brand' in cell_str or 'name' in cell_str:
                                brand_col = col_idx
                                header_row = row_idx
                            if 'atv' in cell_str or 'average' in cell_str:
                                atv_col = col_idx
                if header_row:
                    break
            
            if brand_col < 0:
                brand_col = 0
            if atv_col < 0:
                atv_col = 1
            
            # Parse data rows
            for row_idx, row in enumerate(sheet.iter_rows(values_only=True), 1):
                if header_row and row_idx <= header_row:
                    continue
                if row and len(row) > max(brand_col, atv_col):
                    brand_name = str(row[brand_col] or '').strip()
                    try:
                        atv = float(row[atv_col] or 0)
                    except Exception:
                        atv = 0
                    if brand_name and brand_name.lower() not in ['', 'nan', 'none', 'brand', 'brand name']:
                        brands_data.append({"brand_name": brand_name, "atv": atv})
            
            workbook.close()
        
        logger.info(f"Parsed {len(brands_data)} brands from file")
        
        if not brands_data:
            return {"success": False, "message": "No valid brands found in file", "imported": 0, "updated": 0}
        
        # Import brands
        imported = 0
        updated = 0
        
        for item in brands_data:
            brand_name = item["brand_name"]
            atv = item["atv"]
            
            existing = await db.brands.find_one({"brand_name": {"$regex": f"^{brand_name}$", "$options": "i"}})
            
            if existing:
                await db.brands.update_one(
                    {"id": existing["id"]},
                    {"$set": {"atv": atv, "updated_at": datetime.now(timezone.utc).isoformat()}}
                )
                updated += 1
            else:
                brand = BrandConfig(brand_name=brand_name, atv=atv)
                await db.brands.insert_one(brand.model_dump())
                imported += 1
        
        # Log upload history
        upload_record = {
            "id": str(uuid.uuid4()),
            "filename": file.filename,
            "uploaded_by": payload.get("username", "unknown"),
            "uploaded_at": datetime.now(timezone.utc).isoformat(),
            "brands_in_file": len(brands_data),
            "imported": imported,
            "updated": updated
        }
        await db.brand_upload_history.insert_one(upload_record)
        
        total_brands = await db.brands.count_documents({})
        
        return {
            "success": True,
            "message": f"Imported {imported} new brands, updated {updated} existing",
            "imported": imported,
            "updated": updated,
            "brands_in_file": len(brands_data),
            "total_brands": total_brands
        }
        
    except Exception as e:
        logger.error(f"Error processing brands Excel: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error processing file: {str(e)}")

@api_router.get("/admin/brands/upload-history")
async def get_brand_upload_history(payload: dict = Depends(verify_jwt_token)):
    """Get history of brand file uploads"""
    history = await db.brand_upload_history.find({}, {"_id": 0}).sort("uploaded_at", -1).limit(20).to_list(20)
    return {"history": history}


@api_router.post("/admin/brands/upload-categories-excel")
async def upload_brands_categories_excel(
    file: UploadFile = File(...),
    payload: dict = Depends(verify_jwt_token)
):
    """Upload Excel/CSV file with brand names and category taxonomy.
    Expected columns (any order, header row detected automatically):
        Brand Name, Category, Sub Category, Sub Category 2
    Never touches `atv` — pair with /upload-excel for ATV updates."""
    import openpyxl
    import io as _io

    logger.info(f"Uploading brand categories: {file.filename}")
    content = await file.read()
    rows = []

    def _match_col(cell_str: str):
        s = (cell_str or "").strip().lower()
        if not s: return None
        if s in ("brand", "brand name", "brand_name", "name"): return "brand_name"
        if s in ("categery", "category"): return "category"
        if s in ("sub categery", "sub category", "sub_category", "subcategory"): return "sub_category"
        if s in ("sub categery 2", "sub category 2", "sub_category_2", "subcategory 2"): return "sub_category_2"
        return None

    try:
        if file.filename and file.filename.lower().endswith('.csv'):
            import csv
            text = content.decode('utf-8-sig', errors='ignore')
            reader = csv.reader(_io.StringIO(text))
            all_rows = list(reader)
            header_idx, col_map = None, {}
            for i, row in enumerate(all_rows):
                mapped = {j: _match_col(str(c)) for j, c in enumerate(row)}
                if any(v == "brand_name" for v in mapped.values()):
                    header_idx = i
                    col_map = {v: j for j, v in mapped.items() if v}
                    break
            if header_idx is None:
                raise HTTPException(400, "Could not find header row with 'Brand Name' column")
            for row in all_rows[header_idx + 1:]:
                if len(row) <= col_map["brand_name"]: continue
                b = str(row[col_map["brand_name"]] or "").strip()
                if not b: continue
                def _get(k):
                    idx = col_map.get(k)
                    if idx is None or idx >= len(row): return ""
                    return str(row[idx] or "").strip()
                rows.append({
                    "brand_name": b,
                    "category": _get("category"),
                    "sub_category": _get("sub_category"),
                    "sub_category_2": _get("sub_category_2"),
                })
        else:
            wb = openpyxl.load_workbook(_io.BytesIO(content), read_only=True, data_only=True)
            sh = wb.active
            all_rows = list(sh.iter_rows(values_only=True))
            header_idx, col_map = None, {}
            for i, row in enumerate(all_rows):
                if not row: continue
                mapped = {j: _match_col(str(c) if c is not None else "") for j, c in enumerate(row)}
                if any(v == "brand_name" for v in mapped.values()):
                    header_idx = i
                    col_map = {v: j for j, v in mapped.items() if v}
                    break
            if header_idx is None:
                raise HTTPException(400, "Could not find header row with 'Brand Name' column")
            for row in all_rows[header_idx + 1:]:
                if not row: continue
                b_idx = col_map.get("brand_name")
                if b_idx is None or b_idx >= len(row): continue
                b = str(row[b_idx] or "").strip()
                if not b or b.lower() in ("nan", "none"): continue
                def _get(k):
                    idx = col_map.get(k)
                    if idx is None or idx >= len(row): return ""
                    v = row[idx]
                    return str(v).strip() if v is not None else ""
                rows.append({
                    "brand_name": b,
                    "category": _get("category"),
                    "sub_category": _get("sub_category"),
                    "sub_category_2": _get("sub_category_2"),
                })
            wb.close()

        logger.info(f"Parsed {len(rows)} brand-category rows")
        if not rows:
            return {"success": False, "message": "No valid rows found",
                    "imported": 0, "updated": 0}

        imported, updated = 0, 0
        now = datetime.now(timezone.utc).isoformat()
        for r in rows:
            existing = await db.brands.find_one({
                "brand_name": {"$regex": f"^{re.escape(r['brand_name'])}$", "$options": "i"}
            })
            update_doc = {
                "category": r["category"],
                "sub_category": r["sub_category"],
                "sub_category_2": r["sub_category_2"],
                "updated_at": now,
            }
            if existing:
                await db.brands.update_one({"id": existing["id"]}, {"$set": update_doc})
                updated += 1
            else:
                new_doc = BrandConfig(brand_name=r["brand_name"], atv=0.0).model_dump()
                new_doc.update(update_doc)
                await db.brands.insert_one(new_doc)
                imported += 1

        await db.brand_upload_history.insert_one({
            "id": str(uuid.uuid4()),
            "filename": file.filename,
            "kind": "categories",
            "uploaded_by": payload.get("username", "unknown"),
            "uploaded_at": now,
            "brands_in_file": len(rows),
            "imported": imported,
            "updated": updated,
        })

        return {
            "success": True,
            "message": f"Imported {imported} new brands, updated categories on {updated} existing",
            "imported": imported,
            "updated": updated,
            "brands_in_file": len(rows),
            "total_brands": await db.brands.count_documents({}),
            "preview": rows[:5],
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Category upload failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@api_router.get("/admin/brands/lookup/{store_name}")
async def lookup_brand_atv(store_name: str, payload: dict = Depends(verify_jwt_token)):
    """Lookup brand ATV by store name"""
    brand = await db.brands.find_one(
        {"brand_name": {"$regex": f"^{store_name}$", "$options": "i"}},
        {"_id": 0}
    )
    if brand:
        return {"found": True, "brand": brand}
    return {"found": False, "brand": None}

@api_router.post("/admin/sync-fundle-customers")
async def sync_fundle_customers(payload: dict = Depends(verify_jwt_token)):
    """Force sync ALL users with fundle_customers list.
    Any user whose phone is in fundle_customers will be marked as 'existing'.
    This runs WITHOUT any condition checks - just hard converts based on phone match.
    """
    logger.info("Starting force sync of users with fundle_customers list...")
    
    # Get all phone numbers from fundle_customers
    fundle_phones = await db.fundle_customers.find({}, {"phone_10": 1, "_id": 0}).to_list(50000)
    phone_set_10 = set(doc["phone_10"] for doc in fundle_phones)
    phone_set_12 = set("91" + doc["phone_10"] for doc in fundle_phones)
    
    logger.info(f"Found {len(phone_set_10)} phone numbers in fundle_customers list")
    
    # Get all users
    all_users = await db.users.find({}, {"_id": 0, "id": 1, "phone": 1, "customer_type": 1}).to_list(100000)
    logger.info(f"Found {len(all_users)} total users in database")
    
    updated_count = 0
    already_existing = 0
    
    for user in all_users:
        phone = user.get("phone", "")
        # Extract 10-digit number
        phone_10 = phone[2:] if phone.startswith("91") and len(phone) == 12 else phone
        
        # Check if this phone is in fundle_customers
        if phone_10 in phone_set_10 or phone in phone_set_12:
            if user.get("customer_type") != "existing":
                # Force update to existing
                await db.users.update_one(
                    {"id": user["id"]},
                    {"$set": {"customer_type": "existing"}}
                )
                updated_count += 1
                logger.info(f"Updated user {phone} to 'existing'")
            else:
                already_existing += 1
    
    logger.info(f"Sync complete: {updated_count} users updated to 'existing', {already_existing} already existing")
    
    return {
        "success": True,
        "message": "Force synced users with fundle_customers list",
        "fundle_customers_count": len(phone_set_10),
        "total_users": len(all_users),
        "updated_to_existing": updated_count,
        "already_existing": already_existing
    }

# ======================== WHATSAPP LOGS ROUTES ========================

@api_router.get("/whatsapp/logs")
async def get_whatsapp_logs(
    skip: int = 0,
    limit: int = 100,
    phone: Optional[str] = None,
    payload: dict = Depends(verify_jwt_token)
):
    """Get all WhatsApp logs with conversation view"""
    query = {}
    if phone:
        query["user_phone"] = {"$regex": phone}
    
    total = await db.whatsapp_logs.count_documents(query)
    logs = await db.whatsapp_logs.find(query, {"_id": 0}).skip(skip).limit(limit).sort("timestamp", -1).to_list(limit)
    
    return {"logs": logs, "total": total, "skip": skip, "limit": limit}

@api_router.get("/whatsapp/conversations")
async def get_whatsapp_conversations(payload: dict = Depends(verify_jwt_token)):
    """Get all unique phone conversations with latest message"""
    pipeline = [
        {"$sort": {"timestamp": -1}},
        {"$group": {
            "_id": "$user_phone",
            "last_message": {"$first": "$content"},
            "last_timestamp": {"$first": "$timestamp"},
            "message_count": {"$sum": 1},
            "user_id": {"$first": "$user_id"}
        }},
        {"$sort": {"last_timestamp": -1}},
        {"$limit": 100}
    ]
    conversations = await db.whatsapp_logs.aggregate(pipeline).to_list(100)
    
    # Enrich with user data
    result = []
    for conv in conversations:
        user = None
        if conv.get("user_id"):
            user = await db.users.find_one({"id": conv["user_id"]}, {"_id": 0, "name": 1, "phone": 1})
        result.append({
            "phone": conv["_id"],
            "user_name": user.get("name") if user else None,
            "last_message": conv["last_message"][:50] + "..." if len(conv.get("last_message", "")) > 50 else conv.get("last_message", ""),
            "last_timestamp": conv["last_timestamp"],
            "message_count": conv["message_count"]
        })
    
    return result

@api_router.get("/whatsapp/conversation/{phone}")
async def get_phone_conversation(phone: str, payload: dict = Depends(verify_jwt_token)):
    """Get all messages for a specific phone number"""
    # Normalize phone
    clean_phone = phone.replace("+", "").replace(" ", "")
    if len(clean_phone) == 10:
        clean_phone = "91" + clean_phone
    
    logs = await db.whatsapp_logs.find(
        {"user_phone": clean_phone},
        {"_id": 0}
    ).sort("timestamp", 1).to_list(500)
    
    # Get user info
    user = await db.users.find_one({"phone": clean_phone}, {"_id": 0})
    
    return {"messages": logs, "user": user, "phone": clean_phone}

# ======================== BILL ROUTES ========================

# ---- Point 49-b: brand mirror cache for audit badge ----
_BRAND_MIRROR_CACHE = {"names": set(), "expires_at": 0.0}

async def _brand_names_norm() -> set:
    """Return set of normalised brand_name strings from db.brands. Cached 60s."""
    import time as _t
    now = _t.time()
    if now < _BRAND_MIRROR_CACHE["expires_at"] and _BRAND_MIRROR_CACHE["names"]:
        return _BRAND_MIRROR_CACHE["names"]
    names = set()
    try:
        async for d in db.brands.find({"brand_name": {"$exists": True, "$ne": ""}}, {"_id": 0, "brand_name": 1}):
            n = (d.get("brand_name") or "").strip().lower()
            if n:
                names.add(re.sub(r"[^a-z0-9]+", "", n))
    except Exception as e:
        logger.warning(f"_brand_names_norm failed: {e}")
    _BRAND_MIRROR_CACHE["names"] = names
    _BRAND_MIRROR_CACHE["expires_at"] = now + 60.0
    return names


def _brand_in_mirror(store_name: str, mirror: set) -> bool:
    if not store_name:
        return False
    key = re.sub(r"[^a-z0-9]+", "", (store_name or "").strip().lower())
    return bool(key and key in mirror)


@api_router.get("/bills")
async def get_bills(
    skip: int = 0,
    limit: int = 50,
    status: Optional[str] = None,
    qr_source: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    payload: dict = Depends(verify_jwt_token)
):
    """Get all bills with pagination and filters"""
    query = {}
    if status:
        query["status"] = status

    # If filtering by QR source, we need to look up users first
    if qr_source:
        user_ids = await db.users.distinct("id", {"first_touch_source": qr_source})
        query["user_id"] = {"$in": user_ids}

    # Date range filter on created_at (ISO string compare works since stored as ISO)
    if start_date or end_date:
        date_q = {}
        if start_date:
            date_q["$gte"] = start_date
        if end_date:
            # Make end inclusive to end-of-day
            if len(end_date) == 10:  # YYYY-MM-DD
                date_q["$lte"] = end_date + "T23:59:59.999Z"
            else:
                date_q["$lte"] = end_date
        query["created_at"] = date_q

    total = await db.bills.count_documents(query)
    # Drop the inline base64 image_url from list responses — it's ~180 KB per
    # bill and turns a 50-item page into 10 MB. Admin UI fetches the image
    # on demand via /api/bills/{id}/image when the row is expanded.
    projection = {
        "_id": 0,
        "image_url": 0,
        "ocr_raw_data": 0,
    }
    bills = await db.bills.find(query, projection).skip(skip).limit(limit).sort("created_at", -1).to_list(limit)

    # Point 49-c: mark bills whose store_name isn't in the local brands
    # mirror so the admin UI can flag them (missing brand → likely Fundle
    # rejection on upload). Cheap in-memory set membership check.
    try:
        mirror = await _brand_names_norm()
        for b in bills:
            b["brand_in_mirror"] = _brand_in_mirror(b.get("store_name") or "", mirror)
    except Exception as _e:
        logger.warning(f"brand_in_mirror flag skip: {_e}")

    return {"bills": bills, "total": total, "skip": skip, "limit": limit}

@api_router.get("/bills/by-qr/{qr_code_id}")
async def get_bills_by_qr(
    qr_code_id: str,
    skip: int = 0,
    limit: int = 50,
    payload: dict = Depends(verify_jwt_token)
):
    """Get all bills uploaded by users from a specific QR code"""
    # Find QR code to get source code
    qr_data = next((qr for qr in QR_CODES if qr["qr_code_id"] == qr_code_id), None)
    if not qr_data:
        raise HTTPException(status_code=404, detail="QR code not found")
    
    source_code = qr_data["source_code"]
    
    # Get all user IDs who came from this QR
    user_ids = await db.users.distinct("id", {"first_touch_source": source_code})
    
    # Get bills from these users
    query = {"user_id": {"$in": user_ids}}
    total = await db.bills.count_documents(query)
    bills = await db.bills.find(query, {"_id": 0}).skip(skip).limit(limit).sort("created_at", -1).to_list(limit)
    
    # Enrich with user phone numbers
    for bill in bills:
        user = await db.users.find_one({"id": bill.get("user_id")}, {"phone": 1, "name": 1})
        if user:
            bill["user_name"] = user.get("name")
    
    return {
        "bills": bills, 
        "total": total, 
        "qr_code_id": qr_code_id,
        "source_code": source_code,
        "location": qr_data.get("location")
    }

@api_router.get("/bills/pending-review")
async def get_pending_bills(payload: dict = Depends(verify_jwt_token)):
    """Get bills pending manual review with full details"""
    # Pending review list: omit the inline image_url + heavy ocr_raw_data — admin
    # loads them on-demand via /api/bills/{id}/image and /api/bills/{id}.
    pipeline = [
        {"$match": {"status": {"$in": ["manual_review", "pending_review"]}}},
        {"$lookup": {
            "from": "users",
            "localField": "user_id",
            "foreignField": "id",
            "as": "user_info"
        }},
        {"$unwind": {"path": "$user_info", "preserveNullAndEmptyArrays": True}},
        {"$project": {
            "_id": 0,
            "id": 1,
            "user_id": 1,
            "user_phone": 1,
            "user_name": "$user_info.name",
            "user_source": "$user_info.first_touch_source",
            "user_qr": "$user_info.first_touch_qr",
            "store_name": 1,
            "bill_no": 1,
            "bill_date": 1,
            "amount": 1,
            "tax": 1,
            "status": 1,
            "image_hash": 1,
            "ocr_confidence": 1,
            "has_image": {"$cond": [{"$ifNull": ["$image_url", False]}, True, False]},
            "system_rejection_reason": "$rejection_reason",
            "invoice_mobile": 1,
            "processed_by": 1,
            "processed_by_username": 1,
            "processed_by_role": 1,
            "processed_at": 1,
            "created_at": 1
        }},
        {"$sort": {"created_at": 1}}
    ]
    bills_list = await db.bills.aggregate(pipeline).to_list(100)
    # Point 49-c: brand-in-mirror flag for pending review too
    try:
        mirror = await _brand_names_norm()
        for b in bills_list:
            b["brand_in_mirror"] = _brand_in_mirror(b.get("store_name") or "", mirror)
    except Exception as _e:
        logger.warning(f"brand_in_mirror flag (pending) skip: {_e}")
    # $project already drops _id; map to plain dicts so the EB lint stays happy
    return [dict(b) for b in bills_list]


@api_router.get("/bills/{bill_id}/image/stream")
async def stream_bill_image(bill_id: str, payload: dict = Depends(verify_jwt_token)):
    """Point 49-b: Raw byte stream for bill images. Cuts admin UI load from
    ~180KB base64 JSON per image to raw bytes — Bill Review opens instantly
    even for legacy multi-MB images. Auth-gated (admin JWT).
    """
    from fastapi.responses import StreamingResponse, Response
    from pymongo.errors import NetworkTimeout, AutoReconnect, ServerSelectionTimeoutError, ExecutionTimeout
    _retryable = (NetworkTimeout, AutoReconnect, ServerSelectionTimeoutError, ExecutionTimeout)
    try:
        b = None
        for attempt in range(2):
            try:
                b = await db.bills.find_one({"id": bill_id}, {"_id": 0, "image_url": 1}, max_time_ms=25000)
                break
            except _retryable:
                if attempt == 0:
                    await asyncio.sleep(0.3); continue
                raise
        if not b:
            raise HTTPException(status_code=404, detail="Bill not found")
        raw = (b.get("image_url") or "") if isinstance(b.get("image_url"), str) else ""
        data: Optional[bytes] = None
        ctype = "image/jpeg"
        if raw.startswith("objstore:"):
            try:
                from storage import aresolve_objstore_url
                fetched = await aresolve_objstore_url(raw)
                if fetched:
                    data, ctype = fetched
            except Exception as e:
                logger.warning(f"stream_bill_image objstore read failed: {e}")
        elif raw.startswith("data:"):
            try:
                head, b64 = raw.split(",", 1)
                if ";" in head and ":" in head:
                    ctype = head.split(":", 1)[1].split(";", 1)[0] or "image/jpeg"
                data = base64.b64decode(b64, validate=False)
            except Exception:
                data = None
        elif raw.startswith("base64:"):
            try:
                data = base64.b64decode(raw[7:], validate=False)
            except Exception:
                data = None
        elif raw.startswith("http"):
            try:
                async with httpx.AsyncClient(timeout=8.0) as cx:
                    headers = {"Authorization": f"Bearer {KARIX_API_KEY}"} if KARIX_API_KEY else {}
                    r = await cx.get(raw, headers=headers)
                    if r.status_code != 200 and headers:
                        r = await cx.get(raw)
                    if r.status_code == 200 and r.content:
                        data = r.content
                        ctype = r.headers.get("content-type", "image/jpeg").split(";")[0].strip() or "image/jpeg"
            except Exception as e:
                logger.warning(f"stream_bill_image http fetch failed: {e}")
        if not data:
            raise HTTPException(status_code=404, detail="Image not available")
        return Response(content=data, media_type=ctype, headers={
            "Cache-Control": "private, max-age=300",
            "Content-Length": str(len(data)),
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"stream_bill_image failed for {bill_id}: {e}")
        raise HTTPException(status_code=500, detail="Image stream failed")


@api_router.get("/admin/bills/brand-audit")
async def brand_audit_bills(
    limit: int = 100,
    skip: int = 0,
    payload: dict = Depends(verify_jwt_token),
):
    """Point 49-c: List every bill whose store_name isn't in the local
    brands mirror. Admins use this to seed missing brands/categories BEFORE
    customers upload — pre-empting Fundle rejections."""
    mirror = await _brand_names_norm()
    # Pull recent bills, then filter in-process by mirror membership.
    total_scanned = 0
    missing = []
    async for b in db.bills.find(
        {"store_name": {"$exists": True, "$ne": ""}},
        {"_id": 0, "id": 1, "store_name": 1, "amount": 1, "status": 1, "user_phone": 1, "created_at": 1, "points_issued": 1, "force_credited": 1},
    ).sort("created_at", -1).limit(2000):
        total_scanned += 1
        sn = (b.get("store_name") or "").strip()
        if not _brand_in_mirror(sn, mirror):
            missing.append(b)
    return {
        "total_scanned": total_scanned,
        "total_missing": len(missing),
        "bills": missing[skip:skip+limit],
    }


class PushToFundleResponse(BaseModel):
    success: bool
    message: str
    fundle_points: int = 0
    delta_points: int = 0


@api_router.post("/admin/bills/{bill_id}/push-to-fundle", response_model=PushToFundleResponse)
async def push_bill_to_fundle(bill_id: str, payload: dict = Depends(verify_jwt_token)):
    """Point 49-d: Resend a locally force-credited bill to Fundle. Reconciles
    the user's local balance to match Fundle's earned points (adjusts by the
    delta between the old force-credit and the new Fundle credit). If Fundle
    still rejects, the bill stays force-credited and admin sees the error."""
    bill = await db.bills.find_one({"id": bill_id}, {"_id": 0}, max_time_ms=15000)
    if not bill:
        raise HTTPException(status_code=404, detail="Bill not found")
    if not bill.get("force_credited"):
        raise HTTPException(status_code=400, detail="Only force-credited bills can be pushed to Fundle")
    if bill.get("fundle_pushed_at"):
        raise HTTPException(status_code=400, detail="Already pushed to Fundle")

    phone = bill.get("user_phone") or ""
    mobile_10 = re.sub(r"\D", "", phone)[-10:]
    if not mobile_10:
        raise HTTPException(status_code=400, detail="Bill has no valid user phone")
    amount = float(bill.get("amount") or 0)
    bill_no = bill.get("bill_no") or f"WA-{bill_id[:8].upper()}"
    bill_date = bill.get("bill_date") or datetime.now().strftime("%Y-%m-%d")
    store_name = (bill.get("store_name") or "").strip()

    # Load image bytes for Fundle attachment (same as OCR / reprocess path)
    image_base64 = None
    raw = bill.get("image_url") or ""
    if isinstance(raw, str):
        if raw.startswith("objstore:"):
            try:
                from storage import aresolve_objstore_url
                fetched = await aresolve_objstore_url(raw)
                if fetched:
                    image_base64 = base64.b64encode(fetched[0]).decode()
            except Exception:
                pass
        elif raw.startswith("data:") and "," in raw:
            image_base64 = raw.split(",", 1)[1]
        elif raw.startswith("base64:"):
            image_base64 = raw[7:]

    earn = await tagnpay_client.earn_points(
        mobile_number=mobile_10, bill_amount=amount, bill_number=bill_no,
        bill_date=bill_date, store_name=store_name, bill_image_base64=image_base64,
    )
    fundle_points = 0
    if earn.get("success") and earn.get("data"):
        fundle_points = int(earn["data"].get("earned_points", 0) or 0)
    if fundle_points <= 0:
        err = earn.get("error") or (earn.get("data") or {}).get("message") or "Fundle returned 0 points"
        # Reviewer feedback (iter-80): persist the last push attempt so admins
        # see why repeated clicks aren't landing.
        try:
            await db.bills.update_one({"id": bill_id}, {"$set": {
                "last_push_attempt_at": datetime.now(timezone.utc).isoformat(),
                "last_push_error": err[:200],
            }})
        except Exception:
            pass
        return PushToFundleResponse(success=False, message=f"Fundle rejected: {err}", fundle_points=0, delta_points=0)

    # Reconcile local balance: delta = fundle_points - old force-credited points
    old_local = int(bill.get("points_issued") or 0)
    delta = fundle_points - old_local
    if delta != 0:
        user_id = bill.get("user_id")
        if user_id:
            await db.users.update_one(
                {"id": user_id},
                {"$inc": {"balance_points": delta, "total_earned_points": delta}},
            )
    await db.bills.update_one({"id": bill_id}, {"$set": {
        "points_issued": fundle_points,
        "force_credited": False,
        "processed_by": "admin_push_to_fundle",
        "processed_by_username": payload.get("username") or "admin",
        "fundle_pushed_at": datetime.now(timezone.utc).isoformat(),
        "fundle_original_error": None,
    }})
    return PushToFundleResponse(
        success=True,
        message=f"Fundle accepted with {fundle_points} pts (local balance adjusted by {delta:+d})",
        fundle_points=fundle_points,
        delta_points=delta,
    )


@api_router.get("/bills/{bill_id}/image")
async def get_bill_image(bill_id: str, background_tasks: BackgroundTasks, payload: dict = Depends(verify_jwt_token)):
    """Return just the inline base64 image for a single bill (loaded on demand
    by the admin UI). Keeps list endpoints cheap.

    Point 24: Normalize the image_url so the browser can always render it —
      • data:image/...  → returned as-is
      • base64:<b64>    → wrapped as data:image/jpeg;base64,<b64>
      • https://... (Karix)  → fetched server-side with Karix Bearer auth and
        returned as data:image/jpeg;base64,... so the admin browser doesn't
        hit 401/403 loading a signed WhatsApp media URL.

    Feb 2026 hardening: wrap the whole handler in try/except so any edge case
    (bad legacy row shape, mongo hiccup, oversized fetch response) surfaces
    as a 200-with-fetch_error rather than a blind HTTP 500 that the admin UI
    then renders as "Image endpoint returned HTTP 500".
    """
    try:
        # Feb 2026: explicit one-shot retry on transient socket / server-selection
        # timeouts. Atlas can hiccup under load; one retry after 300ms handles
        # transient blips without user-visible latency in the common case.
        # Narrow to pymongo transient classes so real bugs (auth, decode) are not
        # retried and delayed by 300ms unnecessarily.
        from pymongo.errors import NetworkTimeout, AutoReconnect, ServerSelectionTimeoutError, ExecutionTimeout
        _retryable = (NetworkTimeout, AutoReconnect, ServerSelectionTimeoutError, ExecutionTimeout)
        b = None
        for attempt in range(2):
            try:
                # Feb 2026: 25s maxTimeMS gives Atlas headroom to stream a
                # multi-MB legacy inline image_url without tripping the
                # server-side MaxTimeMSExpired (which was surfacing as
                # "Executor error during find command" in the admin UI).
                # Migrated bills return in <100ms so the ceiling doesn't
                # affect the common path.
                b = await db.bills.find_one(
                    {"id": bill_id},
                    {"_id": 0, "image_url": 1, "image_hash": 1},
                    max_time_ms=25000,
                )
                break
            except _retryable:
                if attempt == 0:
                    await asyncio.sleep(0.3)
                    continue
                raise
        if not b:
            raise HTTPException(status_code=404, detail="Bill not found")

        raw = b.get("image_url") or ""
        normalized = raw if isinstance(raw, str) else ""
        fetch_error: Optional[str] = None

        # Feb 2026 (session-20): objstore:<path> is the new preferred storage
        # for bill images — the Mongo doc is <1KB instead of multi-MB, so
        # find_one is instant and only the actual bytes travel over the
        # object-storage CDN. Legacy inline URLs are progressively migrated
        # by the code path below.
        if isinstance(raw, str) and raw.startswith("objstore:"):
            try:
                from storage import aresolve_objstore_url
                fetched = await aresolve_objstore_url(raw)
                if fetched:
                    data, ctype = fetched
                    normalized = f"data:{ctype or 'image/jpeg'};base64,{base64.b64encode(data).decode()}"
                else:
                    normalized = None
                    fetch_error = "Object storage returned no data (path may be missing)."
            except Exception as e:
                normalized = None
                fetch_error = f"Object storage read error: {str(e)[:120]}"
        elif isinstance(raw, str) and raw.startswith("base64:"):
            payload_b64 = raw[7:]
            # Apply the same <200-byte corrupted-placeholder guard as the
            # data: branch so legacy short base64 payloads also surface
            # the friendly "unreadable" hint.
            if len(payload_b64) < 200:
                normalized = None
                fetch_error = "Stored image is a placeholder / corrupted (bad save). Ask the customer to resend the bill."
            else:
                normalized = f"data:image/jpeg;base64,{payload_b64}"
        elif isinstance(raw, str) and raw.startswith("data:"):
            # Point 39: guard against corrupted / truncated data URLs that were
            # persisted from a broken save. Anything under 200 bytes is a
            # placeholder — return None so the UI shows the "unreadable" hint.
            if len(raw) < 200:
                normalized = None
                fetch_error = "Stored image is a placeholder / corrupted (bad save). Ask the customer to resend the bill."
            else:
                normalized = raw
        elif isinstance(raw, str) and raw.startswith("http"):
            try:
                # Feb 2026: cap the remote WhatsApp/Karix media fetch at 8s so
                # a hung upstream cannot hold the request past Cloudflare's
                # ~30s edge timeout — that was the last unbounded wait that
                # could still surface as a raw HTTP 500 to the admin UI.
                async with httpx.AsyncClient(timeout=8.0) as cx:
                    headers = {}
                    if KARIX_API_KEY:
                        headers = {
                            "Authentication": f"Bearer {KARIX_API_KEY}",
                            "Authorization": f"Bearer {KARIX_API_KEY}",
                        }
                    r = await cx.get(raw, headers=headers)
                    if r.status_code != 200 and headers:
                        # Fallback without auth (some CDN URLs work anonymously)
                        r = await cx.get(raw)
                    if r.status_code == 200 and r.content:
                        ctype = r.headers.get("content-type", "image/jpeg").split(";")[0].strip() or "image/jpeg"
                        b64 = base64.b64encode(r.content).decode()
                        normalized = f"data:{ctype};base64,{b64}"
                        # Persist so the admin doesn't wait on Karix again next time
                        # and the image survives even if the signed URL expires.
                        # Skip the write when the encoded payload would exceed
                        # Mongo's 16MB doc cap — the download still serves.
                        try:
                            if len(normalized) < 15 * 1024 * 1024:
                                await db.bills.update_one({"id": bill_id}, {"$set": {"image_url": normalized}})
                        except Exception:
                            pass
                    else:
                        fetch_error = f"HTTP {r.status_code}"
                        normalized = None
            except Exception as e:
                fetch_error = str(e)[:120]
                normalized = None
        else:
            # Unknown / missing shape — return None with a diagnostic message
            # so the UI can show the "unreadable" state.
            if not raw:
                normalized = None
                fetch_error = "No image on record for this bill."
            else:
                normalized = None
                fetch_error = "Unrecognised image format on record."

        return {
            "image_url": normalized,
            "image_hash": b.get("image_hash"),
            "fetch_error": fetch_error,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"get_bill_image failed for bill_id={bill_id}: {e}")
        # Return 200-with-error so the admin UI shows the friendly hint
        # instead of an opaque HTTP 500.
        return {
            "image_url": None,
            "image_hash": None,
            "fetch_error": f"Server error while loading image: {str(e)[:120]}",
        }
    finally:
        # Session-20: progressive migration — if we successfully served an
        # inline data:image/... URL and it's fat (>50KB), schedule a
        # background task to move it into object storage so the next read
        # only fetches a <1KB Mongo doc.
        try:
            if (
                isinstance(raw, str)
                and normalized
                and isinstance(normalized, str)
                and normalized.startswith("data:image/")
                and not raw.startswith("objstore:")
                and len(normalized) > 50_000
            ):
                background_tasks.add_task(_migrate_bill_image_to_objstore, bill_id, normalized)
        except Exception:
            pass


async def _migrate_bill_image_to_objstore(bill_id: str, data_url: str):
    """Background task — take a data:image/*;base64,... URL and move it to
    Emergent Object Storage. Updates bills.image_url to `objstore:<path>` so
    the next /image call reads a tiny Mongo doc and streams bytes from the
    object-storage CDN. Silent no-op on any failure — inline URL stays in
    place so the UI still works."""
    try:
        header, _, payload_b64 = data_url.partition(",")
        if not payload_b64:
            return
        ctype = "image/jpeg"
        if "image/png" in header:
            ctype = "image/png"
        elif "image/webp" in header:
            ctype = "image/webp"
        try:
            raw_bytes = base64.b64decode(payload_b64)
        except Exception:
            return
        # Skip tiny placeholders — nothing to migrate.
        if len(raw_bytes) < 5_000:
            return
        from storage import aupload_bill_image
        new_url = await aupload_bill_image(bill_id, raw_bytes, ctype)
        if not new_url:
            return
        await db.bills.update_one({"id": bill_id}, {"$set": {
            "image_url": new_url,
            "image_migrated_at": datetime.now(timezone.utc).isoformat(),
        }})
        logger.info(f"Migrated bill {bill_id} image ({len(raw_bytes)} bytes) → {new_url}")
    except Exception as e:
        logger.warning(f"_migrate_bill_image_to_objstore failed for {bill_id}: {e}")

@api_router.get("/bills/{bill_id}")
async def get_bill_details(bill_id: str, payload: dict = Depends(verify_jwt_token)):
    """Get single bill with full details"""
    # Feb 2026: skip large fields (image_url multi-MB base64, ocr_raw_data) —
    # image is fetched on-demand via GET /api/bills/{id}/image. Pulling the
    # full doc here exceeded Atlas maxTimeMS on legacy bills.
    bill = await db.bills.find_one({"id": bill_id}, {"_id": 0, "image_url": 0, "ocr_raw_data": 0})
    if not bill:
        raise HTTPException(status_code=404, detail="Bill not found")
    
    # Get user info
    user = await db.users.find_one({"id": bill.get("user_id")}, {"_id": 0})
    
    return {
        "bill": bill,
        "user": user
    }

@api_router.post("/bills/{bill_id}/process")
async def process_bill(bill_id: str, request: BillProcessRequest, background_tasks: BackgroundTasks, payload: dict = Depends(verify_jwt_token)):
    """Approve or reject a bill with WhatsApp notification"""
    # Feb 2026: skip large fields (image_url multi-MB base64, ocr_raw_data) on
    # the initial fetch — pulling them over Atlas under load exceeded maxTimeMS
    # and produced the admin "Failed to process bill" 500 with 10s latency.
    # The image is only needed for the approve → TagnPay earn-points path, and
    # is re-fetched separately below with a targeted projection.
    bill = await db.bills.find_one(
        {"id": bill_id},
        {"image_url": 0, "ocr_raw_data": 0}
    )
    if not bill:
        raise HTTPException(status_code=404, detail="Bill not found")
    
    user = await db.users.find_one({"id": bill["user_id"]})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    phone = bill.get("user_phone") or user.get("phone")
    mobile_10 = phone[2:] if phone.startswith("91") and len(phone) == 12 else phone
    
    # Store full processor info (name, username, role)
    processor_info = {
        "username": payload.get("username"),
        "name": payload.get("name", payload.get("username")),
        "role": payload.get("role", "admin")
    }
    
    update_data = {
        "processed_at": datetime.now(timezone.utc).isoformat(),
        "processed_by": processor_info.get("name"),
        "processed_by_username": processor_info.get("username"),
        "processed_by_role": processor_info.get("role"),
        "admin_notes": request.admin_notes
    }
    
    whatsapp_message = ""
    
    if request.action == "approve":
        bill_amount = bill.get("amount") or 0
        store_name = bill.get("store_name") or "CP67 Mall"
        bill_no = bill.get("bill_no") or "N/A"
        bill_date = bill.get("bill_date") or "N/A"
        
        # Call TagnPay earn-points API
        # Point 38: use the robust resolver so http:// image URLs are downloaded
        # and re-encoded — the old ".split(',')[-1]" passed the URL as-is which
        # made base64.b64decode explode with "Incorrect padding".
        # Feb 2026: image_url was omitted from the initial find_one to avoid
        # Atlas maxTimeMS on multi-MB legacy bills — re-fetch just image_url
        # here so approve→TagnPay still has the payload.
        try:
            _img_doc = await db.bills.find_one(
                {"id": bill_id},
                {"_id": 0, "image_url": 1},
            )
            if _img_doc and _img_doc.get("image_url"):
                bill["image_url"] = _img_doc["image_url"]
        except Exception as _img_e:
            logger.warning(f"process_bill image re-fetch failed for {bill_id}: {_img_e}")
        bill_image_b64 = await _resolve_bill_image_base64(bill)
        earn_result = await tagnpay_client.earn_points(
            mobile_number=mobile_10,
            bill_amount=bill_amount,
            bill_number=bill_no,
            bill_date=bill_date,
            store_name=store_name,
            bill_image_base64=bill_image_b64,
        )
        
        logger.info(f"TagnPay earn-points for bill {bill_id}: {earn_result}")
        
        # Get points from TagnPay or calculate locally
        points_earned = 0
        total_balance = 0
        
        if earn_result.get("success") and earn_result.get("data"):
            points_earned = earn_result["data"].get("earned_points", 0)
            total_balance = earn_result["data"].get("total_points", 0)
        
        # If TagnPay didn't return points, use override or calculate
        if points_earned == 0:
            points_earned = request.points_override if request.points_override else int(bill_amount * 0.01)
        
        # Get current balance from TagnPay
        points_result = await tagnpay_client.get_customer_points(mobile_10)
        if points_result.get("success") and points_result.get("data"):
            total_balance = int(points_result["data"].get("balance_points", 0))
        
        # ------- Campaign Engine: apply active multipliers/bonuses -------
        campaign_bonus_points = 0
        applied_campaigns = []
        if points_earned > 0:
            is_first = await db.bills.count_documents({"user_id": bill["user_id"], "status": {"$in": ["auto_approved", "approved"]}}) == 0
            camp = await apply_campaign_bonus(
                bill_amount=bill_amount,
                base_points=points_earned,
                store_name=store_name,
                is_first_bill=is_first,
            )
            campaign_bonus_points = camp["bonus_points"]
            applied_campaigns = camp["applied_campaigns"]
            points_earned = camp["final_points"]
            if campaign_bonus_points > 0:
                update_data["campaign_bonus"] = campaign_bonus_points
                update_data["applied_campaigns"] = applied_campaigns
                logger.info(f"Campaign bonus applied on admin approve for bill {bill_id}: +{campaign_bonus_points}")

        update_data["status"] = "approved"
        update_data["points_issued"] = points_earned
        
        # Update user points in our DB
        await db.users.update_one(
            {"id": bill["user_id"]},
            {"$inc": {"balance_points": points_earned, "total_earned_points": points_earned}}
        )

        # Point 44 (Feb 2026): if this user came in via a parking QR and their
        # coupon was deferred pending a verified bill, this is that moment —
        # issue the PARK-XXXX coupon now. Idempotent, safe to call from every
        # approve path.
        try:
            await _maybe_issue_pending_parking_coupon(user.get("phone"))
        except Exception as _pe:
            logger.warning(f"parking coupon hook failed for {bill_id}: {_pe}")
        
        # Update QR analytics
        if user.get("first_touch_qr"):
            await db.qr_analytics.update_one(
                {"qr_code_id": user["first_touch_qr"]},
                {"$inc": {"bill_uploads": 1}},
                upsert=True
            )
        
        store_display = store_name if store_name and store_name != "None" else "CP67 Mall"
        # Success WhatsApp Message (per revised flow document)
        campaign_line = ""
        if campaign_bonus_points > 0 and applied_campaigns:
            names = ", ".join([c["name"] for c in applied_campaigns])
            campaign_line = f"\nBonus: +{campaign_bonus_points} pts ({names})"
        whatsapp_message = f"""Thank you for uploading your bill of {store_display} with Homeland Advantage.

Points Credited: {points_earned}{campaign_line}
Total Balance: {total_balance}

Earn more rewards every time you shop at CP67.

Download the CP67 App:
{os.environ.get('BACKEND_PUBLIC_URL', '')}/app/welcome

Happy Shopping!"""
        
    else:
        # Rejection
        system_reason = bill.get("rejection_reason") or bill.get("ocr_raw_data", {}).get("extraction_notes", "")
        admin_reason = request.rejection_reason or "Bill could not be verified"

        update_data["status"] = "rejected"
        update_data["system_rejection_reason"] = system_reason
        update_data["admin_rejection_reason"] = admin_reason

        # Log rejection to Fundle/TagnPay API IN BACKGROUND — this call can take 20-30s
        # on flaky Fundle latency and was previously blocking the reject response,
        # causing Cloudflare timeout and "Failed to process bill" toasts.
        bill_amount = bill.get("amount") or 0
        store_name_r = bill.get("store_name") or "Unknown"
        bill_no_r = bill.get("bill_no") or "N/A"
        bill_date_r = bill.get("bill_date") or datetime.now(timezone.utc).strftime("%Y-%m-%d")

        async def _log_reject_bg():
            try:
                await tagnpay_client.log_rejected_bill(
                    mobile_number=mobile_10,
                    bill_number=bill_no_r,
                    bill_amount=bill_amount,
                    bill_date=bill_date_r,
                    store_name=store_name_r,
                    rejection_reason=admin_reason,
                )
            except Exception as e:
                logger.error(f"BG TagnPay rejection log failed for bill {bill_id}: {e}")

        background_tasks.add_task(_log_reject_bg)

        # WhatsApp rejection message — use local balance instead of a fresh Fundle
        # fetch to keep the response fast. Frontend & user get an instant confirmation.
        u_doc = await db.users.find_one({"id": user["id"]}, {"_id": 0, "balance_points": 1})
        current_balance = int((u_doc or {}).get("balance_points") or 0)

        whatsapp_message = f"""We're sorry, but your bill could not be processed.

Reason: {admin_reason}

Your Current Points Balance: {current_balance}

Please ensure your next bill upload:
- Is clearly visible and not blurry
- Shows complete bill details
- Has not been submitted before

Keep shopping at CP67 Mall to earn more rewards!"""
    
    await db.bills.update_one({"id": bill_id}, {"$set": update_data})

    # Point 25: alert mall-ops on rejection so no rejected bill sits unnoticed
    if request.action == "reject":
        background_tasks.add_task(
            maybe_alert_admin, bill_id, "rejected",
            update_data.get("rejection_reason") or request.rejection_reason or ""
        )

    # Staff Incentive Sync — approve/reject affects any attached bill_upload incentive
    background_tasks.add_task(_sync_staff_incentive_for_bill, bill_id, update_data.get("status", ""), phone or "")
    
    # Send WhatsApp message if enabled
    if request.send_whatsapp and whatsapp_message:
        # Log outbound message
        outbound_log = WhatsAppLog(
            user_id=user["id"],
            user_phone=phone,
            direction="outbound",
            message_type="interactive" if request.action == "approve" else "text",
            content=whatsapp_message
        )
        await db.whatsapp_logs.insert_one(outbound_log.model_dump())
        
        if request.action == "approve":
            buttons = [
                {"id": "upload_bill", "title": "Upload Another Bill"},
                {"id": "my_points", "title": "My Points"}
            ]
            background_tasks.add_task(send_whatsapp_buttons, phone, whatsapp_message, buttons)
        else:
            buttons = [
                {"id": "upload_bill", "title": "Upload Bill"},
                {"id": "my_points", "title": "My Points"}
            ]
            background_tasks.add_task(send_whatsapp_buttons, phone, whatsapp_message, buttons)
    
    return {
        "success": True, 
        "bill_id": bill_id, 
        "action": request.action,
        "points_issued": update_data.get("points_issued", 0),
        "whatsapp_sent": request.send_whatsapp
    }

@api_router.post("/bills/{bill_id}/reprocess")
async def reprocess_bill(bill_id: str, background_tasks: BackgroundTasks,
                          wait: bool = False,
                          payload: dict = Depends(verify_jwt_token)):
    """Reprocess a pending bill after brand has been added to Fundle.

    Default (fast): queues the reprocess in a background task and returns
    immediately in <1s so Cloudflare/browser doesn't time out. The admin UI
    polls the bills list to see the updated status.

    Set `?wait=true` to run synchronously (legacy behaviour) — may take 20-60s.

    Feb 2026 hardening: top-level try/except so any Mongo hiccup / hang
    surfaces as a JSON body instead of a raw HTTP 500 (which the admin UI
    then renders as "Reprocess timed out").
    """
    try:
        # Feb 2026: only fetch the guard fields — pulling the full bill
        # (including multi-MB legacy inline image_url) here caused Atlas
        # MaxTimeMSExpired under production load and produced the admin
        # "Reprocess timed out" toast.
        bill = await db.bills.find_one(
            {"id": bill_id},
            {"_id": 0, "status": 1, "reprocessing_started_at": 1, "reprocessing_finished_at": 1},
        )
        if not bill:
            raise HTTPException(status_code=404, detail="Bill not found")
        if bill.get("status") not in ["pending_review", "rejected", "manual_review"]:
            raise HTTPException(status_code=400, detail="Only pending/rejected/manual-review bills can be reprocessed")
        # Feb 2026: reject double-clicks — if a reprocess is already in flight
        # for this bill (started but not finished), return 409 rather than
        # queue a duplicate background credit pipeline. Stale guard: after
        # 2 minutes we assume the previous run crashed and allow retry.
        started = bill.get("reprocessing_started_at")
        finished = bill.get("reprocessing_finished_at")
        if started and not finished:
            try:
                started_dt = datetime.fromisoformat(started.replace("Z", "+00:00"))
                age_seconds = (datetime.now(timezone.utc) - started_dt).total_seconds()
            except Exception:
                age_seconds = 0
            if age_seconds < 120:
                raise HTTPException(status_code=409, detail="A reprocess is already running for this bill. Please refresh in ~15s.")

        # Mark reprocessing_started_at so UI can show a spinner
        await db.bills.update_one(
            {"id": bill_id},
            {"$set": {"reprocessing_started_at": datetime.now(timezone.utc).isoformat(),
                      "reprocessing_by": payload.get("username") or "admin"}}
        )

        if not wait:
            background_tasks.add_task(_do_reprocess_bill_bg, bill_id)
            return {
                "success": True,
                "reprocessed": "queued",
                "bill_id": bill_id,
                "message": "Reprocess queued. Refresh the list in ~15 seconds to see the result."
            }

        # Legacy synchronous path
        return await _do_reprocess_bill_sync(bill_id, background_tasks)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"reprocess_bill failed for bill_id={bill_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Reprocess server error: {str(e)[:200]}"
        )


async def _do_reprocess_bill_bg(bill_id: str):
    """Background wrapper — runs the full sync reprocess pipeline off the
    request thread so the browser/Cloudflare fetch doesn't time out on slow
    Fundle calls. Always enables force_credit_on_fundle_reject because the
    admin explicitly clicked "Reprocess" — they want it credited."""
    from fastapi import BackgroundTasks as _BG
    bg = _BG()
    try:
        # Feb 2026: 25s max_time_ms buys Atlas headroom to transfer the
        # (potentially multi-MB legacy inline) image_url without tripping
        # MaxTimeMSExpired. Migrated `objstore:` bills return in <100ms.
        bill = await db.bills.find_one({"id": bill_id}, {"_id": 0}, max_time_ms=25000)
        if not bill:
            return
        await _reprocess_single_bill(
            bill, re_ocr=False, send_whatsapp_flag=True, background_tasks=bg,
            force_credit_on_fundle_reject=True
        )
    except Exception as e:
        logger.exception(f"Background reprocess failed for bill {bill_id}: {e}")
        await db.bills.update_one({"id": bill_id},
            {"$set": {"reprocessing_error": str(e)[:300],
                      "reprocessing_finished_at": datetime.now(timezone.utc).isoformat()}}
        )
        return
    await db.bills.update_one({"id": bill_id},
        {"$set": {"reprocessing_finished_at": datetime.now(timezone.utc).isoformat()}}
    )


async def _do_reprocess_bill_sync(bill_id: str, background_tasks: BackgroundTasks):
    """Original synchronous reprocess kept for `?wait=true`. Delegates to the
    shared `_reprocess_single_bill` helper (same pipeline as bulk reprocess) so
    behaviour stays consistent."""
    # Feb 2026: 25s max_time_ms — same rationale as _do_reprocess_bill_bg.
    bill = await db.bills.find_one({"id": bill_id}, {"_id": 0}, max_time_ms=25000)
    if not bill:
        raise HTTPException(status_code=404, detail="Bill not found")
    res = await _reprocess_single_bill(
        bill, re_ocr=False, send_whatsapp_flag=True, background_tasks=background_tasks,
        force_credit_on_fundle_reject=True
    )
    await db.bills.update_one({"id": bill_id},
        {"$set": {"reprocessing_finished_at": datetime.now(timezone.utc).isoformat()}}
    )
    if res.get("action") == "approved":
        return {"success": True, "points_earned": res.get("points", 0),
                "message": "Bill reprocessed successfully"}
    return {"success": False, "error": res.get("error") or "Reprocess failed",
            "status": res.get("status")}


@api_router.post("/bills/{bill_id}/reprocess-legacy")
async def reprocess_bill_legacy(bill_id: str, background_tasks: BackgroundTasks,
                                 payload: dict = Depends(verify_jwt_token)):
    """Full legacy reprocess implementation kept for reference / debugging.
    Not used by the admin UI anymore — see reprocess_bill above."""
    return await _reprocess_bill_full_legacy_impl(bill_id, background_tasks, payload)


async def _reprocess_bill_full_legacy_impl(bill_id: str, background_tasks: BackgroundTasks, payload: dict):
    """Full inline legacy implementation — kept isolated so the main endpoint
    can use the fast background path. If you need to debug specific Fundle
    calls step-by-step, POST /api/bills/{id}/reprocess-legacy to get the
    complete transaction detail."""
    
    # Get bill
    # Feb 2026: reprocess-legacy needs image_url for _resolve_bill_image_base64,
    # so keep full doc but cap max_time_ms=25000 for legacy multi-MB payloads.
    bill = await db.bills.find_one({"id": bill_id}, {"_id": 0}, max_time_ms=25000)
    if not bill:
        raise HTTPException(status_code=404, detail="Bill not found")
    
    if bill.get("status") not in ["pending_review", "rejected"]:
        raise HTTPException(status_code=400, detail="Only pending/rejected bills can be reprocessed")
    
    # Get user
    user = await db.users.find_one({"id": bill.get("user_id")})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    phone = bill.get("user_phone", user.get("phone"))
    mobile_10 = phone[2:] if phone.startswith("91") and len(phone) == 12 else phone
    
    # STEP 1: Check if user is registered in Fundle, if not, register them first
    logger.info(f"Reprocess bill {bill_id}: Checking if user {mobile_10} is registered in Fundle")
    points_result = await tagnpay_client.get_customer_points(mobile_10)
    
    if not points_result.get("success") or points_result.get("data") is None:
        # User not registered in Fundle - register them first
        logger.info(f"User {mobile_10} not registered in Fundle, registering now...")
        reg_result = await tagnpay_client.register_customer(
            mobile_number=mobile_10,
            name=user.get("name", "Customer"),
            pan_number="",
            source="WhatsApp-Reprocess"
        )
        logger.info(f"Fundle registration result for {mobile_10}: {reg_result}")
        
        if not reg_result.get("success"):
            # Registration failed - still try to proceed with bill processing
            logger.warning(f"Fundle registration failed for {mobile_10}: {reg_result.get('error')}")
        else:
            # Update user in our DB
            await db.users.update_one(
                {"id": user["id"]},
                {"$set": {"kyc_status": True, "fundle_registered": True}}
            )
    else:
        logger.info(f"User {mobile_10} already registered in Fundle")
    
    # STEP 2: Extract bill details
    store_name = bill.get("store_name", "Unknown")
    bill_no = bill.get("bill_no", "")
    bill_date = bill.get("bill_date", "")
    amount = float(bill.get("amount", 0))
    # Point 38: use the robust resolver so http:// URLs are downloaded and
    # re-encoded — the old "treat as raw base64 if no scheme prefix" branch
    # passed URLs into b64decode → "Incorrect padding" and reprocess failed.
    image_base64 = await _resolve_bill_image_base64(bill)

    # STEP 3: Call TagnPay earn-points API
    earn_result = await tagnpay_client.earn_points(
        mobile_number=mobile_10,
        bill_amount=amount,
        bill_number=bill_no,
        bill_date=bill_date,
        store_name=store_name,
        bill_image_base64=image_base64
    )
    
    logger.info(f"Reprocess TagnPay result for {bill_id}: {earn_result}")
    
    points_earned = 0
    if earn_result.get("success") and earn_result.get("data"):
        data = earn_result["data"]
        points_earned = data.get("earned_points", 0)
        message = data.get("message", "")
        
        if points_earned > 0:
            # ------- Campaign Engine: apply active multipliers/bonuses -------
            is_first = await db.bills.count_documents({"user_id": user["id"], "status": {"$in": ["auto_approved", "approved"]}}) == 0
            camp = await apply_campaign_bonus(
                bill_amount=amount,
                base_points=points_earned,
                store_name=store_name,
                is_first_bill=is_first,
            )
            campaign_bonus_points = camp["bonus_points"]
            applied_campaigns = camp["applied_campaigns"]
            points_earned = camp["final_points"]

            # Success! Update bill status
            bill_update = {
                "status": "approved",
                "points_issued": points_earned,
                "rejection_reason": None,
                "processed_at": datetime.now(timezone.utc).isoformat(),
                "processed_by": "admin_reprocess"
            }
            if campaign_bonus_points > 0:
                bill_update["campaign_bonus"] = campaign_bonus_points
                bill_update["applied_campaigns"] = applied_campaigns
            await db.bills.update_one({"id": bill_id}, {"$set": bill_update})

            # Update user points locally
            await db.users.update_one(
                {"id": user["id"]},
                {"$inc": {"balance_points": points_earned, "total_earned_points": points_earned}}
            )

            # Send success WhatsApp message in the background so the admin
            # response returns immediately (it doesn't have to wait on Karix).
            user_doc_after = await db.users.find_one({"id": user["id"]}, {"_id": 0, "balance_points": 1})
            total_balance = int((user_doc_after or {}).get("balance_points", 0))

            campaign_line = ""
            if campaign_bonus_points > 0 and applied_campaigns:
                names = ", ".join([c["name"] for c in applied_campaigns])
                campaign_line = f"\n Bonus: +{campaign_bonus_points} pts ({names})"
            success_msg = f""" *Points Credited!*

Your bill has been processed:
 Store: {store_name}
 Bill No: {bill_no}
 Amount: ₹{amount:.0f}

 Points Earned: {points_earned}{campaign_line}
 Total Balance: {total_balance}

Thank you for your patience! """

            buttons = [{"id": "upload_bill", "title": "Upload Bill"}]
            background_tasks.add_task(send_whatsapp_buttons, phone, success_msg, buttons)

            return {"success": True, "points_earned": points_earned, "message": "Bill reprocessed successfully"}
        else:
            # Still failing - check why
            error_msg = message or "Fundle returned 0 points"
            
            # Update bill with the error reason
            await db.bills.update_one(
                {"id": bill_id},
                {"$set": {"rejection_reason": error_msg}}
            )
            
            return {"success": False, "error": error_msg, "points_earned": 0}
    else:
        error_msg = earn_result.get("error", "Fundle API failed")
        
        # Check if it's a "brand not found" error
        if "brand" in error_msg.lower() or "not found" in error_msg.lower():
            # Send admin alert
            await send_admin_sms_alert(store_name, bill_no, amount, phone)
        
        # Update bill with the error reason
        await db.bills.update_one(
            {"id": bill_id},
            {"$set": {"rejection_reason": error_msg}}
        )
        
        return {"success": False, "error": error_msg, "points_earned": 0}


# ======================== BULK REPROCESS ========================

# Tier × category earn-rate table (single bill amount → rate %).
# Source of truth: tier journey table on the consumer app. The rate is decided
# by the bill amount range (NOT user's accumulated tier), matching how
# Fundle calculates earned_points for each individual transaction.
_EARN_RATES = [
    # (max_amount_inclusive, retail_pct, jewellery_pct)
    (10_000,    10.0,   5.0),
    (25_000,    15.0,   7.5),
    (75_000,    20.0,  10.0),
    (150_000,   25.0,  12.5),
    (300_000,   30.0,  15.0),
    (500_000,   32.5,  16.25),
    (float("inf"), 35.0, 17.5),
]
_JEWELLERY_CATEGORIES = {"jewellery", "electronics"}


async def _compute_auto_points(amount: float, store_name: Optional[str]) -> Dict[str, Any]:
    """Compute force-credit points using the brand category + bill amount range.

    Returns {points, rate_pct, category, range_label, brand_found}.
    Falls back to retail rate if the brand is unknown.
    """
    amt = float(amount or 0)
    if amt <= 0:
        return {"points": 0, "rate_pct": 0, "category": "Unknown",
                "range_label": "n/a", "brand_found": False}

    brand_category = None
    brand_found = False
    if store_name:
        # Case-insensitive partial match against brand_name
        norm = store_name.strip().lower()
        brand = await db.brands.find_one(
            {"$or": [
                {"brand_name": {"$regex": f"^{re.escape(store_name)}$", "$options": "i"}},
                {"brand_name": {"$regex": re.escape(norm), "$options": "i"}}
            ]},
            {"_id": 0, "category": 1, "brand_name": 1}
        )
        if brand:
            brand_category = (brand.get("category") or "").strip()
            brand_found = True

    is_jewellery = (brand_category or "").lower() in _JEWELLERY_CATEGORIES
    rate_key = "jewellery" if is_jewellery else "retail"

    rate_pct = 10.0
    range_label = "≤ 10,000"
    for idx, (ceiling, retail_pct, jewellery_pct) in enumerate(_EARN_RATES):
        if amt <= ceiling:
            rate_pct = jewellery_pct if is_jewellery else retail_pct
            # Build a nice label
            prev = 0 if idx == 0 else _EARN_RATES[idx - 1][0]
            if ceiling == float("inf"):
                range_label = f"> {int(prev):,}"
            else:
                range_label = f"{int(prev)+1 if prev>0 else 0:,} - {int(ceiling):,}"
            break

    points = int(round(amt * rate_pct / 100.0))
    return {
        "points": max(1, points),  # never credit zero on a non-zero bill
        "rate_pct": rate_pct,
        "category": brand_category or "Unknown",
        "range_label": range_label,
        "brand_found": brand_found,
        "rate_basis": rate_key,
    }


class BulkReprocessRequest(BaseModel):
    """Request body for bulk-reprocessing failed/stuck bills.

    Use `from_date`/`to_date` (YYYY-MM-DD) to scope to a window.
    `statuses` defaults to manual_review + pending_review.
    `re_ocr=True` re-runs OCR on the stored image before re-applying rules
    (use this for bills that were broken by an outage like the missing
    EMERGENT_LLM_KEY on prod).
    """
    from_date: Optional[str] = None
    to_date: Optional[str] = None
    statuses: Optional[List[str]] = None
    re_ocr: bool = True
    dry_run: bool = False
    limit: int = 200
    send_whatsapp: bool = True
    # When True, skips Fundle earn_points call and credits locally with
    # the OCR-extracted amount * `force_credit_percent` / 100. Use this only
    # after explicit admin approval (e.g. brand still being added to Fundle).
    force_credit: bool = False
    force_credit_percent: float = 1.0  # 1% of bill amount by default
    # When True (Point 10): if Fundle rejects (brand-mismatch / 0 points),
    # auto-fall-back to LOCAL force-credit via _compute_auto_points. This is
    # the pragmatic path for months of bulk-stuck bills that Fundle refuses.
    force_credit_on_fundle_reject: bool = False


async def _reprocess_single_bill(bill: dict, *, re_ocr: bool, send_whatsapp_flag: bool,
                                 background_tasks: BackgroundTasks,
                                 force_credit: bool = False,
                                 force_credit_percent: float = 1.0,
                                 force_credit_on_fundle_reject: bool = False) -> dict:
    """Reprocess one bill EXACTLY the same way a fresh WhatsApp upload would:
       1. (Optional) re-OCR the stored image
       2. Ensure customer is registered with Fundle
       3. Apply 15-day age rule
       4. Send to Fundle earn_points with the SAME payload as WhatsApp
          (mobile, amount, bill_no, bill_date, store_name, AND the bill image)
       Returns {bill_id, action, status, points, error}.
    """
    bill_id = bill.get("id")
    user = await db.users.find_one({"id": bill.get("user_id")})
    if not user:
        # Fallback: match by phone. Some legacy stub bills stored a user_id that
        # got drift after phone normalization changes — retry via user_phone so
        # we don't silently skip an otherwise-recoverable bill.
        phone_lookup = (bill.get("user_phone") or "").strip()
        if phone_lookup:
            candidates = [phone_lookup]
            if phone_lookup.startswith("91") and len(phone_lookup) == 12:
                candidates.append(phone_lookup[2:])
            elif len(phone_lookup) == 10:
                candidates.append(f"91{phone_lookup}")
            user = await db.users.find_one({"phone": {"$in": candidates}})
    if not user:
        return {"bill_id": bill_id, "action": "skipped", "status": bill.get("status"),
                "points": 0, "error": "User not found"}

    phone = bill.get("user_phone") or user.get("phone") or ""
    mobile_10 = phone[2:] if phone.startswith("91") and len(phone) == 12 else phone[-10:]

    store_name = bill.get("store_name") or "Unknown"
    bill_no = bill.get("bill_no") or ""
    bill_date = bill.get("bill_date") or ""
    amount = float(bill.get("amount") or 0)

    update_payload = {
        "reprocessed_at": datetime.now(timezone.utc).isoformat(),
        "reprocessed_by": "admin_bulk"
    }

    # ----- Fetch the stored image ONCE — used for both OCR + Fundle call -----
    image_url = bill.get("image_url") or ""
    image_base64 = None
    image_download_error: Optional[str] = None
    if image_url.startswith("objstore:"):
        # Feb 2026 (session-20): migrated bills store image bytes in Emergent
        # Object Storage. Without this branch reprocess sent no image to
        # Fundle and got "bill_file missing" → force-credit fallback got
        # correctly suppressed, but the reprocess never succeeded either.
        try:
            from storage import aresolve_objstore_url
            fetched = await aresolve_objstore_url(image_url)
            if fetched:
                data, _ctype = fetched
                image_base64 = base64.b64encode(data).decode()
                logger.info(f"Reprocess: fetched objstore image for {bill_id} ({len(image_base64)} chars)")
            else:
                image_download_error = "Object storage returned no data"
        except Exception as e:
            image_download_error = f"Object storage read error: {str(e)[:120]}"
            logger.warning(f"Reprocess objstore fetch failed for {bill_id}: {e}")
    elif image_url.startswith("data:"):
        try:
            image_base64 = image_url.split(",", 1)[1]
        except Exception:
            image_base64 = None
    elif image_url.startswith("base64:"):
        image_base64 = image_url[7:]
    elif image_url.startswith("http"):
        # Karix media URLs require Bearer auth. Previously we sent no headers
        # → 401/403 → OCR skipped → bill stayed "manual_review" forever (Point 19).
        try:
            async with httpx.AsyncClient(timeout=25.0) as cx:
                headers = {}
                if KARIX_API_KEY:
                    headers = {
                        "Authentication": f"Bearer {KARIX_API_KEY}",
                        "Authorization": f"Bearer {KARIX_API_KEY}",
                    }
                r = await cx.get(image_url, headers=headers)
                if r.status_code != 200 and headers:
                    # Fallback without auth (some CDN URLs work anonymously)
                    r = await cx.get(image_url)
                if r.status_code == 200 and r.content:
                    image_base64 = base64.b64encode(r.content).decode()
                    logger.info(f"Bulk reprocess: downloaded image for {bill_id} ({len(image_base64)} chars, HTTP {r.status_code})")
                    # PERSIST the base64 so future reprocesses skip the network call
                    # and the image survives even if Karix expires the URL.
                    update_payload["image_url"] = f"data:image/jpeg;base64,{image_base64}"
                else:
                    image_download_error = f"HTTP {r.status_code}"
                    logger.warning(f"Bulk reprocess image download failed for {bill_id}: {image_download_error}")
        except Exception as e:
            image_download_error = str(e)[:120]
            logger.warning(f"Bulk reprocess image download failed for {bill_id}: {e}")

    # ----- Auto-force re-OCR for bills that never had data extracted -----
    # Failed WhatsApp bills (rejection_reason starts with "WhatsApp bill processing failed")
    # have no prior OCR data at all — force re-OCR regardless of the caller flag so
    # Bulk Reprocess actually attempts to recover them instead of instantly skipping.
    prior_reason = (bill.get("rejection_reason") or "")
    is_whatsapp_failed = (
        prior_reason.lower().startswith("whatsapp bill processing failed")
        or prior_reason.lower().startswith("ocr could not extract")
    )
    effective_re_ocr = re_ocr or is_whatsapp_failed

    # ----- Step 1: Optionally re-run OCR -----
    if effective_re_ocr and image_base64:
        ocr_result = await analyze_bill_image(image_base64)
        if ocr_result.get("success") and ocr_result.get("data"):
            d = ocr_result["data"]
            store_name = d.get("store_name") or store_name
            bill_no = d.get("bill_no") or bill_no
            bill_date = d.get("bill_date") or bill_date
            try:
                new_amount = float(d.get("amount") or 0)
                if new_amount > 0:
                    amount = new_amount
            except (TypeError, ValueError):
                pass
            update_payload.update({
                "store_name": store_name,
                "bill_no": bill_no,
                "bill_date": bill_date,
                "amount": amount,
                "ocr_confidence": d.get("confidence_score", bill.get("ocr_confidence", 0)),
                "ocr_raw_data": d,
            })
        else:
            logger.info(f"Bulk reprocess: OCR still failing for {bill_id}: {ocr_result.get('error')}")
    elif effective_re_ocr and not image_base64:
        logger.info(f"Bulk reprocess: no image available for {bill_id}, skipping re-OCR")

    # ----- Step 2: Ensure customer is registered in Fundle -----
    try:
        points_result = await tagnpay_client.get_customer_points(mobile_10)
    except Exception as e:
        points_result = {"success": False, "error": str(e)}
    if not points_result.get("success") or points_result.get("data") is None:
        try:
            await tagnpay_client.register_customer(
                mobile_number=mobile_10,
                name=user.get("name", "Customer"),
                pan_number="",
                source="WhatsApp-BulkReprocess"
            )
        except Exception as e:
            logger.warning(f"Bulk reprocess: Fundle register failed for {mobile_10}: {e}")

    # ----- Step 3: Apply bill-age rule (15 days) -----
    if bill_date:
        try:
            bd = datetime.strptime(bill_date, "%Y-%m-%d")
            days_old = (datetime.now() - bd).days
            if days_old > 15:
                update_payload.update({
                    "status": "rejected",
                    "rejection_reason": f"Bill is {days_old} days old (limit: 15 days)"
                })
                await db.bills.update_one({"id": bill_id}, {"$set": update_payload})
                # Point 25: alert mall-ops when reprocess rejects a bill
                asyncio.create_task(maybe_alert_admin(bill_id, "rejected",
                                                     f"Bill is {days_old} days old (limit: 15 days)"))
                return {"bill_id": bill_id, "action": "rejected",
                        "status": "rejected", "points": 0,
                        "error": f"Bill {days_old} days old"}
        except Exception:
            pass

    # ----- Step 4: Send to Fundle earn_points (SAME payload as WhatsApp flow) -----
    # For failed WhatsApp bills where OCR extracted the amount but not a bill_no,
    # auto-generate a synthetic bill_no so Fundle can credit points instead of
    # bouncing the bill back to manual_review indefinitely.
    if amount > 0 and not bill_no:
        bill_no = f"WA-{(bill_id or '')[:8].upper()}"
        update_payload["bill_no"] = bill_no
        update_payload["synthetic_bill_no"] = True
        logger.info(f"Bulk reprocess: generated synthetic bill_no {bill_no} for {bill_id}")

    if amount <= 0 or not bill_no:
        # Distinguish "no image at all" from "OCR failed on image" so admins can
        # tell WhatsApp-failed bills apart from genuinely unreadable ones.
        if not image_base64:
            reason = (
                f"Cannot reprocess: image not available"
                + (f" ({image_download_error})" if image_download_error else "")
            )
            action = "no_image"
        else:
            reason = "OCR could not extract amount/bill_no; manual review required"
            action = "manual_review"
        update_payload["status"] = "manual_review"
        update_payload["rejection_reason"] = reason
        await db.bills.update_one({"id": bill_id}, {"$set": update_payload})
        return {"bill_id": bill_id, "action": action,
                "status": "manual_review", "points": 0,
                "error": reason}

    # ---- force_credit branch: SKIP Fundle, credit locally using tier × amount rate ----
    if force_credit:
        auto = await _compute_auto_points(amount, store_name)
        fc_points = int(auto.get("points") or 0)
        if fc_points <= 0:
            update_payload["status"] = "manual_review"
            update_payload["rejection_reason"] = "Force-credit yielded 0 points (invalid amount)"
            await db.bills.update_one({"id": bill_id}, {"$set": update_payload})
            return {"bill_id": bill_id, "action": "kept_pending",
                    "status": "manual_review", "points": 0,
                    "error": "Force-credit computed 0 points"}
        update_payload.update({
            "status": "approved",
            "points_issued": fc_points,
            "rejection_reason": None,
            "processed_at": datetime.now(timezone.utc).isoformat(),
            "processed_by": "admin_force_credit",
            "force_credited": True,
            "force_credit_rate_pct": auto.get("rate_pct"),
            "force_credit_category": auto.get("category"),
        })
        await db.bills.update_one({"id": bill_id}, {"$set": update_payload})
        await db.users.update_one(
            {"id": user["id"]},
            {"$inc": {"balance_points": fc_points, "total_earned_points": fc_points}}
        )
        # Point 44 (iter-76): explicit force_credit path was missing both the
        # staff-incentive sync AND the parking-coupon hook — parking-QR users
        # whose first bill was admin Force-Credited or auto-force-credited
        # after an edit-brand were left with parking_coupon_pending=true.
        try:
            await _sync_staff_incentive_for_bill(bill_id, "approved", phone or "")
        except Exception as _e:
            logger.warning(f"staff-sync (explicit force-credit) failed: {_e}")
        try:
            await _maybe_issue_pending_parking_coupon(phone)
        except Exception as _pe:
            logger.warning(f"parking coupon hook (explicit force-credit) failed for {bill_id}: {_pe}")
        if send_whatsapp_flag and phone:
            try:
                total_balance_doc = await db.users.find_one({"id": user["id"]}, {"_id": 0, "balance_points": 1})
                total_balance = int((total_balance_doc or {}).get("balance_points", 0))
                msg = (f"Good news! Your bill has been processed.\n\n"
                       f"Store: {store_name}\nBill No: {bill_no}\nAmount: \u20b9{amount:.0f}\n"
                       f"Points Earned: {fc_points}\nTotal Balance: {total_balance}\n\n"
                       f"Thank you for your patience.")
                background_tasks.add_task(send_whatsapp_text, phone, msg)
            except Exception as e:
                logger.warning(f"Force-credit WhatsApp send failed: {e}")
        return {"bill_id": bill_id, "action": "approved",
                "status": "approved", "points": fc_points, "error": None}

    # Point 49-a (Sep 2026): Fundle sometimes rejects on punctuation/case
    # quirks in the brand name (e.g. "sagar ratna" vs "Sagar Ratna"). Try
    # the admin-corrected name first, then Title Case, then UPPER — stop at
    # the first accept. This makes Fix Brand succeed on the first admin
    # click for the most common case-only mismatch.
    def _brand_variants(name: str):
        seen = set()
        for v in (name, name.strip().title(), name.strip().upper()):
            key = (v or "").strip()
            if key and key not in seen:
                seen.add(key); yield key
    earn_result = {"success": False, "error": "no_attempt"}
    tried_variants = []
    for variant in _brand_variants(store_name or ""):
        tried_variants.append(variant)
        try:
            earn_result = await tagnpay_client.earn_points(
                mobile_number=mobile_10,
                bill_amount=amount,
                bill_number=bill_no,
                bill_date=bill_date or datetime.now().strftime("%Y-%m-%d"),
                store_name=variant,
                bill_image_base64=image_base64  # <-- send image, exactly like WhatsApp upload
            )
        except Exception as e:
            earn_result = {"success": False, "error": str(e)}
        pts_probe = int(((earn_result.get("data") or {}).get("earned_points") or 0)) if earn_result.get("success") else 0
        if pts_probe > 0:
            if variant != (store_name or "").strip():
                logger.info(f"Point 49-a: bill {bill_id} accepted by Fundle after brand variant retry '{variant}' (original='{store_name}')")
                # Persist the accepted variant so future reads show the exact name Fundle knows.
                update_payload["store_name"] = variant
                store_name = variant
            break
        else:
            err_probe = str(earn_result.get("error") or (earn_result.get("data") or {}).get("message") or "").lower()
            if not (("brand" in err_probe) or ("match" in err_probe) or ("not found" in err_probe) or ("0 points" in err_probe)):
                # Non-brand error (mobile not registered, image missing, etc.) — variants won't help.
                break

    points_earned = 0
    if earn_result.get("success") and earn_result.get("data"):
        points_earned = int(earn_result["data"].get("earned_points", 0) or 0)

    if points_earned > 0:
        # ------- Campaign Engine: apply active multipliers/bonuses -------
        is_first = await db.bills.count_documents({"user_id": user["id"], "status": {"$in": ["auto_approved", "approved"]}}) == 0
        camp = await apply_campaign_bonus(
            bill_amount=amount,
            base_points=points_earned,
            store_name=store_name,
            is_first_bill=is_first,
        )
        campaign_bonus_points = camp["bonus_points"]
        applied_campaigns = camp["applied_campaigns"]
        points_earned = camp["final_points"]

        update_payload.update({
            "status": "approved",
            "points_issued": points_earned,
            "rejection_reason": None,
            "processed_at": datetime.now(timezone.utc).isoformat(),
            "processed_by": "admin_bulk_reprocess"
        })
        if campaign_bonus_points > 0:
            update_payload["campaign_bonus"] = campaign_bonus_points
            update_payload["applied_campaigns"] = applied_campaigns
        await db.bills.update_one({"id": bill_id}, {"$set": update_payload})

        await db.users.update_one(
            {"id": user["id"]},
            {"$inc": {"balance_points": points_earned, "total_earned_points": points_earned}}
        )

        # Staff Incentive Sync — approve triggers registration-incentive activation
        try:
            await _sync_staff_incentive_for_bill(bill_id, "approved", phone or "")
        except Exception as _e:
            logger.warning(f"staff-sync (reprocess approved) failed: {_e}")

        # Point 44 (Feb 2026): _reprocess_single_bill is the choke point every
        # reprocess (admin queued + bulk + edit-brand) hits — issuing the
        # deferred parking coupon here covers all approved-via-reprocess paths.
        try:
            await _maybe_issue_pending_parking_coupon(phone)
        except Exception as _pe:
            logger.warning(f"parking coupon hook (reprocess) failed for {bill_id}: {_pe}")

        if send_whatsapp_flag and phone:
            try:
                total_balance_doc = await db.users.find_one({"id": user["id"]}, {"_id": 0, "balance_points": 1})
                total_balance = int((total_balance_doc or {}).get("balance_points", 0))
                campaign_line = ""
                if campaign_bonus_points > 0 and applied_campaigns:
                    names = ", ".join([c["name"] for c in applied_campaigns])
                    campaign_line = f"\nBonus: +{campaign_bonus_points} pts ({names})"
                msg = (f"Good news! Your bill has been processed.\n\n"
                       f"Store: {store_name}\nBill No: {bill_no}\nAmount: \u20b9{amount:.0f}\n"
                       f"Points Earned: {points_earned}{campaign_line}\nTotal Balance: {total_balance}\n\n"
                       f"Thank you for your patience.")
                background_tasks.add_task(send_whatsapp_text, phone, msg)
            except Exception as e:
                logger.warning(f"Bulk reprocess WhatsApp send failed: {e}")

        return {"bill_id": bill_id, "action": "approved",
                "status": "approved", "points": points_earned, "error": None}

    # Fundle returned 0 or failed — leave/update reason
    err = earn_result.get("error") or (earn_result.get("data") or {}).get("message") or "Fundle returned 0 points"
    update_payload["rejection_reason"] = err[:300]

    # ------- Point 10 / 12: Fallback to force-credit locally if Fundle rejected -------
    err_low = (err or "").lower()
    fundle_brand_reject = ("brand" in err_low) or ("match" in err_low) or ("0 points" in err_low) or ("not found" in err_low)
    if force_credit_on_fundle_reject and fundle_brand_reject:
        auto = await _compute_auto_points(amount, store_name)
        fc_points = int(auto.get("points") or 0)
        if fc_points > 0:
            update_payload.update({
                "status": "approved",
                "points_issued": fc_points,
                "rejection_reason": None,
                "processed_at": datetime.now(timezone.utc).isoformat(),
                "processed_by": update_payload.get("processed_by") or "auto_force_credit_on_reject",
                "force_credited": True,
                "force_credit_rate_pct": auto.get("rate_pct"),
                "force_credit_category": auto.get("category"),
                "fundle_original_error": err[:200],
            })
            await db.bills.update_one({"id": bill_id}, {"$set": update_payload})
            await db.users.update_one(
                {"id": user["id"]},
                {"$inc": {"balance_points": fc_points, "total_earned_points": fc_points}}
            )
            # Staff Incentive Sync — force-credit approval activates any pending registration incentive
            try:
                await _sync_staff_incentive_for_bill(bill_id, "approved", phone or "")
            except Exception as _e:
                logger.warning(f"staff-sync (reprocess force-credit) failed: {_e}")
            # Point 44 (Feb 2026): force-credit is also a valid "first verified bill".
            try:
                await _maybe_issue_pending_parking_coupon(phone)
            except Exception as _pe:
                logger.warning(f"parking coupon hook (reprocess force-credit) failed for {bill_id}: {_pe}")
            if send_whatsapp_flag and phone and background_tasks is not None:
                try:
                    total_balance_doc = await db.users.find_one({"id": user["id"]}, {"_id": 0, "balance_points": 1})
                    total_balance = int((total_balance_doc or {}).get("balance_points", 0))
                    msg = (f"Good news! Your bill has been processed.\n\n"
                           f"Store: {store_name}\nBill No: {bill_no}\nAmount: \u20b9{amount:.0f}\n"
                           f"Points Earned: {fc_points}\nTotal Balance: {total_balance}\n\n"
                           f"Thank you for your patience.")
                    background_tasks.add_task(send_whatsapp_text, phone, msg)
                except Exception as e:
                    logger.warning(f"Auto force-credit WhatsApp send failed: {e}")
            return {"bill_id": bill_id, "action": "approved",
                    "status": "approved", "points": fc_points, "error": None,
                    "fallback": "force_credit"}

    # Keep status as it was unless it's a brand-not-found which we keep pending
    await db.bills.update_one({"id": bill_id}, {"$set": update_payload})
    return {"bill_id": bill_id, "action": "kept_pending",
            "status": bill.get("status"), "points": 0, "error": err[:200]}


@api_router.post("/admin/bills/bulk-reprocess")
async def bulk_reprocess_bills(request: BulkReprocessRequest,
                                background_tasks: BackgroundTasks,
                                payload: dict = Depends(verify_jwt_token)):
    """Bulk reprocess failed/stuck bills in a date window.

    Returns a per-bill summary. Use `dry_run=True` to preview the candidate
    list without mutating anything.
    """
    # Build query
    statuses = request.statuses or ["manual_review", "pending_review"]
    q: Dict[str, Any] = {"status": {"$in": statuses}}

    # Date filter on `created_at` (ISO string in DB)
    if request.from_date or request.to_date:
        date_q: Dict[str, Any] = {}
        if request.from_date:
            date_q["$gte"] = request.from_date  # ISO date prefix-compare works
        if request.to_date:
            # inclusive end-of-day
            date_q["$lte"] = request.to_date + "T23:59:59.999Z"
        q["created_at"] = date_q

    cursor = db.bills.find(q, {"_id": 0}).sort("created_at", 1).limit(max(1, min(request.limit, 500)))
    bills = await cursor.to_list(length=None)

    if request.dry_run:
        return {
            "dry_run": True,
            "candidates": len(bills),
            "bills": [{
                "id": b.get("id"),
                "status": b.get("status"),
                "user_phone": b.get("user_phone"),
                "store_name": b.get("store_name"),
                "amount": b.get("amount"),
                "created_at": b.get("created_at"),
                "has_image": bool(b.get("image_url")),
            } for b in bills]
        }

    # Real run: start a background job and return job_id immediately so the
    # admin UI doesn't get killed by Cloudflare's ~100s edge timeout. The UI
    # then polls /bulk-reprocess/{job_id}/status for live progress.
    job_id = str(uuid.uuid4())
    job_doc = {
        "id": job_id,
        "status": "running",
        "total": len(bills),
        "processed": 0,
        "summary": {"approved": 0, "rejected": 0, "manual_review": 0, "kept_pending": 0, "skipped": 0, "no_image": 0},
        "total_points_credited": 0,
        "results": [],
        "started_at": datetime.now(timezone.utc).isoformat(),
        "finished_at": None,
        "started_by": payload.get("username") or "admin",
        "options": {"re_ocr": request.re_ocr, "send_whatsapp": request.send_whatsapp,
                    "from_date": request.from_date, "to_date": request.to_date},
    }
    await db.bulk_reprocess_jobs.insert_one(job_doc)

    # asyncio.create_task is safer than FastAPI's BackgroundTasks here because
    # BackgroundTasks runs *after* the response is sent but is still bound to
    # the request lifecycle on some setups. We want a fully detached task.
    asyncio.create_task(_run_bulk_reprocess_job(
        job_id, bills, request.re_ocr, request.send_whatsapp,
        request.force_credit, request.force_credit_percent,
        request.force_credit_on_fundle_reject
    ))

    return {
        "dry_run": False,
        "job_id": job_id,
        "status": "running",
        "total": len(bills),
        "message": "Started in background. Poll /bulk-reprocess/{job_id}/status for progress."
    }


async def _run_bulk_reprocess_job(job_id: str, bills: List[dict],
                                   re_ocr: bool, send_whatsapp_flag: bool,
                                   force_credit: bool = False,
                                   force_credit_percent: float = 1.0,
                                   force_credit_on_fundle_reject: bool = False):
    """Background worker: processes each bill, persists progress to DB after every
    iteration so the UI can poll for live updates."""
    from fastapi import BackgroundTasks as _BG
    bg = _BG()  # fake container so _reprocess_single_bill can queue WA messages
    summary = {"approved": 0, "rejected": 0, "manual_review": 0, "kept_pending": 0, "skipped": 0, "no_image": 0}
    total_points = 0
    results: List[dict] = []
    for idx, b in enumerate(bills, 1):
        try:
            res = await _reprocess_single_bill(
                b, re_ocr=re_ocr, send_whatsapp_flag=send_whatsapp_flag, background_tasks=bg,
                force_credit=force_credit, force_credit_percent=force_credit_percent,
                force_credit_on_fundle_reject=force_credit_on_fundle_reject
            )
        except Exception as e:
            logger.exception(f"Bulk reprocess error on bill {b.get('id')}")
            res = {"bill_id": b.get("id"), "action": "skipped",
                   "status": b.get("status"), "points": 0, "error": str(e)[:200]}
        results.append(res)
        action = res.get("action", "skipped")
        summary[action] = summary.get(action, 0) + 1
        total_points += int(res.get("points") or 0)
        # Persist progress (so the UI can poll)
        await db.bulk_reprocess_jobs.update_one(
            {"id": job_id},
            {"$set": {
                "processed": idx,
                "summary": summary,
                "total_points_credited": total_points,
            }}
        )
    # Mark complete + store final results
    await db.bulk_reprocess_jobs.update_one(
        {"id": job_id},
        {"$set": {
            "status": "completed",
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "results": results[-200:],  # cap to last 200 to keep doc small
        }}
    )
    # Run any queued WhatsApp tasks (BackgroundTasks normally runs them after response;
    # since we're detached, run them inline).
    try:
        for t in bg.tasks:
            try:
                await t.func(*t.args, **t.kwargs)
            except Exception as e:
                logger.warning(f"Bulk reprocess WA task failed: {e}")
    except Exception:
        pass


@api_router.get("/admin/bills/bulk-reprocess/{job_id}/status")
async def bulk_reprocess_status(job_id: str, payload: dict = Depends(verify_jwt_token)):
    """Poll endpoint: returns the live state of a bulk-reprocess job."""
    job = await db.bulk_reprocess_jobs.find_one({"id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@api_router.post("/admin/bills/migrate-images-to-objstore")
async def migrate_bill_images_to_objstore(
    background_tasks: BackgroundTasks,
    limit: int = 500,
    payload: dict = Depends(verify_jwt_token),
):
    """Session-20 (Feb 2026): bulk-migrate inline base64 bill images out of
    the Mongo `bills` doc into Emergent Object Storage. Fire-and-forget —
    returns immediately with the number of docs queued.

    Only migrates bills whose `image_url` starts with `data:image/` or
    `base64:` AND whose stored length is >50KB (skips sub-5KB placeholders
    that would otherwise be re-queued forever). Safe to call repeatedly;
    already-migrated bills are naturally skipped by the prefix filter.
    """
    if payload.get("role") not in ("admin", "super_admin"):
        raise HTTPException(status_code=403, detail="Admin role required")

    q = {
        "image_url": {"$regex": "^(data:image/|base64:)"},
        # Only queue bills with fat image_urls — sub-5KB placeholders are
        # never migrated so the worker doesn't churn on them and the
        # queued count can drain to 0.
        "$expr": {"$gt": [{"$strLenCP": "$image_url"}, 50000]},
    }
    projection = {"_id": 0, "id": 1}
    cursor = db.bills.find(q, projection).limit(max(1, min(limit, 5000)))
    bill_ids = [b["id"] async for b in cursor if b.get("id")]

    for bill_id in bill_ids:
        background_tasks.add_task(_migrate_one_bill_by_id, bill_id)

    return {
        "success": True,
        "queued": len(bill_ids),
        "message": f"Queued {len(bill_ids)} bill(s) for background migration to object storage. Re-run this endpoint to migrate the next batch."
    }


async def _migrate_one_bill_by_id(bill_id: str):
    """Fetch the bill's inline image_url and delegate to
    _migrate_bill_image_to_objstore. Runs in the FastAPI background pool."""
    try:
        b = await db.bills.find_one({"id": bill_id}, {"_id": 0, "image_url": 1})
        if not b:
            return
        raw = b.get("image_url") or ""
        if not isinstance(raw, str):
            return
        if raw.startswith("data:image/"):
            data_url = raw
        elif raw.startswith("base64:"):
            data_url = f"data:image/jpeg;base64,{raw[7:]}"
        else:
            return
        await _migrate_bill_image_to_objstore(bill_id, data_url)
    except Exception as e:
        logger.warning(f"_migrate_one_bill_by_id({bill_id}) failed: {e}")




# ---------------- Point 25: Admin alert config ----------------
class AdminAlertPhonesUpdate(BaseModel):
    phones: List[str]


@api_router.get("/admin/alerts/config")
async def get_admin_alert_config(payload: dict = Depends(verify_jwt_token)):
    """Return the mall-ops phone numbers that receive bill-status alerts."""
    doc = await db.settings.find_one({"key": "admin_alert_phones"}, {"_id": 0})
    phones = (doc or {}).get("phones") if doc else None
    if not phones:
        phones = ADMIN_ALERT_PHONES  # fall back to env default
    return {"phones": phones, "default_from_env": ADMIN_ALERT_PHONES}


@api_router.put("/admin/alerts/config")
async def update_admin_alert_config(body: AdminAlertPhonesUpdate,
                                     payload: dict = Depends(verify_jwt_token)):
    """Set the mall-ops phone numbers. Overrides ADMIN_ALERT_PHONES env at runtime."""
    global ADMIN_ALERT_PHONES
    phones = [p.strip() for p in (body.phones or []) if p and p.strip()]
    await db.settings.update_one(
        {"key": "admin_alert_phones"},
        {"$set": {"key": "admin_alert_phones", "phones": phones,
                  "updated_at": datetime.now(timezone.utc).isoformat(),
                  "updated_by": payload.get("username")}},
        upsert=True
    )
    ADMIN_ALERT_PHONES = phones
    logger.info(f"Admin alert phones updated by {payload.get('username')}: {phones}")
    return {"phones": phones, "success": True}


@api_router.post("/admin/alerts/test")
async def send_test_admin_alert(payload: dict = Depends(verify_jwt_token)):
    """Point 36: fire a diagnostic bill alert to the configured phones and
    return the exact Karix response per phone (status, mid, error). This
    surfaces the WhatsApp Business API 24-hour session limitation so admin
    can tell 'Karix accepted' apart from 'delivered'."""
    fake_bill = {
        "id": "TEST-" + str(uuid.uuid4())[:8],
        "user_phone": "919999999999",
        "store_name": "Test Store",
        "amount": 999,
        "bill_no": "TEST-123",
        "rejection_reason": "This is a TEST alert triggered from admin panel"
    }
    # Compose the same message send_admin_bill_alert would send, but capture per-phone results here.
    msg = (
        "CP67 Bill Alert - MANUAL REVIEW (TEST)\n\n"
        f"Customer: {fake_bill['user_phone']}\n"
        f"Store: {fake_bill['store_name']}\n"
        f"Amount: \u20b9{fake_bill['amount']}\n"
        f"Bill No: {fake_bill['bill_no']}\n"
        f"Bill ID: {fake_bill['id'][:8]}\n"
        f"Reason: {fake_bill['rejection_reason']}\n"
    )
    sms_msg = f"CP67 Bill MANUAL REVIEW (TEST): cust {fake_bill['user_phone']}, {fake_bill['store_name']}, Amt \u20b9{fake_bill['amount']}"
    results = []
    for admin_phone in ADMIN_ALERT_PHONES:
        to = _normalize_alert_phone(admin_phone)
        if not to:
            results.append({"phone": admin_phone, "success": False, "error": "invalid phone"})
            continue
        wa = await send_whatsapp_text_diag(to, msg)
        sms = await send_sms_text(to[-10:] if len(to) >= 10 else to, sms_msg)
        results.append({
            "phone_input": admin_phone,
            "phone_sent_to": to,
            "whatsapp": wa,
            "sms": sms,
            "success": bool(wa.get("success") or sms.get("success")),
        })
    accepted = sum(1 for r in results if r.get("success"))
    return {
        "success": accepted > 0,
        "accepted": accepted,
        "total": len(results),
        "phones": ADMIN_ALERT_PHONES,
        "results": results,
        "hint": "Alert fires via BOTH WhatsApp and SMS. If WhatsApp shows success:true but the phone doesn't receive it, the WhatsApp 24-hour session window is closed — SMS should still deliver.",
    }


@api_router.post("/admin/whatsapp/send-test")
async def send_test_whatsapp(request: Request, payload: dict = Depends(verify_jwt_token)):
    """Point 36: lightweight endpoint that sends a plain-text WhatsApp message
    to an arbitrary number (defaults to caller-supplied phone) and returns the
    full Karix response. Useful when the ops team wants to sanity-check a
    specific number without touching bill-alert config."""
    body = await request.json()
    to = body.get("phone") or ""
    message = (body.get("message") or "Test message from CP67 Mall admin panel — if you receive this, WhatsApp delivery is working.").strip()
    to_norm = _normalize_alert_phone(to)
    if not to_norm:
        raise HTTPException(status_code=400, detail="phone required (10-digit or 12-digit E.164)")
    r = await send_whatsapp_text_diag(to_norm, message)
    r["phone_input"] = to
    r["phone_sent_to"] = to_norm
    r["hint"] = "If Karix returns 200 but the phone doesn't receive the message, the WhatsApp Business 24-hour session window has expired — send a template message or have the recipient message your business number first."
    return r


@api_router.post("/admin/otp/send-test")
async def send_test_otp(request: Request, payload: dict = Depends(verify_jwt_token)):
    """Point 11: dispatch a real OTP through the configured OTP_CHANNEL and return
    per-channel diagnostics so admin can verify OTP delivery end-to-end without
    inventing a fake customer number. Requires a 10-digit target phone."""
    body = await request.json()
    to = (body.get("phone") or "").strip()
    digits = "".join(ch for ch in to if ch.isdigit())
    if len(digits) < 10:
        raise HTTPException(status_code=400, detail="phone required (10-digit)")
    phone_10 = digits[-10:]
    otp = str(random.randint(100000, 999999))
    await store_otp(phone_10, otp)
    result = await send_login_otp(phone_10, otp)
    return {
        "phone": phone_10,
        "otp_channel": OTP_CHANNEL,
        "success": bool(result.get("success")),
        "whatsapp": result.get("whatsapp"),
        "sms": result.get("sms"),
        "hint": "OTP is stored in DB and can be verified via /consumer/auth/verify-otp for 5 minutes. If WhatsApp fails but SMS succeeds you can still login.",
    }


@app.on_event("startup")
async def _load_admin_alert_phones_from_db():
    """On startup, restore admin_alert_phones override from db.settings if set."""
    try:
        doc = await db.settings.find_one({"key": "admin_alert_phones"}, {"_id": 0})
        if doc and isinstance(doc.get("phones"), list) and doc["phones"]:
            global ADMIN_ALERT_PHONES
            ADMIN_ALERT_PHONES = [str(p).strip() for p in doc["phones"] if str(p).strip()]
            logger.info(f"Loaded admin_alert_phones from DB: {ADMIN_ALERT_PHONES}")
    except Exception as e:
        logger.warning(f"admin_alert_phones load skipped: {e}")




@api_router.get("/admin/bills/{bill_id}/force-credit-preview")
async def force_credit_preview(bill_id: str, payload: dict = Depends(verify_jwt_token)):
    """Returns the auto-calculated force-credit points for this bill (no mutation).
    Used by the admin UI to show 'You're about to credit X points' before confirm.
    """
    # Feb 2026: force-credit-preview only reads amount + store_name — lean
    # projection prevents Atlas MaxTimeMSExpired on legacy multi-MB bills.
    bill = await db.bills.find_one(
        {"id": bill_id},
        {"_id": 0, "amount": 1, "store_name": 1},
    )
    if not bill:
        raise HTTPException(status_code=404, detail="Bill not found")
    auto = await _compute_auto_points(float(bill.get("amount") or 0), bill.get("store_name"))
    return {
        "bill_id": bill_id,
        "amount": float(bill.get("amount") or 0),
        "store_name": bill.get("store_name"),
        "calculated_points": auto["points"],
        "rate_pct": auto["rate_pct"],
        "rate_basis": auto["rate_basis"],
        "category": auto["category"],
        "range_label": auto["range_label"],
        "brand_found": auto["brand_found"],
    }


@api_router.post("/admin/bills/{bill_id}/force-credit")
async def force_credit_bill(bill_id: str, background_tasks: BackgroundTasks,
                              payload: dict = Depends(verify_jwt_token)):
    """Force-credit a single bill using the auto-calculated points (category × range).
    No admin input needed — system calculates the exact reward per the earn-rate table.
    """
    # Feb 2026: force_credit path in _reprocess_single_bill never touches
    # the image → exclude image_url + ocr_raw_data + 15s max_time_ms.
    bill = await db.bills.find_one(
        {"id": bill_id},
        {"_id": 0, "image_url": 0, "ocr_raw_data": 0},
        max_time_ms=15000,
    )
    if not bill:
        raise HTTPException(status_code=404, detail="Bill not found")
    if bill.get("status") not in ("manual_review", "pending_review"):
        raise HTTPException(status_code=400,
                            detail=f"Bill is in '{bill.get('status')}' state — only pending bills can be force-credited")

    res = await _reprocess_single_bill(
        bill, re_ocr=False, send_whatsapp_flag=True,
        background_tasks=background_tasks,
        force_credit=True, force_credit_percent=0.0  # unused now; kept for sig
    )
    return {
        "success": res.get("action") == "approved",
        "points_issued": res.get("points", 0),
        "status": res.get("status"),
        "error": res.get("error"),
    }


class EditBrandRequest(BaseModel):
    """Payload for admin brand-name correction on a pending bill."""
    new_store_name: str
    reprocess: bool = True  # queue background reprocess (returns immediately)
    # Point 49 (Sep 2026): default OFF. When admin taps Fix Brand they want
    # the transaction to actually reach Fundle. If Fundle still rejects, the
    # bill stays in manual_review with the Fundle error so admin can try a
    # different brand variant (or use the separate "Force Credit" action to
    # credit locally on purpose). This avoids silently masking Fundle
    # rejections that keep the transaction from ever appearing on the Fundle
    # platform.
    auto_force_credit_on_fundle_reject: bool = False
    wait_for_result: bool = False  # opt-in: block until Fundle responds (legacy sync mode)


async def _apply_brand_edit_and_reprocess_bg(bill_id: str, old_name: Optional[str],
                                              new_name: str, by_user: str, auto_fc: bool):
    """Feb 2026 (iter-70): unified background worker for the Fix Brand popup.
    Owns BOTH the write (store_name + audit note + reprocessing_started_at)
    AND the reprocess call. Moved out of the request thread because an
    update_one on a bill doc that carries a legacy multi-MB inline image_url
    can take 6-10s on Atlas under load, tripping the request-thread timeout
    and surfacing as HTTP 503 to the admin UI.

    All DB writes are retried on transient errors. If both write attempts
    fail, we still try the reprocess (the pipeline itself will re-write
    store_name) so a slow Atlas doesn't lose the admin's edit entirely.
    """
    from pymongo.errors import NetworkTimeout, AutoReconnect, ServerSelectionTimeoutError, ExecutionTimeout
    _retryable = (NetworkTimeout, AutoReconnect, ServerSelectionTimeoutError, ExecutionTimeout)
    audit_note = f"Brand name updated: '{old_name}' → '{new_name}' by admin"
    write_ok = False
    for attempt in range(3):
        try:
            await asyncio.wait_for(
                db.bills.update_one(
                    {"id": bill_id},
                    {"$set": {
                        "store_name": new_name,
                        "brand_edited_at": datetime.now(timezone.utc).isoformat(),
                        "brand_edited_by": by_user,
                        "admin_notes": audit_note,
                        "reprocessing_started_at": datetime.now(timezone.utc).isoformat(),
                    }}
                ),
                timeout=12.0,
            )
            write_ok = True
            break
        except (asyncio.TimeoutError, *_retryable) as e:
            logger.warning(f"edit-brand (bg): update_one attempt {attempt+1} failed for {bill_id}: {e}")
            if attempt < 2:
                await asyncio.sleep(1.0 + attempt)
                continue
        except Exception as e:
            logger.exception(f"edit-brand (bg): update_one non-transient failure for {bill_id}: {e}")
            break
    if not write_ok:
        logger.error(f"edit-brand (bg): all update_one attempts failed for {bill_id}; will still attempt reprocess")
    # Kick off the reprocess pipeline regardless of the write outcome — the
    # pipeline re-writes store_name on approve/manual_review, so a slow
    # Atlas doesn't lose the admin's brand correction.
    try:
        await _reprocess_after_brand_edit(bill_id, new_name, auto_fc)
    except Exception as e:
        logger.exception(f"edit-brand (bg): reprocess chain failed for {bill_id}: {e}")


async def _reprocess_after_brand_edit(bill_id: str, new_name: str, auto_fc: bool):
    """Background worker for edit-brand — runs the reprocess pipeline off the
    request thread so Cloudflare/browser fetch doesn't time out (Fundle
    earn_points can take 30-60s with image upload)."""
    from fastapi import BackgroundTasks as _BG
    bg = _BG()
    try:
        # Feb 2026: 25s max_time_ms — legacy inline image_url transfer.
        updated_bill = await db.bills.find_one({"id": bill_id}, {"_id": 0}, max_time_ms=25000)
        if not updated_bill:
            return
        res = await _reprocess_single_bill(
            updated_bill, re_ocr=False, send_whatsapp_flag=True,
            background_tasks=bg
        )
        # Auto-fallback: if Fundle still rejects, force-credit locally
        fundle_rejected_brand = res.get("action") != "approved" and auto_fc
        if fundle_rejected_brand:
            err_txt = str(res.get("error") or "").lower()
            # Point 38 follow-up: DON'T force-credit when Fundle refused because
            # the bill image was missing/undecodable — a corrupted-image bill
            # is exactly the population we cannot verify, so silently approving
            # 50 pts would be worse than leaving it in manual_review.
            image_missing = ("bill_file" in err_txt) or ("no file was submitted" in err_txt) or ("image" in err_txt and "missing" in err_txt)
            if image_missing:
                logger.info(f"edit-brand (bg): skipping force-credit fallback for {bill_id} — Fundle rejection was due to missing/corrupted image")
            elif ("brand" in err_txt) or ("match" in err_txt) or ("0 points" in err_txt) or ("not found" in err_txt):
                logger.info(f"edit-brand (bg): Fundle rejected '{new_name}'. Auto-force-credit fallback for bill {bill_id}")
                # Feb 2026: 25s max_time_ms + skip the heavy image_url on this
                # reload — the reprocess pipeline just needs status + amount +
                # store_name for the force-credit path (no fresh image needed
                # since we already tried once above).
                updated_bill2 = await db.bills.find_one(
                    {"id": bill_id},
                    {"_id": 0, "image_url": 0, "ocr_raw_data": 0},
                    max_time_ms=15000,
                )
                if updated_bill2 and updated_bill2.get("status") in ("manual_review", "pending_review", "rejected"):
                    await _reprocess_single_bill(
                        updated_bill2, re_ocr=False, send_whatsapp_flag=True,
                        background_tasks=bg,
                        force_credit=True, force_credit_percent=0.0
                    )
    except Exception as e:
        logger.exception(f"edit-brand background reprocess failed for {bill_id}: {e}")


@api_router.post("/admin/bills/{bill_id}/edit-brand")
async def edit_bill_brand(bill_id: str, payload_body: EditBrandRequest,
                           background_tasks: BackgroundTasks,
                           payload: dict = Depends(verify_jwt_token)):
    """Correct the brand name on a bill whose OCR mis-matched Fundle's master,
    then queue a background reprocess (default) or run inline (`wait_for_result=true`).

    The reprocess pipeline includes:
      1. Re-send to Fundle with the corrected brand name
      2. If Fundle still rejects with brand-mismatch → auto force-credit locally
         (using tier × amount earn-rate; admin has visually verified the bill).

    Returns immediately in the default (background) mode — poll the bill row
    for updated status via GET /api/bills.

    Feb 2026 hardening: wrap the whole handler so any unexpected exception
    (mongo hiccup, background task registration error) becomes a 500 with
    a JSON body — the admin UI then shows a readable toast instead of the
    empty "Brand edit failed (HTTP 500)".
    """
    try:
        from pymongo.errors import NetworkTimeout, AutoReconnect, ServerSelectionTimeoutError, ExecutionTimeout
        _retryable = (NetworkTimeout, AutoReconnect, ServerSelectionTimeoutError, ExecutionTimeout)
        # Feb 2026 (iter-70): request thread does ONE cheap indexed find_one
        # and NOTHING else. All writes (audit note + reprocessing_started_at
        # marker) are moved into the background worker together with the
        # actual reprocess call. Reason: even a $set update on a bill doc
        # that carries a legacy multi-MB inline image_url can take 6-10s on
        # Atlas under load — the update_one on the request thread was the
        # last remaining Atlas-timeout risk on this endpoint.
        bill = None
        for attempt in range(2):
            try:
                bill = await db.bills.find_one(
                    {"id": bill_id},
                    {"_id": 0, "id": 1, "store_name": 1, "status": 1},
                    max_time_ms=8000,
                )
                break
            except _retryable:
                if attempt == 0:
                    await asyncio.sleep(0.3)
                    continue
                raise
        if not bill:
            raise HTTPException(status_code=404, detail="Bill not found")
        new_name = (payload_body.new_store_name or "").strip()
        if not new_name:
            raise HTTPException(status_code=400, detail="new_store_name is required")

        old_name = bill.get("store_name")

        # Default: queue background worker that does BOTH the write AND the
        # reprocess. Returns in <200ms regardless of Atlas latency.
        if payload_body.reprocess and not payload_body.wait_for_result:
            background_tasks.add_task(
                _apply_brand_edit_and_reprocess_bg,
                bill_id, old_name, new_name,
                payload.get("username") or "admin",
                payload_body.auto_force_credit_on_fundle_reject,
            )
            return {
                "success": True,
                "reprocessed": "queued",
                "store_name": new_name,
                "message": "Brand updated. Reprocessing in background — refresh the list in ~10 seconds to see the result."
            }

        # Rename-only path (reprocess=false): still needs the write, but
        # without an image-heavy update pipeline. Do it inline with retry.
        audit_note = f"Brand name updated: '{old_name}' → '{new_name}' by admin"
        for attempt in range(2):
            try:
                await asyncio.wait_for(
                    db.bills.update_one(
                        {"id": bill_id},
                        {"$set": {
                            "store_name": new_name,
                            "brand_edited_at": datetime.now(timezone.utc).isoformat(),
                            "brand_edited_by": payload.get("username") or "admin",
                            "admin_notes": audit_note,
                            "reprocessing_started_at": datetime.now(timezone.utc).isoformat() if payload_body.reprocess else None,
                        }}
                    ),
                    timeout=6.0,
                )
                break
            except (asyncio.TimeoutError, *_retryable):
                if attempt == 0:
                    await asyncio.sleep(0.3)
                    continue
                raise

        if not payload_body.reprocess:
            return {"success": True, "reprocessed": False, "store_name": new_name}

        # Sync path (legacy) — waits for Fundle. Kept for admins who need immediate result.
        # Feb 2026: 25s max_time_ms — legacy inline image_url transfer.
        updated_bill = await db.bills.find_one({"id": bill_id}, {"_id": 0}, max_time_ms=25000)
        res = await _reprocess_single_bill(
            updated_bill, re_ocr=False, send_whatsapp_flag=True,
            background_tasks=background_tasks
        )

        # ---- Auto-fallback: if Fundle still rejects, force-credit locally ----
        fundle_rejected_brand = (
            res.get("action") != "approved"
            and payload_body.auto_force_credit_on_fundle_reject
        )
        if fundle_rejected_brand:
            err_txt = str(res.get("error") or "").lower()
            # Only fallback on brand-mismatch errors; leave other errors as-is
            if ("brand" in err_txt) or ("match" in err_txt) or ("0 points" in err_txt) or ("not found" in err_txt):
                logger.info(f"edit-brand: Fundle rejected '{new_name}'. Auto-force-credit fallback for bill {bill_id}")
                # Reload bill (status may have been updated by the reprocess).
                # Feb 2026: skip heavy fields — force-credit only needs status +
                # amount + store_name; image_url is not needed for this fallback.
                updated_bill2 = await db.bills.find_one(
                    {"id": bill_id},
                    {"_id": 0, "image_url": 0, "ocr_raw_data": 0},
                    max_time_ms=15000,
                )
                # Only force-credit if the bill is still in a pending-ish state
                if updated_bill2 and updated_bill2.get("status") in ("manual_review", "pending_review", "rejected"):
                    fc = await _reprocess_single_bill(
                        updated_bill2, re_ocr=False, send_whatsapp_flag=True,
                        background_tasks=background_tasks,
                        force_credit=True, force_credit_percent=0.0
                    )
                    return {
                        "success": fc.get("action") == "approved",
                        "reprocessed": True,
                        "store_name": new_name,
                        "action": fc.get("action"),
                        "status": fc.get("status"),
                        "points": fc.get("points", 0),
                        "fallback": "force_credit",
                        "fundle_error": res.get("error"),
                        "error": fc.get("error"),
                    }

        return {
            "success": res.get("action") == "approved",
            "reprocessed": True,
            "store_name": new_name,
            "action": res.get("action"),
            "status": res.get("status"),
            "points": res.get("points", 0),
            "error": res.get("error"),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"edit_bill_brand failed for bill_id={bill_id}: {e}")
        # Feb 2026 (iter-68): Atlas transient timeouts get a friendlier 503
        # so the admin UI can show "MongoDB slow — please retry" instead of a
        # scary raw 500. Everything else keeps the 500 with the exact reason.
        # Iter-69: use isinstance against the pymongo exception classes —
        # substring matching against str(e) misses AutoReconnect,
        # ServerSelectionTimeoutError and ExecutionTimeout (MaxTimeMSExpired)
        # because their messages never include the class name.
        try:
            from pymongo.errors import (
                NetworkTimeout as _NT,
                AutoReconnect as _AR,
                ServerSelectionTimeoutError as _SST,
                ExecutionTimeout as _ET,
            )
            _transient_classes = (_NT, _AR, _SST, _ET, asyncio.TimeoutError)
        except Exception:
            _transient_classes = (asyncio.TimeoutError,)
        err_txt = str(e)
        is_transient_db = (
            isinstance(e, _transient_classes)
            or ("read operation timed out" in err_txt.lower())
            or ("write operation timed out" in err_txt.lower())
            or ("operation exceeded time limit" in err_txt.lower())
        )
        if is_transient_db:
            raise HTTPException(
                status_code=503,
                detail="MongoDB is under load — the brand edit didn't go through. Please retry in ~10s.",
            )
        raise HTTPException(
            status_code=500,
            detail=f"Brand edit server error: {err_txt[:200]}"
        )


# Karix API Key
KARIX_API_KEY = os.environ.get('WHATSAPP_API_KEY', '')

# ======================== ADMIN SMS ALERT ========================

async def send_admin_sms_alert(brand_name: str, bill_no: str, amount: float, user_phone: str):
    """Send SMS alert to admin when a brand is not found in Fundle master"""
    try:
        logger.info(f"Sending admin alert for brand: {brand_name} to {ADMIN_PHONE}")
        
        # Send WhatsApp message to admin
        admin_msg = f""" *New Brand Alert - Action Required*

A bill was uploaded but the brand is not in Fundle master.

 *Add this exact brand name to Fundle:*
 *{brand_name}*

 Bill Details:
• Bill No: {bill_no}
• Amount: ₹{amount:.0f}
• User: {user_phone}

Please add the brand "{brand_name}" to TagnPay panel, then click "Reprocess" in admin dashboard."""
        
        result = await send_whatsapp_text(ADMIN_PHONE, admin_msg)
        logger.info(f"Admin alert sent for brand: {brand_name}, result: {result}")
        return result
    except Exception as e:
        logger.error(f"Failed to send admin alert: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False

# ======================== KARIX WHATSAPP HELPER ========================
KARIX_SMS_API_URL = os.environ.get('KARIX_SMS_API_URL', 'https://pod2-japi.instaalerts.zone/httpapi/QueryStringReceiver')
KARIX_SMS_API_KEY = os.environ.get('KARIX_SMS_API_KEY', '')
KARIX_SMS_SENDER_ID = os.environ.get('KARIX_SMS_SENDER_ID', 'CP67')
KARIX_SMS_DLT_ENTITY_ID = os.environ.get('KARIX_SMS_DLT_ENTITY_ID', '')
KARIX_SMS_DLT_TEMPLATE_ID = os.environ.get('KARIX_SMS_DLT_TEMPLATE_ID', '')
OTP_DEV_BYPASS = os.environ.get('OTP_DEV_BYPASS', '')

# Point 25: Admin alert channel — WhatsApp text messages are pushed here
# whenever a bill enters pending / manual_review / rejected state. Comma-
# separated list of E.164 or 10/12-digit Indian numbers (both formats accepted;
# normalised at send time). Falls back to the mall ops number below.
ADMIN_ALERT_PHONES = [p.strip() for p in os.environ.get('ADMIN_ALERT_PHONES', '9766692497').split(',') if p.strip()]


def _normalize_alert_phone(p: str) -> str:
    p = "".join(ch for ch in (p or "") if ch.isdigit())
    if len(p) == 10:
        return f"91{p}"
    return p


async def send_admin_bill_alert(event: str, bill: dict, reason: Optional[str] = None) -> None:
    """Fire-and-forget: notify configured mall-ops phones on bill state change.

    event: one of 'pending', 'manual_review', 'rejected'

    Point 36 (Feb 2026): dual-channel — WhatsApp AND SMS to each ops phone so
    the message survives a closed WhatsApp session window. SMS is best-effort;
    Karix may reject on strict DLT match unless a dedicated bill-alert DLT
    template is configured via KARIX_SMS_ALERT_DLT_TEMPLATE_ID.
    """
    if not ADMIN_ALERT_PHONES:
        return
    try:
        pretty_event = {
            "pending": "PENDING REVIEW",
            "manual_review": "MANUAL REVIEW",
            "rejected": "REJECTED",
            "pending_review": "PENDING REVIEW",
        }.get(event, (event or "").upper() or "UPDATED")
        user_phone = bill.get("user_phone") or "-"
        store = bill.get("store_name") or "Unknown"
        amount = bill.get("amount")
        bill_no = bill.get("bill_no") or "-"
        bill_id = bill.get("id") or "-"
        rej = (reason or bill.get("rejection_reason") or "").strip()
        amount_str = f"\u20b9{amount:.0f}" if isinstance(amount, (int, float)) and amount > 0 else "-"
        msg = (
            f"CP67 Bill Alert - {pretty_event}\n\n"
            f"Customer: {user_phone}\n"
            f"Store: {store}\n"
            f"Amount: {amount_str}\n"
            f"Bill No: {bill_no}\n"
            f"Bill ID: {bill_id[:8]}\n"
        )
        if rej:
            msg += f"Reason: {rej[:180]}\n"

        # SMS variant — kept short, plain ASCII to survive DLT truncation.
        sms_msg = f"CP67 Bill {pretty_event}: cust {user_phone}, {store}, Amt {amount_str}, Bill {bill_no}. Reason: {rej[:80] if rej else '-'}"

        for admin_phone in ADMIN_ALERT_PHONES:
            to = _normalize_alert_phone(admin_phone)
            if not to:
                continue
            # 1) WhatsApp
            try:
                await send_whatsapp_text(to, msg)
            except Exception as e:
                logger.warning(f"Admin alert (whatsapp) failed to {to}: {e}")
            # 2) SMS (Point 36 — "put SMS all over")
            try:
                phone_10 = to[-10:] if len(to) >= 10 else to
                await send_sms_text(phone_10, sms_msg)
            except Exception as e:
                logger.warning(f"Admin alert (sms) failed to {to}: {e}")
    except Exception as e:
        logger.warning(f"send_admin_bill_alert failed: {e}")


async def maybe_alert_admin(bill_id: str, status: str, reason: Optional[str] = None) -> None:
    """Alert admin about a bill state change, deduped per (bill_id, status)
    so retries/re-inserts don't spam the ops number. Safe to call in any path.
    """
    if not bill_id or status not in ("pending", "pending_review", "manual_review", "rejected"):
        return
    # Feb 2026: 5-min in-memory cooldown for bills that timed out on the
    # previous attempt. Without this, the 60s scanner loop retries the same
    # legacy heavy bill every cycle, snowballing timed-out Motor connections
    # and starving user-facing operations (brand edits, health checks).
    cooldown_key = (bill_id, status)
    now_ts = time.time()
    cooled_until = _ALERT_FAILURE_COOLDOWN.get(cooldown_key)
    if cooled_until and cooled_until > now_ts:
        return
    try:
        # Feb 2026: project ONLY the fields needed by send_admin_bill_alert.
        # Legacy bills carry a multi-MB base64 image_url inline and pulling
        # the whole doc trips Atlas maxTimeMS / Motor read timeouts under
        # concurrent webhook+scanner load. This is the root cause of the
        # "maybe_alert_admin failed ... The read operation timed out" spam
        # seen in production logs. 5s max_time_ms means scanner queries fail
        # fast instead of holding a socket for the full 20s socketTimeoutMS.
        b = await db.bills.find_one(
            {"id": bill_id},
            {
                "_id": 0,
                "id": 1,
                "user_phone": 1,
                "store_name": 1,
                "amount": 1,
                "bill_no": 1,
                "rejection_reason": 1,
                "admin_alerts_sent": 1,
            },
            max_time_ms=5000,
        )
        if not b:
            return
        already = (b.get("admin_alerts_sent") or {}).get(status)
        if already:
            return
        await send_admin_bill_alert(status, b, reason)
        await db.bills.update_one(
            {"id": bill_id},
            {"$set": {f"admin_alerts_sent.{status}": datetime.now(timezone.utc).isoformat()}}
        )
        # Success — clear any prior cooldown entry so subsequent status
        # transitions on the same bill aren't accidentally suppressed.
        _ALERT_FAILURE_COOLDOWN.pop(cooldown_key, None)
    except Exception as e:
        # Register a 5-minute cooldown so the scanner skips this bill on
        # its next cycle. Prevents timeout snowballing under Atlas hiccups.
        _ALERT_FAILURE_COOLDOWN[cooldown_key] = now_ts + 300
        # Opportunistic GC — the cooldown map is bounded by unique
        # (bill_id, status) pairs but let's not let it grow unbounded in
        # long-running processes.
        if len(_ALERT_FAILURE_COOLDOWN) > 1000:
            _prune_alert_failure_cooldown(now_ts)
        logger.warning(f"maybe_alert_admin failed for {bill_id}/{status}: {e}")


# Feb 2026: (bill_id, status) → epoch-seconds until which this pair is
# skipped by maybe_alert_admin. Populated on any exception (typically
# Atlas MaxTimeMSExpired / read timeout) and cleared on the next
# successful send. Process-local — each pod maintains its own map, which
# is fine because dedup is ultimately enforced by the
# admin_alerts_sent.<status> field on the bill doc itself.
_ALERT_FAILURE_COOLDOWN: Dict[Tuple[str, str], float] = {}


def _prune_alert_failure_cooldown(now_ts: float) -> None:
    """Drop expired entries in-place to keep the cooldown map bounded."""
    expired = [k for k, v in _ALERT_FAILURE_COOLDOWN.items() if v <= now_ts]
    for k in expired:
        _ALERT_FAILURE_COOLDOWN.pop(k, None)


async def insert_bill_and_alert(bill_dict: dict) -> str:
    """Point 36: single entry point for inserting a bill AND firing the admin alert
    to ADMIN_ALERT_PHONES for pending/manual_review/rejected states. Prevents the
    situation where a WhatsApp-only bill goes into pending state and never reaches
    the configured ops number because the legacy path only pinged ADMIN_PHONE.
    Returns the inserted bill id."""
    await db.bills.insert_one(bill_dict)
    bill_id = bill_dict.get("id")
    status = bill_dict.get("status") or ""
    if bill_id and status in ("pending", "pending_review", "manual_review", "rejected"):
        asyncio.create_task(maybe_alert_admin(bill_id, status, bill_dict.get("rejection_reason")))
    return bill_id


async def send_otp_sms(phone_10: str, otp: str) -> dict:
    """Send OTP SMS via Karix HTTP API using DLT-approved template:
    'Your verification OTP is {#var#} Use this at CP67 Mall.'
    `phone_10` is the 10-digit Indian mobile number (without country code).
    """
    if not KARIX_SMS_API_KEY:
        logger.error("Karix SMS API key not configured")
        return {"success": False, "error": "SMS gateway not configured"}

    text = f"Your verification OTP is {otp} Use this at CP67 Mall."
    params = {
        "ver": "1.0",
        "key": KARIX_SMS_API_KEY,
        "encrpt": "0",
        "dest": phone_10,
        "send": KARIX_SMS_SENDER_ID,
        "dlt_entity_id": KARIX_SMS_DLT_ENTITY_ID,
        "dlt_template_id": KARIX_SMS_DLT_TEMPLATE_ID,
        "text": text,
    }
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(KARIX_SMS_API_URL, params=params)
            body = (resp.text or "").strip()
            logger.info(f"Karix SMS to {phone_10}: status={resp.status_code} body={body[:200]}")
            # Karix QueryStringReceiver returns text containing 'Statuscode=200' and 'Platform Accepted' on success
            body_upper = body.upper()
            is_ok = resp.status_code == 200 and ("STATUSCODE=200" in body_upper or "PLATFORM ACCEPTED" in body_upper or body_upper.startswith("OK"))
            return {"success": is_ok, "status_code": resp.status_code, "response": body}
    except Exception as e:
        logger.error(f"Karix SMS send error: {e}")
        return {"success": False, "error": str(e)}


async def send_otp_whatsapp(phone_10: str, otp: str) -> dict:
    """Point 11: Send OTP via WhatsApp (Karix WABA text).
    `phone_10` is the 10-digit Indian mobile number. The message uses the same
    DLT-approved wording as the SMS template so recipients see a familiar
    format. Returns the same {success, status_code, mid, ...} dict shape as
    send_whatsapp_text_diag so callers can log / surface delivery diagnostics.

    NOTE: outside a 24-hour WhatsApp session window, non-template messages will
    be silently dropped by WhatsApp Business. For login OTP flows this is
    typically fine because the app funnels users through a WhatsApp CTA first;
    for cold registrations enable OTP_SMS_FALLBACK to also send an SMS.
    """
    phone_e164 = f"91{phone_10}" if len(phone_10) == 10 else phone_10
    # Point 11 (Aug 2026): Match the DLT-approved SMS template wording exactly so
    # consumer + retailer login OTP messages are consistent across WhatsApp and SMS.
    # Template ref: PEID 1701172802304667512 / Temp ID 1707172914885560615 / Header CP67.
    text = f"Your verification OTP is {otp} Use this at CP67 Mall."
    return await send_whatsapp_text_diag(phone_e164, text)


# Point 11 / Point 36: default channel is BOTH per client direction ("put SMS all over") —
# every OTP fires via WhatsApp AND SMS so delivery is guaranteed even if one channel drops.
OTP_CHANNEL = os.environ.get("OTP_CHANNEL", "both").strip().lower()  # 'whatsapp' | 'sms' | 'both'


async def send_login_otp(phone_10: str, otp: str) -> dict:
    """Dispatch OTP via the configured channel(s). Always returns a dict with
    per-channel results so admin diagnostics can see exactly what happened."""
    results = {"whatsapp": None, "sms": None, "success": False}
    if OTP_CHANNEL in ("whatsapp", "both"):
        results["whatsapp"] = await send_otp_whatsapp(phone_10, otp)
        if results["whatsapp"].get("success"):
            results["success"] = True
    if OTP_CHANNEL in ("sms", "both") or (OTP_CHANNEL == "whatsapp" and not results["success"]
                                          and os.environ.get("OTP_SMS_FALLBACK", "").lower() == "true"):
        results["sms"] = await send_otp_sms(phone_10, otp)
        if results["sms"].get("success"):
            results["success"] = True
    return results


# Point 36 (Feb 2026): ops bill alerts must also go via SMS so that when the WhatsApp
# session window is closed (Karix accepts but WhatsApp drops), the ops team still gets
# an SMS. If your Karix account has a dedicated DLT template for ops alerts, set
# KARIX_SMS_ALERT_DLT_TEMPLATE_ID in .env; otherwise we reuse the existing OTP DLT template
# as best-effort — Karix may reject on strict DLT match, but the try-and-log path
# gives ops visibility either way.
KARIX_SMS_ALERT_DLT_TEMPLATE_ID = os.environ.get('KARIX_SMS_ALERT_DLT_TEMPLATE_ID', '') or KARIX_SMS_DLT_TEMPLATE_ID


async def send_sms_text(phone_10: str, message: str) -> dict:
    """Send a generic SMS via the Karix SMS gateway. Uses KARIX_SMS_ALERT_DLT_TEMPLATE_ID
    if configured, otherwise falls back to the OTP DLT template id (best-effort).
    Returns the same diag shape as send_otp_sms."""
    if not KARIX_SMS_API_KEY:
        return {"success": False, "status_code": None, "error": "SMS gateway not configured"}
    # Karix SMS API caps text; trim aggressively to be safe.
    text = (message or "").strip()[:400]
    params = {
        "ver": "1.0",
        "key": KARIX_SMS_API_KEY,
        "encrpt": "0",
        "dest": phone_10,
        "send": KARIX_SMS_SENDER_ID,
        "dlt_entity_id": KARIX_SMS_DLT_ENTITY_ID,
        "dlt_template_id": KARIX_SMS_ALERT_DLT_TEMPLATE_ID,
        "text": text,
    }
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(KARIX_SMS_API_URL, params=params)
            body = (resp.text or "").strip()
            logger.info(f"Karix SMS (alert) to {phone_10}: status={resp.status_code} body={body[:200]}")
            body_upper = body.upper()
            is_ok = resp.status_code == 200 and ("STATUSCODE=200" in body_upper or "PLATFORM ACCEPTED" in body_upper or body_upper.startswith("OK"))
            return {"success": is_ok, "status_code": resp.status_code, "response": body[:400]}
    except Exception as e:
        logger.error(f"Karix SMS (alert) send error to {phone_10}: {e}")
        return {"success": False, "error": str(e)}


async def store_otp(phone_10: str, otp: str) -> None:
    """Persist OTP with 5-minute expiry. Replaces any prior OTP for this phone."""
    now = datetime.now(timezone.utc)
    expires = now + timedelta(minutes=5)
    await db.otp_codes.update_one(
        {"phone": phone_10},
        {"$set": {
            "phone": phone_10,
            "otp": otp,
            "created_at": now.isoformat(),
            "expires_at": expires.isoformat(),
            "attempts": 0,
        }},
        upsert=True,
    )


async def verify_stored_otp(phone_10: str, otp: str) -> bool:
    """Verify OTP against the stored record. Increments attempt counter,
    blocks after 5 failed attempts, deletes record on success or expiry."""
    rec = await db.otp_codes.find_one({"phone": phone_10}, {"_id": 0})
    if not rec:
        return False
    try:
        expires_at = datetime.fromisoformat(rec["expires_at"])
    except Exception:
        expires_at = None
    if expires_at and expires_at < datetime.now(timezone.utc):
        await db.otp_codes.delete_one({"phone": phone_10})
        return False
    if rec.get("attempts", 0) >= 5:
        await db.otp_codes.delete_one({"phone": phone_10})
        return False
    if str(rec.get("otp")) == str(otp):
        await db.otp_codes.delete_one({"phone": phone_10})
        return True
    await db.otp_codes.update_one({"phone": phone_10}, {"$inc": {"attempts": 1}})
    return False


async def send_whatsapp_text(phone: str, message: str) -> bool:
    """Send simple text WhatsApp message via Karix RCM API."""
    r = await send_whatsapp_text_diag(phone, message)
    return bool(r.get("success"))


async def send_whatsapp_text_diag(phone: str, message: str) -> dict:
    """Point 36: same as send_whatsapp_text but returns the full Karix response
    (status_code, mid, response body) so admin diagnostics can surface exactly
    what happened. Kept separate so the boolean contract of send_whatsapp_text
    doesn't change and existing `if send_whatsapp_text(...)` checks keep working.
    """
    if not KARIX_API_KEY:
        logger.error("Karix API key not configured")
        return {"success": False, "error": "Karix API key not configured", "to": phone}
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://rcmapi.instaalerts.zone/services/rcm/sendMessage",
                headers={
                    "Authentication": f"Bearer {KARIX_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "message": {
                        "channel": "WABA",
                        "content": {
                            "preview_url": False,
                            "type": "TEXT",
                            "text": message
                        },
                        "recipient": {
                            "to": phone,
                            "recipient_type": "individual",
                            "reference": {}
                        },
                        "sender": {
                            "from": WHATSAPP_NUMBER
                        },
                        "preferences": {
                            "webHookDNId": "1001"
                        }
                    },
                    "metaData": {
                        "version": "v1.0.9"
                    }
                }
            )
            body_text = response.text or ""
            logger.info(f"Karix text response ({phone}): {response.status_code} - {body_text[:200]}")
            ok = response.status_code == 200
            mid = None
            try:
                mid = response.json().get("mid")
            except Exception:
                pass
            return {
                "success": ok,
                "status_code": response.status_code,
                "mid": mid,
                "response": body_text[:400],
                "to": phone,
            }
    except Exception as e:
        logger.error(f"Karix send error to {phone}: {e}")
        return {"success": False, "error": str(e), "to": phone}

async def send_whatsapp_buttons(phone: str, body_text: str, buttons: list):
    """Send WhatsApp interactive button message via Karix RCM API
    Automatically switches to list message when more than 3 buttons are provided.
    """
    if not KARIX_API_KEY:
        logger.error("Karix API key not configured")
        return False
    
    # WhatsApp only supports max 3 buttons - use list for more options
    if len(buttons) > 3:
        return await send_whatsapp_list(phone, body_text, buttons)
    
    # Format buttons for Karix API
    button_list = []
    for i, btn in enumerate(buttons):
        button_list.append({
            "type": "reply",
            "reply": {
                "id": btn.get("id", str(i+1)),
                "title": btn.get("title", f"Option {i+1}")
            }
        })
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://rcmapi.instaalerts.zone/services/rcm/sendMessage",
                headers={
                    "Authentication": f"Bearer {KARIX_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "message": {
                        "channel": "WABA",
                        "content": {
                            "preview_url": False,
                            "type": "INTERACTIVE",
                            "interactive": {
                                "type": "button",
                                "body": {
                                    "text": body_text
                                },
                                "action": {
                                    "buttons": button_list
                                }
                            }
                        },
                        "recipient": {
                            "to": phone,
                            "recipient_type": "individual",
                            "reference": {}
                        },
                        "sender": {
                            "from": WHATSAPP_NUMBER
                        },
                        "preferences": {
                            "webHookDNId": "1001"
                        }
                    },
                    "metaData": {
                        "version": "v1.0.9"
                    }
                }
            )
            logger.info(f"Karix buttons response: {response.status_code} - {response.text}")
            return response.status_code == 200
    except Exception as e:
        logger.error(f"Karix buttons error: {e}")
        return False

async def send_whatsapp_list(phone: str, body_text: str, options: list, header_text: str = "Select an Option", button_text: str = "View Options"):
    """Send WhatsApp interactive list message via Karix RCM API
    Used when more than 3 options need to be presented.
    """
    if not KARIX_API_KEY:
        logger.error("Karix API key not configured")
        return False
    
    # Format options as list rows
    rows = []
    for i, opt in enumerate(options):
        rows.append({
            "id": opt.get("id", str(i+1)),
            "title": opt.get("title", f"Option {i+1}")[:24],  # WhatsApp limit: 24 chars
            "description": opt.get("description", "")[:72] if opt.get("description") else ""  # WhatsApp limit: 72 chars
        })
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://rcmapi.instaalerts.zone/services/rcm/sendMessage",
                headers={
                    "Authentication": f"Bearer {KARIX_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "message": {
                        "channel": "WABA",
                        "content": {
                            "preview_url": False,
                            "type": "INTERACTIVE",
                            "interactive": {
                                "type": "list",
                                "header": {
                                    "type": "text",
                                    "text": header_text[:60]  # WhatsApp limit
                                },
                                "body": {
                                    "text": body_text
                                },
                                "footer": {
                                    "text": "CP67 Mall - Homeland Advantage"
                                },
                                "action": {
                                    "button": button_text[:20],  # WhatsApp limit
                                    "sections": [
                                        {
                                            "title": "Options",
                                            "rows": rows
                                        }
                                    ]
                                }
                            }
                        },
                        "recipient": {
                            "to": phone,
                            "recipient_type": "individual",
                            "reference": {}
                        },
                        "sender": {
                            "from": WHATSAPP_NUMBER
                        },
                        "preferences": {
                            "webHookDNId": "1001"
                        }
                    },
                    "metaData": {
                        "version": "v1.0.9"
                    }
                }
            )
            logger.info(f"Karix list response: {response.status_code} - {response.text}")
            return response.status_code == 200
    except Exception as e:
        logger.error(f"Karix list error: {e}")
        return False

# Legacy function for compatibility
async def send_whatsapp_message(phone: str, message: str):
    return await send_whatsapp_text(phone, message)

async def upload_media_to_karix(image_base64: str, filename: str = "qrcode.png") -> Optional[str]:
    """Upload media (image) to Karix and get media ID for sending via WhatsApp
    
    Tries multiple upload methods based on Karix documentation
    Returns: media_id if successful, None if failed
    """
    if not KARIX_API_KEY:
        logger.error("Karix API key not configured")
        return None
    
    try:
        # Extract base64 data if it has data URL prefix
        if image_base64.startswith("data:"):
            image_base64 = image_base64.split(",")[1]
        
        # Convert base64 to binary
        import base64
        image_binary = base64.b64decode(image_base64)
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            # Try multipart form upload (common for media APIs)
            files = {
                'file': (filename, image_binary, 'image/png')
            }
            data = {
                'messaging_product': 'whatsapp',
                'type': 'image/png'
            }
            
            response = await client.post(
                "https://rcmapi.instaalerts.zone/services/rcm/media/upload",
                headers={
                    "Authentication": f"Bearer {KARIX_API_KEY}"
                },
                files=files,
                data=data
            )
            logger.info(f"Karix media upload (multipart): {response.status_code} - {response.text[:200]}")
            
            if response.status_code == 200:
                try:
                    resp_data = response.json()
                    media_id = resp_data.get("id") or resp_data.get("media_id") or resp_data.get("mediaId")
                    if media_id:
                        logger.info(f"Media uploaded successfully, ID: {media_id}")
                        return media_id
                except Exception:
                    pass
            
            logger.warning("Media upload failed, will try direct send")
            return None
    except Exception as e:
        logger.error(f"Karix media upload error: {e}")
        return None

async def send_whatsapp_image(phone: str, image_base64: str, caption: str = ""):
    """Send WhatsApp image via Karix using ATTACHMENT type.
    Exact working format confirmed by Karix support.
    """
    if not KARIX_API_KEY:
        logger.error("Karix API key not configured")
        return False
    
    try:
        import re
        code_match = re.search(r'(PKG-[A-Z0-9-]+|PARK-[A-Z0-9]+)', caption)
        
        if not code_match:
            logger.warning("No parking code found in caption, cannot send image")
            return await send_whatsapp_text(phone, caption)
        
        parking_code = code_match.group(1)
        backend_url = os.environ.get('BACKEND_PUBLIC_URL', 'https://cp67bot.fundlexperiences.com')
        if parking_code.startswith("PARK-"):
            qr_url = f"{backend_url}/api/parking/coupon-qr/{parking_code}"
        else:
            qr_url = f"{backend_url}/api/parking/qr-image/{parking_code}"
        
        logger.info(f"Sending QR image to {phone} via ATTACHMENT type")
        logger.info(f"QR URL: {qr_url}")
        
        payload = {
            "message": {
                "channel": "WABA",
                "content": {
                    "type": "ATTACHMENT",
                    "attachment": {
                        "type": "image",
                        "caption": caption,
                        "mimeType": "image/jpeg",
                        "url": qr_url
                    }
                },
                "recipient": {
                    "to": phone,
                    "recipient_type": "individual",
                    "reference": {}
                },
                "sender": {
                    "from": WHATSAPP_NUMBER
                },
                "preferences": {
                    "webHookDNId": "1001"
                }
            },
            "metaData": {
                "version": "v1.0.9"
            }
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://rcmapi.instaalerts.zone/services/rcm/sendMessage",
                headers={
                    "Authentication": f"Bearer {KARIX_API_KEY}",
                    "Content-Type": "application/json"
                },
                json=payload
            )
            logger.info(f"Karix ATTACHMENT response: {response.status_code} - {response.text[:500]}")
            
            if response.status_code in [200, 202]:
                logger.info(f"QR Image sent successfully to {phone}")
                return True
            
            logger.warning(f"Image send failed (status {response.status_code}), falling back to text")
            return await send_whatsapp_text(phone, caption)
            
    except Exception as e:
        logger.error(f"Karix image send error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return await send_whatsapp_text(phone, caption)

# ======================== WHATSAPP WEBHOOK ROUTES ========================

async def process_new_user_registration(phone: str, profile_name: str, source_code: str, qr_data: dict, background_tasks: BackgroundTasks, attributing_staff: dict = None):
    """Handle new user registration flow.
    `attributing_staff` (optional) — if the customer arrived via a #STAFF:token
    WhatsApp message, we create a pending staff registration incentive that
    becomes redeemable when the customer uploads their first approved bill."""
    # Strip 91 prefix for API calls
    mobile_10 = phone[2:] if phone.startswith("91") and len(phone) == 12 else phone
    
    # First check if user exists in Fundle API
    points_result = await tagnpay_client.get_customer_points(mobile_10)
    is_existing_fundle_user = points_result.get("success") and points_result.get("data") is not None
    balance_points = 0
    fundle_registered = False
    customer_type = "new"  # Default to new customer
    
    # Also check our imported Fundle customer list (from Excel)
    imported_fundle_customer = await db.fundle_customers.find_one({"phone_10": mobile_10})
    if imported_fundle_customer:
        is_existing_fundle_user = True
        logger.info(f"User {mobile_10} found in imported Fundle customer list")
    
    if is_existing_fundle_user:
        # EXISTING CUSTOMER - Already registered in Fundle before our system
        logger.info(f"User {mobile_10} is an EXISTING Fundle customer, adding to local DB")
        balance_points = points_result["data"].get("balance_points", 0) if points_result.get("data") else 0
        fundle_registered = True
        customer_type = "existing"  # Mark as existing Fundle customer
    else:
        # NEW CUSTOMER - Register with Fundle
        logger.info(f"Registering NEW customer {mobile_10} with Fundle")
        reg_result = await tagnpay_client.register_customer(
            mobile_number=mobile_10,
            name=profile_name or "Customer",
            pan_number="",  # Not required for WhatsApp registration
            source="WhatsApp"
        )
        logger.info(f"Fundle registration result for {mobile_10}: {reg_result}")

        if reg_result.get("success"):
            fundle_registered = True
            customer_type = "new"
            points_result = await tagnpay_client.get_customer_points(mobile_10)
            if points_result.get("success") and points_result.get("data"):
                balance_points = points_result["data"].get("balance_points", 0)
        else:
            logger.warning(f"Fundle registration failed for {mobile_10}, proceeding with local registration. Error: {reg_result.get('error')}")
            fundle_registered = False
            customer_type = "new"

    # Create user in our DB. kyc_status now represents "registered locally in CP67"
    # — independent of whether the Fundle/TagnPay sync succeeded. That lets users
    # show as "Registered" in the admin report even when TagnPay returns an error
    # (e.g. unusual phone format). We track Fundle sync status separately.
    new_user = UserData(
        phone=phone,
        name=profile_name or "Customer",
        kyc_status=True,  # local registration is complete the moment they engage
        fundle_registered=fundle_registered,
        customer_type=customer_type,
        registration_time=datetime.now(timezone.utc).isoformat(),
        first_touch_source=source_code or "SRC_WHATSAPP",  # never leave blank
        first_touch_qr=qr_data["qr_code_id"] if qr_data else None,
        first_touch_message="QR Scan Registration" if qr_data else "WhatsApp Direct",
        balance_points=balance_points
    )
    await db.users.insert_one(new_user.model_dump())

    # Staff attribution → pending registration incentive (activates when first bill approved)
    if attributing_staff:
        try:
            mobile_10 = phone[2:] if phone.startswith("91") and len(phone) == 12 else phone
            await create_registration_incentive(mobile_10, attributing_staff)
            logger.info(f"Staff registration incentive created: staff={attributing_staff.get('staff_code')} customer={mobile_10}")
        except Exception as e:
            logger.error(f"Failed to create staff registration incentive: {e}")

    # Point 26: Registration Coupon issuance
    # If a coupon exists for this registration source (RWA / OFFICE etc.),
    # atomically claim one and deliver it to the customer over WhatsApp.
    issued_coupon = None
    if customer_type == "new" and source_code and source_code.upper() not in ("SRC_WHATSAPP", "SRC_PARKING"):
        try:
            issued_coupon = await issue_coupon_for_registration(phone, source_code)
            if issued_coupon:
                logger.info(f"Issued coupon {issued_coupon['code']} to {phone} from {source_code} inventory")
        except Exception as e:
            logger.error(f"Coupon issuance failed for {phone} / {source_code}: {e}")

    # Update QR analytics - only count NEW customers as registrations
    if qr_data:
        if customer_type == "new":
            # New customer - increment both scans and registrations
            await db.qr_analytics.update_one(
                {"qr_code_id": qr_data["qr_code_id"]},
                {"$inc": {"scans": 1, "registrations": 1}},
                upsert=True
            )
        else:
            # Existing Fundle customer - only increment scans, not registrations
            await db.qr_analytics.update_one(
                {"qr_code_id": qr_data["qr_code_id"]},
                {"$inc": {"scans": 1, "existing_customers": 1}},
                upsert=True
            )
    
    # EXACT Registration Success Message (per revised flow document)
    welcome_msg = f"""Hi {profile_name or 'there'}! Congratulations on joining Homeland Advantage.

You are now part of CP67 Mall's exclusive loyalty program, and your 1000 joining bonus points have been credited.

Enjoy exclusive rewards, special benefits, and personalized offers every time you shop.

Shop - Earn - Redeem - Repeat"""

    # Point 26: Append issued coupon details (RWA/Office registration bonus).
    if issued_coupon:
        expiry_txt = issued_coupon.get("expiry") or ""
        welcome_msg += (
            "\n\n🎁 Welcome Coupon Unlocked!\n"
            f"Brand: {issued_coupon.get('brand_name', '')}\n"
            f"Code:  {issued_coupon.get('code', '')}\n"
            f"Value: ₹{int(issued_coupon.get('value') or 0)}\n"
            + (f"Valid till: {expiry_txt}" if expiry_txt else "")
        )
    
    menu_options = [
        {"id": "upload_bill", "title": "Upload Bill", "description": "Upload your shopping bill to earn points"},
        {"id": "redeem_points", "title": "Redeem Points", "description": "Redeem points at participating brands"},
        {"id": "my_points", "title": "My Points", "description": "Check your loyalty points balance"},
        {"id": "customer_support", "title": "Help / Support", "description": "Contact our support team"},
        {"id": "know_more", "title": "Know More", "description": "Participating brands & T&C"}
    ]
    
    # Log outbound
    outbound_log = WhatsAppLog(
        user_id=new_user.id,
        user_phone=phone,
        direction="outbound",
        message_type="interactive",
        content=welcome_msg
    )
    await db.whatsapp_logs.insert_one(outbound_log.model_dump())
    
    await send_whatsapp_list(phone, welcome_msg, menu_options, header_text="Homeland Advantage", button_text="Menu")
    return new_user


async def process_parking_registration(phone: str, profile_name: str, source_code: str, qr_data: dict, background_tasks: BackgroundTasks):
    """Handle new user registration from Parking QR - NO bonus points, get free parking coupon instead"""
    mobile_10 = phone[2:] if phone.startswith("91") and len(phone) == 12 else phone
    
    try:
        # Register with Fundle (without bonus points message)
        fundle_registered = False
        balance_points = 0
        
        # Check if user exists in Fundle API
        points_result = await tagnpay_client.get_customer_points(mobile_10)
        is_existing_fundle_user = points_result.get("success") and points_result.get("data") is not None
        
        # Also check imported list
        imported_fundle_customer = await db.fundle_customers.find_one({"phone_10": mobile_10})
        if imported_fundle_customer:
            is_existing_fundle_user = True
        
        # EXISTING Fundle customer should NOT get free parking
        if is_existing_fundle_user:
            logger.info(f"Existing Fundle customer {mobile_10} tried parking QR - denying free parking")
            existing_msg = f"""Hi {profile_name or 'there'}!

You are already registered with Homeland Advantage.

Free parking is available only for new members who register via the parking QR code.

Use the menu below to explore your rewards!"""
            menu_options = [
                {"id": "upload_bill", "title": "Upload Bill", "description": "Upload your shopping bill to earn points"},
                {"id": "my_points", "title": "My Points", "description": "Check your loyalty points balance"},
                {"id": "redeem_points", "title": "Redeem Points", "description": "Redeem points at participating brands"},
            ]
            outbound_log = WhatsAppLog(user_phone=phone, direction="outbound", message_type="interactive", content=existing_msg)
            await db.whatsapp_logs.insert_one(outbound_log.model_dump())
            await send_whatsapp_list(phone, existing_msg, menu_options, header_text="Homeland Advantage", button_text="Menu")
            
            # Still save them in local DB if not already present
            local_user = await db.users.find_one({"phone": phone})
            if not local_user:
                balance_points = points_result["data"].get("balance_points", 0) if points_result.get("data") else 0
                new_user = UserData(
                    phone=phone,
                    name=profile_name or "Customer",
                    kyc_status=True,
                    customer_type="existing",
                    registration_time=datetime.now(timezone.utc).isoformat(),
                    first_touch_source=source_code,
                    first_touch_qr=qr_data["qr_code_id"] if qr_data else None,
                    first_touch_message="Parking QR - Existing User",
                    balance_points=balance_points
                )
                await db.users.insert_one(new_user.model_dump())
            return
        
        # NEW USER - Register with Fundle using PK001 location code
        reg_result = await tagnpay_client.register_customer(
            mobile_number=mobile_10,
            name=profile_name or "Customer",
            pan_number="",
            source="WhatsApp_Parking",
            location_code="PK001"
        )
        if reg_result.get("success"):
            fundle_registered = True
        
        # Create user in DB
        # Point 44 (Feb 2026): parking coupon is NO LONGER issued on
        # registration alone. The customer must upload at least ONE bill
        # that's approved, then _maybe_issue_pending_parking_coupon fires
        # and creates the actual PARK-XXXX coupon. Mark the user with
        # parking_coupon_pending so the bill-approve hook knows to issue.
        new_user = UserData(
            phone=phone,
            name=profile_name or "Customer",
            kyc_status=True,
            fundle_registered=fundle_registered,
            customer_type="new",
            registration_time=datetime.now(timezone.utc).isoformat(),
            first_touch_source=source_code or "SRC_PARKING",
            first_touch_qr=qr_data["qr_code_id"] if qr_data else None,
            first_touch_message="Parking QR Registration",
            balance_points=0
        )
        user_doc = new_user.model_dump()
        user_doc["parking_coupon_pending"] = True
        user_doc["parking_coupon_source"] = source_code or "SRC_PARKING"
        # 60-day window from registration to upload the qualifying bill.
        _pending_expiry = datetime.now(timezone.utc) + timedelta(days=60)
        user_doc["parking_coupon_pending_expires_at"] = _pending_expiry.isoformat()
        await db.users.insert_one(user_doc)
        
        # Update QR analytics
        if qr_data:
            await db.qr_analytics.update_one(
                {"qr_code_id": qr_data["qr_code_id"]},
                {"$inc": {"scans": 1, "registrations": 1}},
                upsert=True
            )
        
        # Send welcome message asking user to upload a bill to unlock parking
        welcome_msg = (
            f"Hi {profile_name or 'there'}! Welcome to Homeland Advantage, CP67 Mall's exclusive loyalty program.\n\n"
            "Your FREE Parking Coupon is *reserved* for you.\n\n"
            "*How to claim it:* Upload any purchase bill from a CP67 store. Once verified, "
            "your parking coupon QR will be sent to you on WhatsApp.\n\n"
            "Shop, Earn and Redeem rewards every time you visit CP67 Mall!"
        )
        menu_options = [
            {"id": "upload_bill", "title": "Upload Bill", "description": "Upload your bill to unlock parking"},
            {"id": "my_points", "title": "My Points", "description": "Check your loyalty points balance"},
            {"id": "redeem_points", "title": "Redeem Points", "description": "Redeem points at participating brands"},
        ]
        outbound_log = WhatsAppLog(
            user_id=new_user.id,
            user_phone=phone,
            direction="outbound",
            message_type="interactive",
            content=welcome_msg,
        )
        await db.whatsapp_logs.insert_one(outbound_log.model_dump())
        await send_whatsapp_list(phone, welcome_msg, menu_options, header_text="Homeland Advantage", button_text="Menu")
        logger.info(f"Parking QR registration: {phone} — coupon deferred until first verified bill")
        return new_user
    except Exception as e:
        logger.error(f"process_parking_registration failed for {phone}: {e}", exc_info=True)


async def _maybe_issue_pending_parking_coupon(user_phone: str) -> Optional[str]:
    """Point 44 (Feb 2026): if the user registered via a parking QR and has
    a pending parking coupon flag, issue the PARK-XXXX coupon NOW that their
    first bill has been verified. Idempotent — only fires once."""
    if not user_phone:
        return None
    phone = user_phone if user_phone.startswith("91") else f"91{user_phone[-10:]}"
    try:
        user = await db.users.find_one(
            {"phone": phone, "parking_coupon_pending": True},
            {"_id": 0, "id": 1, "name": 1, "parking_coupon_source": 1, "parking_coupon_pending_expires_at": 1},
        )
        if not user:
            return None
        # Expiry check — if the 60-day window elapsed, silently clear the flag.
        try:
            _exp = user.get("parking_coupon_pending_expires_at")
            if _exp and datetime.fromisoformat(_exp) < datetime.now(timezone.utc):
                await db.users.update_one(
                    {"phone": phone},
                    {"$unset": {"parking_coupon_pending": "", "parking_coupon_source": "", "parking_coupon_pending_expires_at": ""}},
                )
                logger.info(f"Parking coupon window expired for {phone}; flag cleared")
                return None
        except Exception:
            pass

        # Atomic clear-and-issue: if another request already flipped the flag
        # we skip so no user ever gets two coupons.
        clear_res = await db.users.update_one(
            {"phone": phone, "parking_coupon_pending": True},
            {"$unset": {"parking_coupon_pending": "", "parking_coupon_source": "", "parking_coupon_pending_expires_at": ""}},
        )
        if clear_res.modified_count == 0:
            return None

        coupon_code = f"PARK-{uuid.uuid4().hex[:8].upper()}"
        expiry_time = datetime.now(timezone.utc) + timedelta(hours=24)
        parking_coupon = {
            "coupon_code": coupon_code,
            "user_phone": phone,
            "user_name": user.get("name") or "Customer",
            "source": user.get("parking_coupon_source") or "SRC_PARKING",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "expires_at": expiry_time.isoformat(),
            "status": "active",
            "used": False,
            "issued_after_bill_verification": True,
        }
        await db.parking_coupons.insert_one(parking_coupon)
        logger.info(f"Parking coupon issued post-bill-verification: {coupon_code} for {phone}")

        # Send QR image on WhatsApp
        try:
            qr_image = await generate_parking_qr_image(coupon_code)
            expiry_str = expiry_time.strftime("%d %b %Y, %I:%M %p")
            caption = (
                f"Congratulations {user.get('name') or 'there'}!\n\n"
                "Your bill has been verified. Here is your FREE Parking Coupon:\n\n"
                f"*Coupon Code:* {coupon_code}\n"
                f"*Valid Until:* {expiry_str}\n\n"
                "Show this QR at the parking exit counter."
            )
            if qr_image:
                await send_whatsapp_image(phone, qr_image, caption)
            else:
                await send_whatsapp_text(phone, caption)
        except Exception as _e:
            logger.warning(f"Parking QR delivery failed for {phone} ({coupon_code}): {_e}")

        return coupon_code
    except Exception as e:
        logger.error(f"_maybe_issue_pending_parking_coupon failed for {phone}: {e}", exc_info=True)
        return None



async def process_bill_image(phone: str, user: dict, image_url: str, background_tasks: BackgroundTasks):
    """Process uploaded bill image with OCR and TagnPay API"""
    mobile_10 = phone[2:] if phone.startswith("91") and len(phone) == 12 else phone
    logger.info(f"Processing bill image for phone {phone}, image_url: {image_url}")
    
    try:
        # First send acknowledgment (per revised flow document)
        ack_msg = """Thank you for uploading your bill!
We're scanning your bill now. Please wait a moment..."""
        await send_whatsapp_text(phone, ack_msg)
        
        # Download image from Karix URL if needed or extract base64 directly
        image_base64 = None
        
        # Check if image_url is already base64 encoded
        if image_url and image_url.startswith("base64:"):
            image_base64 = image_url[7:]  # Remove "base64:" prefix
            logger.info(f"Using direct base64 image data, size: {len(image_base64)} chars")
        elif image_url and image_url.startswith("http"):
            logger.info(f"Downloading image from URL: {image_url}")
            async with httpx.AsyncClient(timeout=30.0) as client:
                # Try with Karix authentication headers first
                headers = {
                    "Authentication": f"Bearer {KARIX_API_KEY}",
                    "Authorization": f"Bearer {KARIX_API_KEY}"
                }
                img_response = await client.get(image_url, headers=headers)
                logger.info(f"Image download response (with auth): {img_response.status_code}")
                
                # If auth fails, try without authentication
                if img_response.status_code != 200:
                    logger.info("Trying image download without auth...")
                    img_response = await client.get(image_url)
                    logger.info(f"Image download response (no auth): {img_response.status_code}")
                
                if img_response.status_code == 200:
                    image_base64 = base64.b64encode(img_response.content).decode()
                    logger.info(f"Image downloaded successfully, size: {len(image_base64)} chars")
                else:
                    logger.error(f"Failed to download image: {img_response.status_code} - {img_response.text[:200]}")
        else:
            logger.warning(f"Invalid or missing image URL: {image_url}")
        
        if not image_base64:
            logger.error("No image data available — inserting stub bill for admin review")

            # Point 19 fix: save a placeholder bill so admin can see it in the panel
            # and manually review / reprocess. Previously this branch silently
            # returned, leaving nothing in the admin panel and confusing the customer.
            try:
                stub_bill = BillData(
                    user_id=user["id"],
                    user_phone=phone,
                    store_name=None,
                    bill_no=None,
                    bill_date=None,
                    amount=None,
                    status="manual_review",
                    image_url=image_url or None,  # keep original Karix URL so admin can retry download
                    rejection_reason="Image could not be downloaded from WhatsApp — manual review",
                )
                await insert_bill_and_alert(stub_bill.model_dump())
            except Exception as _e:
                logger.error(f"Failed to insert stub bill for {phone}: {_e}")

            unclear_msg = """Your uploaded bill image is unclear for automatic processing.

No worries — it has been submitted for manual review. Verification will be completed within 24-48 hours, and points will be credited after approval.

Thank you for being a valued Homeland Advantage member."""

            buttons = [
                {"id": "upload_bill", "title": "Upload Bill"},
                {"id": "redeem_points", "title": "Redeem Points"}
            ]
            await send_whatsapp_buttons(phone, unclear_msg, buttons)
            return
        
        # Check for duplicate (by image hash) — timeout-guarded so a slow index
        # doesn't blow up the whole pipeline (previously caused Atlas
        # "operation exceeded time limit" errors that killed the bill).
        image_hash = hashlib.md5(base64.b64decode(image_base64)).hexdigest()
        existing_bill = None
        try:
            existing_bill = await db.bills.find_one(
                {"image_hash": image_hash, "status": {"$ne": "rejected"}},
                max_time_ms=5000,
            )
        except Exception as _e:
            logger.warning(f"image_hash dedup lookup failed (skipping): {_e}")
            existing_bill = None
        
        if existing_bill:
            # Get current balance
            points_result = await tagnpay_client.get_customer_points(mobile_10)
            balance = 0
            if points_result.get("success") and points_result.get("data"):
                balance = int(points_result["data"].get("balance_points", 0))
            
            # Duplicate Bill Message
            duplicate_msg = f"""Our system shows that this bill has already been processed earlier and rewards have been issued.

Your Current Points Balance: {balance}

Keep shopping at CP67 Mall to earn more points & enjoy exclusive rewards."""
            
            buttons = [
                {"id": "upload_bill", "title": "Upload Bill"},
                {"id": "my_points", "title": "My Points"}
            ]
            await send_whatsapp_buttons(phone, duplicate_msg, buttons)
            return
        
        # OCR Analysis
        ocr_result = await analyze_bill_image(image_base64)
        
        if not ocr_result.get("success"):
            # OCR failed - manual review
            unclear_msg = """Your uploaded bill image is unclear for automatic processing.

No worries — it has been submitted for manual review. Verification will be completed within 24-48 hours, and points will be credited after approval.

Thank you for being a valued Homeland Advantage member."""
            
            # Save for manual review
            bill_data = BillData(
                user_id=user["id"],
                user_phone=phone,
                status="manual_review",
                rejection_reason="OCR processing failed",
                image_url=f"data:image/jpeg;base64,{image_base64}",
                image_hash=image_hash
            )
            await insert_bill_and_alert(bill_data.model_dump())
            
            buttons = [
                {"id": "upload_bill", "title": "Upload Bill"},
                {"id": "my_points", "title": "Redeem Points"}
            ]
            await send_whatsapp_buttons(phone, unclear_msg, buttons)
            return
        
        ocr_data = ocr_result.get("data", {})
        store_name = ocr_data.get("store_name", "Unknown Store")
        bill_no = ocr_data.get("bill_no", f"BILL{datetime.now().strftime('%Y%m%d%H%M%S')}")
        bill_date = ocr_data.get("bill_date", datetime.now().strftime("%Y-%m-%d"))
        amount = float(ocr_data.get("amount", 0) or 0)
        tax = ocr_data.get("tax", 0)
        items = ocr_data.get("items", [])
        confidence = ocr_data.get("confidence_score", 0)
        is_valid = ocr_data.get("is_valid_bill", False)
        tampering = ocr_data.get("tampering_detected", False)
        image_quality = ocr_data.get("image_quality", "fair")
        extraction_notes = ocr_data.get("extraction_notes", "")
        raw_text = ocr_data.get("raw_text", "")
        customer_mobile = ocr_data.get("customer_mobile", None)

        # Points always go to the uploader's WhatsApp number. If the invoice has a
        # different customer mobile printed on it, we flag a mismatch and route the
        # bill to admin review (handled below after CP67/age/duplicate checks).
        points_mobile = mobile_10
        points_mobile_source = "whatsapp"

        invoice_mobile_clean = None
        if customer_mobile:
            digits_only = "".join(ch for ch in str(customer_mobile) if ch.isdigit())
            if len(digits_only) >= 10:
                invoice_mobile_clean = digits_only[-10:]
        invoice_mobile_mismatch = bool(invoice_mobile_clean and invoice_mobile_clean != mobile_10)
        if invoice_mobile_mismatch:
            logger.info(
                f"Invoice mobile mismatch: invoice={invoice_mobile_clean}, uploader={mobile_10}"
            )
        
        # CHECK: Bill date older than 15 days - Reject immediately
        try:
            bill_date_parsed = datetime.strptime(bill_date, "%Y-%m-%d")
            days_old = (datetime.now() - bill_date_parsed).days
            
            if days_old > 15:
                # Bill is older than 15 days - reject (per revised flow document)
                old_bill_msg = f"""Bill Cannot Be Processed

Unfortunately, this bill dated {bill_date} is more than 15 days old and cannot be processed for rewards.

Policy: Bills must be uploaded within 15 days of purchase to earn points.

We appreciate your understanding! Please upload your recent bills to continue earning rewards."""
                
                # Save as rejected
                bill_data = BillData(
                    user_id=user["id"],
                    user_phone=phone,
                    store_name=store_name,
                    bill_no=bill_no,
                    bill_date=bill_date,
                    amount=amount,
                    status="rejected",
                    rejection_reason=f"Bill is {days_old} days old (limit: 15 days)",
                    image_url=f"data:image/jpeg;base64,{image_base64}",
                    image_hash=image_hash,
                    ocr_confidence=confidence,
                    ocr_raw_data=ocr_data
                )
                await insert_bill_and_alert(bill_data.model_dump())
                
                buttons = [
                    {"id": "know_more", "title": "Know More"},
                    {"id": "upload_bill", "title": "Upload Valid Bill"}
                ]
                await send_whatsapp_buttons(phone, old_bill_msg, buttons)
                return
        except Exception as date_err:
            logger.warning(f"Could not parse bill date for 15-day check: {bill_date}, error: {date_err}")
        
        # Check duplicate by bill number + store (after OCR extraction)
        if bill_no and store_name and bill_no != f"BILL{datetime.now().strftime('%Y%m%d%H%M%S')}":
            is_duplicate_by_bill_no = await check_duplicate_bill(image_hash, bill_no, store_name)
            if is_duplicate_by_bill_no:
                # Get current balance
                points_result = await tagnpay_client.get_customer_points(mobile_10)
                balance = 0
                if points_result.get("success") and points_result.get("data"):
                    balance = int(points_result["data"].get("balance_points", 0))
                
                # Duplicate Bill Message
                duplicate_msg = f"""Our system shows that this bill has already been processed earlier and rewards have been issued.

Your Current Points Balance: {balance}

Keep shopping at CP67 Mall to earn more points & enjoy exclusive rewards."""
                
                # Save duplicate record for reference
                bill_data = BillData(
                    user_id=user["id"],
                    user_phone=phone,
                    store_name=store_name,
                    bill_no=bill_no,
                    bill_date=bill_date,
                    amount=amount,
                    status="duplicate",
                    image_url=f"data:image/jpeg;base64,{image_base64}",
                    image_hash=image_hash,
                    ocr_confidence=confidence,
                    ocr_raw_data=ocr_data,
                    rejection_reason="Duplicate bill detected (same bill number and store)"
                )
                await insert_bill_and_alert(bill_data.model_dump())
                
                buttons = [
                    {"id": "upload_bill", "title": "Upload Bill"},
                    {"id": "my_points", "title": "My Points"}
                ]
                await send_whatsapp_buttons(phone, duplicate_msg, buttons)
                return
        
        # FIRST: Show ALL extracted bill details with items
        items_text = ""
        if items and len(items) > 0:
            items_text = "\n *Items:*\n"
            for i, item in enumerate(items[:10], 1):  # Limit to 10 items
                if isinstance(item, str):
                    items_text += f"  {i}. {item}\n"
                elif isinstance(item, dict):
                    item_name = item.get('name', item.get('description', str(item)))
                    item_qty = item.get('qty', item.get('quantity', ''))
                    item_price = item.get('price', item.get('amount', ''))
                    items_text += f"  {i}. {item_name}"
                    if item_qty:
                        items_text += f" (Qty: {item_qty})"
                    if item_price:
                        items_text += f" - ₹{item_price}"
                    items_text += "\n"
        
        tax_text = f"\n Tax: ₹{tax}" if tax else ""
        
        bill_details_msg = f""" *Bill Scan Results*

 *Store:* {store_name}
 *Bill No:* {bill_no}
 *Date:* {bill_date}
 *Amount:* ₹{amount:.2f}{tax_text}
{items_text}
 *Confidence:* {confidence*100:.0f}%

Processing your rewards... ⏳"""
        
        await send_whatsapp_text(phone, bill_details_msg)
        
        # Small delay for better UX
        import asyncio
        await asyncio.sleep(1)
        
        # CHECK FOR CP67 - Only process bills from CP67 Mall
        # Check if CP67 is mentioned in store name, raw text, or any extracted data
        contains_cp67_ocr = ocr_data.get("contains_cp67", False)
        bill_text_combined = f"{store_name} {bill_no} {extraction_notes} {raw_text} {' '.join(str(i) for i in items)}".lower()
        is_cp67_bill = contains_cp67_ocr or "cp67" in bill_text_combined or "cp 67" in bill_text_combined or "cp-67" in bill_text_combined
        
        logger.info(f"CP67 check - OCR flag: {contains_cp67_ocr}, text search: {'cp67' in bill_text_combined}, result: {is_cp67_bill}")
        
        if not is_cp67_bill:
            # NOT a CP67 bill - reject (per revised flow document)
            rejection_reason = "Bill is not from CP67 Mall. Only CP67 Mall bills are eligible for rewards."
            
            reject_msg = """Bill Cannot Be Processed

This bill is not eligible under the Homeland Advantage program.

Only bills from shops inside CP67 Mall are eligible for rewards.

Please upload a valid CP67 Mall bill to earn points."""
            
            # Save as rejected/pending for backend review
            bill_data = BillData(
                user_id=user["id"],
                user_phone=phone,
                store_name=store_name,
                bill_no=bill_no,
                bill_date=bill_date,
                amount=amount,
                status="rejected",
                rejection_reason=rejection_reason,
                image_url=f"data:image/jpeg;base64,{image_base64}",
                image_hash=image_hash,
                ocr_confidence=confidence,
                ocr_raw_data=ocr_data
            )
            await insert_bill_and_alert(bill_data.model_dump())
            
            # Call TagnPay pending-bill API to log rejection
            try:
                token = await tagnpay_client.get_token(mobile_10)
                if token:
                    async with httpx.AsyncClient(timeout=30.0) as client:
                        await client.post(
                            f"{tagnpay_client.base_url}/api/pending-bill/",
                            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                            json={
                                "mobile_number": mobile_10,
                                "bill_number": bill_no,
                                "bill_amount": str(amount),
                                "bill_date": bill_date,
                                "store_name": store_name,
                                "status": "rejected",
                                "rejection_reason": rejection_reason
                            }
                        )
                        logger.info(f"Logged rejected bill to TagnPay for {mobile_10}")
            except Exception as e:
                logger.error(f"Failed to log rejected bill to TagnPay: {e}")
            
            buttons = [
                {"id": "know_more", "title": "Know More"},
                {"id": "upload_bill", "title": "Upload CP67 Bill"}
            ]
            await send_whatsapp_buttons(phone, reject_msg, buttons)
            return
        
        # Check if image is unclear or tampered
        if image_quality == "poor" or confidence < 0.5 or tampering or not is_valid:
            unclear_msg = """Your uploaded bill image is unclear for automatic processing.

No worries — it has been submitted for manual review. Verification will be completed within 24-48 hours, and points will be credited after approval.

Thank you for being a valued Homeland Advantage member."""
            
            # Save for manual review
            bill_data = BillData(
                user_id=user["id"],
                user_phone=phone,
                store_name=store_name,
                bill_no=bill_no,
                bill_date=bill_date,
                amount=amount,
                status="manual_review",
                image_url=f"data:image/jpeg;base64,{image_base64}",
                image_hash=image_hash,
                ocr_confidence=confidence,
                ocr_raw_data=ocr_data
            )
            await insert_bill_and_alert(bill_data.model_dump())
            
            buttons = [
                {"id": "upload_bill", "title": "Upload Bill"},
                {"id": "redeem_points", "title": "Redeem Points"}
            ]
            await send_whatsapp_buttons(phone, unclear_msg, buttons)
            return

        # CHECK: Mobile number on invoice does not match WhatsApp uploader → admin review
        if invoice_mobile_mismatch:
            mismatch_msg = f"""Bill Received - Under Review

Thank you for shopping at {store_name}!

Bill No: {bill_no}
Date: {bill_date}
Amount: Rs {amount:,.0f}

The mobile number printed on this invoice does not match your WhatsApp number, so our team will review it before crediting points. You will be notified within 24-48 hours.

Thank you for your patience!"""

            bill_data = BillData(
                user_id=user["id"],
                user_phone=phone,
                store_name=store_name,
                bill_no=bill_no,
                bill_date=bill_date,
                amount=amount,
                status="pending_review",
                rejection_reason="Mob No not matched with Invoice",
                image_url=f"data:image/jpeg;base64,{image_base64}",
                image_hash=image_hash,
                ocr_confidence=confidence,
                ocr_raw_data=ocr_data
            )
            doc = bill_data.model_dump()
            doc["invoice_mobile"] = invoice_mobile_clean
            await insert_bill_and_alert(doc)

            admin_alert_msg = f""" *Mobile Mismatch Alert*

Invoice mobile does not match WhatsApp sender.

 Store: {store_name}
 Bill No: {bill_no}
 Amount: Rs {amount:,.0f}
 Invoice Mobile: {invoice_mobile_clean}
 WhatsApp Sender: {mobile_10}

Please review in the admin dashboard."""
            background_tasks.add_task(send_whatsapp_text, ADMIN_PHONE, admin_alert_msg)

            buttons = [
                {"id": "upload_bill", "title": "Upload Another Bill"},
                {"id": "my_points", "title": "My Points"}
            ]
            await send_whatsapp_buttons(phone, mismatch_msg, buttons)
            return


        # CHECK: Bill amount > 30000 - Send to pending for manual review
        if amount > 30000:
            high_amount_msg = f"""Bill Received - Under Review

Thank you for shopping at {store_name}!

Bill No: {bill_no}
Date: {bill_date}
Amount: Rs {amount:.0f}

Once verified, your Points will be credited to your account.

Happy shopping!"""
            
            # Save as pending_review
            bill_data = BillData(
                user_id=user["id"],
                user_phone=phone,
                store_name=store_name,
                bill_no=bill_no,
                bill_date=bill_date,
                amount=amount,
                status="pending_review",
                rejection_reason=f"High value bill (₹{amount:.0f}) - requires manual verification",
                image_url=f"data:image/jpeg;base64,{image_base64}",
                image_hash=image_hash,
                ocr_confidence=confidence,
                ocr_raw_data=ocr_data,
                points_mobile=points_mobile,
                points_mobile_source=points_mobile_source
            )
            await insert_bill_and_alert(bill_data.model_dump())
            
            # Send admin notification for high value bill
            admin_alert_msg = f""" *High Value Bill Alert*

A bill over ₹30,000 has been submitted for review.

 Store: {store_name}
 Bill No: {bill_no}
 Amount: ₹{amount:.0f}
 User: {phone}

Please review in the admin dashboard."""
            
            background_tasks.add_task(send_whatsapp_text, ADMIN_PHONE, admin_alert_msg)
            
            buttons = [
                {"id": "upload_bill", "title": "Upload Another Bill"},
                {"id": "my_points", "title": "My Points"}
            ]
            await send_whatsapp_buttons(phone, high_amount_msg, buttons)
            return
        
        # CHECK: Bill amount exceeds Brand ATV - Send to pending for review
        brand_atv = None
        brand_config = await db.brands.find_one(
            {"brand_name": {"$regex": f"^{store_name}$", "$options": "i"}},
            {"_id": 0, "atv": 1, "brand_name": 1}
        )
        if brand_config and brand_config.get("atv", 0) > 0:
            brand_atv = brand_config["atv"]
            if amount > brand_atv:
                atv_exceed_msg = f"""Bill Received - Under Review

Thank you for shopping at {store_name}!

Bill No: {bill_no}
Date: {bill_date}
Amount: Rs.{amount:,.0f}

Your bill is under review for validation by our team. It will be reviewed within 24-48 hours and points will be credited once approved.

Thank you for your patience!"""
                
                # Save as pending_review
                bill_data = BillData(
                    user_id=user["id"],
                    user_phone=phone,
                    store_name=store_name,
                    bill_no=bill_no,
                    bill_date=bill_date,
                    amount=amount,
                    status="pending_review",
                    rejection_reason=f"Bill amount (₹{amount:,.0f}) exceeds brand ATV (₹{brand_atv:,.0f})",
                    image_url=f"data:image/jpeg;base64,{image_base64}",
                    image_hash=image_hash,
                    ocr_confidence=confidence,
                    ocr_raw_data=ocr_data,
                    points_mobile=points_mobile,
                    points_mobile_source=points_mobile_source
                )
                await insert_bill_and_alert(bill_data.model_dump())
                
                # Send admin notification
                admin_alert_msg = f""" *ATV Exceeded Alert*

A bill exceeding brand ATV has been submitted.

 Store: {store_name}
 Bill No: {bill_no}
 Amount: ₹{amount:,.0f}
 Brand ATV: ₹{brand_atv:,.0f}
 User: {phone}

Please review in the admin dashboard."""
                
                background_tasks.add_task(send_whatsapp_text, ADMIN_PHONE, admin_alert_msg)
                logger.info(f"Bill {bill_no} flagged: Amount ₹{amount} exceeds {store_name} ATV ₹{brand_atv}")
                
                buttons = [
                    {"id": "upload_bill", "title": "Upload Another Bill"},
                    {"id": "my_points", "title": "Check Points"}
                ]
                await send_whatsapp_buttons(phone, atv_exceed_msg, buttons)
                return
        
        # Call TagnPay earn-points API with appropriate mobile number
        earn_result = await tagnpay_client.earn_points(
            mobile_number=points_mobile,  # Use mobile from bill if available
            bill_amount=amount,
            bill_number=bill_no,
            bill_date=bill_date,
            store_name=store_name,
            bill_image_base64=image_base64
        )
        
        logger.info(f"TagnPay earn-points result for {points_mobile} (source: {points_mobile_source}): {earn_result}")
        
        points_earned = 0
        total_balance = 0
        tagnpay_error = None
        bill_status = "auto_approved"
        
        if earn_result.get("success") and earn_result.get("data"):
            data = earn_result["data"]
            points_earned = data.get("earned_points", 0)
            total_balance = data.get("total_points", 0)
            message = data.get("message", "")
            
            # Check if brand doesn't match (TagnPay returns success but with 0 points and error message)
            if points_earned == 0 and ("Brand" in message or "brand" in message or "doesnt match" in message.lower()):
                tagnpay_error = f"Brand '{store_name}' not found in Fundle master"
                bill_status = "pending_review"
                logger.warning(f"TagnPay brand mismatch for {store_name}: {message}")
            # TEMPORARILY: Treat 30-day errors as auto_approved for testing (TagnPay still rejects but we log it)
            elif points_earned == 0 and "older than 30 days" in message.lower():
                tagnpay_error = "Bill date older than 30 days (Fundle rejected)"
                bill_status = "auto_approved"  # Mark as approved for testing purposes
                logger.warning(f"TagnPay 30-day rejection (bypassed for testing): {message}")
            elif points_earned == 0 and message:
                # Some other error with 0 points
                tagnpay_error = message[:100] if message else "Unknown TagnPay error"
                bill_status = "pending_review"
                logger.warning(f"TagnPay error with 0 points: {message}")
        else:
            # TagnPay API completely failed
            error_text = str(earn_result.get("error", ""))
            if "Brand" in error_text or "brand" in error_text:
                tagnpay_error = f"Brand '{store_name}' not found in Fundle master"
                bill_status = "pending_review"
            # TEMPORARILY: Treat 30-day errors as auto_approved for testing
            elif "older than 30 days" in error_text:
                tagnpay_error = "Bill date older than 30 days (Fundle rejected)"
                bill_status = "auto_approved"  # Mark as approved for testing purposes
                logger.warning(f"TagnPay 30-day rejection (bypassed for testing): {error_text}")
            else:
                tagnpay_error = error_text[:200] if error_text else "Unknown TagnPay error"
                bill_status = "pending_review"
            
            logger.warning(f"TagnPay earn-points failed: {tagnpay_error}")
        
        # Get current balance from API
        points_result = await tagnpay_client.get_customer_points(mobile_10)
        if points_result.get("success") and points_result.get("data"):
            total_balance = int(points_result["data"].get("balance_points", 0))
        
        # ------- Point 12: Fundle rejected → force-credit fallback if admin enabled -------
        force_credit_fallback_applied = False
        if points_earned == 0 and tagnpay_error and bill_status == "pending_review":
            settings = await _get_app_settings()
            if settings.get("auto_force_credit_on_fundle_reject"):
                err_low = (tagnpay_error or "").lower()
                if "brand" in err_low or "match" in err_low or "not found" in err_low or "0 points" in err_low:
                    auto = await _compute_auto_points(amount, store_name)
                    fc_points = int(auto.get("points") or 0)
                    if fc_points > 0:
                        points_earned = fc_points
                        bill_status = "auto_approved"
                        force_credit_fallback_applied = True
                        logger.info(f"WhatsApp bill auto force-credited: +{fc_points} pts for {phone} (Fundle rejected: {tagnpay_error})")
        
        # ------- Campaign Engine: apply active multipliers/bonuses -------
        campaign_bonus_points = 0
        applied_campaigns = []
        if points_earned > 0:
            is_first = await db.bills.count_documents({"user_id": user["id"], "status": {"$in": ["auto_approved", "approved"]}}) == 0
            camp = await apply_campaign_bonus(
                bill_amount=amount,
                base_points=points_earned,
                store_name=store_name,
                is_first_bill=is_first,
            )
            campaign_bonus_points = camp["bonus_points"]
            applied_campaigns = camp["applied_campaigns"]
            points_earned = camp["final_points"]
            if campaign_bonus_points > 0:
                logger.info(f"Campaign bonus applied for {phone}: +{campaign_bonus_points} pts | {applied_campaigns}")

        # Save bill to DB with appropriate status and error reason
        bill_data = BillData(
            user_id=user["id"],
            user_phone=phone,
            store_name=store_name,
            bill_no=bill_no,
            bill_date=bill_date,
            amount=amount,
            status=bill_status,
            points_issued=points_earned,
            image_url=f"data:image/jpeg;base64,{image_base64}",
            image_hash=image_hash,
            ocr_confidence=confidence,
            ocr_raw_data=ocr_data,
            processed_at=datetime.now(timezone.utc).isoformat(),
            rejection_reason=tagnpay_error  # Store TagnPay error for dashboard reference
        )
        bill_dict = bill_data.model_dump()
        if applied_campaigns:
            bill_dict["campaign_bonus"] = campaign_bonus_points
            bill_dict["applied_campaigns"] = applied_campaigns
        if force_credit_fallback_applied:
            bill_dict["force_credited"] = True
            bill_dict["fundle_original_error"] = tagnpay_error
            bill_dict["rejection_reason"] = None  # cleared since we accepted
        await insert_bill_and_alert(bill_dict)

        # Staff Incentive Sync — WhatsApp bill upload triggers attribution + registration activation
        try:
            await _sync_staff_incentive_for_bill(bill_dict.get("id"), bill_status, phone or "")
        except Exception as _e:
            logger.warning(f"staff-sync (whatsapp bill) failed: {_e}")

        # When force-credited, Fundle didn't add to balance so we must locally
        if force_credit_fallback_applied:
            await db.users.update_one(
                {"id": user["id"]},
                {"$inc": {"balance_points": points_earned, "total_earned_points": points_earned}}
            )
            # Refresh local total_balance for the WhatsApp reply
            u_after = await db.users.find_one({"id": user["id"]}, {"_id": 0, "balance_points": 1})
            if u_after:
                total_balance = int(u_after.get("balance_points", total_balance))
        
        # If brand not found, send admin alert and show processing message to user
        if bill_status == "pending_review" and "Brand" in (tagnpay_error or ""):
            # Send WhatsApp alert to admin
            background_tasks.add_task(send_admin_sms_alert, store_name, bill_no, amount, phone)
            
            # Send processing message to user
            processing_msg = f"""Bill Received Successfully!

Store: {store_name}
Bill No: {bill_no}
Date: {bill_date}
Amount: Rs {amount:.0f}

Your bill is being processed. Points will be updated within 24 hours.

Current Points: {total_balance}

Thank you for shopping at CP67 Mall!"""
            
            buttons = [
                {"id": "upload_bill", "title": "Upload Another Bill"},
                {"id": "my_points", "title": "My Points"},
                {"id": "customer_support", "title": "Customer Support"}
            ]
            await send_whatsapp_buttons(phone, processing_msg, buttons)
            return
        
        # TEMPORARILY DISABLED 30-day check for testing
        # if bill_status == "pending_review" and "30 days" in (tagnpay_error or ""):
        #     old_bill_msg = f""" *Bill Received*
        # 
        #  Store: {store_name}
        #  Bill No: {bill_no}
        #  Date: {bill_date}
        #  Amount: ₹{amount:.0f}
        # 
        #  This bill is older than 30 days and cannot be processed for points.
        # 
        # Please upload bills within 30 days of purchase to earn rewards.
        # 
        #  Current Points: {total_balance}"""
        #     
        #     buttons = [
        #         {"id": "upload_bill", "title": "Upload Recent Bill"},
        #         {"id": "my_points", "title": "Redeem Points"}
        #     ]
        #     await send_whatsapp_buttons(phone, old_bill_msg, buttons)
        #     return
        
        # Update user points in our DB (only for successful processing)
        if points_earned > 0:
            await db.users.update_one(
                {"id": user["id"]},
                {"$inc": {"balance_points": points_earned, "total_earned_points": points_earned}}
            )
            
            # Get updated balance
            updated_user = await db.users.find_one({"id": user["id"]})
            total_balance = int(updated_user.get("balance_points", 0)) if updated_user else total_balance

        # Point 44 (Feb 2026): WhatsApp auto-approve path — issue the deferred
        # parking coupon on the first verified bill.
        if bill_status == "auto_approved":
            try:
                await _maybe_issue_pending_parking_coupon(phone)
            except Exception as _pe:
                logger.warning(f"parking coupon hook (WA auto_approve) failed for {phone}: {_pe}")
        
        # Update QR analytics
        if user.get("first_touch_qr"):
            await db.qr_analytics.update_one(
                {"qr_code_id": user["first_touch_qr"]},
                {"$inc": {"bill_uploads": 1}},
                upsert=True
            )
        
        # Success Message (per revised flow document)
        store_display2 = store_name if store_name and store_name != "None" else "CP67 Mall"
        campaign_line = ""
        if campaign_bonus_points > 0 and applied_campaigns:
            names = ", ".join([c["name"] for c in applied_campaigns])
            campaign_line = f"\nBonus: +{campaign_bonus_points} pts ({names})"
        success_msg = f"""Thank you for uploading your bill from {store_display2} with Homeland Advantage.

Points Credited: {points_earned}{campaign_line}
Total Balance: {total_balance}

Earn more rewards every time you shop at CP67 Mall.

Happy Shopping!"""
        
        buttons = [
            {"id": "upload_bill", "title": "Upload Another Bill"},
            {"id": "my_points", "title": "My Points"}
        ]
        await send_whatsapp_buttons(phone, success_msg, buttons)
        
    except Exception as e:
        logger.error(f"Bill processing error: {e}")
        import traceback
        logger.error(traceback.format_exc())

        # Point 19 fix: previously this branch sent "trouble processing" to the
        # customer but NEVER inserted a bill record → admin panel was empty and
        # the bill was lost. Now save a stub with the raw image (if we have it)
        # so admin can review + retry manually.
        try:
            user_local = await db.users.find_one({"phone": phone})
            if user_local:
                # Prefer the base64 we downloaded if available, else the raw URL
                _img = None
                _b64 = locals().get("image_base64")
                if _b64:
                    _img = f"data:image/jpeg;base64,{_b64}"
                elif isinstance(image_url, str) and image_url.startswith("http"):
                    _img = image_url

                stub_bill = BillData(
                    user_id=user_local["id"],
                    user_phone=phone,
                    store_name=None,
                    bill_no=None,
                    bill_date=None,
                    amount=None,
                    status="manual_review",
                    image_url=_img,
                    rejection_reason=f"WhatsApp bill processing failed: {str(e)[:200]}",
                )
                await insert_bill_and_alert(stub_bill.model_dump())
                # Point 25: alert mall-ops so no failed WhatsApp bill sits unnoticed
                asyncio.create_task(maybe_alert_admin(stub_bill.id, "manual_review",
                                                     f"WhatsApp bill processing failed: {str(e)[:120]}"))
        except Exception as inner:
            logger.error(f"Failed to save fallback bill stub for {phone}: {inner}")

        # Send error message
        error_msg = """We're having trouble processing your bill right now.

Your bill has been submitted to our backend team for manual review.

We will verify it within 24-48 hours.

Thank you for your patience!"""

        buttons = [
            {"id": "upload_bill", "title": "Upload Bill"},
            {"id": "redeem_points", "title": "Redeem Points"}
        ]
        await send_whatsapp_buttons(phone, error_msg, buttons)


@api_router.post("/whatsapp/webhook")
async def whatsapp_webhook(request: Dict[Any, Any], background_tasks: BackgroundTasks):
    """WhatsApp webhook endpoint for Karix"""
    logger.info(f"WhatsApp webhook received: {request}")
    
    try:
        # Parse Karix webhook format
        event_type = request.get("events", {}).get("eventType", "")
        
        # Skip delivery events
        if event_type == "DELIVERY EVENTS":
            return {"status": "ok", "message": "Delivery event acknowledged"}
        
        event_content = request.get("eventContent", {})
        message_data = event_content.get("message", {})
        
        # Get phone number
        phone = message_data.get("from", "") or request.get("from") or request.get("phone", "")
        if not phone:
            return {"status": "ok", "message": "No phone number"}
        
        phone = re.sub(r'[^0-9]', '', str(phone))
        if len(phone) == 10:
            phone = "91" + phone
        
        # Get message content
        message = ""
        message_type = message_data.get("messageType", "text")
        profile_name = message_data.get("profileName", "")
        image_url = None
        
        if message_type == "text":
            text_content = message_data.get("text", "")
            if isinstance(text_content, dict):
                message = text_content.get("body", "")
            elif isinstance(text_content, str):
                message = text_content
            else:
                message = str(text_content) if text_content else ""
        elif message_type == "interactive":
            interactive = message_data.get("interactive", {})
            # Handle both button replies AND list replies
            button_reply = interactive.get("button_reply", {})
            list_reply = interactive.get("list_reply", {})
            message = button_reply.get("id", "") or list_reply.get("id", "") or button_reply.get("title", "") or list_reply.get("title", "")
            logger.info(f"Interactive message parsed - button_reply: {button_reply}, list_reply: {list_reply}, message: {message}")
        elif message_type == "image":
            message = "[IMAGE]"
            # Get image URL or base64 from Karix - uses fileLink for media download
            image_data = message_data.get("image", {})
            # Karix uses 'fileLink' for media download URL
            image_url = image_data.get("fileLink") or image_data.get("url") or image_data.get("link") or image_data.get("media_url")
            # Some providers send base64 directly
            if not image_url and image_data.get("data"):
                image_url = f"base64:{image_data.get('data')}"
            logger.info(f"Image message received - image_data: {image_data}, extracted URL: {image_url[:100] if image_url else None}...")
        else:
            # Fallback: try various Karix formats
            message = message_data.get("text", "") or message_data.get("body", "") or request.get("text") or request.get("message", "")
            if isinstance(message, dict):
                message = message.get("body", "") or message.get("text", "")
            logger.info(f"Unknown message type '{message_type}', raw message_data keys: {list(message_data.keys())}, extracted message: {message}")
        
        # Also check for Karix-specific postback / selectedOption fields
        if not message:
            message = (message_data.get("postbackText", "") or
                       message_data.get("selectedOption", {}).get("id", "") or
                       message_data.get("selectedOption", {}).get("title", "") or
                       event_content.get("postbackText", "") or
                       event_content.get("selectedOption", {}).get("id", "") or
                       "")
            if message:
                logger.info(f"Extracted message from Karix postback/selectedOption: {message}")
        
        logger.info(f"Webhook - type: {message_type}, message: '{message}', phone: {phone}")
        
        if not message:
            return {"status": "ok", "message": "No message content"}
        
        # ===== DEDUPLICATION: Prevent double messages from Karix =====
        # Karix can send duplicate webhooks for the same button click
        dedup_key = f"{phone}:{message}:{message_type}"
        recent_dup = await db.whatsapp_dedup.find_one({"key": dedup_key})
        if recent_dup:
            age_seconds = (datetime.now(timezone.utc) - datetime.fromisoformat(recent_dup["ts"])).total_seconds()
            if age_seconds < 10:
                logger.info(f"Dedup: Ignoring duplicate webhook for {phone} action={message} (age={age_seconds:.1f}s)")
                return {"status": "ok", "message": "Duplicate ignored"}
        await db.whatsapp_dedup.update_one(
            {"key": dedup_key},
            {"$set": {"key": dedup_key, "ts": datetime.now(timezone.utc).isoformat()}},
            upsert=True
        )
        
        # Parse source code
        source_code = parse_source_code(message)
        clean_message = message.split('|')[0].strip() if '|' in message else message
        
        # Match message to QR code
        qr_data = None
        if not source_code:
            msg_lower = clean_message.lower().strip()
            qr_data = MESSAGE_TO_SOURCE.get(msg_lower)
            if qr_data:
                source_code = qr_data["source_code"]
        else:
            qr_data = next((qr for qr in QR_CODES if qr["source_code"] == source_code), None)
        
        # Log inbound message
        log_entry = WhatsAppLog(
            user_phone=phone,
            direction="inbound",
            message_type=message_type,
            content=clean_message,
            source_code=source_code
        )
        await db.whatsapp_logs.insert_one(log_entry.model_dump())
        
        # Check if user exists
        user = await db.users.find_one({"phone": phone})
        mobile_10 = phone[2:] if phone.startswith("91") and len(phone) == 12 else phone
        
        # ===== GLOBAL BLOCKED CHECK — blocks ALL interactions =====
        is_blocked = await db.blocked_phones.find_one({"phone": mobile_10})
        if is_blocked:
            logger.info(f"Blocked phone {mobile_10} attempted interaction — rejected")
            block_msg = "Sorry, this number has been restricted from using Homeland Advantage services. Please contact mall management for assistance."
            outbound_log = WhatsAppLog(user_phone=phone, direction="outbound", message_type="text", content=block_msg)
            await db.whatsapp_logs.insert_one(outbound_log.model_dump())
            await send_whatsapp_text(phone, block_msg)
            return {"status": "ok", "message": "Blocked user"}
        
        # ===== CHECK FOR PARKING QR SCAN =====
        if source_code == "SRC_PARKING_PAY" or "parking validation" in clean_message.lower():
            # PARKING ENTRY FLOW - Generate parking session and send QR
            await process_parking_entry(phone, profile_name or (user.get("name") if user else None), background_tasks)
            return {"status": "ok", "message": "Parking entry processed"}
        
        # ===== CHECK FOR PARKING REGISTRATION QR (SRC_PARKING) =====
        if source_code == "SRC_PARKING":
            if user:
                # EXISTING USER - No free parking
                existing_msg = f"""Hi {(user.get('name') or profile_name or 'there')}!

You are already registered with Homeland Advantage.

Free parking is available only for new members who register via the parking QR code.

Use the menu below to explore your rewards!"""
                menu_options = [
                    {"id": "upload_bill", "title": "Upload Bill", "description": "Upload your shopping bill to earn points"},
                    {"id": "my_points", "title": "My Points", "description": "Check your loyalty points balance"},
                    {"id": "redeem_points", "title": "Redeem Points", "description": "Redeem points at participating brands"},
                ]
                outbound_log = WhatsAppLog(user_id=user["id"], user_phone=phone, direction="outbound", message_type="interactive", content=existing_msg)
                await db.whatsapp_logs.insert_one(outbound_log.model_dump())
                await send_whatsapp_list(phone, existing_msg, menu_options, header_text="Homeland Advantage", button_text="Menu")
            else:
                # NEW USER via Parking QR - Register WITHOUT 1000 points
                background_tasks.add_task(process_parking_registration, phone, profile_name, source_code, qr_data, background_tasks)
            return {"status": "ok", "message": "Parking registration processed"}
        
        # ===== FLOW LOGIC =====

        # Detect Staff Attribution Token (#STAFF:xxx). Open a 15-min window for
        # this customer_phone → staff. Registration & bill incentives get
        # created downstream against this attribution.
        attributing_staff = None
        try:
            attributing_staff = await parse_staff_token_from_message(clean_message)
            if attributing_staff:
                await open_attribution_window(mobile_10, attributing_staff)
                logger.info(f"Staff attribution opened: customer={mobile_10} staff={attributing_staff.get('staff_code')}")
        except Exception as e:
            logger.warning(f"Staff attribution parse failed: {e}")

        if not user:
            # NEW USER - Register
            await log_entry_update(log_entry)
            background_tasks.add_task(process_new_user_registration, phone, profile_name, source_code, qr_data, background_tasks, attributing_staff)
            
        else:
            # EXISTING USER
            await db.whatsapp_logs.update_one({"id": log_entry.id}, {"$set": {"user_id": user["id"]}})
            
            # Resolve display name: WhatsApp profileName > stored name > 'there'
            display_name = (profile_name or user.get("name") or "there").strip()
            if display_name.lower() in ("none", "null", ""):
                display_name = "there"
            
            # Update stored name from WhatsApp if user has no name or name is generic
            stored_name = user.get("name") or ""
            if profile_name and profile_name.strip() and stored_name in ("", "Customer", "there", "None"):
                await db.users.update_one({"id": user["id"]}, {"$set": {"name": profile_name.strip()}})
                display_name = profile_name.strip()
            
            msg_lower = clean_message.lower()
            
            # Map list/button titles to action IDs for robust matching
            TITLE_TO_ACTION = {
                "upload bill": "upload_bill",
                "redeem points": "redeem_points",
                "my points": "my_points",
                "help / support": "customer_support",
                "help/support": "customer_support",
                "help & support": "customer_support",
                "customer support": "customer_support",
                "know more": "know_more",
            }
            # If message matches a known title, convert to action ID
            if msg_lower.strip() in TITLE_TO_ACTION:
                message = TITLE_TO_ACTION[msg_lower.strip()]
                msg_lower = message
                logger.info(f"Title matched to action: {message}")
            
            if message == "my_points" or (msg_lower.strip() == "3" and "my points" not in msg_lower):
                # MY POINTS - Show detailed breakdown (per revised flow document)
                points_result = await tagnpay_client.get_customer_points(mobile_10)
                balance = 0
                total_earned = 0
                redeemed = 0
                if points_result.get("success") and points_result.get("data"):
                    balance = int(points_result["data"].get("balance_points", 0))
                    total_earned = int(points_result["data"].get("total_earned_points", balance))
                    redeemed = int(points_result["data"].get("redeemed_points", 0))
                
                # Also check local DB for earned/redeemed
                if total_earned == balance and redeemed == 0:
                    local_user = await db.users.find_one({"id": user["id"]}, {"_id": 0})
                    if local_user:
                        total_earned = int(local_user.get("total_earned_points", balance))
                        redeemed = total_earned - balance if total_earned > balance else 0
                
                # Update local DB
                await db.users.update_one({"id": user["id"]}, {"$set": {"balance_points": balance}})
                
                points_msg = f"""*Homeland Advantage Loyalty Points Summary:*

Points Earned: {total_earned}
Points Redeemed: {redeemed}
Available Points: {balance}"""
                
                buttons = [
                    {"id": "know_more", "title": "Know More"},
                    {"id": "upload_bill", "title": "Upload Bill"}
                ]
                
                outbound_log = WhatsAppLog(
                    user_id=user["id"],
                    user_phone=phone,
                    direction="outbound",
                    message_type="interactive",
                    content=points_msg
                )
                await db.whatsapp_logs.insert_one(outbound_log.model_dump())
                
                background_tasks.add_task(send_whatsapp_buttons, phone, points_msg, buttons)
            
            elif message == "redeem_points" or "redeem" in msg_lower or ("point" in msg_lower and message != "my_points") or "balance" in msg_lower:
                # REDEEM POINTS - Show redemption info (per revised flow document)
                points_result = await tagnpay_client.get_customer_points(mobile_10)
                balance = 0
                if points_result.get("success") and points_result.get("data"):
                    balance = int(points_result["data"].get("balance_points", 0))
                
                await db.users.update_one({"id": user["id"]}, {"$set": {"balance_points": balance}})
                
                redeem_msg = f"""*You have {balance} Homeland Advantage Points.*

Redeem your points at Participating Brands and Enjoy Instant Discounts."""
                
                buttons = [
                    {"id": "know_more", "title": "Know More"},
                    {"id": "upload_bill", "title": "Upload Bill"}
                ]
                
                outbound_log = WhatsAppLog(
                    user_id=user["id"],
                    user_phone=phone,
                    direction="outbound",
                    message_type="interactive",
                    content=redeem_msg
                )
                await db.whatsapp_logs.insert_one(outbound_log.model_dump())
                
                background_tasks.add_task(send_whatsapp_buttons, phone, redeem_msg, buttons)
            
            elif message == "know_more" or "know more" in msg_lower:
                # KNOW MORE (per revised flow document)
                know_more_msg = """*Explore Homeland Advantage, CP67 Mall's Loyalty Program.*

Check participating brands, points earning and redemption, and program terms.

https://cp67.co.in/homelandadvantage"""
                
                buttons = [
                    {"id": "upload_bill", "title": "Upload Bill"},
                    {"id": "my_points", "title": "My Points"}
                ]
                
                outbound_log = WhatsAppLog(
                    user_id=user["id"],
                    user_phone=phone,
                    direction="outbound",
                    message_type="interactive",
                    content=know_more_msg
                )
                await db.whatsapp_logs.insert_one(outbound_log.model_dump())
                
                background_tasks.add_task(send_whatsapp_buttons, phone, know_more_msg, buttons)
            
            elif message == "customer_support" or "support" in msg_lower or "help" in msg_lower or "contact" in msg_lower or msg_lower.strip() == "4":
                # HELP / SUPPORT (per revised flow document)
                support_msg = """*Need help? Contact us here:*

Email: advantage@homelandgroup.org
Mobile: 97296 76767
Support Desk: Ground Floor"""
                
                buttons = [
                    {"id": "know_more", "title": "Know More"},
                    {"id": "upload_bill", "title": "Upload Bill"}
                ]
                
                outbound_log = WhatsAppLog(
                    user_id=user["id"],
                    user_phone=phone,
                    direction="outbound",
                    message_type="interactive",
                    content=support_msg
                )
                await db.whatsapp_logs.insert_one(outbound_log.model_dump())
                
                background_tasks.add_task(send_whatsapp_buttons, phone, support_msg, buttons)
                
            elif message == "upload_bill" or "upload" in msg_lower or msg_lower.strip() == "1" or ("bill" in msg_lower and "upload" in msg_lower):
                # UPLOAD BILL PROMPT (per revised flow document)
                upload_msg = """*Great Choice!*

• Tap the Camera icon.📸

• Upload your CP67 Shopping Bill using Camera or Gallery.

• Share it with us.

Earn your Homeland Advantage Loyalty points instantly!

More Bills = More Points = More Rewards"""
                
                outbound_log = WhatsAppLog(
                    user_id=user["id"],
                    user_phone=phone,
                    direction="outbound",
                    message_type="text",
                    content=upload_msg
                )
                await db.whatsapp_logs.insert_one(outbound_log.model_dump())
                
                background_tasks.add_task(send_whatsapp_text, phone, upload_msg)
                
            elif message_type == "image" or message == "[IMAGE]":
                # BILL IMAGE UPLOADED - Process
                background_tasks.add_task(process_bill_image, phone, user, image_url, background_tasks)
                
            else:
                # DEFAULT MENU (per revised flow document)
                menu_msg = f"""Hi {display_name}! Welcome back to CP67's Loyalty Program - Homeland Advantage.

What would you like to do today?"""
                
                menu_options = [
                    {"id": "upload_bill", "title": "Upload Bill", "description": "Upload your shopping bill to earn points"},
                    {"id": "redeem_points", "title": "Redeem Points", "description": "Redeem points at participating brands"},
                    {"id": "my_points", "title": "My Points", "description": "Check your loyalty points balance"},
                    {"id": "customer_support", "title": "Help / Support", "description": "Contact our support team"},
                    {"id": "know_more", "title": "Know More", "description": "Participating brands & T&C"}
                ]
                
                outbound_log = WhatsAppLog(
                    user_id=user["id"],
                    user_phone=phone,
                    direction="outbound",
                    message_type="interactive",
                    content=menu_msg
                )
                await db.whatsapp_logs.insert_one(outbound_log.model_dump())
                
                background_tasks.add_task(send_whatsapp_list, phone, menu_msg, menu_options, "Homeland Advantage", "Menu")
        
        return {"status": "ok", "message": "Webhook processed"}
        
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return {"status": "error", "message": str(e)}


async def log_entry_update(log_entry):
    """Helper to update log entry"""
    pass


@api_router.get("/whatsapp/webhook")
async def whatsapp_webhook_verify(request: Dict[Any, Any] = None):
    """Webhook verification endpoint for WhatsApp"""
    return {"status": "ok", "message": "Webhook active"}

@api_router.post("/whatsapp/simulate")
async def simulate_whatsapp_message(request: WhatsAppMessageRequest, payload: dict = Depends(verify_jwt_token)):
    """Simulate WhatsApp message for testing/demo"""
    phone = re.sub(r'[^0-9]', '', request.phone)
    if len(phone) == 10:
        phone = "91" + phone
    
    source_code = parse_source_code(request.message)
    
    # Log the simulated message
    log_entry = WhatsAppLog(
        user_phone=phone,
        direction="inbound",
        message_type=request.message_type,
        content=request.message,
        source_code=source_code
    )
    
    # Check if user exists
    user = await db.users.find_one({"phone": phone})
    
    response_message = ""
    
    if not user:
        # New user
        qr_data = next((qr for qr in QR_CODES if qr["source_code"] == source_code), None)
        new_user = UserData(
            phone=phone,
            first_touch_source=source_code or "SRC_WHATSAPP",
            first_touch_qr=qr_data["qr_code_id"] if qr_data else None,
            first_touch_message=request.message
        )
        await db.users.insert_one(new_user.model_dump())
        log_entry.user_id = new_user.id
        
        if qr_data:
            await db.qr_analytics.update_one(
                {"qr_code_id": qr_data["qr_code_id"]},
                {"$inc": {"scans": 1}},
                upsert=True
            )
        
        response_message = """Welcome to Homeland Advantage – CP67 Mall! 

To complete your registration, please share:
1 Your Name
2 Your PAN Card Number

Type your details in format: NAME | PAN_NUMBER
Example: Rahul Kumar | ABCDE1234F"""
    else:
        log_entry.user_id = user["id"]
        
        # Check if registration is complete
        if not user.get("name") or not user.get("kyc_status"):
            # Check if message contains registration details
            if '|' in request.message and not request.message.startswith('Hi'):
                parts = [p.strip() for p in request.message.split('|')]
                if len(parts) >= 2:
                    name = parts[0]
                    # pan = parts[1]  # captured but not currently persisted
                    
                    # Update user
                    await db.users.update_one(
                        {"id": user["id"]},
                        {"$set": {
                            "name": name,
                            "kyc_status": True,
                            "registration_time": datetime.now(timezone.utc).isoformat()
                        }}
                    )
                    
                    # Update QR registration count
                    if user.get("first_touch_qr"):
                        await db.qr_analytics.update_one(
                            {"qr_code_id": user["first_touch_qr"]},
                            {"$inc": {"registrations": 1}},
                            upsert=True
                        )
                    
                    response_message = f"""Hi {name}!  Congratulations! 

You are now a valued member of Homeland Advantage – CP67 Mall's exclusive Loyalty Program 

Enjoy special privileges, exciting rewards & personalized offers every time you shop with us 

Shop • Earn • Redeem • Repeat

Welcome to a world of advantage & experiences crafted just for you! 

1 Upload Bill
2 Redeem Points"""
                else:
                    response_message = """Please share your details in the correct format:
NAME | PAN_NUMBER
Example: Rahul Kumar | ABCDE1234F"""
            else:
                response_message = """Welcome back! To complete registration, please share:
1 Your Name
2 Your PAN Card Number

Type: NAME | PAN_NUMBER"""
        else:
            # Registered user - handle commands
            msg_lower = request.message.lower()
            if "my points" in msg_lower or "balance" in msg_lower or "2" in msg_lower:
                response_message = f"""Your total Loyalty Points are: {user.get('balance_points', 0):.0f}

Redeem these points directly at participating retailers 

1 Upload Bill"""
            elif "upload" in msg_lower or "bill" in msg_lower or "1" in msg_lower:
                response_message = """Great choice! 

Just share your shopping bill here  and we'll credit your Homeland Advantage loyalty points instantly 

 More bills = More points = More rewards 

Please upload an image of your bill."""
            else:
                response_message = f"""Hi {user.get('name', 'there')}! 

What would you like to do today?

1 Upload Bill
2 Redeem Points

Reply with 1 or 2"""
    
    await db.whatsapp_logs.insert_one(log_entry.model_dump())
    
    # Log outbound response
    outbound_log = WhatsAppLog(
        user_id=log_entry.user_id,
        user_phone=phone,
        direction="outbound",
        message_type="text",
        content=response_message
    )
    await db.whatsapp_logs.insert_one(outbound_log.model_dump())
    
    return {
        "success": True,
        "response": response_message,
        "user_id": log_entry.user_id,
        "is_new_user": user is None
    }

@api_router.post("/whatsapp/simulate-bill-upload")
async def simulate_bill_upload(
    phone: str = Form(...),
    file: UploadFile = File(...),
    payload: dict = Depends(verify_jwt_token)
):
    """Simulate bill upload via WhatsApp"""
    phone = re.sub(r'[^0-9]', '', phone)
    if len(phone) == 10:
        phone = "91" + phone
    
    user = await db.users.find_one({"phone": phone})
    if not user:
        raise HTTPException(status_code=404, detail="User not found. Please register first.")
    
    if not user.get("kyc_status"):
        raise HTTPException(status_code=400, detail="Please complete registration first.")
    
    # Read file
    file_content = await file.read()
    image_base64 = base64.b64encode(file_content).decode()
    image_hash = calculate_image_hash(file_content)
    
    # Log the upload
    log_entry = WhatsAppLog(
        user_id=user["id"],
        user_phone=phone,
        direction="inbound",
        message_type="image",
        content=f"Bill image uploaded: {file.filename}"
    )
    await db.whatsapp_logs.insert_one(log_entry.model_dump())
    
    # Check for duplicate
    is_duplicate = await check_duplicate_bill(image_hash, None, None)
    
    if is_duplicate:
        response_message = f"""Our system shows that this bill has already been processed earlier and rewards have been issued 

 Your Current Points Balance: {user.get('balance_points', 0):.0f}

 Keep shopping at CP67 Mall to earn more points & enjoy exclusive rewards 

1 Upload Bill"""
        
        # Log outbound
        outbound_log = WhatsAppLog(
            user_id=user["id"],
            user_phone=phone,
            direction="outbound",
            message_type="text",
            content=response_message
        )
        await db.whatsapp_logs.insert_one(outbound_log.model_dump())
        
        return {
            "success": False,
            "status": "duplicate",
            "response": response_message
        }
    
    # Analyze bill with OCR
    ocr_result = await analyze_bill_image(image_base64)
    
    bill_data = BillData(
        user_id=user["id"],
        user_phone=phone,
        image_url=f"data:image/{file.content_type.split('/')[-1]};base64,{image_base64}",
        image_hash=image_hash
    )
    
    if ocr_result.get("success"):
        data = ocr_result["data"]
        bill_data.store_name = data.get("store_name")
        bill_data.bill_no = data.get("bill_no")
        bill_data.bill_date = data.get("bill_date")
        bill_data.amount = float(data.get("amount", 0)) if data.get("amount") else None
        bill_data.tax = float(data.get("tax", 0)) if data.get("tax") else None
        bill_data.ocr_confidence = data.get("confidence_score", 0)
        bill_data.ocr_raw_data = data
        
        # Check duplicate by bill number
        if bill_data.bill_no and bill_data.store_name:
            is_duplicate = await check_duplicate_bill(image_hash, bill_data.bill_no, bill_data.store_name)
            if is_duplicate:
                bill_data.status = "duplicate"
                response_message = f"""Our system shows that this bill has already been processed earlier and rewards have been issued 

 Your Current Points Balance: {user.get('balance_points', 0):.0f}

 Keep shopping at CP67 Mall to earn more points & enjoy exclusive rewards 

1 Upload Bill"""
            elif data.get("tampering_detected"):
                bill_data.status = "manual_review"
                bill_data.rejection_reason = f"Tampering indicators: {', '.join(data.get('tampering_indicators', []))}"
                response_message = """We noticed some issues with the bill image you uploaded 

 Your bill has been submitted to our backend team for review.

We will manually verify it within 24–48 hours, and your points will be credited once validation is complete 

Thank you for your patience! 

1 Upload Bill
2 Redeem Points"""
            elif data.get("image_quality") == "poor" or bill_data.ocr_confidence < 0.6:
                bill_data.status = "manual_review"
                response_message = """Your uploaded bill image is unclear for automatic processing.

No worries — it has been submitted for manual review. Verification will be completed within 24-48 hours, and points will be credited after approval.

Thank you for being a valued Homeland Advantage member.

1 Upload Bill
2 Redeem Points"""
            elif data.get("is_valid_bill") and bill_data.amount and bill_data.amount > 0:
                # Auto approve
                points = round(bill_data.amount * 0.01, 2)  # 1% of bill amount
                bill_data.status = "auto_approved"
                bill_data.points_issued = points
                bill_data.processed_at = datetime.now(timezone.utc).isoformat()
                
                # Update user points
                await db.users.update_one(
                    {"id": user["id"]},
                    {"$inc": {"balance_points": points, "total_earned_points": points}}
                )
                
                # Update QR analytics
                if user.get("first_touch_qr"):
                    await db.qr_analytics.update_one(
                        {"qr_code_id": user["first_touch_qr"]},
                        {"$inc": {"bill_uploads": 1}},
                        upsert=True
                    )
                
                new_balance = user.get("balance_points", 0) + points
                response_message = f"""Thank you for uploading your bill with Homeland Advantage 

 Bill Details:
 Store: {bill_data.store_name or 'N/A'}
 Bill No.: {bill_data.bill_no or 'N/A'}
 Date: {bill_data.bill_date or 'N/A'}
 Amount: ₹{bill_data.amount:.2f}

 Points Earned: {points:.0f}
 Total Balance: {new_balance:.0f}

 Keep shopping at CP67 Mall to earn more rewards & unlock exclusive benefits 

1 Upload Bill"""
            else:
                bill_data.status = "manual_review"
                response_message = """We couldn't validate the bill details automatically 

 Your bill has been submitted to our backend team for review.

We will verify it within 24–48 hours 

1 Upload Bill
2 Redeem Points"""
        else:
            bill_data.status = "manual_review"
            response_message = """We couldn't extract all bill details 

 Your bill has been submitted to our backend team for review.

We will verify it within 24–48 hours 

1 Upload Bill
2 Redeem Points"""
    else:
        bill_data.status = "manual_review"
        bill_data.ocr_raw_data = {"error": ocr_result.get("error")}
        response_message = """We're having trouble processing your bill image 

 Your bill has been submitted to our backend team for review.

We will verify it within 24–48 hours 

1 Upload Bill
2 Redeem Points"""
    
    await insert_bill_and_alert(bill_data.model_dump())
    
    # Log outbound response
    outbound_log = WhatsAppLog(
        user_id=user["id"],
        user_phone=phone,
        direction="outbound",
        message_type="text",
        content=response_message
    )
    await db.whatsapp_logs.insert_one(outbound_log.model_dump())
    
    return {
        "success": True,
        "status": bill_data.status,
        "bill_id": bill_data.id,
        "response": response_message,
        "ocr_data": bill_data.ocr_raw_data
    }


# ======================== CAMPAIGN ROUTES ========================

@api_router.get("/admin/campaigns")
async def list_campaigns(payload: dict = Depends(verify_jwt_token)):
    """Get all campaigns"""
    campaigns = []
    async for c in db.campaigns.find({}, {"_id": 0}).sort("created_at", -1):
        campaigns.append(c)
    return {"campaigns": campaigns, "total": len(campaigns)}


@api_router.post("/admin/campaigns")
async def create_campaign(data: CampaignCreate, payload: dict = Depends(verify_jwt_token)):
    """Create a new campaign"""
    campaign = {
        "id": str(uuid.uuid4()),
        "name": data.name,
        "description": data.description or "",
        "campaign_type": data.campaign_type,
        "multiplier": data.multiplier,
        "bonus_points": data.bonus_points,
        "min_spend": data.min_spend,
        "applicable_floors": data.applicable_floors,
        "applicable_categories": data.applicable_categories,
        "applicable_brand_ids": data.applicable_brand_ids,
        "start_date": data.start_date,
        "end_date": data.end_date,
        "is_active": data.is_active,
        "total_triggered": 0,
        "total_bonus_issued": 0,
        "created_by": payload.get("sub", "admin"),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": None,
    }
    await db.campaigns.insert_one(campaign)
    campaign.pop("_id", None)
    return {"success": True, "campaign": campaign}


@api_router.put("/admin/campaigns/{campaign_id}")
async def update_campaign(campaign_id: str, data: CampaignCreate, payload: dict = Depends(verify_jwt_token)):
    """Update an existing campaign"""
    existing = await db.campaigns.find_one({"id": campaign_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Campaign not found")
    update_data = {
        "name": data.name,
        "description": data.description or "",
        "campaign_type": data.campaign_type,
        "multiplier": data.multiplier,
        "bonus_points": data.bonus_points,
        "min_spend": data.min_spend,
        "applicable_floors": data.applicable_floors,
        "applicable_categories": data.applicable_categories,
        "applicable_brand_ids": data.applicable_brand_ids,
        "start_date": data.start_date,
        "end_date": data.end_date,
        "is_active": data.is_active,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.campaigns.update_one({"id": campaign_id}, {"$set": update_data})
    updated = await db.campaigns.find_one({"id": campaign_id}, {"_id": 0})
    return {"success": True, "campaign": updated}


@api_router.delete("/admin/campaigns/{campaign_id}")
async def delete_campaign(campaign_id: str, payload: dict = Depends(verify_jwt_token)):
    """Delete a campaign"""
    result = await db.campaigns.delete_one({"id": campaign_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return {"success": True, "message": "Campaign deleted"}


@api_router.put("/admin/campaigns/{campaign_id}/toggle")
async def toggle_campaign(campaign_id: str, payload: dict = Depends(verify_jwt_token)):
    """Toggle campaign active status"""
    campaign = await db.campaigns.find_one({"id": campaign_id}, {"_id": 0, "is_active": 1})
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    new_status = not campaign.get("is_active", True)
    await db.campaigns.update_one({"id": campaign_id}, {"$set": {"is_active": new_status, "updated_at": datetime.now(timezone.utc).isoformat()}})
    return {"success": True, "is_active": new_status}


@api_router.get("/admin/campaigns/active")
async def get_active_campaigns():
    """Get currently active campaigns (for consumer display / bill processing)"""
    now_iso = datetime.now(timezone.utc).isoformat()
    campaigns = []
    async for c in db.campaigns.find({"is_active": True}, {"_id": 0}).sort("end_date", 1):
        start = c.get("start_date") or ""
        end = c.get("end_date") or ""
        # Normalise date-only strings to full-day windows for correct comparison
        start_check = start + "T00:00:00" if len(start) == 10 else start
        end_check = end + "T23:59:59" if len(end) == 10 else end
        if start_check and start_check > now_iso:
            continue
        if end_check and end_check < now_iso:
            continue
        campaigns.append(c)
    return {"campaigns": campaigns}


# ======================== APP SETTINGS (Font customisation) ========================

_DEFAULT_APP_SETTINGS = {
    "heading_font_family": "Antique Olive",
    "heading_font_size_scale": 1.0,   # 1.0 = default; 1.2 = 20% larger
    "heading_font_weight": 700,
    "content_font_family": "Antique Olive",
    "content_font_size_scale": 1.0,
    "content_font_weight": 400,
    # Point 12: when True, WhatsApp/in-app auto-approved bills that Fundle
    # rejects with brand-mismatch are automatically force-credited locally
    # using the tier × amount earn-rate. Admin toggle in /app-settings.
    "auto_force_credit_on_fundle_reject": False,
}

class AppSettingsUpdate(BaseModel):
    heading_font_family: Optional[str] = None
    heading_font_size_scale: Optional[float] = None
    heading_font_weight: Optional[int] = None
    content_font_family: Optional[str] = None
    content_font_size_scale: Optional[float] = None
    content_font_weight: Optional[int] = None
    auto_force_credit_on_fundle_reject: Optional[bool] = None

async def _get_app_settings() -> Dict:
    doc = await db.app_settings.find_one({"id": "app"}, {"_id": 0})
    if not doc:
        doc = {"id": "app", **_DEFAULT_APP_SETTINGS}
    else:
        # Fill in any missing defaults so consumer never gets nulls
        for k, v in _DEFAULT_APP_SETTINGS.items():
            if doc.get(k) in (None, ""):
                doc[k] = v
    return doc

@api_router.get("/admin/app-settings")
async def get_admin_app_settings(payload: dict = Depends(verify_jwt_token)):
    """Admin: read current app settings (font family & size)."""
    return {"settings": await _get_app_settings()}

@api_router.put("/admin/app-settings")
async def update_admin_app_settings(update: AppSettingsUpdate,
                                     payload: dict = Depends(verify_jwt_token)):
    """Admin: update app settings (font family & size, heading + content separately)."""
    patch = {k: v for k, v in update.model_dump().items() if v is not None}
    # Clamp size scale to a sane range
    for k in ("heading_font_size_scale", "content_font_size_scale"):
        if k in patch:
            try:
                patch[k] = max(0.6, min(2.0, float(patch[k])))
            except (TypeError, ValueError):
                patch.pop(k)
    if "heading_font_weight" in patch:
        try:
            patch["heading_font_weight"] = max(100, min(900, int(patch["heading_font_weight"])))
        except (TypeError, ValueError):
            patch.pop("heading_font_weight")
    if "content_font_weight" in patch:
        try:
            patch["content_font_weight"] = max(100, min(900, int(patch["content_font_weight"])))
        except (TypeError, ValueError):
            patch.pop("content_font_weight")
    patch["updated_at"] = datetime.now(timezone.utc).isoformat()
    patch["updated_by"] = payload.get("username") or "admin"
    await db.app_settings.update_one({"id": "app"}, {"$set": patch}, upsert=True)
    return {"success": True, "settings": await _get_app_settings()}


# ======================== EXPORT ROUTES ========================


# ======================== FUNDLE RECONCILIATION (Points 13, 14) ========================

_LEGACY_154_NUMBERS = [
    "9971893169", "9501434757", "8288014563", "9888423423", "9805835490", "9041155485",
    "9878609065", "9888889030", "9814827567", "9416812567", "7009514900", "9815617567",
    "9872650520", "7895817189", "6280913518", "9818451897", "9999375959", "7696324215",
    "9888788947", "9888888155", "8557817733", "6280850312", "8287130086", "9855080526",
    "8802377850", "6392555129", "9653348499", "9779074863", "8541940053", "7009565642",
    "8395833307", "8077870707", "7009341633", "7536078809", "7742286179", "9781403257",
    "7814534581", "9878996913", "8289857886", "8219487080", "7580072114", "9682690020",
    "7973324298", "9888409447", "8360921152", "9888972305", "8894525028", "9999894799",
    "7006683663", "7973482873", "6239811261", "9877990694", "7351095914", "8699046345",
    "8699054829", "9478833770", "8448396006", "7909014744", "7344467526", "6571150613",
    "7404024981", "7404148378", "7405388695", "7902787411", "7944032791", "7436944843",
    "7423023805", "7423025810", "8725015070", "7440578341", "7733855054", "7889029834",
    "9495738664", "7466491767", "7748416638", "7867249443", "7898002289", "9872013931",
    "9465258129", "7740022436", "7435940325", "7459103870", "7767108012", "7747244425",
    "7405729822", "7818977482", "8888757131", "7459317944", "7747762474", "7451253729",
    "7721630194", "6701520995", "7986979231", "6284122145", "9253297172", "7740008232",
    "6239905311", "8427674850", "9872205779", "9888853423", "9781871321", "9026893931",
    "8727990333", "7087863728", "7719693159", "9360973309", "7814404654", "9780112211",
    "8360842486", "9530600004", "9646883343", "7009865001", "8396990097", "9855580245",
    "7999242647", "8217599309", "7347005652", "7490916937", "8894431066", "7470599499",
    "7982380161", "7352680284", "7901042288", "7424216351", "7696450172", "8136850420",
    "7922177305", "7303170183", "9877591269", "7777339275", "7572866836", "7876502788",
    "9877277065", "7696851527", "7495238593", "7788540708", "7087416307", "9205131589",
    "7473225172", "7484616424", "9766669249", "6562995629", "7459715468", "7949583555",
    "9687009087", "7344897895", "9814090160", "8195030838", "8725850076", "8894735654",
    "9876830594", "8968751707", "9592713209", "9103312918"
]


async def _sync_user_to_fundle(user: Dict) -> Dict:
    """Register a single user on Fundle if not already there. Returns
    {phone, action: registered|already|failed, error?}. Idempotent."""
    phone = user.get("phone") or ""
    phone_10 = phone[-10:] if phone else ""
    if not phone_10 or len(phone_10) != 10 or not phone_10.isdigit():
        return {"phone": phone, "action": "failed", "error": "invalid_phone"}
    # Check if already on Fundle
    try:
        chk = await tagnpay_client.get_customer_points(phone_10)
        if chk.get("success") and chk.get("data"):
            return {"phone": phone_10, "action": "already"}
    except Exception:
        pass
    # Register on Fundle
    try:
        reg = await tagnpay_client.register_customer(
            mobile_number=phone_10,
            name=user.get("name") or "Customer",
            pan_number="",
            source=user.get("first_touch_source") or "SRC_APP",
        )
        if reg.get("success"):
            await db.users.update_one(
                {"id": user["id"]},
                {"$set": {"fundle_synced_at": datetime.now(timezone.utc).isoformat(),
                          "fundle_registered": True}}
            )
            return {"phone": phone_10, "action": "registered"}
        return {"phone": phone_10, "action": "failed", "error": reg.get("error") or "unknown"}
    except Exception as e:
        return {"phone": phone_10, "action": "failed", "error": str(e)[:200]}


async def _sync_user_bills_to_fundle(user: Dict) -> Dict:
    """Re-submit any locally-approved bills for a user that were never
    successfully credited on Fundle. Uses the existing single-reprocess pipeline
    and honours the force_credit fallback."""
    phone_10 = (user.get("phone") or "")[-10:]
    result = {"phone": phone_10, "bills_synced": 0, "bills_failed": 0, "details": []}
    # Only re-run bills that are still not approved on Fundle (i.e., pending/rejected/manual)
    async for bill in db.bills.find(
        {"user_id": user["id"], "status": {"$in": ["pending_review", "manual_review", "rejected"]}},
        {"_id": 0}
    ):
        try:
            res = await _reprocess_single_bill(
                bill, re_ocr=False, send_whatsapp_flag=False, background_tasks=None,
                force_credit=False, force_credit_percent=0.0
            )
            if res.get("action") == "approved":
                result["bills_synced"] += 1
            else:
                result["bills_failed"] += 1
            result["details"].append({"bill_id": bill.get("id"), "action": res.get("action"), "err": res.get("error")})
        except Exception as e:
            result["bills_failed"] += 1
            result["details"].append({"bill_id": bill.get("id"), "err": str(e)[:200]})
    return result


async def run_registration_sync_job():
    """Nightly job (1AM IST): sync any newly-registered app users to Fundle.
    Idempotent — skips users already on Fundle."""
    logger.info("run_registration_sync_job: starting nightly Fundle sync")
    # Users created today OR marked not-yet-synced to Fundle
    cutoff = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    query = {
        "created_at": {"$gte": cutoff},
        "fundle_registered": {"$ne": True},
        "phone": {"$exists": True}
    }
    counters = {"registered": 0, "already": 0, "failed": 0}
    async for user in db.users.find(query, {"_id": 0}):
        r = await _sync_user_to_fundle(user)
        counters[r["action"]] = counters.get(r["action"], 0) + 1
    logger.info(f"run_registration_sync_job: done — {counters}")
    await db.sync_jobs.insert_one({
        "id": str(uuid.uuid4()),
        "type": "nightly_registration_sync",
        "run_at": datetime.now(timezone.utc).isoformat(),
        "counters": counters,
    })
    return counters


@api_router.post("/admin/sync/legacy-154")
async def sync_legacy_154(background_tasks: BackgroundTasks,
                           include_bills: bool = True,
                           payload: dict = Depends(verify_jwt_token)):
    """Point 14: One-time sync of the 154 phone numbers (from CP67 feedback doc)
    to Fundle. For each: (a) register on Fundle if not present, (b) re-sync any
    locally-approved bills. Runs in background; returns job_id for polling."""
    job_id = str(uuid.uuid4())
    await db.sync_jobs.insert_one({
        "id": job_id,
        "type": "legacy_154_sync",
        "status": "queued",
        "total": len(_LEGACY_154_NUMBERS),
        "processed": 0,
        "registered": 0,
        "already": 0,
        "failed": 0,
        "bills_synced": 0,
        "bills_failed": 0,
        "include_bills": include_bills,
        "run_at": datetime.now(timezone.utc).isoformat(),
        "queued_by": payload.get("username") or "admin",
    })

    async def _worker():
        await db.sync_jobs.update_one({"id": job_id}, {"$set": {"status": "running"}})
        for p10 in _LEGACY_154_NUMBERS:
            user = await db.users.find_one({"phone": {"$in": [p10, f"91{p10}", f"+91{p10}"]}}, {"_id": 0})
            if not user:
                await db.sync_jobs.update_one({"id": job_id}, {"$inc": {"processed": 1, "failed": 1}})
                continue
            r = await _sync_user_to_fundle(user)
            update_inc = {"processed": 1}
            update_inc[r["action"]] = 1  # registered / already / failed
            if include_bills and r["action"] in ("registered", "already"):
                br = await _sync_user_bills_to_fundle(user)
                update_inc["bills_synced"] = br["bills_synced"]
                update_inc["bills_failed"] = br["bills_failed"]
            await db.sync_jobs.update_one({"id": job_id}, {"$inc": update_inc})
        await db.sync_jobs.update_one({"id": job_id}, {"$set": {
            "status": "completed",
            "completed_at": datetime.now(timezone.utc).isoformat()
        }})

    background_tasks.add_task(_worker)
    return {"success": True, "job_id": job_id, "total": len(_LEGACY_154_NUMBERS)}


@api_router.get("/admin/sync/status/{job_id}")
async def sync_job_status(job_id: str, payload: dict = Depends(verify_jwt_token)):
    """Poll sync-job progress."""
    job = await db.sync_jobs.find_one({"id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Sync job not found")
    return job


@api_router.get("/admin/sync/jobs")
async def list_sync_jobs(limit: int = 20, payload: dict = Depends(verify_jwt_token)):
    """Recent sync-job history."""
    jobs = []
    async for j in db.sync_jobs.find({}, {"_id": 0}).sort("run_at", -1).limit(limit):
        jobs.append(j)
    return {"jobs": jobs}


@api_router.post("/admin/sync/nightly/run-now")
async def run_nightly_sync_now(background_tasks: BackgroundTasks,
                                payload: dict = Depends(verify_jwt_token)):
    """Trigger the nightly sync immediately for testing."""
    background_tasks.add_task(run_registration_sync_job)
    return {"success": True, "message": "Nightly sync queued"}



@api_router.get("/export/bills")
async def export_bills(
    status: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    payload: dict = Depends(verify_jwt_token)
):
    """Export bills as CSV"""
    query = {}
    if status and status != "all":
        query["status"] = status
    if start_date:
        query["created_at"] = {"$gte": start_date}
    if end_date:
        if "created_at" in query:
            query["created_at"]["$lte"] = end_date
        else:
            query["created_at"] = {"$lte": end_date}
    
    bills = await db.bills.find(query, {"_id": 0}).sort("created_at", -1).to_list(10000)
    
    if not bills:
        return Response(content="No bills found", media_type="text/plain")
    
    # Create CSV
    output = io.StringIO()
    fieldnames = ["id", "user_phone", "store_name", "bill_no", "bill_date", "amount", "status", "points_issued", "rejection_reason", "processed_by", "created_at", "processed_at"]
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction='ignore')
    writer.writeheader()
    
    for bill in bills:
        writer.writerow(bill)
    
    csv_content = output.getvalue()
    output.close()
    
    filename = f"bills_export_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"
    
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@api_router.get("/export/users")
async def export_users(
    customer_type: Optional[str] = None,
    source: Optional[str] = None,
    search: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    payload: dict = Depends(verify_jwt_token)
):
    """Export users as CSV (matches /api/users filters)."""
    query = {}
    if customer_type and customer_type != "all":
        query["customer_type"] = customer_type
    if source and source != "all":
        query["first_touch_source"] = source
    if search:
        query["$or"] = [
            {"phone": {"$regex": search, "$options": "i"}},
            {"name": {"$regex": search, "$options": "i"}},
        ]
    if start_date:
        query["created_at"] = {"$gte": start_date}
    if end_date:
        if "created_at" in query:
            query["created_at"]["$lte"] = end_date
        else:
            query["created_at"] = {"$lte": end_date}

    users = await db.users.find(query, {"_id": 0}).sort("created_at", -1).to_list(50000)

    if not users:
        return Response(content="No users found", media_type="text/plain")

    def _split_ist(iso_str):
        if not iso_str:
            return ("", "")
        try:
            dt = datetime.fromisoformat(str(iso_str).replace("Z", "+00:00"))
            ist_dt = dt.astimezone(IST)
            return (ist_dt.strftime("%d %b %Y"), ist_dt.strftime("%I:%M %p"))
        except Exception:
            return ("", "")

    output = io.StringIO()
    fieldnames = [
        "phone", "name", "loyalty_id", "customer_type",
        "first_touch_source", "first_touch_qr",
        "balance_points", "total_earned_points",
        "kyc_status", "joined_date", "joined_time",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for u in users:
        d, t = _split_ist(u.get("created_at"))
        writer.writerow({
            "phone": u.get("phone", ""),
            "name": u.get("name", ""),
            "loyalty_id": u.get("loyalty_id", ""),
            "customer_type": u.get("customer_type", ""),
            "first_touch_source": u.get("first_touch_source", ""),
            "first_touch_qr": u.get("first_touch_qr", ""),
            "balance_points": u.get("balance_points", 0),
            "total_earned_points": u.get("total_earned_points", 0),
            "kyc_status": u.get("kyc_status", ""),
            "joined_date": d,
            "joined_time": t,
        })

    csv_content = output.getvalue()
    output.close()

    filename = f"users_export_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@api_router.get("/export/brands")
async def export_brands(payload: dict = Depends(verify_jwt_token)):
    """Export brands as CSV"""
    brands = await db.brands.find({}, {"_id": 0}).sort("brand_name", 1).to_list(1000)
    
    if not brands:
        return Response(content="No brands found", media_type="text/plain")
    
    output = io.StringIO()
    fieldnames = ["id", "brand_name", "atv", "category", "is_active", "created_at", "updated_at"]
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction='ignore')
    writer.writeheader()
    
    for brand in brands:
        writer.writerow(brand)
    
    csv_content = output.getvalue()
    output.close()
    
    filename = f"brands_export_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"
    
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@api_router.get("/export/parking")
async def export_parking(
    status: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    payload: dict = Depends(verify_jwt_token)
):
    """Export parking sessions + free coupons as CSV with separate Date / Time columns (IST)."""
    user_gate = payload.get("gate")  # gate1/gate2 for parking staff, None for admin

    # ---- parking_sessions ----
    sess_q = {}
    if status and status != "all":
        sess_q["status"] = status
    if start_date:
        sess_q["entry_time"] = {"$gte": start_date}
    if end_date:
        sess_q.setdefault("entry_time", {})["$lte"] = end_date
    if user_gate:
        sess_q["exit_gate"] = user_gate
    pkg_sessions = await db.parking_sessions.find(sess_q, {"_id": 0}).sort("entry_time", -1).to_list(50000)

    # ---- parking_coupons ----
    coupon_q = {}
    if status == "active":
        coupon_q = {"used": False, "status": {"$ne": "expired"}}
    elif status == "completed":
        coupon_q = {"used": True}
    elif status == "expired":
        coupon_q = {"status": "expired"}
    if start_date:
        coupon_q["created_at"] = {"$gte": start_date}
    if end_date:
        coupon_q.setdefault("created_at", {})["$lte"] = end_date
    if user_gate:
        coupon_q["exit_gate"] = user_gate
    park_coupons = await db.parking_coupons.find(coupon_q, {"_id": 0}).sort("created_at", -1).to_list(50000)

    def _split_ist(iso_str):
        if not iso_str:
            return ("", "")
        try:
            dt = datetime.fromisoformat(str(iso_str).replace("Z", "+00:00"))
            ist_dt = dt.astimezone(IST)
            return (ist_dt.strftime("%d %b %Y"), ist_dt.strftime("%I:%M %p"))
        except Exception:
            return ("", "")

    rows = []
    for s in pkg_sessions:
        ed, et = _split_ist(s.get("entry_time"))
        xd, xt = _split_ist(s.get("exit_time"))
        rows.append({
            "session_code": s.get("session_code", ""),
            "phone": s.get("user_phone", ""),
            "user_name": s.get("user_name", ""),
            "type": "Session",
            "entry_date": ed, "entry_time": et,
            "exit_date": xd, "exit_time": xt,
            "duration_minutes": s.get("duration_minutes") or "",
            "status": s.get("status", ""),
            "exit_gate": s.get("exit_gate", ""),
            "scanned_by": s.get("scanned_by", ""),
        })
    for c in park_coupons:
        ed, et = _split_ist(c.get("created_at"))
        xd, xt = _split_ist(c.get("used_at"))
        if c.get("used"):
            cstatus = "completed"
        elif c.get("status") == "expired":
            cstatus = "expired"
        else:
            cstatus = "active"
        duration = ""
        if c.get("used") and c.get("created_at") and c.get("used_at"):
            try:
                a = datetime.fromisoformat(str(c["created_at"]).replace("Z", "+00:00"))
                b = datetime.fromisoformat(str(c["used_at"]).replace("Z", "+00:00"))
                duration = int((b - a).total_seconds() / 60)
            except Exception:
                pass
        rows.append({
            "session_code": c.get("coupon_code", ""),
            "phone": c.get("user_phone", ""),
            "user_name": c.get("user_name", ""),
            "type": "Free Coupon",
            "entry_date": ed, "entry_time": et,
            "exit_date": xd, "exit_time": xt,
            "duration_minutes": duration,
            "status": cstatus,
            "exit_gate": c.get("exit_gate", ""),
            "scanned_by": c.get("scanned_by", ""),
        })

    # Sort by entry_date+entry_time descending (raw ISO sorting via IST string is OK because we kept original key)
    rows.sort(key=lambda r: (r["entry_date"], r["entry_time"]), reverse=True)

    # Mask phones for parking-gate staff (admin sees full numbers)
    if user_gate:
        for r in rows:
            ph = r.get("phone")
            if ph:
                digits = "".join(ch for ch in str(ph) if ch.isdigit())
                last_10 = digits[-10:] if len(digits) >= 10 else digits
                r["phone"] = ("X" * max(len(last_10) - 4, 0)) + last_10[-4:] if last_10 else ""

    if not rows:
        return Response(content="No parking records found", media_type="text/plain")

    output = io.StringIO()
    fieldnames = [
        "session_code", "phone", "user_name", "type",
        "entry_date", "entry_time", "exit_date", "exit_time",
        "duration_minutes", "status", "exit_gate", "scanned_by",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for r in rows:
        writer.writerow(r)
    csv_content = output.getvalue()
    output.close()

    filename = f"parking_export_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

# ======================== PARKING QR IMAGE ENDPOINT ========================

@api_router.get("/parking/qr-image/{code}")
async def get_parking_qr_image(code: str):
    """Public endpoint to serve parking QR code images as JPEG.
    This URL can be shared via WhatsApp (Karix requires JPEG on HTTPS).
    """
    import qrcode
    from PIL import Image
    
    try:
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(code)
        qr.make(fit=True)
        
        qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
        
        img_buffer = io.BytesIO()
        qr_img.save(img_buffer, format='JPEG', quality=95)
        img_buffer.seek(0)
        
        return Response(
            content=img_buffer.getvalue(),
            media_type="image/jpeg",
            headers={
                "Content-Disposition": f"inline; filename=parking_qr_{code}.jpeg",
                "Cache-Control": "public, max-age=3600"
            }
        )
    except Exception as e:
        logger.error(f"Error generating QR image: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate QR code")

@api_router.get("/parking/coupon-qr/{coupon_code}")
async def get_parking_coupon_qr(coupon_code: str):
    """Public endpoint to serve parking coupon QR code images as JPEG."""
    import qrcode
    from PIL import Image, ImageDraw, ImageFont
    
    try:
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=10,
            border=4,
        )
        qr.add_data(coupon_code)
        qr.make(fit=True)
        
        qr_img = qr.make_image(fill_color="#2E2219", back_color="white").convert("RGB")
        
        img_buffer = io.BytesIO()
        qr_img.save(img_buffer, format='JPEG', quality=95)
        img_buffer.seek(0)
        
        return Response(
            content=img_buffer.getvalue(),
            media_type="image/jpeg",
            headers={
                "Content-Disposition": f"inline; filename=coupon_{coupon_code}.jpeg",
                "Cache-Control": "public, max-age=86400"
            }
        )
    except Exception as e:
        logger.error(f"Error generating coupon QR image: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate coupon QR")



# ======================== ANALYTICS ROUTES ========================

@api_router.get("/analytics/dashboard")
async def get_dashboard_stats(payload: dict = Depends(verify_jwt_token)):
    """Get dashboard overview statistics (parallelised for fast response)."""
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()

    points_pipeline = [{"$group": {"_id": None, "total": {"$sum": "$points_issued"}}}]

    # Run every count in parallel
    results = await asyncio.gather(
        db.users.count_documents({}),
        db.users.count_documents({"kyc_status": True}),
        db.users.count_documents({"customer_type": "new"}),
        db.users.count_documents({"customer_type": "existing"}),
        db.users.count_documents({"customer_type": {"$exists": False}}),
        db.bills.count_documents({}),
        db.bills.count_documents({"status": "auto_approved"}),
        db.bills.count_documents({"status": "manual_review"}),
        db.bills.count_documents({"status": "pending_review"}),
        db.bills.count_documents({"status": "approved"}),
        db.bills.count_documents({"status": "rejected"}),
        db.bills.count_documents({"status": "duplicate"}),
        db.bills.aggregate(points_pipeline).to_list(1),
        db.qr_analytics.find({}, {"_id": 0}).to_list(10),
        db.whatsapp_logs.count_documents({}),
        db.whatsapp_logs.count_documents({"direction": "inbound"}),
        db.whatsapp_logs.count_documents({"direction": "outbound"}),
        db.users.count_documents({"created_at": {"$gte": today_start}}),
        db.users.count_documents({"created_at": {"$gte": today_start}, "customer_type": "new"}),
        db.users.count_documents({"created_at": {"$gte": today_start}, "customer_type": "existing"}),
        db.bills.count_documents({"created_at": {"$gte": today_start}}),
        _get_footfall_stats(),
    )

    (total_users, registered_users, new_customers_raw, existing_customers, legacy_users,
     total_bills, auto_approved, manual_review, pending_review, approved, rejected, duplicate,
     points_result, qr_stats,
     total_messages, inbound, outbound,
     today_users, today_new_customers, today_existing_customers, today_bills,
     footfall) = results

    new_customers = new_customers_raw + legacy_users
    total_points_issued = points_result[0]["total"] if points_result else 0
    total_scans = sum(q.get("scans", 0) for q in qr_stats)

    return {
        "users": {
            "total": total_users,
            "registered": registered_users,
            "new_customers": new_customers,
            "existing_customers": existing_customers,
            "today": today_users,
            "today_new": today_new_customers,
            "today_existing": today_existing_customers
        },
        "bills": {
            "total": total_bills,
            "auto_approved": auto_approved,
            "manual_review": manual_review,
            "pending_review": pending_review,
            "approved": approved,
            "rejected": rejected,
            "duplicate": duplicate,
            "today": today_bills
        },
        "points": {
            "total_issued": total_points_issued
        },
        "qr": {
            "total_scans": total_scans,
            "by_code": qr_stats
        },
        "whatsapp": {
            "total_messages": total_messages,
            "inbound": inbound,
            "outbound": outbound
        },
        "footfall": footfall
    }


async def _get_footfall_stats():
    """Get footfall summary"""
    total = 0
    entries = []
    async for f in db.footfall.find({}, {"_id": 0}).sort("date", -1).limit(30):
        total += f.get("count", 0)
        entries.append(f)
    return {"total": total, "recent": entries}


@api_router.post("/admin/footfall")
async def add_footfall(data: dict, payload: dict = Depends(verify_jwt_token)):
    """Add daily footfall entry"""
    date = data.get("date", datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    count = int(data.get("count", 0))
    existing = await db.footfall.find_one({"date": date})
    if existing:
        await db.footfall.update_one({"date": date}, {"$set": {"count": count, "updated_at": datetime.now(timezone.utc).isoformat()}})
    else:
        await db.footfall.insert_one({"date": date, "count": count, "created_at": datetime.now(timezone.utc).isoformat()})
    return {"success": True, "date": date, "count": count}


@api_router.get("/admin/footfall")
async def get_footfall(payload: dict = Depends(verify_jwt_token)):
    """Get footfall history"""
    entries = []
    async for f in db.footfall.find({}, {"_id": 0}).sort("date", -1).limit(90):
        entries.append(f)
    total = sum(f.get("count", 0) for f in entries)
    return {"total": total, "entries": entries}


@api_router.get("/analytics/qr-performance")
async def get_qr_performance(payload: dict = Depends(verify_jwt_token)):
    """Get QR code performance analytics"""
    qr_stats = []
    for qr in QR_CODES:
        stats = await db.qr_analytics.find_one({"qr_code_id": qr["qr_code_id"]}, {"_id": 0})
        scans = stats.get("scans", 0) if stats else 0
        registrations = stats.get("registrations", 0) if stats else 0  # Only NEW customers
        existing_customers = stats.get("existing_customers", 0) if stats else 0  # Returning Fundle customers
        bill_uploads = stats.get("bill_uploads", 0) if stats else 0
        
        # Conversion rate based on NEW registrations only
        conversion_rate = (registrations / scans * 100) if scans > 0 else 0
        
        qr_stats.append({
            "qr_code_id": qr["qr_code_id"],
            "location": qr["location"],
            "source_code": qr["source_code"],
            "scans": scans,
            "registrations": registrations,  # New customers only
            "existing_customers": existing_customers,  # Returning Fundle customers
            "bill_uploads": bill_uploads,
            "conversion_rate": round(conversion_rate, 2)
        })
    
    return qr_stats

@api_router.get("/analytics/user-funnel")
async def get_user_funnel(payload: dict = Depends(verify_jwt_token)):
    """Get user funnel analytics"""
    total_scans = 0
    qr_stats = await db.qr_analytics.find({}, {"_id": 0}).to_list(10)
    for stat in qr_stats:
        total_scans += stat.get("scans", 0)
    
    total_users = await db.users.count_documents({})
    registered = await db.users.count_documents({"kyc_status": True})
    
    # Users who uploaded at least one bill
    users_with_bills = await db.bills.distinct("user_id")
    bill_uploaders = len(users_with_bills)
    
    # Users who earned points
    points_earners = await db.users.count_documents({"total_earned_points": {"$gt": 0}})
    
    return {
        "funnel": [
            {"stage": "QR Scans", "count": total_scans},
            {"stage": "User Created", "count": total_users},
            {"stage": "Registered", "count": registered},
            {"stage": "Bill Uploaded", "count": bill_uploaders},
            {"stage": "Points Earned", "count": points_earners}
        ]
    }

@api_router.get("/analytics/daily-stats")
async def get_daily_stats(
    days: int = 7, 
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    payload: dict = Depends(verify_jwt_token)
):
    """Get daily statistics for charts with optional custom date range"""
    stats = []
    
    if from_date and to_date:
        # Custom date range
        try:
            start_date = datetime.strptime(from_date, "%Y-%m-%d")
            end_date = datetime.strptime(to_date, "%Y-%m-%d")
            days_diff = (end_date - start_date).days + 1
            
            for i in range(days_diff):
                date = start_date + timedelta(days=i)
                date_start = date.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
                date_end = date.replace(hour=23, minute=59, second=59, microsecond=999999).isoformat()
                
                users = await db.users.count_documents({
                    "created_at": {"$gte": date_start, "$lte": date_end}
                })
                
                bills = await db.bills.count_documents({
                    "created_at": {"$gte": date_start, "$lte": date_end}
                })
                
                stats.append({
                    "date": date.strftime("%Y-%m-%d"),
                    "users": users,
                    "bills": bills
                })
            return stats
        except Exception as e:
            logger.error(f"Date parsing error: {e}")
            # Fall back to days-based query
    
    # Preset days range
    for i in range(days):
        date = datetime.now(timezone.utc) - timedelta(days=i)
        date_start = date.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        date_end = date.replace(hour=23, minute=59, second=59, microsecond=999999).isoformat()
        
        users = await db.users.count_documents({
            "created_at": {"$gte": date_start, "$lte": date_end}
        })
        
        bills = await db.bills.count_documents({
            "created_at": {"$gte": date_start, "$lte": date_end}
        })
        
        stats.append({
            "date": date.strftime("%Y-%m-%d"),
            "users": users,
            "bills": bills
        })
    
    return list(reversed(stats))

# ======================== PARKING ROUTES ========================

async def process_parking_entry(phone: str, name: Optional[str], background_tasks: BackgroundTasks):
    """Process parking entry from WhatsApp QR scan - creates session and sends QR to user"""
    try:
        # Normalize phone
        clean_phone = phone.replace("+", "").replace(" ", "")
        if len(clean_phone) == 10:
            clean_phone = "91" + clean_phone
        
        # Check if user has an active parking session
        existing_active = await db.parking_sessions.find_one({
            "user_phone": clean_phone,
            "status": "active"
        })
        
        if existing_active:
            # User already has active session - send reminder
            session_code = existing_active["session_code"]
            entry_time = datetime.fromisoformat(existing_active["entry_time"].replace('Z', '+00:00')).strftime("%I:%M %p")
            
            reminder_msg = f"""🅿 *CP67 Mall Parking*

You already have an active parking session!

 *Your Exit Code:*
━━━━━━━━━━━━━━━
*{session_code}*
━━━━━━━━━━━━━━━

⏰ *Entry Time:* {entry_time}

 Show this code at the exit counter when leaving.

Have a great time shopping! """
            
            # Log outbound
            outbound_log = WhatsAppLog(
                user_phone=clean_phone,
                direction="outbound",
                message_type="interactive",
                content=reminder_msg
            )
            await db.whatsapp_logs.insert_one(outbound_log.model_dump())
            
            buttons = [
                {"id": "upload_bill", "title": "Upload Bill"},
                {"id": "my_points", "title": "Check Points"}
            ]
            await send_whatsapp_buttons(clean_phone, reminder_msg, buttons)
            return
        
        # Generate unique session code
        session_code = generate_parking_code()
        
        # Create parking session
        session = ParkingSession(
            session_code=session_code,
            user_phone=clean_phone,
            user_name=name,
            status="active"
        )
        
        await db.parking_sessions.insert_one(session.model_dump())
        logger.info(f"Parking session created: {session_code} for {clean_phone}")
        
        entry_time = datetime.fromisoformat(session.entry_time).strftime("%I:%M %p")
        entry_date = datetime.fromisoformat(session.entry_time).strftime("%d %b %Y")
        
        welcome_msg = f"""🅿 *Welcome to CP67 Mall Parking!*

Your FREE parking session has started 

 *Your Exit Code:*
━━━━━━━━━━━━━━━━━━
*{session_code}*
━━━━━━━━━━━━━━━━━━

 *Date:* {entry_date}
⏰ *Entry Time:* {entry_time}

 *Show this code at the parking exit counter when leaving.*

Enjoy your visit to CP67 Mall! """
        
        # Log outbound
        outbound_log = WhatsAppLog(
            user_phone=clean_phone,
            direction="outbound",
            message_type="interactive",
            content=welcome_msg
        )
        await db.whatsapp_logs.insert_one(outbound_log.model_dump())
        
        # Generate QR code image
        qr_image = await generate_parking_qr_image(session_code)
        
        # Try to send QR image first, fall back to buttons if image fails
        if qr_image:
            qr_caption = f"""🅿 *Welcome to CP67 Mall Parking!*

Your FREE parking session has started 

 *Session Code:* {session_code}
 *Date:* {entry_date}
⏰ *Entry Time:* {entry_time}

 *Show this QR code at the exit counter*

Enjoy your visit to CP67 Mall! """
            
            # Try sending image
            image_sent = await send_whatsapp_image(clean_phone, qr_image, qr_caption)
            
            if image_sent:
                logger.info(f"Parking QR image sent successfully to {clean_phone}")
                return
        
        # Fallback: Send text message with buttons
        logger.info(f"Falling back to text message for parking entry {session_code}")
        buttons = [
            {"id": "upload_bill", "title": "Upload Bill"},
            {"id": "my_points", "title": "Check Points"}
        ]
        await send_whatsapp_buttons(clean_phone, welcome_msg, buttons)
            
    except Exception as e:
        logger.error(f"Error processing parking entry: {e}")
        import traceback
        logger.error(traceback.format_exc())

def generate_parking_code():
    """Generate unique parking session code"""
    timestamp = datetime.now().strftime("%H%M%S")
    random_part = uuid.uuid4().hex[:6].upper()
    return f"PKG-{timestamp}-{random_part}"

async def generate_parking_qr_image(session_code: str):
    """Generate QR code image for parking session"""
    try:
        import qrcode
        from io import BytesIO
        
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(session_code)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        
        buffer = BytesIO()
        img.save(buffer, format='PNG')
        buffer.seek(0)
        
        image_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
        return f"data:image/png;base64,{image_base64}"
    except Exception as e:
        logger.error(f"Failed to generate parking QR: {e}")
        return None

@api_router.post("/parking/entry")
async def create_parking_entry(phone: str, name: Optional[str] = None, background_tasks: BackgroundTasks = None):
    """Create parking entry and send QR to WhatsApp"""
    # Normalize phone
    clean_phone = phone.replace("+", "").replace(" ", "")
    if len(clean_phone) == 10:
        clean_phone = "91" + clean_phone
    
    # Generate unique session code
    session_code = generate_parking_code()
    
    # Create parking session
    session = ParkingSession(
        session_code=session_code,
        user_phone=clean_phone,
        user_name=name,
        status="active"
    )
    
    await db.parking_sessions.insert_one(session.model_dump())
    
    # Generate QR image
    qr_image = await generate_parking_qr_image(session_code)
    
    # Send WhatsApp message with QR
    if qr_image and background_tasks:
        entry_time = datetime.fromisoformat(session.entry_time).strftime("%I:%M %p")
        message = f"""🅿 *CP67 Mall Parking*

Your parking session has started!

 *Session Code:* {session_code}
⏰ *Entry Time:* {entry_time}

Please show the QR code below at the exit counter when leaving.

Thank you for visiting CP67 Mall! """
        
        background_tasks.add_task(send_whatsapp_image, clean_phone, qr_image, message)
    
    return {
        "success": True,
        "session_id": session.id,
        "session_code": session_code,
        "entry_time": session.entry_time,
        "qr_image": qr_image
    }

@api_router.post("/parking/validate/{session_code}")
async def validate_parking(session_code: str, request: Request = None, background_tasks: BackgroundTasks = None):
    """Validate parking QR code at exit - PUBLIC endpoint for scanner app"""
    # Parse body for scanned_by and gate
    scanned_by = None
    gate = None
    try:
        body = await request.json() if request else {}
        scanned_by = body.get("scanned_by")
        gate = body.get("gate")
    except Exception:
        pass
    
    # ===== CHECK PARKING COUPONS (PARK-XXXX) =====
    if session_code.startswith("PARK-"):
        coupon = await db.parking_coupons.find_one({"coupon_code": session_code}, {"_id": 0})
        
        if not coupon:
            return {
                "valid": False,
                "error": "Invalid parking code",
                "message": "This parking code does not exist in our system."
            }
        
        if coupon.get("used"):
            return {
                "valid": False,
                "error": "Already used",
                "message": "This parking coupon has already been used.",
                "exit_time": coupon.get("used_at")
            }
        
        # Check expiry
        expires_at = datetime.fromisoformat(coupon["expires_at"].replace('Z', '+00:00'))
        if datetime.now(timezone.utc) > expires_at:
            await db.parking_coupons.update_one(
                {"coupon_code": session_code},
                {"$set": {"status": "expired"}}
            )
            return {
                "valid": False,
                "error": "Expired",
                "message": "This parking coupon has expired."
            }
        
        # Mark coupon as used
        now = datetime.now(timezone.utc)
        update_fields = {
            "used": True,
            "used_at": now.isoformat(),
            "status": "used",
            "scanned_by": scanned_by
        }
        if gate:
            update_fields["exit_gate"] = gate
        await db.parking_coupons.update_one(
            {"coupon_code": session_code},
            {"$set": update_fields}
        )
        
        created_at = datetime.fromisoformat(coupon["created_at"].replace('Z', '+00:00'))
        now_ist = now.astimezone(IST)
        entry_ist = created_at.astimezone(IST)
        duration = now - created_at
        duration_minutes = int(duration.total_seconds() / 60)
        hours = duration_minutes // 60
        mins = duration_minutes % 60
        duration_display = f"{hours}h {mins}m" if hours > 0 else f"{mins} minutes"
        
        return {
            "valid": True,
            "message": "EXIT APPROVED - Free Parking Coupon",
            "session_code": session_code,
            "mobile_number": coupon.get("user_phone", ""),
            "user_name": coupon.get("user_name", "Customer"),
            "entry_time": coupon.get("created_at"),
            "entry_time_display": entry_ist.strftime("%I:%M %p"),
            "exit_time": now.isoformat(),
            "exit_time_display": now_ist.strftime("%I:%M %p"),
            "duration_minutes": duration_minutes,
            "duration_display": duration_display,
            "coupon_type": "free_parking",
            "thank_you_sent": False
        }
    
    # ===== CHECK PARKING SESSIONS (PKG-XXXX) =====
    session = await db.parking_sessions.find_one({"session_code": session_code}, {"_id": 0})
    
    if not session:
        return {
            "valid": False,
            "error": "Invalid parking code",
            "message": "This parking code does not exist in our system."
        }
    
    if session.get("status") == "completed":
        return {
            "valid": False,
            "error": "Already used",
            "message": "This parking code has already been used for exit.",
            "exit_time": session.get("exit_time")
        }
    
    if session.get("status") == "expired":
        return {
            "valid": False,
            "error": "Expired",
            "message": "This parking code has expired."
        }
    
    # Calculate duration
    entry_time = datetime.fromisoformat(session["entry_time"].replace('Z', '+00:00'))
    exit_time = datetime.now(timezone.utc)
    duration = exit_time - entry_time
    duration_minutes = int(duration.total_seconds() / 60)
    
    # Mark session as completed
    update_fields = {
        "status": "completed",
        "exit_time": exit_time.isoformat(),
        "duration_minutes": duration_minutes,
        "scanned_by": scanned_by
    }
    if gate:
        update_fields["exit_gate"] = gate
    await db.parking_sessions.update_one(
        {"session_code": session_code},
        {"$set": update_fields}
    )
    
    # Format times for display in IST
    entry_ist = entry_time.astimezone(IST)
    exit_ist = exit_time.astimezone(IST)
    entry_display = entry_ist.strftime("%I:%M %p")
    exit_display = exit_ist.strftime("%I:%M %p")
    date_display = exit_ist.strftime("%d %b %Y")
    
    hours = duration_minutes // 60
    mins = duration_minutes % 60
    duration_display = f"{hours}h {mins}m" if hours > 0 else f"{mins} minutes"
    
    # Send Thank You WhatsApp message to customer
    user_phone = session.get("user_phone")
    if user_phone:
        thank_you_msg = f""" *Thank You for Visiting CP67 Mall!*

We hope you had a wonderful experience! 

🅿 *Parking Summary:*
 Date: {date_display}
⏰ Entry: {entry_display}
⏰ Exit: {exit_display}
⏱ Duration: {duration_display}

 Your parking was FREE! 

We look forward to seeing you again soon!

 *Homeland Advantage* - Your CP67 Mall Loyalty Program"""
        
        # Log outbound message
        outbound_log = WhatsAppLog(
            user_phone=user_phone,
            direction="outbound",
            message_type="interactive",
            content=thank_you_msg
        )
        await db.whatsapp_logs.insert_one(outbound_log.model_dump())
        
        # Send with buttons for engagement
        buttons = [
            {"id": "upload_bill", "title": "Upload Bill"},
            {"id": "my_points", "title": "Check Points"}
        ]
        
        if background_tasks:
            background_tasks.add_task(send_whatsapp_buttons, user_phone, thank_you_msg, buttons)
        else:
            # Direct send if no background tasks
            await send_whatsapp_buttons(user_phone, thank_you_msg, buttons)
    
    return {
        "valid": True,
        "message": "Parking validated successfully!",
        "session_code": session_code,
        "mobile_number": session.get("user_phone"),
        "user_name": session.get("user_name"),
        "entry_time": session.get("entry_time"),
        "entry_time_display": entry_display,
        "exit_time": exit_time.isoformat(),
        "exit_time_display": exit_display,
        "duration_minutes": duration_minutes,
        "duration_display": duration_display,
        "thank_you_sent": True if user_phone else False
    }

@api_router.get("/parking/sessions")
async def get_parking_sessions(
    skip: int = 0,
    limit: int = 50,
    status: Optional[str] = None,
    payload: dict = Depends(verify_jwt_token)
):
    """Get parking sessions report - includes both PKG sessions and PARK coupons"""
    user_gate = payload.get("gate")  # None for admin, "gate1"/"gate2" for staff
    
    query = {}
    if status:
        query["status"] = status
    if user_gate:
        query["exit_gate"] = user_gate
    
    # Get PKG parking sessions
    pkg_sessions = await db.parking_sessions.find(query, {"_id": 0}).sort("entry_time", -1).to_list(500)
    
    # Get PARK coupons and normalize to same format
    coupon_query = {}
    if status == "active":
        coupon_query = {"used": False, "status": {"$ne": "expired"}}
    elif status == "completed":
        coupon_query = {"used": True}
    elif status == "expired":
        coupon_query = {"status": "expired"}
    if user_gate:
        coupon_query["exit_gate"] = user_gate
    
    park_coupons = await db.parking_coupons.find(coupon_query, {"_id": 0}).sort("created_at", -1).to_list(500)
    
    # Normalize coupons to session format
    for c in park_coupons:
        c["session_code"] = c.get("coupon_code", "")
        c["user_phone"] = c.get("user_phone", "")
        c["entry_time"] = c.get("created_at", "")
        c["exit_time"] = c.get("used_at") if c.get("used") else None
        c["status"] = "completed" if c.get("used") else ("expired" if c.get("status") == "expired" else "active")
        c["duration_minutes"] = None
        c["type"] = "coupon"
        if c.get("used") and c.get("created_at") and c.get("used_at"):
            try:
                created = datetime.fromisoformat(c["created_at"].replace('Z', '+00:00'))
                used = datetime.fromisoformat(c["used_at"].replace('Z', '+00:00'))
                c["duration_minutes"] = int((used - created).total_seconds() / 60)
            except Exception:
                pass
    
    # Merge and sort by entry_time descending
    all_sessions = pkg_sessions + park_coupons
    all_sessions.sort(key=lambda x: x.get("entry_time", "") or "", reverse=True)
    
    total = len(all_sessions)
    paginated = all_sessions[skip:skip + limit]
    
    # Convert entry/exit times to IST for display
    for s in paginated:
        if s.get("entry_time"):
            try:
                et = datetime.fromisoformat(s["entry_time"].replace('Z', '+00:00'))
                s["entry_time"] = et.astimezone(IST).isoformat()
            except Exception:
                pass
        if s.get("exit_time"):
            try:
                xt = datetime.fromisoformat(s["exit_time"].replace('Z', '+00:00'))
                s["exit_time"] = xt.astimezone(IST).isoformat()
            except Exception:
                pass

    # Mask phone numbers for parking-gate staff. Admin sees full numbers.
    if user_gate:
        for s in paginated:
            ph = s.get("user_phone")
            if ph:
                digits = "".join(ch for ch in str(ph) if ch.isdigit())
                last_10 = digits[-10:] if len(digits) >= 10 else digits
                s["user_phone"] = ("X" * max(len(last_10) - 4, 0)) + last_10[-4:] if last_10 else ""

    # Calculate stats (gate-filtered for parking staff)
    pkg_stat_q = {"status": "active"}
    coupon_stat_q = {"used": False, "status": {"$ne": "expired"}}
    if user_gate:
        pkg_stat_q["exit_gate"] = user_gate
        coupon_stat_q["exit_gate"] = user_gate
    
    active_pkg = await db.parking_sessions.count_documents(pkg_stat_q)
    active_coupons = await db.parking_coupons.count_documents(coupon_stat_q)
    active_count = active_pkg + active_coupons
    
    # IST midnight
    now_ist = datetime.now(IST)
    ist_midnight = now_ist.replace(hour=0, minute=0, second=0, microsecond=0)
    ist_midnight_utc = ist_midnight.astimezone(timezone.utc)
    
    pkg_today_q = {"status": "completed", "exit_time": {"$gte": ist_midnight_utc.isoformat()}}
    coupon_today_q = {"used": True, "used_at": {"$gte": ist_midnight_utc.isoformat()}}
    if user_gate:
        pkg_today_q["exit_gate"] = user_gate
        coupon_today_q["exit_gate"] = user_gate
    
    completed_pkg_today = await db.parking_sessions.count_documents(pkg_today_q)
    completed_coupons_today = await db.parking_coupons.count_documents(coupon_today_q)
    completed_today = completed_pkg_today + completed_coupons_today
    
    # Average duration
    avg_match = {"status": "completed", "duration_minutes": {"$exists": True}}
    if user_gate:
        avg_match["exit_gate"] = user_gate
    avg_pipeline = [
        {"$match": avg_match},
        {"$group": {"_id": None, "avg_duration": {"$avg": "$duration_minutes"}}}
    ]
    avg_result = await db.parking_sessions.aggregate(avg_pipeline).to_list(1)
    avg_duration = round(avg_result[0]["avg_duration"]) if avg_result else 0
    
    return {
        "sessions": paginated,
        "total": total,
        "skip": skip,
        "limit": limit,
        "gate": user_gate,
        "stats": {
            "active": active_count,
            "completed_today": completed_today,
            "avg_duration_minutes": avg_duration
        }
    }

@api_router.get("/parking/session/{session_id}")
async def get_parking_session(session_id: str, payload: dict = Depends(verify_jwt_token)):
    """Get single parking session details"""
    session = await db.parking_sessions.find_one({"id": session_id}, {"_id": 0})
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


# ======================== HEALTH CHECK ========================

@api_router.get("/")
async def root():
    return {"message": "CP67 Loyalty System API", "status": "running"}

@api_router.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.now(timezone.utc).isoformat()}

# Root-level health check for Kubernetes/deployment probes
@app.get("/health")
async def root_health_check():
    return {"status": "healthy", "timestamp": datetime.now(timezone.utc).isoformat()}

# Include router
app.include_router(api_router)

# Consumer App Routes
from routes.consumer import consumer_router, init_consumer_routes, auto_seed_if_empty
BACKEND_PUBLIC_URL = os.environ.get('BACKEND_PUBLIC_URL', '')
init_consumer_routes(db, tagnpay_client, JWT_SECRET, JWT_ALGORITHM, EMERGENT_LLM_KEY, BACKEND_PUBLIC_URL)
app.include_router(consumer_router)

# Staff Incentive Routes (Retailer Staff Incentive Platform — Point 19)
from routes.staff import (
    staff_router,
    staff_admin_router,
    bind_db as bind_staff_db,
    parse_staff_token_from_message,
    open_attribution_window,
    create_registration_incentive,
    create_or_activate_bill_incentive,
    sync_incentive_on_bill_status_change,
)
bind_staff_db(db, send_sms_otp=send_login_otp, store_otp=store_otp, verify_stored_otp=verify_stored_otp)
app.include_router(staff_router)
app.include_router(staff_admin_router)

# Point 21 — DIY Admin panels: Push broadcasts, Popups, Referral config
from routes.admin_diy import admin_diy_router, consumer_diy_router, init_diy_routes
init_diy_routes(db)
app.include_router(admin_diy_router)
app.include_router(consumer_diy_router)

# Point 26 — Registration Coupon Inventory (RWA / Office etc.)
from routes.coupons import (
    coupons_admin_router,
    bind_db as bind_coupons_db,
    issue_coupon_for_registration,
)
bind_coupons_db(db)
app.include_router(coupons_admin_router)


# ==================== PUBLIC DOWNLOADS ====================
from fastapi.responses import FileResponse, RedirectResponse

@app.get("/api/downloads/ios-build")
async def download_ios_build():
    """Public download of the Xcode project zip. No auth — safe because the
    zip contains only public source that the user themselves generated."""
    path = "/app/ios-build.zip"
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="ios-build.zip not yet generated. Ask the agent to package it.")
    return FileResponse(
        path,
        media_type="application/zip",
        filename="ios-build.zip",
        headers={"Cache-Control": "no-store"},
    )


# Point 23 — QR that redirects to Play Store listing.
PLAY_STORE_URL = "https://play.google.com/store/apps/details?id=com.homelandadvantage.cp67&hl=en_IN"
APP_STORE_URL = os.environ.get("APP_STORE_URL", "")  # fill once iOS app is live

@app.get("/api/downloads/play-store-qr")
async def download_play_store_qr(size: int = 512):
    """PNG QR code that scans → opens the Homeland Advantage Play Store listing.
    Print + laminate + display at CP67 information desks."""
    import qrcode
    from io import BytesIO
    size = max(128, min(size, 2048))
    qr = qrcode.QRCode(
        version=None, error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10, border=2,
    )
    qr.add_data(PLAY_STORE_URL)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#1E1B18", back_color="#FAF8F5").convert("RGB")
    if img.size[0] != size:
        img = img.resize((size, size))
    buf = BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return Response(
        content=buf.getvalue(),
        media_type="image/png",
        headers={"Content-Disposition": 'inline; filename="homeland-play-store.png"',
                 "Cache-Control": "public, max-age=3600"},
    )


@app.get("/api/download-app")
async def download_app_redirect(request: Request):
    """Universal download page — Android goes to Play Store, iOS to App Store,
    desktop shows a landing page with both links + PWA install guide.
    Point QR codes at this URL for a single, future-proof entry point."""
    ua = (request.headers.get("user-agent") or "").lower()
    if "android" in ua:
        return RedirectResponse(url=PLAY_STORE_URL, status_code=302)
    if any(k in ua for k in ("iphone", "ipad", "ipod")):
        if APP_STORE_URL:
            return RedirectResponse(url=APP_STORE_URL, status_code=302)
        # No App Store link yet → send iPhone users to install guide
        return RedirectResponse(url="/ios-install", status_code=302)
    # Desktop / other — bounce to Play Store (biggest audience) as default
    return RedirectResponse(url=PLAY_STORE_URL, status_code=302)



async def _sync_staff_incentive_for_bill(bill_id: str, new_status: str, user_phone: str):
    """Central hook called after ANY bill status change.
       - Creates a bill_upload incentive if the customer has an active
         staff attribution window and this bill hasn't been credited yet.
       - Syncs any existing bill_upload incentive on this bill to the new status.
       - Activates any pending registration incentive when a bill is approved.
    All calls are safe / idempotent."""
    try:
        # Normalise phone to 10-digit for attribution lookup
        mobile_10 = re.sub(r"\D", "", user_phone or "")[-10:]
        await create_or_activate_bill_incentive(bill_id, mobile_10, new_status)
        await sync_incentive_on_bill_status_change(bill_id, new_status)
    except Exception as e:
        logger.warning(f"staff-incentive sync failed for bill={bill_id}: {e}")


async def expire_old_parking_coupons():
    """Mark all parking coupons past their 24hr expiry as expired"""
    now = datetime.now(timezone.utc).isoformat()
    result = await db.parking_coupons.update_many(
        {"used": False, "status": {"$ne": "expired"}, "expires_at": {"$lt": now}},
        {"$set": {"status": "expired"}}
    )
    if result.modified_count > 0:
        logger.info(f"Auto-expired {result.modified_count} parking coupons")

async def _parking_expiry_loop():
    """Background loop to auto-expire parking coupons every 5 minutes"""
    import asyncio
    while True:
        try:
            await expire_old_parking_coupons()
        except Exception as e:
            logger.error(f"Parking expiry loop error: {e}")
        await asyncio.sleep(300)  # 5 minutes

@app.on_event("startup")
async def startup_seed():
    await auto_seed_if_empty()
    # Expire any stale coupons immediately on startup
    await expire_old_parking_coupons()
    # Start background expiry loop
    import asyncio
    asyncio.create_task(_parking_expiry_loop())
    # Ensure DB indexes for fast queries (idempotent)
    await ensure_db_indexes()
    # Session-20 (Feb 2026): initialise Emergent Object Storage for bill
    # images. Non-fatal — if init fails we fall back to inline storage and
    # log a warning.
    try:
        from storage import init_storage
        init_storage()
    except Exception as e:
        logger.warning(f"Object storage init on startup failed (non-fatal): {e}")
    # Point 16: Backfill bill_no_normalized on legacy bills (idempotent, one-off per doc)
    asyncio.create_task(_backfill_bill_no_normalized())
    # Point 25: One-time backfill so the alert scanner doesn't flood ops with
    # historical bills; only future bills entering an alert-worthy status
    # will notify. Then start the scanner as a safety net for any creation
    # path we didn't wire up explicitly.
    asyncio.create_task(_backfill_admin_alerts_sent())
    asyncio.create_task(_bill_alert_scanner_loop())
    # Point 13: Schedule nightly Fundle registration sync at 1 AM IST
    _start_scheduler()


async def _backfill_admin_alerts_sent():
    """One-off: mark all pre-existing bills as already-alerted so the scanner
    only fires for bills that arrive after this deployment. Idempotent."""
    try:
        now = datetime.now(timezone.utc).isoformat()
        res = await db.bills.update_many(
            {"admin_alerts_sent": {"$exists": False}},
            {"$set": {"admin_alerts_sent": {"backfill": now}}}
        )
        if getattr(res, "modified_count", 0):
            logger.info(f"admin_alerts_sent backfilled on {res.modified_count} legacy bills")
    except Exception as e:
        logger.warning(f"admin_alerts_sent backfill skipped: {e}")


async def _bill_alert_scanner_loop():
    """Safety-net loop: every 60s finds bills in manual_review/pending_review/
    rejected whose current status hasn't been alerted yet, and fires the alert
    via maybe_alert_admin (which dedupes).

    Feb 2026: (a) limit is 10 per status (was 50) so each cycle triggers at
    most 30 concurrent DB reads instead of 150 — prevents burst-starving
    user-facing endpoints. (b) 0.5s pause between per-bill maybe_alert_admin
    calls so we don't fire everything simultaneously against Atlas.
    """
    ALERT_STATUSES = ("manual_review", "pending_review", "rejected")
    while True:
        try:
            for status in ALERT_STATUSES:
                cursor = db.bills.find(
                    {"status": status, f"admin_alerts_sent.{status}": {"$exists": False}},
                    {"_id": 0, "id": 1, "rejection_reason": 1}
                ).limit(10)
                async for b in cursor:
                    try:
                        await maybe_alert_admin(b["id"], status, b.get("rejection_reason"))
                    except Exception as _e:
                        logger.warning(f"scanner alert failed: {_e}")
                    # Small pause between per-bill alerts so the scanner
                    # doesn't burst up to N find_ones simultaneously.
                    await asyncio.sleep(0.5)
        except Exception as e:
            logger.warning(f"bill alert scanner error: {e}")
        await asyncio.sleep(60)


async def _backfill_bill_no_normalized():
    """One-off backfill so historical bills participate in normalised-dedup.
    Idempotent — only touches docs missing the field."""
    try:
        cursor = db.bills.find(
            {"bill_no": {"$nin": [None, ""]}, "bill_no_normalized": {"$exists": False}},
            {"_id": 0, "id": 1, "bill_no": 1}
        )
        n = 0
        async for b in cursor:
            await db.bills.update_one(
                {"id": b["id"]},
                {"$set": {"bill_no_normalized": normalize_bill_no(b.get("bill_no"))}}
            )
            n += 1
        if n:
            logger.info(f"Backfilled bill_no_normalized on {n} legacy bills")
    except Exception as e:
        logger.warning(f"bill_no_normalized backfill skipped: {e}")


_scheduler = None
def _start_scheduler():
    """Start APScheduler with nightly Fundle sync (1 AM IST). Idempotent."""
    global _scheduler
    if _scheduler is not None:
        return
    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from apscheduler.triggers.cron import CronTrigger
        import pytz
        ist = pytz.timezone("Asia/Kolkata")
        _scheduler = AsyncIOScheduler(timezone=ist)
        _scheduler.add_job(
            run_registration_sync_job,
            CronTrigger(hour=1, minute=0, timezone=ist),
            id="nightly_fundle_sync",
            replace_existing=True,
        )
        _scheduler.start()
        logger.info("Scheduler started — nightly Fundle sync at 1:00 AM IST")
    except Exception as e:
        logger.warning(f"Scheduler failed to start: {e}")


async def ensure_db_indexes():
    """Create indexes on hot query paths. Idempotent — safe on every boot.
    Each index is created independently so one failure doesn't block the rest."""
    index_specs = [
        ("users", "phone", {}),
        ("users", "phone_10", {}),
        ("users", "loyalty_id", {}),
        ("users", "created_at", {}),
        ("users", "customer_type", {}),
        ("users", "first_touch_source", {}),
        ("users", "kyc_status", {}),
        # Feb 2026: `id` is the primary lookup key on every doc in the app
        # (bills.id, users.id, brands.id, etc.) — without these indexes
        # find_one({"id": ...}) forces a full collection scan and on Atlas
        # with growing collections triggers "read operation timed out"
        # (the user's production HTTP 500 root cause on Admin Bills).
        ("users", "id", {}),
        ("bills", "id", {}),
        ("brands", "id", {}),
        ("stores", "id", {}),
        ("campaigns", "id", {}),
        ("coupons", "id", {}),
        ("staff", "id", {}),
        ("staff_incentives", "id", {}),
        # Also index `id` on the remaining collections that are looked up
        # by application id — pre-empting the same COLLSCAN timeout pattern
        # as bills/users hit on production Atlas.
        ("parking_sessions", "id", {}),
        ("parking_coupons", "id", {}),
        ("sync_jobs", "id", {}),
        ("bulk_reprocess_jobs", "id", {}),
        ("app_settings", "id", {}),
        ("staff_attributions", "id", {}),
        ("bills", "created_at", {}),
        ("bills", "status", {}),
        ("bills", "user_id", {}),
        ("bills", "user_phone", {}),
        ("bills", "bill_no_normalized", {}),
        ("bills", "image_hash", {}),
        ("bills", [("user_id", 1), ("store_name", 1), ("bill_no_normalized", 1)], {}),
        ("bills", [("status", 1), ("created_at", -1)], {}),
        ("bills", [("image_hash", 1), ("status", 1)], {}),
        ("whatsapp_logs", "created_at", {}),
        ("whatsapp_logs", "direction", {}),
        ("whatsapp_logs", "user_phone", {}),
        ("parking_sessions", "entry_time", {}),
        ("parking_sessions", "status", {}),
        ("parking_sessions", "user_phone", {}),
        ("parking_sessions", "exit_gate", {}),
        ("parking_coupons", "coupon_code", {}),
        ("parking_coupons", "user_phone", {}),
        ("parking_coupons", "status", {}),
        ("parking_coupons", "created_at", {}),
        ("parking_coupons", "exit_gate", {}),
        ("blocked_phones", "phone", {}),
        ("otp_codes", "phone", {}),
        ("otp_codes", "expires_at", {}),
        ("whatsapp_dedup", "ts", {}),
        ("qr_analytics", "qr_code_id", {}),
        ("footfall", "date", {}),
    ]

    async def _safe_create(col, key, kwargs):
        try:
            await db[col].create_index(key, **kwargs)
        except Exception as e:
            logger.warning(f"Index {col}.{key} skip: {e}")

    await asyncio.gather(*(_safe_create(c, k, kw) for c, k, kw in index_specs))
    logger.info("DB indexes ensured")

    # One-time backfills so the admin User report doesn't show blanks/Pending
    # for users that registered before these flags were enforced.
    try:
        # 1) Backfill first_touch_source: app users → SRC_APP, everyone else → SRC_WHATSAPP
        app_backfill = await db.users.update_many(
            {
                "$or": [
                    {"first_touch_source": {"$exists": False}},
                    {"first_touch_source": None},
                    {"first_touch_source": ""},
                ],
                "app_registered": True,
            },
            {"$set": {"first_touch_source": "SRC_APP"}},
        )
        wa_backfill = await db.users.update_many(
            {
                "$or": [
                    {"first_touch_source": {"$exists": False}},
                    {"first_touch_source": None},
                    {"first_touch_source": ""},
                ]
            },
            {"$set": {"first_touch_source": "SRC_WHATSAPP"}},
        )
        # 2) Backfill kyc_status=True for any user with a phone number — being in our
        # system at all means they completed local registration. TagnPay sync status
        # is tracked separately via the `fundle_registered` field.
        kyc_backfill = await db.users.update_many(
            {
                "$or": [
                    {"kyc_status": {"$exists": False}},
                    {"kyc_status": False},
                    {"kyc_status": None},
                ]
            },
            {"$set": {"kyc_status": True}},
        )
        if app_backfill.modified_count or wa_backfill.modified_count or kyc_backfill.modified_count:
            logger.info(
                f"User backfill: app={app_backfill.modified_count}, "
                f"whatsapp={wa_backfill.modified_count}, kyc={kyc_backfill.modified_count}"
            )
    except Exception as e:
        logger.warning(f"user report backfill skipped: {e}")


# Static file serving for uploads
from fastapi.staticfiles import StaticFiles
os.makedirs("uploads/brands", exist_ok=True)
app.mount("/api/uploads", StaticFiles(directory="uploads"), name="uploads")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
