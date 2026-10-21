"""
PinPilot CLI — Command Line Interface

Usage:
    python main.py validate          Validate API connections & config
    python main.py publish           Publish new Pins from Dropbox products
    python main.py publish --dry-run Preview what would be published
    python main.py status            Show publishing history & stats
    python main.py boards            List Pinterest boards
    python main.py schedule          Run on a recurring schedule
    python main.py export            Export tracking data to CSV
"""

import logging
import sys
import time
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.logging import RichHandler

from pinpilot.config import Config
from pinpilot.publisher import Publisher
from pinpilot.tracker import PublishTracker

console = Console()


def setup_logging(level: str = "INFO", log_file: str | None = None) -> None:
    """Configure logging with Rich handler for pretty console output."""
    handlers: list[logging.Handler] = [
        RichHandler(
            console=console,
            show_time=True,
            show_path=False,
            markup=True,
        )
    ]

    if log_file:
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s | %(name)s | %(levelname)s | %(message)s")
        )
        handlers.append(file_handler)

    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        handlers=handlers,
        format="%(message)s",
    )


def load_config() -> Config:
    """Load and display configuration status."""
    config = Config.from_env()
    return config


@click.group()
@click.option("--env-file", type=click.Path(exists=True), default=None,
              help="Path to .env file")
@click.pass_context
def cli(ctx: click.Context, env_file: str | None) -> None:
    """🚀 PinPilot — Automated Pinterest → Gumroad Pipeline"""
    ctx.ensure_object(dict)

    if env_file:
        config = Config.from_env(env_file)
    else:
        config = Config.from_env()

    setup_logging(config.logging.level, config.logging.log_file)
    ctx.obj["config"] = config


@cli.command()
@click.pass_context
def validate(ctx: click.Context) -> None:
    """Validate API connections and configuration."""
    config = ctx.obj["config"]

    console.print(Panel(
        "[bold cyan]PinPilot Configuration Check[/bold cyan]",
        border_style="cyan",
    ))

    tracker = PublishTracker()
    publisher = Publisher(config, tracker)

    all_ok, messages = publisher.validate_setup()

    for msg in messages:
        if msg.startswith("✅"):
            console.print(f"  {msg}", style="green")
        elif msg.startswith("❌"):
            console.print(f"  {msg}", style="red bold")
        elif msg.startswith("⚠️"):
            console.print(f"  {msg}", style="yellow")
        elif msg.startswith("ℹ️"):
            console.print(f"  {msg}", style="blue")
        else:
            console.print(f"  {msg}")

    console.print()
    if all_ok:
        console.print("  [bold green]All systems go! Ready to publish.[/bold green]")
    else:
        console.print("  [bold red]Fix the issues above before publishing.[/bold red]")
        console.print("  Copy .env.example to .env and fill in your API keys.")


@cli.command()
@click.option("--dry-run", is_flag=True, help="Preview without publishing")
@click.option("--max-pins", type=int, default=None, help="Max pins to publish")
@click.option("--product", type=str, default=None, help="Publish a specific product only")
@click.pass_context
def publish(ctx: click.Context, dry_run: bool, max_pins: int | None, product: str | None) -> None:
    """Publish new Pins from Dropbox product folders."""
    config = ctx.obj["config"]
    tracker = PublishTracker()
    publisher = Publisher(config, tracker)

    if dry_run:
        console.print(Panel(
            "[bold yellow]DRY RUN MODE — Nothing will actually be published[/bold yellow]",
            border_style="yellow",
        ))
    else:
        console.print(Panel(
            "[bold green]Publishing Pins...[/bold green]",
            border_style="green",
        ))

    if product:
        # Publish a specific product
        products = publisher.dropbox.get_all_products()
        target = next((p for p in products if p.name == product), None)
        if not target:
            console.print(f"[red]Product '{product}' not found.[/red]")
            console.print("Available products:")
            for p in products:
                console.print(f"  • {p.name}")
            return

        results = publisher.publish_product(target, dry_run=dry_run, max_pins=max_pins)
        _print_results({target.name: results})
    else:
        # Publish all products
        all_results = publisher.publish_all(dry_run=dry_run, max_pins_total=max_pins)
        _print_results(all_results)


