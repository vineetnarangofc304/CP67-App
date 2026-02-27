from fastapi import FastAPI, APIRouter, HTTPException, Depends, UploadFile, File, Form, BackgroundTasks
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
import asyncio
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict, Any
import uuid
from datetime import datetime, timezone, timedelta
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
client = AsyncIOMotorClient(mongo_url)
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

class AdminUser(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    username: str
    password_hash: str
    name: str
    role: str = "admin"  # admin, super_admin
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
    
    async def register_customer(self, mobile_number: str, name: str, pan_number: str, source: str = "WhatsApp") -> Dict:
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
                    "loc_id": LOCATION_CODE,
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
                image_data = base64.b64decode(bill_image_base64.split(',')[-1] if ',' in bill_image_base64 else bill_image_base64)
                temp_file = tempfile.NamedTemporaryFile(suffix='.jpg', delete=False)
                temp_file.write(image_data)
                temp_file.close()
                temp_file_path = temp_file.name
            
            async with httpx.AsyncClient(timeout=60.0) as client:
                # Build form data - pass store name from bill OCR to both brand fields
                brand_name = store_name or "CP67 Mall"
                data = {
                    "mobile_number": mobile_number,
                    "bill_amount": str(bill_amount),
                    "bill_number": bill_number,
                    "bill_date": bill_date,
                    "brand": brand_name,  # Store name from bill OCR
                    "brand_text": brand_name,  # Store name from bill OCR
                    "category": "Shopping",
                    "location": LOCATION_CODE
                }
                
                logger.info(f"TagnPay earn-points request: mobile={mobile_number}, amount={bill_amount}, brand={brand_name}")
                
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

tagnpay_client = TagnPayClient()

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
        current_month = datetime.now().month
        
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

async def check_duplicate_bill(image_hash: str, bill_no: Optional[str], store_name: Optional[str]) -> bool:
    """Check if bill already exists in database"""
    # Check by image hash
    existing = await db.bills.find_one({"image_hash": image_hash, "status": {"$ne": "rejected"}})
    if existing:
        return True
    
    # Check by bill number and store (if available)
    if bill_no and store_name:
        existing = await db.bills.find_one({
            "bill_no": bill_no,
            "store_name": store_name,
            "status": {"$ne": "rejected"}
        })
        if existing:
            return True
    
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
    }
]

# Message to source mapping (for tracking without visible source code)
MESSAGE_TO_SOURCE = {qr["prefilled_message"].lower(): qr for qr in QR_CODES}

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
            "admin_id": admin["id"]
        })
        return AdminLoginResponse(token=token, username=admin["username"])
    
    # Fallback to env credentials for backward compatibility
    if request.username == ADMIN_USERNAME and request.password == ADMIN_PASSWORD:
        token = create_jwt_token({"username": request.username, "name": "Admin", "role": "super_admin"})
        return AdminLoginResponse(token=token, username=request.username)
    
    raise HTTPException(status_code=401, detail="Invalid credentials")

@api_router.get("/admin/me")
async def get_admin_profile(payload: dict = Depends(verify_jwt_token)):
    return {
        "username": payload.get("username"),
        "name": payload.get("name", payload.get("username")),
        "role": payload.get("role")
    }

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
                "whatsapp_link": f"https://wa.me/{WHATSAPP_NUMBER}?text={qr['prefilled_message'].replace(' ', '%20')}%20%7C%20{qr['source_code']}",
                "scans": stats_data.get("total_sessions", 0),
                "registrations": 0,  # Parking doesn't affect registrations
                "bill_uploads": 0,   # Parking doesn't affect bill uploads
                "parking_active": stats_data.get("active", 0),
                "parking_completed": stats_data.get("completed", 0)
            }
        else:
            # Regular loyalty QR codes
            stats = await db.qr_analytics.find_one({"qr_code_id": qr["qr_code_id"]}, {"_id": 0})
            whatsapp_link = f"https://wa.me/{WHATSAPP_NUMBER}?text={qr['prefilled_message'].replace(' ', '%20')}%20%7C%20{qr['source_code']}"
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
        whatsapp_link = f"https://wa.me/{WHATSAPP_NUMBER}?text={qr['prefilled_message'].replace(' ', '%20')}%20%7C%20{qr['source_code']}"
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
    
    whatsapp_link = f"https://wa.me/{WHATSAPP_NUMBER}?text={qr_data['prefilled_message'].replace(' ', '%20')}%20%7C%20{qr_data['source_code']}"
    
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
    not_found = []
    
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
            except:
                pass
    
    return {
        "message": f"Imported {inserted_count} Fundle customer phone numbers",
        "imported": inserted_count,
        "total_provided": len(phone_numbers)
    }

@api_router.get("/admin/check-fundle-customer/{phone}")
async def check_fundle_customer(phone: str, payload: dict = Depends(verify_jwt_token)):
    """Check if a phone number is in the imported Fundle customer list"""
    clean_phone = ''.join(filter(str.isdigit, phone))
    if len(clean_phone) == 12 and clean_phone.startswith('91'):
        clean_phone = clean_phone[2:]
    
    existing = await db.fundle_customers.find_one({"phone_10": clean_phone})
    return {"phone": phone, "is_fundle_customer": existing is not None}

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

