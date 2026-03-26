# bettercode/cli/main.py
import typer

# Import the command function from separate module
from .cmd_config import modelconfig

# Create the main CLI application
app = typer.Typer(
    name="bettercode", 
    help="BetterCode CLI - Pure Python desktop project structure explorer",
    no_args_is_help=True
)

app.command(name="config")(modelconfig)

@app.callback()
def main_callback():
    pass

def run():
    """Entry point defined in pyproject.toml"""
    app()

if __name__ == "__main__":
    run()