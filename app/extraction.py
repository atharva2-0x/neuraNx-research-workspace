"""Table-first extraction with immutable raw tokens and native PDF geometry.

This adapter recognizes the report's annual, quarterly, allocation and forecast
tables by headers, not by hardcoded page numbers or copied planning values.
"""
import hashlib
import json
import re
import shutil
import subprocess
import zipfile
import xml.etree.ElementTree as ET
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from io import BytesIO
from pathlib import Path
import pdfplumber
from app.models import Fact, Source

MAX_PAGES = 200


def numeric(token):
    token = str(token or "").strip().replace(",", "").replace("%", "").replace("*", "").replace("−", "-")
    if not re.fullmatch(r"[+-]?\d+(?:\.\d+)?", token):
        raise ValueError(f"Not a numeric source token: {token!r}")
    return Decimal(token)


def extract_pdf(path: Path, progress=None):
    pages = []
    with pdfplumber.open(path) as pdf:
        if not pdf.pages or len(pdf.pages) > MAX_PAGES:
            raise ValueError(f"PDF must contain between 1 and {MAX_PAGES} pages")
        for index, page in enumerate(pdf.pages):
            text = page.extract_text(layout=False) or ""
            method = "pdfplumber · native text"
            warnings = []
            if len(text.strip()) < 50:
                if shutil.which("tesseract"):
                    image = BytesIO()
                    page.to_image(resolution=180).original.save(image, format="PNG")
                    result = subprocess.run(["tesseract", "stdin", "stdout", "--psm", "3"], input=image.getvalue(), capture_output=True, timeout=90)
                    if result.returncode == 0:
                        text = result.stdout.decode("utf-8", errors="replace")
                        method = "tesseract · OCR"
                        warnings.append("OCR text requires review; native table geometry may be unavailable")
                    else:
                        warnings.append("OCR failed; inspect the original page")
                else:
                    warnings.append("Low-text page: OCR required; Tesseract is not installed")
            section = next((line.strip() for line in text.splitlines() if line.strip()), f"Page {index+1}")
            tables = []
            for tindex, table in enumerate(page.find_tables()):
                rows = table.extract()
                tables.append({"id": f"p{index+1}-t{tindex+1}", "rows": rows,
                               "bbox": list(table.bbox),
                               "cells": [[list(c) if c else None for c in r.cells] for r in table.rows]})
            glyphs = [c for c in page.chars if c.get("fontname") == "ZapfDingbats" and c.get("text") == "n"]
            if glyphs:
                warnings.append("Source currency glyph renders as a square; currency is not inferred")
            observations = chart_observations(page, text)
            pages.append({"number": index+1, "text": text, "section": section,
                          "char_count": len(text), "method": method, "warnings": warnings,
                          "tables": tables, "chart_observations": observations})
            if progress:
                progress(index+1, len(pdf.pages))
    if not any(p["char_count"] >= 50 for p in pages):
        raise ValueError("No usable text was extracted. This PDF may require OCR; install Tesseract or upload a text-based PDF.")
    return pages


def extract_docx(path: Path, progress=None):
    pages = []
    with zipfile.ZipFile(path) as z:
        if "word/document.xml" not in z.namelist():
            raise ValueError("Invalid Word document: missing word/document.xml")
        xml_content = z.read("word/document.xml")
        tree = ET.fromstring(xml_content)
        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        
        paragraphs = []
        for p in tree.iterfind(".//w:p", ns):
            texts = [t.text for t in p.iterfind(".//w:t", ns) if t.text]
            if texts:
                paragraphs.append("".join(texts))
        
        tables = []
        for tindex, tbl in enumerate(tree.iterfind(".//w:tbl", ns)):
            rows = []
            for tr in tbl.iterfind(".//w:tr", ns):
                row = []
                for tc in tr.iterfind(".//w:tc", ns):
                    cell_texts = [t.text for t in tc.iterfind(".//w:t", ns) if t.text]
                    row.append(" ".join(cell_texts))
                if row:
                    rows.append(row)
            if rows:
                tables.append({"id": f"p1-t{tindex+1}", "rows": rows, "bbox": [0, 0, 0, 0], "cells": []})
        
        full_text = "\n\n".join(paragraphs) if paragraphs else ""
        if not full_text.strip() and not tables:
            raise ValueError("No usable text or tables found in the Word document")
        
        # Split into logical pages if long (> 2500 chars), else single page
        chunks = [full_text[i:i+2500] for i in range(0, max(len(full_text), 1), 2500)]
        for idx, chunk_text in enumerate(chunks):
            sec = next((l.strip() for l in chunk_text.splitlines() if l.strip()), f"Section {idx+1}")
            page_tables = tables if idx == 0 else []
            pages.append({
                "number": idx + 1,
                "text": chunk_text,
                "section": sec,
                "char_count": len(chunk_text),
                "method": "docx · native text",
                "warnings": [],
                "tables": page_tables,
                "chart_observations": []
            })
            if progress:
                progress(idx + 1, len(chunks))
    return pages


