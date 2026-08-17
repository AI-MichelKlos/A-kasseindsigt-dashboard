# A-kasseindsigt

A-kasseorienteret dashboard for Danske A-kasser.

Forsiden har en hovedvaelger for a-kasse og en valgfri benchmark. Raad medlemstal vises som KPI, mens sammenligninger mellem a-kasser saa vidt muligt bruger indeks, procenter eller rater.

## Officielle kilder

- DST AUA01: forsikringsaktive efter a-kasse, alder og koen.
- DST AUP03: fuldtidsledige i pct. af samtlige forsikrede efter a-kasse.
- Jobindsats.dk / STAR: a-dagpenge, dimittendledighed, langtidsledighed, opbrugt dagpengeret, forbrug af dagpengeperioden, overlevelseskurver, arbejdsmarkedsstatus efter afsluttet forloeb, tidlig samtaleindsats og raadighedssanktioner.

De centrale Jobindsats-tabeller findes via API v3-metadata, mens verificerede specialtabeller kan have faste tabel-id'er. Hver Jobindsats-maaling har selvstaendig status i datafilen.

## Navnestandard

`config/a-kasse-navne.json` er navnebroen mellem Danske A-kassers foretrukne visningsnavne og navnene hos DST, Jobindsats.dk og STAR. Dashboardet viser DAK-navnet og DAK-forkortelsen. Kildenavnene bruges kun til datamatching. Tabellen er opgjort april 2026 og bygger paa DAKs interne ark med a-kassenavne og forkortelser.

Hvis en aktiv a-kasse ikke kan matches til navnestandarden, fejler valideringen i stedet for at publicere et ukendt eller forkert navn.

## Drift

GitHub Actions koerer paa hverdage med flere backup-forsoeg og gemmer hoejst en succesfuld opdatering pr. dansk dato. Data gemmes i `data/dashboard-data.json` og driftsspor i `status/last-run.txt`.

Jobindsats kraever repository-secret `API_ADGANG`. Secretet eksponeres kun til workflowet som `JOBINDSATS_API_TOKEN` og maa ikke ligge i kode eller datafiler.

GitHub Pages publicerer fra `main` og repository-root. `.nojekyll` er medtaget, fordi dashboardet er ren statisk HTML.

## Besoegstaeller

Forsiden indeholder GoatCounter for `akassesiden.goatcounter.com` efter aftale.

## Rådighedssanktioner

Sektion 7 henter Jobindsats.dk-tabellen `y01h01` (Antal rådighedssanktioner) kvartalsvist. Dashboardet viser samlet antal, andel sanktionerede ledige, sanktionstype og gennemsnitligt antal sanktioner pr. sanktioneret ledig. Historikken starter i 2019, og der markeres databrud fra 1. kvt. 2021.