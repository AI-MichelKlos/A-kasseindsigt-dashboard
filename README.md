# A-kasseindsigt

A-kasseorienteret dashboard for Danske A-kasser.

Forsiden har en hovedvaelger for a-kasse og en valgfri benchmark. Raad medlemstal vises som KPI, mens sammenligninger mellem a-kasser saa vidt muligt bruger indeks, procenter eller rater.

## Officielle kilder

- DST AUA01: forsikringsaktive efter a-kasse, alder og koen.
- DST AUP03: fuldtidsledige i pct. af samtlige forsikrede efter a-kasse.
- Jobindsats.dk / STAR: a-dagpenge, dimittendledighed, langtidsledighed, opbrugt dagpengeret, forbrug af dagpengeperioden, overlevelseskurver, arbejdsmarkedsstatus efter afsluttet forloeb, samtaleformer i a-kassen, efterloen, efterloensbidragsbetalere og raadighedssanktioner.

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

## Forsidens brugeroplevelse

Forsiden har et aktuelt overblik med retningspile, sektionsnavigation, en mobilvenlig
filtermenu og mulighed for at vise eller hente data bag hver graf. Grafer uden for
skærmbilledet oprettes først, når brugeren nærmer sig den relevante sektion.

Den fulde RM01AK-fil bruges fortsat af resultatmålsiden. Forsiden henter i stedet
`data/rm01ak-summary.json`, der kun indeholder metadata, a-kasser, tidsserier og
populationstal. Den kompakte fil bygges automatisk sammen med `data/rm01ak.json`.

## Jobsøgning

Sektion 10 viser, hvor stor en andel af dagpengemodtagerne der har mindst én registreret jobansøgning i måneden. Jobindsats har ikke en API-tabel for rapporten [Dagpengemodtageres jobsøgning](https://jobindsats.dk/rapportbank/rapporter/dagpengemodtageres-jobsogning/). Tallene kommer derfor fra to manuelle Excel-eksporter pr. måned. Workflowet `discover-jobsearch-source` kører den 3. i hver måned og igen, hvis der senere dukker en API-tabel op.

Hver måned, når rapporten er opdateret:

1. Åbn rapporten og sæt Område til Alle kommuner, A-kasse til Alle A-kasser og Periode til den nye måned.
2. Eksportér søjlediagrammet Opsummerede data som `YYYYMM-fordeling.xlsx`.
3. Eksportér tabellen som `YYYYMM-tabel.xlsx`.
4. Læg begge filer i `data/raw/jobsearch/`. Filnavnet angiver måneden, for eksempel `202607-fordeling.xlsx` og `202607-tabel.xlsx` for juli 2026.

Næste kørsel af opdateringen læser filerne ind i `funds[kode].jobindsats.jobSearch`. En manglende måned springes over og stopper ikke resten af opdateringen. Importen er endnu ikke et krav i valideringen. Betegnelser, der ikke kan matches til navnestandarden eller de eksplicitte eksportaliaser i `scripts/import_jobsearch.py`, udelades og skrives i kildestatus i stedet for at blive gættet.

## Rådighedssanktioner

Sektion 9 henter Jobindsats.dk-tabellen `y01h01` (Antal rådighedssanktioner) kvartalsvist. Dashboardet viser samlet antal, andel sanktionerede ledige, sanktionstype og gennemsnitligt antal sanktioner pr. sanktioneret ledig. Historikken starter i 2019, og der markeres databrud fra 1. kvt. 2021. `I alt` hentes som en selvstaendig officiel række fra samme Jobindsats-tabel og bruges som standardbenchmark; den beregnes ikke som sum eller gennemsnit af a-kasserne. Både totalrækken og de enkelte a-kasser valideres i den automatiske opdatering. Jobindsats' kvartalskoder normaliseres, så fx `2026Q01` fortolkes som 1. kvartal 2026.
