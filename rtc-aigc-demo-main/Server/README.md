# Python AIGC Server

## 启动

```bash
cd Server
conda activate ai_agent

pip install -r requirements.txt
python app.py
```

默认监听 `http://localhost:3001`，也可通过 `HOST`、`PORT`、`RTC_API_URL` 环境变量配置。

服务启动时会读取 `scenes` 下的 JSON 文件。`RTCConfig.RoomId`、`UserId`、`Token` 任一缺失时，会按原 Node.js 逻辑生成 UUID 和 24 小时 RTC Token；返回场景时会移除 `RTCConfig.AppKey`。

接口保持不变：

- `POST /getScenes`
- `POST /proxy?Action=StartVoiceChat&Version=2024-12-01`，JSON body 需包含 `SceneID`

AccountConfig 的 AK/SK、RTC AppId/AppKey 等敏感参数请写入场景配置或部署环境，不要提交真实密钥。原 Node 文件仍保留，可用于迁移期间的行为对照。
