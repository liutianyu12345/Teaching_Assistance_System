"""Short-lived classroom view cache. SQL records remain authoritative on reconnect."""

import json
import os
from redis import Redis
from redis.exceptions import RedisError

url = os.getenv("REDIS_URL")
cache = (
    Redis.from_url(url, decode_responses=True, socket_connect_timeout=0.3, socket_timeout=0.3)
    if url
    else None
)


def invalidate(pub):
    if cache is None:
        return
    try:
        key = "live:rev:" + pub
        with cache.pipeline() as commands:
            commands.incr(key).expire(key, 3600).execute()
    except RedisError:
        pass


def view(pub, user_id, load):
    if cache is None:
        return load()
    try:
        rev = cache.get("live:rev:" + pub) or "0"
        key = "live:view:" + pub + ":" + user_id + ":" + rev
        if raw := cache.get(key):
            return json.loads(raw)
    except RedisError:
        return load()
    data = load()
    try:
        cache.setex(key, 3, json.dumps(data, ensure_ascii=False))
    except RedisError:
        pass
    return data
