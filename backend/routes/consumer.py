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
import random

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
    """Auto-seed consumer data on startup if banners/brands collections are empty"""
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
    # Ensure brands have floor/category data
    try:
        await _enrich_brands()
    except Exception as e:
        logger.error(f"Brand enrichment error: {e}")
    # Always ensure brand logos are set to CDN URLs
    try:
        await _migrate_brand_logos()
    except Exception as e:
        logger.error(f"Logo migration error: {e}")


BRAND_LOGO_MAP = {
    "Adidas": "adidas.com", "Aldo": "aldoshoes.com", "Allen Solly": "allensolly.com",
    "Allen Solly Junior": "allensolly.com", "American Eagle": "ae.com", "Apple": "apple.com",
    "Arrow": "arrowlife.com", "Baskin Robbins": "baskinrobbins.com", "Bata": "bata.in",
    "Bath And Body Works": "bathandbodyworks.com", "Bella Vita": "bellavitaorganic.com",
    "Biba": "bfrands.com", "Bira Taproom": "bfrands.com", "Burger King": "bk.com",
    "Calvin Klein": "calvinklein.com", "Chaayos": "chaayos.com", "Crocs": "crocs.com",
    "Croma": "croma.com", "Da Milano": "damilano.it", "Dominos": "dominos.com",
    "Fab India": "fabindia.com", "Forever New": "forevernew.com.au", "Gant": "gant.com",
    "H&M": "hm.com", "Haldirams": "haldirams.com", "Hamleys": "hamleys.com",
    "Hidesign": "hidesign.com", "Home Centre": "homecentre.com",
    "Hush Puppies": "hushpuppies.com", "Jack And Jones": "jackjones.com",
    "Kazo": "kazo.com", "Kiko Milano": "kikocosmetics.com",
    "Lakme Salon": "lakmesalon.in", "Levis": "levi.com",
    "Lifestyle": "lifestylestores.com", "Louis Philippe": "louisphilippe.com",
    "Mango": "mango.com", "Marks & Spencer": "marksandspencer.in",
    "M&S Food": "marksandspencer.in", "Mcdonald": "mcdonalds.com",
    "Metro Shoes": "metroshoes.net", "Mini So": "miniso.com",
    "Monte Carlo": "montecarlo.in", "Nicobar": "nicobar.com", "Only": "only.com",
    "Pantaloons": "pantaloons.com", "Park Avenue": "parkavenue.co.in",
    "Peter England": "peterengland.com", "Plum": "plumgoodness.com", "Puma": "puma.com",
    "Reliance Digital": "reliancedigital.in", "Samsung": "samsung.com",
    "Sketchers": "skechers.com", "Starbucks": "starbucks.com", "Subway": "subway.com",
    "Sugar": "sugarcosmetics.com", "Superdry": "superdry.com", "Titan": "titan.co.in",
    "Titan Eye+": "titaneyeplus.com", "Titan Tanishq": "tanishq.co.in",
    "Tommy Hilfiger": "tommy.com", "U.S. Polo Assn.": "uspoloassn.com",
    "United Colors Of Benetton": "benetton.com", "Van Heusen": "vanheusenindia.com",
    "Vero Moda": "veromoda.com", "W": "wforwoman.com", "Woodland": "woodland.co.in",
    "Zara": "zara.com", "Licious": "licious.in", "Keventers": "keventers.com",
    "T.g.i. Friday": "tgifridays.com", "Tasva": "tasva.com",
    "Paris Saint-Germain": "psg.fr", "Cookie Man": "cookieman.in",
    "Fizzy Goblet": "fizzygoblet.com", "Fun City": "funcity.in",
    "Lk Bennette": "lkbennett.com", "Miraj Cinemas": "mirajcinemas.com",
    "Naturals": "naturals.in", "Paul": "paul-uk.com", "Satya Paul": "satyapaul.com",
    "Reliance Smart Bazaar": "jiomart.com", "Ethos": "ethoswatches.com",
    "Zimson Watch & Lifestyle": "zimsonwatches.com",
    "Melting Moments": "meltingmoments.in", "House Of Candy": "houseofcandy.in",
    "House of Candy 2nd floor": "houseofcandy.in", "Bonker Corner": "bonkerscorner.com",
    "Berry Brothers": "berrybrothers.in", "Trends": "ajio.com",
    "Dayal Opticals": "dayalopticals.com", "Dayal Opticals Kiosk": "dayalopticals.com",
    "Bhpc": "bhpc.com", "Colorplus": "colorplus.in", "La Pino": "lapinoz.com",
    "Chique": "chiqueindia.com", "Kap Kids": "kapkids.com",
    "Gola Sizzlers": "golasizzlers.com", "Healthy Hut": "healthyhut.in",
    "Chai Choori": "chaichoori.com", "Fluffy Whirls": "fluffywhirls.com",
    "Mama Earth": "mamaearth.in", "Nykaa": "nykaa.com", "Mars": "mars.com",
    "Nailashes": "nailashes.in", "Love Child by Masaba": "lovelychild.in",
    "Oud Arabia": "oudarabia.com", "Oud by Idol": "oudbyidol.com",
    "Pilgrim": "discover.pilgrim.com", "The Man Company": "themancompany.com",
}

async def _migrate_brand_logos():
    """Ensure brands without logos get a CDN fallback. Never overwrite manually uploaded logos."""
    if _db is None:
        return
    updated = 0
    async for brand in _db.brands.find({"brand_name": {"$exists": True, "$ne": ""}}, {"_id": 0, "id": 1, "brand_name": 1, "logo_url": 1}):
        name = brand.get("brand_name", "")
        current_logo = brand.get("logo_url", "")
        
        # Skip if brand already has a custom logo (data URL from admin upload or external URL)
        if current_logo and current_logo.startswith("data:"):
            continue
        if current_logo and not current_logo.startswith("https://www.google.com/s2/favicons") and current_logo.startswith("http"):
            continue
        
        domain = BRAND_LOGO_MAP.get(name, "")
        if domain:
            expected = f"https://www.google.com/s2/favicons?domain={domain}&sz=128"
            if current_logo != expected:
                await _db.brands.update_one(
                    {"id": brand["id"]},
                    {"$set": {"logo_url": expected}}
                )
                updated += 1
        elif not current_logo or "/api/uploads/" in current_logo:
            await _db.brands.update_one(
                {"id": brand["id"]},
                {"$set": {"logo_url": ""}}
            )
    if updated > 0:
        logger.info(f"Set CDN fallback logos for {updated} brands")


