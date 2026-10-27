"""Application configuration loaded from environment variables."""

from dataclasses import dataclass
import os

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    portal_url: str
    portal_user: str
    portal_pass: str


def get_settings() -> Settings:
    load_dotenv()
    return Settings(
        portal_url=os.getenv("PORTAL_URL", "https://urja-ops.flockenergy.tech").rstrip("/"),
        portal_user=os.getenv("PORTAL_USER", ""),
        portal_pass=os.getenv("PORTAL_PASS", ""),
    )
