from pathlib import Path


def read(path):
    return Path(path).read_text(encoding="utf-8")


def write(path, text):
    Path(path).write_text(text, encoding="utf-8")


def replace_once(text, old, new, label):
    if old not in text:
        raise RuntimeError(f"Kunne ikke finde forventet tekst: {label}")
    return text.replace(old, new, 1)


# fetch_sources.py: fjern den gamle 3+-samtalemåling fra det generiske pass.
path = "scripts/fetch_sources.py"
text = read(path)
old_line = '        ("jobEarlyTalks", "earlyTalks", ["jobsamtaler", "a dagpengemodtagere", "a kasserne"], ["jobcent"], "latest:60", lambda r,f,t: process_timeseries(r,f,t,"earlyTalks",["andel"],"share"), "pct."),\n'
if old_line in text:
    text = text.replace(old_line, "", 1)
write(path, text)


# jobindsats_api.py: Jobindsats bruger også Y som periodetype for årsdata.
path = "scripts/jobindsats_api.py"
text = read(path)
old = 'for period_type in ("M", "Q", "A"):'
new = 'for period_type in ("M", "Q", "A", "Y"):'
if old in text:
    text = text.replace(old, new, 1)
elif new not in text:
    raise RuntimeError("Kunne ikke tilføje Y-periodetype til Jobindsats-klienten")
write(path, text)


# jobindsats_patch.py: erstat den gamle early_talks-funktion med verificerede kilder.
path = "scripts/jobindsats_patch.py"
text = read(path)

old_pkey = '''    q = re.fullmatch(r"(\\d{4})Q0?([1-4])", text)
    if q:
        return int(q.group(1)), int(q.group(2)) * 3
    return 0, 0
'''
new_pkey = '''    q = re.fullmatch(r"(\\d{4})Q0?([1-4])", text)
    if q:
        return int(q.group(1)), int(q.group(2)) * 3
    y = re.fullmatch(r"(\\d{4})Y\\d{2}", text)
    if y:
        return int(y.group(1)), 12
    return 0, 0
'''
text = replace_once(text, old_pkey, new_pkey, "årsperioder i pkey")