def extract_txt(path: Path, progress=None):
    pages = []
    content = path.read_text(encoding="utf-8", errors="replace")
    if not content.strip():
        raise ValueError("Text file is empty")
    chunks = [content[i:i+2500] for i in range(0, max(len(content), 1), 2500)]
    for idx, chunk_text in enumerate(chunks):
        sec = next((l.strip() for l in chunk_text.splitlines() if l.strip()), f"Page {idx+1}")
        pages.append({
            "number": idx + 1,
            "text": chunk_text,
            "section": sec,
            "char_count": len(chunk_text),
            "method": "txt · plain text",
            "warnings": [],
            "tables": [],
            "chart_observations": []
        })
        if progress:
            progress(idx + 1, len(chunks))
    return pages


def extract_json(path: Path, progress=None):
    pages = []
    raw = path.read_text(encoding="utf-8", errors="replace")
    try:
        data = json.loads(raw)
    except Exception as exc:
        raise ValueError(f"Invalid JSON format: {exc}") from exc
    
    tables = []
    # If the JSON contains an array of tabular objects, extract as a table
    if isinstance(data, list) and data and all(isinstance(x, dict) for x in data):
        headers = list(data[0].keys())
        rows = [headers]
        for item in data:
            rows.append([str(item.get(h, "")) for h in headers])
        tables.append({"id": "p1-t1", "rows": rows, "bbox": [0, 0, 0, 0], "cells": []})
        formatted_text = json.dumps(data, indent=2)
    elif isinstance(data, dict):
        # Look for table structures or nested arrays
        formatted_text = json.dumps(data, indent=2)
        tcount = 1
        for k, v in data.items():
            if isinstance(v, list) and v and all(isinstance(x, dict) for x in v):
                hdrs = list(v[0].keys())
                rws = [hdrs]
                for item in v:
                    rws.append([str(item.get(h, "")) for h in hdrs])
                tables.append({"id": f"p1-t{tcount}", "rows": rws, "bbox": [0, 0, 0, 0], "cells": []})
                tcount += 1
    else:
        formatted_text = str(data)

    chunks = [formatted_text[i:i+2500] for i in range(0, max(len(formatted_text), 1), 2500)]
    for idx, chunk_text in enumerate(chunks):
        sec = next((l.strip() for l in chunk_text.splitlines() if l.strip()), f"Record {idx+1}")
        pages.append({
            "number": idx + 1,
            "text": chunk_text,
            "section": sec,
            "char_count": len(chunk_text),
            "method": "json · structured text",
            "warnings": [],
            "tables": tables if idx == 0 else [],
            "chart_observations": []
        })
        if progress:
            progress(idx + 1, len(chunks))
    return pages


def extract_document(path: Path, filename: str, progress=None):
    ext = Path(filename).suffix.lower()
    if ext == ".pdf":
        return extract_pdf(path, progress)
    elif ext in {".docx", ".doc"}:
        return extract_docx(path, progress)
    elif ext in {".txt", ".text", ".md", ".csv"}:
        return extract_txt(path, progress)
    elif ext == ".json":
        return extract_json(path, progress)
    else:
        # Default attempt text extraction
        return extract_txt(path, progress)



def chart_observations(page, text):
    """Read native vector axes. The highest tick is NOT the axis maximum."""
    if "Projected NAV path" not in text:
        return []
    words = page.extract_words()
    candidates = [line for line in page.lines if abs(line["x0"]-line["x1"]) < .1 and line["bottom"]-line["top"] > 70]
    observations = []
    for axis in candidates:
        ticks = [w for w in words if re.fullmatch(r"\d+(?:\.\d+)?", w["text"]) and
                 0 < axis["x0"]-w["x1"] < 20 and axis["top"]-4 < w["top"] < axis["bottom"]+4]
        if len(ticks) < 3:
            continue
        ticks.sort(key=lambda w: float(w["text"]))
        low, high = ticks[0], ticks[-1]
        ylow = (low["top"]+low["bottom"])/2
        yhigh = (high["top"]+high["bottom"])/2
        scale = (float(high["text"])-float(low["text"]))/(ylow-yhigh)
        estimated_max = float(low["text"])+(ylow-axis["top"])*scale
        observations.append({"kind": "native_vector_axis", "highest_labeled_tick": float(high["text"]),
                             "estimated_axis_max": round(estimated_max, 1), "bbox": [axis["x0"], axis["top"], axis["x1"], axis["bottom"]],
                             "method": "Native labels and vector geometry; estimate requires visual review"})
    return observations


