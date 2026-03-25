# bettercode/llm/config_manager.py
import os
import yaml
from pathlib import Path
from typing import Dict, Any
from .config import LLMConfig

class LLMConfigManager:
    def __init__(self):
        # 1. 项目级配置路径：当前工作目录下的 bettercode/config/config.yaml
        self.local_config_file = Path.cwd() / "bettercode" / "config" / "config.yaml"
        
        # 2. 全局配置路径：~/.config/bettercode/config.yaml
        self.global_config_file = Path.home() / ".config" / "bettercode" / "config.yaml"
        
        # 决定当前使用的配置文件：
        if (Path.cwd() / "bettercode").exists():
            self.config_file = self.local_config_file
        else:
            self.config_file = self.global_config_file

        self._local_configs: Dict[str, Dict[str, Any]] = self._load()

    def _load(self) -> Dict[str, Dict[str, Any]]:
        if self.config_file.exists():
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    # 使用 safe_load 防止 YAML 注入
                    data = yaml.safe_load(f)
                    return data if isinstance(data, dict) else {}
            except Exception as e:
                print(f"⚠️ 解析 YAML 配置文件失败 {self.config_file}: {e}")
                return {}
        return {}

    def save_config(self, config: LLMConfig) -> None:
        """将配置保存到 YAML 文件，以 model_id 为顶级键"""
        # 确保目录存在
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        
        # 核心改动：使用 model_id 作为 YAML 的最外层键
        model_key = config.model_id
        self._local_configs[model_key] = {
            "api_key": config.api_key,
            "base_url": config.base_url,
            "provider": config.provider,
            "model_id": config.model_id
        }
        
        # 写入 YAML
        with open(self.config_file, "w", encoding="utf-8") as f:
            yaml.safe_dump(
                self._local_configs, 
                f, 
                allow_unicode=True, 
                sort_keys=False,
                default_flow_style=False
            )

    def get_model_config(self, model_id: str, default_provider: str = "") -> LLMConfig:
        """
        根据 model_id 获取配置。
        优先从 YAML 中精确匹配 model_id，如果找不到则降级查找环境变量。
        """
        # 1. 优先读取持久化配置 (YAML)，直接通过 model_id 查找
        if model_id in self._local_configs:
            data = self._local_configs[model_id]
            return LLMConfig(
                model_id=data.get("model_id", model_id),
                api_key=data.get("api_key", ""),
                base_url=data.get("base_url"),
                provider=data.get("provider", default_provider or "openai")
            )

        # 2. 降级读取环境变量 (.env 或系统环境)
        # 注意：使用 default_provider 决定前缀，如果不传默认用 OPENAI
        prefix = default_provider.upper() if default_provider else "OPENAI"
        
        return LLMConfig(
            model_id=os.getenv(f"{prefix}_MODEL_ID", model_id),
            api_key=os.getenv(f"{prefix}_API_KEY", ""),
            base_url=os.getenv(f"{prefix}_BASE_URL"),
            provider=default_provider or "openai"
        )

# 全局单例管理器
config_manager = LLMConfigManager()