# eedc Mobile-Konzept (Konzept-Skelett)

> **Status:** Wachsendes Konzept-Dokument, **eigene Timeline** parallel zu [`docs/KONZEPT-STYLE-GUIDE.md`](KONZEPT-STYLE-GUIDE.md). Skelett liegt vor; Umsetzungs-Wellen folgen, wenn Stakeholder-Bedarf konkret wird.
>
> **Eingangsperspektive:** eedc ist primär datendichte Desktop-App. Mobile-Erfahrung wird hier **konzeptionell eigenständig** gedacht — nicht als Responsive-Beilage in jedem Style-Guide-Bereich. Companion-App-Touchpoints (HA-Mobile-App) sind die wichtigste Anwender-Realität.
>
> **Aktuelle Stakeholder-Lage:** dünn. Rainer (rapahl) hat sich von Mobile-Nutzung zurückgezogen (siehe #243 B5-Absenkung). detLAN (#203) bleibt aktiver Mobile-Beobachter. Weitere Mobile-Bedarfsmeldungen werden als Beschleuniger gewertet.

---

## Methodik

- **Wachsend** wie das Style-Guide-Dokument: pro Welle 1–2 Bereiche.
- **Stakeholder-Trigger:** Umsetzungs-Welle für einen Bereich startet, wenn ≥ 2 Anwender konkrete Bedarfsmeldungen mit reproduzierbarem Setup liefern. Memory `feedback_smoketest_braucht_release.md` mahnt: Mobile-Test ohne lokales Setup ist Tester-Roulette, deshalb keine Big-Bang-Wellen.
- **Pro Bereich:** Designentscheidung, Pattern-Beispiel (Code/Mockup), Verlinkung auf entsprechende Style-Guide-Sektion.

---

## Bereiche

### M1 — Reduce-Logik (welche Sektionen kollabieren/verschwinden)

> **Mechanik:** `<CollapsibleSection>` mit neuem `defaultOpenMobile={false}`-Prop für datenreiche Sektionen, plus `<HideOnMobile>`-Wrapper für Sektionen die auf Mobile komplett ausgeblendet werden.
> **Designregel (Konzept-Vorschlag):** Cockpit-Übersicht + Wichtigste KPIs „immer offen". Detail-Stunden, Prognosen-Spalten, Lernfaktor-Vergleich kollabiert oder versteckt.
> **Konkrete Pro-Seite-Tabelle** wird beim Umsetzungs-Start gepflegt.
>
> Bezug: [Style-Guide B6 Aufklapp-Verhalten](KONZEPT-STYLE-GUIDE.md#b6--aufklapp-verhalten-collapsiblesection).

**Datenpunkte:** #243 B5c, #204 (Rainer-Simple-Swipe-Card-Wunsch), #203 (detLAN Mobile-Bildlaufleisten).

---

### M2 — Sticky-Header + Scroll-Verhalten

> **Designentscheidung:** Sticky-Header auf Mobile **verschiebbar** statt fixiert am Viewport. Damit verschwindet er beim Scrollen nach unten und kommt beim Scrollen nach oben zurück (Stichwort: „auto-hide on scroll down").
> **HA-Companion-Bar** auf Mobile entfallen lassen (~48 px Gewinn; Swipe-from-left holt sie ohnehin).
> **Floating-Selektoren** dürfen Mobile-Bildschirm nicht zusätzlich blockieren — falls Konflikt: Selektor wird auf Mobile zur Klapp-Schublade.
>
> Bezug: [Style-Guide B5 Selektoren](KONZEPT-STYLE-GUIDE.md#b5--selektoren).

**Datenpunkte:** #243 B5a+B5b, #203.

---

### M3 — Tabellen-Swipe-Pattern

> **Designentscheidung:** Tabellen mit `overflow-x: auto` bekommen einen Swipe-Hinweis (kleines „←→"-Indikator), Scrollbar selber ausgeblendet. Touch-Swipe ist primäre Interaktion.
> **Audit aller `<Table>`-Verwendungen** als Umsetzungs-Phase.
>
> Bezug: [Style-Guide B2 Tabellen + Listen](KONZEPT-STYLE-GUIDE.md#b2--tabellen--listen).

**Datenpunkte:** #243 B5d, #203.

---

### M4 — Touch-Targets + Mindestabstände

> **Konvention:** Klickbare Elemente ≥ 44×44 px (Apple-/Google-Standard). Listen-Items mit ausreichend Padding für Daumen-Touch.
> **Tap-Konflikte:** keine überlappenden klickbaren Bereiche (z. B. Sektion-Header + Aufklapp-Chevron sollen als ein Touch-Target zählen).

**Datenpunkte:** *(noch keine direkten)*

---

### M5 — Companion-App-Spezifika (iframe-Context)

> **Bekannte Quirks** aus iOS Safari + HA Companion-App (intern festgehalten):
> - `h-dvh` statt `h-screen` (dynamic viewport, hat Toolbar-Berücksichtigung)
> - `lib/download.ts:downloadFile()` statt `window.open` (Companion blockiert neue Fenster)
> - `overscroll-contain` auf Sticky-Container
> - `position: sticky` in `iframe` mit `overflow:auto` ist tricky — Workaround pro Fall
>
> Bezug: keine eigene Style-Guide-Sektion — gilt querschnittlich.

**Datenpunkte:** bestehende interne Linie aus früheren iOS-Tests.

---

### M6 — Card-Stil-Anlehnung (Beobachtung, kein Designauftrag)

> Simple-Swipe-Card-Format (Rainer #204-Screenshot) als möglicher Wunschstil für die wichtigsten Mobile-Kacheln. **Stakeholder-Druck heute dünn** (Rainer Mobile raus). Bleibt als Datenpunkt in Beobachtung, kein Designauftrag.

**Datenpunkte:** #204.

---

## Querverweise

- **Desktop-Style-Guide** → [`docs/KONZEPT-STYLE-GUIDE.md`](KONZEPT-STYLE-GUIDE.md)
- **Bekannte iOS/Companion-Stolperstellen** sind im Code bereits punktuell adressiert; eine systematische Sammlung folgt mit erster Umsetzungs-Welle.
- **Konzept-Issue #243** mit Bausteinen B5a–B5e als Sub-Tracker.
