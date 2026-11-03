"""Command-line entry point for local replay of an impact investigation."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .investigator import ImpactInvestigationAgent
from .models import Ticket
from .tools import LocalCorpusTools


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Investigate a proposed change against local commerce-service evidence.")
    parser.add_argument("--corpus", type=Path, default=Path("sample-repositories"), help="Path to the sample-repositories directory")
    parser.add_argument("--ticket-json", type=Path, help="JSON file with ticket_id, summary, description, and acceptance_criteria")
    parser.add_argument("--summary", help="Ticket summary when not using --ticket-json")
    parser.add_argument("--description", default="", help="Ticket or proposed-change description")
    parser.add_argument("--ticket-id", default="PROPOSED-CHANGE")
    parser.add_argument("--output", choices=("json", "markdown"), default="markdown")
    args = parser.parse_args(argv)

    if args.ticket_json:
        ticket_data = json.loads(args.ticket_json.read_text(encoding="utf-8"))
    elif args.summary:
        ticket_data = {"ticket_id": args.ticket_id, "summary": args.summary, "description": args.description}
    else:
        parser.error("provide --ticket-json or --summary")
    agent = ImpactInvestigationAgent(LocalCorpusTools(args.corpus))
    result = agent.investigate(Ticket.from_dict(ticket_data))
    if args.output == "json":
        print(json.dumps(result.to_dict(), indent=2))
    else:
        sys.stdout.write(result.to_markdown())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
