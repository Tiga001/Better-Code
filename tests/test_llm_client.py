import argparse
import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from bettercode.llm import create_llm_client
from bettercode.llm.schemas import Message, MessageRole


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Manual connectivity test for BetterCode LLM client."
    )
    parser.add_argument(
        "--model",
        default="deepseek-ai/DeepSeek-R1-0528",
        help="Model ID key in bettercode/config/config.yaml",
    )
    parser.add_argument(
        "--prompt",
        default="你好，请回复一句：连接测试成功。然后介绍自己。",
        help="User prompt sent to the model.",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.2,
        help="Sampling temperature.",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=10000,
        help="Maximum completion tokens for the response.",
    )
    parser.add_argument(
        "--show-reasoning",
        action="store_true",
        default=True,
        help="Print reasoning content when the model provides it.",
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    client = create_llm_client(args.model)
    messages = [Message(role=MessageRole.USER, content=args.prompt)]

    response = await client.achat(
        messages=messages,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
    )

    print("\n=== LLM Response ===")
    print(response.content)
    print("\n=== Meta ===")
    print(f"model: {response.model}")
    print(f"latency_ms: {response.latency_ms}")
    print(f"usage: {response.usage.model_dump()}")
    if not response.content:
        print("warning: final content is empty; try increasing --max-tokens")
    if args.show_reasoning and response.reasoning_content:
        print("\n=== Reasoning ===")
        print(response.reasoning_content)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as exc:
        print("\nLLM connectivity test failed.")
        print(f"error: {exc}")
        print("hint: check model_id/provider/api_key/base_url in bettercode/config/config.yaml")
        raise
