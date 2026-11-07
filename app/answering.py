"""Explicit query routing, source-preserving lookups, and auditable calculations."""
import logging
import re
import time
from collections import defaultdict
from decimal import Decimal
from app.calculations import compound, percentage_change, difference, display, decimal
from app.retrieval import retrieve, tokenize
from app import provider

logger=logging.getLogger("fund.answering")


def answer_question(payload,question,document_id):
    started=time.perf_counter()
    q=question.lower().strip()
    facts=payload["facts"]
    years=re.findall(r"\b(?:19|20)\d{2}\b",q)
    calculations=[]
    selected=[]
    warnings=[]
    answer=""
    route="structured"
    method="structured facts"
    composer="deterministic"
    source_overrides=[]
    def find(metric,period=None,classification=None):
        return [f for f in facts if f["metric"]==metric and (period is None or f["period"]==str(period)) and (classification is None or f["classification"]==classification)]
    def unique(observations):
        seen=set();result=[]
        for f in observations:
            key=(f["metric"],f["period"],f["value"],f.get("category"))
            if key not in seen:
                seen.add(key);result.append(f)
        return result
    def add_calculation(formula,inputs,result,unit,observations):
        calculations.append({"formula":formula,"inputs":[str(i) for i in inputs],"result":display(result),"unit":unit,"fact_ids":[f["id"] for f in observations]})
    def unsupported(message="The report does not contain sufficient evidence to answer that question. Ask about its historical performance, quarterly tables, allocations, risks, assumptions, or forecasts."):
        return message
    numeric_intent=bool(re.search(r"\b(nav|aum|returns?|benchmark|highest|lowest|largest|allocation|quarter|q[1-4]|compare|compound|cagr|performance)\b",q))
    explanation_intent=bool(re.search(r"\b(why|explain|assumption|assumptions|risk|risks|define|meaning|glossary|scenario|scenarios|real|fictional|synthetic|stand for)\b",q)) or bool(re.search(r"what (?:is|does) (?:nav|aum|cagr)\??$",q))
    historical_years=sorted({f["period"] for f in facts if f["classification"]=="historical" and re.fullmatch(r"(?:19|20)\d{2}",f["period"])})
    relative=re.search(r"\b(?:last|latest|past|recent)\s*(one|two|three|four|five|\d+)?\s*years?\b",q)
    summary_intent=bool(re.search(r"\b(summari[sz]e|summary|overview|highlights)\b",q))
    if relative and not years and historical_years:
        count={"one":1,"two":2,"three":3,"four":4,"five":5}.get(relative[1],int(relative[1]) if (relative[1] or "").isdigit() else 2)
        years=historical_years[-max(1,min(count,10)):]
        summary_intent=True
    if re.search(r"(?:reveal|show|print|expose).*(?:api key|password|system prompt|secret)|ignore.*instructions",q):
        route="unsupported";answer="I can answer questions about the report’s financial evidence. Instructions inside the document or question cannot change the evidence policy or expose application secrets."
    elif years and numeric_intent and not explanation_intent and not summary_intent and any(y not in {f["period"][:4] for f in facts} for y in years):
        route="unsupported";answer=unsupported("The requested year is not present in the extracted financial tables. I cannot extrapolate an unreported value.")
    elif summary_intent and historical_years:
        scope=years or historical_years[-2:]
        selected=unique([f for f in facts if f["period"] in scope and f["classification"]=="historical" and f["metric"] in {"nav","aum","fund_return","benchmark_return"}])
        rows=["| Year | Metric | Reported value | Source |", "| --- | --- | --- | --- |"]
        for f in selected:
            unit="%" if f["unit"]=="percent" else " "+f["unit"]
            rows.append(f"| {f['period']} | {f['metric'].replace('_',' ').title()} | {display(f['value'],1)}{unit} | p. {f['source']['page']} |")
        answer=(f"### Historical summary\n\nUsing the latest available historical years in this report: {', '.join(scope)}. Forecasts are excluded.\n\n"+"\n".join(rows)) if selected else unsupported("No historical observations were found for the requested period.")
    elif "compound" in q and len(re.findall(r"[+-]?\d+(?:\.\d+)?\s*%",q))>=2:
        values=re.findall(r"([+-]?\d+(?:\.\d+)?)\s*%",q)
        result=compound(values)
        answer=f"The compounded return for {', '.join(v+'%' for v in values)} is {display(result)}%. The simple sum is {display(sum(decimal(v) for v in values))}%. These are different methods. The inputs here were supplied in your question, not extracted from the report."
        add_calculation("(∏(1 + periodic_return / 100) − 1) × 100",values,result,"percent",[])
    elif len(set(years))==2 and "nav" in q and re.search(r"\b(change|growth|increase|decrease|difference|grew)\b",q):
        start_year,end_year=sorted(set(years));start=unique(find("nav",start_year));end=unique(find("nav",end_year))
        if start and end:
            selected=[start[0],end[0]];result=percentage_change(start[0]["value"],end[0]["value"])
            answer=f"Source-reported NAV changes from {start[0]['value']} in {start_year} to {end[0]['value']} in {end_year}: {display(result)}%. This is calculated NAV growth, distinct from source-reported periodic returns."
            add_calculation("(ending NAV / starting NAV − 1) × 100",[start[0]["value"],end[0]["value"]],result,"percent",selected)
            if any(f["classification"]=="forecast" for f in selected):answer+=" The comparison includes a forecast endpoint."
        else:answer=unsupported()
    elif re.search(r"\b(real|fictional|synthetic)\b",q) and not years:
        route="semantic";method="source passage"
        p=next((p for p in payload["pages"] if "fictional" in p["text"].lower()),None)
        answer="The report explicitly says ABC Company Fund and all figures are fictional and created for demonstration. This is not a real fund report or investment advice." if p else unsupported()
        if p:source_overrides=[{"page":p["number"],"section":p["section"],"excerpt":p["text"][:800]}]
    elif re.search(r"\b(reconcile|agree|disagree|conflict|inconsisten|mismatch|differ|difference)\w*\b",q) and ("quarter" in q or "nav" in q):
        route="hybrid"
        if not years:
            route="clarification";answer="Which year would you like to reconcile? The report contains historical annual tables for 2020–2025 and quarterly versions for 2023–2025."
        elif "quarter" in q:
            lines=[]
            for year in dict.fromkeys(years):
                annual=unique(find("nav",year,"historical"))
                closings=find("closing_nav",f"{year}-Q4")
                if not annual or not closings:continue
                selected.extend(annual+closings)
                lines.append(f"{year}: the annual section reports NAV {annual[0]['value']} on p. {annual[0]['source']['page']}. The quarterly section reports Q4 closing NAV "+", ".join(f"{f['value']} on p. {f['source']['page']}" for f in closings)+". These figures do not reconcile. The report does not establish which version is authoritative.")
            answer="\n\n".join(lines) or unsupported()
        else:
            year=years[0];current=unique(find("nav",year,"historical"));previous=unique(find("nav",str(int(year)-1),"historical"));reported=unique(find("fund_return",year,"historical"))
            if current and previous and reported:
                selected=previous+current+reported;computed=percentage_change(previous[0]["value"],current[0]["value"])
                answer=f"The {year} annual table reports a {reported[0]['value']}% return. NAV moves from {previous[0]['value']} to {current[0]['value']}, which implies {display(computed)}%. "+("The values differ; the report does not establish a reconciliation." if abs(computed-decimal(reported[0]['value']))>Decimal('.15') else "The difference is within the 0.15 percentage-point rounding tolerance.")
                add_calculation("(closing NAV / previous year NAV − 1) × 100",[previous[0]["value"],current[0]["value"]],computed,"percent",selected)
            else:answer=unsupported("A prior-year NAV and reported annual return are needed for this calculation; the required evidence is absent.")
    elif re.search(r"\b(q[1-4]|quarter|quarterly)\b",q) and not ("define" in q or "meaning" in q):
        if not years:
            route="clarification";answer="Which year do you mean: 2023, 2024, or 2025? There are multiple quarterly table versions for each year, so I will show page-specific figures rather than choose one silently."
        elif "compound" in q:
            year=years[0];grouped=defaultdict(list)
            for f in find("quarter_return"):
                if re.fullmatch(year+r"-Q[1-4]",f["period"]):grouped[f["source"]["page"]].append(f)
            lines=[]
            for page,observations in sorted(grouped.items()):
                observations.sort(key=lambda f:f["period"]);selected.extend(observations);result=compound([f["value"] for f in observations])
                lines.append(f"Page {page}: {', '.join(f['value']+'%' for f in observations)} compounds to {display(result)}% (simple sum: {display(sum(decimal(f['value']) for f in observations))}%).")
                add_calculation("(∏(1 + quarterly_return / 100) − 1) × 100",[f["value"] for f in observations],result,"percent",observations)
            answer="\n".join(lines) or unsupported()
        else:
            quarter=re.search(r"\bq([1-4])\b",q);quarter=quarter[1] if quarter else None;year=years[0];periods=[f"{year}-Q{quarter}"] if quarter else [f"{year}-Q{i}" for i in range(1,5)];lines=[]
            for period in periods:
                returns=find("quarter_return",period);bench=find("quarter_benchmark",period)
                for f in returns:
                    b=next((b for b in bench if b["source"]["page"]==f["source"]["page"]),None)
                    selected.append(f);selected.extend([b] if b else [])
                    line=f"{period} · p. {f['source']['page']}: fund return {f['value']}%"
                    if b:
                        gap=difference(f["value"],b["value"]);line+=f", benchmark {b['value']}%, difference {display(gap)} percentage points"
                        add_calculation("fund return − benchmark return",[f["value"],b["value"]],gap,"percentage points",[f,b])
                    lines.append(f"| {period} | p. {f['source']['page']} | {f['value']}% | {b['value']+'%' if b else '—'} | {display(gap) if b else '—'} |")
            answer=("### Quarterly performance\n\nEach source version is shown separately; conflicting figures are not averaged. Differences are in percentage points.\n\n| Quarter | Source | Fund return | Benchmark | Difference (pp) |\n| --- | --- | --- | --- | --- |\n"+"\n".join(lines)) if lines else unsupported()
    elif ("cagr" in q or "annualized" in q) and not ("what is" in q and not years):
        observations=sorted(unique(find("nav",classification="historical")),key=lambda f:f["period"])
        if years:observations=[f for f in observations if f["period"] in years]
        if len(observations)>=2:
            start,end=observations[0],observations[-1];n=int(end["period"])-int(start["period"]);result=((decimal(end["value"])/decimal(start["value"]))**(Decimal(1)/n)-1)*100;selected=[start,end]
            answer=f"The NAV-based CAGR from {start['period']} to {end['period']} is {display(result)}%, using {start['value']} and {end['value']} over {n} years. This is a derived NAV growth rate, distinct from the source-reported annual returns."
            add_calculation("((ending NAV / starting NAV)^(1 / years) − 1) × 100",[start["value"],end["value"],str(n)],result,"percent",selected)
        else:answer=unsupported("CAGR needs two reported historical NAV endpoints with distinct years.")
    elif re.search(r"\b(allocation|sector|technology|market risk|management expense|institutional|regional|india|investor|portfolio composition)\b",q) and not ("why" in q or "assumption" in q):
        dimensions=[f for f in facts if f["metric"]=="allocation"]
        group="Portfolio Allocation"
        if "risk" in q:group="Risk Profile"
        elif "expense" in q or "management" in q:group="Expense Breakdown"
        elif "investor" in q or "institutional" in q:group="Investor Mix"
        elif "regional" in q or "india" in q:group="Regional Exposure"
        observations=unique([f for f in dimensions if f["period"].lower()==group.lower()])
        matching=[f for f in observations if f.get("category","").lower() in q]
        if matching:observations=matching
        elif re.search(r"\b(largest|highest|biggest)\b",q) and observations:observations=[max(observations,key=lambda f:decimal(f["value"]))]
        selected=observations
        answer=f"{group} (source-reported): "+"; ".join(f"{f['category']} {f['value']}%" for f in observations)+". These are illustrative shares of this distribution, not a fund fee rate or real holdings." if observations else unsupported()
    elif re.search(r"\b(highest|best|lowest|worst)\b",q):
        classification="forecast" if "forecast" in q or "projected" in q else "historical";metric="nav" if "nav" in q else "fund_return";observations=unique(find(metric,classification=classification))
        if observations:
            best=(min if "lowest" in q or "worst" in q else max)(observations,key=lambda f:decimal(f["value"]));selected=[best]
            answer=f"{best['period']} has the {'lowest' if 'lowest' in q or 'worst' in q else 'highest'} {classification} source-reported {metric.replace('_',' ')}: {best['value']}{'%' if best['unit']=='percent' else ' NAV units'}. This ranking uses the table values without silently reconciling inconsistencies."
        else:answer=unsupported()
    elif numeric_intent and not explanation_intent or (numeric_intent and years and "assumption" not in q and "risk" not in q and "why" not in q):
        if not years:
            route="clarification";answer="Which year would you like to inspect? The historical tables cover 2020–2025, and forecast tables cover 2026–2030."
        else:
            lines=[]
            for year in dict.fromkeys(years):
                classification="forecast" if any(f["classification"]=="forecast" and f["period"]==year for f in facts) else "historical"
                metrics=[]
                if "nav" in q:metrics.append("nav")
                if "aum" in q or "assets under" in q:metrics.append("aum")
                if "return" in q or "perform" in q or "benchmark" in q:metrics.append("fund_return")
                if "benchmark" in q or "compare" in q:metrics.append("benchmark_return")
                if not metrics:metrics=["nav","fund_return"]
                observations=[]
                for metric in dict.fromkeys(metrics):observations+=unique(find(metric,year,classification))
                if not observations:continue
                selected.extend(observations)
                lines.append(f"{year} · {'Forecast, not a historical outcome' if classification=='forecast' else 'Historical, source-reported'}: "+"; ".join(f"{f['metric'].replace('_',' ')} {display(f['value'],1)} {f['unit']}" for f in observations)+".")
                fund=next((f for f in observations if f["metric"]=="fund_return"),None);bench=next((f for f in observations if f["metric"]=="benchmark_return"),None)
                if fund and bench:
                    gap=difference(fund["value"],bench["value"]);lines.append(f"The fund {'exceeds' if gap>=0 else 'trails'} the benchmark by {display(abs(gap))} percentage points.")
                    add_calculation("fund return − benchmark return",[fund["value"],bench["value"]],gap,"percentage points",[fund,bench])
            answer="\n".join(lines) or unsupported()
            if explanation_intent:route="hybrid"
    else:
        route="semantic";method="BM25 keyword retrieval"
        passages=retrieve(question,payload["chunks"])
        if payload.get("_semantic_passages"):
            passages=list({p["id"]:p for p in payload["_semantic_passages"]+passages}.values())[:6];method="BGE-small-en-v1.5 embeddings + pgvector cosine search + BM25"
        # Prefer purpose-specific narrative pages over sample-question/glossary
        # matches. This still selects source text; it never fills missing facts.
        wanted=[]
        if "assumption" in q or "scenario" in q:wanted=["forecast scenarios","forecast outlook"]
        elif "risk" in q or "limitation" in q:wanted=["risks and limitations"]
        elif any(w in q for w in ["define","meaning","what is nav","what is aum","stand for","glossary"]):wanted=["glossary and data dictionary"]
        if wanted:
            preferred=[c for w in wanted for c in payload["chunks"] if w in c["section"].lower()]
            passages=preferred[:4] or passages
        if "assumption" in q:
            observations=payload.get("assumptions",[])
            if years:observations=[a for a in observations if a["period"] in years]
            unique_assumptions={}
            for a in observations:unique_assumptions.setdefault((a["period"],a["text"]),a)
            if unique_assumptions:
                assumptions=list(unique_assumptions.values())
                answer="Source-reported forecast assumptions:\n\n"+"\n".join(f"{a['period']}: {a['text']} (p. {a['page']})." for a in assumptions)
                answer+="\n\nThese are fictional base-case assumptions, not predictions or guarantees."
                source_overrides=[{"page":a["page"],"section":a["section"],"excerpt":a["text"]} for a in assumptions]
        if provider.enabled("ENABLE_EMBEDDINGS"):
            try:
                from app.vector import search
                semantic=search(document_id,question)
                combined={p["id"]:p for p in semantic+passages}
                passages=list(combined.values())[:6];method="BGE-small-en-v1.5 embedding + BM25 keyword retrieval"
            except Exception:
                logger.exception("semantic_retrieval_failed",extra={"document_id":document_id})
                warnings.append("Semantic retrieval is unavailable; keyword retrieval was used.")
        if answer:
            pass
        elif not passages:
            route="unsupported";answer=unsupported()
        else:
            source_overrides=[{"page":p["page"],"section":p["section"],"excerpt":p["content"]} for p in passages]
            # Offline mode quotes the relevant opening narrative rather than
            # claiming an LLM has composed a semantic answer.
            lines=[]
            for p in passages[:3]:
                content=p["content"]
                stop=re.search(r"(?:Topic Key information|Year Projected NAV|Category Allocation|ABC Company Fund \|)",content)
                if stop:content=content[:stop.start()].strip()
                title=p["section"]
                if content.startswith(title):content=content[len(title):].strip()
                lines.append(f"{title} (p. {p['page']}): {content[:950]}")
            answer="The report states:\n\n"+"\n\n".join(lines)
            credentials=payload.get("_llm_credentials")
            if credentials or provider.enabled("ENABLE_LLM"):
                try:
                    composed=provider.compose(question,passages,credentials=credentials);answer=composed.answer;composer="llm";source_overrides=[s for s in source_overrides if s["page"] in composed.citation_pages]
                except Exception:
                    logger.exception("answer_composer_failed",extra={"document_id":document_id})
                    warnings.append("The explanation provider is unavailable or failed evidence validation. Showing source passages instead.")
    selected_ids={f["id"] for f in selected}
    # Attach findings for the same metric/period even when an identical repeated
    # observation has a different ID on another page.
    selected_keys={(f["metric"],f["period"]) for f in selected}
    equivalent_ids={f["id"] for f in facts if (f["metric"],f["period"]) in selected_keys}
    for issue in payload["issues"]:
        if issue["severity"]!="info" and equivalent_ids.intersection(issue["fact_ids"]):
            warnings.append(issue["description"])
    if any(f["classification"]=="forecast" for f in selected):warnings.append("Forecasts are scenario-based projections, not guarantees or historical outcomes.")
    if any("currency unresolved" in f["unit"] for f in selected):warnings.append("The source currency symbol is unresolved. NAV units and AUM crore are preserved without inferring a currency.")
    if payload["synthetic"] and route not in {"clarification","unsupported"}:warnings.append("All fund figures in this report are fictional demonstration data.")
    sources=[];seen=set()
    for f in selected:
        s=f["source"];key=(s["page"],s["table"])
        if key not in seen:
            sources.append({**s,"excerpt":f"{s['row']} · {s['column']}: {f['raw_text']}","fact_ids":[x["id"] for x in selected if x["source"]["page"]==s["page"]]});seen.add(key)
    for s in source_overrides:
        if (s["page"],None) not in seen:sources.append(s);seen.add((s["page"],None))
    # All citations are built from known extraction records.
    valid_pages={p["number"] for p in payload["pages"]}
    assert all(s["page"] in valid_pages for s in sources)
    if answer.startswith("The report does not contain sufficient") and not selected:route="unsupported"
    return {"answer":answer,"query_type":route,"calculations":calculations,"calculation":calculations[0] if calculations else None,
            "sources":sources,"warnings":list(dict.fromkeys(warnings)),"retrieval_method":method,"composer":composer,
            "latency_ms":int((time.perf_counter()-started)*1000),"source_fact_ids":sorted(selected_ids)}
