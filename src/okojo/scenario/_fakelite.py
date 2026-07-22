"""A minimal, dependency-free stand-in for the subset of Faker this project uses.

The generator prefers the real ``faker`` package (see requirements.txt); this
fallback only kicks in when Faker isn't installed, so the scenario still
generates in a bare environment. Deterministic given the same seed."""

from __future__ import annotations

import random
from datetime import date

_FIRST = [
    "Amir", "Lena", "Karim", "Sofia", "Wei", "Mina", "Omar", "Hana", "Ravi", "Nadia",
    "Emre", "Yuki", "Diego", "Farah", "Leo", "Priya", "Yusuf", "Elif", "Bo", "Ines",
    "Tariq", "Marta", "Jun", "Salma", "Nils", "Aya", "Rustam", "Vera", "Kai", "Dina",
]
_LAST = [
    "Haddad", "Novak", "Chen", "Rossi", "Khan", "Aydin", "Silva", "Popov", "Nair", "Meyer",
    "Ganem", "Okonkwo", "Tanaka", "Ferreira", "Aliyev", "Costa", "Demir", "Wang", "Bauer", "Reyes",
]
_CO_A = ["Meridian", "Zenith", "Crescent", "Harbour", "Vanguard", "Solstice", "Pinnacle", "Aurora",
         "Blackstone", "Cobalt", "Delta", "Basalt", "Onyx", "Cedar", "Falcon", "Marlin"]
_CO_B = ["Trading", "Holdings", "Commodities", "Petroleum", "Bitumen", "Global", "Logistics",
         "Custody", "Capital", "Ventures", "Energy", "Resources"]
_CO_C = ["Ltd", "LLC", "DMCC", "Limited", "FZE", "PTE. LTD.", "Co."]


class FakeLite:
    """Implements only .name(), .company(), .date_of_birth(), .seed_instance()."""

    def __init__(self, seed: int = 0) -> None:
        self._rng = random.Random(seed)

    def seed_instance(self, seed: int) -> None:
        self._rng = random.Random(seed)

    def name(self) -> str:
        return f"{self._rng.choice(_FIRST)} {self._rng.choice(_LAST)}"

    def company(self) -> str:
        return f"{self._rng.choice(_CO_A)} {self._rng.choice(_CO_B)} {self._rng.choice(_CO_C)}"

    def date_of_birth(self, minimum_age: int = 25, maximum_age: int = 65) -> date:
        year = 2026 - self._rng.randint(minimum_age, maximum_age)
        return date(year, self._rng.randint(1, 12), self._rng.randint(1, 28))
