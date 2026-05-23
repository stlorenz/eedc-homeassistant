"""ROI-Dashboard Benzinpreis-Auflösung — Folge-Fix nach #260.

`get_roi_dashboard` las im E-Auto-Branch zwar 7 Parameter aus `inv.parameter`
(jahresfahrleistung_km, verbrauch_kwh_100km, …), aber nicht
`benzinpreis_euro`. Stattdessen ging immer der Query-Default 1,85 €/L in
die Berechnung — die per-Investition gepflegten Werte und der EU-Weekly-
Oil-Bulletin-Preis aus den Monatsdaten waren effektiv tot.

Gleiche Bug-Klasse wie der v3.25.0-Fix für die anderen toten Schema-Keys,
nur für `benzinpreis_euro` damals vergessen.

Diese Tests deckeln:
- die reine Auflösungs-Kette `resolve_eauto_benzinpreis`,
- den Lookup-Helper `letzter_kraftstoffpreis_aus_lookup`,
- die Integration über `get_roi_dashboard` (per-Inv-Param wirkt, Slider
  override, Monatsdaten-Fallback, Response-Hinweis-Feld).
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.api.routes.investitionen.crud import get_roi_dashboard
from backend.models import Anlage, Investition, Monatsdaten
from backend.services.eauto_wirtschaftlichkeit import (
    letzter_kraftstoffpreis_aus_lookup,
    resolve_eauto_benzinpreis,
)


# ============================================================================
# Unit: resolve_eauto_benzinpreis — Reihenfolge der Auflösungs-Kette
# ============================================================================


def test_resolve_slider_override_gewinnt():
    """Query-Override (Slider) schlägt alles andere."""
    erg = resolve_eauto_benzinpreis(
        query_override=2.10,
        eauto_parameter={"benzinpreis_euro": 1.95},
        letzter_monats_benzinpreis=1.80,
    )
    assert erg.preis_euro == pytest.approx(2.10)
    assert erg.quelle == "slider"


def test_resolve_per_inv_param_gewinnt_ohne_slider():
    """Ohne Slider: per-Investition `benzinpreis_euro` schlägt Monatsdaten + Default.

    Das war die eigentliche Bug-Klasse: vorher las `get_roi_dashboard` den
    per-Inv-Wert nie und nutzte stattdessen den Query-Default.
    """
    erg = resolve_eauto_benzinpreis(
        query_override=None,
        eauto_parameter={"benzinpreis_euro": 1.95},
        letzter_monats_benzinpreis=1.80,
    )
    assert erg.preis_euro == pytest.approx(1.95)
    assert erg.quelle == "parameter"


def test_resolve_monatsdaten_fallback_ohne_param():
    """Ohne Slider und ohne per-Inv-Param: letzter Monatsdaten-Preis (EU OB)."""
    erg = resolve_eauto_benzinpreis(
        query_override=None,
        eauto_parameter={},
        letzter_monats_benzinpreis=1.80,
    )
    assert erg.preis_euro == pytest.approx(1.80)
    assert erg.quelle == "monatsdaten"


def test_resolve_default_wenn_nichts_vorhanden():
    """Letzter Fallback: PARAM_E_AUTO_DEFAULTS['benzinpreis_euro'] = 1,65."""
    erg = resolve_eauto_benzinpreis(
        query_override=None,
        eauto_parameter=None,
        letzter_monats_benzinpreis=None,
    )
    assert erg.preis_euro == pytest.approx(1.65)
    assert erg.quelle == "default"


def test_resolve_param_none_faellt_durch():
    """Wenn `benzinpreis_euro` im Param explizit None ist, weiter zur nächsten Stufe."""
    erg = resolve_eauto_benzinpreis(
        query_override=None,
        eauto_parameter={"benzinpreis_euro": None},
        letzter_monats_benzinpreis=1.80,
    )
    assert erg.preis_euro == pytest.approx(1.80)
    assert erg.quelle == "monatsdaten"


# ============================================================================
# Unit: letzter_kraftstoffpreis_aus_lookup
# ============================================================================


def test_letzter_kraftstoffpreis_leerer_lookup():
    assert letzter_kraftstoffpreis_aus_lookup({}) is None


def test_letzter_kraftstoffpreis_alle_none():
    lookup = {(2026, 1): None, (2026, 2): None, (2026, 3): None}
    assert letzter_kraftstoffpreis_aus_lookup(lookup) is None


def test_letzter_kraftstoffpreis_juengster_monat():
    """Jüngster nicht-leerer Monat gewinnt — auch wenn jüngere Monate None sind."""
    lookup = {
        (2026, 1): 1.70,
        (2026, 2): 1.75,
        (2026, 3): 1.80,
        (2026, 4): None,  # noch nicht aus EU OB importiert
    }
    assert letzter_kraftstoffpreis_aus_lookup(lookup) == pytest.approx(1.80)


def test_letzter_kraftstoffpreis_jahreswechsel():
    """Sortierung berücksichtigt Jahr + Monat."""
    lookup = {
        (2025, 11): 1.85,
        (2025, 12): 1.90,
        (2026, 1): 1.75,
    }
    assert letzter_kraftstoffpreis_aus_lookup(lookup) == pytest.approx(1.75)


# ============================================================================
# Integration: get_roi_dashboard mit E-Auto + Monatsdaten + per-Inv-Param
# ============================================================================


async def _seed_eauto(
    db,
    *,
    benzinpreis_param: float | None = None,
    kraftstoffpreise: list[tuple[int, int, float | None]] = (),
) -> int:
    """Anlage + E-Auto. Optional per-Inv `benzinpreis_euro` und EU-OB-Preise."""
    anlage = Anlage(anlagenname="Test", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    for jahr, monat, preis in kraftstoffpreise:
        db.add(Monatsdaten(
            anlage_id=anlage.id, jahr=jahr, monat=monat,
            netzbezug_kwh=100.0, einspeisung_kwh=200.0,
            kraftstoffpreis_euro=preis,
        ))
    params: dict = {
        "jahresfahrleistung_km": 15000,
        "verbrauch_kwh_100km": 18,
        "pv_ladeanteil_prozent": 60,
        "vergleich_verbrauch_l_100km": 7.5,
    }
    if benzinpreis_param is not None:
        params["benzinpreis_euro"] = benzinpreis_param
    db.add(Investition(
        anlage_id=anlage.id, typ="e-auto",
        bezeichnung="Test-EV",
        anschaffungsdatum=date(2024, 1, 1),
        anschaffungskosten_gesamt=40000.0,
        parameter=params,
    ))
    await db.flush()
    return anlage.id


def _eauto_detail(result) -> dict:
    """Detail-Dict der E-Auto-Berechnung aus der Response herausziehen."""
    eauto_b = next(b for b in result.berechnungen if b.investition_typ == "e-auto")
    return eauto_b.detail_berechnung


async def test_roi_per_inv_benzinpreis_wirkt(db):
    """Bug-Klasse: per-Inv `benzinpreis_euro` muss in die ROI-Berechnung einfließen.

    Vor diesem Fix: Query-Default 1,85 € wurde verwendet, der Param ignoriert.
    """
    anlage_id = await _seed_eauto(db, benzinpreis_param=1.95)
    result = await get_roi_dashboard(
        anlage_id=anlage_id, strompreis_cent=None, einspeiseverguetung_cent=None,
        benzinpreis_euro=None, jahr=None, db=db,
    )
    detail = _eauto_detail(result)
    assert detail["verwendeter_benzinpreis_euro"] == pytest.approx(1.95)
    assert detail["benzinpreis_quelle"] == "parameter"


async def test_roi_slider_override_schlaegt_per_inv(db):
    """Wenn der ROI-Slider einen Wert sendet, wirkt der über allen Pro-Inv-Werten."""
    anlage_id = await _seed_eauto(db, benzinpreis_param=1.95)
    result = await get_roi_dashboard(
        anlage_id=anlage_id, strompreis_cent=None, einspeiseverguetung_cent=None,
        benzinpreis_euro=2.10, jahr=None, db=db,
    )
    detail = _eauto_detail(result)
    assert detail["verwendeter_benzinpreis_euro"] == pytest.approx(2.10)
    assert detail["benzinpreis_quelle"] == "slider"


async def test_roi_monatsdaten_fallback_ohne_inv_param(db):
    """Ohne per-Inv-Param und ohne Slider: letzter Monatsdaten-Preis aus EU OB."""
    anlage_id = await _seed_eauto(
        db,
        benzinpreis_param=None,
        kraftstoffpreise=[(2026, 1, 1.70), (2026, 2, 1.75), (2026, 3, 1.82)],
    )
    result = await get_roi_dashboard(
        anlage_id=anlage_id, strompreis_cent=None, einspeiseverguetung_cent=None,
        benzinpreis_euro=None, jahr=None, db=db,
    )
    detail = _eauto_detail(result)
    assert detail["verwendeter_benzinpreis_euro"] == pytest.approx(1.82)
    assert detail["benzinpreis_quelle"] == "monatsdaten"


async def test_roi_default_ohne_param_und_ohne_monatsdaten(db):
    """Letzter Fallback wenn weder Param noch Monatsdaten: 1,65 € (Default)."""
    anlage_id = await _seed_eauto(db, benzinpreis_param=None)
    result = await get_roi_dashboard(
        anlage_id=anlage_id, strompreis_cent=None, einspeiseverguetung_cent=None,
        benzinpreis_euro=None, jahr=None, db=db,
    )
    detail = _eauto_detail(result)
    assert detail["verwendeter_benzinpreis_euro"] == pytest.approx(1.65)
    assert detail["benzinpreis_quelle"] == "default"


async def test_roi_response_benzinpreis_hinweis_zeigt_letzten_marktpreis(db):
    """Response liefert `benzinpreis_hinweis_euro` für den Slider-Placeholder."""
    anlage_id = await _seed_eauto(
        db,
        kraftstoffpreise=[(2026, 1, 1.70), (2026, 2, 1.82)],
    )
    result = await get_roi_dashboard(
        anlage_id=anlage_id, strompreis_cent=None, einspeiseverguetung_cent=None,
        benzinpreis_euro=None, jahr=None, db=db,
    )
    assert result.benzinpreis_hinweis_euro == pytest.approx(1.82)


async def test_roi_response_benzinpreis_hinweis_default_ohne_monatsdaten(db):
    """Ohne EU-OB-Daten: Hinweis-Wert ist der PARAM_E_AUTO-Default."""
    anlage_id = await _seed_eauto(db)
    result = await get_roi_dashboard(
        anlage_id=anlage_id, strompreis_cent=None, einspeiseverguetung_cent=None,
        benzinpreis_euro=None, jahr=None, db=db,
    )
    assert result.benzinpreis_hinweis_euro == pytest.approx(1.65)
