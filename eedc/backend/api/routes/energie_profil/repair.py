"""
Energie-Profil API — Repair- / Write-Endpoints.

DELETE /api/energie-profil/{anlage_id}/rohdaten — Löscht TagesEnergieProfil-Daten einer Anlage
DELETE /api/energie-profil/rohdaten — Löscht TagesEnergieProfil-Daten aller Anlagen
POST   /api/energie-profil/reaggregate-heute — Triggert Neu-Aggregation heutiger Tag
POST   /api/energie-profil/{anlage_id}/reaggregate-tag — Reaggregate eines Tages
POST   /api/energie-profil/{anlage_id}/vollbackfill — Lückenfüller aus HA-LTS (additiv)
POST   /api/energie-profil/{anlage_id}/kraftstoffpreis-backfill[/tages|/monats] — EU Oil Bulletin
"""

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, and_, delete, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_db
from backend.models.anlage import Anlage
from backend.models.tages_energie_profil import TagesEnergieProfil, TagesZusammenfassung

from ._shared import logger

router = APIRouter()


@router.delete("/{anlage_id}/rohdaten")
async def delete_rohdaten(
    anlage_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Löscht alle TagesEnergieProfil- und TagesZusammenfassung-Daten einer Anlage.

    Der Scheduler schreibt ab dem nächsten Lauf (alle 15 Min) neue, korrekte Daten.
    Monatsdaten bleiben erhalten.
    """
    result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    anlage = result.scalar_one_or_none()
    if not anlage:
        raise HTTPException(status_code=404, detail="Anlage nicht gefunden")

    del_stunden = await db.execute(
        delete(TagesEnergieProfil).where(TagesEnergieProfil.anlage_id == anlage_id)
    )
    del_tage = await db.execute(
        delete(TagesZusammenfassung).where(TagesZusammenfassung.anlage_id == anlage_id)
    )
    # Flag zurücksetzen, damit der nächste Monatsabschluss den Auto-Vollbackfill
    # aus HA Statistics erneut anstößt
    anlage.vollbackfill_durchgefuehrt = False
    await db.commit()

    return {
        "geloescht_stundenwerte": del_stunden.rowcount,
        "geloescht_tagessummen": del_tage.rowcount,
        "hinweis": "Scheduler schreibt ab dem nächsten Lauf (max. 15 Min) neue Daten. Monatsdaten bleiben erhalten.",
    }


@router.post("/reaggregate-heute")
async def reaggregate_heute():
    """Triggert sofortige Neu-Aggregation des heutigen Tages für alle Anlagen."""
    from backend.services.energie_profil_service import aggregate_today_all
    results = await aggregate_today_all()
    return {"status": "ok", "anlagen": results}


@router.post("/{anlage_id}/reaggregate-tag")
async def reaggregate_tag(
    anlage_id: int,
    datum: date = Query(..., description="Tag, der neu aggregiert werden soll"),
    mit_resnap: bool = Query(
        True,
        description="Vor dem Aggregat die SensorSnapshots des Tages frisch aus HA-Statistics ziehen "
                    "(repariert Counter-Spikes, z. B. nach Update-Restarts). Default an.",
    ),
    db: AsyncSession = Depends(get_db),
):
    """
    Aggregiert einen einzelnen Tag für eine Anlage neu (Self-Service nach
    Snapshot-Spike o. ä.).

    Mit `mit_resnap=true` (Default) werden zuerst die SensorSnapshots für den
    Tag frisch aus HA Long-Term Statistics geschrieben und danach die Aggregate
    daraus neu gebaut. Ohne Resnap (`mit_resnap=false`) wird nur das Aggregat
    aus den vorhandenen Snapshots neu gerechnet — sinnvoll, wenn die Snapshots
    bekannt-gut sind und nur die Tagesprofil-/Zusammenfassungs-Schicht neu soll.

    `aggregate_day` macht intern delete + insert für Tagesprofil und
    Zusammenfassung — der Aufruf ist also idempotent und sicher mehrfach
    ausführbar.
    """
    from backend.services.energie_profil_service import aggregate_day

    result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    anlage = result.scalar_one_or_none()
    if not anlage:
        raise HTTPException(status_code=404, detail=f"Anlage {anlage_id} nicht gefunden")

    if mit_resnap:
        try:
            from backend.services.sensor_snapshot_service import resnap_anlage_range
            from datetime import datetime as _dt, timedelta as _td
            # Range deckt zwei Boundaries ab, die der Read-Pfad braucht:
            #   - Vortag 23:00: Backward-Slot 0 = snap(Tag 00:00) − snap(Vortag 23:00)
            #     für kWh- und (seit Etappe 3c P2) Counter-Pfad. Ohne den Boundary
            #     bleibt ein korrupter Snapshot persistent und erzeugt dauerhaft
            #     einen Stunde-0-Spike (Befund Rainer 1.5.2026).
            #   - Folgetag 00:00: HA-konformes Tagesgesamt der Counter
            #     = snap(Folgetag 00:00) − snap(Tag 00:00). Ohne den Boundary
            #     stehen alte Werte aus prä-Sensor-Wechsel-Zeiten dauerhaft drin
            #     und falten sich beim Recycle als Lifetime-Sprung in die
            #     Tagessumme (Befund MartyBr 7.5.2026, Counter-Migration
            #     Vicare→Optisplitter).
            # Slot-Konvention seit Etappe 3c P2 (KONZEPT-ENERGIEPROFIL-3C.md):
            # Hourly-Konsumenten gehen einheitlich über
            # `BoundaryRange.for_hourly_slots(datum)` — Backward (#144).
            # Tages-Counter nutzen Boundary-Diff über das HA-Tagesfenster.
            tag_start = _dt.combine(datum, _dt.min.time())
            von_dt = tag_start - _td(hours=1)               # Vortag 23:00
            bis_dt = tag_start + _td(days=1, hours=1)       # Folgetag 01:00 → schließt Folgetag 00:00 ein
            resnap_stats = await resnap_anlage_range(
                db, anlage, von=von_dt, bis=bis_dt, include_5min=True,
            )
            logger.info(
                f"Reaggregate Anlage {anlage_id} {datum}: Resnap "
                f"{resnap_stats['hourly']} hourly + {resnap_stats['5min']} 5-Min Slots"
            )
        except Exception as e:
            logger.warning(
                f"Reaggregate Anlage {anlage_id} {datum}: Resnap fehlgeschlagen "
                f"(Aggregat läuft trotzdem): {type(e).__name__}: {e}"
            )

    try:
        zusammenfassung = await aggregate_day(anlage, datum, db, datenquelle="manuell")
    except Exception as e:
        logger.error(f"Reaggregate Anlage {anlage_id} {datum} FEHLER: {type(e).__name__}: {e}")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")

    if zusammenfassung is None:
        raise HTTPException(
            status_code=400,
            detail=f"Aggregation für {datum} nicht möglich — keine Live-/MQTT-Daten gefunden.",
        )

    # Zählt Stunden mit echten Messwerten (nicht nur geschriebene None-Zeilen).
    # `stunden_verfuegbar` aus der Zusammenfassung zählt alle 24 Slots auch
    # wenn pv_kw=einspeisung_kw=netzbezug_kw=NULL — das wäre für die
    # Erfolgsmeldung im Frontend irreführend.
    from sqlalchemy import or_, func
    messwerte_result = await db.execute(
        select(func.count()).select_from(TagesEnergieProfil).where(
            and_(
                TagesEnergieProfil.anlage_id == anlage_id,
                TagesEnergieProfil.datum == datum,
                or_(
                    TagesEnergieProfil.pv_kw.isnot(None),
                    TagesEnergieProfil.einspeisung_kw.isnot(None),
                    TagesEnergieProfil.netzbezug_kw.isnot(None),
                    TagesEnergieProfil.verbrauch_kw.isnot(None),
                ),
            )
        )
    )
    stunden_mit_messdaten = messwerte_result.scalar_one()

    await db.commit()
    return {
        "status": "ok",
        "datum": datum.isoformat(),
        "stunden_verfuegbar": zusammenfassung.stunden_verfuegbar,
        "stunden_mit_messdaten": stunden_mit_messdaten,
    }


@router.post("/{anlage_id}/vollbackfill")
async def vollbackfill(
    anlage_id: int,
    von: Optional[date] = Query(None, description="Startdatum (Standard: frühestes Datum in HA Statistics)"),
    bis: Optional[date] = Query(None, description="Enddatum (Standard: gestern)"),
    overwrite: Optional[bool] = Query(
        None,
        description="DEPRECATED (#190): wird ignoriert. Vollbackfill ist immer additiv.",
        deprecated=True,
    ),
    db: AsyncSession = Depends(get_db),
):
    """
    Füllt fehlende Tage im Energieprofil aus HA Long-Term Statistics nach.

    **Immer additiv** (#190): bestehende Tage bleiben unverändert.
    Für gezielte Reparatur einzelner Tage: /reaggregate-tag mit Vorschau.

    Returns:
        verarbeitet: Anzahl Tage im Zeitraum
        geschrieben: Davon neu geschriebene Tage
        uebersprungen_keine_daten: Tage ohne HA-Statistics-Werte
        uebersprungen_existiert: Tage mit bereits vorhandenem Profil
    """
    from backend.services.energie_profil_service import resolve_and_backfill_from_statistics

    if overwrite:
        logger.info(
            f"Vollbackfill Anlage {anlage_id}: overwrite=true wurde gesendet, wird ignoriert "
            "(#190: nur additiv, bestehende Tage bleiben)"
        )

    result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    anlage = result.scalar_one_or_none()
    if not anlage:
        raise HTTPException(status_code=404, detail=f"Anlage {anlage_id} nicht gefunden")

    try:
        backfill = await resolve_and_backfill_from_statistics(anlage, db, von=von, bis=bis)
    except Exception as e:
        import traceback
        logger.error(f"Vollbackfill Anlage {anlage_id} FEHLER: {type(e).__name__}: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")

    if backfill.missing_eids:
        logger.warning(
            f"Anlage {anlage_id}: {len(backfill.missing_eids)} Sensor(en) nicht in HA "
            f"statistics_meta gefunden, werden ignoriert: {backfill.missing_eids}"
        )

    if backfill.status == "ha_unavailable":
        raise HTTPException(status_code=503, detail=backfill.detail)
    if backfill.status in ("no_sensors", "no_valid_sensors", "earliest_unknown", "empty_range"):
        raise HTTPException(status_code=400, detail=backfill.detail)

    # Flag setzen, damit der Auto-Vollbackfill im _post_save_hintergrund nicht erneut läuft
    anlage.vollbackfill_durchgefuehrt = True
    await db.commit()

    logger.info(
        f"Vollbackfill Anlage {anlage_id}: {backfill.geschrieben}/{backfill.verarbeitet} Tage "
        f"von {backfill.von} bis {backfill.bis} "
        f"(skip ohne_daten={backfill.uebersprungen_keine_daten}, "
        f"skip existiert={backfill.uebersprungen_existiert})"
    )
    return {
        "verarbeitet": backfill.verarbeitet,
        "geschrieben": backfill.geschrieben,
        "uebersprungen_keine_daten": backfill.uebersprungen_keine_daten,
        "uebersprungen_existiert": backfill.uebersprungen_existiert,
        "von": backfill.von.isoformat(),
        "bis": backfill.bis.isoformat(),
    }


@router.post("/{anlage_id}/kraftstoffpreis-backfill/tages")
async def kraftstoffpreis_backfill_tages(
    anlage_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Befüllt TagesZusammenfassung.kraftstoffpreis_euro aus EU Oil Bulletin
    (Euro-Super 95, inkl. Steuern) für alle Tage ohne Preis.
    """
    result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    anlage = result.scalar_one_or_none()
    if not anlage:
        raise HTTPException(status_code=404, detail=f"Anlage {anlage_id} nicht gefunden")

    from backend.services.kraftstoff_preis_service import backfill_kraftstoffpreise
    land = anlage.standort_land or "DE"
    info = await backfill_kraftstoffpreise(anlage_id, land, db)
    return {
        "aktualisiert": info.get("aktualisiert", 0),
        "land": info.get("land", land),
        "hinweis": info.get("hinweis"),
        "fehler": info.get("fehler"),
    }


@router.post("/{anlage_id}/kraftstoffpreis-backfill/monats")
async def kraftstoffpreis_backfill_monats(
    anlage_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Befüllt Monatsdaten.kraftstoffpreis_euro aus EU Oil Bulletin
    (Monatsdurchschnitt aus Wochenpreisen) für alle Monate ohne Preis.
    """
    result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    anlage = result.scalar_one_or_none()
    if not anlage:
        raise HTTPException(status_code=404, detail=f"Anlage {anlage_id} nicht gefunden")

    from backend.services.kraftstoff_preis_service import backfill_monatsdaten_kraftstoffpreise
    land = anlage.standort_land or "DE"
    info = await backfill_monatsdaten_kraftstoffpreise(anlage_id, land, db)
    return {
        "aktualisiert": info.get("aktualisiert", 0),
        "land": info.get("land", land),
        "hinweis": info.get("hinweis"),
        "fehler": info.get("fehler"),
    }


@router.post("/{anlage_id}/kraftstoffpreis-backfill")
async def kraftstoffpreis_backfill(
    anlage_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Alt-Endpoint (Rückwärtskompatibilität): befüllt Tages- und Monats-Kraftstoffpreise
    in einem Aufruf. Neue UIs sollten die split-Endpoints ``/tages`` und ``/monats`` nutzen.
    """
    result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    anlage = result.scalar_one_or_none()
    if not anlage:
        raise HTTPException(status_code=404, detail=f"Anlage {anlage_id} nicht gefunden")

    from backend.services.kraftstoff_preis_service import (
        backfill_kraftstoffpreise, backfill_monatsdaten_kraftstoffpreise
    )
    land = anlage.standort_land or "DE"
    tages_info = await backfill_kraftstoffpreise(anlage_id, land, db)
    monats_info = await backfill_monatsdaten_kraftstoffpreise(anlage_id, land, db)
    return {
        "tages_aktualisiert": tages_info.get("aktualisiert", 0),
        "monats_aktualisiert": monats_info.get("aktualisiert", 0),
        "land": tages_info.get("land", land),
    }


@router.delete("/rohdaten")
async def delete_alle_rohdaten(
    db: AsyncSession = Depends(get_db),
):
    """
    Löscht alle TagesEnergieProfil- und TagesZusammenfassung-Daten aller Anlagen.

    Wird verwendet wenn Energieprofil-Daten durch falsch gemappte Sensoren
    korrumpiert wurden. Monatsdaten bleiben erhalten.
    Der Scheduler berechnet alles neu (max. 15 Min).
    """
    del_stunden = await db.execute(delete(TagesEnergieProfil))
    del_tage = await db.execute(delete(TagesZusammenfassung))
    # Flag bei ALLEN Anlagen zurücksetzen, damit der nächste Monatsabschluss
    # den Auto-Vollbackfill aus HA Statistics erneut anstößt
    await db.execute(update(Anlage).values(vollbackfill_durchgefuehrt=False))
    await db.commit()

    return {
        "geloescht_stundenwerte": del_stunden.rowcount,
        "geloescht_tagessummen": del_tage.rowcount,
        "hinweis": "Scheduler schreibt ab dem nächsten Lauf (max. 15 Min) neue Daten. Monatsdaten bleiben erhalten.",
    }
