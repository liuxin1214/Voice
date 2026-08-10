"""Python 版 AIGC 后台服务入口，接口行为对应 Server/app.js。"""

from __future__ import annotations
import copy, json, os, uuid
from pathlib import Path
import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

try:
    from .util import AppError, assert_value, readFiles
    from .rtc_token import AccessToken, PrivSubscribeStream, PrivPublishStream
    from .openapi_signer import sign_request
except ImportError:  # 兼容在 Server 目录直接执行 python app.py
    from util import AppError, assert_value, readFiles
    from rtc_token import AccessToken, PrivSubscribeStream, PrivPublishStream
    from openapi_signer import sign_request

BASE_DIR = Path(__file__).resolve().parent
SCENES = readFiles(BASE_DIR / "scenes", ".json")
UPSTREAM = os.getenv("RTC_API_URL", "https://rtc.volcengineapi.com")
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "3001"))
app = FastAPI()
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)


def js_stringify_error(exc):
    return str(exc)


@app.post("/proxy")
async def proxy(request: Request):
    metadata = {"Action": "proxy"}
    try:
        query = request.query_params
        action = query.get("Action")
        version = query.get("Version", "2024-12-01")
        assert_value(action, "Action 不能为空")
        assert_value(version, "Version 不能为空")
        data = await request.json()
        scene_id = data.get("SceneID") if isinstance(data, dict) else None
        assert_value(scene_id, "SceneID 不能为空, SceneID 用于指定场景的 JSON")
        json_data = SCENES.get(scene_id)
        assert_value(
            json_data, f"{scene_id} 不存在, 请先在 Server/scenes 下定义该场景的 JSON."
        )
        voice = json_data.get("VoiceChat", {})
        account = json_data.get("AccountConfig", {})
        assert_value(account.get("accessKeyId"), "AccountConfig.accessKeyId 不能为空")
        assert_value(account.get("secretKey"), "AccountConfig.secretKey 不能为空")
        if action == "StartVoiceChat":
            body = voice
        elif action == "StopVoiceChat":
            app_id, room_id, task_id = (
                voice.get("AppId"),
                voice.get("RoomId"),
                voice.get("TaskId"),
            )
            assert_value(app_id, "VoiceChat.AppId 不能为空")
            assert_value(room_id, "VoiceChat.RoomId 不能为空")
            assert_value(task_id, "VoiceChat.TaskId 不能为空")
            body = {"AppId": app_id, "RoomId": room_id, "TaskId": task_id}
        else:
            body = {}
        payload = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode()
        headers = sign_request(
            "POST",
            "rtc.volcengineapi.com",
            "/",
            {"Action": action, "Version": version},
            payload,
            account["accessKeyId"],
            account["secretKey"],
        )
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{UPSTREAM}?Action={action}&Version={version}",
                content=payload,
                headers=headers,
            )
        return JSONResponse(content=response.json(), status_code=response.status_code)
    except Exception as exc:
        return JSONResponse(
            {
                "ResponseMetadata": {
                    **metadata,
                    "Error": {"Code": -1, "Message": js_stringify_error(exc)},
                }
            }
        )


@app.post("/getScenes")
async def get_scenes():
    try:
        result = []
        for scene, data in SCENES.items():
            scene_config = data.get("SceneConfig", {})
            rtc = data.setdefault("RTCConfig", {})
            voice = data.get("VoiceChat", {})
            app_id, room_id, user_id, app_key, token = (
                rtc.get(k) for k in ("AppId", "RoomId", "UserId", "AppKey", "Token")
            )
            assert_value(app_id, f"{scene} 场景的 RTCConfig.AppId 不能为空")
            if app_id and (not token or not user_id or not room_id):
                room_id = room_id or str(uuid.uuid4())
                user_id = user_id or str(uuid.uuid4())
                rtc["RoomId"] = voice["RoomId"] = room_id
                rtc["UserId"] = user_id
                agent = voice.setdefault("AgentConfig", {})
                targets = agent.setdefault("TargetUserId", [None])
                targets[0] = user_id
                assert_value(
                    app_key, f"自动生成 Token 时, {scene} 场景的 AppKey 不可为空"
                )
                key = AccessToken(app_id, app_key, room_id, user_id)
                key.addPrivilege(PrivSubscribeStream, 0)
                key.addPrivilege(PrivPublishStream, 0)
                key.expireTime(
                    __import__("time").time_ns() // 1_000_000_000 + 24 * 3600
                )
                rtc["Token"] = key.serialize()
            scene_config.update(
                {
                    "id": scene,
                    "botName": voice.get("AgentConfig", {}).get("UserId"),
                    "isInterruptMode": voice.get("Config", {}).get("InterruptMode")
                    == 0,
                    "isVision": voice.get("Config", {})
                    .get("LLMConfig", {})
                    .get("VisionConfig", {})
                    .get("Enable"),
                    "isScreenMode": voice.get("Config", {})
                    .get("LLMConfig", {})
                    .get("VisionConfig", {})
                    .get("SnapshotConfig", {})
                    .get("StreamType")
                    == 1,
                    "isAvatarScene": voice.get("Config", {})
                    .get("AvatarConfig", {})
                    .get("Enabled"),
                    "avatarBgUrl": voice.get("Config", {})
                    .get("AvatarConfig", {})
                    .get("BackgroundUrl"),
                }
            )
            rtc.pop("AppKey", None)
            result.append({"scene": scene_config or {}, "rtc": rtc})
        return {"scenes": result}
    except Exception as exc:
        return {
            "ResponseMetadata": {
                "Action": "getScenes",
                "Error": {"Code": -1, "Message": str(exc)},
            }
        }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=HOST, port=PORT)