start = text.index("def early_talks(data):")
end = text.index("\ndef long_term(data):", start)
new_block = '''def query_up_to(table, spec, limit, breakdowns):
    try:
        return ji.query(table, spec, f"latest:{limit}", breakdowns)
    except RuntimeError as exc:
        matches = [int(x) for x in re.findall(r"only (\\d+) periods are available", str(exc), re.IGNORECASE)]
        if not matches:
            raise
        available = max(matches)
        if available < 1:
            raise
        return ji.query(table, spec, f"latest:{min(limit, available)}", breakdowns)


def all_fund_rows(table, spec, limit):
    fund_h, selection = setup_spec(spec)
    rows = query_up_to(table, spec, limit, ((fund_h, selection),))
    total_rows = query_up_to(table, spec, limit, ((fund_h, ji.total_value(fund_h)),))
    for row in total_rows:
        row["_dak_force_total"] = True
    rows.extend(total_rows)
    return rows


def row_fund_code(row, fcol, data):
    if row.get("_dak_force_total"):
        return data["meta"]["totalFundCode"]
    return fund_code(row.get(fcol), data)


def talk_forms(data):
    table = "smt02"
    spec, _, _ = setup(table)
    rows = all_fund_rows(table, spec, 120)
    fcol = exact_col(rows, "A-kasse") or ji.best_col(rows, ["a kasse"], distinct=True)
    pcol = exact_col(rows, "Periode") or ji.best_col(rows, ["periode"], distinct=True)
    cols = {
        "total": exact_col(rows, "Samtaler i alt"),
        "physical": exact_col(rows, "Fysiske samtaler"),
        "phone": exact_col(rows, "Telefoniske samtaler"),
        "video": exact_col(rows, "Videosamtaler"),
        "other": exact_col(rows, "Anden kontakt"),
    }
    missing = [key for key, col in cols.items() if not col]
    if missing:
        raise RuntimeError(f"Samtaleformer mangler kolonner: {missing}; har {ji.columns(rows)}")
    grouped = defaultdict(dict)
    for row in rows:
        code = row_fund_code(row, fcol, data)
        period = str(row.get(pcol) or "")
        if code not in data["funds"] or not period:
            continue
        grouped[code][period] = {key: ji.number(row.get(col)) for key, col in cols.items()}
    if not grouped:
        raise RuntimeError("Samtaleformer gav ingen a-kassedata")
    for code, values in grouped.items():
        labels = sorted(values, key=pkey)
        data["funds"][code]["jobindsats"]["talkForms"] = {
            "labels": labels,
            **{key: [values[p][key] for p in labels] for key in cols},
        }
    latest = max((p for values in grouped.values() for p in values), key=pkey)
    put_status(
        data,
        "jobTalkForms",
        table,
        latest,
        "antal jobsamtaler efter samtaleform",
        "Omfatter jobsamtaler afholdt i a-kassen med personer, der modtog a-dagpenge på samtaletidspunktet. Serien findes fra januar 2024.",
    )
    data["meta"]["sourceStatus"].pop("jobEarlyTalks", None)
    data["meta"].setdefault("jobindsatsTables", {}).pop("jobEarlyTalks", None)
    for fund in data["funds"].values():
        fund.get("jobindsats", {}).pop("earlyTalks", None)


def afterlon(data):
    table = "y28a02"
    spec, _, _ = setup(table)
    rows = all_fund_rows(table, spec, 120)
    fcol = exact_col(rows, "A-kasse") or ji.best_col(rows, ["a kasse"], distinct=True)
    pcol = exact_col(rows, "Periode") or ji.best_col(rows, ["periode"], distinct=True)
    persons = exact_col(rows, "Antal personer på efterløn")
    paid = exact_col(rows, "Antal personer med udbetalt efterløn")
    fulltime = exact_col(rows, "Antal fuldtidspersoner med udbetalt efterløn")
    if not persons or not paid or not fulltime:
        raise RuntimeError(f"Efterløn mangler forventede kolonner; har {ji.columns(rows)}")
    grouped = defaultdict(dict)
    for row in rows:
        code = row_fund_code(row, fcol, data)
        period = str(row.get(pcol) or "")
        if code in data["funds"] and period:
            grouped[code][period] = {
                "persons": ji.number(row.get(persons)),
                "paidPersons": ji.number(row.get(paid)),
                "fulltime": ji.number(row.get(fulltime)),
            }
    if not grouped:
        raise RuntimeError("Efterløn gav ingen a-kassedata")
    for code, values in grouped.items():
        labels = sorted(values, key=pkey)
        data["funds"][code]["jobindsats"]["afterlon"] = {
            "labels": labels,
            "persons": [values[p]["persons"] for p in labels],
            "paidPersons": [values[p]["paidPersons"] for p in labels],
            "fulltime": [values[p]["fulltime"] for p in labels],
        }
    latest = max((p for values in grouped.values() for p in values), key=pkey)
    put_status(data, "jobAfterlon", table, latest, "personer og fuldtidspersoner på efterløn")


def afterlon_contrib(data):
    table = "y28a15"
    spec, _, _ = setup(table)
    rows = all_fund_rows(table, spec, 30)
    fcol = exact_col(rows, "A-kasse") or ji.best_col(rows, ["a kasse"], distinct=True)
    pcol = exact_col(rows, "Periode") or ji.best_col(rows, ["periode"], distinct=True)
    count = exact_col(rows, "Antal efterlønsbidragsbetalere")
    share = exact_col(rows, "Andel efterlønsbidragsbetalere blandt dagpengeforsikrede")
    if not count or not share:
        raise RuntimeError(f"Efterlønsbidrag mangler forventede kolonner; har {ji.columns(rows)}")
    grouped = defaultdict(dict)
    for row in rows:
        code = row_fund_code(row, fcol, data)
        period = str(row.get(pcol) or "")
        if code in data["funds"] and period:
            grouped[code][period] = {
                "count": ji.number(row.get(count)),
                "share": ji.number(row.get(share)),
            }
    if not grouped:
        raise RuntimeError("Efterlønsbidrag gav ingen a-kassedata")
    for code, values in grouped.items():
        labels = sorted(values, key=pkey)
        data["funds"][code]["jobindsats"]["afterlonContrib"] = {
            "labels": labels,
            "count": [values[p]["count"] for p in labels],
            "share": [values[p]["share"] for p in labels],
        }
    latest = max((p for values in grouped.values() for p in values), key=pkey)
    put_status(
        data,
        "jobAfterlonContrib",
        table,
        latest,
        "antal og pct. efterlønsbidragsbetalere blandt dagpengeforsikrede",
        "Opgøres én gang årligt pr. 1. september, dog 1. november i 2012.",
    )
'''
text = text[:start] + new_block + text[end:]
text = replace_once(
    text,
    '        ("jobEarlyTalks", early_talks),\n',
    '        ("jobTalkForms", talk_forms),\n        ("jobAfterlon", afterlon),\n        ("jobAfterlonContrib", afterlon_contrib),\n',
    "special-jobliste",
)
write(path, text)


