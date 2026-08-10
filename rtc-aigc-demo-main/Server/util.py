"""兼容 Node util.js 的文件加载、断言与响应包装逻辑。"""

from __future__ import annotations
import inspect, json
from pathlib import Path


class AppError(Exception):
    pass


def assert_value(expression, msg):
    # JS 的 includes(' ') 只针对拥有 includes 方法且包含半角空格的值。
    has_space = isinstance(expression, (str, list, tuple)) and " " in expression
    if not expression or has_space:
        print(f"\033[31m校验失败: {msg}\033[0m")
        raise AppError(msg)


def readFiles(directory, suffix):
    scenes = {}
    for item in Path(directory).iterdir():
        with item.open(encoding="utf-8") as stream:
            scenes[item.name.replace(suffix, "", 1)] = json.load(stream)
    return scenes


async def invoke_logic(logic):
    result = logic()
    return await result if inspect.isawaitable(result) else result


async def wrapper(
    ctx, method="post", apiName=None, logic=None, containResponseMetadata=True
):
    if ctx.method.lower() == method and ctx.url.startswith(f"/{apiName}"):
        metadata = {"Action": apiName}
        try:
            result = await invoke_logic(logic)
            ctx.body = (
                {"ResponseMetadata": metadata, "Result": result}
                if containResponseMetadata
                else result
            )
        except Exception as exc:
            ctx.body = {
                "ResponseMetadata": {
                    **metadata,
                    "Error": {"Code": -1, "Message": str(exc)},
                }
            }
