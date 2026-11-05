import os,sqlite3,secrets,hashlib,hmac,io,base64,time
from datetime import date,datetime,timezone
from zoneinfo import ZoneInfo
from contextlib import contextmanager
from pathlib import Path
from fastapi import FastAPI,HTTPException,Request,Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel,Field
import qrcode
ROOT=Path(__file__).resolve().parent
DB=Path(os.getenv('MAPLE_DB',str(ROOT/'maple.sqlite3')))
DB.parent.mkdir(parents=True,exist_ok=True)
app=FastAPI(title='Maple Rewards V5', docs_url=None, redoc_url=None)
app.mount('/static',StaticFiles(directory=ROOT/'static'),name='static')
@app.middleware('http')
async def check_request_origin(request:Request,call_next):
 # Reject cross-origin browser state changes. Production requires HTTPS + secure cookies.
 if request.method in ('POST','PUT','PATCH','DELETE'):
  origin=request.headers.get('origin')
  allowed=os.getenv('MAPLE_PUBLIC_ORIGIN','').rstrip('/')
  if origin and allowed and origin.rstrip('/')!=allowed:
   return Response('Origen no autorizado',status_code=403)
  if origin and not allowed:
   host=request.headers.get('host','')
   if origin.rstrip('/') not in ('http://'+host,'https://'+host):
    return Response('Origen no autorizado',status_code=403)
 return await call_next(request)
@app.get('/healthz')
def healthz():return {'status':'ok'}
def db():
 c=sqlite3.connect(DB,timeout=10,isolation_level=None);c.row_factory=sqlite3.Row;c.execute('PRAGMA foreign_keys=ON');c.execute('PRAGMA busy_timeout=10000');return c

def init():
 with db() as c:
  c.executescript('''CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY,name TEXT NOT NULL,email TEXT NOT NULL UNIQUE,password_hash TEXT NOT NULL,salt TEXT NOT NULL,birthday TEXT,marketing INTEGER NOT NULL DEFAULT 0,role TEXT NOT NULL DEFAULT 'customer',qr_token TEXT NOT NULL UNIQUE,birthday_year INTEGER);
CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES users(id),expires INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS ledger(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id TEXT NOT NULL REFERENCES users(id),delta INTEGER NOT NULL,reason TEXT NOT NULL,reference TEXT UNIQUE,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS redemptions(id TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES users(id),kind TEXT NOT NULL,created_at TEXT NOT NULL);
''')
init()
def pwdhash(password,salt):return hashlib.pbkdf2_hmac('sha256',password.encode(),bytes.fromhex(salt),250000).hex()
def now():return datetime.now(timezone.utc).isoformat()
def local_today():return datetime.now(ZoneInfo("America/Argentina/Buenos_Aires")).date()
def tokenhash(s):return hashlib.sha256(s.encode()).hexdigest()
def new_session(c,user_id,response):
 token=secrets.token_urlsafe(32);c.execute('INSERT INTO sessions VALUES(?,?,?)',(tokenhash(token),user_id,int(time.time())+7*86400));response.set_cookie('maple_session',token,httponly=True,secure=os.getenv('MAPLE_COOKIE_SECURE','0')=='1',samesite='lax',max_age=7*86400,path='/')
def auth(request,admin=False):
 token=request.cookies.get('maple_session','')
 if not token:raise HTTPException(401,'Iniciá sesión')
 with db() as c:
  u=c.execute('SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=? AND s.expires>?',(tokenhash(token),int(time.time()))).fetchone()
 if not u:raise HTTPException(401,'Sesión inválida')
 if admin and u['role']!='admin':raise HTTPException(403,'Solo administradores')
 return u

def balance(c,uid):return c.execute('SELECT COALESCE(SUM(delta),0) FROM ledger WHERE user_id=?',(uid,)).fetchone()[0]
def profile(c,u):
 return {'id':u['id'],'name':u['name'],'email':u['email'],'birthday':u['birthday'],'role':u['role'],'stamps':balance(c,u['id']),'birthday_available':birthday_available(u)}
def birthday_available(u):
 if not u['birthday']:return False
 try:return u['birthday'][5:]==local_today().isoformat()[5:] and u['birthday_year']!=local_today().year
 except:return False
class Signup(BaseModel):
 name:str=Field(min_length=2,max_length=80);email:str;password:str=Field(min_length=10,max_length=128);birthday:str|None=None;marketing:bool=False
class Login(BaseModel):email:str;password:str
class Sale(BaseModel):customer_id:str;quantity:int=Field(ge=1,le=100);sale_id:str=Field(min_length=3,max_length=120)
class Refund(BaseModel):sale_id:str
class Redeem(BaseModel):customer_id:str;kind:str='stamps'
@app.get('/')
def home():return FileResponse(ROOT/'static'/'index.html')
@app.post('/api/signup')
def signup(body:Signup,response:Response):
 email=body.email.strip().lower()
 if '@' not in email or len(email)>254:raise HTTPException(400,'Correo inválido')
 if body.birthday:
  try:date.fromisoformat(body.birthday)
  except:raise HTTPException(400,'Fecha inválida')
 uid=secrets.token_hex(12);salt=secrets.token_hex(16)
 with db() as c:
  try:
   c.execute('BEGIN IMMEDIATE');c.execute('INSERT INTO users(id,name,email,password_hash,salt,birthday,marketing,qr_token) VALUES(?,?,?,?,?,?,?,?)',(uid,body.name.strip(),email,pwdhash(body.password,salt),salt,body.birthday,int(body.marketing),secrets.token_urlsafe(24)))
   c.execute('INSERT INTO ledger(user_id,delta,reason,reference,created_at) VALUES(?,?,?,?,?)',(uid,1,'Bienvenida','welcome:'+uid,now()))
   new_session(c,uid,response);c.execute('COMMIT')
  except sqlite3.IntegrityError:
   c.execute('ROLLBACK');raise HTTPException(409,'Correo ya registrado')
 return {'ok':True}
