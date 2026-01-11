import asyncio
import importlib
import socket
import ssl
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import AsyncIterator, Optional

import pytest
import uvicorn

_SERVER_CERT = """-----BEGIN CERTIFICATE-----
MIIDCTCCAfGgAwIBAgIUT89U079clajgHJUuD3WXVbaOipMwDQYJKoZIhvcNAQEL
BQAwFDESMBAGA1UEAwwJbG9jYWxob3N0MB4XDTI1MTExNDE4MzgzOVoXDTI1MTEx
NTE4MzgzOVowFDESMBAGA1UEAwwJbG9jYWxob3N0MIIBIjANBgkqhkiG9w0BAQEF
AAOCAQ8AMIIBCgKCAQEAo91bNDo5ll2VLcsK1ney4OSjpqMpnQUyvYCqS5kcPU6O
yRtXm3xhtoo7w0IcFPBxqQKWl99CMETVZj86VIrdhW9eRVDAIao/bw/LWikgO0Z3
onJYDKFn6ex97dRBG5OLSFle2KXFHnMAlWe9tnu7ZaR8SAvgs+goFBi99VL9ZDw8
reOfCyEyGw95cLG4A4PC20P4+ZO6xkfehOGuSt8pevpdT8G3U83KDlYQbri28+2r
b7/KmYVn0w6rGwDb7eBGiT10yJEd/Y0NQIbEZwlspphERnkKkKsGoU7DOCVCOkWK
X4wftgh57+PF0TinmyVZJoYQrdqaJqqtFuUONhgltQIDAQABo1MwUTAdBgNVHQ4E
FgQUaeycCaoUTaVG8otxR6amcDuiLNgwHwYDVR0jBBgwFoAUaeycCaoUTaVG8otx
R6amcDuiLNgwDwYDVR0TAQH/BAUwAwEB/zANBgkqhkiG9w0BAQsFAAOCAQEAcKYL
O2hmJbH40P4vq1e3FTwPZX8tGmFtx++SG7jvTy7VLnNhHRNq95wgYb92p3PM5oLP
F+b+Bt9p33wgR2V0grJsKEBn/AiupRMh0iKorWe+yAxoqDtpGR2OXNijTLnIOxxW
3YC+rYVgdACVPHpg3wGlwCQry/Zh979XpTT1U8jrILY72Qp1M57tXGzHz/jIGRZ8
LVi7eR06cof+6p5NmPJcsBWlt+rT3des/gDvTROK6X467XXrl6plYUaLh2GQ+snQ
e+ft/yi5dwn1smKfO9vcDcNXGLSmrPQkL7E8k4ria8le94MOZPtbXRss449qS6hA
mHtxYVWO3AMlyWtV2A==
-----END CERTIFICATE-----
"""

