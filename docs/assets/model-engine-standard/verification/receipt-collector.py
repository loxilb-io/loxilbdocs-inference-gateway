"""QA-only transparent backend receipt collector; never a product patch."""
import argparse, hashlib, http.client, json, pathlib, threading, time, uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ap=argparse.ArgumentParser();ap.add_argument('--bind',required=True);ap.add_argument('--port',type=int,default=8101);ap.add_argument('--upstream-port',type=int,default=8000);ap.add_argument('--directory',required=True);args=ap.parse_args()
root=pathlib.Path(args.directory);root.mkdir(mode=0o700,parents=True,exist_ok=True);lock=threading.Lock()
hop={'connection','keep-alive','proxy-authenticate','proxy-authorization','te','trailer','transfer-encoding','upgrade','content-length','server','date'}
class Handler(BaseHTTPRequestHandler):
 protocol_version='HTTP/1.0'
 def log_message(self,*a):pass
 def handle_one(self):
  rid=self.headers.get('X-ModeQA-Request-ID') or ('probe-'+uuid.uuid4().hex)
  rid=''.join(c for c in rid if c.isalnum() or c in '-_')[:100]
  received=time.time();body=b'';response=b'';status=None;error=None;completed=False;request_file=None
  try:
   if self.headers.get('Transfer-Encoding','').lower()=='chunked':
    pieces=[]
    while True:
     size=int(self.rfile.readline().split(b';')[0],16)
     if not size:
      while self.rfile.readline() not in (b'\r\n',b'\n',b''):pass
      break
     pieces.append(self.rfile.read(size));assert self.rfile.read(2)==b'\r\n'
    body=b''.join(pieces)
   else:body=self.rfile.read(int(self.headers.get('Content-Length',0)))
   request_file=rid+'-'+uuid.uuid4().hex[:6]+'.request.json'
   (root/request_file).write_bytes(body)
   headers={k:v for k,v in self.headers.items() if k.lower() not in hop and k.lower()!='host'}
   headers['Content-Length']=str(len(body));headers['Connection']='close'
   conn=http.client.HTTPConnection('127.0.0.1',args.upstream_port,timeout=180)
   conn.request(self.command,self.path,body,headers);resp=conn.getresponse();status=resp.status
   self.send_response(status)
   for k,v in resp.getheaders():
    if k.lower() not in hop:self.send_header(k,v)
   self.send_header('X-ModeQA-Backend',args.bind);self.send_header('Connection','close');self.end_headers()
   with (root/(rid+'-'+uuid.uuid4().hex[:6]+'.response')).open('wb') as out:
    while True:
     chunk=resp.read1(65536)
     if not chunk:break
     out.write(chunk);response+=chunk;self.wfile.write(chunk);self.wfile.flush()
   completed=True;conn.close()
  except Exception as exc:
   error=type(exc).__name__+': '+str(exc)
   if status is None:
    try:self.send_error(502,'QA receipt upstream error')
    except Exception:pass
  finally:
   record={'requestId':rid,'requestFile':request_file,'worker':args.bind,'method':self.command,'path':self.path,'started':received,'ended':time.time(),'requestBytes':len(body),'requestSha256':hashlib.sha256(body).hexdigest(),'responseBytes':len(response),'responseSha256':hashlib.sha256(response).hexdigest(),'httpStatus':status,'upstreamComplete':completed,'error':error}
   with lock:
    with (root/'receipts.jsonl').open('a') as f:f.write(json.dumps(record)+'\n')
 def do_GET(self):self.handle_one()
 def do_POST(self):self.handle_one()
 def do_DELETE(self):self.handle_one()
ThreadingHTTPServer((args.bind,args.port),Handler).serve_forever()
