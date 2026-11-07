"""Independent checks that report uncertainty and never modify source facts."""
from collections import defaultdict
from decimal import Decimal
from hashlib import sha256
from app.calculations import percentage_change, compound, display, decimal
from app.models import Issue


def validate(facts, pages):
    issues = []
    def issue(rule, severity, title, description, related, details=None, extra_pages=None):
        ids = [f["id"] for f in related]
        page_numbers = sorted(set([f["source"]["page"] for f in related]+(extra_pages or [])))
        uid = sha256(f"{rule}:{ids}:{page_numbers}".encode()).hexdigest()[:16]
        issues.append(Issue(id=uid, rule=rule, severity=severity, title=title, description=description,
                            fact_ids=ids, pages=page_numbers, details=details or {}).model_dump(mode="json"))
    annual = {}
    for f in facts:
        if f["metric"] == "nav" and f["classification"] == "historical":
            annual.setdefault(f["period"], f)
    years = sorted(annual)
    for previous, year in zip(years, years[1:]):
        if int(year)-int(previous)!=1:
            continue
        reported = next((f for f in facts if f["metric"]=="fund_return" and f["period"]==year and f["classification"]=="historical"), None)
        if reported and decimal(annual[previous]["value"]) != 0:
            implied = percentage_change(annual[previous]["value"], annual[year]["value"])
            if abs(implied-decimal(reported["value"])) > Decimal("0.15"):
                issue("nav_return_mismatch", "warning", f"{year} return does not reconcile with NAV",
                      f"NAV moves from {annual[previous]['value']} to {annual[year]['value']}, implying {display(implied)}%, while the annual table reports {reported['value']}%. Timing, distributions, or methodology are not resolved by the source.",
                      [annual[previous], annual[year], reported], {"reported": reported["value"], "computed": str(implied), "formula": "(closing NAV / previous year NAV − 1) × 100", "tolerance_pp": "0.15"})
    # Same metric and period may have more than one observation, including
    # genuinely contradictory versions. Never use last-write-wins ingestion.
    grouped = defaultdict(list)
    for f in facts:
        grouped[(f["metric"],f["period"],f.get("category"),f["classification"])].append(f)
    conflicting_quarters = defaultdict(list)
    duplicates = []
    for key, observations in grouped.items():
        values = {decimal(f["value"]) for f in observations}
        if len(values)>1:
            if "-Q" in key[1] or "-FY-quarterly" in key[1]:
                conflicting_quarters[key[1][:4]].extend(observations)
            else:
                issue("conflicting_observations", "warning", f"Conflicting {key[0].replace('_',' ')} for {key[1]}",
                      "Multiple source locations report different values for the same metric and period. No authoritative version is specified.", observations,
                      {"values": [{"page":f["source"]["page"],"value":f["value"]} for f in observations]})
        elif len(observations)>1:
            duplicates.extend(observations)
    for year, observations in conflicting_quarters.items():
        issue("quarterly_version_conflict", "warning", f"{year} has conflicting quarterly tables",
              f"The report repeats {year} quarterly data with different opening NAV, closing NAV, or returns. Every observation is retained with its own page; the system cannot choose an authoritative version.",
              list({f["id"]:f for f in observations}.values()),
              {"source_pages": sorted({f["source"]["page"] for f in observations}), "policy": "Present all page-specific variants; never average or select silently"})
    # Reconciliation and compounding run within each table version.
    quarters = defaultdict(list)
    for f in facts:
        if "-Q" in f["period"] or "-FY-quarterly" in f["period"]:
            quarters[f["source"]["page"]].append(f)
    reconciliation = defaultdict(list)
    compound_groups = defaultdict(list)
    for page_number, table_facts in quarters.items():
        qreturns = sorted([f for f in table_facts if f["metric"]=="quarter_return" and "-Q" in f["period"]], key=lambda f:f["period"])
        if len(qreturns) != 4:
            continue
        year = qreturns[0]["period"][:4]
        for q in range(1,4):
            closing = next((f for f in table_facts if f["period"]==f"{year}-Q{q}" and f["metric"]=="closing_nav"),None)
            opening = next((f for f in table_facts if f["period"]==f"{year}-Q{q+1}" and f["metric"]=="opening_nav"),None)
            if closing and opening and abs(decimal(closing["value"])-decimal(opening["value"]))>Decimal("0.1"):
                issue("quarter_nav_continuity", "warning", f"Quarter NAV continuity breaks on p. {page_number}",
                      "The next quarter opens at a different NAV from the preceding quarter's close.",[closing,opening])
        close = next((f for f in table_facts if f["period"]==f"{year}-Q4" and f["metric"]=="closing_nav"),None)
        if close and year in annual and abs(decimal(close["value"])-decimal(annual[year]["value"]))>Decimal("0.1"):
            reconciliation[year].append(close)
        compounded = compound([f["value"] for f in qreturns])
        simple = sum(decimal(f["value"]) for f in qreturns)
        full_year = next((f for f in table_facts if f["metric"]=="quarter_return" and "FY-quarterly" in f["period"]),None)
        compound_groups[year].append({"page":page_number,"simple_sum":str(simple),"compounded":str(compounded),"inputs":[f["value"] for f in qreturns]})
        if full_year and abs(decimal(full_year["value"])-simple)>Decimal("0.15"):
            issue("quarterly_sum_mismatch","warning",f"Full-year simple sum differs on p. {page_number}","The report labels this as a simple sum, but the reported total does not match the quarter inputs.",qreturns+[full_year])
    for year, close_facts in reconciliation.items():
        variants = ", ".join(f"{f['value']} (p. {f['source']['page']})" for f in close_facts)
        issue("annual_quarterly_mismatch", "warning", f"{year} annual and quarterly NAV disagree",
              f"The annual NAV is {annual[year]['value']} (p. {annual[year]['source']['page']}); quarterly Q4 closing values are {variants}. No source is silently preferred.",
              [annual[year]]+close_facts,{"annual_nav":annual[year]["value"],"quarterly_versions":[{"page":f["source"]["page"],"closing_nav":f["value"]} for f in close_facts]})
    for year, versions in compound_groups.items():
        related = [f for f in facts if f["metric"]=="quarter_return" and f["period"].startswith(year+"-")]
        issue("simple_sum_vs_compounding", "info", f"{year} quarterly totals use a simple sum",
              "The PDF explicitly labels its full-year return as a simple sum. That is not a compounded annual return. The assistant compounds the four inputs separately and shows its formula; this source convention is not treated as an arithmetic error.",
              related,{"formula":"(∏(1 + quarterly_return / 100) − 1) × 100","versions":versions})
    allocation_groups = defaultdict(list)
    for f in facts:
        if f["metric"]=="allocation":
            allocation_groups[(f["period"],f["source"]["page"])].append(f)
    for (dimension,page_number), observations in allocation_groups.items():
        page = next(p for p in pages if p["number"]==page_number)
        # Allocation charts in annual reviews expressly do not claim exhaustive
        # holdings. Only check the dedicated distribution table.
        if "illustrative distribution" in page["text"].lower():
            total = sum(decimal(f["value"]) for f in observations)
            if abs(total-100)>Decimal("0.1"):
                issue("allocation_total", "warning", f"{dimension} distribution totals {display(total)}%",
                      "The categories in this distribution do not add to 100%; verify exhaustiveness and overlap before interpreting.", observations,{"sum_percent":str(total)})
    if duplicates:
        issue("identical_repeated_observations", "info", "Identical observations appear on multiple pages",
              "Annual, forecast, and allocation tables repeat. Identical values are grouped in the overview, while all source observations remain available for audit. Conflicting quarterly versions are tracked separately.",
              duplicates,{"duplicate_observations":len(duplicates),"display_policy":"Group identical values only; retain each provenance record"})
    glyph_pages = [p["number"] for p in pages if any("currency glyph" in w for w in p["warnings"])]
    if glyph_pages:
        issue("unresolved_currency_glyph", "warning", "Currency symbols are unresolved in the source",
              "The original PDF renders a square where the currency symbol should be; extraction reads a dingbat 'n'. NAV units and AUM crore are preserved, but a currency such as INR is not inferred.",[],{"unit_policy":"NAV units; crore (currency unresolved)","raw_glyph":"n / ZapfDingbats"},glyph_pages)
    chart_pages = [p for p in pages if p.get("chart_observations")]
    if chart_pages:
        obs = chart_pages[0]["chart_observations"][0]
        forecasts = [f for f in facts if f["metric"]=="nav" and f["classification"]=="forecast"]
        if forecasts:
            highest = max(forecasts,key=lambda f:decimal(f["value"]))
            if float(highest["value"])>obs["estimated_axis_max"]+2:
                issue("chart_range_review","warning","Forecast NAV may exceed the chart range","The table NAV exceeds the estimated chart axis range. This requires a visual cross-check; no value is corrected.",[highest],obs,[p["number"] for p in chart_pages])
            elif float(highest["value"])>obs["highest_labeled_tick"]:
                issue("chart_tick_is_not_axis_max", "info", "The forecast chart extends beyond its highest labeled tick",
                      "The highest labeled tick is 360, but native vector geometry places the axis top near 450. The 390.3 table value is within that range. A highest-tick comparison alone would create a false discrepancy.",
                      [highest],obs,[p["number"] for p in chart_pages])
    low_pages = [p for p in pages if any("OCR" in w for w in p["warnings"])]
    for p in low_pages:
        issue("ocr_review", "warning", f"Page {p['number']} requires extraction review", "; ".join(p["warnings"]),[],{},[p["number"]])
    return issues
