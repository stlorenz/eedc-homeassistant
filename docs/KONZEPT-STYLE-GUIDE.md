# eedc Style-Guide v4.0.0 (Konzept-Skelett)

> **Status:** Wachsendes Konzept-Dokument. Wird pro Umsetzungs-Welle abschnittsweise befüllt — nicht im Voraus fertigschreiben.
>
> **Eingangsperspektive:** Maintainer-konzipiert mit eigenen Designstandards. Anwender-Feedback aus Forum und Issues fließt als **Datenpunkt** ein, ist aber nicht der einzige Treiber. Jede Regel hat eine bewusste Designentscheidung dahinter, kein Aggregat einzelner Bug-/UX-Reports.
>
> **Ziel:** Konsistente, dokumentierte UI-Sprache für eedc. Marken-Wert für v4.0.0: „strukturell sauber + konsistent".
>
> **Mobile-Verhalten** wird in einem **eigenen Konzept-Dokument** behandelt: [`docs/KONZEPT-MOBILE.md`](KONZEPT-MOBILE.md). Bei Bereichen mit Mobile-Bezug Querverweis statt Inline-Lösung.

---

## Methodik

- **Wachsend statt Big-Bang.** Pro Umsetzungs-Welle (typisch 1–2 Bereiche) werden die zugehörigen Abschnitte hier mit-geschrieben — fertige Regel + Vorher/Nachher-Screenshot aus dem ausgelieferten Code.
- **Tester-Beobachtungen** (Issues, Forum-Posts) sind **Datenpunkte**. Pro Punkt bewusst entscheiden: übernehmen (weil zu unserer Linie passt) oder explizit anders (mit dokumentierter Begründung).
- **Eigene Themen einplanen**, die nicht aus Tester-Backlog kommen — siehe Teil A.
- Querverweise auf Memory-Linien (intern), nicht im Dokument.

---

## Teil A — Visuelle Sprache (Querschnitt)

Diese Abschnitte definieren das gemeinsame Fundament, auf dem alle Komponenten in Teil B aufsetzen.

### A1 — Typografie-System

> **Skala (semantisch, nicht Pixel):** Display · Title-XL · Title-L · Title-M · Title-S · Body-L · Body-M · Body-S · Caption.
> Tokens statt ad-hoc Tailwind-Klassen. Schriftfamilie, Line-Heights, Letter-Spacing pro Token.

*Konkrete Tabelle folgt mit erster Umsetzungs-Welle.*

**Betroffene Issues (Datenpunkte):** #258 P4 (Textgestaltung-Unruhe), #256 (Schriftgrößen-Inkonsistenz).

---

### A2 — Farb-Palette + semantische Farb-Codes

> **Semantik:** Datentyp → Farbe. PV/Energie = gelb, Kosten = rot/orange, Umwelt = grün, Verbrauch = blau, Speicher = lila. Status-Farben (OK/Warning/Error/Info) getrennt.
> Dunkel- vs. Hell-Mode mit eigener Linien-Logik (Kontrast, Schatten, Saturation).

*Konkrete Farbliste folgt.*

**Betroffene Issues:** *(noch keine direkten)*

---

### A3 — Datenzustand-Vokabular

