"""Build the Vercel frontend and private OCI workspace proxy.

The OCI service will own durable ingestion. This portable demo does not pretend
that a serverless filesystem is a durable database.
"""
import json
import shutil
from pathlib import Path
from app.db import Session,Document,metadata
from app.pipeline import pdf_path
import pdfplumber

def main():
    root=Path('deploy/vercel');public=root/'public';public.mkdir(parents=True,exist_ok=True)
    (root/'api').mkdir(exist_ok=True);(root/'app').mkdir(exist_ok=True)
    with Session() as session:
        doc=session.get(Document,'d3d7c69a8629c647cc9e6aa4');payload=doc.payload;meta=metadata(doc)
    for name in ['__init__.py','answering.py','calculations.py','retrieval.py','provider.py']:
        shutil.copy2(Path('app')/name,root/'app'/name)
    (root/'evidence.json').write_text(json.dumps({'metadata':meta,'payload':payload}))
    shutil.copytree('ui',public/'static',dirs_exist_ok=True)
    html=(Path('ui/index.html').read_text().replace('Local, private workspace','Private browser workspace').replace('Local workspace','Private browser workspace').replace('<body>','<body data-hosted="vercel">'))
    (public/'index.html').write_text(html.replace('Up to 25 MB','Up to 4 MB'))
    js=(public/'static/app.js').read_text()
    js=js.replace('25*1024*1024','4*1024*1024').replace('smaller than 25 MB','smaller than 4 MB')
    (public/'static/app.js').write_text(js)
    out=public/'pages';out.mkdir(exist_ok=True)
    with pdfplumber.open(pdf_path(doc.id)) as pdf:
        for i,p in enumerate(pdf.pages):p.to_image(resolution=100).save(out/f'{i+1}.png')
    shutil.copy2(pdf_path(doc.id),public/'sample-report.pdf')
    (root/'requirements.txt').write_text('fastapi>=0.115,<1\nhttpx>=0.28,<1\npydantic>=2,<3\n')
    (root/'vercel.json').write_text(json.dumps({'version':2,'outputDirectory':'public','functions':{'api/index.py':{'includeFiles':'*.json','maxDuration':60}},'rewrites':[
        
        
        {'source':'/documents','destination':'/api/index?route=/documents'},
        {'source':'/documents/:path*','destination':'/api/index?route=/documents/:path*'},
        {'source':'/chat/query','destination':'/api/index?route=/chat/query'},
        {'source':'/health','destination':'/api/index?route=/health'}]},indent=2))
    shutil.copy2('deployment/vercel_api.py',root/'api/index.py')
    backend=Path('deployment/backend.json')
    if backend.exists():shutil.copy2(backend,root/'backend.json')
    deck=Path('output/Fund_Intelligence_FDE_Deck.html')
    if deck.exists():shutil.copy2(deck,public/'deck.html')
    shutil.make_archive('output/fund-intelligence-vercel','zip',root)
    print('Prepared deploy/vercel and output/fund-intelligence-vercel.zip')

if __name__=='__main__':main()
