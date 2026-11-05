"""Network adapters: configured HTTP, ActiveMQ STOMP, SQLite, JSON logs."""
import json
import hmac
import ipaddress
import logging
import os
import sqlite3
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib import request, error


def load_config(path=None):
    path = Path(path or os.environ.get('COMMERCE_CONFIG', 'config/local.json'))
    config = json.loads(path.read_text())
    if not config.get('service') or not config.get('server'):
        raise ValueError('Config requires service and server')
    return config


def log(service, event, level='INFO', **fields):
    # Callers provide allowlisted metadata, never request bodies or credentials.
    record = {'timestamp': datetime.now(timezone.utc).isoformat(), 'status': level,
              'service': service, 'env': os.environ.get('COMMERCE_ENV', 'local'),
              'event': event, **fields}
    print(json.dumps(record, separators=(',', ':')), file=sys.stdout, flush=True)


class Database:
    def __init__(self, path=':memory:'):
        if path != ':memory:':
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path, timeout=10)
        self.connection.execute('CREATE TABLE IF NOT EXISTS records (kind TEXT, key TEXT, payload TEXT, PRIMARY KEY(kind,key))')
    def get(self, kind, key):
        row = self.connection.execute('SELECT payload FROM records WHERE kind=? AND key=?', (kind,str(key))).fetchone()
        return json.loads(row[0]) if row else None
    def put(self, kind, key, value):
        self.connection.execute('INSERT OR REPLACE INTO records VALUES (?,?,?)', (kind,str(key),json.dumps(value)))
        self.connection.commit()
    def close(self):
        self.connection.close()


class DownstreamError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


def api_token():
    return os.environ.get('COMMERCE_API_TOKEN', '')


def request_authorized(handler):
    token = api_token()
    if not token:
        return True
    supplied = handler.headers.get('Authorization', '')
    candidate = supplied[7:] if supplied.startswith('Bearer ') else ''
    return hmac.compare_digest(candidate, token)


def validate_server_binding(config):
    host = config['server']['host']
    try:
        exposed = not ipaddress.ip_address(host).is_loopback
    except ValueError:
        exposed = host not in {'localhost'}
    required = config.get('environment', 'local') != 'local' or exposed
    if required and not api_token():
        raise RuntimeError('COMMERCE_API_TOKEN is required outside loopback local mode')


class HTTPClient:
    def __init__(self, config):
        self.config = config
    def post(self, target, path, payload):
        endpoint = self.config['http'][target]
        if path not in endpoint['endpoints'].values():
            raise ValueError('Unconfigured endpoint')
        url = f"{endpoint['scheme']}://{endpoint['host']}:{endpoint['port']}{path}"
        headers = {'Content-Type':'application/json', 'X-Request-ID':str(uuid.uuid4())}
        if target in {'payment-provider-api', 'carrier-provider-api'}:
            token_name = target.replace('-', '_').upper() + '_TOKEN'
            token = os.environ.get(token_name, '')
        else:
            token = api_token()
        if token:
            headers['Authorization'] = f'Bearer {token}'
        req = request.Request(url, data=json.dumps(payload).encode(), headers=headers, method='POST')
        start = time.monotonic()
        try:
            with request.urlopen(req, timeout=endpoint.get('timeout_seconds',5)) as response:
                result = json.load(response)
            log(self.config['service'],'http.client',target=target,path=path,status_code=200,duration_ms=round((time.monotonic()-start)*1000,2))
            return result
        except error.HTTPError as exc:
            log(self.config['service'],'http.client.failed','ERROR',target=target,path=path,status_code=exc.code)
            # Do not log/return potentially sensitive upstream response bodies.
            status = exc.code
            exc.close()
            raise DownstreamError(status, f'{target} rejected request') from exc
        except (error.URLError, TimeoutError, OSError) as exc:
            log(self.config['service'],'http.client.unavailable','ERROR',target=target,path=path)
            raise DownstreamError(503, f'{target} unavailable') from exc


def broker_connection(config):
    import stomp
    broker = config['mq']
    connection = stomp.Connection12([(broker['host'],broker['port'])], heartbeats=(10000,10000), timeout=broker.get('connect_timeout_seconds',5), reconnect_attempts_max=1)
    if broker.get('tls'):
        connection.set_ssl(for_hosts=[(broker['host'],broker['port'])], ca_certs=broker['ca_certs'])
    return connection


def connect(connection, config):
    broker = config['mq']
    connection.connect(os.environ.get(broker['username_env'],''),
                       os.environ.get(broker['password_env'],''), wait=True)


class ActiveMQEvents:
    def __init__(self, config, connection_factory=broker_connection):
        self.config, self.connection_factory = config, connection_factory
    def publish(self, topic, payload):
        destinations = self.config['mq']['publish'][topic]
        connection = self.connection_factory(self.config)
        receipts = {}
        # STOMP listener callbacks used by stomp.py.
        class ReceiptListener:
            def on_receipt(self, frame):
                item = receipts.get(frame.headers.get('receipt-id'))
                if item: item.set()
            def on_error(self, frame):
                log(self_outer.config['service'],'mq.error','ERROR')
            def __getattr__(self, name):
                return lambda *args, **kwargs: None
        self_outer = self
        connection.set_listener('receipts',ReceiptListener())
        try:
            connect(connection,self.config)
            for destination in destinations:
                receipt = str(uuid.uuid4())
                receipts[receipt] = threading.Event()
                connection.send(destination=destination,body=json.dumps(payload),headers={
                    'content-type':'application/json','persistent':'true','event-type':topic,'receipt':receipt})
                if not receipts[receipt].wait(self.config['mq'].get('receipt_timeout_seconds',5)):
                    raise TimeoutError('ActiveMQ receipt not received')
                log(self.config['service'],'mq.published',topic=topic,queue=destination,event_id=payload.get('event_id'))
        finally:
            if connection.is_connected(): connection.disconnect()


def publish_pending(db, events, topic, payload):
    """Retry publication on request/event redelivery; crash-window duplicates remain possible."""
    key = topic + ':' + payload['event_id']
    if not db.get('published_events',key):
        events.publish(topic,payload)
        db.put('published_events',key,{'event_id':payload['event_id'],'status':'sent'})


def configure_logging(config):
    """Keep third-party library logs JSON as well as application logs."""
    class JSONFormatter(logging.Formatter):
        def format(self, record):
            return json.dumps({'timestamp':datetime.now(timezone.utc).isoformat(),
                'status':record.levelname,'service':config['service'],
                'env':config['environment'],'event':'library.log',
                'logger':record.name,'message':record.getMessage()})
    handler=logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())
    logging.basicConfig(level=logging.INFO,handlers=[handler],force=True)