> **Unterscheidung:** `—` (echte Datenlücke) · *N/A* (strukturell nicht zutreffend, z. B. Komponente nicht vorhanden) · `…` (in Berechnung) · `?` (unsicher / Schätzung).
> Display-Token `—` bereits etabliert (v3.29.1 #239). Andere Zustände noch nicht systematisch.

**Betroffene Issues:** Disc #162 (`fmtKpi`-Helfer + Datenloch vs. strukturell N/A).

---

### A4 — Animation + Übergänge

> **Animiert:** Wert-Änderungen (Zahlen-Tween), Hover-Highlights, State-Toggles.
> **Statisch:** Layout-Wechsel, Modal-Inhalt-Wechsel, Tab-Wechsel.
> **Dauer-Konvention:** 150 ms (Mikro), 300 ms (Standard), 500 ms+ (Hervorhebung). Easing `ease-out` Standard.

*Konkrete Animation-Tokens folgen.*

**Betroffene Issues:** *(noch keine direkten)*

---

### A5 — Icons + Symbol-Konventionen

> **Linien-Icons:** `lucide-react` als SoT.
> **Komponenten-Typ-Icons:** via `lib/komponentenStyle.ts` (Memory: noch unvollständig — WP/Speicher ja, E-Auto/BKW/Wallbox/Sonstiges/PV-Anlage offen, Disc #163).
> **Status-Icons:** konsistent (Check/Warning/Error/Info).
> **Dekorative Icons** in Headern/Bannern vermeiden (Forum #206 P2-Linie).

**Betroffene Issues:** #210 (Komponenten-Icons in Finanzen), #258 P3 (Box-Icon-Position), #244 (Cockpit-Banner-Icon).

---

## Teil B — Komponenten

### B1 — KPI-Karten

> **Layout:** Titel oben · Wert (groß) zentral · Einheit (klein) rechts vom Wert · optional Icon dezent unten/Hintergrund · optional Subtitle/Berechnung-Tooltip.
> **Einheits-Position einheitlich:** entweder rechts vom Wert ODER eigene Zeile darunter — nicht gemischt (#258 P1).
> **Inhalts-Ausrichtung horizontal:** Werte aller Karten einer Reihe auf gleicher Baseline (#258 P2).
> **Icon-Position:** alle Karten einer Sektion gleich, oder konsistent „ohne Icon" (#258 P3).
>
> **SoT-Komponente** statt drei parallelen Implementierungen (Memory: B9 KPICard-Konsolidierung als Pflicht-Item).

**Vorbedingung:** Konsolidierung der drei aktuellen `KPICard`-Komponenten (B9 in #243).
**Betroffene Issues:** #243 B9, #247 P1, #258 P1+P2+P3.

---

### B2 — Tabellen + Listen

> **Spalten-Header:** Stil-Konvention folgt.
> **Sortierung:** `INVESTITION_TYP_ORDER` aus `lib/constants.ts` als SoT (etabliert v3.27.1, in v3.29.2 weiter ausgerollt). Suffix-Typen-Sortierung über Präfix-Match.
> **Leerwert-Darstellung:** `—` aus A3.
> **Einheits-Anzeige:** Spalten-Header mit Einheit (z. B. „Strom (kWh)"), nicht pro Zelle (#237).

**Betroffene Issues:** #243 B8, #210, #237.

---

### B3 — Navigation

> **Hauptnav:** horizontale Reihe, definierte Reihenfolge. Reorganisation offen (#243 B2).
> **Sub-Nav:** **Unterstrich + Icons** (`SubTabs.tsx`) als Standard. `PillTabs.tsx` wird deprecated und in den 3 letzten Verwendern (Aussichten, Auswertung, Community) migriert (#243 B1, detLAN-Klärung #216).
> **Sprungmarken** in langen Seiten (TOC-Pattern). *Offen.*

**Betroffene Issues:** #243 B1+B2, #208, #209, #216.

---

### B4 — Header + Banner

> **Cockpit-Banner:** kompakt, ~88 px, `flex items-center` mit `min-height`, vertikal zentriert (#243 B4).
> **PageHeader:** alle 39 Seiten mit hardcoded `<h1>` auf `<PageHeader>` migrieren (#243 B10). Show/Hide-Default pro Seite definieren: Hide wenn `<h1>`-Text = aktives Tab-Label, sonst Show.
> **Keine dekorativen Icons** vor Selektoren in Top-Bars (#206 P2-Linie, z. B. Calendar-Icon in v3.29.2 entfernt).

**Betroffene Issues:** #243 B4+B10, #196, #206 P2, #244.

---

### B5 — Selektoren

> **Schwebend** auf langen Scroll-Seiten (Sticky `top: 0` mit Backdrop-Blur). Reusable `<FloatingSelector>` (#243 B3).
> **Single-Anlage-Selektor:** ausblenden wenn ohne Auswahl-Sinn (#243 B12 — Audit).
> Mobile-Sticky-Verhalten in [KONZEPT-MOBILE.md M2](KONZEPT-MOBILE.md).

**Betroffene Issues:** #243 B3+B12, #206 P3, #208 P2+P6.

---

### B6 — Aufklapp-Verhalten (`CollapsibleSection`)

> **Persistenz:** Aufklapp-Status pro Sektion in LocalStorage (etabliert für Monatsberichte/Energieprofil-Monat — Vorbild laut detLAN #258 P5). Konsistente Implementierung über alle Verwender.
> **Default-Open** pro Sektion definieren (datenreich → standardmäßig offen; sekundär → standardmäßig zu).
> **Mobile-Default** abweichend siehe [KONZEPT-MOBILE.md M1](KONZEPT-MOBILE.md).

**Betroffene Issues:** #258 P5, #148.

---

## Teil C — Layout + Texte

### C1 — Spacing-Standards

> **Tokens:** `--page-padding-top` · `--nav-content-gap` · `--section-spacing` · `--card-padding` · `--card-gap`.
> SoT: `lib/spacing.ts` (oder Tailwind-Custom-Theme).
> Bestehende Spacings im Code auditieren und auf Tokens migrieren.

**Betroffene Issues:** #243 B6, #209 P5.

---

### C2 — Schreibweisen + Zahlen-Format

> **Marken-Schreibung:** „eedc" lower-case in Anwendertexten (etabliert v3.29.2). „EEDC" nur in Code-Identifiern (`EEDC_Prognose`-Formel, Env-Vars). Marken-Style-Guide folgt.
> **`%`-Zeichen:** mit Leerzeichen vor `%` (deutsche Konvention, z. B. „84,2 %") (#258 P6 — Drift heute).
> **Datums-Format:** TT.MM.JJJJ in Listen; „Mai 2026" in Headern.
> **Zahlen-Format:** deutsches Komma, Tausender-Punkt.
> **Display-Token `—`** als einheitliches Leerwert-Zeichen (etabliert v3.29.1).

**Betroffene Issues:** #243 B7, #258 P6.

---

## Querverweise

- **Mobile-Konzept** → [`docs/KONZEPT-MOBILE.md`](KONZEPT-MOBILE.md)
- **Aggregations- und Berechnungs-Themen** → [`docs/BERECHNUNGEN.md`](BERECHNUNGEN.md)
- **Sensor-Themen** → [`docs/SENSOR-REFERENZ.md`](SENSOR-REFERENZ.md)
- **Architektur-Überblick** → [`docs/ARCHITEKTUR.md`](ARCHITEKTUR.md)
- **Konzept-Issue mit Sub-Trackern** → [#243](https://github.com/supernova1963/eedc-homeassistant/issues/243)
