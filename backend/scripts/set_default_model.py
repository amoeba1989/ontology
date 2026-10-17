# -*- coding: utf-8 -*-
"""把系统默认 AI 模型规整为 DeepSeek Flash（幂等）。

密钥不入库：留空即可，运行期由 .env 的 LLM_API_KEY 提供
（llm_resolver 在 DB 模型无 key 时回退到 settings.LLM_*）。

用法：cd backend && python -m scripts.set_default_model
"""
from __future__ import annotations

import json
import sys

from app.database import SessionLocal
from app.models.system_config import SystemConfig

DEFAULT_MODELS = [
    {"id": "deepseek-flash", "name": "DeepSeek Flash", "provider": "DeepSeek",
     "model_id": "deepseek-flash", "api_key": "", "base_url": "https://api.deepseek.com",
     "temperature": 0.7, "max_tokens": 4096,
     "scenes": ["ontology", "agent", "data", "general"], "is_default": True},
    {"id": "claude-sonnet", "name": "Claude Sonnet 4", "provider": "Anthropic",
     "model_id": "claude-sonnet-4-20250514", "api_key": "", "base_url": "https://api.anthropic.com",
     "temperature": 0.7, "max_tokens": 4096, "scenes": ["ontology", "general"], "is_default": False},
    {"id": "claude-opus", "name": "Claude Opus 4", "provider": "Anthropic",
     "model_id": "claude-opus-4-20250514", "api_key": "", "base_url": "https://api.anthropic.com",
     "temperature": 0.5, "max_tokens": 8192, "scenes": ["ontology"], "is_default": False},
    {"id": "gpt-4o", "name": "GPT-4o", "provider": "OpenAI",
     "model_id": "gpt-4o", "api_key": "", "base_url": "https://api.openai.com",
     "temperature": 0.7, "max_tokens": 4096, "scenes": ["agent", "data"], "is_default": False},
]


def main() -> int:
    db = SessionLocal()
    try:
        row = db.query(SystemConfig).filter(SystemConfig.key == "ai.models").first()
        if not row:
            row = SystemConfig(group="ai", key="ai.models", description="AI 模型列表")
            db.add(row)
        row.value = json.dumps(DEFAULT_MODELS, ensure_ascii=False)

        # 同步旧单值配置项（group=ai，key 为 model / base_url）
        for k, v in {"model": "deepseek-flash", "base_url": "https://api.deepseek.com"}.items():
            r = db.query(SystemConfig).filter(
                SystemConfig.group == "ai", SystemConfig.key == k).first()
            if r:
                r.value = v
        db.commit()
        print("默认 AI 模型已设为 DeepSeek Flash；密钥请在 .env 的 LLM_API_KEY 配置。")
        print("当前 ai.models 默认项：", json.dumps(DEFAULT_MODELS[0], ensure_ascii=False))
        return 0
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        print(f"执行失败已回滚：{exc}")
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
