"""Seed / remove a TEST_ITER74_ 3:1 banner with edge markers to validate Point 43 (no side cropping)."""
import asyncio
import base64
import io
import sys
import uuid
from datetime import datetime, timezone

sys.path.insert(0, "/app/backend")
import server  # noqa: E402

from PIL import Image, ImageDraw  # noqa: E402

TITLE = "TEST_ITER74_BANNER"


def make_image():
    img = Image.new("RGB", (1200, 400), (20, 60, 140))
    d = ImageDraw.Draw(img)
    # left/right edge markers (red bars) — cropped sides would hide these
    d.rectangle([0, 0, 40, 399], fill=(255, 0, 0))
    d.rectangle([1159, 0, 1199, 399], fill=(255, 0, 0))
    d.rectangle([580, 180, 620, 220], fill=(0, 255, 0))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=80)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


async def seed():
    doc = {
        "id": str(uuid.uuid4()),
        "title": TITLE,
        "subtitle": "iter74 point43 check",
        "image_url": make_image(),
        "link_type": "none",
        "link_id": None,
        "position": 0,
        "is_active": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await server.db.banners.insert_one(doc)
    print("seeded", doc["id"])


async def remove():
    r = await server.db.banners.delete_many({"title": TITLE})
    print("deleted", r.deleted_count)


if __name__ == "__main__":
    asyncio.run(remove() if len(sys.argv) > 1 and sys.argv[1] == "remove" else seed())
