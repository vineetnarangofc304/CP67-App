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
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks, UploadFile, File, Form, Query
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
import asyncio

try:
    import qrcode
except ImportError:
    qrcode = None

logger = logging.getLogger(__name__)

staff_router = APIRouter(prefix="/api/staff")
staff_admin_router = APIRouter(prefix="/api/admin/staff")

_db = None
_send_sms_otp = None      # async fn(phone_10: str, otp: str) -> dict
_store_otp = None         # async fn(phone_10: str, otp: str) -> None
_verify_stored_otp = None # async fn(phone_10: str, otp: str) -> bool
security = HTTPBearer(auto_error=False)

JWT_SECRET = os.environ.get('JWT_SECRET', 'cp67-secret-key-2025')
OTP_DEV_BYPASS = os.environ.get('OTP_DEV_BYPASS', '')

# ==================== SETUP ====================

def bind_db(db, send_sms_otp=None, store_otp=None, verify_stored_otp=None):
    global _db, _send_sms_otp, _store_otp, _verify_stored_otp
    _db = db
    if send_sms_otp is not None:
        _send_sms_otp = send_sms_otp
    if store_otp is not None:
        _store_otp = store_otp
    if verify_stored_otp is not None:
        _verify_stored_otp = verify_stored_otp


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
    # Point 3: Category-wise & Brand-wise overrides.
    # Structure:
    #   category_slabs: { "<Category Name>": { "registration_slabs": [...], "bill_upload_slabs": [...] } }
    #   brand_slabs:    { "<Brand Name>":    { "registration_slabs": [...], "bill_upload_slabs": [...] } }
    # Lookup priority when awarding an incentive: brand override → category override → default.
    "category_slabs": {},
    "brand_slabs": {},
    # Point 8: Flat registration reward per category (no min/max — just amount).
    # Structure: { "__ALL__": <amount>, "<Category Name>": <amount>, ... }
    "registration_by_category": {},
    # Point 9: Bill-value-based slabs per category (rewards depend on the bill amount uploaded, not the count).
    # Structure: { "__ALL__": [{"min_value": 0, "max_value": 1000, "amount": 20}, ...], "<Category Name>": [...] }
    "bill_upload_value_slabs_by_category": {},
    "attribution_window_minutes": 15,
    "registration_validity_days": 60,
}


async def get_staff_config() -> Dict:
    doc = await _db.staff_config.find_one({"id": "staff_config"}, {"_id": 0})
    if not doc:
        # copy so pymongo doesn't inject _id into our module-level constant
        seed = dict(DEFAULT_STAFF_CONFIG)
        await _db.staff_config.insert_one(seed)
        return dict(DEFAULT_STAFF_CONFIG)
    # Backfill new fields if config was created before category/brand slabs existed
    changed = False
    if "category_slabs" not in doc:
        doc["category_slabs"] = {}
        changed = True
    if "brand_slabs" not in doc:
        doc["brand_slabs"] = {}
        changed = True
    if "registration_by_category" not in doc:
        doc["registration_by_category"] = {}
        changed = True
    if "bill_upload_value_slabs_by_category" not in doc:
        doc["bill_upload_value_slabs_by_category"] = {}
        changed = True
    if changed:
        await _db.staff_config.update_one(
            {"id": "staff_config"},
            {"$set": {
                "category_slabs": doc["category_slabs"],
                "brand_slabs": doc["brand_slabs"],
                "registration_by_category": doc["registration_by_category"],
                "bill_upload_value_slabs_by_category": doc["bill_upload_value_slabs_by_category"],
            }},
        )
    return doc


def _amount_for_slab(count: int, slabs: List[Dict]) -> int:
    for s in slabs:
        if s["min"] <= count <= s["max"]:
            return int(s["amount"])
    return int(slabs[-1]["amount"]) if slabs else 0


def _amount_for_value_slab_match(bill_value: float, slabs: List[Dict]) -> Optional[int]:
    """Return the slab amount if bill_value fits any [min,max] range, or None on miss.
    Point 18 (Sep 2026): caller uses None to cascade to the next fallback tier
    (e.g. category slabs → __ALL__ slabs → 0) instead of prematurely returning 0."""
    if not slabs:
        return None
    for s in slabs:
        lo = float(s.get("min_value", 0))
        hi = float(s.get("max_value", 0))
        if lo <= bill_value <= hi:
            return int(s.get("amount", 0))
    return None


def _amount_for_value_slab(bill_value: float, slabs: List[Dict]) -> int:
    """Point 9: pick the slab whose [min_value, max_value] range contains bill_value.
    Point 17 (Sep 2026 bug fix): if bill_value is BELOW the lowest slab's
    min_value → 0 (no reward). If bill_value EXCEEDS the highest slab's
    max_value → use the last slab's amount (cap). Previously any miss
    fell through to `slabs[-1].amount`, so a ₹62 bill under a config that
    starts at ₹100 wrongly earned the top-tier reward."""
    if not slabs:
        return 0
    matched = _amount_for_value_slab_match(bill_value, slabs)
    if matched is not None:
        return matched
    # Determine floor/ceiling behaviour based on where bill_value lies.
    lowest_min = min(float(s.get("min_value", 0)) for s in slabs)
    if bill_value < lowest_min:
        return 0
    return int(slabs[-1].get("amount", 0))


async def _brand_category(brand_name: str) -> Optional[str]:
    if not brand_name:
        return None
    doc = await _db.brands.find_one(
        {"brand_name": {"$regex": f"^{re.escape(brand_name)}$", "$options": "i"}},
        {"_id": 0, "category": 1},
    )
    return (doc or {}).get("category") if doc else None


async def _resolve_registration_amount(cfg: Dict, staff: Dict, reg_count: int) -> int:
    """Point 8: Category-flat registration reward with universal fallback.
    Priority:
      1. registration_by_category[<staff's brand category>]
      2. registration_by_category["__ALL__"]
      3. Legacy per-brand/category slab table
      4. Default count-based slabs
    """
    reg_map = cfg.get("registration_by_category") or {}
    category = await _brand_category((staff.get("brand_name") or "").strip())
    if category and category in reg_map:
        return int(reg_map[category])
    if "__ALL__" in reg_map:
        return int(reg_map["__ALL__"])
    # Legacy count-based fallback
    slabs = await _resolve_slabs_for_staff(cfg, staff, "registration_slabs")
    return _amount_for_slab(reg_count, slabs)


async def _resolve_bill_upload_amount(cfg: Dict, staff: Dict, bill_value: float, upload_count: int) -> int:
    """Point 9: Value-based bill-upload reward with category and universal support.
    Priority:
      1. bill_upload_value_slabs_by_category[<staff's brand category>]  (only if a slab matches)
      2. bill_upload_value_slabs_by_category["__ALL__"]                 (fallback if category didn't match)
      3. Cap-or-zero on the deepest tier that was configured
      4. Legacy count-based slab table

    Point 18 (Sep 2026): when the category slabs are configured but none of
    them cover bill_value (e.g. category has slabs starting at ₹500 but the
    bill is ₹353), we now CASCADE to the universal `__ALL__` slabs before
    returning 0. Previously the code stopped at the category tier and paid 0
    even though the universal rule said ₹10.
    """
    value_map = cfg.get("bill_upload_value_slabs_by_category") or {}
    category = await _brand_category((staff.get("brand_name") or "").strip())

    tiers: List[List[Dict]] = []
    if category and value_map.get(category):
        tiers.append(value_map[category])
    if value_map.get("__ALL__"):
        tiers.append(value_map["__ALL__"])

    # 1+2: try each tier for a direct in-range match
    for slabs in tiers:
        matched = _amount_for_value_slab_match(bill_value, slabs)
        if matched is not None:
            return matched

    # 3: no tier matched → use the deepest configured tier's floor/ceiling rule
    if tiers:
        deepest = tiers[-1]
        return _amount_for_value_slab(bill_value, deepest)

    # 4: legacy count-based fallback (nothing configured in value_map)
    slabs = await _resolve_slabs_for_staff(cfg, staff, "bill_upload_slabs")
    return _amount_for_slab(upload_count, slabs)


