"""`FANTABOT_LEAGUE_ID=` (no value) must not crash `Settings()`.

`.env.example` ships the field blank for a harvest-only setup that never reads
it, and pydantic-settings only falls back to a field's default when the
variable is missing entirely — present-but-empty reaches `int("")` instead.
Every command imports `settings` at module load (the Alembic env included), so
this broke `alembic upgrade head` on a fresh clone before the field's own "0
means unset" was made to actually hold for the blank string too.
"""

from __future__ import annotations

from fantabot.config import Settings


def _settings(**overrides: object) -> Settings:
    """A Settings built from arguments only — no `.env`, no ambient environment."""
    return Settings(_env_file=None, **overrides)


def test_a_blank_league_id_is_unset_not_a_crash() -> None:
    assert _settings(fantabot_league_id="").fantabot_league_id == 0


def test_a_real_league_id_still_parses() -> None:
    assert _settings(fantabot_league_id="4103937").fantabot_league_id == 4103937


def test_the_default_is_still_unset() -> None:
    assert _settings().fantabot_league_id == 0
