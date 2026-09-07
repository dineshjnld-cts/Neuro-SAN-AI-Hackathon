"""Run the local Fraud War Room dashboard."""

from pathlib import Path

from dotenv import load_dotenv


# Match the Studio CLI's local development behavior while preserving process
# environment precedence for production deployments.
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from apps.fraud_war_room.server import main  # noqa: E402


if __name__ == "__main__":
    main()
