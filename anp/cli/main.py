"""ANP CLI main entrypoint."""

import typer
from rich.console import Console
from rich.table import Table

from anp.sdk.client import ANPClient
from anp.models.identity import ServiceOrientation, IdentityProviderType

app = typer.Typer(
    name="anp",
    help="Agent Network Protocol CLI",
    no_args_is_help=True,
)
console = Console()


@app.command()
def init(
    name: str = typer.Argument(..., help="Agent name"),
    description: str = typer.Option(None, "--description", "-d", help="Agent description"),
    capabilities: str = typer.Option(None, "--capabilities", "-c", help="Comma-separated capabilities"),
):
    """Initialize a new agent identity."""
    client = ANPClient()
    
    # Check if identity already exists
    existing = client.load_identity()
    if existing:
        console.print(f"[yellow]Identity already exists: {existing.id}[/yellow]")
        raise typer.Abort()
    
    caps = capabilities.split(",") if capabilities else []
    
    identity = client.create_identity(
        name=name,
        description=description,
        capabilities=caps,
        service_orientation=ServiceOrientation.SERVICE_TO_OTHERS,
    )
    
    console.print(f"[green]✓ Created identity: {identity.id}[/green]")
    console.print(f"  Public key: {identity.public_key[:40]}...")
    console.print(f"  Saved to: {client.identity_path}")


@app.command()
def show():
    """Show current agent identity."""
    client = ANPClient()
    identity = client.load_identity()
    
    if not identity:
        console.print("[red]No identity found. Run 'anp init <name>' first.[/red]")
        raise typer.Abort()
    
    table = Table(title="Agent Identity")
    table.add_column("Field", style="cyan")
    table.add_column("Value")
    
    table.add_row("ID", identity.id)
    table.add_row("Name", identity.name)
    table.add_row("Description", identity.description or "-")
    table.add_row("Capabilities", ", ".join(identity.capabilities) or "-")
    table.add_row("Service Orientation", identity.service_orientation.value)
    table.add_row("Public Key", identity.public_key[:40] + "..." if identity.public_key else "-")
    table.add_row("Created", str(identity.created_at))
    
    console.print(table)
    
    if identity.identity_providers:
        console.print("\n[bold]Identity Providers:[/bold]")
        for provider in identity.identity_providers:
            status = "✓" if provider.verified else "○"
            console.print(f"  {status} {provider.type.value}: {provider.handle}")


@app.command()
def link(
    provider: str = typer.Argument(..., help="Provider type (moltbook, claude_connect, ens)"),
    handle: str = typer.Argument(..., help="Username/address on the provider"),
    profile_url: str = typer.Option(None, "--url", "-u", help="Profile URL"),
):
    """Link an identity provider to this agent."""
    client = ANPClient()
    identity = client.load_identity()
    
    if not identity:
        console.print("[red]No identity found. Run 'anp init <name>' first.[/red]")
        raise typer.Abort()
    
    try:
        provider_type = IdentityProviderType(provider)
    except ValueError:
        console.print(f"[red]Unknown provider: {provider}[/red]")
        console.print(f"Valid providers: {', '.join(p.value for p in IdentityProviderType)}")
        raise typer.Abort()
    
    client.add_identity_provider(provider_type, handle, profile_url)
    console.print(f"[green]✓ Linked {provider}: {handle}[/green]")


@app.command()
def version():
    """Show ANP version."""
    from anp import __version__
    console.print(f"ANP version {__version__}")


if __name__ == "__main__":
    app()
