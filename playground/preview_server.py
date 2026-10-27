"""Isolated Playground transport; runtime routes delegate to the Solution's bridge."""
import importlib
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

ROOT = Path(__file__).parent
DATA = Path(os.environ.get('PREVIEW_DATA_DIR', '/data'))


def bind_data_dir() -> None:
    # BUG-085: the generated KPI service reads PREVIEW_DATA_DIR to find kpis.sqlite. Set it to the folder this server
    # passes to the bridge. Only the server process sets it, so an import does not change the environment.
    os.environ.setdefault('PREVIEW_DATA_DIR', str(DATA))
MOCK = '--mock' in sys.argv


def _load_dotenv() -> None:
    # The deploy folder holds the env file (C1-8). An older root file still works.
    path = next((c for c in (ROOT.parent / 'deploy' / '.env', ROOT.parent / '.env') if c.is_file()), None)
    if path is None:
        return
    for raw in path.read_text(encoding='utf-8').splitlines():
        line = raw.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        key = key.strip()
        if not key or key in os.environ:
            continue
        value = value.strip().strip('"').strip("'")
        os.environ[key] = value


_load_dotenv()
_SRC = ROOT.parent / 'src'
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


def read_precord():
    # BUG-109: read the Precord data the way the Solution does, so one request never mixes two copies.
    try:
        from solution.playground_paths import precord
    except ImportError:
        return json.loads((ROOT/'src/precord.json').read_text())
    return precord()


