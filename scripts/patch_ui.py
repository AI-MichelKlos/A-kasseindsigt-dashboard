from __future__ import annotations

from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
HTML = BASE / "index.html"

PERIOD_CSS = ".period-highlight{margin:6px 0 12px;padding:8px 10px;border-left:3px solid var(--g);background:#f7faf8;color:#405b63;font-size:.84rem;line-height:1.4}.period-highlight strong{color:var(--ink)}"

STATUS_OLD = '<div class="card"><h3>Arbejdsmarkedsstatus 3 måneder efter ophør i a-dagpenge</h3><div class="explain">'
STATUS_NEW = '<div class="card"><h3>Arbejdsmarkedsstatus 3 måneder efter ophør i a-dagpenge</h3><div class="period-highlight">Afslutningsperiode: <strong id="statusPeriodHeadline">-</strong></div><div class="explain">'

SURV_OLD = '<div class="card wide"><h3>Varighed i nye a-dagpengeforløb</h3><div class="desc">'
SURV_NEW = '<div class="card wide"><h3>Varighed i nye a-dagpengeforløb</h3><div class="period-highlight">Forløb påbegyndt i: <strong id="survPeriodHeadline">-</strong></div><div class="desc">'

SURV_SOURCE = '<div class="source"><span>Kilde: <a href="https://jobindsats.dk/information/om-malinger/om-ydelser/om-a-dagpenge/om-overlevelseskurver/" target="_blank" rel="noopener">Jobindsats.dk – Overlevelseskurver</a></span><span id="sSurv"></span></div></div>'

COMPLETED_CARD = '''<div class="card wide"><h3>Varighed af afsluttede a-dagpengeforløb</h3><div class="period-highlight">Forløb afsluttet i: <strong id="completedDurationPeriodHeadline">-</strong></div><div class="desc">Fordeling af afsluttede a-dagpengeforløb efter forløbenes samlede varighed. Figuren viser andele, så a-kasser kan sammenlignes på tværs af størrelse.</div><div class="explain"><strong>Gennemsnitlig varighed:</strong> <span id="completedDurationAverage">-</span>. Et forløb regnes som afsluttet, når der følger en sammenhængende kalendermåned uden udbetaling af a-dagpenge.</div><div id="completedDurationWrap" class="chart"><canvas id="completedDurationChart"></canvas></div><div class="source"><span>Kilde: <a href="https://jobindsats.dk/information/om-malinger/om-ydelser/om-a-dagpenge/a-dagpenge-antal-og-varighed-af-afsluttede-forlob/" target="_blank" rel="noopener">Jobindsats.dk – Antal og varighed af afsluttede forløb</a></span><span id="sCompletedDuration"></span></div></div>'''

ENHANCEMENT_MARKER = "/* DAK_UI_ENHANCEMENTS_20260821 */"
ENHANCEMENTS = r'''<script>
/* DAK_UI_ENHANCEMENTS_20260821 */
(function(){
  const baseLineChart=lineChart;
  lineChart=function(k,id,labels,sets,percent=false,beginZero=false){
    baseLineChart(k,id,labels,sets,percent,beginZero);
    if(id==='membersIndexChart'&&charts[k]){
      const values=sets.flatMap(s=>Array.isArray(s.data)?s.data:[]).map(Number).filter(Number.isFinite);
      if(values.length){
        const lowest=Math.min(...values);
        const axisMin=lowest<80?Math.floor(lowest/5)*5:80;
        charts[k].options.scales.y.min=axisMin;
        charts[k].update('none');
      }
    }
  };

  const baseProfileAge=compareProfileAge;
  compareProfileAge=function(){
    baseProfileAge();
    const chart=charts.age;
    if(chart){
      chart.options.plugins.tooltip={callbacks:{label:function(ctx){
        const value=ctx.parsed&&Number.isFinite(ctx.parsed.y)?ctx.parsed.y:ctx.raw;
        return ctx.dataset.label+': '+pf.format(value)+' %';
      }}};
      chart.update('none');
    }
  };

  function completedDurationChart(){
    const block=fund()?.jobindsats?.completedDuration;
    if(!block?.items?.length){missing('completedDurationWrap');return;}
    compareCategory('completedDuration','completedDurationChart','completedDuration',true,true,true);
    const avg=block.averageWeeks;
    $('completedDurationAverage').textContent=avg==null?'Ikke tilgængelig':pf.format(avg)+' uger';
  }

  const baseSetSources=setSources;
  setSources=function(){
    baseSetSources();
    const statusPeriod=period(DATA.meta.sourceStatus?.jobStatusAfter?.latestPeriod);
    const survivalPeriod=period(DATA.meta.sourceStatus?.jobOverlevelse?.latestPeriod);
    const completedPeriod=period(DATA.meta.sourceStatus?.jobCompletedDuration?.latestPeriod);
    if($('statusPeriodHeadline'))$('statusPeriodHeadline').textContent=statusPeriod;
    if($('survPeriodHeadline'))$('survPeriodHeadline').textContent=survivalPeriod;
    if($('completedDurationPeriodHeadline'))$('completedDurationPeriodHeadline').textContent=completedPeriod;
    if($('sCompletedDuration'))$('sCompletedDuration').textContent=source('jobCompletedDuration');
  };

  const baseDraw=draw;
  draw=function(){baseDraw();completedDurationChart();};
})();
</script>
'''

PERSONAL_VIEW_SCRIPT = '<script src="assets/personal-view.js"></script>\n'


def require_replace(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        return text
    if old not in text:
        raise RuntimeError(f"Kunne ikke finde UI-markør: {label}")
    return text.replace(old, new, 1)


def main():
    text = HTML.read_text(encoding="utf-8")

    text = text.replace(".source a{color:var(--gd);font-weight:700;text-decoration:none}", ".source a{color:var(--gd);font-weight:400;text-decoration:none}")

    if PERIOD_CSS not in text:
        marker = ".desc{font-size:.86rem;color:var(--muted);margin:5px 0 12px;line-height:1.5}"
        if marker not in text:
            raise RuntimeError("Kunne ikke finde CSS-markør til periodefelt")
        text = text.replace(marker, marker + PERIOD_CSS, 1)

    text = require_replace(text, STATUS_OLD, STATUS_NEW, "arbejdsmarkedsstatus")
    text = require_replace(text, SURV_OLD, SURV_NEW, "nye dagpengeforløb")

    if 'id="completedDurationChart"' not in text:
        if SURV_SOURCE not in text:
            raise RuntimeError("Kunne ikke finde overlevelsesgrafens kildeblok")
        text = text.replace(SURV_SOURCE, SURV_SOURCE + COMPLETED_CARD, 1)

    if ENHANCEMENT_MARKER not in text:
        marker = '<script data-goatcounter="https://akassesiden.goatcounter.com/count"'
        if marker not in text:
            raise RuntimeError("Kunne ikke finde GoatCounter-markør")
        text = text.replace(marker, ENHANCEMENTS + marker, 1)

    if PERSONAL_VIEW_SCRIPT.strip() not in text:
        marker = '<script data-goatcounter="https://akassesiden.goatcounter.com/count"'
        if marker not in text:
            raise RuntimeError("Kunne ikke finde GoatCounter-markør til personlig visning")
        text = text.replace(marker, PERSONAL_VIEW_SCRIPT + marker, 1)

    HTML.write_text(text, encoding="utf-8")
    print("OK: UI-patch anvendt")


if __name__ == "__main__":
    main()
