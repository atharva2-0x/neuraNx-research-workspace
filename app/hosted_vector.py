"""Local neural embeddings and tenant-filtered PostgreSQL vector retrieval."""
import json, os, threading
import psycopg2
from fastembed import TextEmbedding
_MODEL=None
_LOCK=threading.Lock()
MODEL='BAAI/bge-small-en-v1.5'
def connect():return psycopg2.connect(os.environ.get('VECTOR_DATABASE_URL','dbname=neuranx user=opc host=/var/run/postgresql'))
def model():
    global _MODEL
    if _MODEL is None:_MODEL=TextEmbedding(model_name=MODEL,threads=1,cache_dir='/opt/neuranx/models')
    return _MODEL
def initialize():
    with connect() as db,db.cursor() as c:
        c.execute('CREATE EXTENSION IF NOT EXISTS vector')
        c.execute('CREATE TABLE IF NOT EXISTS report_vectors (workspace text, document_id text, chunk_id text, payload jsonb, embedding vector(384), PRIMARY KEY(workspace,document_id,chunk_id))')
        c.execute('CREATE INDEX IF NOT EXISTS report_vectors_hnsw ON report_vectors USING hnsw (embedding vector_cosine_ops)')
def index(workspace,document_id,chunks):
    with _LOCK:
        with connect() as db,db.cursor() as c:
            c.execute('SELECT count(*) FROM report_vectors WHERE workspace=%s AND document_id=%s',(workspace,document_id))
            if c.fetchone()[0]==len(chunks):return
            vectors=model().embed([x['content'] for x in chunks],batch_size=4)
            for chunk,vector in zip(chunks,vectors):
                c.execute('INSERT INTO report_vectors VALUES (%s,%s,%s,%s,%s::vector) ON CONFLICT(workspace,document_id,chunk_id) DO UPDATE SET payload=EXCLUDED.payload,embedding=EXCLUDED.embedding',(workspace,document_id,chunk['id'],json.dumps(chunk),json.dumps(vector.tolist())))
def search(workspace,document_id,question,chunks):
    index(workspace,document_id,chunks)
    with _LOCK:vector=next(model().query_embed(question)).tolist()
    with connect() as db,db.cursor() as c:
        c.execute('SELECT payload,1-(embedding <=> %s::vector) FROM report_vectors WHERE workspace=%s AND document_id=%s ORDER BY embedding <=> %s::vector LIMIT 4',(json.dumps(vector),workspace,document_id,json.dumps(vector)))
        return [{**p,'score':float(score)} for p,score in c.fetchall()]