@app.post('/api/login')
def login(body:Login,response:Response):
 with db() as c:
  u=c.execute('SELECT * FROM users WHERE email=?',(body.email.strip().lower(),)).fetchone()
  if not u or not hmac.compare_digest(pwdhash(body.password,u['salt']),u['password_hash']):raise HTTPException(401,'Credenciales incorrectas')
  new_session(c,u['id'],response)
 return {'ok':True}
@app.post('/api/logout')
def logout(request:Request,response:Response):
 t=request.cookies.get('maple_session','')
 with db() as c:c.execute('DELETE FROM sessions WHERE token_hash=?',(tokenhash(t),))
 response.delete_cookie('maple_session',path='/');return {'ok':True}
@app.get('/api/me')
def me(request:Request):
 u=auth(request)
 with db() as c:return profile(c,u)
@app.get('/api/history')
def history(request:Request):
 u=auth(request)
 with db() as c:return [dict(x) for x in c.execute('SELECT delta,reason,created_at FROM ledger WHERE user_id=? ORDER BY id DESC LIMIT 100',(u['id'],))]
@app.get('/api/qr')
def qr(request:Request):
 u=auth(request);qr=qrcode.QRCode(box_size=6,border=3);qr.add_data('MAPLE:'+u['qr_token']);qr.make(fit=True);out=io.BytesIO();qr.make_image(fill_color='#294936',back_color='white').save(out,format='PNG');return {'image':'data:image/png;base64,'+base64.b64encode(out.getvalue()).decode()}
@app.get('/api/admin/customers')
def customers(request:Request):
 auth(request,True)
 with db() as c:return [profile(c,u) for u in c.execute('SELECT * FROM users WHERE role="customer" ORDER BY name LIMIT 500')]
@app.post('/api/admin/sale')
def sale(body:Sale,request:Request):
 auth(request,True)
 with db() as c:
  try:
   c.execute('BEGIN IMMEDIATE')
   if not c.execute('SELECT id FROM users WHERE id=? AND role="customer"',(body.customer_id,)).fetchone():raise HTTPException(404,'Cliente no encontrado')
   c.execute('INSERT INTO ledger(user_id,delta,reason,reference,created_at) VALUES(?,?,?,?,?)',(body.customer_id,body.quantity,'Venta confirmada (registro manual)', 'sale:'+body.sale_id,now()))
   c.execute('COMMIT')
  except sqlite3.IntegrityError:
   c.execute('ROLLBACK');raise HTTPException(409,'Esta venta ya fue registrada')
 return {'ok':True}
@app.post('/api/admin/refund')
def refund(body:Refund,request:Request):
 auth(request,True)
 with db() as c:
  try:
   c.execute('BEGIN IMMEDIATE');original=c.execute('SELECT user_id,delta FROM ledger WHERE reference=?',('sale:'+body.sale_id,)).fetchone()
   if not original:raise HTTPException(404,'Venta no encontrada')
   c.execute('INSERT INTO ledger(user_id,delta,reason,reference,created_at) VALUES(?,?,?,?,?)',(original['user_id'],-original['delta'],'Anulación de venta','refund:'+body.sale_id,now()))
   c.execute('COMMIT')
  except sqlite3.IntegrityError:
   c.execute('ROLLBACK');raise HTTPException(409,'Venta ya anulada')
 return {'ok':True}
@app.post('/api/admin/redeem')
def redeem(body:Redeem,request:Request):
 auth(request,True)
 if body.kind not in ('stamps','birthday'):raise HTTPException(400,'Premio inválido')
 with db() as c:
  c.execute('BEGIN IMMEDIATE');u=c.execute('SELECT * FROM users WHERE id=? AND role="customer"',(body.customer_id,)).fetchone()
  if not u:raise HTTPException(404,'Cliente no encontrado')
  if body.kind=='stamps':
   if balance(c,u['id'])<10:raise HTTPException(409,'Sellos insuficientes')
   delta=-10;reason='Canje de café gratis'
  else:
   if not birthday_available(u):raise HTTPException(409,'Beneficio de cumpleaños no disponible')
   delta=0;reason='Café de cumpleaños';c.execute('UPDATE users SET birthday_year=? WHERE id=?',(local_today().year,u['id']))
  rid=secrets.token_hex(12);c.execute('INSERT INTO redemptions VALUES(?,?,?,?)',(rid,u['id'],body.kind,now()))
  c.execute('INSERT INTO ledger(user_id,delta,reason,reference,created_at) VALUES(?,?,?,?,?)',(u['id'],delta,reason,'redeem:'+rid,now()));c.execute('COMMIT')
 return {'ok':True}
