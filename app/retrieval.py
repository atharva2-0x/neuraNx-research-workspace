"""Page-aware BM25 baseline plus optional embedding ranking.

The offline path is explicitly keyword retrieval, not a claim of vector search.
No report text is sent to a provider unless the corresponding option is enabled.
"""
import math
import re
from collections import Counter

STOP = set("a an the of to for and or is are was were what which how did do does in on with it its this that be by from as at about report fund company illustrative sample data synthetic".split())
SYNONYMS = {"assumptions":"assumption", "risks":"risk", "forecast":"projected", "forecasts":"projected", "definition":"glossary", "defines":"glossary", "meaning":"glossary", "growth":"increases", "sector":"allocation"}


def tokenize(text):
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    return [SYNONYMS.get(t, t) for t in tokens if t not in STOP and len(t)>1]


def chunks_from_pages(pages):
    chunks = []
    for p in pages:
        # Paragraph-sized overlapping windows preserve table footnotes and page context.
        words = p["text"].split()
        for i in range(0, len(words), 180):
            content = " ".join(words[i:i+240])
            if content:
                chunks.append({"id":f"p{p['number']}-c{i//180}", "page":p["number"], "section":p["section"], "content":content})
    return chunks


def retrieve(question, chunks, limit=4):
    query = tokenize(question)
    if not query or not chunks:
        return []
    docs = [tokenize(c["section"]+" "+c["section"]+" "+c["content"]) for c in chunks]
    avg = sum(map(len, docs))/len(docs) or 1
    frequencies = Counter(t for doc in docs for t in set(doc))
    scored = []
    for chunk, tokens in zip(chunks, docs):
        counts = Counter(tokens)
        score = 0.0
        overlap = 0
        for term in set(query):
            tf = counts[term]
            if tf:
                overlap += 1
                idf = math.log(1+(len(docs)-frequencies[term]+.5)/(frequencies[term]+.5))
                score += idf*tf*2.5/(tf+1.5*(.25+.75*len(tokens)/avg))
        if overlap:
            scored.append({**chunk,"score":round(score,5),"overlap":overlap})
    scored.sort(key=lambda c:c["score"],reverse=True)
    # Repeated pages must not crowd out distinct evidence.
    result, seen = [], set()
    for c in scored:
        fingerprint = re.sub(r"Page \d+", "", c["content"]).strip()
        if fingerprint not in seen:
            result.append(c);seen.add(fingerprint)
        if len(result)==limit:
            break
    return result


def cosine(a,b):
    if not a or not b or len(a)!=len(b):
        return 0.0
    denom = math.sqrt(sum(x*x for x in a)*sum(x*x for x in b))
    return sum(x*y for x,y in zip(a,b))/denom if denom else 0.0
