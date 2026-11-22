"""MQTT delivery reuses the HTTP telemetry validation and transaction semantics."""
import json
import logging
import os
import re
from database import SessionLocal
from schemas.iot_device import Telemetry

log=logging.getLogger(__name__)

def process_message(topic,payload):
    if len(payload)>16384: raise ValueError('MQTT payload too large')
    match=re.fullmatch(r'parkly/devices/([A-Za-z0-9_-]+)/telemetry',topic)
    if not match: raise ValueError('Invalid MQTT topic')
    body=json.loads(payload)
    if not isinstance(body,dict) or set(body)!={'api_key','telemetry'}: raise ValueError('Invalid MQTT envelope')
    key=body['api_key']
    if not isinstance(key,str) or len(key)>256: raise ValueError('Invalid device key')
    data=Telemetry.model_validate(body['telemetry'])
    from routers.iot_devices import telemetry
    with SessionLocal() as db:
        try: return telemetry(match[1],data,key,db)
        except Exception: db.rollback();raise

def start_bridge():
    if os.getenv('MQTT_ENABLED')!='1': return None
    import paho.mqtt.client as mqtt
    from uuid import uuid4
    client=mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,client_id='parkly-backend-'+uuid4().hex[:10])
    if os.getenv('MQTT_USER'): client.username_pw_set(os.getenv('MQTT_USER'),os.getenv('MQTT_PASSWORD'))
    if os.getenv('MQTT_TLS')=='1': client.tls_set(ca_certs=os.getenv('MQTT_CA_CERT') or None)
    def connected(c,u,flags,reason,properties):
        if reason==0: c.subscribe('parkly/devices/+/telemetry',qos=1)
    def received(c,u,message):
        try:
            if message.retain: return  # Stored snapshots must not revive stale sensors.
            result=process_message(message.topic,message.payload)
            c.publish(message.topic.rsplit('/',1)[0]+'/ack',json.dumps(result),qos=1,retain=False)
        except Exception:
            # Never log envelopes: they contain device credentials.
            log.warning('MQTT telemetry rejected (invalid, stale, duplicate conflict or unavailable database)')
    client.on_connect=connected;client.on_message=received
    client.reconnect_delay_set(1,15)
    client.connect_async(os.getenv('MQTT_HOST','127.0.0.1'),int(os.getenv('MQTT_PORT','1883')),keepalive=30)
    client.loop_start()
    return client

def stop_bridge(client):
    if client: client.disconnect();client.loop_stop()
