import asyncio
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient


async def main():
    load_dotenv('/app/backend/.env')
    client = AsyncIOMotorClient(os.environ['MONGO_URL'])
    db = client[os.environ.get('DB_NAME', 'cp67_loyalty')]

    staff_query = {
        '$or': [
            {'brand_name': 'BV46_STAFF_VERIFY_BRAND'},
            {'phone': {'$in': ['9304697302', '9304797302']}},
        ]
    }
    coupon_query = {
        'brand_name': 'BV46_VERIFY_BRAND',
        'code': {'$in': ['BV46_A', 'BV46_B']},
    }
    brand_query = {'brand_name': {'$in': ['BV46_STAFF_VERIFY_BRAND', 'BV46_VERIFY_BRAND']}}

    pre_staff = await db.retail_staff.count_documents(staff_query)
    pre_coupons = await db.coupon_codes.count_documents(coupon_query)
    staff_delete = await db.retail_staff.delete_many(staff_query)
    coupon_delete = await db.coupon_codes.delete_many(coupon_query)
    brand_delete = await db.brands.delete_many(brand_query)
    post_staff = await db.retail_staff.count_documents(staff_query)
    post_coupons = await db.coupon_codes.count_documents(coupon_query)
    total_staff = await db.retail_staff.count_documents({})

    result = {
        'pre_staff_matches': pre_staff,
        'deleted_staff': staff_delete.deleted_count,
        'post_staff_matches': post_staff,
        'pre_coupon_matches': pre_coupons,
        'deleted_coupon_leftovers': coupon_delete.deleted_count,
        'post_coupon_matches': post_coupons,
        'deleted_brand_docs': brand_delete.deleted_count,
        'final_staff_total': total_staff,
    }
    out = Path('/app/test_reports/ui_46/bug46_cleanup_results.json')
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))
    client.close()


if __name__ == '__main__':
    asyncio.run(main())