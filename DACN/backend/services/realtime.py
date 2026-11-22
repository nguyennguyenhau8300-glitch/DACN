"""Broadcast committed changes to WebSocket clients in every backend process."""

import asyncio
from contextlib import closing
import json
import logging
import os
from select import select
from threading import Event, Thread
from uuid import uuid4

from sqlalchemy import event, text
from sqlalchemy.orm import Session


logger = logging.getLogger(__name__)
CACHE_TTL = 2
PENDING_CHANGES = 'parkly_changed_transactions'
# NOTIFY channels are database-wide. Include the schema to isolate separate lots of test data.
_CHANNEL_SQL = "'parkly_events_' || md5(current_schema())"
_NOTIFY_SQL = text(f'SELECT pg_notify({_CHANNEL_SQL}, :source)')
_instance = uuid4().hex
_revision = uuid4().hex
_worker = None
_peers = set()
_redis = None
_listener_connected = Event()
_uses_postgres = False


def _source():
    return f'{os.getpid()}:{_instance}'


def invalidate():
    global _revision
    _revision = uuid4().hex
    running = _worker
    if running is not None:
        loop, changed = running
        try:
            loop.call_soon_threadsafe(changed.set)
        except RuntimeError:
            pass  # The worker's event loop is shutting down.


def notification(kind):
    return {'type': kind, 'revision': _revision}


def invalidate_on_commit(session):
    connection = session.connection()
    transaction = session.get_nested_transaction() or session.get_transaction()
    pending = session.info.setdefault(PENDING_CHANGES, set())
    if transaction in pending:
        return
    if connection.dialect.name == 'postgresql':
        connection.execute(_NOTIFY_SQL, {'source': _source()})
    pending.add(transaction)


@event.listens_for(Session, 'after_flush')
def _flushed(session, _):
    if session.new or session.deleted or any(session.is_modified(row) for row in session.dirty):
        invalidate_on_commit(session)


@event.listens_for(Session, 'after_commit')
def _committed(session):
    pending = session.info.get(PENDING_CHANGES)
    if not pending:
        return
    nested = session.get_nested_transaction()
    if nested is not None:
        if nested in pending:
            pending.add(nested.parent)
    elif session.get_transaction() in pending:
        invalidate()


@event.listens_for(Session, 'after_transaction_end')
def _finished(session, transaction):
    pending = session.info.get(PENDING_CHANGES)
    if pending is not None:
        pending.discard(transaction)
        if not pending:
            session.info.pop(PENDING_CHANGES)


def _listen(engine, stop):
    from psycopg2 import sql

    args, options = engine.dialect.create_connect_args(engine.url)
    options.setdefault('connect_timeout', 5)
    options.setdefault('application_name', 'parkly-events')
    source = _source()
    while not stop.is_set():
        try:
            with closing(engine.dialect.connect(*args, **options)) as connection:
                connection.autocommit = True
                with connection.cursor() as cursor:
                    cursor.execute(f'SELECT {_CHANNEL_SQL}')
                    channel = sql.Identifier(cursor.fetchone()[0])
                    cursor.execute(sql.SQL('LISTEN {}').format(channel))
                _listener_connected.set()
                invalidate()  # Refresh snapshots after a startup or reconnect gap.
                while not stop.is_set():
                    if not select([connection], [], [], 0.5)[0]:
                        continue
                    connection.poll()
                    changed = any(notification.payload != source for notification in connection.notifies)
                    connection.notifies.clear()
                    if changed:
                        invalidate()
        except (OSError, ValueError, engine.dialect.loaded_dbapi.Error) as exc:
            if not stop.is_set():
                logger.warning('PostgreSQL event listener will reconnect (%s)', type(exc).__name__)
        finally:
            _listener_connected.clear()
        stop.wait(1)


def _redis_client():
    global _redis
    url = os.getenv('REDIS_URL')
    if url and _redis is None:
        import redis

        _redis = redis.Redis.from_url(url, decode_responses=True, socket_connect_timeout=0.2, socket_timeout=0.2)
    return _redis if url else None


def cached_capacity(lot_id, load):
    # WebSocket invalidation has its own transport. Redis only caches display data briefly.
    if not os.getenv('REDIS_URL') or (_uses_postgres and not _listener_connected.is_set()):
        return load()
    try:
        client = _redis_client()
        key = f'{os.getenv("REDIS_NAMESPACE", "parkly")}:capacity:{lot_id}:{_revision}'
        value = client.get(key)
        if value is not None:
            return json.loads(value)
    except Exception:
        return load()
    value = load()
    try:
        client.setex(key, CACHE_TTL, json.dumps(value))
    except Exception:
        pass
    return value


async def _send(peer, message):
    try:
        await asyncio.wait_for(peer.send_json(message), timeout=2)
    except Exception:
        leave(peer)
        try:
            await asyncio.wait_for(peer.close(code=1011), timeout=1)
        except Exception:
            pass


async def worker(engine):
    global _worker, _uses_postgres
    changed = asyncio.Event()
    _worker = asyncio.get_running_loop(), changed
    _uses_postgres = engine.dialect.name == 'postgresql'
    stop = Event()
    listener = None
    if _uses_postgres:
        listener = Thread(target=_listen, args=(engine, stop), name='parkly-events', daemon=True)
        listener.start()
    try:
        while True:
            await changed.wait()
            changed.clear()
            message = notification('invalidate')
            await asyncio.gather(*(_send(peer, message) for peer in tuple(_peers)))
    finally:
        _worker = None
        stop.set()
        if listener is not None:
            await asyncio.to_thread(listener.join, 6)
        for peer in tuple(_peers):
            try:
                await peer.close(code=1001)
            except Exception:
                pass
        _peers.clear()


def join(socket):
    _peers.add(socket)


def leave(socket):
    _peers.discard(socket)


def integration_status():
    try:
        client = _redis_client()
        redis_available = client is not None and bool(client.ping())
    except Exception:
        redis_available = False
    return {
        'redis_configured': bool(os.getenv('REDIS_URL')),
        'redis_available': redis_available,
        'redis_backend_kind': os.getenv('REDIS_BACKEND_KIND', 'REDIS'),
        'event_transport': 'postgresql' if _uses_postgres else 'in_process',
        'postgres_listener_connected': _listener_connected.is_set(),
        'websocket_clients': len(_peers),
        'cache_ttl_seconds': CACHE_TTL,
        'consistency': 'PostgreSQL is authoritative; cache is display-only',
    }
