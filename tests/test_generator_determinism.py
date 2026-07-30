"""Cross-platform determinism canaries for the synthetic generator.

The generator is seeded and MUST regenerate byte-identically on every host —
that promise is what lets the repo commit only the generator, never
``data/synthetic/``, and score every capability against a committed answer key.

Faker's ``date_time`` provider historically broke that promise: it branches its
RNG draw on ``platform.system()`` (Windows draws integer seconds via
``random.randint``; other hosts draw a float via ``random.uniform``), and the
two consume different amounts of the seeded Mersenne-Twister stream. A single
``fake.date_of_birth()`` therefore shifted every subsequent Faker name draw on
Linux relative to Windows, so the generated name set — and every downstream CSV
and eval keyed on it — diverged across platforms at a fixed seed. The generator
pins all hosts to the integer-second path (see
``src/okojo/scenario/generator.py``); these tests are the tripwire that keeps it
pinned. If either fails, a platform divergence has re-entered the GENERATOR and
would otherwise surface as a mysterious downstream eval failure on CI only.
"""
from __future__ import annotations

import hashlib

from faker import Faker

# The sha256 of the generated account name set — ``{uid}\t{entity_name}`` per
# account, in uid order, newline-joined. Pinned to the Windows reference
# platform; Linux/macOS must match it byte-for-byte. Bump DELIBERATELY (and only)
# when the scenario's account roster is intentionally changed — never to paper
# over a platform difference.
EXPECTED_ACCOUNT_NAME_SET_SHA256 = (
    "a216bc44b0ccf66c3d153e22339eb60979bf6bcdd2e4d64f3988f4a96bd18f4e"
)


def _account_name_set_sha(conn) -> str:
    accts = sorted(conn.all_accounts(), key=lambda a: int(a["uid"]))
    blob = "\n".join(f"{int(a['uid'])}\t{str(a['entity_name'])}" for a in accts)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def test_account_name_set_is_platform_stable(conn):
    """The Faker-drawn account names hash to the committed expectation.

    A mismatch means the generator's name set changed. If it changed ONLY on
    CI (not locally), the generator has become platform-dependent again — fix
    the generator, do not update the constant. If the roster was changed on
    purpose, update the constant deliberately.
    """
    got = _account_name_set_sha(conn)
    assert got == EXPECTED_ACCOUNT_NAME_SET_SHA256, (
        "account name set diverged from the committed hash "
        f"(got {got}); if this fails only on CI the generator is "
        "platform-dependent again — see tests/test_generator_determinism.py"
    )


def test_faker_date_sampling_pinned_to_integer_seconds():
    """The Faker date pin is active: ``date_time_ad`` yields whole seconds.

    On the unpinned float path (``random.uniform``) ``timedelta(seconds=ts)``
    carries sub-second precision, so ``microsecond`` is essentially always
    non-zero. On the pinned integer path (``random.randint``) it is always
    zero. Importing the generator (done transitively by the test session)
    applies the class-level pin, so any Faker instance here inherits it.
    """
    fake = Faker()
    fake.seed_instance(42)
    samples = [fake.date_time_ad() for _ in range(25)]
    assert all(dt.microsecond == 0 for dt in samples), (
        "Faker date sampling is NOT pinned to integer seconds — the "
        "cross-platform determinism pin in scenario/generator.py is not active"
    )
