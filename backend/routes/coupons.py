"""
Point 26: RWA/Office Registration Coupon Inventory

Admin uploads coupon codes tied to a registration source (RWA, OFFICE, etc.).
When a new customer registers via that source's QR, the next available coupon
for that source is atomically issued to them and delivered on WhatsApp.

Data model — collection `coupon_codes`
  {
    id: uuid,
    source_code: 'SRC_RWA' | 'SRC_OFFICE' | ...,
    brand_name: str,
    code: str,                      # the actual coupon token
    value: float,                   # face value in ₹
    expiry: str (ISO date),
    status: 'available' | 'issued' | 'expired' | 'void',
    issued_to_phone: str | None,
    issued_at: str | None,
    created_at: str,
  }
"""
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import Optional, List, Dict
from datetime import datetime, timezone
import uuid
import jwt
import os
import csv
import io
import logging

logger = logging.getLogger(__name__)

coupons_admin_router = APIRouter(prefix="/api/admin/coupons")
security = HTTPBearer(auto_error=False)

_db = None
JWT_SECRET = os.environ.get('JWT_SECRET', 'cp67-secret-key-2025')


def bind_db(db):
    global _db
    _db = db


async def _verify_admin(auth: HTTPAuthorizationCredentials = Depends(security)) -> Dict:
    if not auth:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(auth.credentials, JWT_SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
    if payload.get("role") in ("retail_staff", "retailer_manager"):
        raise HTTPException(status_code=403, detail="Admin only")
    return payload


# ==================== TEMPLATE ====================

@coupons_admin_router.get("/template.csv")
async def coupons_template(auth=Depends(_verify_admin)):
    from fastapi.responses import Response
    body = (
        "Brand Name,Coupon Code,Coupon Value,Expiry Date\n"
        "Zara,ZARA100OFF,100,2026-12-31\n"
        "Croma,CROMA500,500,2026-12-31\n"
        "Haldiram,HALDIRAM50,50,2026-06-30\n"
    )
    return Response(
        content=body,
        media_type="text/csv",
        headers={
            "Content-Disposition": 'attachment; filename="coupon-upload-template.csv"',
            "Cache-Control": "no-store",
        },
    )


# ==================== BULK UPLOAD ====================

@coupons_admin_router.post("/bulk-upload")
async def coupons_bulk_upload(
    file: UploadFile = File(...),
    source_code: str = Form(...),
    dry_run: bool = Form(False),
    auth=Depends(_verify_admin),
):
    """Upload coupons for a registration source.

    CSV headers (case-insensitive):
        Brand Name, Coupon Code, Coupon Value, Expiry Date (YYYY-MM-DD)
    Rows without brand/code are invalid. Duplicate codes (same source_code) are
    skipped."""
    src = (source_code or "").strip().upper()
    if not src:
        raise HTTPException(status_code=400, detail="source_code is required (e.g. SRC_RWA, SRC_OFFICE)")
    try:
        raw = await file.read()
        text = raw.decode("utf-8-sig")
    except Exception:
        raise HTTPException(status_code=400, detail="Failed to read CSV — expected UTF-8 text")

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise HTTPException(status_code=400, detail="CSV appears empty or missing header row")
    norm = {h.strip().lower(): h for h in reader.fieldnames if h}
    col_brand = norm.get("brand name") or norm.get("brand")
    col_code = norm.get("coupon code") or norm.get("code")
    col_value = norm.get("coupon value") or norm.get("value") or norm.get("amount")
    col_expiry = norm.get("expiry date") or norm.get("expiry") or norm.get("valid till")
    if not (col_brand and col_code and col_value and col_expiry):
        raise HTTPException(
            status_code=400,
            detail="CSV missing required columns. Need: Brand Name, Coupon Code, Coupon Value, Expiry Date",
        )

    # Pre-load existing codes for this source to skip duplicates
    existing = set()
    async for c in _db.coupon_codes.find({"source_code": src}, {"_id": 0, "code": 1}):
        if c.get("code"):
            existing.add(c["code"].strip().upper())

    to_insert = []
    imported = []
    skipped = []
    invalid = []
    idx = 1
    from datetime import date as _date
    for row in reader:
        idx += 1
        brand = (row.get(col_brand) or "").strip()
        code = (row.get(col_code) or "").strip()
        value_raw = (row.get(col_value) or "").strip()
        expiry = (row.get(col_expiry) or "").strip()
        if not brand:
            invalid.append({"row": idx, "reason": "missing brand", "code": code})
            continue
        if not code:
            invalid.append({"row": idx, "reason": "missing code", "brand": brand})
            continue
        try:
            value = float(value_raw)
        except ValueError:
            invalid.append({"row": idx, "reason": "invalid value", "brand": brand, "code": code, "raw_value": value_raw})
            continue
        # Expiry date must be strict YYYY-MM-DD
        if not expiry:
            invalid.append({"row": idx, "reason": "missing expiry date", "brand": brand, "code": code})
            continue
        import re as _re
        if not _re.match(r"^\d{4}-\d{2}-\d{2}$", expiry):
            invalid.append({"row": idx, "reason": "invalid expiry date (need YYYY-MM-DD)", "brand": brand, "code": code, "raw_expiry": expiry})
            continue
        try:
            _date.fromisoformat(expiry)
        except ValueError:
            invalid.append({"row": idx, "reason": "invalid expiry date (need YYYY-MM-DD)", "brand": brand, "code": code, "raw_expiry": expiry})
            continue
        if code.upper() in existing:
            skipped.append({"row": idx, "brand": brand, "code": code, "reason": "duplicate for this source"})
            continue
        existing.add(code.upper())
        to_insert.append({
            "id": str(uuid.uuid4()),
            "source_code": src,
            "brand_name": brand,
            "code": code,
            "value": value,
            "expiry": expiry,
            "status": "available",
            "issued_to_phone": None,
            "issued_at": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        imported.append({"brand": brand, "code": code, "value": value, "expiry": expiry})

    if not dry_run and to_insert:
        await _db.coupon_codes.insert_many([dict(d) for d in to_insert])

    return {
        "success": True,
        "dry_run": dry_run,
        "source_code": src,
        "summary": {
            "total_rows": idx - 1,
            "imported": len(imported),
            "skipped_duplicates": len(skipped),
            "invalid": len(invalid),
        },
        "imported_preview": imported[:20],
        "skipped_preview": skipped[:20],
        "invalid_preview": invalid[:20],
    }


# ==================== INVENTORY ====================

@coupons_admin_router.get("/inventory")
async def coupons_inventory(source_code: Optional[str] = None, auth=Depends(_verify_admin)):
    """Return per-source × brand × status counts. Optionally filtered by source_code."""
    match: Dict = {}
    if source_code:
        match["source_code"] = source_code.strip().upper()
    pipe = []
    if match:
        pipe.append({"$match": match})
    pipe.extend([
        {"$group": {
            "_id": {"source_code": "$source_code", "brand_name": "$brand_name", "status": "$status"},
            "count": {"$sum": 1},
            "total_value": {"$sum": "$value"},
        }},
        {"$sort": {"_id.source_code": 1, "_id.brand_name": 1, "_id.status": 1}},
    ])
    rows = []
    async for r in _db.coupon_codes.aggregate(pipe):
        rows.append({
            "source_code": r["_id"]["source_code"],
            "brand_name": r["_id"]["brand_name"],
            "status": r["_id"]["status"],
            "count": r["count"],
            "total_value": r["total_value"],
        })

    # Also return top-level totals for the UI
    total = {"available": 0, "issued": 0, "expired": 0, "void": 0}
    for r in rows:
        st = r["status"]
        if st in total:
            total[st] += r["count"]

    return {"inventory": rows, "totals": total}


@coupons_admin_router.get("/issued")
async def coupons_issued(source_code: Optional[str] = None, limit: int = 200, auth=Depends(_verify_admin)):
    q: Dict = {"status": "issued"}
    if source_code:
        q["source_code"] = source_code.strip().upper()
    rows = []
    async for c in _db.coupon_codes.find(q, {"_id": 0}).sort("issued_at", -1).limit(limit):
        rows.append(c)
    return {"issued": rows, "total": len(rows)}


@coupons_admin_router.get("/list")
async def coupons_list(source_code: Optional[str] = None, status: Optional[str] = None,
                        brand_name: Optional[str] = None, limit: int = 500,
                        auth=Depends(_verify_admin)):
    q: Dict = {}
    if source_code:
        q["source_code"] = source_code.strip().upper()
    if status:
        q["status"] = status
    if brand_name:
        q["brand_name"] = brand_name
    rows = []
    async for c in _db.coupon_codes.find(q, {"_id": 0}).sort("created_at", -1).limit(limit):
        rows.append(c)
    return {"coupons": rows, "total": len(rows)}


class CouponDeleteRequest(BaseModel):
    ids: List[str]


@coupons_admin_router.post("/delete")
async def coupons_delete(payload: CouponDeleteRequest, auth=Depends(_verify_admin)):
    if not payload.ids:
        raise HTTPException(status_code=400, detail="No ids provided")
    r = await _db.coupon_codes.delete_many({"id": {"$in": payload.ids}, "status": "available"})
    return {"success": True, "deleted": r.deleted_count}


# ==================== ISSUE-ON-REGISTRATION ====================

async def issue_coupon_for_registration(phone: str, source_code: str) -> Optional[Dict]:
    """Atomically pick one available coupon for `source_code` and mark it
    issued to `phone`. Returns the issued coupon or None if inventory empty.

    Uses find_one_and_update with $set so two concurrent registrations can
    never receive the same coupon.
    """
    if _db is None:
        return None
    src = (source_code or "").strip().upper()
    if not src:
        return None
    now = datetime.now(timezone.utc).isoformat()
    updated = await _db.coupon_codes.find_one_and_update(
        {"source_code": src, "status": "available"},
        {"$set": {"status": "issued", "issued_to_phone": phone, "issued_at": now}},
        projection={"_id": 0},
        sort=[("created_at", 1)],
    )
    if updated:
        # Note: motor's find_one_and_update returns the ORIGINAL document by
        # default. Refetch by id to return the mutated state so the caller
        # sees status='issued'.
        fresh = await _db.coupon_codes.find_one({"id": updated["id"]}, {"_id": 0})
        return fresh
    return None