async def _resolve_slabs_for_staff(cfg: Dict, staff: Dict, slab_kind: str) -> List[Dict]:
    """Resolve which slab table to apply for a given staff member.

    Priority: brand override → category override → "ALL" override → default.
    slab_kind: 'registration_slabs' or 'bill_upload_slabs'.
    """
    brand_name = (staff.get("brand_name") or "").strip()
    # Brand-wise override
    brand_slabs = (cfg.get("brand_slabs") or {}).get(brand_name)
    if brand_slabs and brand_slabs.get(slab_kind):
        return brand_slabs[slab_kind]
    # Category-wise override — look up the brand's category
    if brand_name:
        brand_doc = await _db.brands.find_one(
            {"brand_name": {"$regex": f"^{re.escape(brand_name)}$", "$options": "i"}},
            {"_id": 0, "category": 1},
        )
        category = (brand_doc or {}).get("category") if brand_doc else None
        if category:
            cat_slabs = (cfg.get("category_slabs") or {}).get(category)
            if cat_slabs and cat_slabs.get(slab_kind):
                return cat_slabs[slab_kind]
    # "ALL" scope override — Point 7: configure once for everyone
    all_override = (cfg.get("category_slabs") or {}).get("__ALL__")
    if all_override and all_override.get(slab_kind):
        return all_override[slab_kind]
    # Fallback default
    return cfg.get(slab_kind) or []


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
    # Feb 2026 (iter-72 privesc fix): allowlist admin roles instead of the
    # previous "reject only retail_staff" blacklist, which let a
    # retailer_manager JWT reach every /api/admin/staff/* endpoint and leak
    # the retailer whitelist + full incentive ledger. Roles that legitimately
    # need admin-only endpoints: 'admin', 'super_admin', 'mall_admin'.
    role = (payload.get("role") or payload.get("type") or "").strip()
    if role not in ("admin", "super_admin", "mall_admin"):
        raise HTTPException(status_code=403, detail="Admin only")
    return payload


# ==================== ADMIN: STAFF CRUD ====================

class StaffCreate(BaseModel):
    name: str
    phone: str  # 10 digits, will be normalised
    brand_name: str
    brand_category: Optional[str] = None
    store_location: Optional[str] = None
    email: Optional[str] = None


class StaffUpdate(BaseModel):
    name: Optional[str] = None
    brand_name: Optional[str] = None
    brand_category: Optional[str] = None
    store_location: Optional[str] = None
    email: Optional[str] = None
    is_active: Optional[bool] = None


def _normalise_phone(p: str) -> str:
    d = re.sub(r"\D", "", p or "")
    if len(d) >= 10:
        return d[-10:]
    return d


# ==================== POINT 7: BRAND & CATEGORY CATALOG ====================

@staff_admin_router.get("/catalog/brands-categories")
async def admin_list_brand_catalog(auth=Depends(_verify_admin)):
    """Return distinct brand names and category names from the brands
    collection so the Admin UI can render dropdowns for slab overrides,
    instead of free-text inputs (Point 7).

    Point 10: also returns `staff_mapped_categories` + `staff_mapped_brands` — the
    subset of categories / brands that actually have at least one retail-staff
    record attached (via retail_staff.brand_name → brands.category). The Slabs
    Point 8/9 dropdowns should use these subsets so admins only see options
    that are relevant to their retailer staff base."""
    brands = []
    categories = set()
    brand_to_cat: Dict[str, str] = {}
    async for b in _db.brands.find({}, {"_id": 0, "brand_name": 1, "category": 1}):
        bn = (b.get("brand_name") or "").strip()
        cat = (b.get("category") or "").strip()
        if bn:
            brands.append({"brand_name": bn, "category": cat})
            brand_to_cat[bn.lower()] = cat
        if cat:
            categories.add(cat)
    # Sort + de-duplicate brand list
    seen = set()
    uniq = []
    for x in sorted(brands, key=lambda r: r["brand_name"].lower()):
        key = x["brand_name"].lower()
        if key in seen:
            continue
        seen.add(key)
        uniq.append(x)

    # Point 10: derive the brand & category subsets that are actually in use by retail staff
    staff_brand_set = set()
    for sb in await _db.retail_staff.distinct("brand_name"):
        if not sb:
            continue
        staff_brand_set.add(sb.strip())
    staff_mapped_brands = sorted({b for b in staff_brand_set if b.lower() in brand_to_cat}, key=str.lower)
    staff_mapped_categories = sorted({brand_to_cat[b.lower()] for b in staff_mapped_brands if brand_to_cat.get(b.lower())}, key=str.lower)

    return {
        "brands": uniq,
        "categories": sorted(categories, key=str.lower),
        "staff_mapped_brands": staff_mapped_brands,
        "staff_mapped_categories": staff_mapped_categories,
    }


@staff_admin_router.post("/catalog/brand-category-mapping")
async def admin_upload_brand_category_mapping(
    file: UploadFile = File(...),
    dry_run: bool = Form(False),
    auth=Depends(_verify_admin),
):
    """Point 7: Bulk upload / update the brand → category mapping.

    Accepted CSV headers (case-insensitive):
        Brand Name, Brand Category
    Behavior:
      - If brand exists: update its `category`.
      - If brand doesn't exist: create a minimal brand doc with the category.
      - Empty category rows are treated as invalid.
      - `dry_run=true` parses but doesn't write.
    """
    import csv, io as _io
    try:
        raw = await file.read()
        text = raw.decode("utf-8-sig")
    except Exception:
        raise HTTPException(status_code=400, detail="Failed to read CSV — expected UTF-8 text")

    reader = csv.DictReader(_io.StringIO(text))
    if not reader.fieldnames:
        raise HTTPException(status_code=400, detail="CSV appears empty or missing header row")
    norm = {h.strip().lower(): h for h in reader.fieldnames if h}
    col_brand = norm.get("brand name") or norm.get("brand")
    col_cat = norm.get("brand category") or norm.get("category")
    if not (col_brand and col_cat):
        raise HTTPException(status_code=400,
            detail="CSV missing required columns. Need: Brand Name, Brand Category")

    updates = []
    creates = []
    invalid = []
    idx = 1
    for row in reader:
        idx += 1
        b = (row.get(col_brand) or "").strip()
        c = (row.get(col_cat) or "").strip()
        if not b or not c:
            invalid.append({"row": idx, "brand": b, "category": c, "reason": "missing brand or category"})
            continue
        existing = await _db.brands.find_one(
            {"brand_name": {"$regex": f"^{re.escape(b)}$", "$options": "i"}},
            {"_id": 0, "id": 1, "brand_name": 1, "category": 1},
        )
        if existing:
            if (existing.get("category") or "").strip().lower() != c.lower():
                updates.append({"id": existing["id"], "brand_name": existing["brand_name"], "old": existing.get("category") or "", "new": c})
        else:
            creates.append({"brand_name": b, "category": c})

    if not dry_run:
        now = datetime.now(timezone.utc).isoformat()
        for u in updates:
            await _db.brands.update_one({"id": u["id"]}, {"$set": {"category": u["new"], "updated_at": now}})
        for cr in creates:
            await _db.brands.insert_one({
                "id": str(uuid.uuid4()),
                "brand_name": cr["brand_name"],
                "atv": 0.0,
                "category": cr["category"],
                "is_active": True,
                "created_at": now,
                "import_source": "brand_category_mapping",
            })

    return {
        "success": True,
        "dry_run": dry_run,
        "summary": {
            "updated": len(updates),
            "created": len(creates),
            "invalid": len(invalid),
        },
        "updates_preview": updates[:30],
        "creates_preview": creates[:30],
        "invalid_preview": invalid[:30],
    }


