"""Run the supplied golden bank against a live endpoint; persist no credentials."""
import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import httpx


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('base_url')
    parser.add_argument('--bank',default='output/rag-golden-evaluation-2026-11-08.json')
    parser.add_argument('--output',default='output/llm-live-check.json')
    args=parser.parse_args()
    bank=json.loads(Path(args.bank).read_text())
    def run(case):
        response=httpx.post(args.base_url.rstrip('/')+'/chat/query',json={
            'document_id':'d3d7c69a8629c647cc9e6aa4','question':case['question']},timeout=60)
        response.raise_for_status()
        result={'id':case['id'],'question':case['question'],'expected':case['expected'],**response.json()}
        print(json.dumps({k:result.get(k) for k in ['id','composer','llm','answer']},ensure_ascii=False),flush=True)
        return result
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(run,bank['cases']))
    output={'base_url':args.base_url,'llm_used':sum(r.get('llm',{}).get('used',False) for r in results),'total':len(results),'results':results}
    Path(args.output).write_text(json.dumps(output,indent=2))
    print(f"LLM used: {output['llm_used']}/{output['total']}; {args.output}")


if __name__=='__main__':main()