def read_state(key, default):
    with sqlite3.connect(DATA/'preview.sqlite') as db:
        db.execute('CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
        row=db.execute('SELECT value FROM state WHERE key=?',(key,)).fetchone()
        return json.loads(row[0]) if row else default


def write_state(key, value):
    with sqlite3.connect(DATA/'preview.sqlite') as db:
        db.execute('CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
        db.execute('INSERT INTO state VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(key,json.dumps(value)))


class Handler(SimpleHTTPRequestHandler):
    def respond(self,status,value):
        body=json.dumps(value).encode();self.send_response(status)
        self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)

    def list_directory(self,path):
        self.send_error(404);return None

    def route(self,method):
        path=unquote(urlsplit(self.path).path)
        if path=='/health': self.respond(200,{'status':'ok','fidelity':'mock system'});return True
        if path=='/cases' and method=='GET':
            query=parse_qs(urlsplit(self.path).query)
            try:
                limit=min(max(int(query.get('limit',['100'])[0]),1),500)
                offset=max(int(query.get('offset',['0'])[0]),0)
            except ValueError:
                self.respond(422,{'error':'Case pagination must use integers'});return True
            try:
                from solution.cases import CaseStore
                from solution.masking import mask_cases
                cases=mask_cases(CaseStore().list_cases(limit,offset))
            except (ImportError, RuntimeError):
                self.respond(503,{'error':'The Solution case database is not configured'});return True
            self.respond(200,{'cases':cases});return True
        if not path.startswith('/playground/'): return False
        route=path.removeprefix('/playground/')
        length=int(self.headers.get('Content-Length','0'))
        if length>1048576: self.respond(413,{'error':'Request too large'});return True
        try: body=json.loads(self.rfile.read(length)) if length else {}
        except ValueError: self.respond(400,{'error':'Invalid JSON'});return True
        metadata=read_precord()
        user=read_state('user',{'id':'preview-operator','name':'Preview operator','role':'sme'})
        if route=='session': self.respond(200,user);return True
        if route=='session/role' and method=='PUT':
            if body.get('role') not in {'sme','technical'}: self.respond(422,{'error':'Unknown role'});return True
            user['role']=body['role'];write_state('user',user);self.respond(200,user);return True
        if route=='overview/figures':
            agents=metadata['files']['spec/agents.yaml'];self.respond(200,{'agentsBuilt':{'built':sum(bool(a.get('built')) for a in agents),'total':len(agents)}});return True
        if route=='next-steps/draft':
            if method=='PUT': write_state('draft',body)
            self.respond(200,read_state('draft',{'tickedItems':[],'comments':{},'tickedRecommendations':[],'freeText':''}));return True
        if route=='next-steps/send' and method=='POST':
            draft=body.get('draft',{});actions=[];proposals=read_state('proposals',[])
            for identity in dict.fromkeys(draft.get('tickedItems',[])+draft.get('tickedRecommendations',[])):
                text=draft.get('comments',{}).get(identity) or draft.get('freeText') or identity
                proposals.append({'kind':'AddOpenItem','tenant_id':metadata['tenant_id'],'requirement_id':metadata['requirement_id'],
                    'actor':user['id'],'reason':text,'build_revision':metadata['build']['buildId'],'expected_hash':metadata['open_items_hash'],
                    'provenance':identity,'subject':text,'detail':'Raised in the Solution Playground for '+identity+'.'})
                actions.append({'itemId':identity,'text':text,'comment':draft.get('comments',{}).get(identity,''),
                    'freeText':draft.get('freeText',''),'userId':user['id'],'userName':user['name'],'role':user['role'],
                    'sentAt':datetime.now(timezone.utc).isoformat(),'buildId':metadata['build']['buildId'],
                    'kind':'open_item' if identity in draft.get('tickedItems',[]) else 'recommendation'})
            write_state('proposals',proposals);self.respond(200,actions);return True
        if route=='sign-off':
            state=read_state('sign-off',{'records':[],'invitees':[]})
            if method=='POST':
                if body.get('tag') not in {'GOOD TO GO','NOT YET'}: self.respond(422,{'error':'Unknown decision'});return True
                state['records'].append({'userId':user['id'],'name':user['name'],'role':user['role'],'tag':body['tag'],
                    'comment':body.get('comment',''),'at':datetime.now(timezone.utc).isoformat(),'buildId':metadata['build']['buildId']})
                write_state('sign-off',state)
            self.respond(200,state);return True
        try:
            bridge=importlib.import_module('solution.playground_bridge')
        except ModuleNotFoundError as error:
            if error.name != 'solution.playground_bridge' and error.name != 'solution': raise
            self.respond(404,{'error':'No runtime data yet'});return True
        try:
            result=bridge.dispatch(method,route,body,DATA)
        except LookupError:
            self.respond(404,{'error':'No runtime data yet'});return True
        except ValueError as error:
            self.respond(422,{'error':str(error)});return True
        except TypeError as error:
            self.respond(500,{'error':str(error)});return True
        self.respond(200,result);return True

    def serve_ui(self):
        path=unquote(urlsplit(self.path).path)
        if not path.startswith('/ui/'): return False
        root=(ROOT.parent/'ui').resolve()
        target=(ROOT.parent/path.lstrip('/')).resolve()
        try: target.relative_to(root)
        except ValueError: self.send_error(404);return True
        if not target.is_file(): self.send_error(404);return True
        body=target.read_bytes();self.send_response(200)
        if target.suffix=='.html': ctype='text/html; charset=utf-8'
        elif target.suffix=='.js': ctype='application/javascript'
        elif target.suffix=='.css': ctype='text/css'
        else: ctype='application/octet-stream'
        self.send_header('Content-Type',ctype);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body);return True

    def do_GET(self):
        if self.serve_ui(): return
        if not self.route('GET'): super().do_GET()
    def do_POST(self):
        if MOCK:
            self.respond(501,{'fidelity':'mock system','error':'Mock response requires a declared contract fixture'});return
        if not self.route('POST'): self.send_error(404)
    def do_PUT(self):
        if not self.route('PUT'): self.send_error(404)


if __name__=='__main__':
    bind_data_dir()
    DATA.mkdir(parents=True,exist_ok=True)
    ThreadingHTTPServer(('0.0.0.0',8000),partial(Handler,directory=str(ROOT/'dist'))).serve_forever()
