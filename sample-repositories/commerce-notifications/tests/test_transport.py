import contextlib
import io
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from types import SimpleNamespace
from commerce_notifications.runtime import HTTPClient, DownstreamError, ActiveMQEvents, log, load_config

class TransportTests(unittest.TestCase):
    def test_real_http_roundtrip_and_error(self):
        received=[]
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args): pass
            def do_POST(self):
                received.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
                self.send_response(422 if self.path=='/reject' else 200)
                self.end_headers(); self.wfile.write(b'{"ok":true}')
        server=HTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        client=HTTPClient({'service':'test','http':{'remote-api':{'scheme':'http','host':'127.0.0.1','port':server.server_port,'endpoints':{'create':'/resource','reject':'/reject'}}}})
        try:
            self.assertEqual(client.post('remote-api','/resource',{'value':3}),{'ok':True})
            self.assertEqual(received,[{'value':3}])
            with self.assertRaises(DownstreamError): client.post('remote-api','/reject',{})
            with self.assertRaises(ValueError): client.post('remote-api','/unconfigured',{})
        finally: server.shutdown();server.server_close();thread.join()
    def test_json_log_format(self):
        output=io.StringIO()
        with contextlib.redirect_stdout(output): log('test','request.complete',status_code=200)
        record=json.loads(output.getvalue())
        self.assertEqual(record['service'],'test')
        self.assertEqual(record['status'],'INFO')
        self.assertIn('timestamp',record)
    def test_broker_persistent_fanout_receipts(self):
        class Connection:
            def __init__(self): self.sent=[];self.connected=False
            def set_listener(self,name,listener): self.listener=listener
            def connect(self,*args,**kwargs): self.connected=True
            def is_connected(self): return self.connected
            def disconnect(self): self.connected=False
            def send(self,**kwargs):
                self.sent.append(kwargs)
                self.listener.on_receipt(SimpleNamespace(headers={'receipt-id':kwargs['headers']['receipt']}))
        connection=Connection()
        config={'service':'test','mq':{'username_env':'TEST_MQ_USER','password_env':'TEST_MQ_PASS','publish':{'event.v1':['/queue/a','/queue/b']}}}
        ActiveMQEvents(config,lambda c:connection).publish('event.v1',{'event_id':'1'})
        self.assertEqual([s['destination'] for s in connection.sent],['/queue/a','/queue/b'])
        self.assertTrue(all(s['headers']['persistent']=='true' for s in connection.sent))
        self.assertFalse(connection.connected)
    def test_environment_configs(self):
        local=load_config('config/local.json'); development=load_config('config/development.json')
        self.assertEqual(local['server']['port'],development['server']['port'])
        for target,endpoint in development['http'].items(): self.assertEqual(endpoint['host'],target)

    def test_worker_ack_and_failure_nack(self):
        from commerce_notifications.app import run_worker
        for fail in (False,True):
            class Connection:
                connected=False
                acked=[]
                nacked=[]
                def set_listener(self,name,listener): self.listener=listener
                def connect(self,*args,**kwargs): self.connected=True
                def is_connected(self): return self.connected
                def disconnect(self): self.connected=False
                def ack(self,id): self.acked.append(id)
                def nack(self,id): self.nacked.append(id)
                def subscribe(self,**kwargs):
                    assert kwargs['ack']=='client-individual'
                    self.listener.on_message(SimpleNamespace(headers={'destination':'/queue/in','ack':'ack-1'},body='{"order_id":"1"}'))
                    self.listener.on_disconnected()
            class DB:
                def close(self): pass
            class Consumer:
                db=DB()
                def consume(self,topic,event):
                    if fail: raise ValueError('invalid event')
                    assert topic=='event.v1'
            connection=Connection();connection.acked=[];connection.nacked=[]
            config={'service':'test','mq':{'consume':{'/queue/in':'event.v1'},'username_env':'TEST_USER','password_env':'TEST_PASS'}}
            run_worker(config,lambda c:connection,lambda c:Consumer())
            self.assertEqual(connection.nacked,['ack-1'] if fail else [])
            self.assertEqual(connection.acked,[] if fail else ['ack-1'])
