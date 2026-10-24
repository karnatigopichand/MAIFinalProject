"""Runnable HTTP API and ActiveMQ worker. Run from repository root."""
import argparse
import json
import os
import signal
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse
from .runtime import Database, HTTPClient, ActiveMQEvents, DownstreamError, load_config, log, broker_connection, connect, configure_logging
from .service import Service


def make_service(config):
    return Service(db=Database(config['database']['path']),http=HTTPClient(config),events=ActiveMQEvents(config))


def make_handler(config, service_factory=make_service):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass  # Suppress non-JSON access logs.
        def respond(self,status,payload):
            encoded=json.dumps(payload).encode()
            self.send_response(status)
            self.send_header('Content-Type','application/json')
            self.send_header('Content-Length',str(len(encoded)))
            self.end_headers(); self.wfile.write(encoded)
            log(config['service'],'http.server',method=self.command,path=urlparse(self.path).path,status_code=status)
        def do_GET(self):
            path=urlparse(self.path).path
            if path=='/health':
                self.respond(200,{'service':config['service'],'status':'up','dependency_check':False}); return
            route=config['api']['read_path']+'/'
            if not path.startswith(route) or not path[len(route):]:
                self.respond(404,{'error':'not_found'}); return
            service=service_factory(config)
            try:
                value=service.db.get(config['api']['record_kind'],path[len(route):])
                self.respond(200 if value else 404,value or {'error':'not_found'})
            finally: service.db.close()
        def do_POST(self):
            path=urlparse(self.path).path
            method=config['api']['write_routes'].get(path)
            if not method:
                self.respond(404,{'error':'not_found'}); return
            service=None
            try:
                size=int(self.headers.get('Content-Length','0'))
                if size<=0 or size>1048576:
                    self.respond(400,{'error':'invalid_body_size'}); return
                payload=json.loads(self.rfile.read(size))
                if not isinstance(payload,dict): raise ValueError('Object required')
                service=service_factory(config)
                if method=='seed_stock':
                    service.seed_stock(payload['sku'],payload['quantity'])
                    result={'sku':payload['sku'],'quantity':payload['quantity']}
                else: result=getattr(service,method)(payload)
                self.respond(200,result)
            except (ValueError, KeyError, TypeError):
                self.respond(422,{'error':'invalid_request_or_business_rejection'})
            except DownstreamError as exc:
                self.respond(422 if 400<=exc.status<500 else 502,{'error':'downstream_failure'})
            except Exception as exc:
                log(config['service'],'request.failed','ERROR',error_type=type(exc).__name__)
                self.respond(503,{'error':'dependency_or_storage_failure'})
            finally:
                if service: service.db.close()
    return Handler


def run_worker(config, connection_factory=broker_connection, service_factory=make_service):
    connection=connection_factory(config)
    stopped=threading.Event()
    class Listener:
        def on_message(self,frame):
            service=None
            try:
                destination=frame.headers['destination']
                topic=config['mq']['consume'][destination]
                service=service_factory(config)
                service.consume(topic,json.loads(frame.body))
                connection.ack(id=frame.headers['ack'])
                log(config['service'],'mq.consumed',queue=destination,topic=topic)
            except Exception as exc:
                log(config['service'],'mq.consume.failed','ERROR',error_type=type(exc).__name__)
                connection.nack(id=frame.headers['ack'])
            finally:
                if service: service.db.close()
        def on_disconnected(self): stopped.set()
        def on_error(self,frame):
            log(config['service'],'mq.error','ERROR'); stopped.set()
        def __getattr__(self,name): return lambda *args,**kwargs: None
    connection.set_listener('consumer',Listener())
    def stop(*args): stopped.set()
    if threading.current_thread() is threading.main_thread():
        signal.signal(signal.SIGTERM,stop); signal.signal(signal.SIGINT,stop)
    try:
        connect(connection,config)
        for index,queue in enumerate(config['mq']['consume']):
            connection.subscribe(destination=queue,id=str(index),ack='client-individual',headers={'activemq.prefetchSize':'1'})
            log(config['service'],'mq.subscribed',queue=queue)
        stopped.wait()
    finally:
        if connection.is_connected(): connection.disconnect()


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--config',default=None)
    parser.add_argument('--worker',action='store_true')
    args=parser.parse_args()
    config=load_config(args.config)
    os.environ['COMMERCE_ENV']=config['environment']
    configure_logging(config)
    if args.worker:
        if not config['mq']['consume']: parser.error('This service has no queue subscriptions')
        run_worker(config)
    else:
        server=HTTPServer((config['server']['host'],config['server']['port']),make_handler(config))
        log(config['service'],'server.started',port=config['server']['port'])
        try: server.serve_forever()
        except KeyboardInterrupt: pass
        finally: server.server_close()

if __name__=='__main__':
    try: main()
    except Exception as exc:
        log('commerce.startup','process.failed','ERROR',error_type=type(exc).__name__)
        raise SystemExit(1)
