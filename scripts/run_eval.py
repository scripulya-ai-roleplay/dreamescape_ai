import os
import subprocess
import sys
from pathlib import Path

import click

REPO_ROOT = Path(__file__).resolve().parent.parent


@click.command()
@click.option("--transcript", "transcript", default=None, help="Run a single transcript stem (e.g. 'callback').")
def main(transcript: str | None) -> None:
	"""Run the memory eval probes against a live stack.

	Requires the full environment to be up (see scripulya_deploy) and OPENAI_API_KEY configured for
	embeddings/summary. Probes replay scripted transcripts from tests/eval/transcripts and assert
	long-range recall / reversal behavior via the context-usage endpoint.
	"""
	expr = f"eval and {transcript}" if transcript else "eval"
	cmd = [sys.executable, "-m", "pytest", "-m", expr, "tests/eval", "-v"]
	# EVAL_ENABLED flips the probes from skip to run.
	env = {**os.environ, "EVAL_ENABLED": "1"}
	click.echo(f"Running: {' '.join(cmd)}")
	raise SystemExit(subprocess.call(cmd, cwd=str(REPO_ROOT), env=env))


if __name__ == "__main__":
	main()