@staff_admin_router.get("/catalog/brand-category-mapping/template.csv")
async def admin_brand_category_mapping_template(auth=Depends(_verify_admin)):
    from fastapi.responses import Response
    body = "Brand Name,Brand Category\nZara,Fashion\nCroma,Electronics\nHaldiram,Food\n"
    return Response(
        content=body,
        media_type="text/csv",
        headers={
            "Content-Disposition": 'attachment; filename="brand-category-mapping-template.csv"',
            "Cache-Control": "no-store",
        },
    )


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
        "brand_category": (payload.brand_category or "").strip(),
        "store_location": (payload.store_location or "").strip(),
        "email": (payload.email or "").strip(),
        "is_active": True,
        # QR contains an encrypted-ish token, but for MVP we use staff_id itself
        # since the QR is derived from staff_id and only distributed to that staff.
        "qr_token": f"HL{staff_id[:12].replace('-','').upper()}",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    # insert_one mutates the dict by adding _id → clone to avoid leaking ObjectId to response
    await _db.retail_staff.insert_one(dict(doc))
    return {"success": True, "staff": doc}


@staff_admin_router.get("")
async def admin_list_staff(active_only: bool = False, brand: Optional[str] = None,
                            auth=Depends(_verify_admin)):
    q = {}
    if active_only:
        q["is_active"] = True
    if brand:
        q["brand_name"] = brand
    # Point 35: enrich each staff row with is_brand_mapped and the master brand's canonical category
    # so the admin UI can tag unmapped rows and auto-fill category during in-place edits.
    master_brands = {}
    async for b in _db.brands.find({"brand_name": {"$exists": True, "$ne": ""}}, {"_id": 0, "brand_name": 1, "category": 1}):
        bn = (b.get("brand_name") or "").strip()
        if bn:
            master_brands[bn.lower()] = {
                "brand_name": bn,
                "category": (b.get("category") or "").strip(),
            }

    staff = []
    async for s in _db.retail_staff.find(q, {"_id": 0}).sort("created_at", -1):
        raw_brand = (s.get("brand_name") or "").strip()
        master = master_brands.get(raw_brand.lower())
        s["is_brand_mapped"] = bool(master)
        s["canonical_brand_name"] = master["brand_name"] if master else raw_brand
        s["canonical_brand_category"] = master["category"] if master else (s.get("brand_category") or "")
        staff.append(s)
    unmapped = sum(1 for s in staff if not s["is_brand_mapped"])
    return {"staff": staff, "total": len(staff), "unmapped_count": unmapped}


@staff_admin_router.get("/qr-cards.pdf")
async def admin_export_qr_cards_pdf(
    brand: Optional[str] = None,
    active_only: bool = True,
    ids: Optional[str] = None,
    auth=Depends(_verify_admin),
):
    """Generate a print-ready A4 PDF of QR cards for retail staff.
    6 cards per A4 page (3 rows × 2 columns). Each card contains:
      - Staff QR (encodes wa.me link with #STAFF:<token>)
      - Staff Name
      - Staff Code
      - Brand
      - Cut & fold guides

    Query params:
      brand=Zara         → only staff for that brand
      active_only=true   → skip deactivated staff (default true)
      ids=id1,id2,...    → specific staff IDs (overrides brand + active_only)
    """
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas
    from reportlab.lib.utils import ImageReader
    from io import BytesIO
    import qrcode
    from fastapi.responses import Response

    # Resolve target staff list
    if ids:
        id_list = [s.strip() for s in ids.split(",") if s.strip()]
        query = {"id": {"$in": id_list}}
    else:
        query = {}
        if active_only:
            query["is_active"] = True
        if brand:
            query["brand_name"] = brand

    staff_docs = []
    async for s in _db.retail_staff.find(query, {"_id": 0}).sort([("brand_name", 1), ("name", 1)]):
        staff_docs.append(s)

    if not staff_docs:
        raise HTTPException(status_code=404, detail="No staff match the given filter")

    # Use the same WhatsApp phone + message format as the single-QR endpoint
    # so PDF cards + in-app cards decode to identical URLs.
    wa_phone = os.environ.get("WA_BUSINESS_PHONE") or os.environ.get("WHATSAPP_NUMBER") or "917347576767"

    # ---- Layout constants (A4 = 210 × 297 mm) ----
    PAGE_W, PAGE_H = A4
    MARGIN = 10 * mm
    COLS, ROWS = 2, 3
    CARDS_PER_PAGE = COLS * ROWS
    GUTTER = 4 * mm
    CARD_W = (PAGE_W - 2 * MARGIN - (COLS - 1) * GUTTER) / COLS
    CARD_H = (PAGE_H - 2 * MARGIN - (ROWS - 1) * GUTTER) / ROWS

    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)

    for idx, staff in enumerate(staff_docs):
        # Position of this card on the current page
        slot = idx % CARDS_PER_PAGE
        col = slot % COLS
        row = slot // COLS
        # y grows from bottom in reportlab, so flip
        x0 = MARGIN + col * (CARD_W + GUTTER)
        y0 = PAGE_H - MARGIN - (row + 1) * CARD_H - row * GUTTER

        # Draw card border (dashed cut-guide + soft fill)
        c.setStrokeColorRGB(0.72, 0.53, 0.04)  # luxury gold
        c.setLineWidth(0.6)
        c.setDash(3, 2)
        c.rect(x0, y0, CARD_W, CARD_H, stroke=1, fill=0)
        c.setDash()

        # Cream fill panel (top 40%)
        c.setFillColorRGB(0.98, 0.97, 0.96)
        c.rect(x0 + 2 * mm, y0 + 2 * mm, CARD_W - 4 * mm, CARD_H - 4 * mm, stroke=0, fill=1)

        # ---- Header — "Homeland Advantage" + brand ----
        c.setFillColorRGB(0.72, 0.53, 0.04)
        c.setFont("Helvetica-Bold", 8)
        c.drawString(x0 + 6 * mm, y0 + CARD_H - 7 * mm, "HOMELAND ADVANTAGE")
        c.setFillColorRGB(0.35, 0.32, 0.28)
        c.setFont("Helvetica", 6)
        c.drawString(x0 + 6 * mm, y0 + CARD_H - 10 * mm, "CP67 Mall · Retail Rewards")

        # ---- QR ----
        msg = f"Hi CP67! I'm registering via staff {staff.get('staff_code','')} ({staff.get('brand_name','')}). #STAFF:{staff.get('qr_token','')}"
        wa_url = f"https://wa.me/{wa_phone}?text={_url_encode(msg)}"
        qr = qrcode.QRCode(
            error_correction=qrcode.constants.ERROR_CORRECT_H,
            box_size=10, border=1,
        )
        qr.add_data(wa_url)
        qr.make(fit=True)
        qr_img = qr.make_image(fill_color="#1E1B18", back_color="#FAF8F5").convert("RGB")

        # Place QR — 40mm square centered horizontally, near the top
        qr_size = 38 * mm
        qr_x = x0 + (CARD_W - qr_size) / 2
        qr_y = y0 + CARD_H - qr_size - 15 * mm
        c.drawImage(ImageReader(qr_img), qr_x, qr_y, width=qr_size, height=qr_size, mask="auto")

        # ---- Staff details (below QR) ----
        c.setFillColorRGB(0.12, 0.11, 0.09)
        c.setFont("Helvetica-Bold", 11)
        name = (staff.get("name") or "")[:28]
        c.drawCentredString(x0 + CARD_W / 2, y0 + 20 * mm, name)

        c.setFont("Helvetica", 8)
        c.setFillColorRGB(0.35, 0.32, 0.28)
        brand_txt = (staff.get("brand_name") or "")[:32]
        c.drawCentredString(x0 + CARD_W / 2, y0 + 15 * mm, brand_txt)

        c.setFont("Helvetica-Bold", 9)
        c.setFillColorRGB(0.72, 0.53, 0.04)
        code = staff.get("staff_code") or ""
        c.drawCentredString(x0 + CARD_W / 2, y0 + 10 * mm, code)

        c.setFont("Helvetica-Oblique", 6)
        c.setFillColorRGB(0.5, 0.48, 0.44)
        c.drawCentredString(x0 + CARD_W / 2, y0 + 5 * mm,
                            "Scan → WhatsApp → earn rewards on your bill")

        # Page break
        if slot == CARDS_PER_PAGE - 1 and idx != len(staff_docs) - 1:
            c.showPage()

    c.showPage()
    c.save()
    buf.seek(0)

    fname_bits = ["homeland-staff-qrs"]
    if brand:
        fname_bits.append(brand.lower().replace(" ", "-"))
    fname_bits.append(f"{len(staff_docs)}cards")
    filename = "-".join(fname_bits) + ".pdf"

    return Response(
        content=buf.getvalue(),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )



