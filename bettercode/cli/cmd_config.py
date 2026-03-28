# bettercode/cli/cmd_config.py
import typer
from rich.console import Console
from rich.panel import Panel

from bettercode.llm.config_manager import config_manager
from bettercode.llm.config import LLMConfig

console = Console()

def modelconfig(
    model_id: str = typer.Option(..., "--model", "-m", help="Model ID, e.g., gpt-4o"),
    provider: str = typer.Option(..., "--provider", "-p", help="Provider name, e.g., openai, deepseek, anthropic"),
    api_key: str = typer.Option(None, "--api-key", "-k", help="LLM API Key"),
    base_url: str = typer.Option(None, "--base-url", "-b", help="Custom API base URL (optional)"),
    api_key_env: str = typer.Option(None, "--api-key-env", help="Environment variable name for storing API key")
):
    """
    Configure connection parameters for an LLM provider.
    The configuration will be saved to local or global config.yaml centered by Model ID.
    """
    provider = provider.lower()

    existing_entry = config_manager.get_model_entry(model_id)
    try:
        existing_config = config_manager.get_model_config(model_id, default_provider=provider)
    except RuntimeError:
        existing_config = LLMConfig(
            model_id=model_id,
            api_key="",
            base_url=None,
            provider=provider,
        )
    stored_api_key_ref = str(existing_entry.get("api_key", "")).strip()
    new_base_url = base_url if base_url is not None else existing_config.base_url

    env_file_path = None
    masked_key_preview = ""
    effective_api_key_ref = stored_api_key_ref

    if api_key is not None:
        env_name = (api_key_env or config_manager.default_api_key_env_name(model_id)).strip()
        if not env_name:
            console.print("[bold red]Error:[/bold red] --api-key-env cannot be empty.")
            raise typer.Exit(code=1)
        env_file_path = config_manager.upsert_api_key_env(env_name, api_key, scope="project")
        effective_api_key_ref = f"ENV:{env_name}"
        masked_key_preview = f"{api_key[:4]}...{api_key[-4:]}" if len(api_key) > 8 else "..."
    elif effective_api_key_ref:
        resolved_key = existing_config.api_key or ""
        masked_key_preview = f"{resolved_key[:4]}...{resolved_key[-4:]}" if len(resolved_key) > 8 else "..."
    else:
        console.print(
            f"[bold red]Error:[/bold red] API Key is required for new model '{model_id}'. "
            "Please use -k to provide it."
        )
        raise typer.Exit(code=1)

    # Build updated config object.
    updated_config = LLMConfig(
        model_id=model_id,
        api_key=effective_api_key_ref,
        base_url=new_base_url,
        provider=provider
    )
    
    # Save to config.yaml (keyed by model_id).
    config_manager.save_config(updated_config)
    
    details = (
        f"[bold cyan]Model:[/bold cyan]    {updated_config.model_id}\n"
        f"[bold cyan]Provider:[/bold cyan] {updated_config.provider}\n"
        f"[bold cyan]Base URL:[/bold cyan] {updated_config.base_url or 'Default'}\n"
        f"[bold cyan]API Key Ref:[/bold cyan] {updated_config.api_key}\n"
        f"[bold cyan]API Key Value:[/bold cyan] {masked_key_preview or 'unchanged'}"
    )
    if env_file_path is not None:
        details += f"\n[bold cyan].env Path:[/bold cyan] {env_file_path}"

    console.print(Panel(details, title="Configuration saved", expand=False, border_style="green"))
