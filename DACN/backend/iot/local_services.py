"""Local MQTT broker + Redis protocol simulator for Windows without Docker.
For real Redis/Mosquitto use ../cong_cu_phat_trien/infrastructure/compose.yaml instead.
All listeners bind localhost; no anonymous broker is exposed on the LAN.
"""
import asyncio
import argparse
import logging
from threading import Thread
from amqtt.broker import Broker
from fakeredis import TcpFakeServer

async def main(args):
    redis=broker=None
    if not args.mqtt_only:
        redis=TcpFakeServer(('127.0.0.1',6379))
        Thread(target=redis.serve_forever,daemon=True).start()
    if not args.redis_only:
        broker=Broker({'listeners':{'default':{'type':'tcp','bind':'127.0.0.1:1883'}},
                       'plugins':{'amqtt.plugins.authentication.AnonymousAuthPlugin':{'allow_anonymous':True}}})
        await broker.start()
    print('MQTT broker: 127.0.0.1:1883. Redis protocol SIMULATOR: 127.0.0.1:6379. Not a Redis performance benchmark.',flush=True)
    try: await asyncio.Event().wait()
    finally:
        if broker: await broker.shutdown()
        if redis: redis.shutdown();redis.server_close()

if __name__=='__main__':
    logging.basicConfig(level=logging.ERROR)
    parser=argparse.ArgumentParser();group=parser.add_mutually_exclusive_group();group.add_argument('--mqtt-only',action='store_true');group.add_argument('--redis-only',action='store_true')
    try: asyncio.run(main(parser.parse_args()))
    except KeyboardInterrupt: pass
