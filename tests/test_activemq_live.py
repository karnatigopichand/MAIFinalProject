"""Opt-in real ActiveMQ verification. Requires installed stomp.py and a live broker."""
import json
import os
from pathlib import Path
import sys
import threading
import unittest
import uuid
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'sample-repositories/commerce-orders/src'))
from commerce_orders.runtime import ActiveMQEvents, broker_connection, connect

@unittest.skipUnless(os.environ.get('ACTIVEMQ_TEST_HOST'),'Set ACTIVEMQ_TEST_HOST to run live broker verification')
class LiveBrokerTests(unittest.TestCase):
    def test_real_persistent_fanout_and_ack(self):
        queues=['/queue/commerce.integration.shipping','/queue/commerce.integration.notifications']
        config={'service':'integration-test','mq':{'host':os.environ['ACTIVEMQ_TEST_HOST'],'port':int(os.environ.get('ACTIVEMQ_TEST_PORT','61613')),'username_env':'ACTIVEMQ_USERNAME','password_env':'ACTIVEMQ_PASSWORD','publish':{'integration.v1':queues}}}
        received=[];done=threading.Event();event_id=str(uuid.uuid4())
        connection=broker_connection(config)
        class Listener:
            def on_message(self,frame):
                value=json.loads(frame.body)
                connection.ack(id=frame.headers['ack'])
                if value.get('event_id')==event_id:
                    received.append(frame.headers['destination'])
                    if len(received)==2:done.set()
            def __getattr__(self,name):return lambda *args,**kwargs:None
        connection.set_listener('integration',Listener())
        try:
            connect(connection,config)
            for i,q in enumerate(queues):connection.subscribe(destination=q,id=str(i),ack='client-individual')
            ActiveMQEvents(config).publish('integration.v1',{'event_id':event_id})
            self.assertTrue(done.wait(10),'Did not receive both queue deliveries')
            self.assertCountEqual(received,queues)
        finally:
            if connection.is_connected():connection.disconnect()