_SERVER_KEY = """-----BEGIN PRIVATE KEY-----
MIIEvgIBADANBgkqhkiG9w0BAQEFAASCBKgwggSkAgEAAoIBAQCj3Vs0OjmWXZUt
ywrWd7Lg5KOmoymdBTK9gKpLmRw9To7JG1ebfGG2ijvDQhwU8HGpApaX30IwRNVm
PzpUit2Fb15FUMAhqj9vD8taKSA7RneiclgMoWfp7H3t1EEbk4tIWV7YpcUecwCV
Z722e7tlpHxIC+Cz6CgUGL31Uv1kPDyt458LITIbD3lwsbgDg8LbQ/j5k7rGR96E
4a5K3yl6+l1PwbdTzcoOVhBuuLbz7atvv8qZhWfTDqsbANvt4EaJPXTIkR39jQ1A
hsRnCWymmERGeQqQqwahTsM4JUI6RYpfjB+2CHnv48XROKebJVkmhhCt2pomqq0W
5Q42GCW1AgMBAAECggEABUiObQNBQZWlXnYI6gGEg+dOASy1cLG5oS4RmkE8IvGS
PYOTQiO9ySNbtMVAKgsBoyvT8V7PtRuMZOZTf2UrKib9MLofORv9PRu9gwacmoSr
DVK8qjWXEo4J673tASezSo3PzCeg0NqaPCGoQTFr8/rxzec3eMgwE0vOmNHIR+/I
XgdRq8svk7zFiteLjOegZqomE/w9rt15jTTiKGzSGFtG4ucrbf5J7RW7HESCTaSP
yNdv1a3ltJbSEiqQ7cY/m6/5qhUfQ15JKKlc+EG82vtcklzT9oPeIr4KLHCkJpae
SCGevqTWhw6pTGaS0wvwfEgw196/7TwBD5FF9tRokQKBgQDblIi9bAqn2uZ1RxbH
gkNsxpDMr/qFAE+YeYUH6KVu13KVDOD+Ygvi8KxZgj4pAevMDsY8P+DUiPNPjjbi
v28MSj+i9hdTG/ySlxrgNG0sgjm+1xLZbJ3oClbBSx2epHuLuLF8OH6JSZDc8xvf
J1I7Bzp9XV7U7aWULfaZQIcphQKBgQC/Cx4Uio90CfvvTQVaPAh1i2kmt/KZLJMn
XIKOVqNZZPtmjVuraAOD6MrQuAGeNiZ9JeMsJN/H+zRtJgmD3fJq/IVAwh23jxC+
T2yu4yQgeaHsss0PL/bzcm5PgTVnCvqpi0D8KQ6WraFsFfKizPWHzHzwYWcmJ5zs
TD57kdMqcQKBgQCdOXfHmirvEbBeXS6UYFOC+ZMI3SDWRui3VpvIk+6QtTfYPcaE
nxO/xXDDDp0Po86A6DtNPLfxtrXxSvVF2qja9fcm6mq9GZb6J7QYwbFCY2SRn1Jh
2IIgefawpOZqh3/nBbIgLht8le5iJrjYSkF4/q4Ewex7LkaXGWovRaMCOQKBgCod
Gklu7ganeMkc0nQ8zaST0d8+J5WKlPnVU9Zq1OGM+Dp4KOAVMskuVR9DoN+ukjd+
VaDSlB4yizEQdIKEN79L4VgQMprXR9qcCZpX6gvapE5YcAnMCgVKkXSnSA1qBy2+
y9mKd3PR3MbF49HtmqaP9m7LGgD4NIiGmjOFRuaRAoGBAKQR+0ooMRG6AqckEULQ
+EeR5+mq12pC8qulR/wr5EFbpvsrJMM4bcJrDIzWIJIcbNGPhzNlKRK2aOnZJ+ML
1Z4ewGFQSTzxCJn2hH++xw89mq3dqlx8dRhKHiHEAoCNqiXseifcsBCSbmJYERlY
d4jXTwcy8gWBpWkK9x09AATC
-----END PRIVATE KEY-----
"""


def _get_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@dataclass
class TLSMaterials:
    ssl_context: ssl.SSLContext
    ca_path: str


@pytest.fixture(scope="session")
def tls_materials(tmp_path_factory) -> TLSMaterials:
    tls_dir = tmp_path_factory.mktemp("tls")
    cert_path = tls_dir / "cert.pem"
    key_path = tls_dir / "key.pem"
    ca_path = tls_dir / "ca.pem"

    cert_path.write_text(_SERVER_CERT)
    key_path.write_text(_SERVER_KEY)
    ca_path.write_text(_SERVER_CERT)

    ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ssl_context.load_cert_chain(cert_path, key_path)

    return TLSMaterials(ssl_context=ssl_context, ca_path=str(ca_path))


@asynccontextmanager
async def _run_uvicorn(app, host: str, port: int, ssl_context: Optional[ssl.SSLContext] = None) -> AsyncIterator[str]:
    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        loop="asyncio",
        lifespan="on",
        ssl=ssl_context,
        log_level="warning",
    )
    server = uvicorn.Server(config)
    task = asyncio.create_task(server.serve())
    try:
        while not server.started:
            await asyncio.sleep(0.05)
        scheme = "https" if ssl_context else "http"
        yield f"{scheme}://{host}:{port}"
    finally:
        server.should_exit = True
        await task


@pytest.fixture
def agent_state():
    return {}


@pytest.fixture
async def agent_server(agent_state):
    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse
    from matrix.models import Msg, Reply
    from matrix.utils import state_hash
    import time

    app = FastAPI(title="Test Agent")

    @app.post("/draft", response_model=Reply)
    async def draft(msg: Msg, request: Request):
        agent_state["authorization"] = request.headers.get("authorization")
        output = {"echo": msg.input}
        return Reply(
            id=msg.id,
            ts=time.time(),
            agent="osteon",
            ok=True,
            output=output,
            state_hash=state_hash(output),
        )

    @app.post("/error")
    async def error(msg: Msg):
        return JSONResponse(status_code=418, content={"detail": "brew failure", "id": msg.id})

    port = _get_free_port()
    async with _run_uvicorn(app, "127.0.0.1", port) as url:
        yield url


@pytest.fixture
async def mesh_server(agent_server, tls_materials, monkeypatch):
    monkeypatch.setenv("AGENT_OSTEON_URL", agent_server)
    mesh_module = importlib.reload(importlib.import_module("mesh.main"))

    port = _get_free_port()
    async with _run_uvicorn(mesh_module.app, "127.0.0.1", port, ssl_context=tls_materials.ssl_context) as url:
        yield url
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