def normalize(pages):
    facts = []
    assumptions = []
    warnings = []
    for page in pages:
        for table in page["tables"]:
            rows = table["rows"]
            if len(rows) < 2:
                continue
            header = [str(c or "").replace("\n", " ") for c in rows[0]]
            joined = " ".join(header).lower()
            def add(row_index, column, metric, period, classification="historical", category=None):
                row = rows[row_index]
                if column >= len(row):
                    return
                token = str(row[column] or "")
                try:
                    value = numeric(token)
                except (ValueError, InvalidOperation):
                    if token.strip() not in {"", "—", "-"}:
                        warnings.append({"page": page["number"], "table": table["id"], "token": token, "reason": "Unparseable numeric cell"})
                    return
                unit = "percentage points" if metric == "excess_return" else "percent" if "return" in metric or metric in {"allocation", "quarter_benchmark"} else "crore (currency unresolved)" if metric == "aum" else "NAV units (currency unresolved)"
                bbox = None
                if row_index < len(table["cells"]) and column < len(table["cells"][row_index]):
                    bbox = table["cells"][row_index][column]
                identity = f"{page['number']}:{table['id']}:{row_index}:{column}:{metric}"
                fact = Fact(id=hashlib.sha256(identity.encode()).hexdigest()[:16], metric=metric, period=period,
                            value=value, unit=unit, classification=classification, category=category,
                            raw_text=token, source=Source(page=page["number"], section=page["section"],
                            table=table["id"], row=str(row[0]), column=header[column], bbox=bbox), confidence=.97)
                facts.append(fact.model_dump(mode="json"))
            if "year-end nav" in joined and "annual return" in joined:
                for ri, row in enumerate(rows[1:], 1):
                    if re.fullmatch(r"20\d{2}", str(row[0] or "")):
                        for ci, metric in [(1,"nav"),(2,"fund_return"),(3,"benchmark_return"),(4,"excess_return")]:
                            add(ri, ci, metric, str(row[0]))
            elif "opening nav" in joined and "closing nav" in joined:
                year_match = re.search(r"20\d{2}", page["section"])
                for ri, row in enumerate(rows[1:], 1):
                    label = str(row[0] or "")
                    match = re.search(r"Q([1-4])\s+(20\d{2})", label)
                    if match:
                        period = f"{match[2]}-Q{match[1]}"
                    elif "full year" in label.lower() and year_match:
                        period = f"{year_match[0]}-FY-quarterly"
                    else:
                        continue
                    for ci, metric in [(1,"opening_nav"),(2,"closing_nav"),(3,"quarter_return"),(4,"quarter_benchmark")]:
                        add(ri, ci, metric, period)
            elif "projected nav" in joined and "expected return" in joined:
                for ri, row in enumerate(rows[1:], 1):
                    if not re.fullmatch(r"20\d{2}", str(row[0] or "")):
                        continue
                    for ci, metric in [(1,"nav"),(2,"fund_return"),(3,"aum")]:
                        add(ri, ci, metric, str(row[0]), "forecast")
                    if len(row) > 4 and row[4]:
                        assumptions.append({"period": str(row[0]), "text": row[4], "page": page["number"], "section": page["section"]})
            elif "category" in joined and "allocation" in joined:
                dimension = re.sub(r"^Portfolio Analysis\s*[—–-]\s*", "", page["section"], flags=re.I)
                for ri, row in enumerate(rows[1:], 1):
                    if row[0]:
                        add(ri, 1, "allocation", dimension, category=str(row[0]))
    return facts, assumptions, warnings


def summarize(facts):
    """Collapse identical observations for display only. All originals remain."""
    annual, forecast, allocation = {}, {}, {}
    for fact in facts:
        metric, period, classification = fact["metric"], fact["period"], fact["classification"]
        if re.fullmatch(r"20\d{2}", period):
            target = forecast if classification == "forecast" else annual
            entry = target.setdefault(period, {"year": period, "nav": None, "fund_return": None, "benchmark_return": None,
                                               "aum": None, "classification": classification, "page": fact["source"]["page"]})
            if metric in entry and entry[metric] is None:
                entry[metric] = fact["value"]
        if metric == "allocation":
            group = allocation.setdefault(period, {"name": period, "rows": [], "page": fact["source"]["page"]})
            if not any(r["category"]==fact["category"] and r["value"]==fact["value"] for r in group["rows"]):
                group["rows"].append({"category": fact["category"], "value": fact["value"]})
    return {"annual": [annual[y] for y in sorted(annual)], "forecast": [forecast[y] for y in sorted(forecast)], "allocations": list(allocation.values())}
