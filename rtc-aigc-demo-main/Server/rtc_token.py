"""与 Node token.js 保持二进制兼容的 RTC Token 实现。"""
from __future__ import annotations
import base64, hashlib, hmac, random, struct, time

VERSION = "001"
APP_ID_LENGTH = 24
random_int = random.randint(0, 0xFFFFFFFF)
PrivPublishStream = 0
privPublishAudioStream = 1
privPublishVideoStream = 2
privPublishDataStream = 3
PrivSubscribeStream = 4
privileges = {"PrivPublishStream": 0, "PrivSubscribeStream": 4}

class _Writer:
    def __init__(self): self.buf = bytearray(1024); self.pos = 0
    def _put(self, data):
        end = self.pos + len(data)
        if end > len(self.buf): raise BufferError("Token buffer exceeds 1024 bytes")
        self.buf[self.pos:end] = data; self.pos = end; return self
    def u16(self, v): return self._put(struct.pack("<H", v))
    def u32(self, v): return self._put(struct.pack("<I", v))
    def bytes(self, value): return self.u16(len(value))._put(value)
    def string(self, value): return self.bytes(str(value).encode())
    def pack(self): return bytes(self.buf[:self.pos])

class _Reader:
    def __init__(self, data): self.data, self.pos = data, 0
    def _read(self, n):
        if self.pos + n > len(self.data): raise ValueError("Token payload truncated")
        out = self.data[self.pos:self.pos+n]; self.pos += n; return out
    def u16(self): return struct.unpack("<H", self._read(2))[0]
    def u32(self): return struct.unpack("<I", self._read(4))[0]
    def string(self): return self._read(self.u16())
    def map_u32(self): return {self.u16(): self.u32() for _ in range(self.u16())}

class AccessToken:
    def __init__(self, appID, appKey, roomID, userID):
        self.appID, self.appKey, self.roomID, self.userID = appID, appKey, roomID, userID
        self.issuedAt, self.nonce, self.expireAt, self.privileges = int(time.time()), random_int, 0, {}
    def addPrivilege(self, privilege, expireTimestamp):
        self.privileges[int(privilege)] = expireTimestamp
        if privilege == PrivPublishStream:
            for p in (privPublishVideoStream, privPublishAudioStream, privPublishDataStream): self.privileges[p] = expireTimestamp
    def expireTime(self, expireTimestamp): self.expireAt = expireTimestamp
    def packMsg(self):
        w = _Writer().u32(self.nonce).u32(self.issuedAt).u32(self.expireAt).string(self.roomID).string(self.userID).u16(len(self.privileges))
        # JS 对象整数键的枚举顺序为升序，显式排序以保证跨语言字节一致。
        for key in sorted(self.privileges): w.u16(int(key)).u32(self.privileges[key])
        return w.pack()
    def serialize(self):
        msg = self.packMsg(); signature = hmac.new(str(self.appKey).encode(), msg, hashlib.sha256).digest()
        content = _Writer().bytes(msg).bytes(signature).pack()
        return VERSION + str(self.appID) + base64.b64encode(content).decode()
    def verify(self, key):
        if self.expireAt > 0 and int(time.time()) > self.expireAt: return False
        self.appKey = key
        return hmac.new(str(key).encode(), self.packMsg(), hashlib.sha256).digest().decode(errors="replace") == self.signature

def Parse(raw):
    try:
        if len(raw) <= 27 or raw[:3] != VERSION: return None
        token = AccessToken("", "", "", ""); token.appID = raw[3:27]
        r = _Reader(base64.b64decode(raw[27:])); msg = r.string(); token.signature = r.string().decode(errors="replace")
        m = _Reader(msg); token.nonce, token.issuedAt, token.expireAt = m.u32(), m.u32(), m.u32(); token.roomID = m.string().decode(errors="replace"); token.userID = m.string().decode(errors="replace"); token.privileges = m.map_u32(); return token
    except Exception as exc:
        print(exc); return None
