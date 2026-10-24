"""Real loopback HTTP integration; only external providers and MQ are test doubles."""
from pathlib import Path
import json
import sys
import tempfile
import threading
import unittest
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.request import Request,urlopen
from urllib.error import HTTPError
ROOT=Path(__file__).resolve().parents[1]
for repo in (ROOT/'sample-repositories').glob('commerce-*'): sys.path.insert(0,str(repo/'src'))
from commerce_checkout.app import make_handler
from commerce_checkout.runtime import Database, HTTPClient
from commerce_checkout.service import Service as Checkout
from commerce_orders.service import Service as Orders
from commerce_inventory.service import Service as Inventory
from commerce_payments.service import Service as Payments
from commerce_shipping.service import Service as Shipping
from commerce_notifications.service import Service as Notifications

class Events:
    def __init__(self): self.messages=[]
    def publish(self,topic,payload): self.messages.append((topic,payload))

class NetworkFlow(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.servers=[];self.threads=[];self.events=Events();self.configs={}
        class Provider(BaseHTTPRequestHandler):
            def log_message(self,*args): pass
            def do_POST(self):
                data=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                if self.path=='/charges':
                    value={'status':'declined'} if data['token']=='decline' else {'status':'authorized','authorization_id':'AUTH-1'}
                else: value={'tracking_number':'TRACK-1'}
                self.send_response(200);self.end_headers();self.wfile.write(json.dumps(value).encode())
        provider=self.start(Provider)
        classes={'checkout':Checkout,'orders':Orders,'inventory':Inventory,'payments':Payments,'shipping':Shipping,'notifications':Notifications}
        for name in classes:
            config=json.loads((ROOT/f'sample-repositories/commerce-{name}/config/local.json').read_text())
            config['database']['path']=str(Path(self.temp.name)/f'{name}.sqlite')
            self.configs[name]=config
        def factory(config):
            cls=classes[config['service'].removeprefix('commerce-')]
            return cls(db=Database(config['database']['path']),http=HTTPClient(config),events=self.events)
        self.factory=factory
        for name in classes:
            server=self.start(make_handler(self.configs[name],factory))
            self.configs[name]['test_port']=server.server_port
        for config in self.configs.values():
            for target,endpoint in config['http'].items():
                endpoint['port']=self.configs[target.removeprefix('commerce-')]['test_port'] if target.startswith('commerce-') else provider.server_port
        self.post('inventory','/stock',{'sku':'book','quantity':5})
    def start(self,handler):
        server=HTTPServer(('127.0.0.1',0),handler);self.servers.append(server)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();self.threads.append(thread)
        return server
    def tearDown(self):
        for s in self.servers: s.shutdown();s.server_close()
        for t in self.threads:t.join()
        self.temp.cleanup()
    def post(self,name,path,data):
        req=Request(f"http://127.0.0.1:{self.configs[name]['test_port']}{path}",data=json.dumps(data).encode(),headers={'Content-Type':'application/json'},method='POST')
        with urlopen(req,timeout=10) as response:return json.load(response)
    def payload(self,token='ok',quantity=1):
        return {'checkout_id':'1','cart':{'items':[{'sku':'book','quantity':quantity}]},'total_cents':100,'currency':'USD','delivery':{'address':'Main St'},'payment_token':token}
    def test_actual_http_flow_then_event_processing_and_read_api(self):
        result=self.post('checkout','/checkout',self.payload());self.assertEqual(result['status'],'confirmed')
        self.post('checkout','/checkout',self.payload())
        self.assertEqual(len(self.events.messages),1)
        topic,event=self.events.messages[0]
        for name in ('shipping','notifications'):
            service=self.factory(self.configs[name])
            try:service.consume(topic,event);service.consume(topic,event)
            finally:service.db.close()
        topic,event=self.events.messages[1]
        service=self.factory(self.configs['notifications'])
        try:service.consume(topic,event)
        finally:service.db.close()
        with urlopen(f"http://127.0.0.1:{self.configs['shipping']['test_port']}/shipments/1") as response:
            self.assertEqual(json.load(response)['tracking_number'],'TRACK-1')
    def test_stock_failure_is_http_rejection(self):
        with self.assertRaises(HTTPError) as result:self.post('checkout','/checkout',self.payload(quantity=6))
        self.assertEqual(result.exception.code,422);result.exception.close();self.assertEqual(self.events.messages,[])
    def test_payment_decline_is_http_rejection(self):
        with self.assertRaises(HTTPError) as result:self.post('checkout','/checkout',self.payload(token='decline'))
        self.assertEqual(result.exception.code,422);result.exception.close();self.assertEqual(self.events.messages,[])
    def test_health_and_missing_resource(self):
        for config in self.configs.values():
            with urlopen(f"http://127.0.0.1:{config['test_port']}/health") as response:
                self.assertEqual(json.load(response)['status'],'up')
        with self.assertRaises(HTTPError) as missing:
            urlopen(f"http://127.0.0.1:{self.configs['shipping']['test_port']}/shipments/missing")
        missing.exception.close()