# run_update.py: alle nye kilder og moduler bliver obligatoriske.
path = "scripts/run_update.py"
text = read(path)
text = replace_once(
    text,
    '        "jobEarlyTalks",\n',
    '        "jobTalkForms",\n        "jobAfterlon",\n        "jobAfterlonContrib",\n',
    "required sources",
)
text = replace_once(
    text,
    '        "earlyTalks",\n',
    '        "talkForms",\n        "afterlon",\n        "afterlonContrib",\n',
    "required modules",
)
text = replace_once(
    text,
    '        ("earlyTalks", "labels", "jobEarlyTalks"),\n',
    '        ("talkForms", "labels", "jobTalkForms"),\n        ("afterlon", "labels", "jobAfterlon"),\n        ("afterlonContrib", "labels", "jobAfterlonContrib"),\n',
    "period checks",
)
text = replace_once(
    text,
    "        'id=\"talkPeriodText\"',\n",
    "        'id=\"talkPeriodText\"',\n        'id=\"afterlonPeriodText\"',\n        'id=\"afterlonContribPeriodText\"',\n        'id=\"afterlonChart\"',\n        'id=\"afterlonContribChart\"',\n",
    "HTML ids",
)
text = replace_once(
    text,
    "        'Mindst 3 samtaler',\n",
    "        'Samtaleformer i a-kassen',\n        'Efterløn',\n",
    "HTML labels",
)
write(path, text)


# update-dashboard.yml: eksplicit source-gate.
path = ".github/workflows/update-dashboard.yml"
text = read(path)
text = replace_once(
    text,
    "--require-source jobEarlyTalks ",
    "--require-source jobTalkForms --require-source jobAfterlon --require-source jobAfterlonContrib ",
    "workflow source-gate",
)
write(path, text)


# README.
path = "README.md"
text = read(path)
old = "Jobindsats.dk / STAR: a-dagpenge, dimittendledighed, langtidsledighed, opbrugt dagpengeret, forbrug af dagpengeperioden, overlevelseskurver, arbejdsmarkedsstatus efter afsluttet forloeb, tidlig samtaleindsats og raadighedssanktioner."
new = "Jobindsats.dk / STAR: a-dagpenge, dimittendledighed, langtidsledighed, opbrugt dagpengeret, forbrug af dagpengeperioden, overlevelseskurver, arbejdsmarkedsstatus efter afsluttet forloeb, samtaleformer i a-kassen, efterloen, efterloensbidragsbetalere og raadighedssanktioner."
text = replace_once(text, old, new, "README kildeliste")
write(path, text)


# index.html: KPI, sektioner, kilder og grafer.
path = "index.html"
text = read(path)
text = replace_once(text, "<small>Mindst 3 samtaler</small>", "<small>Samtaler i a-kassen</small>", "KPI label")

