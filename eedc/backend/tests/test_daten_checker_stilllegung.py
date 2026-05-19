"""
Akzeptanztest: Daten-Checker respektiert `stilllegungsdatum` in der
kWp-Σ und im Sensor-Mapping-Vollständigkeits-Check (#608 MartyBr).

Hintergrund: Bei einer String-Verlegung zwischen Wechselrichtern wird der
alte String stillgelegt (Stilllegungsdatum gesetzt, `aktiv` bleibt True
für historische Auswertungen). Beim großen `ist_aktiv_im_monat`-Sweep
v3.29.0 (#236) hatten zwei Daten-Checker-Pfade die Filterung nicht
übernommen: kWp-Summe addierte den stillgelegten String mit, und der
Sensor-Mapping-Check bemängelte fehlende Entität an einer Komponente,
die gar keine Daten mehr liefern soll.

Self-contained:

    eedc/backend/venv/bin/python -m pytest \\
        eedc/backend/tests/test_daten_checker_stilllegung.py
"""

from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from datetime import date, timedelta
from pathlib import Path

import pytest

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND_ROOT))

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402

from backend.core.database import Base  # noqa: E402
from backend.models import (  # noqa: E402, F401
    Anlage, Investition,
)


@asynccontextmanager
async def _session_ctx():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    session = Session()
    try:
        yield session
    finally:
        await session.close()
        await engine.dispose()


async def _seed(db: AsyncSession, total_kwp: float) -> Anlage:
    anlage = Anlage(anlagenname="Test", leistung_kwp=total_kwp)
    db.add(anlage)
    await db.flush()
    return anlage


def _add_module(
    db: AsyncSession, anlage_id: int, bezeichnung: str, kwp: float,
    anschaffungsdatum: date,
    stilllegungsdatum: date | None = None,
    aktiv: bool = True,
):
    inv = Investition(
        anlage_id=anlage_id, typ="pv-module", bezeichnung=bezeichnung,
        leistung_kwp=kwp, anschaffungsdatum=anschaffungsdatum,
        stilllegungsdatum=stilllegungsdatum, aktiv=aktiv,
    )
    db.add(inv)
    return inv


@pytest.mark.asyncio
async def test_kwp_summe_ignoriert_stillgelegten_string():
    """MartyBr-Befund: Σ aktiver kWp inkludierte stillgelegten Ost-String.
    Nach Fix: nur Module ohne (oder mit zukünftigem) Stilllegungsdatum zählen.
    """
    from backend.services.daten_checker import DatenChecker
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    async with _session_ctx() as db:
        # Vor 1 Jahr verlegt: Ost-String wurde von WR-A zu WR-B verlegt.
        # Alter Eintrag stillgelegt, neuer aktiv. Anlagenleistung 16 kWp =
        # 6 (Süd) + 4 (West) + 6 (Ost neu).  Ohne Filter würde der Checker
        # 21.8 kWp errechnen (inkl. 5.8 alter Ost) und ein Mismatch melden.
        anlage = await _seed(db, total_kwp=16.0)
        gestern = date.today() - timedelta(days=365)
        _add_module(db, anlage.id, "Süd", 6.0, anschaffungsdatum=date(2024, 1, 1))
        _add_module(db, anlage.id, "West", 4.0, anschaffungsdatum=date(2024, 1, 1))
        _add_module(
            db, anlage.id, "Ost (alt, verlegt)", 5.8,
            anschaffungsdatum=date(2024, 1, 1),
            stilllegungsdatum=gestern,
        )
        _add_module(db, anlage.id, "Ost (neu)", 6.0, anschaffungsdatum=gestern)
        await db.commit()

        anlage = (await db.execute(
            select(Anlage).options(selectinload(Anlage.investitionen)).where(Anlage.id == anlage.id)
        )).scalar_one()

        checker = DatenChecker(db)
        ergebnisse = checker._check_stammdaten(anlage)

        # OK-Meldung muss die Summe der drei aktiven Module zeigen (16.0 kWp,
        # 3 Modul-Gruppen) — ohne den stillgelegten Ost-Eintrag.
        ok_meldungen = [r for r in ergebnisse if "PV-Module:" in r.meldung]
        assert len(ok_meldungen) == 1, f"Erwarte 1 PV-Modul-Σ-Meldung, fand {len(ok_meldungen)}"
        msg = ok_meldungen[0].meldung
        assert "16.0 kWp" in msg, f"Σ aktiver kWp sollte 16.0 sein (ohne stillgelegten String), war: {msg}"
        assert "3 Modul-Gruppen" in msg, f"3 aktive Module erwartet, war: {msg}"

        # Kein Mismatch-WARNING
        warnings = [r for r in ergebnisse if "stimmt nicht" in r.meldung]
        assert len(warnings) == 0, (
            f"Kein kWp-Mismatch erwartet (Σ aktiv == Anlagenleistung), "
            f"fand: {[w.meldung for w in warnings]}"
        )