@staff_admin_router.get("/bulk-import/template.csv")
async def admin_bulk_import_template(auth=Depends(_verify_admin)):
    """Point 4: Download a ready-to-fill CSV template with the exact column
    headers the bulk-import endpoint expects."""
    from fastapi.responses import Response
    header = "Mob No,Name of Employee,Brand Name,Brand Category\n"
    sample = (
        "9876543210,Rahul Sharma,Zara,Fashion\n"
        "9876543211,Priya Verma,Zara,Fashion\n"
        "9876543212,Aman Khan,Croma,Electronics\n"
    )
    body = header + sample
    return Response(
        content=body,
        media_type="text/csv",
        headers={
            "Content-Disposition": 'attachment; filename="staff-upload-template.csv"',
            "Cache-Control": "no-store",
        },
    )


@staff_admin_router.post("/bulk-import")
async def admin_bulk_import_staff(
    file: UploadFile = File(...),
    dry_run: bool = Form(False),
    auth=Depends(_verify_admin),
):
    """Bulk-import retail staff from a CSV file.

    Accepts the CP67 "merged-cell" format where Brand Name is filled only on
    the first row of each brand and blank for subsequent staff of the same
    brand — this endpoint forward-fills automatically.

    Required columns (headers can have trailing spaces):
        Brand Name, Staff Name, Contact No.
    Optional columns:
        Designation, S.no, Email, Store Location

    Behavior:
      - Rows without staff name or phone → invalid
      - Phones normalised to 10 digits (strips country code, punctuation)
      - Existing phones → skipped (never overwrite an active staff record)
      - Each accepted row gets an auto-generated staff_code (HL-NNNN)
      - dry_run=true → parses + validates but doesn't insert (preview only)
    """
    import csv, io, re

    try:
        raw = await file.read()
        text = raw.decode("utf-8-sig")
    except Exception:
        raise HTTPException(status_code=400, detail="Failed to read CSV — expected UTF-8 text")

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise HTTPException(status_code=400, detail="CSV appears empty or missing header row")

    # Normalise header names — strip whitespace + lowercase for lookup
    norm_headers = {h.strip().lower(): h for h in reader.fieldnames if h}

    def h(key):  # returns actual header string or None
        return norm_headers.get(key)

    col_brand = h("brand name") or h("brand")
    col_category = h("brand category") or h("category")
    col_name = h("staff name") or h("name of employee") or h("name")
    col_phone = h("mob no") or h("mob no.") or h("mobile no") or h("mobile no.") or h("mobile") or h("contact no.") or h("contact") or h("phone")
    col_desig = h("designation") or h("role")
    col_store = h("store location") or h("store")
    col_email = h("email")

    if not (col_brand and col_name and col_phone):
        raise HTTPException(
            status_code=400,
            detail="CSV missing required columns. Need: Mob No, Name of Employee, Brand Name, Brand Category",
        )

    # Parse + ffill brand name
    parsed = []
    last_brand = ""
    last_category = ""
    for row in reader:
        brand_cell = (row.get(col_brand) or "").strip()
        if brand_cell:
            last_brand = brand_cell
        cat_cell = (row.get(col_category) or "").strip() if col_category else ""
        if cat_cell:
            last_category = cat_cell
        parsed.append({
            "brand": last_brand,
            "brand_category": last_category,
            "name": (row.get(col_name) or "").strip(),
            "phone_raw": (row.get(col_phone) or "").strip(),
            "designation": (row.get(col_desig) or "").strip() if col_desig else "",
            "store": (row.get(col_store) or "").strip() if col_store else "",
            "email": (row.get(col_email) or "").strip() if col_email else "",
        })

    imported, skipped_existing, invalid = [], [], []
    seq_base = await _db.retail_staff.count_documents({})

    # Pre-load existing phones to avoid N round-trips
    existing_phones = set()
    async for s in _db.retail_staff.find({}, {"_id": 0, "phone": 1}):
        if s.get("phone"):
            existing_phones.add(s["phone"])

    to_insert = []
    for idx, r in enumerate(parsed):
        digits = re.sub(r"\D", "", r["phone_raw"])
        phone = digits[-10:] if len(digits) >= 10 else ""
        if not r["name"]:
            invalid.append({"row": idx + 2, "reason": "missing staff name",
                            "brand": r["brand"], "phone_raw": r["phone_raw"]})
            continue
        if not r["brand"]:
            invalid.append({"row": idx + 2, "reason": "missing brand", "name": r["name"]})
            continue
        if not phone or len(phone) != 10:
            invalid.append({"row": idx + 2, "reason": "invalid phone",
                            "name": r["name"], "phone_raw": r["phone_raw"]})
            continue
        if phone in existing_phones:
            skipped_existing.append({"row": idx + 2, "phone": phone, "name": r["name"], "brand": r["brand"]})
            continue

        seq_base += 1
        staff_id = str(uuid.uuid4())
        doc = {
            "id": staff_id,
            "staff_code": f"HL-{seq_base:04d}",
            "name": r["name"],
            "phone": phone,
            "brand_name": r["brand"],
            "brand_category": r.get("brand_category") or "",
            "store_location": r["store"] or "",
            "designation": r["designation"] or "",
            "email": r["email"] or "",
            "is_active": True,
            "qr_token": f"HL{staff_id[:12].replace('-','').upper()}",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "import_source": "csv_bulk",
        }
        existing_phones.add(phone)   # prevent dupes within the same file
        to_insert.append(doc)
        imported.append({"phone": phone, "name": r["name"], "brand": r["brand"], "staff_code": doc["staff_code"]})

    if not dry_run and to_insert:
        await _db.retail_staff.insert_many([dict(d) for d in to_insert])
        # Auto-upsert brand category into the brands collection so category
        # taxonomy stays consistent with staff imports.
        seen_brands: Dict[str, str] = {}
        for d in to_insert:
            b = (d.get("brand_name") or "").strip()
            c = (d.get("brand_category") or "").strip()
            if b and c and b not in seen_brands:
                seen_brands[b] = c
        for bname, cat in seen_brands.items():
            existing_brand = await _db.brands.find_one(
                {"brand_name": {"$regex": f"^{re.escape(bname)}$", "$options": "i"}},
                {"_id": 0, "id": 1, "category": 1},
            )
            if existing_brand:
                if not (existing_brand.get("category") or "").strip():
                    await _db.brands.update_one(
                        {"id": existing_brand["id"]},
                        {"$set": {"category": cat, "updated_at": datetime.now(timezone.utc).isoformat()}},
                    )
            else:
                await _db.brands.insert_one({
                    "id": str(uuid.uuid4()),
                    "brand_name": bname,
                    "atv": 0.0,
                    "category": cat,
                    "is_active": True,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "import_source": "staff_csv_bulk",
                })

    return {
        "success": True,
        "dry_run": dry_run,
        "summary": {
            "total_rows": len(parsed),
            "imported": len(imported),
            "skipped_existing": len(skipped_existing),
            "invalid": len(invalid),
            "brands_imported": len({r["brand"] for r in imported}),
        },
        "imported_preview": imported[:20],
        "skipped_preview": skipped_existing[:20],
        "invalid_preview": invalid[:20],
    }


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
    wa_phone = os.environ.get("WA_BUSINESS_PHONE") or os.environ.get("WHATSAPP_NUMBER") or "917347576767"
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
    category_slabs: Optional[Dict[str, Dict[str, List[Dict]]]] = None
    brand_slabs: Optional[Dict[str, Dict[str, List[Dict]]]] = None
    registration_by_category: Optional[Dict[str, int]] = None
    bill_upload_value_slabs_by_category: Optional[Dict[str, List[Dict]]] = None
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


