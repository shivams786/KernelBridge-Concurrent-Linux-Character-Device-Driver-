"""Sequential, nonblocking byte-stream contract. No kernel imports required."""

import errno
import random

MIN_CAPACITY = 256
MAX_CAPACITY = 65536
MAX_OPERATIONS = 10000
MAX_TRANSFER = 4096


def success(count=0, data=None):
    result = {"ret": count, "errno": 0}
    if data is not None:
        result["data"] = data.hex()
    return result


def failure(code):
    return {"ret": -1, "errno": code}


def validate(scenario):
    if not isinstance(scenario, dict) or scenario.get("version") != 1:
        raise ValueError("scenario version must be 1")
    capacity = scenario.get("capacity")
    if type(capacity) is not int or not MIN_CAPACITY <= capacity <= MAX_CAPACITY:
        raise ValueError("initial capacity must be 256..65536")
    operations = scenario.get("operations")
    if not isinstance(operations, list) or not 1 <= len(operations) <= MAX_OPERATIONS:
        raise ValueError("scenario must contain 1..10000 operations")
    for op in operations:
        if not isinstance(op, dict):
            raise ValueError("operation must be an object")
        kind = op.get("op")
        fields = {"read": {"op", "count"}, "write": {"op", "data"},
                  "resize": {"op", "capacity"}, "clear": {"op"},
                  "capacity": {"op"}}
        if not isinstance(kind, str) or kind not in fields or set(op) != fields[kind]:
            raise ValueError("unknown operation or unexpected fields")
        if kind == "read" and (type(op["count"]) is not int or
                               not 0 <= op["count"] <= MAX_TRANSFER):
            raise ValueError("read count must be 0..4096")
        if kind == "resize" and (type(op["capacity"]) is not int or
                                 not 0 <= op["capacity"] < 2**64):
            raise ValueError("resize capacity must fit unsigned 64 bits")
        if kind == "write":
            data = op["data"]
            if not isinstance(data, str) or len(data) > MAX_TRANSFER * 2:
                raise ValueError("write data must be hex encoding at most 4096 bytes")
            try:
                decoded = bytes.fromhex(data)
            except ValueError as exc:
                raise ValueError("invalid write hex data") from exc
            if decoded.hex() != data:
                raise ValueError("write data must use canonical lowercase hex")
    return scenario


class ReferenceModel:
    def __init__(self, capacity):
        self.capacity = capacity
        self.data = bytearray()

    def apply(self, op):
        kind = op["op"]
        if kind == "write":
            payload = bytes.fromhex(op["data"])
            count = min(len(payload), self.capacity - len(self.data))
            if payload and not count:
                return failure(errno.EAGAIN)
            self.data.extend(payload[:count])
            return success(count)
        if kind == "read":
            count = min(op["count"], len(self.data))
            if op["count"] and not count:
                return failure(errno.EAGAIN)
            payload = bytes(self.data[:count])
            del self.data[:count]
            return success(count, payload)
        if kind == "resize":
            capacity = op["capacity"]
            if not MIN_CAPACITY <= capacity <= MAX_CAPACITY:
                return failure(errno.EINVAL)
            if capacity < len(self.data):
                return failure(errno.EMSGSIZE)
            self.capacity = capacity
            return success()
        if kind == "clear":
            self.data.clear()
            return success()
        if kind == "capacity":
            return success(self.capacity)
        raise ValueError("unknown operation")


def generate(seed, steps):
    if not 1 <= steps <= MAX_OPERATIONS:
        raise ValueError("steps must be 1..10000")
    rng = random.Random(seed)
    operations = []
    for _ in range(steps):
        kind = rng.choice(["write", "write", "read", "read", "resize", "clear", "capacity"])
        op = {"op": kind}
        if kind == "write":
            size = rng.choice([0, 1, 63, 255, 256, 257, 512, 4096])
            op["data"] = bytes(rng.randrange(256) for _ in range(size)).hex()
        elif kind == "read":
            op["count"] = rng.choice([0, 1, 63, 255, 256, 257, 512, 4096])
        elif kind == "resize":
            op["capacity"] = rng.choice([0, 255, 256, 512, 4096, 65536, 65537])
        operations.append(op)
    return {"version": 1, "seed": seed, "capacity": 256, "operations": operations}
