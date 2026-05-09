# Konzept: Daten-Pipeline & Reparatur-Architektur (Etappe 3d)

> **Status:** Konzept-Phase, Aufräum-Sprint Phase C (2026-05-09).
> **Voraussetzung Implementierung:** Etappe 3c abgeschlossen (Detail-Konzept: [`KONZEPT-ENERGIEPROFIL-3C.md`](KONZEPT-ENERGIEPROFIL-3C.md) — Slot-Konvention an [#144](https://github.com/supernova1963/eedc-homeassistant/issues/144) angleichen + `quelle`-Marker auf `sensor_snapshots` als Schema-Vorlage).
> **Ziel:** Provenance, Konflikt-Resolver, Reparatur-Orchestrator, Idempotenz und Aufräumen der Monster-Module der gesamten Aggregat-Daten-Schicht.

Vier Architektur-Entscheidungen tragen dieses Konzept:

- **Hierarchie der Schreib-Quellen ist hartcoded** in `source_priority.py` — kein Quellen-Picker pro Anlage. (Quellenwahl im UI-Sinne ist Sache von [`KONZEPT-PROGNOSEQUELLEN-WAHL.md`](KONZEPT-PROGNOSEQUELLEN-WAHL.md), anderer Scope.)
- **Provenance lebt hybrid:** `source_provenance` JSON-Spalte pro Aggregat-Tabelle für Live-Resolution + Append-Only `data_provenance_log` für historische Diagnose.
- **Konflikt-Resolver hybrid:** synchroner Hierarchie-Check beim Schreiben (verhindert stilles Überschreiben) + asynchrone Daten-Checker-Sichtbarkeit für Doppel-Schreiber.
- **Reparatur über Orchestrator** mit Plan + Execute (Vorschau-Pflicht analog Vollbackfill-Pattern aus #190).

Implementierung sequenziell **nach** Etappe 3c, kein Quick-Win-Vorziehen. Refactoring der Monster-Module ist Querschnitt pro Päckchen, kein eigener Vor-Sprint.

## 1. Ist-Inventur

> Best-Effort-Übersicht für die Konzept-Phase. **Vollständige Re-Inventur** ist Teil von Päckchen 1 vor der eigentlichen Implementierung — die Tabellen hier sollen die Größenordnung greifbar machen, nicht jedes Detail erschöpfen.

### 1.1 Eingabe-Pfade (Schreiber auf Aggregat-Tabellen)

| # | Pfad | Code-Stelle | Ziel-Tabelle(n) | Schreib-Modus heute |
|---|---|---|---|---|
| 1 | Manual-Form Monatsdaten | `routes/monatsdaten.py:398/508/558` | `monatsdaten`, `investition_monatsdaten` | INSERT/UPDATE/DELETE per ID |
| 2 | Auto-Aggregation Monatsabschluss | `routes/monatsabschluss.py` (Logik in der Route) | `monatsdaten` | UPDATE-or-INSERT, kein Konflikt-Check |
| 3 | CSV-Import (eigene Datei) | `routes/custom_import.py:757` (`/apply`) | `monatsdaten`, `investition_monatsdaten` | Read-then-Update-or-Insert via `_upsert_investition_monatsdaten` — durch UNIQUE-Constraint + User-Dialog „Überschreiben?" idempotent. **Hierarchie-Verletzung möglich**: bei `ueberschreiben=true` werden manuelle Werte mit CSV-Werten überschrieben (Risiko #2). |
| 4–13 | Cloud-Import × 10 | `services/cloud_import/{solaredge,fronius,growatt,hoymiles,huawei,ecoflow_powerstream,ecoflow_powerocean,anker_solix,deye_solarman,sungrow_isolarcloud,viessmann_gridbox}.py` | `investition_monatsdaten` | Apply-Pfad geht über `data_import.py` — durch UNIQUE-Constraint + Skip-/Merge-Logik idempotent. **Hierarchie-Verletzung möglich**: bei `ueberschreiben=true` wie bei CSV (Risiko #2). |
| 14 | HA-Statistics-Import | `services/ha_statistics_service.py` + `routes/ha_statistics.py` + `routes/ha_import.py` | `tages_zusammenfassung`, `tages_energie_profil` | Backfill-Logik mit eigenen Annahmen |
| 15 | Connector (HA-Sensor → Live) | `routes/connector.py` + `services/sensor_snapshot_service.py` | `sensor_snapshots`, `tages_energie_profil` | INSERT-or-UPDATE pro Slot |
| 16 | MQTT-Inbound (Standalone-Pfad und HA-Lücken-Fallback) | `services/mqtt_inbound_service.py` + `services/mqtt_energy_history_service.py` | `mqtt_energy_snapshots`, `tages_energie_profil` | Fallback-Pfad zu (15) |
| 17 | Solcast-Service | `services/solcast_service.py` | `tages_zusammenfassung.solcast_prognose_kwh` + `_p10/_p90` | UPDATE pro Tag — gleiches Feld auch via HA-Sensor-Pfad in `live_wetter` (Risiko #3) |
| 18 | Kraftstoffpreis-Service | `services/kraftstoff_preis_service.py` | `tages_zusammenfassung.kraftstoffpreis_*`, `monatsdaten.kraftstoffpreis_*` | EU Oil Bulletin-Sammlung + Backfill |

→ **Größenordnung: ~17 distinct Schreiber** auf 5 zentrale Aggregat-Tabellen.

### 1.2 Reparatur-Pfade (heute verteilt)

| Endpoint | Operation | Quelle |
|---|---|---|
| `POST /api/energie-profil/reaggregate-heute` | Heutigen Tag aus Snapshots neu zusammenrechnen | `routes/energie_profil.py:1008` |
| `GET /api/energie-profil/{anlage_id}/reaggregate-tag/preview` | Vorschau Tages-Reaggregation | `routes/energie_profil.py:1047` |
| `POST /api/energie-profil/{anlage_id}/reaggregate-tag` | Tag neu aus Snapshots aggregieren (idempotent additiv, #190) | `routes/energie_profil.py:1121` |
| `POST /api/energie-profil/{anlage_id}/vollbackfill` | Komplette Historie aus HA-Statistics neu aufbauen — additiv | `routes/energie_profil.py:1230` |
| `POST /api/energie-profil/{anlage_id}/kraftstoffpreis-backfill[/tages\|/monats]` | Kraftstoffpreis-Werte rückwirkend einsetzen | `routes/energie_profil.py:1340/1365/1390` |
| `DELETE /api/monatsdaten/{id}` | Manueller Datensatz-Delete | `routes/monatsdaten.py:558` |
| `DELETE /api/cloud-import/anlage/{id}` (sinngemäß) | Cloud-Import-Daten zurücksetzen | `routes/cloud_import.py` |
| Datenverwaltung-Backup-Restore | Anlage-Backup einspielen | `routes/data_import.py` + Frontend |

→ **Verteilte Reparatur-Logik:** ~7 Endpoints im Energieprofil-Bereich + Lösch-/Restore-Pfade in mind. 3 weiteren Modulen, **keine zentrale Plan-/Vorschau-Schicht**.

### 1.3 Aggregat-Tabellen-Übersicht (Schreib-Fan-In)

| Tabelle | Heutige Schreiber | Konflikt-Potenzial |
|---|---|---|
| `monatsdaten` | Manual-Form, Auto-Aggregation, CSV-Import | **Hoch** (Risiko #1: Manual ↔ Auto, Risiko #2: Manual ↔ Cloud/CSV) |
| `investition_monatsdaten` | Manual-Form, CSV-Import, 10× Cloud-Importer | **Hoch** (Risiko #2: Manual ↔ Cloud/CSV-Override). Doppel-Klick-Schutz ist durch UNIQUE-Constraint + Skip-/Merge-Logik bereits gegeben. |
| `tages_zusammenfassung` | HA-Stats-Import, Solcast-Service, `live_wetter`, Kraftstoffpreis-Service | **Hoch** (Risiko #3) |
| `tages_energie_profil` | Connector + Snapshot-Service, MQTT-Inbound, HA-Stats-Backfill, Reaggregate-Endpoints | **Hoch** (Risiko #4 + Etappe-3c-Themen) |
| `sensor_snapshots` | Connector | Niedrig — eindeutiger Schreiber, Etappe 3c ergänzt Source-Marker |

### 1.4 Modul-Größen-Audit (Monster-PYs)

| Datei | Zeilen | Verantwortlichkeiten heute (vermischt) |
|---|---:|---|
| `routes/energie_profil.py` | 1741 | Read-Endpoints + Repair-Endpoints (reaggregate, vollbackfill, kraftstoffpreis-backfill) + Diagnose |
| `services/energie_profil_service.py` | 1621 | Tag-Aggregation aus Snapshots + HA-Stats-Backfill + Read-Helper + Reaggregator + Diagnose |
| `services/sensor_snapshot_service.py` | 1530 | Snapshot-Schreiben + HA-zu-MQTT-Fallback-Logik + Hourly-Aggregation + Reaggregate-Tag + Backfill aus HA-Stats |
| `routes/monatsabschluss.py` | 1092 | Wizard-Steps + Read-Endpoints + Auto-Aggregations-Logik (gehört in Service-Schicht) |
| `routes/custom_import.py` | 1046 | Analyze + Preview + Apply + Template-CRUD + DB-Schreib-Pfad |
| `services/solcast_service.py` | 593 | API-Fetch + Cache + DB-Write + Stundenprofil + Kalibrierung |

Diese Module sind **direkt betroffen** von 3d — Provenance-Helper, Provenance-Wrapper für Cloud-/CSV-Import und Orchestrator-Wrapping müssen hier integriert werden. Integration in Files mit > 1000 Zeilen ist praktisch nicht testbar und produziert Konflikt-Reibung. Refactoring ist daher nicht „nice to have", sondern Voraussetzung jedes betroffenen Päckchens (siehe Sektion 7 + Roadmap-Tails).

## 2. Die vier strukturellen Drift-Risiken

| # | Befund | Akute Folge | Code-Stelle | Päckchen |
|---|---|---|---|---|
| 1 | **Manual-Eingabe vs. Auto-Aggregation** — `monatsdaten` wird sowohl von User-Form als auch von Auto-Roll-up beschrieben, keine Konflikt-Auflösung | Manuelle Korrektur kann stillschweigend von nächtlichem Auto-Job überschrieben werden | `routes/monatsdaten.py` + Monatsabschluss-Logik | 3 |
| 2 | **Cloud-/CSV-Import überschreibt manuelle Werte** — bei `ueberschreiben=true` im Wizard werden manuelle Werte mit Cloud-/CSV-Werten ersetzt, ohne Hierarchie-Check | Manuelle Korrektur geht beim nächsten Cloud-Sync verloren | `routes/data_import.py` + `routes/custom_import.py` + `_upsert_investition_monatsdaten` | 3 |
| 3 | **HA-Sensor + Solcast schreiben dasselbe Feld** — `tages_zusammenfassung.solcast_prognose_kwh` aus zwei Pfaden | Last-Writer-Wins ohne Hierarchie | `services/solcast_service.py` + `routes/live_wetter.py` | 6 |
| 4 | **Snapshot-Fallback unsichtbar** — `sensor_snapshot_service` wechselt zu MQTT wenn HA unvollständig, kein Source-Marker | Drift-Quelle bei späterer Diagnose nicht zuordenbar | `services/sensor_snapshot_service.py` | 5 |

**Wichtige Klarstellung:** Doppel-Klick-Schutz auf `investition_monatsdaten` und `monatsdaten` ist bereits gegeben — beide Tabellen haben UNIQUE-Constraints (`uq_inv_monatsdaten_periode`, `uq_monatsdaten_anlage_periode`), und der Apply-Pfad in `data_import.py:298–310` macht expliziten Skip-if-exists. Datenverdoppelung durch Doppel-Klick ist physisch unmöglich. Was die Risiken #1+#2 oben adressieren, ist **Hierarchie-Verletzung** beim absichtlichen Schreiben aus dem jeweiligen Pfad — kein Idempotenz-Problem.

Alle vier Risiken sind „still und lange unentdeckbar" — keines ist akut datenkorrumpierend, aber alle vier untergraben Vertrauen in die Daten über Zeit.

## 3. Quellen-Hierarchie & Provenance-Tracking

### 3.1 Hierarchie pro Feld

Fünf Stufen, niedrigere Zahl = höhere Priorität:

| Priorität | Source-Klasse | Beispiele | Begründung |
|---|---|---|---|
| 0 | `repair` | Repair-Orchestrator mit `force_override=True` | Korrektur-Lauf steht über allem — ein expliziter User-„Reset" muss jede Hierarchie durchbrechen können. Audit-Log-pflichtig mit Operation-ID. |
| 1 | `manual` | Monatsdaten-Form, Investitions-Form, CSV-Import-Wizard | User-Eingabe ist Wahrheit — niemals von Maschine überschreiben. CSV gleichauf, weil bewusst gewählter Klick-Pfad. |
| 2 | `external_authoritative` | Cloud-Portale (Solaredge/Fronius/...), HA-Statistics-LTS-Backfill | Maschinen-bestätigte Quelle, aber nicht User-bestätigt. Konflikt zwischen Cloud + HA-Stats: Last-Writer-Wins (selten, in Praxis eindeutiger Pfad pro Anlage). |
| 3 | `auto_aggregation` | Monatsabschluss-Roll-up aus Tageswerten, abgeleitete Berechnungen | Berechnet, Annahmen-behaftet. |
| 4 | `fallback` | Sensor-Snapshot Live-Aggregator, MQTT-Fallback bei HA-Lücken | Best-Effort, lückenanfällig. |

Last-Writer-Wins innerhalb einer Stufe ist akzeptiert (gleiche „Vertrauensklasse" → kein zwingender Tiebreaker nötig). Wer wirklich entscheiden muss, kann den Repair-Orchestrator (Stufe 0) gezielt einsetzen.

Definiert in neuem Modul `backend/core/source_priority.py` (analog `field_definitions.py`, `mqtt_topic_registry.py`):

```python
# backend/core/source_priority.py
from enum import IntEnum

class SourcePriority(IntEnum):
    REPAIR = 0
    MANUAL = 1
    EXTERNAL_AUTHORITATIVE = 2
    AUTO_AGGREGATION = 3
    FALLBACK = 4

SOURCE_LABELS: dict[str, SourcePriority] = {
    "repair": SourcePriority.REPAIR,                                # Repair-Orchestrator force_override
    "manual:form": SourcePriority.MANUAL,                           # Monatsdaten/Investitions-Form
    "manual:csv_import": SourcePriority.MANUAL,                     # CSV-Wizard
    "external:cloud_import:solaredge": SourcePriority.EXTERNAL_AUTHORITATIVE,
    "external:cloud_import:fronius":   SourcePriority.EXTERNAL_AUTHORITATIVE,
    # ... 10 Cloud-Provider
    "external:ha_statistics": SourcePriority.EXTERNAL_AUTHORITATIVE,
    "auto:monatsabschluss":  SourcePriority.AUTO_AGGREGATION,
    "fallback:sensor_snapshot": SourcePriority.FALLBACK,
    "fallback:mqtt_inbound":    SourcePriority.FALLBACK,
}
```

`repair` als eigene Stufe (statt nur `force_override=True`-Flag auf einer anderen Quelle) macht Korrektur-Läufe im Audit-Log auf den ersten Blick erkennbar — relevant für Diagnose-Frage „warum hat dieser Wert seine Provenance verloren?".

### 3.2 Inline-Provenance: `source_provenance`-Spalte

Neue JSON-Spalte in den 4 Aggregat-Tabellen (`monatsdaten`, `investition_monatsdaten`, `tages_zusammenfassung`, `tages_energie_profil`):

```python
class Monatsdaten(Base):
    # ... bestehende Felder
    source_provenance = Column(JSON, nullable=False, default=dict)
    # Inhalt:
    # {
    #   "netzbezug_kwh":   {"source": "manual",
    #                        "writer": "user@email",
    #                        "at": "2026-05-09T10:33:00Z"},
    #   "pv_erzeugung_kwh": {"source": "auto_aggregation:monatsabschluss",
    #                        "writer": "monatsabschluss_service",
    #                        "at": "2026-05-08T03:00:00Z",
    #                        "input_hash": "sha256:..."}
    # }
```

Pro Feld: `source` (Label aus `SOURCE_LABELS`), `writer` (User-Email für `manual`, Service-Name für `auto`, Provider-Account-ID für Cloud), `at` (ISO-Timestamp), optional `input_hash` (für idempotente Sources, siehe Sektion 6).

### 3.3 Audit-Log: `data_provenance_log`

Neue Append-Only-Tabelle für historische Diagnose („wer hat im Februar mein Investitions-Monatsdatum überschrieben?"):

```sql
CREATE TABLE data_provenance_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    table_name TEXT NOT NULL,           -- "monatsdaten" | "investition_monatsdaten" | ...
    row_pk_json TEXT NOT NULL,          -- JSON: {"anlage_id": 1, "jahr": 2026, "monat": 4}
    field_name TEXT NOT NULL,
    source TEXT NOT NULL,
    writer TEXT NOT NULL,
    written_at TEXT NOT NULL,           -- ISO-Timestamp
    old_value TEXT,                     -- JSON-encoded (nullable für Initial-Insert)
    new_value TEXT,                     -- JSON-encoded
    input_hash TEXT,                    -- für idempotente Sources
    decision TEXT NOT NULL,             -- "applied" | "rejected_lower_priority" | "no_op_same_value"
    decision_reason TEXT
);

CREATE INDEX idx_provlog_lookup
    ON data_provenance_log (table_name, row_pk_json, written_at DESC);
CREATE INDEX idx_provlog_audit
    ON data_provenance_log (writer, written_at DESC);
```

**Append-only Garantie:** Keine UPDATE/DELETE-Pfade auf diese Tabelle, weder im Code noch via Migration. Eine spätere Retention-Policy (z. B. „älter als 24 Monate → archivieren") ist möglich, selektive Löschung nicht.

### 3.4 Zentraler Helper Pflicht

Pattern aus `feedback_aggregations_drift.md` und `mqtt_topic_registry.py`: ein einziger SoT-Helper, alle Schreiber gehen darüber.

```python
# backend/services/provenance.py

@dataclass
class WriteResult:
    applied: bool
    decision: Literal["applied", "rejected_lower_priority", "no_op_same_value"]
    reason: str
    conflicting_source: Optional[str] = None  # bei rejected_lower_priority

def write_with_provenance(
    db: Session,
    obj: Base,
    field: str,
    value: Any,
    source: str,
    writer: str,
    input_hash: Optional[str] = None,
    *,
    force_override: bool = False,  # nur für Repair-Orchestrator
) -> WriteResult:
    """
    Atomarer Write mit Hierarchie-Check + Audit-Log + JSON-Source-Update.

    - Liest aktuelle source_provenance[field] aus obj
    - Vergleicht via SOURCE_LABELS[new_source].priority vs. existing
    - Bei höherer oder gleicher Priorität: schreibt + Audit-Log "applied"
    - Bei niedrigerer Priorität: kein Schreiben + Audit-Log "rejected_lower_priority"
    - Bei identischem Wert + Hash: kein Schreiben + Audit-Log "no_op_same_value"
    - flag_modified(obj, "source_provenance") wegen JSON-Falle
    """
```

`force_override=True` ist allein dem Repair-Orchestrator (Sektion 5) vorbehalten und immer mit explizitem Audit-Log-Eintrag inklusive Operation-ID.

## 4. Konflikt-Resolver-Architektur

### 4.1 Synchroner Resolver im Write-Pfad

`provenance.write_with_provenance()` (Sektion 3.4) ist der Resolver. Konkret:

```
existing = obj.source_provenance.get(field)
if existing is None:
    → applied (Initial-Write, immer)
elif SOURCE_LABELS[new].priority < SOURCE_LABELS[existing.source].priority:
    → applied (höhere Priorität gewinnt — niedrigere Zahl ist höher)
elif SOURCE_LABELS[new].priority == SOURCE_LABELS[existing.source].priority:
    → applied (gleiche Source-Klasse, Last-Writer-Wins ist OK)
else:
    → rejected_lower_priority + Audit-Log + WriteResult(applied=False, ...)
```

**Folge:** Auto-Aggregation kann manuell gepflegte Werte nicht mehr überschreiben (Risiko #1 gelöst). Cloud-/CSV-Import kann manuell gepflegte Werte nicht überschreiben (Risiko #2 gelöst). Sensor-Snapshot kann nicht versehentlich Cloud-Werte verdrängen.

### 4.2 Asynchrone Sichtbarkeit: Daten-Checker `PROVENANCE_CONFLICT`

Neue Kategorie in `services/daten_checker.py`:

```python
def check_provenance_conflicts(db: Session, anlage_id: int, days: int = 30) -> list[Anomaly]:
    """
    Scannt data_provenance_log auf Felder mit ≥ 2 distinct sources im Zeitraum.
    Meldet pro Konflikt: Tabelle, Row-PK, Feld, Quellen, letzte Entscheidung.
    """
```

UI-Behandlung folgt `feedback_daten_checker_kein_akzeptiert.md`: **kein Quittier-Knopf**, nur Hinweis + Link zur Reparatur-Werkbank (Sektion 5). Konflikte verschwinden erst, wenn die strukturelle Ursache adressiert ist (Quelle deaktivieren / Hierarchie anpassen / Reparatur durchführen).

### 4.3 UI-Sichtbarkeit der Provenance pro Datensatz

Quellen-Badge pro Wert mit Hover-Tooltip („zuletzt geschrieben von X via Y am Z") in Monatsdaten-/Investitions-/Energieprofil-Detail-Ansichten. UX-Polish, kein Critical-Path — landet in Päckchen 7.

## 5. Reparatur-Orchestrator

### 5.1 Service-Schnitt

```python
# backend/services/repair_orchestrator.py

class RepairOperationType(str, Enum):
    REAGGREGATE_DAY = "reaggregate_day"
    REAGGREGATE_TODAY = "reaggregate_today"
    VOLLBACKFILL = "vollbackfill"
    KRAFTSTOFFPREIS_BACKFILL = "kraftstoffpreis_backfill"
    DELETE_MONATSDATEN = "delete_monatsdaten"
    RESET_CLOUD_IMPORT = "reset_cloud_import"
    SOLCAST_REWRITE = "solcast_rewrite"  # Risiko #3

class FieldDiff(BaseModel):
    table: str
    row_pk: dict
    field: str
    old_value: Any
    new_value: Any
    source_before: Optional[str]
    source_after: str
    decision: Literal["applied", "rejected_lower_priority", "no_op_same_value"]

class RepairPlan(BaseModel):
    plan_id: UUID
    anlage_id: int
    operation: RepairOperationType
    operation_params: dict
    created_at: datetime
    expires_at: datetime                # z. B. +1h
    estimated_changes: dict[str, int]
    diff_preview: list[FieldDiff]       # paginiert / capped (z. B. 200 Einträge)
    diff_total_count: int
    warnings: list[str]                 # z. B. "12 Felder werden Auto-Aggregation
                                        #        überschreiben — ist das gewollt?"

class RepairResult(BaseModel):
    plan_id: UUID
    executed_at: datetime
    actual_changes: dict[str, int]
    audit_log_ids: list[int]            # Verknüpfung in data_provenance_log

async def plan(req: RepairOperationRequest) -> RepairPlan: ...
async def execute(plan_id: UUID) -> RepairResult: ...
async def list_plans(anlage_id: int, limit: int = 20) -> list[RepairPlan]: ...
async def discard_plan(plan_id: UUID) -> None: ...
```

**Plan-Lebenszyklus:** in-memory + Lock (analog Snapshot-Cache). Expiry verhindert „Stale Plan trifft veränderten Datenbestand".

### 5.2 Bestehende Endpoints werden Wrapper

Backward-Kompat: alte Reparatur-Endpoints rufen intern Orchestrator auf, Frontend stellt schrittweise um.

| Alter Endpoint | Neuer Pfad |
|---|---|
| `POST /reaggregate-tag` | intern `plan()` + sofortiges `execute()` (kein Frontend-Break); parallel neue API `/repair/plan` + `/repair/execute/{plan_id}` für Plan-Vorschau |
| `POST /vollbackfill` | analog — alte Body-Parameter mappen 1:1 auf `RepairOperationRequest` |
| `POST /kraftstoffpreis-backfill[/tages\|/monats]` | analog |
| `POST /reaggregate-heute` | analog |
| `DELETE /monatsdaten/{id}` | bleibt direkt (kein Orchestrator-Bedarf für Single-Row-Delete), schreibt aber Audit-Log |
| `DELETE /cloud-import/anlage/{id}` | wird Orchestrator-Operation `RESET_CLOUD_IMPORT` (mit Vorschau!) |

### 5.3 Vereinheitlichte Reparatur-Werkbank im Frontend

Erweiterung der heutigen Datenverwaltung-Seite (`pages/Datenverwaltung.tsx`):

- **Operation-Auswahl** als Liste verfügbarer Reparaturen mit Kurzbeschreibung
- **Plan-Vorschau** als Tabelle der Field-Diffs, gruppiert nach Tabelle, mit Decision-Anzeige (`applied` / `rejected_lower_priority`)
- **Bestätigungs-Knopf** „Diese 47 Änderungen anwenden" statt heutigem Direkt-Klick
- **Verlauf** der letzten Reparaturen mit Verknüpfung zum Audit-Log

## 6. Cloud-/CSV-Import an Provenance anschließen

> **Korrektur gegenüber Übergabe-Notiz:** Die ursprünglich angenommene Idempotenz-Lücke existiert nicht — UNIQUE-Constraints und Skip-/Merge-Logik im Apply-Pfad sind schon da. Was bleibt zu tun, ist der Hierarchie-Anschluss (Risiko #2): Cloud-/CSV-Import muss `write_with_provenance()` verwenden, damit das `ueberschreiben=true`-Häkchen manuelle Werte nicht stillschweigend ersetzt.

### 6.1 Schema-Ergänzung

```sql
-- Optional, für Provenance-Drill-Down: erkennt ob ein Re-Import
-- denselben Datensatz nochmal liefert (ohne Wertänderung)
ALTER TABLE investition_monatsdaten ADD COLUMN source_hash TEXT;
ALTER TABLE monatsdaten ADD COLUMN source_hash TEXT;
```

UNIQUE-Constraints auf `(investition_id, jahr, monat)` und `(anlage_id, jahr, monat)` sind **bereits vorhanden** — kein Schema-Change nötig.

### 6.2 Gemeinsamer Provenance-Wrapper für Cloud + CSV

Heutiger `_upsert_investition_monatsdaten` in [`routes/import_export/helpers.py:60`](../eedc/backend/api/routes/import_export/helpers.py) wird zur Provenance-Variante umgebaut:

```python
# backend/services/import_writer.py (neu — gemeinsam für Cloud + CSV)

async def upsert_investition_monatsdaten_with_provenance(
    db: AsyncSession,
    *,
    investition_id: int,
    jahr: int,
    monat: int,
    payload: dict[str, Any],
    source: str,           # "external:cloud_import:solaredge" | "manual:csv_import" | ...
    writer: str,           # Account-ID / User-Email / Connector-Run-ID
    ueberschreiben: bool,  # Wizard-Flag — wirkt nur als zusätzliche Erlaubnis,
                           # ersetzt die Hierarchie nicht
) -> WriteResult:
    """
    1. Berechnet source_hash = sha256(canonical_json(payload))
    2. SELECT existing WHERE (investition_id, jahr, monat)
    3. Wenn existing.source_hash == source_hash → No-Op + Audit-Log("no_op_same_value")
    4. Sonst: für jedes Feld in payload → write_with_provenance()
       — Hierarchie blockiert Überschreiben manueller Werte trotz ueberschreiben=true
       — gleiche Source-Klasse + ueberschreiben=true: erlaubt
    5. existing.source_hash = source_hash, db.commit()
    """
```

**Verhalten gegenüber heute:**
- **Doppel-Klick mit unverändertem Payload:** war schon idempotent, ist jetzt zusätzlich im Audit-Log als „no_op_same_value" sichtbar.
- **`ueberschreiben=true` auf manuell gepflegtem Wert:** war bisher destruktiv, wird jetzt durch Hierarchie blockiert. User sieht in der Wizard-Antwort „X Felder durch manuelle Eingabe geschützt — Reset über Reparatur-Werkbank wenn gewollt".
- **`ueberschreiben=true` auf Cloud-/CSV-Wert (gleiche Source-Klasse):** erlaubt wie heute.

### 6.3 Migration der 10 Cloud-Importer + CSV-Importer

Cloud-Importer schreiben heute nicht direkt in die DB — sie liefern Daten an den Apply-Pfad in `data_import.py`, der `_upsert_investition_monatsdaten` ruft. Migration daher punktuell:

1. **`routes/import_export/helpers.py:_upsert_investition_monatsdaten`** auf Provenance-Wrapper umstellen
2. **`routes/data_import.py`** Skip-Logic für `monatsdaten` ebenfalls auf `write_with_provenance` umstellen
3. **`routes/custom_import.py`** (CSV) — gleicher Helper, Source-Tag `manual:csv_import`
4. Wizard-Texte anpassen: „X von Y Feldern durch manuelle Werte geschützt" als sichtbares Ergebnis

Die 10 Connector-Files in `services/cloud_import/*.py` selbst müssen nicht angefasst werden, weil sie nur Daten produzieren, nicht persistieren.

## 7. Modul-Refactoring (Monster-PYs zerlegen)

### 7.1 Pattern: Vertical Slicing nach Verantwortlichkeit

Jedes betroffene Monster-PY (Sektion 1.4) wird **vor** der Provenance-/Resolver-/Orchestrator-Integration in Verantwortlichkeits-Slices zerlegt. Pattern bewusst gleich für alle Files:

- **Routes** zerfallen in `views.py` (Read-only GET) + `repair.py` / `wizard.py` (Write-Endpoints) + `__init__.py` (Router-Aggregation).
- **Services** zerfallen in `<slice>.py` pro Verantwortlichkeit, mit `__init__.py` als Re-Export-Fassade — bestehende Importer im restlichen Code bleiben unverändert (`from services.energie_profil_service import X` funktioniert weiter).
- **Tests** ziehen mit, pro Slice eigenes `test_<slice>.py`.

Slice-Schnitte werden so gewählt, dass die Provenance-Integration danach **eine** Datei pro Aggregat-Schreibstelle anfasst, nicht mehrere parallel.

### 7.2 Zerlegungs-Plan pro Monster-PY

| Heute | Soll-Struktur | Zugeordnet zu |
|---|---|---|
| `routes/energie_profil.py` (1741) | `routes/energie_profil/views.py` (Read), `routes/energie_profil/repair.py` (alle Repair-Endpoints — wird in Päckchen 4 zu Orchestrator-Wrapper), `__init__.py` | Päckchen 4 |
| `services/energie_profil_service.py` (1621) | `services/energie_profil/aggregator.py` (Tag-Aggregation aus Snapshots), `services/energie_profil/backfill.py` (HA-Stats-Backfill), `services/energie_profil/reader.py` (Read-Helper), `services/energie_profil/reaggregator.py` (Reaggregate-Tag), `__init__.py` Re-Export | Päckchen 3 |
| `services/sensor_snapshot_service.py` (1530) | `services/snapshot/writer.py` (Snapshot-Schreiben pro Sensor), `services/snapshot/aggregator.py` (Snapshots → Hourly), `services/snapshot/fallback.py` (HA → MQTT-Fallback-Logik, **Source-Marker landet hier**), `services/snapshot/reaggregator.py`, `services/snapshot/backfill.py`, `__init__.py` | Päckchen 3 (Zerlegung), Päckchen 5 (Source-Marker integrieren) |
| `routes/monatsabschluss.py` (1092) | `routes/monatsabschluss/wizard.py` (Multi-Step), `routes/monatsabschluss/views.py` (Read), **plus** Auslagerung der Auto-Aggregations-Logik aus der Route nach `services/monatsabschluss_aggregator.py` (gehört nicht in einen Route-Layer) | Päckchen 3 |
| `routes/custom_import.py` (1046) | `routes/custom_import/analyze.py`, `routes/custom_import/preview.py`, `routes/custom_import/apply.py`, `routes/custom_import/templates.py`, **plus** Auslagerung des DB-Schreib-Pfads nach `services/import_writer.py` (gemeinsamer Provenance-Wrapper für Cloud + CSV, siehe Päckchen 2) | Päckchen 2 |
| `services/solcast_service.py` (593) | `services/solcast/api.py` (API-Fetch + Quota), `services/solcast/cache.py`, `services/solcast/writer.py` (DB-Write — landet in Päckchen 6 als alleiniger Schreiber), `services/solcast/kalibrierung.py` | Päckchen 6 |

### 7.3 Refactoring-Disziplin

- **Pro Päckchen:** Refactoring-PR landet **vor** der Architektur-PR (zwei distincte Commits oder zwei distincte PRs). Kein Vermischen.
- **Verhalten unverändert:** Refactoring-PR ist reines Verschieben + Re-Export, alle Tests grün, kein Verhaltens-Diff. CI-Smoke + manueller Round-Trip in HA-Add-on.
- **Keine spekulativen Slices:** ein Slice pro Verantwortlichkeit, die heute schon im File existiert. Nicht „könnte mal jemand brauchen". Memory-Linie `feedback_pfadabhaengigkeits_reflex.md` gilt auch hier.

## 8. Migrations-Roadmap

Reihenfolge: Etappe 3c zuerst abschließen, dann Etappe 3d in nummerierten Päckchen. Pro Päckchen: **Refactoring-Tail** zuerst (Sektion 7.2), dann Architektur-Integration.

### Päckchen 1 — Datenmodell-Fundament
**Voraussetzung:** Etappe 3c abgeschlossen.
- Lückenlose Re-Inventur aller Schreiber + Reparatur-Pfade (über die Best-Effort-Liste in Sektion 1 hinaus)
- Migration: `data_provenance_log`-Tabelle anlegen
- Migration: `source_provenance` JSON-Spalte in 4 Aggregat-Tabellen (`monatsdaten`, `investition_monatsdaten`, `tages_zusammenfassung`, `tages_energie_profil`)
- Migration: `source_hash` TEXT-Spalte in `monatsdaten` + `investition_monatsdaten`
- Modul `backend/core/source_priority.py` mit Hierarchie-Konstanten
- Modul `backend/services/provenance.py` mit `write_with_provenance()` + Unit-Tests
- **Refactoring-Tail:** keiner (nur neue Module).

→ **Akzeptanz:** Alle Tests grün, Schema migriert, Helper aufrufbar, kein Verhaltens-Diff.

### Päckchen 2 — Cloud-/CSV-Import an Provenance anschließen
- **Refactoring-Tail:** `routes/custom_import.py` zerlegen (Sektion 7.2).
- `source_hash`-Spalte in `investition_monatsdaten` + `monatsdaten` (für Provenance-Drill-Down, optional)
- `services/import_writer.py` als gemeinsamer Provenance-Wrapper (siehe 6.2)
- `_upsert_investition_monatsdaten` in `routes/import_export/helpers.py` auf Provenance-Wrapper umstellen
- CSV-Apply-Pfad (`routes/custom_import.py`) auf Provenance-Wrapper umstellen
- Wizard-Texte: „X von Y Feldern durch manuelle Werte geschützt" als sichtbares Ergebnis im Apply-Schritt
- Daten-Checker: optionaler `import_no_op_same_value`-Counter pro Anlage (Diagnose, ob Re-Imports etwas ändern)

→ **Akzeptanz:** `ueberschreiben=true` auf einem manuell gepflegten Feld lässt den manuellen Wert stehen + Wizard zeigt Schutz-Hinweis. Audit-Log dokumentiert die `rejected_lower_priority`-Entscheidung. UNIQUE-Constraint-Schutz aus dem Status quo bleibt unverändert wirksam.

### Päckchen 3 — Konflikt-Resolver aktivieren
- **Refactoring-Tail:** `services/energie_profil_service.py` + `services/sensor_snapshot_service.py` + `routes/monatsabschluss.py` zerlegen (Sektion 7.2). Auto-Aggregations-Logik aus der Monatsabschluss-Route in den neuen Service auslagern.
- `write_with_provenance()` in alle 4 Aggregat-Schreib-Pfade einsetzen:
  - Manual-Form (`routes/monatsdaten.py`)
  - Auto-Aggregation (`services/monatsabschluss_aggregator.py` neu)
  - HA-Stats-Import (`services/ha_statistics_service.py`)
  - Solcast-Service (Stub für Risiko #3, finale Auflösung in Päckchen 6)
- Daten-Checker: `PROVENANCE_CONFLICT`-Kategorie aktivieren
- Migration: bestehende Datenbestände bekommen Initial-`source_provenance` mit Konvention `"legacy:unknown"` (niedrigste Priorität)

→ **Akzeptanz:** Manuelle Korrektur überlebt nächtlichen Auto-Aggregations-Job. Daten-Checker meldet Doppel-Schreiber-Felder.

### Päckchen 4 — Reparatur-Orchestrator
- **Refactoring-Tail:** `routes/energie_profil.py` zerlegen (Sektion 7.2). Repair-Endpoints landen in `routes/energie_profil/repair.py`.
- `RepairOrchestrator`-Service mit Plan + Execute
- Bestehende Repair-Endpoints zu Wrapper umstellen (kein Frontend-Break)
- Neue Plan-API + Vorschau-API
- Frontend: zentrale Reparatur-Werkbank in Datenverwaltung
- Verlauf-Ansicht mit Audit-Log-Verknüpfung

→ **Akzeptanz:** Vor jeder Reparatur sieht User Diff-Vorschau. Verlauf zeigt mindestens letzte 20 Operationen.

### Päckchen 5 — Snapshot-Source-Marker (Risiko #4)
- **Refactoring-Tail:** keiner — `sensor_snapshot_service` ist bereits in Päckchen 3 zerlegt.
- `services/snapshot/fallback.py` schreibt Source-Marker `sensor_snapshot` vs. `mqtt_fallback` in `source_provenance`
- Daten-Checker zeigt Fallback-Quote pro Anlage und Zeitraum

→ **Akzeptanz:** Diagnose „Welche meiner Tagesprofile basieren auf MQTT-Fallback statt HA-Native?" ist beantwortbar.

### Päckchen 6 — Solcast-Doppel-Schreiber auflösen (Risiko #3)
- **Refactoring-Tail:** `services/solcast_service.py` zerlegen (Sektion 7.2).
- `tages_zusammenfassung.solcast_prognose_kwh` bekommt eindeutigen Schreiber via Resolver
- Entscheidung: gewinnt `services/solcast/writer.py` (geplanter Schreiber) immer, `routes/live_wetter.py`-Logging-Pfad wird stillgelegt — analog zum geplanten `sfml_prognose_kwh`-Cleanup aus dem Quellenwahl-Konzept
- Migration: bestehende Datenbestände bekommen Source-Tag

→ **Akzeptanz:** Nur ein Pfad schreibt in `solcast_prognose_kwh`; Audit-Log bestätigt.

### Päckchen 7 — Provenance-UI-Polish
- **Refactoring-Tail:** keiner (Frontend).
- Quellen-Badge in Monatsdaten-/Investitions-/Energieprofil-Detail-Views
- Hover-Tooltip mit Source + Writer + Timestamp
- Audit-Log-Drill-Down per Feld
- Optional: „Show all changes for this field"-Modal

→ **Akzeptanz:** User kann pro Wert einsehen, wer ihn zuletzt warum gesetzt hat.

## 9. Verhältnis zu anderen Konzepten

[`KONZEPT-ENERGIEPROFIL.md`](KONZEPT-ENERGIEPROFIL.md) Etappe 3c liefert Slot-Konvention + Source-Tracking auf `sensor_snapshots` als Schema-Vorlage; 3d generalisiert auf alle Aggregat-Tabellen. [`KONZEPT-PROGNOSEQUELLEN-WAHL.md`](KONZEPT-PROGNOSEQUELLEN-WAHL.md) ist Lese-Resolver pro Anlage über drei alternative Prognose-Quellen — disjunkt zum Schreib-Resolver hier, Berührungspunkt nur in Päckchen 6 (Solcast-Cleanup). [`KONZEPT-KORREKTURPROFIL.md`](KONZEPT-KORREKTURPROFIL.md), [`KONZEPT-LIVE-SNAPSHOT-5MIN.md`](KONZEPT-LIVE-SNAPSHOT-5MIN.md) und [`KONZEPT-MQTT-GATEWAY.md`](KONZEPT-MQTT-GATEWAY.md) sind unabhängig; MQTT-Gateway wird in Päckchen 5 lose berührt (Source-Marker `mqtt_fallback`).