def _print_results(results: dict) -> None:
    """Print a summary table of publishing results."""
    table = Table(title="Publishing Results", border_style="cyan")
    table.add_column("Product", style="cyan bold")
    table.add_column("Published", style="green", justify="center")
    table.add_column("Failed", style="red", justify="center")
    table.add_column("Total", justify="center")

    for product_name, pin_results in results.items():
        success = sum(1 for r in pin_results if r.success)
        failed = sum(1 for r in pin_results if not r.success)
        table.add_row(product_name, str(success), str(failed), str(len(pin_results)))

    console.print(table)


@cli.command()
@click.pass_context
def status(ctx: click.Context) -> None:
    """Show publishing history and statistics."""
    tracker = PublishTracker()
    summary = tracker.get_summary()

    console.print(Panel(
        "[bold cyan]PinPilot Publishing Status[/bold cyan]",
        border_style="cyan",
    ))

    # Overview
    console.print(f"  Total Pins published:  [bold green]{summary['total_published']}[/bold green]")
    console.print(f"  Total records:         {summary['record_count']}")
    console.print(f"  Last run:              {summary['last_run'] or 'never'}")

    # By product
    if summary["products"]:
        console.print()
        table = Table(title="Pins by Product", border_style="blue")
        table.add_column("Product", style="cyan")
        table.add_column("Pins", justify="center", style="green")

        for product_name, count in sorted(
            summary["products"].items(), key=lambda x: -x[1]
        ):
            table.add_row(product_name, str(count))

        console.print(table)
    else:
        console.print("\n  [dim]No Pins published yet.[/dim]")


@cli.command()
@click.pass_context
def boards(ctx: click.Context) -> None:
    """List all Pinterest boards."""
    config = ctx.obj["config"]
    pinterest = __import__("pinpilot.pinterest_client", fromlist=["PinterestClient"])
    client = pinterest.PinterestClient(config.pinterest)

    board_list = client.list_boards()

    table = Table(title="Pinterest Boards", border_style="magenta")
    table.add_column("Name", style="magenta bold")
    table.add_column("ID", style="dim")
    table.add_column("Privacy", justify="center")
    table.add_column("Pin Count", justify="center")

    for board in board_list:
        table.add_row(
            board.get("name", ""),
            board.get("id", ""),
            board.get("privacy", ""),
            str(board.get("pin_count", 0)),
        )

    console.print(table)


@cli.command()
@click.option("--interval", type=int, default=None,
              help="Hours between runs (overrides config)")
@click.option("--dry-run", is_flag=True, help="Preview mode for scheduled runs")
@click.pass_context
def schedule(ctx: click.Context, interval: int | None, dry_run: bool) -> None:
    """Run PinPilot on a recurring schedule."""
    import schedule as scheduler

    config = ctx.obj["config"]
    hours = interval or config.publishing.schedule_interval_hours

    console.print(Panel(
        f"[bold cyan]Scheduled Mode — Running every {hours} hour(s)[/bold cyan]\n"
        f"[dim]Press Ctrl+C to stop[/dim]",
        border_style="cyan",
    ))

    tracker = PublishTracker()
    publisher = Publisher(config, tracker)

    def run_job():
        console.print(f"\n[cyan]Running scheduled publish...[/cyan]")
        publisher.publish_all(dry_run=dry_run)

    # Run immediately, then on schedule
    run_job()
    scheduler.every(hours).hours.do(run_job)

    try:
        while True:
            scheduler.run_pending()
            time.sleep(60)
    except KeyboardInterrupt:
        console.print("\n[yellow]Scheduler stopped.[/yellow]")


@cli.command()
@click.option("--output", type=str, default="pinpilot_export.csv",
              help="Output CSV file path")
@click.pass_context
def export(ctx: click.Context, output: str) -> None:
    """Export publishing records to CSV."""
    tracker = PublishTracker()
    path = tracker.export_csv(output)
    console.print(f"[green]Exported to: {path}[/green]")


if __name__ == "__main__":
    cli()