BRAND_DIRECTORY = [
    # Ground Floor
    {"brand_name": "Zara", "category": "Fashion", "floor": "Ground Floor", "unit_no": "G-01"},
    {"brand_name": "H&M", "category": "Fashion", "floor": "Ground Floor", "unit_no": "G-02"},
    {"brand_name": "Marks & Spencer", "category": "Fashion", "floor": "Ground Floor", "unit_no": "G-03"},
    {"brand_name": "Calvin Klein", "category": "Fashion", "floor": "Ground Floor", "unit_no": "G-04"},
    {"brand_name": "Tommy Hilfiger", "category": "Fashion", "floor": "Ground Floor", "unit_no": "G-05"},
    {"brand_name": "Levis", "category": "Fashion", "floor": "Ground Floor", "unit_no": "G-06"},
    {"brand_name": "Mango", "category": "Fashion", "floor": "Ground Floor", "unit_no": "G-07"},
    {"brand_name": "Gant", "category": "Fashion", "floor": "Ground Floor", "unit_no": "G-08"},
    {"brand_name": "Superdry", "category": "Fashion", "floor": "Ground Floor", "unit_no": "G-09"},
    {"brand_name": "Forever New", "category": "Fashion", "floor": "Ground Floor", "unit_no": "G-10"},
    {"brand_name": "Vero Moda", "category": "Fashion", "floor": "Ground Floor", "unit_no": "G-11"},
    {"brand_name": "Only", "category": "Fashion", "floor": "Ground Floor", "unit_no": "G-12"},
    {"brand_name": "Jack And Jones", "category": "Fashion", "floor": "Ground Floor", "unit_no": "G-13"},
    {"brand_name": "Bath And Body Works", "category": "Beauty", "floor": "Ground Floor", "unit_no": "G-14"},
    {"brand_name": "Kiko Milano", "category": "Beauty", "floor": "Ground Floor", "unit_no": "G-15"},
    {"brand_name": "Samsung", "category": "Electronics", "floor": "Ground Floor", "unit_no": "G-16"},
    {"brand_name": "Apple", "category": "Electronics", "floor": "Ground Floor", "unit_no": "G-17"},
    {"brand_name": "Titan", "category": "Accessories", "floor": "Ground Floor", "unit_no": "G-18"},
    {"brand_name": "Hidesign", "category": "Accessories", "floor": "Ground Floor", "unit_no": "G-19"},
    {"brand_name": "Da Milano", "category": "Accessories", "floor": "Ground Floor", "unit_no": "G-20"},
    {"brand_name": "Aldo", "category": "Footwear", "floor": "Ground Floor", "unit_no": "G-21"},
    {"brand_name": "Crocs", "category": "Footwear", "floor": "Ground Floor", "unit_no": "G-22"},
    {"brand_name": "Starbucks", "category": "Cafe", "floor": "Ground Floor", "unit_no": "G-23"},
    # First Floor
    {"brand_name": "Adidas", "category": "Sports", "floor": "First Floor", "unit_no": "F-01"},
    {"brand_name": "Puma", "category": "Sports", "floor": "First Floor", "unit_no": "F-02"},
    {"brand_name": "United Colors Of Benetton", "category": "Fashion", "floor": "First Floor", "unit_no": "F-03"},
    {"brand_name": "Allen Solly", "category": "Fashion", "floor": "First Floor", "unit_no": "F-04"},
    {"brand_name": "Van Heusen", "category": "Fashion", "floor": "First Floor", "unit_no": "F-05"},
    {"brand_name": "Louis Philippe", "category": "Fashion", "floor": "First Floor", "unit_no": "F-06"},
    {"brand_name": "Arrow", "category": "Fashion", "floor": "First Floor", "unit_no": "F-07"},
    {"brand_name": "Peter England", "category": "Fashion", "floor": "First Floor", "unit_no": "F-08"},
    {"brand_name": "Park Avenue", "category": "Fashion", "floor": "First Floor", "unit_no": "F-09"},
    {"brand_name": "Pantaloons", "category": "Fashion", "floor": "First Floor", "unit_no": "F-10"},
    {"brand_name": "Lifestyle", "category": "Department Store", "floor": "First Floor", "unit_no": "F-11"},
    {"brand_name": "Bata", "category": "Footwear", "floor": "First Floor", "unit_no": "F-12"},
    {"brand_name": "Metro Shoes", "category": "Footwear", "floor": "First Floor", "unit_no": "F-13"},
    {"brand_name": "Hush Puppies", "category": "Footwear", "floor": "First Floor", "unit_no": "F-14"},
    {"brand_name": "Woodland", "category": "Footwear", "floor": "First Floor", "unit_no": "F-15"},
    {"brand_name": "Sketchers", "category": "Footwear", "floor": "First Floor", "unit_no": "F-16"},
    {"brand_name": "W", "category": "Fashion", "floor": "First Floor", "unit_no": "F-17"},
    {"brand_name": "Biba", "category": "Fashion", "floor": "First Floor", "unit_no": "F-18"},
    {"brand_name": "Fab India", "category": "Fashion", "floor": "First Floor", "unit_no": "F-19"},
    {"brand_name": "Kazo", "category": "Fashion", "floor": "First Floor", "unit_no": "F-20"},
    {"brand_name": "Monte Carlo", "category": "Fashion", "floor": "First Floor", "unit_no": "F-21"},
    {"brand_name": "Nicobar", "category": "Fashion", "floor": "First Floor", "unit_no": "F-22"},
    {"brand_name": "Allen Solly Junior", "category": "Kids", "floor": "First Floor", "unit_no": "F-23"},
    {"brand_name": "Hamleys", "category": "Kids", "floor": "First Floor", "unit_no": "F-24"},
    {"brand_name": "Croma", "category": "Electronics", "floor": "First Floor", "unit_no": "F-25"},
    {"brand_name": "Reliance Digital", "category": "Electronics", "floor": "First Floor", "unit_no": "F-26"},
    {"brand_name": "Titan Eye+", "category": "Accessories", "floor": "First Floor", "unit_no": "F-27"},
    {"brand_name": "Titan Tanishq", "category": "Jewellery", "floor": "First Floor", "unit_no": "F-28"},
    # Second Floor
    {"brand_name": "American Eagle", "category": "Fashion", "floor": "Second Floor", "unit_no": "S-01"},
    {"brand_name": "U.S. Polo Assn.", "category": "Fashion", "floor": "Second Floor", "unit_no": "S-02"},
    {"brand_name": "Colorplus", "category": "Fashion", "floor": "Second Floor", "unit_no": "S-03"},
    {"brand_name": "Bhpc", "category": "Fashion", "floor": "Second Floor", "unit_no": "S-04"},
    {"brand_name": "Tasva", "category": "Fashion", "floor": "Second Floor", "unit_no": "S-05"},
    {"brand_name": "Paris Saint-Germain", "category": "Sports", "floor": "Second Floor", "unit_no": "S-06"},
    {"brand_name": "Satya Paul", "category": "Fashion", "floor": "Second Floor", "unit_no": "S-07"},
    {"brand_name": "Lk Bennette", "category": "Fashion", "floor": "Second Floor", "unit_no": "S-08"},
    {"brand_name": "Fizzy Goblet", "category": "Footwear", "floor": "Second Floor", "unit_no": "S-09"},
    {"brand_name": "Bonker Corner", "category": "Fashion", "floor": "Second Floor", "unit_no": "S-10"},
    {"brand_name": "Trends", "category": "Fashion", "floor": "Second Floor", "unit_no": "S-11"},
    {"brand_name": "Home Centre", "category": "Home & Living", "floor": "Second Floor", "unit_no": "S-12"},
    {"brand_name": "Mini So", "category": "Lifestyle", "floor": "Second Floor", "unit_no": "S-13"},
    {"brand_name": "Ethos", "category": "Accessories", "floor": "Second Floor", "unit_no": "S-14"},
    {"brand_name": "Zimson Watch & Lifestyle", "category": "Accessories", "floor": "Second Floor", "unit_no": "S-15"},
    {"brand_name": "Dayal Opticals", "category": "Accessories", "floor": "Second Floor", "unit_no": "S-16"},
    {"brand_name": "Dayal Opticals Kiosk", "category": "Accessories", "floor": "Second Floor", "unit_no": "S-17"},
    {"brand_name": "Bella Vita", "category": "Beauty", "floor": "Second Floor", "unit_no": "S-18"},
    {"brand_name": "Plum", "category": "Beauty", "floor": "Second Floor", "unit_no": "S-19"},
    {"brand_name": "Sugar", "category": "Beauty", "floor": "Second Floor", "unit_no": "S-20"},
    {"brand_name": "Mama Earth", "category": "Beauty", "floor": "Second Floor", "unit_no": "S-21"},
    {"brand_name": "Nykaa", "category": "Beauty", "floor": "Second Floor", "unit_no": "S-22"},
    {"brand_name": "Pilgrim", "category": "Beauty", "floor": "Second Floor", "unit_no": "S-23"},
    {"brand_name": "Love Child by Masaba", "category": "Beauty", "floor": "Second Floor", "unit_no": "S-24"},
    {"brand_name": "The Man Company", "category": "Grooming", "floor": "Second Floor", "unit_no": "S-25"},
    {"brand_name": "Oud Arabia", "category": "Fragrance", "floor": "Second Floor", "unit_no": "S-26"},
    {"brand_name": "Oud by Idol", "category": "Fragrance", "floor": "Second Floor", "unit_no": "S-27"},
    {"brand_name": "Nailashes", "category": "Beauty", "floor": "Second Floor", "unit_no": "S-28"},
    {"brand_name": "Lakme Salon", "category": "Beauty", "floor": "Second Floor", "unit_no": "S-29"},
    {"brand_name": "Naturals", "category": "Beauty", "floor": "Second Floor", "unit_no": "S-30"},
    {"brand_name": "Fun City", "category": "Entertainment", "floor": "Second Floor", "unit_no": "S-31"},
    {"brand_name": "Kap Kids", "category": "Kids", "floor": "Second Floor", "unit_no": "S-32"},
    {"brand_name": "Chique", "category": "Fashion", "floor": "Second Floor", "unit_no": "S-33"},
    {"brand_name": "Miraj Cinemas", "category": "Entertainment", "floor": "Second Floor", "unit_no": "S-34"},
    # Third Floor / Food Court
    {"brand_name": "Burger King", "category": "Food & Beverage", "floor": "Food Court", "unit_no": "FC-01"},
    {"brand_name": "Mcdonald", "category": "Food & Beverage", "floor": "Food Court", "unit_no": "FC-02"},
    {"brand_name": "Dominos", "category": "Food & Beverage", "floor": "Food Court", "unit_no": "FC-03"},
    {"brand_name": "Subway", "category": "Food & Beverage", "floor": "Food Court", "unit_no": "FC-04"},
    {"brand_name": "Haldirams", "category": "Food & Beverage", "floor": "Food Court", "unit_no": "FC-05"},
    {"brand_name": "Baskin Robbins", "category": "Food & Beverage", "floor": "Food Court", "unit_no": "FC-06"},
    {"brand_name": "Chaayos", "category": "Cafe", "floor": "Food Court", "unit_no": "FC-07"},
    {"brand_name": "Bira Taproom", "category": "Food & Beverage", "floor": "Food Court", "unit_no": "FC-08"},
    {"brand_name": "Paul", "category": "Cafe", "floor": "Food Court", "unit_no": "FC-09"},
    {"brand_name": "T.g.i. Friday", "category": "Food & Beverage", "floor": "Food Court", "unit_no": "FC-10"},
    {"brand_name": "Keventers", "category": "Food & Beverage", "floor": "Food Court", "unit_no": "FC-11"},
    {"brand_name": "Cookie Man", "category": "Food & Beverage", "floor": "Food Court", "unit_no": "FC-12"},
    {"brand_name": "Licious", "category": "Food & Beverage", "floor": "Food Court", "unit_no": "FC-13"},
    {"brand_name": "La Pino", "category": "Food & Beverage", "floor": "Food Court", "unit_no": "FC-14"},
    {"brand_name": "Gola Sizzlers", "category": "Food & Beverage", "floor": "Food Court", "unit_no": "FC-15"},
    {"brand_name": "Healthy Hut", "category": "Food & Beverage", "floor": "Food Court", "unit_no": "FC-16"},
    {"brand_name": "Chai Choori", "category": "Cafe", "floor": "Food Court", "unit_no": "FC-17"},
    {"brand_name": "Fluffy Whirls", "category": "Food & Beverage", "floor": "Food Court", "unit_no": "FC-18"},
    {"brand_name": "Melting Moments", "category": "Food & Beverage", "floor": "Food Court", "unit_no": "FC-19"},
    {"brand_name": "House Of Candy", "category": "Food & Beverage", "floor": "Food Court", "unit_no": "FC-20"},
    {"brand_name": "House of Candy 2nd floor", "category": "Food & Beverage", "floor": "Second Floor", "unit_no": "S-35"},
    {"brand_name": "Berry Brothers", "category": "Food & Beverage", "floor": "Food Court", "unit_no": "FC-21"},
    {"brand_name": "Mars", "category": "Food & Beverage", "floor": "Food Court", "unit_no": "FC-22"},
    # Lower Ground
    {"brand_name": "Reliance Smart Bazaar", "category": "Supermarket", "floor": "Lower Ground", "unit_no": "LG-01"},
    {"brand_name": "M&S Food", "category": "Food & Beverage", "floor": "Lower Ground", "unit_no": "LG-02"},
]