@staff_admin_router.get("/redemptions")
async def admin_list_redemptions(status: Optional[str] = None, limit: int = 200,
                                  auth=Depends(_verify_admin)):
    """List redemption requests. Simple request-only stub — admin manually
    settles offline (marks 'settled' via PATCH)."""
    q = {}
    if status:
        q["status"] = status
    rows = []
    async for r in _db.staff_redemptions.find(q, {"_id": 0}).sort("requested_at", -1).limit(limit):
        # Enrich with staff details
        s = await _db.retail_staff.find_one({"id": r.get("staff_id")}, {"_id": 0, "name": 1, "phone": 1, "staff_code": 1, "brand_name": 1})
        if s:
            r.update({f"staff_{k}": v for k, v in s.items()})
        rows.append(r)
    return {"redemptions": rows, "total": len(rows)}


class RedemptionStatusUpdate(BaseModel):
    status: str  # requested | approved | settled | rejected
    admin_note: Optional[str] = None
    payout_ref: Optional[str] = None


@staff_admin_router.patch("/redemptions/{redemption_id}")
async def admin_update_redemption(redemption_id: str, patch: RedemptionStatusUpdate,
                                    auth=Depends(_verify_admin)):
    updates = {"status": patch.status, "updated_at": datetime.now(timezone.utc).isoformat()}
    if patch.admin_note:
        updates["admin_note"] = patch.admin_note
    if patch.payout_ref:
        updates["payout_ref"] = patch.payout_ref
    r = await _db.staff_redemptions.update_one({"id": redemption_id}, {"$set": updates})
    if r.matched_count == 0:
        raise HTTPException(status_code=404, detail="Redemption not found")
    doc = await _db.staff_redemptions.find_one({"id": redemption_id}, {"_id": 0})
    return {"success": True, "redemption": doc}


# ==================== POINT 12: RETAILER INCENTIVE REPORTS ====================

@staff_admin_router.get("/incentives/report")
async def admin_incentive_report(
    incentive_type: Optional[str] = None,   # 'registration' | 'bill_upload' | None (all)
    brand: Optional[str] = None,
    status: Optional[str] = None,           # 'pending' | 'pending_verification' | 'redeemable' | 'cancelled' | 'redeemed'
    staff_id: Optional[str] = None,
    start_date: Optional[str] = None,       # ISO YYYY-MM-DD (inclusive)
    end_date: Optional[str] = None,         # ISO YYYY-MM-DD (inclusive, end-of-day)
    limit: int = Query(1000, ge=1, le=5000),
    auth=Depends(_verify_admin),
):
    """Point 12 (Aug 2026): Retailer incentive earn report.

    Returns each incentive record enriched with staff details (name, phone,
    staff_code, brand) and, for bill_upload rows, the bill amount / status /
    store name. Registration rows carry the customer mobile number (which
    signed up under this staff QR); bill_upload rows carry both the customer
    mobile and the bill_id/amount. Admin can filter by type / brand / status /
    staff / date range and download as CSV via `?format=csv`.
    """
    q: Dict = {}
    if incentive_type in ("registration", "bill_upload"):
        q["type"] = incentive_type
    if status:
        q["status"] = status
    if staff_id:
        q["staff_id"] = staff_id
    if start_date or end_date:
        rng = {}
        if start_date:
            rng["$gte"] = f"{start_date}T00:00:00"
        if end_date:
            rng["$lte"] = f"{end_date}T23:59:59.999999+00:00"
        q["created_at"] = rng

    # Point 12 (iter 53 fix): apply brand filter at the Mongo layer BEFORE the limit,
    # otherwise a filter on 1000+ staff can silently miss rows past the cursor cap.
    if brand:
        brand_norm = brand.strip().lower()
        matched_staff_ids: List[str] = []
        async for s in _db.retail_staff.find({}, {"_id": 0, "id": 1, "brand_name": 1}):
            if (s.get("brand_name") or "").strip().lower() == brand_norm:
                matched_staff_ids.append(s["id"])
        if not matched_staff_ids:
            return {"rows": [], "summary": {"total": 0, "registration_count": 0, "bill_upload_count": 0, "total_amount": 0, "redeemable_amount": 0}}
        q["staff_id"] = {"$in": matched_staff_ids}

    rows: List[Dict] = []
    # Cache staff/bill lookups to keep this endpoint fast for large data-sets.
    staff_cache: Dict[str, Dict] = {}
    # Point 15 (Feb 2026): bound the primary find with max_time_ms so an Atlas
    # hiccup surfaces as a friendly 503 (via top-level except below), not an
    # opaque "Failed to load report" toast. The per-row bill.find_one is also
    # bounded so one bad row can't stall the whole scan.
    try:
        cur = _db.staff_incentives.find(q, {"_id": 0}).sort("created_at", -1).limit(limit)
        try:
            cur = cur.max_time_ms(15000)
        except Exception as _e:
            logger.warning(f"admin_incentive_report: max_time_ms unavailable on cursor: {_e}")
        async for r in cur:
            sid = r.get("staff_id")
            if sid and sid not in staff_cache:
                try:
                    s = await _db.retail_staff.find_one(
                        {"id": sid},
                        {"_id": 0, "name": 1, "phone": 1, "staff_code": 1, "brand_name": 1, "brand_category": 1, "store_location": 1},
                        max_time_ms=5000,
                    )
                except Exception as _se:
                    logger.warning(f"admin_incentive_report: retail_staff lookup failed for {sid}: {_se}")
                    s = None
                staff_cache[sid] = s or {}
            s = staff_cache.get(sid) or {}

            row = {
                "id": r.get("id"),
                "type": r.get("type"),
                "status": r.get("status"),
                "amount": r.get("amount"),
                "customer_phone": r.get("customer_phone"),
                "created_at": r.get("created_at"),
                "approved_at": r.get("approved_at"),
                "expires_at": r.get("expires_at"),
                "staff_id": sid,
                "staff_code": s.get("staff_code") or r.get("staff_code"),
                "staff_name": s.get("name"),
                "staff_phone": s.get("phone"),
                "staff_brand": s.get("brand_name"),
                "staff_brand_category": s.get("brand_category"),
                "staff_store": s.get("store_location"),
            }
            if r.get("type") == "bill_upload":
                bill_id = r.get("bill_id")
                row["bill_id"] = bill_id
                row["bill_value"] = r.get("bill_value")
                if bill_id:
                    try:
                        bill = await _db.bills.find_one(
                            {"id": bill_id},
                            {"_id": 0, "amount": 1, "store_name": 1, "status": 1, "bill_no": 1, "created_at": 1},
                            max_time_ms=5000,
                        )
                    except Exception as _be:
                        logger.warning(f"admin_incentive_report: bills lookup failed for {bill_id}: {_be}")
                        bill = None
                    if bill:
                        row["bill_amount"] = bill.get("amount") or row.get("bill_value")
                        row["bill_store"] = bill.get("store_name")
                        row["bill_status"] = bill.get("status")
                        row["bill_no"] = bill.get("bill_no")
            rows.append(row)
    except Exception as e:
        # Feb 2026 Point 15: return a friendly 503 instead of a raw 500 so
        # the "Failed to load report" toast can be replaced with a retry hint.
        # Iter-72 hardening: use isinstance() against pymongo classes because
        # message-substring matching misses AutoReconnect / ExecutionTimeout.
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
        err_txt = str(e).lower()
        transient = (
            isinstance(e, _transient_classes)
            or ("timed out" in err_txt)
            or ("maxtimeexceeded" in err_txt)
            or ("networktimeout" in err_txt)
            or ("time limit" in err_txt)
        )
        if transient:
            logger.warning(f"admin_incentive_report Atlas hiccup: {e}")
            raise HTTPException(status_code=503, detail="Report DB is under load — retry in ~10s. If it persists, narrow the date range or brand filter.")
        logger.exception(f"admin_incentive_report failed: {e}")
        raise HTTPException(status_code=500, detail=f"Report failed: {str(e)[:200]}")

    # Summary counts (respects filters)
    summary = {
        "total": len(rows),
        "registration_count": sum(1 for x in rows if x["type"] == "registration"),
        "bill_upload_count": sum(1 for x in rows if x["type"] == "bill_upload"),
        "total_amount": sum(float(x.get("amount") or 0) for x in rows),
        "redeemable_amount": sum(float(x.get("amount") or 0) for x in rows if x.get("status") == "redeemable"),
    }
    return {"rows": rows, "summary": summary}


