"""Send an actual checkout HTTP request to a running deployment."""
import argparse
import json
from urllib.request import Request, urlopen
parser=argparse.ArgumentParser()
parser.add_argument('--url',default='http://127.0.0.1:8000/checkout')
parser.add_argument('--order-id',default='demo-1')
args=parser.parse_args()
payload={'checkout_id':args.order_id,'cart':{'items':[{'sku':'book','quantity':1}]},'total_cents':2500,'currency':'USD','delivery':{'address':'10 Main St'},'payment_token':'demo-token'}
request=Request(args.url,data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'},method='POST')
with urlopen(request,timeout=20) as response: print(response.read().decode())
