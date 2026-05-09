"""
Source-Hierarchie für Schreib-Entscheidungen auf Aggregat-Tabellen
(Etappe 3d Päckchen 1).

Niedrigere Zahl = höhere Priorität. Eingesetzt von
`backend.services.provenance.write_with_provenance()` ab Päckchen 3.

Konzept: docs/KONZEPT-DATENPIPELINE.md Sektion 3.1.

Vokabular ist hier abgeschlossen pro Päckchen-Lieferung — neue Schreib-Pfade
müssen ihr Source-Label hier eintragen, sonst weist der Helper sie ab.
Hierarchie-Verletzungen werden im Audit-Log mit decision="rejected_lower_priority"
dokumentiert; gleiche Priorität ist Last-Writer-Wins (akzeptiert, gleiche
Vertrauensklasse). Repair-Source steht als eigene Stufe über allem, damit
explizite User-Reset-Läufe im Audit-Log auf den ersten Blick erkennbar sind.
"""

from enum import IntEnum


class SourcePriority(IntEnum):
    """Schreib-Hierarchie. Niedrigere Zahl gewinnt."""

    REPAIR = 0
    """Repair-Orchestrator mit force_override=True. Steht über allem,
    audit-log-pflichtig mit Operation-ID."""

    MANUAL = 1
    """User-Eingabe (Form, CSV-Wizard). Niemals von Maschine überschreiben."""

    EXTERNAL_AUTHORITATIVE = 2
    """Maschinen-bestätigte Quelle (Cloud-Portal, HA-Statistics-LTS).
    Konflikt zwischen Cloud + HA-Stats: Last-Writer-Wins (selten in Praxis,
    eindeutiger Pfad pro Anlage)."""

    AUTO_AGGREGATION = 3
    """Berechnet, Annahmen-behaftet (Monatsabschluss-Roll-up)."""

    FALLBACK = 4
    """Best-Effort, lückenanfällig (Snapshot-Aggregator, MQTT-Fallback)."""


SOURCE_LABELS: dict[str, SourcePriority] = {
    # Repair (force_override über Repair-Orchestrator, P4-Lieferung)
    "repair": SourcePriority.REPAIR,

    # Manual (User-Eingabe)
    "manual:form": SourcePriority.MANUAL,
    "manual:csv_import": SourcePriority.MANUAL,

    # External Authoritative — 11 Cloud-Provider aus services/cloud_import/
    # Apply-Pfad: routes/data_import.py → routes/import_export/helpers.py
    # _upsert_investition_monatsdaten. P2 stellt diesen Helper auf
    # write_with_provenance() um.
    "external:cloud_import:anker_solix":         SourcePriority.EXTERNAL_AUTHORITATIVE,
    "external:cloud_import:deye_solarman":       SourcePriority.EXTERNAL_AUTHORITATIVE,
    "external:cloud_import:ecoflow_powerocean":  SourcePriority.EXTERNAL_AUTHORITATIVE,
    "external:cloud_import:ecoflow_powerstream": SourcePriority.EXTERNAL_AUTHORITATIVE,
    "external:cloud_import:fronius_solarweb":    SourcePriority.EXTERNAL_AUTHORITATIVE,
    "external:cloud_import:growatt":             SourcePriority.EXTERNAL_AUTHORITATIVE,
    "external:cloud_import:hoymiles_smiles":     SourcePriority.EXTERNAL_AUTHORITATIVE,
    "external:cloud_import:huawei_fusionsolar":  SourcePriority.EXTERNAL_AUTHORITATIVE,
    "external:cloud_import:solaredge":           SourcePriority.EXTERNAL_AUTHORITATIVE,
    "external:cloud_import:sungrow_isolarcloud": SourcePriority.EXTERNAL_AUTHORITATIVE,
    "external:cloud_import:viessmann_gridbox":   SourcePriority.EXTERNAL_AUTHORITATIVE,

    # External Authoritative — HA-Statistics-LTS-Backfill
    # (services/ha_statistics_service.py + routes/ha_statistics.py)
    "external:ha_statistics": SourcePriority.EXTERNAL_AUTHORITATIVE,

    # Auto-Aggregation — Monatsabschluss-Roll-up aus Tageswerten
    # (routes/monatsabschluss.py — wird in P3 in Service-Schicht ausgelagert)
    "auto:monatsabschluss":  SourcePriority.AUTO_AGGREGATION,

    # Fallback — Sensor-Snapshot-Aggregator + MQTT-Inbound-Pfad
    "fallback:sensor_snapshot": SourcePriority.FALLBACK,
    "fallback:mqtt_inbound":    SourcePriority.FALLBACK,
}

# Päckchen 2 erweitert dieses Dict um manual:json_backup, manual:csv_backup
# (beide MANUAL) und auto:demo_data (AUTO_AGGREGATION) — vgl. Konzept Sektion 6.3.


def get_priority(source: str) -> SourcePriority:
    """Liefert die Priorität für ein Source-Label.

    Wirft `KeyError`, wenn das Label nicht im Vokabular steht — Schreib-Pfade,
    die ein neues Label brauchen, müssen es hier eintragen, sonst gibt's keine
    stille Akzeptanz.
    """
    return SOURCE_LABELS[source]