section_start = text.index('<section><h2>6. A-kassens egen tidlige indsats</h2>')
sanctions_start = text.index('<section><h2>7. Rådighedssanktioner</h2>', section_start)
sanctions_heading_end = sanctions_start + len('<section><h2>7. Rådighedssanktioner</h2>')
new_sections = '''<section><h2>6. Samtaler i a-kassen</h2><p>Hvor mange jobsamtaler a-kassen afholder, og hvordan samtalerne gennemføres.</p><div class="card"><h3>Samtaleformer i a-kassen</h3><div class="explain"><strong>Hvad måles:</strong> Alle jobsamtaler afholdt af a-kassen med personer, der modtog a-dagpenge på samtaletidspunktet, fordelt på fysisk fremmøde, telefon, video og anden kontakt. Serien starter i januar 2024. <strong>Seneste periode:</strong> <span id="talkPeriodText">-</span>.</div><div id="talkWrap" class="chart"><canvas id="talkChart"></canvas></div><div class="source"><span>Kilde: <a href="https://jobindsats.dk/databank/indsatser/tilbud-og-samtaler/samtaler/samtaleformer-i-a-kassen/" target="_blank" rel="noopener">Jobindsats.dk - Samtaleformer i a-kassen</a></span><span id="sTalk"></span></div></div></section>
<section><h2>7. Efterløn</h2><p>Efterløn er fortsat en a-kasseopgave. Her vises både brugen af ordningen og tilslutningen via efterlønsbidrag.</p><div class="grid"><div class="card"><h3>Personer på efterløn</h3><div class="desc">Antal personer, der er inde i efterlønsordningen i måneden. Konkrete a-kasser valgt under Sammenlign med vises også.</div><div class="explain"><strong>Seneste periode:</strong> <span id="afterlonPeriodText">-</span>. Personer kan indgå uden at have fået efterløn udbetalt i den pågældende måned.</div><div id="afterlonWrap" class="chart"><canvas id="afterlonChart"></canvas></div><div class="source"><span>Kilde: <a href="https://www.jobindsats.dk/information/om-malinger/om-ydelser/om-efterlon/om-antal-personer-og-fuldtidspersoner-pa-efterlon/" target="_blank" rel="noopener">Jobindsats.dk - Antal personer og fuldtidspersoner på efterløn</a></span><span id="sAfterlon"></span></div></div><div class="card"><h3>Efterlønsbidragsbetalere blandt dagpengeforsikrede</h3><div class="desc">Andel af de dagpengeforsikrede, der indbetaler efterlønsbidrag. Målingen viser den fremtidige tilslutning til ordningen.</div><div class="explain"><strong>Seneste år:</strong> <span id="afterlonContribPeriodText">-</span>. Opgøres én gang årligt pr. 1. september, dog 1. november i 2012.</div><div id="afterlonContribWrap" class="chart"><canvas id="afterlonContribChart"></canvas></div><div class="source"><span>Kilde: <a href="https://jobindsats.dk/information/om-malinger/om-ydelser/om-efterlon/om-antal-og-andel-efterlonsbidragsbetalere-blandt-dagpengeforsikrede/" target="_blank" rel="noopener">Jobindsats.dk - Efterlønsbidragsbetalere blandt dagpengeforsikrede</a></span><span id="sAfterlonContrib"></span></div></div></div></section>
<section><h2>8. Rådighedssanktioner</h2>'''
text = text[:section_start] + new_sections + text[sanctions_heading_end:]

# Årsperioder skal vises som årstal.
text = replace_once(
    text,
    "m=/^(\\d{4})K([1-4])$/.exec(p||'');if(m)return m[2]+'. kvt. '+m[1];return p||'-'};const pct",
    "m=/^(\\d{4})K([1-4])$/.exec(p||'');if(m)return m[2]+'. kvt. '+m[1];m=/^(\\d{4})Y\\d{2}$/.exec(p||'');if(m)return m[1];return p||'-'};const pct",
    "period formatter",
)