@api_router.get("/bills")
async def get_bills(
    skip: int = 0,
    limit: int = 50,
    status: Optional[str] = None,
    qr_source: Optional[str] = None,
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
    
    total = await db.bills.count_documents(query)
    bills = await db.bills.find(query, {"_id": 0}).skip(skip).limit(limit).sort("created_at", -1).to_list(limit)
    
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
            "image_url": 1,
            "image_hash": 1,
            "ocr_confidence": 1,
            "ocr_raw_data": 1,
            "system_rejection_reason": "$rejection_reason",
            "rejection_reason": 1,
            "processed_by": 1,
            "processed_by_username": 1,
            "processed_by_role": 1,
            "processed_at": 1,
            "created_at": 1
        }},
        {"$sort": {"created_at": 1}}
    ]
    bills = await db.bills.aggregate(pipeline).to_list(100)
    return bills

@api_router.get("/bills/{bill_id}")
async def get_bill_details(bill_id: str, payload: dict = Depends(verify_jwt_token)):
    """Get single bill with full details"""
    bill = await db.bills.find_one({"id": bill_id}, {"_id": 0})
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
    bill = await db.bills.find_one({"id": bill_id})
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
        earn_result = await tagnpay_client.earn_points(
            mobile_number=mobile_10,
            bill_amount=bill_amount,
            bill_number=bill_no,
            bill_date=bill_date,
            store_name=store_name,
            bill_image_base64=bill.get("image_url", "").split(",")[-1] if bill.get("image_url") else None
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
        
        update_data["status"] = "approved"
        update_data["points_issued"] = points_earned
        
        # Update user points in our DB
        await db.users.update_one(
            {"id": bill["user_id"]},
            {"$inc": {"balance_points": points_earned, "total_earned_points": points_earned}}
        )
        
        # Update QR analytics
        if user.get("first_touch_qr"):
            await db.qr_analytics.update_one(
                {"qr_code_id": user["first_touch_qr"]},
                {"$inc": {"bill_uploads": 1}},
                upsert=True
            )
        
        # EXACT Success WhatsApp Message
        whatsapp_message = f"""Thank you for uploading your bill with Homeland Advantage 🎉

🧾 Bill Details:
🏬 Store: {store_name}
🧾 Bill No.: {bill_no}
📅 Date: {bill_date}
💰 Amount: ₹{bill_amount:.0f}

✨ Points Earned: {points_earned}
💳 Total Balance: {total_balance}

🛍️ Keep shopping at CP67 Mall to earn more rewards & unlock exclusive benefits 🌟"""
        
    else:
        # Rejection
        system_reason = bill.get("rejection_reason") or bill.get("ocr_raw_data", {}).get("extraction_notes", "")
        admin_reason = request.rejection_reason or "Bill could not be verified"
        
        update_data["status"] = "rejected"
        update_data["system_rejection_reason"] = system_reason
        update_data["admin_rejection_reason"] = admin_reason
        
        # Get current balance for message
        points_result = await tagnpay_client.get_customer_points(mobile_10)
        current_balance = 0
        if points_result.get("success") and points_result.get("data"):
            current_balance = int(points_result["data"].get("balance_points", 0))
        
        # WhatsApp rejection message
        whatsapp_message = f"""We're sorry, but your bill could not be processed 🧾

📌 Reason: {admin_reason}

💳 Your Current Points Balance: {current_balance}

Please ensure your next bill upload:
✅ Is clearly visible and not blurry
✅ Shows complete bill details
✅ Has not been submitted before

🛍️ Keep shopping at CP67 Mall to earn more rewards 🌟"""
    
    await db.bills.update_one({"id": bill_id}, {"$set": update_data})
    
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
            buttons = [{"id": "upload_bill", "title": "Upload Bill"}]
            background_tasks.add_task(send_whatsapp_buttons, phone, whatsapp_message, buttons)
        else:
            buttons = [
                {"id": "upload_bill", "title": "Upload Bill"},
                {"id": "my_points", "title": "Redeem Points"}
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
async def reprocess_bill(bill_id: str, background_tasks: BackgroundTasks, payload: dict = Depends(verify_jwt_token)):
    """Reprocess a pending bill after brand has been added to Fundle.
    This will also register the customer if they are not registered in Fundle.
    """
    
    # Get bill
    bill = await db.bills.find_one({"id": bill_id})
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
    image_url = bill.get("image_url", "")
    
    # Extract base64 from image URL if present
    image_base64 = None
    if image_url and image_url.startswith("data:"):
        image_base64 = image_url.split(",")[1] if "," in image_url else None
    
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
            # Success! Update bill status
            await db.bills.update_one(
                {"id": bill_id},
                {"$set": {
                    "status": "approved",
                    "points_issued": points_earned,
                    "rejection_reason": None,
                    "processed_at": datetime.now(timezone.utc).isoformat(),
                    "processed_by": "admin_reprocess"
                }}
            )
            
            # Update user points
            await db.users.update_one(
                {"id": user["id"]},
                {"$inc": {"balance_points": points_earned, "total_earned_points": points_earned}}
            )
            
            # Get updated balance
            points_result = await tagnpay_client.get_customer_points(mobile_10)
            total_balance = 0
            if points_result.get("success") and points_result.get("data"):
                total_balance = int(points_result["data"].get("balance_points", 0))
            
            # Send success message to user
            success_msg = f"""🎉 *Points Credited!*

Your bill has been processed:
🏬 Store: {store_name}
🧾 Bill No: {bill_no}
💰 Amount: ₹{amount:.0f}

✨ Points Earned: {points_earned}
💳 Total Balance: {total_balance}

Thank you for your patience! 🛍️"""
            
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

# Karix API Key
KARIX_API_KEY = os.environ.get('WHATSAPP_API_KEY', '')

# ======================== ADMIN SMS ALERT ========================

async def send_admin_sms_alert(brand_name: str, bill_no: str, amount: float, user_phone: str):
    """Send SMS alert to admin when a brand is not found in Fundle master"""
    try:
        logger.info(f"Sending admin alert for brand: {brand_name} to {ADMIN_PHONE}")
        
        # Send WhatsApp message to admin
        admin_msg = f"""🚨 *New Brand Alert - Action Required*

A bill was uploaded but the brand is not in Fundle master.

📝 *Add this exact brand name to Fundle:*
👉 *{brand_name}*

🧾 Bill Details:
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

async def send_whatsapp_text(phone: str, message: str):
    """Send simple text WhatsApp message via Karix RCM API"""
    if not KARIX_API_KEY:
        logger.error("Karix API key not configured")
        return False
    
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
            logger.info(f"Karix text response: {response.status_code} - {response.text}")
            return response.status_code == 200
    except Exception as e:
        logger.error(f"Karix send error: {e}")
        return False

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
                except:
                    pass
            
            logger.warning("Media upload failed, will try direct send")
            return None
    except Exception as e:
        logger.error(f"Karix media upload error: {e}")
        return None

async def send_whatsapp_image(phone: str, image_base64: str, caption: str = ""):
    """Send WhatsApp image message via Karix RCM API
    
    Flow: 
    1. Upload image to Karix media API to get media_id
    2. Send image using the media_id
    3. If that fails, try sending image directly with base64
    4. Fall back to text message if all else fails
    """
    if not KARIX_API_KEY:
        logger.error("Karix API key not configured")
        return False
    
    try:
        # Extract base64 data if it has data URL prefix
        if image_base64.startswith("data:"):
            image_base64 = image_base64.split(",")[1]
        
        # STEP 1: Try uploading media first to get media_id
        media_id = await upload_media_to_karix(image_base64, f"parking_qr_{datetime.now().strftime('%Y%m%d%H%M%S')}.png")
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            if media_id:
                # STEP 2: Send using media_id
                logger.info(f"Sending image with media_id: {media_id}")
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
                                "type": "IMAGE",
                                "image": {
                                    "id": media_id,
                                    "caption": caption
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
                logger.info(f"Karix image (with media_id) response: {response.status_code} - {response.text[:200]}")
                
                if response.status_code == 200:
                    return True
            
            # STEP 3: Try direct base64 in 'link' field as data URI
            logger.info("Trying direct base64 data URI method...")
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
                            "type": "IMAGE",
                            "image": {
                                "link": f"data:image/png;base64,{image_base64}",
                                "caption": caption
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
            logger.info(f"Karix image (data URI) response: {response.status_code} - {response.text[:200]}")
            
            if response.status_code == 200:
                return True
            
            # STEP 4: If image failed, fall back to sending text message with caption
            logger.warning(f"Image send failed, falling back to text message")
            return await send_whatsapp_text(phone, caption)
            
    except Exception as e:
        logger.error(f"Karix image send error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        # Fall back to text message
        return await send_whatsapp_text(phone, caption)

# ======================== WHATSAPP WEBHOOK ROUTES ========================

async def process_new_user_registration(phone: str, profile_name: str, source_code: str, qr_data: dict, background_tasks: BackgroundTasks):
    """Handle new user registration flow"""
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
            customer_type = "new"  # Confirmed new customer registered via our system
            # Get initial points after registration
            points_result = await tagnpay_client.get_customer_points(mobile_10)
            if points_result.get("success") and points_result.get("data"):
                balance_points = points_result["data"].get("balance_points", 0)
        else:
            # Fundle registration failed - still proceed with local registration
            logger.warning(f"Fundle registration failed for {mobile_10}, proceeding with local registration. Error: {reg_result.get('error')}")
            fundle_registered = False
            customer_type = "new"  # Still a new customer to our system
    
    # Create user in our DB
    new_user = UserData(
        phone=phone,
        name=profile_name or "Customer",
        kyc_status=fundle_registered,  # True if Fundle registration succeeded
        customer_type=customer_type,  # "new" or "existing"
        registration_time=datetime.now(timezone.utc).isoformat(),
        first_touch_source=source_code,
        first_touch_qr=qr_data["qr_code_id"] if qr_data else None,
        first_touch_message="QR Scan Registration",
        balance_points=balance_points
    )
    await db.users.insert_one(new_user.model_dump())
    
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
    
    # EXACT Registration Success Message
    welcome_msg = f"""Hi {profile_name or 'there'}! 🎉 Congratulations! 🎉

You are now successfully registered as a valued member of Homeland Advantage – CP67 Mall's exclusive Loyalty Program ✨

📱 Mobile: {mobile_10}
👤 Name: {profile_name or 'Customer'}
💳 Current Points: {balance_points}

Enjoy special privileges, exciting rewards & personalized offers every time you shop with us 🛍️

Shop • Earn • Redeem • Repeat

Welcome to a world of advantage & experiences crafted just for you! 🌟💎"""
    
    buttons = [
        {"id": "upload_bill", "title": "Upload Bill"},
        {"id": "my_points", "title": "Redeem Points"},
        {"id": "customer_support", "title": "Customer Support"}
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
    
    await send_whatsapp_buttons(phone, welcome_msg, buttons)
    return new_user


async def process_bill_image(phone: str, user: dict, image_url: str, background_tasks: BackgroundTasks):
    """Process uploaded bill image with OCR and TagnPay API"""
    mobile_10 = phone[2:] if phone.startswith("91") and len(phone) == 12 else phone
    logger.info(f"Processing bill image for phone {phone}, image_url: {image_url}")
    
    try:
        # First send acknowledgment
        ack_msg = """Thank you for uploading your bill! 🧾

We're scanning your bill now. Please wait a moment... ⏳"""
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
            logger.error("No image data available - sending manual review message")
            # Send unclear image response
            unclear_msg = """We noticed that the bill image you uploaded is not clear enough to process automatically 🧾

📌 Don't worry — your bill has been submitted to our backend team.

We will manually verify it within 24–48 hours, and your points will be credited once validation is complete ✅

Thank you for your patience and for being a valued member of Homeland Advantage 🌟"""
            
            buttons = [
                {"id": "upload_bill", "title": "Upload Bill"},
                {"id": "my_points", "title": "Redeem Points"}
            ]
            await send_whatsapp_buttons(phone, unclear_msg, buttons)
            return
        
        # Check for duplicate (by image hash)
        image_hash = hashlib.md5(base64.b64decode(image_base64)).hexdigest()
        existing_bill = await db.bills.find_one({"image_hash": image_hash, "status": {"$ne": "rejected"}})
        
        if existing_bill:
            # Get current balance
            points_result = await tagnpay_client.get_customer_points(mobile_10)
            balance = 0
            if points_result.get("success") and points_result.get("data"):
                balance = int(points_result["data"].get("balance_points", 0))
            
            # EXACT Duplicate Bill Message
            duplicate_msg = f"""Our system shows that this bill has already been processed earlier and rewards have been issued ✅

💳 Your Current Points Balance: {balance}

🛍️ Keep shopping at CP67 Mall to earn more points & enjoy exclusive rewards 🌟"""
            
            buttons = [{"id": "upload_bill", "title": "Upload Bill"}]
            await send_whatsapp_buttons(phone, duplicate_msg, buttons)
            return
        
        # OCR Analysis
        ocr_result = await analyze_bill_image(image_base64)
        
        if not ocr_result.get("success"):
            # OCR failed - manual review
            unclear_msg = """We noticed that the bill image you uploaded is not clear enough to process automatically 🧾

📌 Don't worry — your bill has been submitted to our backend team.

We will manually verify it within 24–48 hours, and your points will be credited once validation is complete ✅

Thank you for your patience and for being a valued member of Homeland Advantage 🌟"""
            
            # Save for manual review
            bill_data = BillData(
                user_id=user["id"],
                user_phone=phone,
                status="manual_review",
                rejection_reason="OCR processing failed",
                image_url=f"data:image/jpeg;base64,{image_base64}",
                image_hash=image_hash
            )
            await db.bills.insert_one(bill_data.model_dump())
            
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
        
        # Determine which mobile number to use for points
        # If bill has customer mobile, use that; otherwise use WhatsApp sender
        points_mobile = mobile_10  # Default to WhatsApp sender
        points_mobile_source = "whatsapp"
        
        if customer_mobile:
            # Clean and validate customer mobile from bill
            clean_customer_mobile = str(customer_mobile).replace(" ", "").replace("-", "").replace("+", "")
            # Extract last 10 digits if longer
            if len(clean_customer_mobile) >= 10:
                clean_customer_mobile = clean_customer_mobile[-10:]
                if clean_customer_mobile.isdigit() and len(clean_customer_mobile) == 10:
                    points_mobile = clean_customer_mobile
                    points_mobile_source = "bill"
                    logger.info(f"Using customer mobile from bill: {points_mobile} (WhatsApp sender: {mobile_10})")
        
        # CHECK: Bill date older than 15 days - Reject immediately
        try:
            bill_date_parsed = datetime.strptime(bill_date, "%Y-%m-%d")
            days_old = (datetime.now() - bill_date_parsed).days
            
            if days_old > 15:
                # Bill is older than 15 days - reject
                old_bill_msg = f"""📋 *Bill Cannot Be Processed*

Thank you for uploading your bill from *{store_name}*.

Unfortunately, this bill dated *{bill_date}* is more than 15 days old and cannot be processed for rewards.

📌 *Policy:* Bills must be uploaded within 15 days of purchase to earn points.

We appreciate your understanding! Please upload your recent bills to continue earning rewards 🛍️✨"""
                
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
                await db.bills.insert_one(bill_data.model_dump())
                
                buttons = [
                    {"id": "upload_bill", "title": "Upload Recent Bill"},
                    {"id": "my_points", "title": "Check Points"}
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
                
                # EXACT Duplicate Bill Message
                duplicate_msg = f"""Our system shows that this bill has already been processed earlier and rewards have been issued ✅

💳 Your Current Points Balance: {balance}

🛍️ Keep shopping at CP67 Mall to earn more points & enjoy exclusive rewards 🌟"""
                
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
                await db.bills.insert_one(bill_data.model_dump())
                
                buttons = [{"id": "upload_bill", "title": "Upload Bill"}]
                await send_whatsapp_buttons(phone, duplicate_msg, buttons)
                return
        
        # FIRST: Show ALL extracted bill details with items
        items_text = ""
        if items and len(items) > 0:
            items_text = "\n📦 *Items:*\n"
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
        
        tax_text = f"\n💵 Tax: ₹{tax}" if tax else ""
        
        bill_details_msg = f"""📋 *Bill Scan Results*

🏬 *Store:* {store_name}
🧾 *Bill No:* {bill_no}
📅 *Date:* {bill_date}
💰 *Amount:* ₹{amount:.2f}{tax_text}
{items_text}
🔍 *Confidence:* {confidence*100:.0f}%

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
            # NOT a CP67 bill - reject and mark as pending
            rejection_reason = "Bill is not from CP67 Mall. Only CP67 Mall bills are eligible for rewards."
            
            reject_msg = f"""❌ *Bill Rejected*

This bill is not from CP67 Mall.

🏬 Store detected: {store_name}

Only bills from shops inside CP67 Mall are eligible for Homeland Advantage rewards.

Please upload a valid CP67 Mall bill to earn points! 🛍️"""
            
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
            await db.bills.insert_one(bill_data.model_dump())
            
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
            
            buttons = [{"id": "upload_bill", "title": "Upload CP67 Bill"}]
            await send_whatsapp_buttons(phone, reject_msg, buttons)
            return
        
        # Check if image is unclear or tampered
        if image_quality == "poor" or confidence < 0.5 or tampering or not is_valid:
            unclear_msg = """We noticed that the bill image you uploaded is not clear enough to process automatically 🧾

📌 Don't worry — your bill has been submitted to our backend team.

We will manually verify it within 24–48 hours, and your points will be credited once validation is complete ✅

Thank you for your patience and for being a valued member of Homeland Advantage 🌟"""
            
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
            await db.bills.insert_one(bill_data.model_dump())
            
            buttons = [
                {"id": "upload_bill", "title": "Upload Bill"},
                {"id": "my_points", "title": "Redeem Points"}
            ]
            await send_whatsapp_buttons(phone, unclear_msg, buttons)
            return
        
        # CHECK: Bill amount > 30000 - Send to pending for manual review
        if amount > 30000:
            high_amount_msg = f"""📋 *Bill Received - Under Review*

Thank you for shopping at *{store_name}*!

🧾 *Bill No:* {bill_no}
📅 *Date:* {bill_date}
💰 *Amount:* ₹{amount:.0f}

⏳ Bills above ₹30,000 require manual verification by our team.

Your bill will be reviewed within 24-48 hours and points will be credited once approved ✅

Thank you for your patience! 🛍️"""
            
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
            await db.bills.insert_one(bill_data.model_dump())
            
            # Send admin notification for high value bill
            admin_alert_msg = f"""🔔 *High Value Bill Alert*

A bill over ₹30,000 has been submitted for review.

🏬 Store: {store_name}
🧾 Bill No: {bill_no}
💰 Amount: ₹{amount:.0f}
📱 User: {phone}

Please review in the admin dashboard."""
            
            background_tasks.add_task(send_whatsapp_text, ADMIN_PHONE, admin_alert_msg)
            
            buttons = [
                {"id": "upload_bill", "title": "Upload Another Bill"},
                {"id": "my_points", "title": "Check Points"}
            ]
            await send_whatsapp_buttons(phone, high_amount_msg, buttons)
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
        await db.bills.insert_one(bill_data.model_dump())
        
        # If brand not found, send admin alert and show processing message to user
        if bill_status == "pending_review" and "Brand" in (tagnpay_error or ""):
            # Send WhatsApp alert to admin
            background_tasks.add_task(send_admin_sms_alert, store_name, bill_no, amount, phone)
            
            # Send processing message to user
            processing_msg = f"""📋 *Bill Received Successfully!*

🏬 Store: {store_name}
🧾 Bill No: {bill_no}
📅 Date: {bill_date}
💰 Amount: ₹{amount:.0f}

⏳ Your bill is being processed. Points will be updated within 24 hours.

💳 Current Points: {total_balance}

Thank you for shopping at CP67 Mall! 🛍️"""
            
            buttons = [
                {"id": "upload_bill", "title": "Upload Another Bill"},
                {"id": "my_points", "title": "Redeem Points"},
                {"id": "customer_support", "title": "Customer Support"}
            ]
            await send_whatsapp_buttons(phone, processing_msg, buttons)
            return
        
        # TEMPORARILY DISABLED 30-day check for testing
        # if bill_status == "pending_review" and "30 days" in (tagnpay_error or ""):
        #     old_bill_msg = f"""📋 *Bill Received*
        # 
        # 🏬 Store: {store_name}
        # 🧾 Bill No: {bill_no}
        # 📅 Date: {bill_date}
        # 💰 Amount: ₹{amount:.0f}
        # 
        # ⚠️ This bill is older than 30 days and cannot be processed for points.
        # 
        # Please upload bills within 30 days of purchase to earn rewards.
        # 
        # 💳 Current Points: {total_balance}"""
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
        
        # Update QR analytics
        if user.get("first_touch_qr"):
            await db.qr_analytics.update_one(
                {"qr_code_id": user["first_touch_qr"]},
                {"$inc": {"bill_uploads": 1}},
                upsert=True
            )
        
        # EXACT Success Message - Always show points credited immediately
        success_msg = f"""Thank you for uploading your bill with Homeland Advantage 🎉

🧾 Bill Details:
🏬 Store: {store_name}
🧾 Bill No.: {bill_no}
📅 Date: {bill_date}
💰 Amount: ₹{amount:.0f}

✨ Points Earned: {points_earned}
💳 Total Balance: {total_balance}

🛍️ Keep shopping at CP67 Mall to earn more rewards & unlock exclusive benefits 🌟"""
        
        buttons = [{"id": "upload_bill", "title": "Upload Bill"}]
        await send_whatsapp_buttons(phone, success_msg, buttons)
        
    except Exception as e:
        logger.error(f"Bill processing error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        
        # Send error message
        error_msg = """We're having trouble processing your bill right now 🧾

📌 Your bill has been submitted to our backend team for manual review.

We will verify it within 24–48 hours ✅

Thank you for your patience! 🌟"""
        
        buttons = [
            {"id": "upload_bill", "title": "Upload Bill"},
            {"id": "my_points", "title": "Redeem Points"}
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
            message = message_data.get("text", {}).get("body", "")
        elif message_type == "interactive":
            interactive = message_data.get("interactive", {})
            button_reply = interactive.get("button_reply", {})
            message = button_reply.get("id", "") or button_reply.get("title", "")
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
            message = request.get("text") or request.get("message", "")
        
        if not message:
            return {"status": "ok", "message": "No message content"}
        
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
        
        # ===== CHECK FOR PARKING QR SCAN =====
        if source_code == "SRC_PARKING_PAY" or "parking validation" in clean_message.lower():
            # PARKING ENTRY FLOW - Generate parking session and send QR
            await process_parking_entry(phone, profile_name or (user.get("name") if user else None), background_tasks)
            return {"status": "ok", "message": "Parking entry processed"}
        
        # ===== FLOW LOGIC =====
        
        if not user:
            # NEW USER - Register
            await log_entry_update(log_entry)
            background_tasks.add_task(process_new_user_registration, phone, profile_name, source_code, qr_data, background_tasks)
            
        else:
            # EXISTING USER
            await db.whatsapp_logs.update_one({"id": log_entry.id}, {"$set": {"user_id": user["id"]}})
            
            msg_lower = clean_message.lower()
            
            if message == "my_points" or "my points" in msg_lower or "redeem" in msg_lower or msg_lower.strip() == "2" or "point" in msg_lower or "balance" in msg_lower:
                # REDEEM POINTS - Call TagnPay API
                points_result = await tagnpay_client.get_customer_points(mobile_10)
                balance = 0
                if points_result.get("success") and points_result.get("data"):
                    balance = int(points_result["data"].get("balance_points", 0))
                
                # Update local DB
                await db.users.update_one({"id": user["id"]}, {"$set": {"balance_points": balance}})
                
                # EXACT Points Message
                points_msg = f"""Your total Loyalty Points are: {balance}

Redeem these points directly at participating retailers 🛍️"""
                
                buttons = [
                    {"id": "upload_bill", "title": "Upload Bill"},
                    {"id": "customer_support", "title": "Customer Support"}
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
            
            elif message == "customer_support" or "support" in msg_lower or "help" in msg_lower or "contact" in msg_lower or msg_lower.strip() == "3":
                # CUSTOMER SUPPORT
                support_msg = """📞 *Customer Support*

We're here to help! Reach out to us through any of these channels:

📧 *Email:* advantage@homelandgroup.org

📱 *Mobile:* 97296 76767

🏢 *Support Desk:* Reach out to our customer support desk for more enquiries at Ground Floor

Our team is happy to assist you with any questions! 💫"""
                
                buttons = [
                    {"id": "upload_bill", "title": "Upload Bill"},
                    {"id": "my_points", "title": "Redeem Points"}
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
                # UPLOAD BILL PROMPT - EXACT Text
                upload_msg = """Great choice! 🎉

Just share your shopping bill here 🛍️ and we'll credit your Homeland Advantage loyalty points instantly ✨

💡 More bills = More points = More rewards 🎁"""
                
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
                # DEFAULT MENU
                menu_msg = f"""Hi {user.get('name', 'there')}! 👋

Welcome back to Homeland Advantage – CP67 Mall!

What would you like to do today?"""
                
                buttons = [
                    {"id": "upload_bill", "title": "Upload Bill"},
                    {"id": "my_points", "title": "Redeem Points"},
                    {"id": "customer_support", "title": "Customer Support"}
                ]
                
                outbound_log = WhatsAppLog(
                    user_id=user["id"],
                    user_phone=phone,
                    direction="outbound",
                    message_type="interactive",
                    content=menu_msg
                )
                await db.whatsapp_logs.insert_one(outbound_log.model_dump())
                
                background_tasks.add_task(send_whatsapp_buttons, phone, menu_msg, buttons)
        
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
            first_touch_source=source_code,
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
        
        response_message = f"""Welcome to Homeland Advantage – CP67 Mall! 🎉

To complete your registration, please share:
1️⃣ Your Name
2️⃣ Your PAN Card Number

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
                    pan = parts[1]
                    
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
                    
                    response_message = f"""Hi {name}! 🎉 Congratulations! 🎉

You are now a valued member of Homeland Advantage – CP67 Mall's exclusive Loyalty Program ✨

Enjoy special privileges, exciting rewards & personalized offers every time you shop with us 🛍️

Shop • Earn • Redeem • Repeat

Welcome to a world of advantage & experiences crafted just for you! 🌟💎

1️⃣ Upload Bill
2️⃣ Redeem Points"""
                else:
                    response_message = """Please share your details in the correct format:
NAME | PAN_NUMBER
Example: Rahul Kumar | ABCDE1234F"""
            else:
                response_message = f"""Welcome back! To complete registration, please share:
1️⃣ Your Name
2️⃣ Your PAN Card Number

Type: NAME | PAN_NUMBER"""
        else:
            # Registered user - handle commands
            msg_lower = request.message.lower()
            if "my points" in msg_lower or "balance" in msg_lower or "2" in msg_lower:
                response_message = f"""Your total Loyalty Points are: {user.get('balance_points', 0):.0f}

Redeem these points directly at participating retailers 🛍️

1️⃣ Upload Bill"""
            elif "upload" in msg_lower or "bill" in msg_lower or "1" in msg_lower:
                response_message = """Great choice! 🎉

Just share your shopping bill here 🛍️ and we'll credit your Homeland Advantage loyalty points instantly ✨

💡 More bills = More points = More rewards 🎁

Please upload an image of your bill."""
            else:
                response_message = f"""Hi {user.get('name', 'there')}! 👋

What would you like to do today?

1️⃣ Upload Bill
2️⃣ Redeem Points

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
        response_message = f"""Our system shows that this bill has already been processed earlier and rewards have been issued ✅

💳 Your Current Points Balance: {user.get('balance_points', 0):.0f}

🛍️ Keep shopping at CP67 Mall to earn more points & enjoy exclusive rewards 🌟

1️⃣ Upload Bill"""
        
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
                response_message = f"""Our system shows that this bill has already been processed earlier and rewards have been issued ✅

💳 Your Current Points Balance: {user.get('balance_points', 0):.0f}

🛍️ Keep shopping at CP67 Mall to earn more points & enjoy exclusive rewards 🌟

1️⃣ Upload Bill"""
            elif data.get("tampering_detected"):
                bill_data.status = "manual_review"
                bill_data.rejection_reason = f"Tampering indicators: {', '.join(data.get('tampering_indicators', []))}"
                response_message = """We noticed some issues with the bill image you uploaded 🧾

📌 Your bill has been submitted to our backend team for review.

We will manually verify it within 24–48 hours, and your points will be credited once validation is complete ✅

Thank you for your patience! 🌟

1️⃣ Upload Bill
2️⃣ Redeem Points"""
            elif data.get("image_quality") == "poor" or bill_data.ocr_confidence < 0.6:
                bill_data.status = "manual_review"
                response_message = """We noticed that the bill image you uploaded is not clear enough to process automatically 🧾

📌 Don't worry — your bill has been submitted to our backend team.

We will manually verify it within 24–48 hours, and your points will be credited once validation is complete ✅

Thank you for your patience and for being a valued member of Homeland Advantage 🌟

1️⃣ Upload Bill
2️⃣ Redeem Points"""
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
                response_message = f"""Thank you for uploading your bill with Homeland Advantage 🎉

🧾 Bill Details:
🏬 Store: {bill_data.store_name or 'N/A'}
🧾 Bill No.: {bill_data.bill_no or 'N/A'}
📅 Date: {bill_data.bill_date or 'N/A'}
💰 Amount: ₹{bill_data.amount:.2f}

✨ Points Earned: {points:.0f}
💳 Total Balance: {new_balance:.0f}

🛍️ Keep shopping at CP67 Mall to earn more rewards & unlock exclusive benefits 🌟

1️⃣ Upload Bill"""
            else:
                bill_data.status = "manual_review"
                response_message = """We couldn't validate the bill details automatically 🧾

📌 Your bill has been submitted to our backend team for review.

We will verify it within 24–48 hours ✅

1️⃣ Upload Bill
2️⃣ Redeem Points"""
        else:
            bill_data.status = "manual_review"
            response_message = """We couldn't extract all bill details 🧾

📌 Your bill has been submitted to our backend team for review.

We will verify it within 24–48 hours ✅

1️⃣ Upload Bill
2️⃣ Redeem Points"""
    else:
        bill_data.status = "manual_review"
        bill_data.ocr_raw_data = {"error": ocr_result.get("error")}
        response_message = """We're having trouble processing your bill image 🧾

📌 Your bill has been submitted to our backend team for review.

We will verify it within 24–48 hours ✅

1️⃣ Upload Bill
2️⃣ Redeem Points"""
    
    await db.bills.insert_one(bill_data.model_dump())
    
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

# ======================== ANALYTICS ROUTES ========================

@api_router.get("/analytics/dashboard")
async def get_dashboard_stats(payload: dict = Depends(verify_jwt_token)):
    """Get dashboard overview statistics"""
    # Total users
    total_users = await db.users.count_documents({})
    registered_users = await db.users.count_documents({"kyc_status": True})
    
    # New vs Existing customers
    new_customers = await db.users.count_documents({"customer_type": "new"})
    existing_customers = await db.users.count_documents({"customer_type": "existing"})
    # For users without customer_type field (legacy), count as new
    legacy_users = await db.users.count_documents({"customer_type": {"$exists": False}})
    new_customers += legacy_users
    
    # Bills stats
    total_bills = await db.bills.count_documents({})
    auto_approved = await db.bills.count_documents({"status": "auto_approved"})
    manual_review = await db.bills.count_documents({"status": "manual_review"})
    pending_review = await db.bills.count_documents({"status": "pending_review"})
    approved = await db.bills.count_documents({"status": "approved"})
    rejected = await db.bills.count_documents({"status": "rejected"})
    duplicate = await db.bills.count_documents({"status": "duplicate"})
    
    # Points issued
    points_pipeline = [
        {"$group": {"_id": None, "total": {"$sum": "$points_issued"}}}
    ]
    points_result = await db.bills.aggregate(points_pipeline).to_list(1)
    total_points_issued = points_result[0]["total"] if points_result else 0
    
    # QR stats
    qr_stats = await db.qr_analytics.find({}, {"_id": 0}).to_list(10)
    total_scans = sum(q.get("scans", 0) for q in qr_stats)
    
    # WhatsApp stats
    total_messages = await db.whatsapp_logs.count_documents({})
    inbound = await db.whatsapp_logs.count_documents({"direction": "inbound"})
    outbound = await db.whatsapp_logs.count_documents({"direction": "outbound"})
    
    # Today's stats
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    today_users = await db.users.count_documents({"created_at": {"$gte": today_start}})
    today_new_customers = await db.users.count_documents({"created_at": {"$gte": today_start}, "customer_type": "new"})
    today_existing_customers = await db.users.count_documents({"created_at": {"$gte": today_start}, "customer_type": "existing"})
    today_bills = await db.bills.count_documents({"created_at": {"$gte": today_start}})
    
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
        }
    }

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

@api_router.get("/whatsapp/logs")
async def get_whatsapp_logs(
    skip: int = 0,
    limit: int = 100,
    phone: Optional[str] = None,
    payload: dict = Depends(verify_jwt_token)
):
    """Get WhatsApp interaction logs"""
    query = {}
    if phone:
        phone_clean = re.sub(r'[^0-9]', '', phone)
        query["user_phone"] = {"$regex": phone_clean}
    
    total = await db.whatsapp_logs.count_documents(query)
    logs = await db.whatsapp_logs.find(query, {"_id": 0}).skip(skip).limit(limit).sort("timestamp", -1).to_list(limit)
    
    return {"logs": logs, "total": total, "skip": skip, "limit": limit}

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
            
            reminder_msg = f"""🅿️ *CP67 Mall Parking*

You already have an active parking session!

📋 *Your Exit Code:*
━━━━━━━━━━━━━━━
*{session_code}*
━━━━━━━━━━━━━━━

⏰ *Entry Time:* {entry_time}

👉 Show this code at the exit counter when leaving.

Have a great time shopping! 🛍️"""
            
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
        
        welcome_msg = f"""🅿️ *Welcome to CP67 Mall Parking!*

Your FREE parking session has started ✅

📋 *Your Exit Code:*
━━━━━━━━━━━━━━━━━━
*{session_code}*
━━━━━━━━━━━━━━━━━━

📅 *Date:* {entry_date}
⏰ *Entry Time:* {entry_time}

👉 *Show this code at the parking exit counter when leaving.*

Enjoy your visit to CP67 Mall! 🛍️✨"""
        
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
            qr_caption = f"""🅿️ *Welcome to CP67 Mall Parking!*

Your FREE parking session has started ✅

📋 *Session Code:* {session_code}
📅 *Date:* {entry_date}
⏰ *Entry Time:* {entry_time}

👆 *Show this QR code at the exit counter*

Enjoy your visit to CP67 Mall! 🛍️✨"""
            
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
        message = f"""🅿️ *CP67 Mall Parking*

Your parking session has started!

📋 *Session Code:* {session_code}
⏰ *Entry Time:* {entry_time}

Please show the QR code below at the exit counter when leaving.

Thank you for visiting CP67 Mall! 🛍️"""
        
        background_tasks.add_task(send_whatsapp_image, clean_phone, qr_image, message)
    
    return {
        "success": True,
        "session_id": session.id,
        "session_code": session_code,
        "entry_time": session.entry_time,
        "qr_image": qr_image
    }

@api_router.post("/parking/validate/{session_code}")
async def validate_parking(session_code: str, scanned_by: Optional[str] = None, background_tasks: BackgroundTasks = None):
    """Validate parking QR code at exit - PUBLIC endpoint for scanner app"""
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
    await db.parking_sessions.update_one(
        {"session_code": session_code},
        {
            "$set": {
                "status": "completed",
                "exit_time": exit_time.isoformat(),
                "duration_minutes": duration_minutes,
                "scanned_by": scanned_by
            }
        }
    )
    
    # Format times for display
    entry_display = entry_time.strftime("%I:%M %p")
    exit_display = exit_time.strftime("%I:%M %p")
    date_display = exit_time.strftime("%d %b %Y")
    
    hours = duration_minutes // 60
    mins = duration_minutes % 60
    duration_display = f"{hours}h {mins}m" if hours > 0 else f"{mins} minutes"
    
    # Send Thank You WhatsApp message to customer
    user_phone = session.get("user_phone")
    if user_phone:
        thank_you_msg = f"""🎉 *Thank You for Visiting CP67 Mall!*

We hope you had a wonderful experience! 🛍️

🅿️ *Parking Summary:*
📅 Date: {date_display}
⏰ Entry: {entry_display}
⏰ Exit: {exit_display}
⏱️ Duration: {duration_display}

✨ Your parking was FREE! ✨

We look forward to seeing you again soon!

💎 *Homeland Advantage* - Your CP67 Mall Loyalty Program"""
        
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
    """Get parking sessions report"""
    query = {}
    if status:
        query["status"] = status
    
    total = await db.parking_sessions.count_documents(query)
    sessions = await db.parking_sessions.find(query, {"_id": 0}).skip(skip).limit(limit).sort("entry_time", -1).to_list(limit)
    
    # Calculate stats
    active_count = await db.parking_sessions.count_documents({"status": "active"})
    completed_today = await db.parking_sessions.count_documents({
        "status": "completed",
        "exit_time": {"$gte": datetime.now(timezone.utc).replace(hour=0, minute=0, second=0).isoformat()}
    })
    
    # Average duration
    avg_pipeline = [
        {"$match": {"status": "completed", "duration_minutes": {"$exists": True}}},
        {"$group": {"_id": None, "avg_duration": {"$avg": "$duration_minutes"}}}
    ]
    avg_result = await db.parking_sessions.aggregate(avg_pipeline).to_list(1)
    avg_duration = round(avg_result[0]["avg_duration"]) if avg_result else 0
    
    return {
        "sessions": sessions,
        "total": total,
        "skip": skip,
        "limit": limit,
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

# Include router
app.include_router(api_router)

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
