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
    base_url: str = typer.Option(None, "--base-url", "-b", help="Custom API base URL (optional)")
):
    """
    Configure connection parameters for an LLM provider.
    The configuration will be saved to local or global config.yaml centered by Model ID.
    """
    provider = provider.lower()
    
    # Load existing config (if any) to support incremental updates.
    existing_config = config_manager.get_model_config(model_id, default_provider=provider)
    
    new_api_key = api_key if api_key is not None else existing_config.api_key
    new_base_url = base_url if base_url is not None else existing_config.base_url
    
    # Enforce API key on first-time configuration.
    if not new_api_key:
        console.print(f"[bold red]Error:[/bold red] API Key is required for new model '{model_id}'. Please use -k to provide it.")
        raise typer.Exit(code=1)

    # Build updated config object.
    updated_config = LLMConfig(
        model_id=model_id,
        api_key=new_api_key,
        base_url=new_base_url,
        provider=provider
    )
    
    # Save to config.yaml (keyed by model_id).
    config_manager.save_config(updated_config)
    
    # Print success info with masked API key.
    masked_key = f"{updated_config.api_key[:4]}...{updated_config.api_key[-4:]}" if len(updated_config.api_key) > 8 else "..."
    
    details = (
        f"[bold cyan]Model:[/bold cyan]    {updated_config.model_id}\n"
        f"[bold cyan]Provider:[/bold cyan] {updated_config.provider}\n"
        f"[bold cyan]Base URL:[/bold cyan] {updated_config.base_url or 'Default'}\n"
        f"[bold cyan]API Key:[/bold cyan]  {masked_key}"
    )
    
    console.print(Panel(details, title="Configuration saved", expand=False, border_style="green"))