async def _seed_brands():
    """Seed brand directory from master list"""
    if _db is None:
        return
    brands_to_insert = []
    for b in BRAND_DIRECTORY:
        domain = BRAND_LOGO_MAP.get(b["brand_name"], "")
        logo_url = f"https://www.google.com/s2/favicons?domain={domain}&sz=128" if domain else ""
        brands_to_insert.append({
            "id": str(uuid.uuid4()),
            "brand_name": b["brand_name"],
            "category": b.get("category", ""),
            "floor": b.get("floor", ""),
            "unit_no": b.get("unit_no", ""),
            "description": f"{b['brand_name']} at CP67 Mall, Mohali",
            "logo_url": logo_url,
            "cover_image_url": "",
            "timing": "11:00 AM - 9:00 PM",
            "tags": [],
            "atv": 0,
            "is_active": True,
            "is_eligible": True,
            "is_featured": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
    if brands_to_insert:
        await _db.brands.insert_many(brands_to_insert)
        logger.info(f"Seeded {len(brands_to_insert)} brands")


async def _enrich_brands():
    """Update existing brands with floor/category from directory if missing"""
    if _db is None:
        return
    directory_map = {b["brand_name"]: b for b in BRAND_DIRECTORY}
    updated = 0
    async for brand in _db.brands.find({"brand_name": {"$exists": True, "$ne": ""}}, {"_id": 0, "id": 1, "brand_name": 1, "category": 1, "floor": 1, "unit_no": 1, "is_eligible": 1}):
        name = brand.get("brand_name", "")
        info = directory_map.get(name)
        if not info:
            continue
        updates = {}
        if not brand.get("category"):
            updates["category"] = info["category"]
        if not brand.get("floor"):
            updates["floor"] = info["floor"]
        if not brand.get("unit_no"):
            updates["unit_no"] = info.get("unit_no", "")
        if brand.get("is_eligible") is None:
            updates["is_eligible"] = True
        if updates:
            await _db.brands.update_one({"id": brand["id"]}, {"$set": updates})
            updated += 1
    if updated > 0:
        logger.info(f"Enriched {updated} brands with floor/category data")


# ==================== MODELS ====================

class SendOTPRequest(BaseModel):
    phone: str

class VerifyOTPRequest(BaseModel):
    phone: str
    otp: str
    source: Optional[str] = None        # e.g. SRC_MARKETING, SRC_BRANDS, captured from ?src= query param on login
    qr_code: Optional[str] = None       # e.g. QR0124008

class UpdateProfileRequest(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    gender: Optional[str] = None
    dob: Optional[str] = None
    address: Optional[str] = None
    house_no: Optional[str] = None
    landmark: Optional[str] = None
    pincode: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    interests: Optional[List[str]] = None

class RedeemRequest(BaseModel):
    reward_id: str
    points: int

class FavoriteRequest(BaseModel):
    store_id: str


# ==================== AUTH HELPERS ====================

def create_consumer_token(user_id: str, phone: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=90)
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
async def send_otp(request: SendOTPRequest, background_tasks: BackgroundTasks):
    phone = request.phone.strip().replace(" ", "").replace("-", "")
    if not phone.startswith("91"):
        phone = "91" + phone
    phone_10 = phone[-10:]

    # Check if phone is blocked (brand staff)
    blocked = await _db.blocked_phones.find_one({"phone": phone_10})
    if blocked:
        raise HTTPException(status_code=403, detail="This number is not eligible for the Homeland Advantage loyalty program.")

    # App Store / Play Store reviewer bypass (Point 22): skip SMS + Fundle sync
    # for the reviewer number so review teams get an instant success.
    if phone_10 == "9999999999":
        return {"success": True, "message": "OTP sent to your phone", "phone": phone}

    # Generate a 6-digit OTP and persist it (5-min TTL, max 5 attempts)
    from server import send_otp_sms, store_otp
    otp = str(random.randint(100000, 999999))
    await store_otp(phone_10, otp)

    # Send the SMS in the background — Karix occasionally takes 30+ seconds, and
    # we don't want the user staring at a loading spinner on the login screen.
    async def _send_sms_bg(p10: str, code: str):
        try:
            res = await send_otp_sms(p10, code)
            if res.get("success"):
                logger.info(f"OTP SMS sent to {p10}")
            else:
                logger.warning(f"SMS gateway failed for {p10}: {res}")
        except Exception as e:
            logger.warning(f"SMS send error for {p10}: {e}")
    background_tasks.add_task(_send_sms_bg, phone_10, otp)

    # TagnPay sync also runs in the background.
    async def _tagnpay_bg_sync(p10: str):
        try:
            existing = await _tagnpay_client.send_login_otp(p10)
            if not existing.get("success"):
                await _tagnpay_client.register_customer(p10, "Customer", "")
        except Exception as e:
            logger.warning(f"TagnPay sync (non-fatal) failed for {p10}: {e}")
    background_tasks.add_task(_tagnpay_bg_sync, phone_10)

    return {"success": True, "message": "OTP sent to your phone", "phone": phone}


@consumer_router.post("/auth/verify-otp")
async def verify_otp(request: VerifyOTPRequest):
    phone = request.phone.strip().replace(" ", "").replace("-", "")
    if not phone.startswith("91"):
        phone = "91" + phone
    phone_10 = phone[-10:]

    # Check if phone is blocked (brand staff)
    blocked = await _db.blocked_phones.find_one({"phone": phone_10})
    if blocked:
        raise HTTPException(status_code=403, detail="This number is not eligible for the Homeland Advantage loyalty program.")

    # Dev override (testing agent + QA) — read from env, default '1234'
    # + App Store / Play Store reviewer bypass (Point 22): phone 9999999999 → OTP 123456
    from server import verify_stored_otp, OTP_DEV_BYPASS
    APP_STORE_REVIEWER_PHONE = "9999999999"
    APP_STORE_REVIEWER_OTP = "123456"

    is_dev = bool(OTP_DEV_BYPASS) and request.otp == OTP_DEV_BYPASS
    is_reviewer = (phone_10 == APP_STORE_REVIEWER_PHONE and request.otp == APP_STORE_REVIEWER_OTP)

    if not is_dev and not is_reviewer:
        ok = await verify_stored_otp(phone_10, request.otp)
        if not ok:
            raise HTTPException(status_code=400, detail="Invalid OTP. Please try again.")

    # Find or create user
    user = await _db.users.find_one(
        {"phone": {"$in": [phone, phone_10, f"91{phone_10}"]}},
        {"_id": 0}
    )

    is_new = False
    if not user:
        is_new = True
        # Default to SRC_APP if no source code was passed in (= direct app open).
        source_code = (request.source or "SRC_APP").strip().upper()
        if not source_code.startswith("SRC_"):
            source_code = "SRC_APP"
        qr_code_id = request.qr_code.strip() if request.qr_code else None

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
            "kyc_status": True,  # registered locally in CP67
            "onboarding_complete": False,
            "balance_points": 0,
            "total_earned_points": 0,
            "referral_code": f"CP{phone_10[-6:]}",
            "referred_by": None,
            "first_touch_source": source_code,
            "first_touch_qr": qr_code_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "last_active": datetime.now(timezone.utc).isoformat()
        }
        await _db.users.insert_one(user)
    else:
        update_set = {
            "last_active": datetime.now(timezone.utc).isoformat(),
            "app_registered": True,
        }
        # Backfill source if missing for older users registered before this fix
        if not user.get("first_touch_source"):
            update_set["first_touch_source"] = (
                request.source.strip().upper() if request.source else "SRC_APP"
            )
            if not update_set["first_touch_source"].startswith("SRC_"):
                update_set["first_touch_source"] = "SRC_APP"
        if not user.get("first_touch_qr") and request.qr_code:
            update_set["first_touch_qr"] = request.qr_code.strip()
        await _db.users.update_one({"id": user["id"]}, {"$set": update_set})

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
    if request.house_no is not None:
        update_data["house_no"] = request.house_no
    if request.landmark is not None:
        update_data["landmark"] = request.landmark
    if request.pincode is not None:
        update_data["pincode"] = request.pincode
    if request.city is not None:
        update_data["city"] = request.city
    if request.state is not None:
        update_data["state"] = request.state

    if update_data:
        update_data["onboarding_complete"] = True
        update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
        await _db.users.update_one({"id": current_user["sub"]}, {"$set": update_data})

    user = await _db.users.find_one({"id": current_user["sub"]}, {"_id": 0})
    return {"success": True, "user": {k: v for k, v in user.items() if k != "_id"}}


@consumer_router.delete("/account")
async def delete_consumer_account(current_user=Depends(get_current_consumer)):
    """Apple App Store 5.1.1(v) compliance — user can delete their account
    from within the app. This is a hard delete of PII with a tombstone kept
    so we can detect re-registration abuse and honour any legal holds.

    Deletes: profile PII, favourites, notifications, push subscriptions,
    session tokens. Retains (audit trail): bill history, redemption txns,
    tagnpay Fundle ledger — these are transactional records governed by
    RBI-compliant retention policy but are anonymised (user_id kept, PII stripped).
    """
    user_id = current_user["sub"]
    user = await _db.users.find_one({"id": user_id}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    phone = user.get("phone", "")
    now_iso = datetime.now(timezone.utc).isoformat()

    # 1. Anonymise the user record (retain id for FK integrity in bills/txns)
    await _db.users.update_one(
        {"id": user_id},
        {"$set": {
            "name": "Deleted User",
            "email": None,
            "phone_deleted_hash": phone,  # keep hashed for abuse-prevention only
            "phone": f"DELETED-{user_id[:8]}",
            "gender": None,
            "dob": None,
            "address": None,
            "house_no": None,
            "landmark": None,
            "pincode": None,
            "city": None,
            "state": None,
            "interests": [],
            "is_deleted": True,
            "deleted_at": now_iso,
            "onboarding_complete": False,
        }}
    )

    # 2. Hard-delete anything user-controlled with zero downstream dependency
    await _db.favorites.delete_many({"user_id": user_id})
    await _db.notifications.delete_many({"user_id": user_id})
    await _db.push_subscriptions.delete_many({"user_id": user_id})
    await _db.otp_codes.delete_many({"phone": phone})

    # 3. Log the deletion for compliance audit trail
    await _db.deletion_log.insert_one({
        "user_id": user_id,
        "deleted_at": now_iso,
        "reason": "user_requested_via_app",
    })

    return {"success": True, "message": "Your account and personal data have been deleted."}


@consumer_router.get("/pincode/{pincode}")
async def lookup_pincode(pincode: str):
    """Lookup city and state from pincode using India Post API"""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"https://api.postalpincode.in/pincode/{pincode}")
            data = resp.json()
            if data and data[0].get("Status") == "Success" and data[0].get("PostOffice"):
                po = data[0]["PostOffice"][0]
                return {"success": True, "city": po.get("District", ""), "state": po.get("State", "")}
    except Exception:
        pass
    return {"success": False, "city": "", "state": ""}



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

    # Banners (random order each time)
    banners = []
    async for b in _db.banners.find({"is_active": True}, {"_id": 0}):
        banners.append(b)
    random.shuffle(banners)

    # Featured stores — prefer brands collection (Point 33: admin's is_featured toggle on a brand must be reflected here)
    featured_stores = []
    async for b in _db.brands.find(
        {"is_active": {"$ne": False}, "is_featured": True, "hidden_from_app": {"$ne": True}, "brand_name": {"$exists": True, "$ne": ""}},
        {"_id": 0}
    ).limit(8):
        featured_stores.append({
            "id": b.get("id"),
            "name": b.get("brand_name"),
            "category": b.get("category") or "General",
            "cover_image": b.get("cover_image_url") or b.get("logo_url") or "",
            "logo_url": b.get("logo_url") or "",
            "is_featured": True
        })

    # Fallback: if no featured brands, pull first few from brands collection (respecting hidden_from_app)
    if not featured_stores:
        async for b in _db.brands.find(
            {"is_active": {"$ne": False}, "hidden_from_app": {"$ne": True}, "brand_name": {"$exists": True, "$ne": ""}},
            {"_id": 0}
        ).limit(8):
            featured_stores.append({
                "id": b.get("id"),
                "name": b.get("brand_name"),
                "category": b.get("category") or "General",
                "cover_image": b.get("cover_image_url") or b.get("logo_url") or "",
                "logo_url": b.get("logo_url") or "",
                "is_featured": True
            })

    # Trending offers
    offers = []
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
    """List stores from brands collection with filters"""
    # Point 32: brands marked hidden_from_app are excluded from the consumer directory
    query = {
        "is_active": {"$ne": False},
        "hidden_from_app": {"$ne": True},
        "brand_name": {"$exists": True, "$ne": ""},
    }
    if category:
        query["category"] = category
    if floor:
        query["floor"] = floor
    if search:
        query["brand_name"] = {"$regex": search, "$options": "i"}

    stores = []
    async for b in _db.brands.find(query, {"_id": 0}).sort("brand_name", 1):
        stores.append({
            "id": b.get("id"),
            "name": b.get("brand_name"),
            "category": b.get("category") or "",
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

    EXCLUDED_FLOORS = {"Food Court"}
    _list_filter = {"is_active": {"$ne": False}, "hidden_from_app": {"$ne": True}, "brand_name": {"$exists": True, "$ne": ""}}
    categories = sorted([c for c in await _db.brands.distinct("category", _list_filter) if c])
    floors_list = sorted([f for f in await _db.brands.distinct("floor", _list_filter) if f and f not in EXCLUDED_FLOORS])
    # Ensure Third Floor is always available
    if "Third Floor" not in floors_list:
        floors_list.append("Third Floor")
    floor_order = ["First Floor", "Ground Floor", "Lower Ground", "Second Floor", "Third Floor"]
    floors_list.sort(key=lambda f: floor_order.index(f) if f in floor_order else 99)

    return {"stores": stores, "categories": categories, "floors": floors_list}


@consumer_router.get("/stores/{store_id}")
async def get_store(store_id: str):
    # Try brands collection first (primary data source)
    brand = await _db.brands.find_one({"id": store_id}, {"_id": 0})
    if not brand:
        brand = await _db.stores.find_one({"id": store_id, "is_active": True}, {"_id": 0})
    if not brand:
        raise HTTPException(status_code=404, detail="Store not found")

    store = {
        "id": brand.get("id"),
        "name": brand.get("brand_name") or brand.get("name"),
        "category": brand.get("category") or "",
        "floor": brand.get("floor") or "",
        "unit_no": brand.get("unit_no") or "",
        "description": brand.get("description") or "",
        "cover_image": brand.get("cover_image_url") or brand.get("cover_image") or "",
        "logo_url": brand.get("logo_url") or "",
        "timing": brand.get("timing") or "11:00 AM - 9:00 PM",
        "tags": brand.get("tags") or [],
        "is_featured": brand.get("is_featured", False),
        "is_active": True
    }

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


@consumer_router.get("/campaigns/active")
async def list_active_campaigns():
    """Public: currently active campaigns for consumer display (Live Now banner)."""
    now_iso = datetime.now(timezone.utc).isoformat()
    campaigns = []
    async for c in _db.campaigns.find({"is_active": True}, {"_id": 0}).sort("end_date", 1):
        start = c.get("start_date") or ""
        end = c.get("end_date") or ""
        end_check = end + "T23:59:59" if len(end) == 10 else end
        start_check = start + "T00:00:00" if len(start) == 10 else start
        if start_check and start_check > now_iso:
            continue
        if end_check and end_check < now_iso:
            continue
        campaigns.append(c)
    return {"campaigns": campaigns}


@consumer_router.get("/app-settings")
async def get_consumer_app_settings():
    """Public: current app settings (font family + size scale) so the PWA can
    theme itself according to admin-set values."""
    defaults = {
        "heading_font_family": "Antique Olive",
        "heading_font_size_scale": 1.0,
        "heading_font_weight": 700,
        "content_font_family": "Antique Olive",
        "content_font_size_scale": 1.0,
        "content_font_weight": 400,
    }
    doc = await _db.app_settings.find_one({"id": "app"}, {"_id": 0})
    if not doc:
        return {"settings": defaults}
    for k, v in defaults.items():
        if doc.get(k) in (None, ""):
            doc[k] = v
    return {"settings": doc}


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
        {"name": "Bronze", "min": 0, "max": 2499, "color": "#B87333", "next": "Silver", "next_at": 2500},
        {"name": "Silver", "min": 2500, "max": 9999, "color": "#A8A9AD", "next": "Gold", "next_at": 10000},
        {"name": "Gold", "min": 10000, "max": 24999, "color": "#DAA520", "next": "Platinum", "next_at": 25000},
        {"name": "Platinum", "min": 25000, "max": 49999, "color": "#C4C4C0", "next": "Titanium", "next_at": 50000},
        {"name": "Titanium", "min": 50000, "max": 99999, "color": "#54545A", "next": "Diamond", "next_at": 100000},
        {"name": "Diamond", "min": 100000, "max": 249999, "color": "#A7D8DE", "next": "Privilege", "next_at": 250000},
        {"name": "Privilege", "min": 250000, "max": 999999, "color": "#6B3FA0", "next": None, "next_at": None},
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
    return await _handle_bill_upload_bytes(contents, background_tasks, current_user)


class BillUploadJSON(BaseModel):
    """JSON alternative to multipart upload — handy for Android WebView clients
    where multipart FormData can be finicky. `image_base64` may be either a raw
    base64 string OR a full data-URL like 'data:image/jpeg;base64,...'."""
    image_base64: str


@consumer_router.post("/bills/upload-base64")
async def upload_bill_base64(
    payload: BillUploadJSON,
    background_tasks: BackgroundTasks,
    current_user=Depends(get_current_consumer)
):
    """Bill upload via JSON base64 body — reliable path for Android WebView.
    Point 11: Bill upload from app was failing due to multipart edge cases
    in older Android WebViews. This endpoint accepts the base64 directly."""
    b64 = payload.image_base64 or ""
    if b64.startswith("data:"):
        # Strip 'data:image/jpeg;base64,' prefix
        try:
            b64 = b64.split(",", 1)[1]
        except IndexError:
            raise HTTPException(status_code=400, detail="Malformed data URL")
    try:
        contents = base64.b64decode(b64)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid base64 image")
    return await _handle_bill_upload_bytes(contents, background_tasks, current_user)


async def _handle_bill_upload_bytes(contents: bytes, background_tasks: BackgroundTasks, current_user):
    """Shared bill upload flow used by both multipart and JSON entry points."""
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
    """Background task to process bill via Gemini OCR — uses the same
    analyze_bill_image function as the WhatsApp upload flow (server.py),
    so the consumer app uses the SAME working OCR pipeline.
    """
    try:
        # Import lazily to avoid circular imports (server imports consumer router)
        from server import analyze_bill_image

        ocr_result = await analyze_bill_image(image_base64)
        if not ocr_result.get("success") or not ocr_result.get("data"):
            err = ocr_result.get("error", "OCR failed")
            logger.error(f"OCR failed for bill {bill_id}: {err}")
            await _db.bills.update_one({"id": bill_id}, {"$set": {
                "status": "manual_review",
                "rejection_reason": f"OCR failed: {err}"
            }})
            await send_app_notification(user_id, "Bill Under Review",
                "We couldn't auto-read your bill. Our team will review it shortly.", "bill")
            return

        ocr_data = ocr_result["data"]
        store_name = ocr_data.get("store_name") or "Unknown"
        bill_no = ocr_data.get("bill_no") or "N/A"
        bill_no_norm = re.sub(r"[^A-Za-z0-9]+", "", str(bill_no)).lower() if bill_no else ""
        bill_date = ocr_data.get("bill_date") or ""
        try:
            amount = float(ocr_data.get("amount") or 0)
        except (TypeError, ValueError):
            amount = 0.0
        # analyze_bill_image uses `contains_cp67`, not `is_cp67`
        is_cp67 = bool(ocr_data.get("contains_cp67") or ocr_data.get("is_cp67"))
        confidence = float(ocr_data.get("confidence_score") or ocr_data.get("confidence") or 0)

        phone_10 = phone[-10:]

        # Point 16: Prevent duplicate credit — check if another APPROVED bill
        # for this user/store has the same normalised bill_no (colon/space etc
        # stripped). This closes the 'INV:12345' vs 'INV12345' loophole.
        if bill_no_norm and store_name and store_name != "Unknown":
            dup = await _db.bills.find_one({
                "user_id": user_id,
                "store_name": store_name,
                "bill_no_normalized": bill_no_norm,
                "id": {"$ne": bill_id},
                "status": {"$in": ["auto_approved", "approved"]}
            }, {"_id": 0, "id": 1, "bill_no": 1})
            if dup:
                await _db.bills.update_one({"id": bill_id}, {"$set": {
                    "status": "rejected",
                    "store_name": store_name,
                    "bill_no": bill_no,
                    "bill_no_normalized": bill_no_norm,
                    "bill_date": bill_date,
                    "amount": amount,
                    "ocr_confidence": confidence,
                    "ocr_raw_data": ocr_data,
                    "rejection_reason": f"Duplicate — same bill already credited (bill_no={dup.get('bill_no')})"
                }})
                await send_app_notification(user_id, "Bill Rejected",
                    "This bill has already been credited previously. Only one submission per bill is allowed.", "bill")
                return

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

        # Mobile number mismatch check: if invoice has a customer mobile and it
        # doesn't match the uploader's number (last 10 digits), send to pending review.
        invoice_mobile = ocr_data.get("customer_mobile")
        invoice_mobile_clean = None
        if invoice_mobile:
            digits_only = "".join(ch for ch in str(invoice_mobile) if ch.isdigit())
            if len(digits_only) >= 10:
                invoice_mobile_clean = digits_only[-10:]

        if invoice_mobile_clean and invoice_mobile_clean != phone_10:
            await _db.bills.update_one({"id": bill_id}, {"$set": {
                "status": "pending_review",
                "store_name": store_name,
                "bill_no": bill_no,
                "bill_date": bill_date,
                "amount": amount,
                "ocr_confidence": confidence,
                "ocr_raw_data": ocr_data,
                "invoice_mobile": invoice_mobile_clean,
                "rejection_reason": "Mob No not matched with Invoice"
            }})
            await send_app_notification(user_id, "Bill Under Review",
                f"Your bill from {store_name} is under review (mobile on invoice does not match your number). Our team will verify it shortly.",
                "bill")
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
                "rejection_reason": "High value bill - requires manual verification"
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
                "rejection_reason": "Bill amount exceeds brand ATV"
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

        # ------- Campaign Engine: apply active multipliers/bonuses -------
        campaign_bonus_points = 0
        applied_campaigns = []
        if points_earned > 0:
            is_first = await _db.bills.count_documents({"user_id": user_id, "status": {"$in": ["auto_approved", "approved"]}}) == 0
            camp = await _apply_campaign_bonus_local(
                bill_amount=amount,
                base_points=points_earned,
                store_name=store_name,
                is_first_bill=is_first,
            )
            campaign_bonus_points = camp["bonus_points"]
            applied_campaigns = camp["applied_campaigns"]
            points_earned = camp["final_points"]
            # Sync bonus to user's local balance (Fundle balance already has base)
            if campaign_bonus_points > 0:
                await _db.users.update_one(
                    {"id": user_id},
                    {"$inc": {"balance_points": campaign_bonus_points, "total_earned_points": campaign_bonus_points}}
                )

        update_set = {
            "status": status,
            "store_name": store_name,
            "bill_no": bill_no,
            "bill_no_normalized": bill_no_norm,
            "bill_date": bill_date,
            "amount": amount,
            "points_issued": points_earned,
            "ocr_confidence": confidence,
            "ocr_raw_data": ocr_data,
            "processed_at": datetime.now(timezone.utc).isoformat()
        }
        if campaign_bonus_points > 0:
            update_set["campaign_bonus"] = campaign_bonus_points
            update_set["applied_campaigns"] = applied_campaigns
        await _db.bills.update_one({"id": bill_id}, {"$set": update_set})

        # Staff Incentive Sync — creates bill_upload incentive if attribution window active,
        # and activates any pending registration incentive on approval.
        try:
            from routes.staff import create_or_activate_bill_incentive, sync_incentive_on_bill_status_change
            import re as _re
            mobile_10 = _re.sub(r"\D", "", phone or "")[-10:]
            await create_or_activate_bill_incentive(bill_id, mobile_10, status)
            await sync_incentive_on_bill_status_change(bill_id, status)
        except Exception as _e:
            logger.warning(f"staff-sync (consumer ocr) failed: {_e}")

        if status == "approved":
            bonus_txt = f" (incl. +{campaign_bonus_points} campaign bonus)" if campaign_bonus_points > 0 else ""
            await send_app_notification(user_id, "Points Earned!",
                f"You earned {points_earned} points{bonus_txt} from your purchase at {store_name}!", "points")

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


async def _apply_campaign_bonus_local(bill_amount: float, base_points: int,
                                       store_name: Optional[str] = None,
                                       is_first_bill: bool = False) -> Dict:
    """Apply active campaign multipliers/bonuses to Fundle-earned points (consumer route local copy).
    Kept in-file to avoid circular imports with server.py."""
    if base_points <= 0 and not is_first_bill:
        return {"final_points": base_points, "bonus_points": 0, "applied_campaigns": []}
    now_iso = datetime.now(timezone.utc).isoformat()
    brand_category = None
    brand_id = None
    if store_name:
        brand = await _db.brands.find_one(
            {"brand_name": {"$regex": f"^{re.escape(store_name)}$", "$options": "i"}, "is_active": True},
            {"_id": 0, "id": 1, "category": 1},
        )
        if brand:
            brand_category = (brand.get("category") or "").strip().lower()
            brand_id = brand.get("id")
    applied = []
    multiplier_extra = 0
    total_bonus = 0
    async for c in _db.campaigns.find({"is_active": True}, {"_id": 0}):
        start = c.get("start_date") or ""
        end = c.get("end_date") or ""
        end_check = end + "T23:59:59" if len(end) == 10 else end
        start_check = start + "T00:00:00" if len(start) == 10 else start
        if start_check and start_check > now_iso:
            continue
        if end_check and end_check < now_iso:
            continue
        if bill_amount < (c.get("min_spend") or 0):
            continue
        cats = c.get("applicable_categories")
        if cats:
            if not brand_category or brand_category not in [x.strip().lower() for x in cats]:
                continue
        brands = c.get("applicable_brand_ids")
        if brands:
            if not brand_id or brand_id not in brands:
                continue
        ctype = c.get("campaign_type")
        if ctype == "first_visit" and not is_first_bill:
            continue
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
    return {"final_points": int(base_points + multiplier_extra + total_bonus),
            "bonus_points": int(multiplier_extra + total_bonus),
            "applied_campaigns": applied}


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


# ==================== PUSH NOTIFICATION SUBSCRIPTIONS ====================
# Stores Web Push subscription endpoints so that backend can send pushes
# (via FCM/Web Push) once a VAPID key + service-account JSON are configured.
# The save endpoint is also useful for analytics ("how many users opted-in").

class PushSubscriptionRequest(BaseModel):
    endpoint: str
    keys: Optional[Dict[str, str]] = None  # { p256dh, auth }
    user_agent: Optional[str] = None
    platform: Optional[str] = None  # 'pwa' | 'twa' | 'web'


@consumer_router.post("/push/subscribe")
async def push_subscribe(payload: PushSubscriptionRequest,
                          current_user=Depends(get_current_consumer)):
    """Save (idempotently) the user's push subscription endpoint."""
    user_id = current_user["sub"]
    phone = current_user.get("phone")
    doc = {
        "user_id": user_id,
        "phone": phone,
        "endpoint": payload.endpoint,
        "keys": payload.keys or {},
        "user_agent": payload.user_agent or "",
        "platform": payload.platform or "pwa",
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    await _db.push_subscriptions.update_one(
        {"endpoint": payload.endpoint},
        {"$set": doc, "$setOnInsert": {"created_at": doc["updated_at"]}},
        upsert=True
    )
    # Flag user as having opted in to push so we can target them later
    await _db.users.update_one(
        {"id": user_id},
        {"$set": {"push_opt_in": True, "push_opt_in_at": doc["updated_at"]}}
    )
    return {"success": True}


@consumer_router.post("/push/unsubscribe")
async def push_unsubscribe(payload: PushSubscriptionRequest,
                            current_user=Depends(get_current_consumer)):
    await _db.push_subscriptions.delete_many({
        "user_id": current_user["sub"],
        "endpoint": payload.endpoint
    })
    return {"success": True}


@consumer_router.get("/push/status")
async def push_status(current_user=Depends(get_current_consumer)):
    count = await _db.push_subscriptions.count_documents({"user_id": current_user["sub"]})
    return {"subscribed": count > 0, "endpoints": count}


class APNsRegisterRequest(BaseModel):
    apns_token: str
    bundle_id: Optional[str] = None
    device_model: Optional[str] = None
    os_version: Optional[str] = None
    app_version: Optional[str] = None


@consumer_router.post("/push/apns/register")
async def register_apns_token(payload: APNsRegisterRequest,
                               current_user=Depends(get_current_consumer)):
    """Register the iOS APNs device token. Called by the iOS WKWebView shell
    once Apple issues a device token (see AppDelegate.swift → __cp67APNsToken).
    Same shape as the web-push endpoint so admin fan-out treats them uniformly."""
    user_id = current_user["sub"]
    phone = current_user.get("phone")
    now_iso = datetime.now(timezone.utc).isoformat()
    doc = {
        "user_id": user_id,
        "phone": phone,
        "endpoint": f"apns:{payload.apns_token}",
        "apns_token": payload.apns_token,
        "keys": {},
        "user_agent": f"{payload.device_model or 'iOS'} / {payload.os_version or ''}",
        "platform": "ios",
        "bundle_id": payload.bundle_id or "com.fundle.cp67ios",
        "app_version": payload.app_version or "",
        "updated_at": now_iso,
    }
    await _db.push_subscriptions.update_one(
        {"endpoint": doc["endpoint"]},
        {"$set": doc, "$setOnInsert": {"created_at": now_iso}},
        upsert=True,
    )
    await _db.users.update_one(
        {"id": user_id},
        {"$set": {"push_opt_in": True, "push_opt_in_at": now_iso, "ios_apns_token": payload.apns_token}}
    )
    return {"success": True}


@consumer_router.post("/push/apns/test")
async def send_apns_test(current_user=Depends(get_current_consumer)):
    """Send a test push to the caller's registered iOS device — useful during
    TestFlight beta. Requires APNs env vars to be configured; otherwise
    returns success=False with reason='not_configured'."""
    from services.apns_client import send_apns, is_configured
    if not is_configured():
        return {"success": False, "reason": "not_configured",
                "hint": "Set APNS_KEY_ID / APNS_TEAM_ID / APNS_KEY_P8 in backend/.env"}

    sub = await _db.push_subscriptions.find_one(
        {"user_id": current_user["sub"], "platform": "ios"},
        sort=[("updated_at", -1)],
    )
    if not sub or not sub.get("apns_token"):
        raise HTTPException(status_code=404, detail="No iOS device registered for this account")

    r = await send_apns(
        device_token=sub["apns_token"],
        title="Homeland Advantage",
        body="Test push — you're all set to receive rewards updates.",
        data={"kind": "test"},
    )
    return {"success": r.get("success"), "status": r.get("status"), "detail": r.get("body")}


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

    if filter_type in ("all", "expired"):
        async for e in _db.expired_points.find(
            {"user_phone": {"$in": [current_user["phone"], phone_10, f"91{phone_10}"]}},
            {"_id": 0}
        ).sort("expired_at", -1).limit(100):
            transactions.append({
                "id": e.get("id", ""),
                "type": "expired",
                "description": e.get("reason", "Points expired"),
                "store_name": "",
                "amount": 0,
                "points": -(e.get("points", 0)),
                "status": "expired",
                "date": e.get("expired_at", e.get("created_at"))
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



# ==================== PARTICIPATING BRANDS (REDEMPTION) ====================

@consumer_router.get("/participating-brands")
async def get_participating_brands(
    search: str = "",
    floor: str = "",
    category: str = "",
):
    """Get participating brands for redemption with search and filters"""
    query = {"brand_name": {"$exists": True, "$ne": ""}, "is_eligible": {"$ne": False}}
    if search:
        query["brand_name"] = {"$regex": search, "$options": "i"}
    if floor:
        query["floor"] = floor
    if category and category != "All":
        query["category"] = category

    backend_url = os.environ.get("BACKEND_PUBLIC_URL", "")

    brands = []
    async for b in _db.brands.find(query, {"_id": 0}).sort("brand_name", 1):
        logo = b.get("logo_url", "")
        # Normalize local paths to absolute URLs
        if logo and logo.startswith("/api/uploads/"):
            logo = backend_url + logo
        brands.append({
            "id": b.get("id", ""),
            "name": b.get("brand_name", ""),
            "category": b.get("category", ""),
            "floor": b.get("floor", ""),
            "logo_url": logo,
            "unit_no": b.get("unit_no", ""),
        })

    # Get unique floors and categories for filter dropdowns
    EXCLUDED_FLOORS = {"Food Court"}
    all_floors = []
    all_categories = []
    async for b in _db.brands.find({"brand_name": {"$exists": True, "$ne": ""}, "is_eligible": {"$ne": False}}, {"_id": 0, "floor": 1, "category": 1}):
        if b.get("floor") and b["floor"] not in all_floors and b["floor"] not in EXCLUDED_FLOORS:
            all_floors.append(b["floor"])
        if b.get("category") and b["category"] not in all_categories:
            all_categories.append(b["category"])

    floor_order = ["Lower Ground", "Ground Floor", "First Floor", "Second Floor", "Third Floor"]
    all_floors.sort(key=lambda f: floor_order.index(f) if f in floor_order else 99)
    # Ensure Third Floor is always available
    if "Third Floor" not in all_floors:
        all_floors.append("Third Floor")
    all_categories.sort()

    return {
        "brands": brands,
        "total": len(brands),
        "filters": {
            "floors": all_floors,
            "categories": all_categories,
        }
    }



# ==================== MALL MAP & AMENITIES ====================

@consumer_router.get("/mall-map")
async def get_mall_map(current_user=Depends(get_current_consumer)):
    """Get floor-wise brand locations for mall map"""
    floors = {}
    async for brand in _db.brands.find(
        {"brand_name": {"$exists": True, "$ne": ""}},
        {"_id": 0, "brand_name": 1, "floor": 1, "category": 1, "logo_url": 1}
    ):
        floor = brand.get("floor") or "Other"
        if floor not in floors:
            floors[floor] = []
        floors[floor].append({
            "name": brand["brand_name"],
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
            {"name": "Washroom - Ground Floor", "location": "Zone 4", "floor": "Ground Floor"},
            {"name": "Washroom - First Floor", "location": "Zone 4", "floor": "First Floor"},
            {"name": "Washroom - Second Floor", "location": "Zone 2 & Zone 4", "floor": "Second Floor"},
            {"name": "Washroom - Third Floor", "location": "Zone 1 & Zone 4", "floor": "Third Floor"},
            {"name": "Washroom - 4th Floor", "location": "Zone 4", "floor": "4th Floor"},
        ]},
        {"category": "Services", "items": [
            {"name": "Customer Help Desk", "location": "Ground Floor", "floor": "Ground Floor"},
            {"name": "Lost & Found", "location": "Ground Floor, Security Office", "floor": "Ground Floor"},
            {"name": "Wheelchairs", "location": "Available on request at Help Desk", "floor": "Ground Floor"},
            {"name": "Baby Prams", "location": "Available on request at Help Desk", "floor": "Ground Floor"},
            {"name": "Cold Towel Service", "location": "Available on request", "floor": "Ground Floor"},
            {"name": "Baby Care Room", "location": "Available on request", "floor": "Ground Floor"},
            {"name": "Handicap Washrooms", "location": "Available on all floors", "floor": "All Floors"},
            {"name": "Drinking Water Spouts", "location": "Available on all floors", "floor": "All Floors"},
            {"name": "Free EV Car Parking", "location": "Basement Levels", "floor": "Basement"},
            {"name": "Free EV Charging Points", "location": "Basement Levels", "floor": "Basement"},
        ]},
        {"category": "Connectivity", "items": [
            {"name": "Free WiFi", "location": "Available throughout the mall", "floor": "All Floors"},
            {"name": "Mobile Charging Ports", "location": "Available on multiple floors", "floor": "All Floors"},
        ]},
        {"category": "Parking & EV Services", "items": [
            {"name": "Basement Parking", "location": "B1 & B2 Levels", "floor": "Basement"},
            {"name": "Valet Parking", "location": "Main Entrance", "floor": "Ground Floor"},
            {"name": "EV Charging Station", "location": "Basement Levels", "floor": "Basement"},
        ]},
        {"category": "Emergency", "items": [
            {"name": "First Aid", "location": "Ground Floor, Security Office", "floor": "Ground Floor"},
        ]},
    ]
    return {"amenities": amenities}


# ==================== REFERRAL SYSTEM ====================

@consumer_router.get("/referral")
async def get_referral_info(current_user=Depends(get_current_consumer)):
    """Get user's referral info and stats (uses live admin-configured values)"""
    from routes.admin_diy import get_live_referral_config
    cfg = await get_live_referral_config()
    referrer_pts = int(cfg.get("referrer_points", 50))

    user = await _db.users.find_one({"id": current_user["sub"]}, {"_id": 0})
    referral_code = user.get("referral_code", "")

    # Count successful referrals
    referral_count = await _db.users.count_documents({"referred_by": referral_code})

    # Referral bonus points earned — uses live admin config
    bonus_earned = referral_count * referrer_pts

    return {
        "referral_code": referral_code,
        "referral_link": f"{os.environ.get('BACKEND_PUBLIC_URL', '')}/app/welcome?ref={referral_code}",
        "total_referrals": referral_count,
        "bonus_points_earned": bonus_earned,
        "points_per_referral": referrer_pts,
        "referee_points": int(cfg.get("referee_points", 50)),
        "program_active": bool(cfg.get("active", True)),
        "share_text": cfg.get("message") or f"Join Homeland Advantage at CP67 Mall and earn exciting rewards! Use my referral code: {referral_code}"
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
        {"name": "Bronze", "min_points": 0, "color": "#B87333", "purchase_range": "0 - 10,000", "retail": "10%", "jewellery": "5%"},
        {"name": "Silver", "min_points": 2500, "color": "#A8A9AD", "purchase_range": "10,001 - 25,000", "retail": "15%", "jewellery": "7.5%"},
        {"name": "Gold", "min_points": 10000, "color": "#DAA520", "purchase_range": "25,001 - 75,000", "retail": "20%", "jewellery": "10%"},
        {"name": "Platinum", "min_points": 25000, "color": "#C4C4C0", "purchase_range": "75,001 - 1,50,000", "retail": "25%", "jewellery": "12.5%"},
        {"name": "Titanium", "min_points": 50000, "color": "#54545A", "purchase_range": "1,50,001 - 3,00,000", "retail": "30%", "jewellery": "15%"},
        {"name": "Diamond", "min_points": 100000, "color": "#A7D8DE", "purchase_range": "3,00,001 - 5,00,000", "retail": "32.5%", "jewellery": "16.25%"},
        {"name": "Privilege", "min_points": 250000, "color": "#6B3FA0", "purchase_range": "5,00,001 & Above", "retail": "35%", "jewellery": "17.5%"},
    ]

    return {
        "current_tier": current_tier,
        "total_earned": total_earned,
        "tiers": tiers
    }



# ==================== ACTIVE CAMPAIGNS (CONSUMER) ====================

@consumer_router.get("/campaigns")
async def get_consumer_campaigns():
    """Get currently active campaigns for consumer display"""
    now = datetime.now(timezone.utc).isoformat()
    campaigns = []
    async for c in _db.campaigns.find(
        {"is_active": True, "start_date": {"$lte": now}, "end_date": {"$gte": now}},
        {"_id": 0, "applicable_brand_ids": 0, "created_by": 0, "total_triggered": 0, "total_bonus_issued": 0}
    ):
        campaigns.append(c)
    return {"campaigns": campaigns}



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