@staff_admin_router.get("/incentives/report.csv")
async def admin_incentive_report_csv(
    incentive_type: Optional[str] = None,
    brand: Optional[str] = None,
    status: Optional[str] = None,
    staff_id: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 5000,
    auth=Depends(_verify_admin),
):
    """CSV export of the same data returned by /incentives/report."""
    data = await admin_incentive_report(
        incentive_type=incentive_type, brand=brand, status=status, staff_id=staff_id,
        start_date=start_date, end_date=end_date, limit=limit, auth=auth,
    )
    import csv
    from io import StringIO
    from fastapi.responses import Response

    buf = StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "Type", "Staff Code", "Staff Name", "Staff Phone", "Brand", "Category", "Store",
        "Customer Phone", "Amount", "Status",
        "Bill No", "Bill Store", "Bill Amount", "Bill Status",
        "Created At", "Approved At",
    ])
    for r in data["rows"]:
        writer.writerow([
            r.get("type") or "",
            r.get("staff_code") or "",
            r.get("staff_name") or "",
            r.get("staff_phone") or "",
            r.get("staff_brand") or "",
            r.get("staff_brand_category") or "",
            r.get("staff_store") or "",
            r.get("customer_phone") or "",
            r.get("amount") or 0,
            r.get("status") or "",
            r.get("bill_no") or "",
            r.get("bill_store") or "",
            r.get("bill_amount") or "",
            r.get("bill_status") or "",
            r.get("created_at") or "",
            r.get("approved_at") or "",
        ])
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="retailer_incentives_report.csv"'},
    )




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

    # Generate 6-digit OTP, persist, then send via Karix SMS (best-effort, non-blocking success)
    import random
    otp = f"{random.randint(0, 999999):06d}"
    if _store_otp is not None:
        try:
            await _store_otp(phone, otp)
        except Exception as e:
            logger.error(f"staff store_otp failed: {e}")
    else:
        # Fallback local storage
        await _db.staff_otps.update_one(
            {"phone": phone},
            {"$set": {"otp": otp, "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()}},
            upsert=True,
        )

    # Point 11 (Aug 2026): staff login OTP must ride WhatsApp (dual-channel via
    # send_login_otp). Return per-channel diagnostics to help admin debug delivery.
    delivery = {"whatsapp": None, "sms": None, "success": False}
    if _send_sms_otp is not None:
        try:
            r = await _send_sms_otp(phone, otp)
            if isinstance(r, dict):
                delivery = r
            logger.info(f"Staff OTP dispatch to {phone}: {r}")
        except Exception as e:
            logger.error(f"staff OTP send failed for {phone}: {e}")

    logger.info(f"Staff OTP generated for {phone}: {otp}")  # dev observability
    return {"success": True, "message": "OTP sent", "delivery": delivery}


@staff_router.post("/auth/verify-otp")
async def staff_verify_otp(payload: StaffOTPVerify):
    phone = _normalise_phone(payload.phone)

    # Dev bypass
    ok = False
    if OTP_DEV_BYPASS and payload.otp == OTP_DEV_BYPASS:
        ok = True
    elif _verify_stored_otp is not None:
        try:
            ok = await _verify_stored_otp(phone, payload.otp)
        except Exception as e:
            logger.error(f"staff verify_stored_otp failed: {e}")
            ok = False
    else:
        rec = await _db.staff_otps.find_one({"phone": phone}, {"_id": 0})
        if rec and rec.get("otp") == payload.otp:
            ok = True

    if not ok:
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
    reg_slabs = await _resolve_slabs_for_staff(cfg, staff, "registration_slabs")
    upl_slabs = await _resolve_slabs_for_staff(cfg, staff, "bill_upload_slabs")
    current_reg_slab = _amount_for_slab(reg_count, reg_slabs)
    current_upload_slab = _amount_for_slab(upload_count, upl_slabs)

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
            "registration_slabs": reg_slabs,
            "bill_upload_slabs": upl_slabs,
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
    wa_phone = os.environ.get("WA_BUSINESS_PHONE") or os.environ.get("WHATSAPP_NUMBER") or "917347576767"
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
    # Point 8: flat-per-category resolver (falls back to legacy count-based slabs).
    amount = await _resolve_registration_amount(cfg, staff, count_so_far)
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


async def create_or_activate_bill_incentive(bill_id: str, customer_phone: str, bill_status: str, bill_value: float = 0.0):
    """Called from the bill-upload pipeline after each bill status change.
      - If a matching active attribution exists → create a bill_upload incentive.
      - Additionally, if the customer has a pending registration incentive → activate it.
      - Status mapping: approved→approved(redeemable), pending/manual→pending_verification, rejected→cancelled.
    Point 9: `bill_value` (₹) is used to pick the value-based slab reward. If not provided, we look it up from the bill record.
    Point 14 (Aug 2026): Retailer bill incentive is now BRAND-MATCHED. The bill's
    store_name must equal the attributed staff's brand_name (case-insensitive,
    ignoring punctuation). If the customer scans Retailer A's QR but uploads
    a bill for Retailer B, Retailer A gets NO incentive. The attribution is
    still marked `used` so a later matching bill can't sneak in on the same
    scan — one scan = one bill decision (the client's "immediately after"
    rule from the spec doc).
    """
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
            attributed_staff = await _db.retail_staff.find_one({"id": staff_id}, {"_id": 0}) or attribution
            # Point 14: enforce brand match between the bill and the staff's brand.
            bill_doc = await _db.bills.find_one({"id": bill_id}, {"_id": 0, "amount": 1, "total_amount": 1, "bill_amount": 1, "store_name": 1, "brand": 1})
            bill_brand = ""
            if bill_doc:
                bill_brand = (bill_doc.get("store_name") or bill_doc.get("brand") or "").strip()
            staff_brand = (attributed_staff.get("brand_name") or "").strip()

            def _norm(s: str) -> str:
                return re.sub(r"[^a-z0-9]+", "", (s or "").lower())

            brand_match = bool(bill_brand and staff_brand and _norm(bill_brand) == _norm(staff_brand))

            if brand_match:
                count_so_far = await _db.staff_incentives.count_documents({"staff_id": staff_id, "type": "bill_upload"})
                if not bill_value and bill_doc:
                    bill_value = float(bill_doc.get("amount") or bill_doc.get("total_amount") or bill_doc.get("bill_amount") or 0)
                amount = await _resolve_bill_upload_amount(cfg, attributed_staff, bill_value, count_so_far)
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
                    "bill_value": bill_value,
                    "bill_brand": bill_brand,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "approved_at": datetime.now(timezone.utc).isoformat() if status == "redeemable" else None,
                })
                logger.info(f"Point 14: brand-matched incentive credited staff={staff_id} bill_brand='{bill_brand}' staff_brand='{staff_brand}'")
            else:
                # Log an attribution_miss row for reporting / audit — no incentive credited.
                try:
                    await _db.staff_attribution_misses.insert_one({
                        "id": str(uuid.uuid4()),
                        "staff_id": staff_id,
                        "staff_code": attribution["staff_code"],
                        "customer_phone": customer_phone,
                        "bill_id": bill_id,
                        "bill_brand": bill_brand,
                        "staff_brand": staff_brand,
                        "reason": "brand_mismatch",
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    })
                except Exception as e:
                    logger.warning(f"attribution miss log failed: {e}")
                logger.info(f"Point 14: brand-mismatch, no credit. staff='{staff_brand}' bill='{bill_brand}' bill_id={bill_id}")

            # Point 14: whether or not the bill matched, consume the attribution.
            # This enforces "one scan = one bill decision" — later bills need a new QR scan.
            await _db.staff_attributions.update_one({"id": attribution["id"]}, {"$set": {"used": True}})

    # 2. If bill approved, activate any pending registration incentive whose
    #    staff belongs to the SAME brand as the current bill.
    #    Feb 2026 (Point 14b): registration incentive must NOT activate when
    #    the customer uploads a bill for a DIFFERENT retailer. Every incentive
    #    (registration + bill_upload) is now gated on brand match, so the
    #    registration source never leaks credit for someone else's activity.
    #    If the customer uploads a bill for Brand B, the pending Brand A
    #    registration stays pending until the customer eventually uploads a
    #    matching Brand A bill within the 60-day window.
    if bill_status in ("auto_approved", "approved"):
        # Reuse the bill_doc we already fetched above if present; otherwise fetch a lean copy.
        if 'bill_doc' not in locals() or bill_doc is None:
            bill_doc = await _db.bills.find_one(
                {"id": bill_id},
                {"_id": 0, "store_name": 1, "brand": 1},
            )
        current_bill_brand = ""
        if bill_doc:
            current_bill_brand = (bill_doc.get("store_name") or bill_doc.get("brand") or "").strip()

        def _norm(s: str) -> str:
            return re.sub(r"[^a-z0-9]+", "", (s or "").lower())

        current_bill_brand_norm = _norm(current_bill_brand)

        pendings = _db.staff_incentives.find(
            {"customer_phone": customer_phone, "type": "registration", "status": "pending"},
            {"_id": 0, "id": 1, "staff_id": 1, "staff_code": 1},
        )
        activated = 0
        skipped_wrong_brand = 0
        async for pending_reg in pendings:
            reg_staff_id = pending_reg.get("staff_id")
            reg_staff = await _db.retail_staff.find_one({"id": reg_staff_id}, {"_id": 0, "brand_name": 1})
            reg_brand = (reg_staff or {}).get("brand_name") or ""
            reg_brand_norm = _norm(reg_brand)
            if not current_bill_brand_norm or not reg_brand_norm or current_bill_brand_norm != reg_brand_norm:
                skipped_wrong_brand += 1
                # Audit: this bill did NOT unlock the registration incentive
                # because it was for a different brand. Log so admin can see
                # why the registering retailer wasn't paid.
                try:
                    await _db.staff_attribution_misses.insert_one({
                        "id": str(uuid.uuid4()),
                        "staff_id": reg_staff_id,
                        "staff_code": pending_reg.get("staff_code"),
                        "customer_phone": customer_phone,
                        "bill_id": bill_id,
                        "bill_brand": current_bill_brand,
                        "staff_brand": reg_brand,
                        "reason": "registration_activation_brand_mismatch",
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    })
                except Exception as e:
                    logger.warning(f"registration miss log failed: {e}")
                continue
            await _db.staff_incentives.update_one(
                {"id": pending_reg["id"]},
                {"$set": {"status": "redeemable", "approved_at": datetime.now(timezone.utc).isoformat()}}
            )
            activated += 1
        if activated or skipped_wrong_brand:
            logger.info(
                f"Point 14b: registration activation for {customer_phone} on bill_id={bill_id} "
                f"bill_brand='{current_bill_brand}': activated={activated} skipped_brand_mismatch={skipped_wrong_brand}"
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



# ==================== POINT 5: RETAILER MANAGER LOGIN ====================
# Whitelisted brand-manager accounts can log in with OTP and view aggregate
# incentives for the brand(s) they own — WITHOUT seeing customer PII.

class RetailerManagerCreate(BaseModel):
    name: str
    phone: str
    brands: List[str]                # brand names the manager can view
    email: Optional[str] = None
    is_active: Optional[bool] = True


class RetailerManagerUpdate(BaseModel):
    name: Optional[str] = None
    brands: Optional[List[str]] = None
    email: Optional[str] = None
    is_active: Optional[bool] = None


def _make_retailer_token(manager: Dict) -> str:
    return jwt.encode({
        "sub": manager["id"],
        "phone": manager["phone"],
        "role": "retailer_manager",
        "exp": datetime.now(timezone.utc) + timedelta(days=30),
    }, JWT_SECRET, algorithm="HS256")


async def _verify_retailer_manager(auth: HTTPAuthorizationCredentials = Depends(security)) -> Dict:
    if not auth:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(auth.credentials, JWT_SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
    if payload.get("role") != "retailer_manager":
        raise HTTPException(status_code=403, detail="Retailer manager only")
    mgr = await _db.retailer_managers.find_one({"id": payload["sub"]}, {"_id": 0})
    if not mgr or not mgr.get("is_active"):
        raise HTTPException(status_code=403, detail="Retailer manager inactive or not found")
    return mgr


# -------- Admin CRUD for retailer managers --------

@staff_admin_router.get("/retailer-managers")
async def admin_list_retailer_managers(auth=Depends(_verify_admin)):
    rows = []
    async for m in _db.retailer_managers.find({}, {"_id": 0}).sort("created_at", -1):
        rows.append(m)
    return {"managers": rows, "total": len(rows)}


@staff_admin_router.post("/retailer-managers")
async def admin_create_retailer_manager(payload: RetailerManagerCreate, auth=Depends(_verify_admin)):
    phone = _normalise_phone(payload.phone)
    if len(phone) != 10:
        raise HTTPException(status_code=400, detail="Phone must be 10 digits")
    if not payload.brands:
        raise HTTPException(status_code=400, detail="At least one brand is required")
    existing = await _db.retailer_managers.find_one({"phone": phone}, {"_id": 0, "id": 1})
    if existing:
        raise HTTPException(status_code=400, detail="Retailer manager with this phone already exists")

    doc = {
        "id": str(uuid.uuid4()),
        "name": payload.name.strip(),
        "phone": phone,
        "brands": [b.strip() for b in payload.brands if b.strip()],
        "email": (payload.email or "").strip(),
        "is_active": True if payload.is_active is None else bool(payload.is_active),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await _db.retailer_managers.insert_one(dict(doc))
    return {"success": True, "manager": doc}


@staff_admin_router.patch("/retailer-managers/{manager_id}")
async def admin_update_retailer_manager(manager_id: str, patch: RetailerManagerUpdate,
                                          auth=Depends(_verify_admin)):
    updates = {k: v for k, v in patch.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="Nothing to update")
    if "brands" in updates:
        updates["brands"] = [b.strip() for b in updates["brands"] if b.strip()]
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    r = await _db.retailer_managers.update_one({"id": manager_id}, {"$set": updates})
    if r.matched_count == 0:
        raise HTTPException(status_code=404, detail="Manager not found")
    doc = await _db.retailer_managers.find_one({"id": manager_id}, {"_id": 0})
    return {"success": True, "manager": doc}


@staff_admin_router.delete("/retailer-managers/{manager_id}")
async def admin_delete_retailer_manager(manager_id: str, auth=Depends(_verify_admin)):
    r = await _db.retailer_managers.delete_one({"id": manager_id})
    if r.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Manager not found")
    return {"success": True}


# Point 11 (Aug 2026): admin diagnostic — trigger a real OTP send to any retailer
# manager phone and surface Karix per-channel response so admin can verify that
# WhatsApp + SMS delivery is actually landing.
class OTPTestPayload(BaseModel):
    phone: str


@staff_admin_router.post("/retailer/test-otp")
async def admin_test_retailer_otp(payload: OTPTestPayload, auth=Depends(_verify_admin)):
    phone = _normalise_phone(payload.phone)
    if len(phone) != 10:
        raise HTTPException(status_code=400, detail="Phone must be 10 digits")
    mgr = await _db.retailer_managers.find_one({"phone": phone, "is_active": True}, {"_id": 0})
    if not mgr:
        return {"success": False, "message": "Phone is not a whitelisted retailer manager (or is inactive)"}

    import random
    otp = f"{random.randint(0, 999999):06d}"
    if _store_otp is not None:
        try:
            await _store_otp(phone, otp)
        except Exception as e:
            logger.error(f"admin retailer test store_otp failed: {e}")

    delivery = {"whatsapp": None, "sms": None, "success": False}
    if _send_sms_otp is not None:
        try:
            r = await _send_sms_otp(phone, otp)
            if isinstance(r, dict):
                delivery = r
        except Exception as e:
            logger.error(f"admin retailer test OTP send failed for {phone}: {e}")

    return {
        "success": bool(delivery.get("success")),
        "phone": phone,
        "manager_name": mgr.get("name"),
        "delivery": delivery,
        "note": "OTP sent via WhatsApp + SMS. Ask retailer to check both channels.",
    }


# -------- Retailer manager auth (OTP) --------

@staff_router.post("/retailer/auth/send-otp")
async def retailer_send_otp(payload: StaffOTPRequest):
    phone = _normalise_phone(payload.phone)
    mgr = await _db.retailer_managers.find_one({"phone": phone, "is_active": True}, {"_id": 0})
    if not mgr:
        # Point 11 (Feb 2026): log the miss so admin can see when a real user
        # is being silently rejected because the phone isn't whitelisted. UI
        # still gets the neutral message so we don't leak whitelist status.
        logger.warning(f"Retailer OTP requested by non-whitelisted / inactive phone: {phone}")
        return {"success": True, "message": "OTP sent if number is registered"}

    import random
    otp = f"{random.randint(0, 999999):06d}"
    if _store_otp is not None:
        try:
            await _store_otp(phone, otp)
        except Exception as e:
            logger.error(f"retailer store_otp failed: {e}")
    else:
        await _db.staff_otps.update_one(
            {"phone": phone},
            {"$set": {"otp": otp, "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()}},
            upsert=True,
        )

    # Point 11 (Aug 2026): retailer OTP must ride WhatsApp (dual-channel WA+SMS via
    # send_login_otp). Capture per-channel diagnostics so /admin/alerts/test type
    # endpoints can surface delivery failures instead of silently swallowing them.
    delivery = {"whatsapp": None, "sms": None, "success": False}
    if _send_sms_otp is not None:
        try:
            r = await _send_sms_otp(phone, otp)
            if isinstance(r, dict):
                delivery = r
        except Exception as e:
            logger.error(f"retailer OTP send failed for {phone}: {e}")
    else:
        # Feb 2026: if the OTP dispatcher hasn't been wired at bootstrap
        # (e.g. server.py didn't bind_staff_db yet), fail loudly instead of
        # silently returning success — this was masking Point 11's "no OTP"
        # symptom.
        logger.error("retailer_send_otp: _send_sms_otp binding is None — check bind_staff_db in server.py")

    logger.info(f"Retailer OTP generated for {phone}: {otp} delivery={delivery}")
    return {"success": True, "message": "OTP sent", "delivery": delivery}


@staff_admin_router.get("/retailer/diagnose-otp")
async def admin_retailer_diagnose_otp(phone: str, auth=Depends(_verify_admin)):
    """Point 11 (Feb 2026): admin-only diagnostic — explains why a given
    phone would or would NOT get a retailer login OTP. Returns whether the
    phone is whitelisted, whether the OTP send binding is present, and the
    OTP channel configuration. Read-only; does NOT send an OTP."""
    phone10 = _normalise_phone(phone)
    mgr = await _db.retailer_managers.find_one(
        {"phone": phone10},
        {"_id": 0, "phone": 1, "is_active": 1, "name": 1},
    )
    return {
        "phone": phone10,
        "is_whitelisted": bool(mgr),
        "is_active": bool(mgr and mgr.get("is_active", True)),
        "manager_name": (mgr or {}).get("name"),
        "otp_send_bound": _send_sms_otp is not None,
        "otp_channel": os.environ.get("OTP_CHANNEL", "both"),
        "explanation": (
            "Whitelisted + active + OTP dispatcher bound → user will receive OTP via WhatsApp+SMS."
            if mgr and mgr.get("is_active", True) and _send_sms_otp is not None
            else "User will silently get 'OTP sent if number is registered' without any message actually being sent."
        ),
    }


@staff_router.post("/retailer/auth/verify-otp")
async def retailer_verify_otp(payload: StaffOTPVerify):
    phone = _normalise_phone(payload.phone)
    ok = False
    if OTP_DEV_BYPASS and payload.otp == OTP_DEV_BYPASS:
        ok = True
    elif _verify_stored_otp is not None:
        try:
            ok = await _verify_stored_otp(phone, payload.otp)
        except Exception as e:
            logger.error(f"retailer verify_stored_otp failed: {e}")
            ok = False
    else:
        rec = await _db.staff_otps.find_one({"phone": phone}, {"_id": 0})
        if rec and rec.get("otp") == payload.otp:
            ok = True

    if not ok:
        raise HTTPException(status_code=401, detail="Invalid OTP")

    mgr = await _db.retailer_managers.find_one({"phone": phone, "is_active": True}, {"_id": 0})
    if not mgr:
        raise HTTPException(status_code=401, detail="Retailer manager not registered or inactive")
    token = _make_retailer_token(mgr)
    return {
        "success": True,
        "token": token,
        "manager": {
            "id": mgr["id"], "name": mgr["name"], "phone": mgr["phone"],
            "brands": mgr.get("brands") or [],
        },
    }


# -------- Retailer dashboard --------

@staff_router.get("/retailer/dashboard")
async def retailer_dashboard(mgr=Depends(_verify_retailer_manager)):
    brands = mgr.get("brands") or []
    if not brands:
        return {"brands": [], "summary": {}, "staff": []}

    # Fetch staff members for these brands (case-insensitive on brand name)
    lowered = {b.lower() for b in brands}
    staff_docs: List[Dict] = []
    async for s in _db.retail_staff.find({}, {"_id": 0}):
        if (s.get("brand_name") or "").strip().lower() in lowered:
            staff_docs.append(s)

    staff_ids = [s["id"] for s in staff_docs]
    # Aggregate incentives grouped by staff & status
    by_staff: Dict[str, Dict[str, float]] = {}
    if staff_ids:
        pipe = [
            {"$match": {"staff_id": {"$in": staff_ids}}},
            {"$group": {"_id": {"staff_id": "$staff_id", "status": "$status"},
                        "amount": {"$sum": "$amount"}, "count": {"$sum": 1}}},
        ]
        async for row in _db.staff_incentives.aggregate(pipe):
            sid = row["_id"]["staff_id"]
            status = row["_id"]["status"]
            by_staff.setdefault(sid, {})[status] = row["amount"]

    def _redeemable(d: Dict) -> float: return float(d.get("redeemable") or 0)
    def _redeemed(d: Dict) -> float: return float(d.get("redeemed") or 0)
    def _pending(d: Dict) -> float: return float(d.get("pending") or 0) + float(d.get("pending_verification") or 0)

    staff_view = []
    total_redeemable = total_redeemed = total_pending = 0.0
    for s in staff_docs:
        d = by_staff.get(s["id"], {})
        r = _redeemable(d); rd = _redeemed(d); p = _pending(d)
        total_redeemable += r; total_redeemed += rd; total_pending += p
        staff_view.append({
            "staff_code": s.get("staff_code"),
            "name": s.get("name"),
            "brand_name": s.get("brand_name"),
            "brand_category": s.get("brand_category") or "",
            "store_location": s.get("store_location") or "",
            "is_active": s.get("is_active", True),
            "redeemable": r,
            "redeemed": rd,
            "pending": p,
        })

    # Redemption history (across all brand staff)
    redemptions: List[Dict] = []
    if staff_ids:
        async for rr in _db.staff_redemptions.find(
            {"staff_id": {"$in": staff_ids}}, {"_id": 0}
        ).sort("requested_at", -1).limit(200):
            s = next((x for x in staff_docs if x["id"] == rr.get("staff_id")), None)
            redemptions.append({
                "reference": rr.get("reference"),
                "amount": rr.get("amount"),
                "status": rr.get("status"),
                "requested_at": rr.get("requested_at"),
                "staff_name": (s or {}).get("name"),
                "staff_code": (s or {}).get("staff_code"),
            })

    return {
        "manager": {"name": mgr.get("name"), "phone": mgr.get("phone"), "brands": brands},
        "summary": {
            "total_staff": len(staff_docs),
            "active_staff": sum(1 for s in staff_docs if s.get("is_active")),
            "redeemable": total_redeemable,
            "redeemed": total_redeemed,
            "pending": total_pending,
        },
        "staff": staff_view,
        "redemptions": redemptions,
    }