annual_fn = "function compareJobAnnual(k,id,moduleKey,field,percent=false){const f=fund(),a=f?.jobindsats?.[moduleKey];if(!a){missing(id.replace('Chart','Wrap'));return}const n=Math.max(1,Math.ceil(+$('periodSelect').value/12)),w=seriesWindow(a,field,n),sets=[{label:f.name,data:w.values,borderColor:C.gd,backgroundColor:C.gd,pointRadius:0,borderWidth:2.6,tension:.18,spanGaps:false}];compareCodes().forEach((code,i)=>{const b=DATA.funds[code]?.jobindsats?.[moduleKey];if(!b)return;sets.push({label:DATA.funds[code].name,data:mapValues(b,field,w.labels),borderColor:color(i),backgroundColor:color(i),pointRadius:0,borderWidth:2,tension:.18,spanGaps:false})});lineChart(k,id,w.labels,sets,percent,true)}"
text = replace_once(text, "function shares(items){", annual_fn + "function shares(items){", "annual chart helper")

talk_fn = "function talkFormsChart(){const s=fund()?.jobindsats?.talkForms;if(!s?.labels?.length){missing('talkWrap');return}const n=+$('periodSelect').value,start=Math.max(0,s.labels.length-n),labels=s.labels.slice(start),defs=[['Fysisk','physical',C.gd],['Telefon','phone',C.b],['Video','video',C.o],['Anden kontakt','other',C.p]],sets=defs.map(([label,key,col])=>({label,data:(s[key]||[]).slice(start),borderColor:col,backgroundColor:col,pointRadius:0,borderWidth:2.3,tension:.18,spanGaps:false}));lineChart('talk','talkChart',labels,sets,false,true)}"
text = replace_once(text, "function sanctionTypeChart(){", talk_fn + "function sanctionTypeChart(){", "talk chart helper")

text = replace_once(
    text,
    "['sStatus','jobStatusAfter'],['sTalk','jobEarlyTalks'],['sSanctionsTotal','jobSanctions']",
    "['sStatus','jobStatusAfter'],['sTalk','jobTalkForms'],['sAfterlon','jobAfterlon'],['sAfterlonContrib','jobAfterlonContrib'],['sSanctionsTotal','jobSanctions']",
    "source mapping",
)
text = replace_once(
    text,
    "$('talkPeriodText').textContent=period(DATA.meta.sourceStatus?.jobEarlyTalks?.latestPeriod);$('sanctionsPeriodText')",
    "$('talkPeriodText').textContent=period(DATA.meta.sourceStatus?.jobTalkForms?.latestPeriod);$('afterlonPeriodText').textContent=period(DATA.meta.sourceStatus?.jobAfterlon?.latestPeriod);$('afterlonContribPeriodText').textContent=period(DATA.meta.sourceStatus?.jobAfterlonContrib?.latestPeriod);$('sanctionsPeriodText')",
    "period labels",
)
text = replace_once(
    text,
    "s=f.jobindsats?.earlyTalks;x=last(s,'share');$('k6').textContent=x?pct(x.value):'-';$('k6s').textContent=kpiSub(s,'share',x,pct)",
    "s=f.jobindsats?.talkForms;x=last(s,'total');$('k6').textContent=x?num(x.value):'-';$('k6s').textContent=kpiSub(s,'total',x,num)",
    "KPI data",
)
text = replace_once(
    text,
    "compareCategory('status','statusChart','statusAfter3m',true,false,false);compareJobTime('talk','talkChart','earlyTalks','share',true,false);singleQuarterTime",
    "compareCategory('status','statusChart','statusAfter3m',true,false,false);talkFormsChart();rawJobTime('al','afterlonChart','afterlon','persons',true);compareJobAnnual('ac','afterlonContribChart','afterlonContrib','share',true);singleQuarterTime",
    "draw calls",
)
write(path, text)

print("Migration anvendt")
