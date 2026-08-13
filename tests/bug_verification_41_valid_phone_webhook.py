import json, time, uuid, requests
from datetime import datetime, timezone
from pathlib import Path
from pymongo import MongoClient

def load_env(path):
    out={}
    for line in Path(path).read_text().splitlines():
        if '=' in line and not line.strip().startswith('#'):
            k,v=line.split('=',1); out[k]=v.strip().strip('"').strip("'")
    return out

env=load_env('/app/backend/.env')
client=MongoClient(env.get('MONGO_URL','mongodb://localhost:27017'))
db=client[env.get('DB_NAME','test_database')]
BASE='http://localhost:8001/api'
phone='919888410001'  # valid 91 + 10 digits
code='TEST41_VALID_PHONE_COUPON'
# cleanup before
db.coupon_codes.delete_many({'code': code})
db.users.delete_many({'phone': phone})
db.whatsapp_logs.delete_many({'user_phone': phone})
db.whatsapp_dedup.delete_many({'key': {'$regex': phone}})
db.fundle_customers.delete_many({'phone_10': phone[2:]})
db.blocked_phones.delete_many({'phone': phone[2:]})
# seed
db.coupon_codes.insert_one({'id': str(uuid.uuid4()), 'source_code':'SRC_RWA','brand_name':'TEST41_ValidBrand','code':code,'value':432,'expiry':'2026-12-31','status':'available','issued_to_phone':None,'issued_at':None,'created_at':datetime.now(timezone.utc).isoformat()})
payload={'events': {'eventType': 'USER MESSAGE'}, 'eventContent': {'message': {'from': phone, 'messageType': 'text', 'profileName': 'TEST41 Valid User', 'text': {'body': 'Hi! Register me for CP67 Loyalty — RWA valid | SRC_RWA'}}}}
r=requests.post(f'{BASE}/whatsapp/webhook', json=payload, timeout=60)
doc=None; logs=[]
for _ in range(35):
    doc=db.coupon_codes.find_one({'code':code}, {'_id':0})
    logs=list(db.whatsapp_logs.find({'user_phone': phone, 'direction':'outbound', 'content': {'$regex':'Welcome Coupon Unlocked'}}, {'_id':0,'content':1}))
    if doc and doc.get('status')=='issued' and logs:
        break
    time.sleep(2)
result={'status_code':r.status_code,'response':r.text[:200], 'coupon_doc':doc, 'coupon_logs': len(logs), 'log_excerpt': logs[0]['content'][:500] if logs else ''}
print(json.dumps(result, indent=2, default=str))
# cleanup
db.coupon_codes.delete_many({'code': code})
db.users.delete_many({'phone': phone})
db.whatsapp_logs.delete_many({'user_phone': phone})
db.whatsapp_dedup.delete_many({'key': {'$regex': phone}})
raise SystemExit(0 if result['status_code']==200 and doc and doc.get('status')=='issued' and logs and code in logs[0]['content'] else 1)