@pytest.mark.asyncio
async def test_sensor_mapping_check_ignoriert_stillgelegten_string():
    """MartyBr-Befund: stillgelegter String wurde im Sensor-Mapping-
    Vollständigkeits-Check bemängelt, obwohl keine Sensor-Zuordnung
    mehr sinnvoll ist."""
    from backend.services.daten_checker import DatenChecker
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    async with _session_ctx() as db:
        anlage = await _seed(db, total_kwp=10.0)
        gestern = date.today() - timedelta(days=30)
        # Aktiver Süd mit gemapptem Sensor
        _add_module(db, anlage.id, "Süd", 10.0, anschaffungsdatum=date(2024, 1, 1))
        # Stillgelegter Ost ohne Sensor — soll NICHT bemängelt werden
        _add_module(
            db, anlage.id, "Ost (alt)", 5.0,
            anschaffungsdatum=date(2024, 1, 1),
            stilllegungsdatum=gestern,
        )
        await db.flush()
        # Sensor-Mapping für die aktive Süd-Investition:
        sued_id = next(i.id for i in (await db.execute(select(Investition))).scalars() if i.bezeichnung == "Süd")
        anlage.sensor_mapping = {
            "basis": {
                "einspeisung": {"strategie": "sensor", "sensor_id": "sensor.einspeisung"},
                "netzbezug": {"strategie": "sensor", "sensor_id": "sensor.netzbezug"},
            },
            "investitionen": {
                str(sued_id): {
                    "felder": {
                        "pv_erzeugung_kwh": {"strategie": "sensor", "sensor_id": "sensor.sued_kwh"},
                    },
                },
            },
        }
        await db.commit()

        anlage = (await db.execute(
            select(Anlage).options(selectinload(Anlage.investitionen)).where(Anlage.id == anlage.id)
        )).scalar_one()

        checker = DatenChecker(db)
        ergebnisse = checker._check_energieprofil_abdeckung(anlage)

        # Erwartung: OK-Meldung „Alle 1 aktive Komponenten haben kWh-Zähler
        # gemappt" — der stillgelegte Ost-String wird gar nicht erst geprüft.
        ok = [r for r in ergebnisse if "aktiven Komponenten haben kWh-Zähler gemappt" in r.meldung]
        assert len(ok) == 1, (
            f"Erwarte 1 OK-Meldung für vollständige Abdeckung, fand:\n"
            + "\n".join(f"  {r.schwere.value}: {r.meldung}" for r in ergebnisse)
        )
        assert "Alle 1" in ok[0].meldung, (
            f"Erwarte Zählung '1' (nur Süd ist aktiv), war: {ok[0].meldung}"
        )

        # Kein WARNING zu fehlender Komponenten-Abdeckung
        warnings = [r for r in ergebnisse if "ohne vollständige kWh-Zähler-Abdeckung" in r.meldung]
        assert len(warnings) == 0, (
            f"Stillgelegter String darf nicht bemängelt werden, fand:\n"
            + "\n".join(f"  {w.meldung}: {w.details}" for w in warnings)
        )


@pytest.mark.asyncio
async def test_zukuenftig_stillgelegt_zaehlt_weiterhin():
    """Wenn das Stilllegungsdatum in der Zukunft liegt (geplante Verlegung),
    zählt das Modul heute noch als aktiv — kein vorzeitiger Ausschluss."""
    from backend.services.daten_checker import DatenChecker
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    async with _session_ctx() as db:
        anlage = await _seed(db, total_kwp=10.0)
        morgen = date.today() + timedelta(days=30)
        _add_module(db, anlage.id, "Süd", 6.0, anschaffungsdatum=date(2024, 1, 1))
        _add_module(
            db, anlage.id, "Geplant abgeschaltet", 4.0,
            anschaffungsdatum=date(2024, 1, 1),
            stilllegungsdatum=morgen,
        )
        await db.commit()

        anlage = (await db.execute(
            select(Anlage).options(selectinload(Anlage.investitionen)).where(Anlage.id == anlage.id)
        )).scalar_one()

        checker = DatenChecker(db)
        ergebnisse = checker._check_stammdaten(anlage)
        ok = [r for r in ergebnisse if "PV-Module:" in r.meldung]
        assert len(ok) == 1
        assert "10.0 kWp" in ok[0].meldung
        assert "2 Modul-Gruppen" in ok[0].meldung
