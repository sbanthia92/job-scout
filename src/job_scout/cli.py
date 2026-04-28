import os
from pathlib import Path
from typing import Annotated

import structlog
import typer

log = structlog.get_logger()

app = typer.Typer(help="Job Scout — AI-powered job search agent", no_args_is_help=True)


def _split_list(value: str) -> list[str]:
    return [item.strip() for item in value.split(";") if item.strip()]


@app.command()
def setup(
    resume: Annotated[Path, typer.Option("--resume", help="Path to resume PDF")],
    output: Annotated[Path, typer.Option("--output", help="Output path for encrypted profile")] = Path(
        "profile.encrypted.json"
    ),
) -> None:
    """Parse a resume PDF and create an encrypted profile for job matching."""
    from anthropic import Anthropic

    from job_scout.profile import extract_text_from_pdf, parse_resume, save_profile

    if not resume.exists():
        typer.echo(f"Error: {resume} does not exist", err=True)
        raise typer.Exit(1)

    key_str = os.environ.get("PROFILE_ENCRYPTION_KEY")
    if not key_str:
        typer.echo(
            "Error: PROFILE_ENCRYPTION_KEY environment variable is not set.\n"
            "Generate a key with:\n"
            "  python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\"",
            err=True,
        )
        raise typer.Exit(1)

    typer.echo(f"Extracting text from {resume}...")
    raw_text = extract_text_from_pdf(resume)
    if not raw_text.strip():
        typer.echo("Warning: could not extract text from PDF. Profile quality may be low.", err=True)

    typer.echo("\nAnswer the following questions to configure your job search.")
    typer.echo("Separate multiple values with semicolons ( ; )\n")

    titles_str: str = typer.prompt("Target job titles  (e.g. Software Engineer; Backend Engineer)")
    target_titles = _split_list(titles_str)

    seniority_str: str = typer.prompt("Seniority levels  (e.g. senior; staff; principal)")
    seniority = [s.lower() for s in _split_list(seniority_str)]

    locations_str: str = typer.prompt("Target locations  (e.g. San Francisco, CA; Remote)")
    target_locations = _split_list(locations_str)

    salary_str: str = typer.prompt("Salary floor in USD (press Enter to skip)", default="")
    salary_floor: float | None = float(salary_str.replace(",", "")) if salary_str.strip() else None

    requires_visa: bool = typer.confirm("Require visa sponsorship?")

    deal_breakers_str: str = typer.prompt("Deal-breaker keywords (press Enter to skip)", default="")
    deal_breakers = [d.lower() for d in _split_list(deal_breakers_str)]

    ideal_role: str = typer.prompt("Describe your ideal role in 1–2 sentences")

    artifacts_str: str = typer.prompt("Work artifact URLs or descriptions (press Enter to skip)", default="")
    work_artifacts = _split_list(artifacts_str)

    typer.echo("\nParsing profile with Claude Sonnet…")

    client = Anthropic()
    try:
        profile = parse_resume(
            raw_text=raw_text,
            target_titles=target_titles,
            seniority=seniority,
            target_locations=target_locations,
            salary_floor=salary_floor,
            requires_visa_sponsorship=requires_visa,
            deal_breakers=deal_breakers,
            ideal_role_description=ideal_role,
            work_artifacts=work_artifacts,
            client=client,
        )
    except Exception as exc:
        typer.echo(f"Error parsing profile: {exc}", err=True)
        raise typer.Exit(1)

    typer.echo("\n--- Parsed Profile ---")
    typer.echo(profile.model_dump_json(indent=2))

    if not typer.confirm("\nSave this profile?"):
        typer.echo("Aborted.")
        raise typer.Exit(0)

    save_profile(profile, output, key_str.encode())
    typer.echo(f"\nProfile saved to {output}")


@app.command()
def run(
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Print scored jobs without emailing or updating state")] = False,
) -> None:
    """Run the job search pipeline."""
    typer.echo("scout run is not yet implemented.", err=True)
    raise typer.Exit(1)
