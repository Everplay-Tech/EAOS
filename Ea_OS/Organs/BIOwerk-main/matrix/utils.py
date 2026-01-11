import json, blake3

def canonical(obj) -> bytes:
    return json.dumps(obj, separators=(",", ":"), sort_keys=True, ensure_ascii=False).encode("utf-8")

def state_hash(payload) -> str:
    return blake3.blake3(canonical(payload)).hexdigest()
