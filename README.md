# A-kasseindsigt

A-kasseorienteret dashboard for Danske A-kasser.

Forsiden har en hovedvaelger for a-kasse og en valgfri benchmark. Raad medlemstal vises som KPI, mens sammenligninger mellem a-kasser saa vidt muligt bruger indeks, procenter eller rater.

## Officielle kilder

- DST AUA01: forsikringsaktive efter a-kasse, alder og koen.
- DST AUP03: fuldtidsledige i pct. af samtlige forsikrede efter a-kasse.
- Jobindsats.dk / STAR: a-dagpenge, dimittendledighed, langtidsledighed, opbrugt dagpengeret, forbrug af dagpengeperioden, overlevelseskurver, arbejdsmarkedsstatus efter afsluttet forloeb, samtaleformer i a-kassen, efterloen, efterloensbidragsbetalere og raadighedssanktioner. Jobsøgning blandt dagpengemodtagere opdateres fra manuelle eksporter, se afsnittet nedenfor.

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

## Rådighedssanktioner

Sektion 9 henter Jobindsats.dk-tabellen `y01h01` (Antal rådighedssanktioner) kvartalsvist. Dashboardet viser samlet antal, andel sanktionerede ledige, sanktionstype og gennemsnitligt antal sanktioner pr. sanktioneret ledig. Historikken starter i 2019, og der markeres databrud fra 1. kvt. 2021. `I alt` hentes som en selvstaendig officiel række fra samme Jobindsats-tabel og bruges som standardbenchmark; den beregnes ikke som sum eller gennemsnit af a-kasserne. Både totalrækken og de enkelte a-kasser valideres i den automatiske opdatering. Jobindsats' kvartalskoder normaliseres, så fx `2026Q01` fortolkes som 1. kvartal 2026.

## Jobsøgning

Sektion 10 viser andelen af dagpengemodtagere med mindst én registreret jobansøgning i måneden for den valgte a-kasse og for alle a-kasser. Jobindsats har ikke et API-tabel for målingen. Tallene kommer fra manuelle eksporter af rapporten [Dagpengemodtageres jobsøgning](https://jobindsats.dk/rapportbank/rapporter/dagpengemodtageres-jobsogning/).

Hver måned, når rapporten har en ny periode:

1. Åbn rapporten med Område = Alle kommuner og A-kasse = Alle A-kasser, og vælg den nye måned.
2. Eksportér søjlediagrammets opsummerede data som `YYYYMM-fordeling.xlsx`.
3. Eksportér tabellen som `YYYYMM-tabel.xlsx`.
4. Læg begge filer i `data/raw/jobsearch/`. `YYYYMM` er måneden, for eksempel `202608` for august 2026.

`scripts/import_jobsearch.py` læser filerne ved den almindelige opdatering og skriver serien til `funds[kode].jobindsats.jobSearch`. En måned uden begge filer springes over. Kilden er ikke påkrævet i valideringen, så en manglende ny måned stopper ikke de øvrige opdateringer. Importen bruger Python-pakken `openpyxl`.

Forkortelser og navne kobles til dashboardets a-kasser via `config/a-kasse-navne.json`, via det navnepar, som fordeling-filen selv angiver, og via en fast liste over stavemåder fra eksporten (`DFH-A`, `Det Faglige Hus`, `Laka`, `3FA` og `FOA - Fag og Arbejdes A-kasse`). Rækker, der ikke kan kobles entydigt, udelades og skrives i kørselsloggen. Der gættes ikke.

Workflowet `discover-jobsearch-source` kører desuden den 2. i hver måned for at opdage, hvis Jobindsats senere udgiver målingen som API-tabel.
