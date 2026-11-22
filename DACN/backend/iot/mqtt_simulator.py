"""MQTT transport for existing persisted simulator scenarios, with application ACK."""
import argparse
import json
import os
from pathlib import Path
from threading import Event
import time
import paho.mqtt.client as mqtt
from simulator import exclusive,save_json,make_payload

def send(client,device,payload,ack,received):
    ack.clear();received.clear()
    envelope=json.dumps({'api_key':device['api_key'],'telemetry':payload})
    for attempt in range(3):
        client.publish(f"parkly/devices/{device['device_code']}/telemetry",envelope,qos=1,retain=False).wait_for_publish(timeout=5)
        if ack.wait(5): return dict(received)
    raise RuntimeError('Chưa nhận ACK từ backend; giữ bản tin để gửi lại')

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--config',type=Path,default=Path(__file__).with_name('devices.local.json'))
    parser.add_argument('--host',default='127.0.0.1');parser.add_argument('--port',type=int,default=1883)
    parser.add_argument('--rounds',type=int,default=3);parser.add_argument('--interval',type=float,default=10)
    parser.add_argument('--scenario',choices=['idle','cycle','charger-fault','overheat','wrong-energy','wrong-vehicle-type','connection-loss'],default='idle')
    args=parser.parse_args()
    connected,ack=Event(),Event();expected={};received={}
    client=mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    if os.getenv('MQTT_USER'): client.username_pw_set(os.getenv('MQTT_USER'),os.getenv('MQTT_PASSWORD'))
    if os.getenv('MQTT_TLS')=='1': client.tls_set(ca_certs=os.getenv('MQTT_CA_CERT') or None)
    def on_connect(c,u,f,reason,p):
        if reason==0: c.subscribe('parkly/devices/+/ack',qos=1)
    def on_subscribe(c,u,mid,reasons,props): connected.set()
    def on_message(c,u,msg):
        try: result=json.loads(msg.payload)
        except ValueError: return
        if result.get('device_code')==expected.get('code') and result.get('sequence')==expected.get('sequence'):
            received.update(result);ack.set()
    client.on_connect=on_connect;client.on_subscribe=on_subscribe;client.on_message=on_message
    client.connect(args.host,args.port);client.loop_start()
    try:
        if not connected.wait(5): raise RuntimeError('Không kết nối được MQTT broker')
        with exclusive(args.config):
            config=json.loads(args.config.read_text(encoding='utf-8'))
            for index in range(args.rounds):
                count=0
                if args.scenario!='connection-loss':
                    for device in config['devices']:
                        payload=device.get('pending') or make_payload(device,args.scenario,index)
                        device['pending']=payload;save_json(args.config,config)
                        expected.update(code=device['device_code'],sequence=payload['sequence'])
                        send(client,device,payload,ack,received)
                        device.update(sequence=payload['sequence'],energy_kwh=payload.get('energy_kwh',0),pending=None)
                        save_json(args.config,config);count+=1
                print(json.dumps({'round':index+1,'transport':'MQTT QoS1 + backend ACK','accepted':count}),flush=True)
                if index+1<args.rounds: time.sleep(args.interval)
    finally: client.disconnect();client.loop_stop()

if __name__=='__main__':main()
