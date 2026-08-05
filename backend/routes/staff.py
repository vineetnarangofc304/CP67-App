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
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks, UploadFile, File, Form
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
    staff = []
    async for s in _db.retail_staff.find(q, {"_id": 0}).sort("created_at", -1):
        staff.append(s)
    return {"staff": staff, "total": len(staff)}


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
    wa_phone = os.environ.get("WA_BUSINESS_PHONE") or "917988077663"

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
    col_name = h("staff name") or h("name")
    col_phone = h("contact no.") or h("contact") or h("phone")
    col_desig = h("designation") or h("role")
    col_store = h("store location") or h("store")
    col_email = h("email")

    if not (col_brand and col_name and col_phone):
        raise HTTPException(
            status_code=400,
            detail="CSV missing required columns. Need: Brand Name, Staff Name, Contact No.",
        )

    # Parse + ffill brand name
    parsed = []
    last_brand = ""
    for row in reader:
        brand_cell = (row.get(col_brand) or "").strip()
        if brand_cell:
            last_brand = brand_cell
        parsed.append({
            "brand": last_brand,
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

    if _send_sms_otp is not None:
        try:
            r = await _send_sms_otp(phone, otp)
            logger.info(f"Staff OTP SMS to {phone}: {r}")
        except Exception as e:
            logger.error(f"staff SMS send failed for {phone}: {e}")

    logger.info(f"Staff OTP generated for {phone}: {otp}")  # dev observability
    return {"success": True, "message": "OTP sent"}


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
