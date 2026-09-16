from flask import Flask, jsonify, request, session, render_template, g, abort, redirect
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from pathlib import Path
import sqlite3, os, secrets, time, json, hmac, hashlib, urllib.request, urllib.error, io
import qrcode

BASE=Path(__file__).parent
ENV_FILE=BASE/'.env'
if ENV_FILE.exists():
    for line in ENV_FILE.read_text(encoding='utf-8').splitlines():
        line=line.strip()
        if line and not line.startswith('#') and '=' in line:
            key,value=line.split('=',1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
OPS_DB=Path(os.environ.get('KLIKTECH_OPS_DB',str(BASE/'kliktech_operations.sqlite3')))
STOCK_DB=Path(os.environ.get('KLIKTECH_STOCK_DB',str(BASE/'kliktech_stock.sqlite3')))
OPS_DB.parent.mkdir(parents=True,exist_ok=True)
STOCK_DB.parent.mkdir(parents=True,exist_ok=True)
ADMIN_PATH='ademiroputo'
app=Flask(__name__,template_folder='templates',static_folder='static',static_url_path='/static')
app.config.update(SECRET_KEY=os.environ.get('KLIKTECH_SECRET_KEY',secrets.token_hex(32)),SESSION_COOKIE_HTTPONLY=True,SESSION_COOKIE_SAMESITE='Lax',SESSION_COOKIE_SECURE=os.environ.get('KLIKTECH_COOKIE_SECURE','0')=='1',MAX_CONTENT_LENGTH=6*1024*1024)
PLANS={'30GB · 1 mês':20,'45GB · 1 mês':30,'30GB · 2 meses':40,'45GB · 2 meses':50}
RATE={}
def conn(path,key):
    connection=getattr(g,key,None)
    if connection is None:
        connection=sqlite3.connect(path);connection.row_factory=sqlite3.Row;connection.execute('PRAGMA foreign_keys=ON');connection.execute('PRAGMA busy_timeout=5000');setattr(g,key,connection)
    return connection
def ops():return conn(OPS_DB,'ops')
def stockdb():return conn(STOCK_DB,'stock')
@app.teardown_appcontext
def close(_=None):
    for key in ('ops','stock'):
        c=g.pop(key,None)
        if c:c.close()
def init_db():
    o=sqlite3.connect(OPS_DB);o.executescript('''CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY,email TEXT UNIQUE NOT NULL,name TEXT NOT NULL,password_hash TEXT NOT NULL,balance_cents INTEGER NOT NULL DEFAULT 0,is_admin INTEGER NOT NULL DEFAULT 0,public_id TEXT UNIQUE,profile_photo BLOB,profile_photo_mime TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP);CREATE TABLE IF NOT EXISTS wallet_charges(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL,provider_id TEXT UNIQUE NOT NULL,external_reference TEXT UNIQUE NOT NULL,amount_cents INTEGER NOT NULL,status TEXT DEFAULT 'PENDING',pix_copy_paste TEXT,expires_at TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP,paid_at TEXT);CREATE TABLE IF NOT EXISTS wallet_ledger(id INTEGER PRIMARY KEY,event_id TEXT UNIQUE NOT NULL,user_id INTEGER NOT NULL,provider_id TEXT,amount_cents INTEGER NOT NULL,kind TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP);CREATE TABLE IF NOT EXISTS carts(id INTEGER PRIMARY KEY,user_id INTEGER,session_key TEXT,plan TEXT NOT NULL,status TEXT DEFAULT 'active',created_at TEXT DEFAULT CURRENT_TIMESTAMP,updated_at TEXT DEFAULT CURRENT_TIMESTAMP);CREATE TABLE IF NOT EXISTS purchases(id INTEGER PRIMARY KEY,user_id INTEGER NOT NULL,inventory_id INTEGER NOT NULL,plan TEXT NOT NULL,price_cents INTEGER NOT NULL,status TEXT DEFAULT 'approved',created_at TEXT DEFAULT CURRENT_TIMESTAMP);CREATE TABLE IF NOT EXISTS admin_events(id INTEGER PRIMARY KEY,event TEXT,detail TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP);''');email=os.environ.get('KLIKTECH_ADMIN_EMAIL','admin@kliktech.local').lower();pw=os.environ.get('KLIKTECH_ADMIN_PASSWORD','troque-esta-senha')
    cols={row[1] for row in o.execute('PRAGMA table_info(users)').fetchall()}
    if 'public_id' not in cols:o.execute('ALTER TABLE users ADD COLUMN public_id TEXT')
    if 'profile_photo' not in cols:o.execute('ALTER TABLE users ADD COLUMN profile_photo BLOB')
    if 'profile_photo_mime' not in cols:o.execute('ALTER TABLE users ADD COLUMN profile_photo_mime TEXT')
    existing_ids={row[0] for row in o.execute('SELECT public_id FROM users WHERE public_id IS NOT NULL').fetchall()}
    for row in o.execute('SELECT id FROM users WHERE public_id IS NULL').fetchall():
        candidate=f'{secrets.randbelow(90000000)+10000000:08d}'
        while candidate in existing_ids:candidate=f'{secrets.randbelow(90000000)+10000000:08d}'
        o.execute('UPDATE users SET public_id=? WHERE id=?',(candidate,row[0]));existing_ids.add(candidate)
    admin=o.execute('SELECT id FROM users WHERE email=?',(email,)).fetchone()
    if admin:
        o.execute('UPDATE users SET name=?,password_hash=?,is_admin=1 WHERE id=?',('Administrador',generate_password_hash(pw),admin[0]))
    else:
        existing=o.execute('SELECT id FROM users WHERE is_admin=1 ORDER BY id LIMIT 1').fetchone()
        if existing:
            o.execute('UPDATE users SET email=?,name=?,password_hash=?,is_admin=1 WHERE id=?',(email,'Administrador',generate_password_hash(pw),existing[0]))
        else:
            o.execute('INSERT INTO users(email,name,password_hash,is_admin) VALUES(?,?,?,1)',(email,'Administrador',generate_password_hash(pw)))
    o.commit();o.close();s=sqlite3.connect(STOCK_DB);s.execute('''CREATE TABLE IF NOT EXISTS inventory(id INTEGER PRIMARY KEY,plan TEXT NOT NULL,model TEXT NOT NULL,line TEXT,ddd TEXT,photo BLOB,photo_mime TEXT,smdp TEXT NOT NULL,activation_code TEXT NOT NULL,sold_at TEXT,sold_to INTEGER,created_at TEXT DEFAULT CURRENT_TIMESTAMP)''');s.commit()
    stock_cols={row[1] for row in s.execute('PRAGMA table_info(inventory)').fetchall()}
    if 'ddd' not in stock_cols:s.execute('ALTER TABLE inventory ADD COLUMN ddd TEXT')
    s.commit();s.close()
@app.before_request
def load():
    g.user=None
    if session.get('user_id'):g.user=ops().execute('SELECT * FROM users WHERE id=?',(session['user_id'],)).fetchone()
    if request.endpoint and request.method in ('POST','PUT','PATCH') and request.endpoint!='bravopay_webhook':
        ip=request.headers.get('X-Forwarded-For',request.remote_addr or 'unknown').split(',')[0];now=time.time();arr=[x for x in RATE.get(ip,[]) if now-x<60];arr.append(now);RATE[ip]=arr
        if len(arr)>90:return jsonify(error='Muitas tentativas. Aguarde um minuto.'),429
def login_required(f):
    @wraps(f)
    def w(*a,**k):return f(*a,**k) if g.user else (jsonify(error='Faça login para continuar.'),401)
    return w
def admin_required(f):
    @wraps(f)
    def w(*a,**k):return f(*a,**k) if g.user and g.user['is_admin'] else (jsonify(error='Área administrativa protegida.'),403)
    return w
def safe_user(r):return {'id':r['public_id'],'name':r['name'],'email':r['email'],'balance':r['balance_cents']/100,'profile_photo_url':('/api/account/profile/photo' if r['profile_photo'] else None)}
def mask_email(e):
    a,b=e.split('@',1);return (a[:2]+'***' if len(a)>2 else a+'*')+'@'+b
@app.get('/')
def store():return render_template('index.html')
@app.get('/healthz')
def healthz():return jsonify(status='ok',service='kliktech-esim')
def admin_page_or_forbid():
    if not g.user:return redirect('/cliente')
    if not g.user['is_admin']:abort(403)
    return render_template('admin.html')
@app.get('/admin')
def hidden_admin_block():abort(404)
@app.get('/ademiroputo')
def admin_root():return redirect('/ademiroputo/dashboard')
@app.get('/ademiroputo/dashboard')
def admin_dashboard_page():return admin_page_or_forbid()
@app.get('/ademiroputo/esims')
def admin_esims_page():return admin_page_or_forbid()
@app.get('/ademiroputo/estoque')
def admin_stock_page():return admin_page_or_forbid()
@app.get('/ademiroputo/pedidos')
def admin_orders_page():return admin_page_or_forbid()
@app.get('/ademiroputo/clientes')
def admin_customers_page():return admin_page_or_forbid()
@app.get('/ademiroputo/configuracoes')
def admin_settings_page():return admin_page_or_forbid()
# Compatibilidade com a grafia antiga publicada na primeira versão.
@app.get('/ademiropto')
def legacy_admin_root():return redirect('/ademiroputo/dashboard', code=301)
@app.get('/ademiropto/<path:legacy_path>')
def legacy_admin_path(legacy_path):return redirect('/ademiroputo/'+legacy_path, code=301)
@app.get('/cliente')
def client_root():return redirect('/cliente/dashboard')
@app.get('/cliente/dashboard')
def client_dashboard_page():return render_template('client.html')
@app.get('/cliente/esims')
def client_esims_page():return render_template('client.html')
@app.get('/cliente/pedidos')
def client_orders_page():return render_template('client.html')
@app.get('/cliente/suporte')
def client_support_page():return render_template('client.html')
@app.get('/cliente/configuracoes')
def client_settings_page():return render_template('client.html')
@app.errorhandler(403)
def forbidden(_):return render_template('error.html',code=403,title='Acesso negado',message='Você não tem permissão para acessar esta área.'),403
@app.errorhandler(404)
def not_found(_):return render_template('error.html',code=404,title='Página não encontrada',message='O endereço informado não existe.'),404
@app.get('/<path:slug>')
def unknown_path(slug):abort(404)
@app.post('/api/auth/register')
def register():
    d=request.get_json() or {};email=d.get('email','').strip().lower();name=d.get('name','').strip();pw=d.get('password','');confirm=d.get('password_confirmation','')
    if '@' not in email or not name or len(pw)<8:return jsonify(error='Informe nome, e-mail e senha com pelo menos 8 caracteres.'),400
    if pw!=confirm:return jsonify(error='As senhas não conferem.'),400
    try:
        c=ops();public_id=f'{secrets.randbelow(90000000)+10000000:08d}'
        while c.execute('SELECT 1 FROM users WHERE public_id=?',(public_id,)).fetchone():public_id=f'{secrets.randbelow(90000000)+10000000:08d}'
        cur=c.execute('INSERT INTO users(email,name,password_hash,public_id) VALUES(?,?,?,?)',(email,name,generate_password_hash(pw),public_id));c.commit();session.clear();session['user_id']=cur.lastrowid;return jsonify(user=safe_user(c.execute('SELECT * FROM users WHERE id=?',(cur.lastrowid,)).fetchone()))
    except sqlite3.IntegrityError:return jsonify(error='Este e-mail já está cadastrado.'),409
@app.post('/api/auth/login')
def login():
    d=request.get_json() or {};u=ops().execute('SELECT * FROM users WHERE email=?',(d.get('email','').strip().lower(),)).fetchone()
    if not u or not check_password_hash(u['password_hash'],d.get('password','')):return jsonify(error='E-mail ou senha inválidos.'),401
    session.clear();session['user_id']=u['id'];return jsonify(user=safe_user(u),is_admin=bool(u['is_admin']))
@app.post('/api/auth/logout')
def logout():session.clear();return jsonify(ok=True)
@app.get('/api/me')
def me():return jsonify(user=safe_user(g.user) if g.user else None,is_admin=bool(g.user and g.user['is_admin']))
@app.post('/api/account/profile')
@login_required
def update_profile():
    name=(request.form.get('name') or '').strip()
    photo=request.files.get('photo')
    if not name:return jsonify(error='Informe seu nome completo.'),400
    if photo and (not photo.mimetype or not photo.mimetype.startswith('image/')):return jsonify(error='Envie uma imagem válida.'),400
    c=ops()
    if photo:c.execute('UPDATE users SET name=?,profile_photo=?,profile_photo_mime=? WHERE id=?',(name,photo.read(),photo.mimetype,g.user['id']))
    else:c.execute('UPDATE users SET name=? WHERE id=?',(name,g.user['id']))
    c.commit();return jsonify(user=safe_user(c.execute('SELECT * FROM users WHERE id=?',(g.user['id'],)).fetchone()))
@app.get('/api/account/profile/photo')
@login_required
def profile_photo():
    row=ops().execute('SELECT profile_photo,profile_photo_mime FROM users WHERE id=?',(g.user['id'],)).fetchone()
    if not row or not row['profile_photo']:abort(404)
    return app.response_class(row['profile_photo'],mimetype=row['profile_photo_mime'] or 'image/jpeg',headers={'Cache-Control':'private, no-store'})
@app.post('/api/cart')
def cart_add():
    d=request.get_json() or {};plan=d.get('plan')
    if plan not in PLANS:return jsonify(error='Plano inválido.'),400
    c=ops();sid=session.get('cart_key') or secrets.token_urlsafe(18);session['cart_key']=sid;c.execute('INSERT INTO carts(session_key,plan) VALUES(?,?)',(sid,plan));c.commit();return jsonify(ok=True)
@app.post('/api/wallet/create-pix')
@login_required
def create_pix():
    d=request.get_json() or {}
    try:amount=int(round(float(d.get('amount',0))*100))
    except:amount=0
    if amount<500 or amount>1000000:return jsonify(error='Escolha entre R$ 5 e R$ 10.000.'),400
    key=os.environ.get('BRAVOPAY_API_KEY','').strip()
    if not key:return jsonify(error='Pagamento ainda não configurado no servidor.'),503
    external=f'wallet:{g.user["id"]}:{secrets.token_hex(8)}';payload={'amount_cents':amount,'method':'pix','customer':{'email':g.user['email'],'name':g.user['name']},'description':'Recarga KlicTech Sem Fronteiras','external_reference':external,'metadata':{'user_id':str(g.user['id']),'purpose':'wallet_topup'},'expires_in':3600};req=urllib.request.Request('https://bravopay.club/api/v1/transactions',data=json.dumps(payload).encode(),method='POST',headers={'Authorization':'Bearer '+key,'Content-Type':'application/json','Idempotency-Key':external})
    try:
        with urllib.request.urlopen(req,timeout=15) as r:res=json.loads(r.read())
    except urllib.error.HTTPError as exc:
        try: detail=json.loads(exc.read().decode()).get('error',{}).get('message','')
        except Exception: detail=''
        return jsonify(error=('BravoPay recusou a cobrança: '+detail) if detail else 'BravoPay recusou a cobrança. Verifique a API Key e tente novamente.'),502
    except Exception:return jsonify(error='Não foi possível conectar à BravoPay agora.'),502
    pix=res.get('pix') or {};tx=res.get('id')
    if not tx or not pix.get('copy_paste'):return jsonify(error='Resposta inválida da BravoPay.'),502
    ops().execute('INSERT INTO wallet_charges(user_id,provider_id,external_reference,amount_cents,status,pix_copy_paste,expires_at) VALUES(?,?,?,?,?,?,?)',(g.user['id'],tx,external,amount,res.get('status','PENDING'),pix['copy_paste'],pix.get('expires_at')));ops().commit();return jsonify(charge={'id':tx,'amount':amount/100,'status':'PENDING','copy_paste':pix['copy_paste']})
@app.post('/webhooks/bravopay')
def bravopay_webhook():
    raw=request.get_data();head=request.headers.get('BravoPay-Signature') or request.headers.get('X-Bravopay-Signature');secret=os.environ.get('BRAVOPAY_WEBHOOK_SECRET','');parts=dict(x.split('=',1) for x in (head or '').split(',') if '=' in x)
    try:valid=secret and abs(int(time.time())-int(parts.get('t','0')))<=300 and hmac.compare_digest(hmac.new(secret.encode(),(parts['t']+'.'+raw.decode()).encode(),hashlib.sha256).hexdigest(),parts.get('v1',''))
    except:valid=False
    if not valid:return jsonify(error='Assinatura inválida.'),401
    e=json.loads(raw);eid=e.get('id');typ=e.get('type');d=e.get('data') or {};c=ops()
    if c.execute('SELECT id FROM wallet_ledger WHERE event_id=?',(eid,)).fetchone():return jsonify(ok=True)
    ch=c.execute('SELECT * FROM wallet_charges WHERE provider_id=?',(d.get('id'),)).fetchone()
    if not ch:return jsonify(ok=True)
    if typ=='transaction.paid' and ch['status']!='PAID':
        amt=int(d.get('amount_cents') or ch['amount_cents']);c.execute('UPDATE users SET balance_cents=balance_cents+? WHERE id=?',(amt,ch['user_id']));c.execute('UPDATE wallet_charges SET status="PAID",paid_at=CURRENT_TIMESTAMP WHERE id=?',(ch['id'],));c.execute('INSERT INTO wallet_ledger(event_id,user_id,provider_id,amount_cents,kind) VALUES(?,?,?,?,?)',(eid,ch['user_id'],ch['provider_id'],amt,'credit'))
    elif typ in ('transaction.expired','transaction.failed'):c.execute('UPDATE wallet_charges SET status=? WHERE id=?',('EXPIRED' if typ.endswith('expired') else 'FAILED',ch['id']))
    c.commit();return jsonify(ok=True)
@app.get('/api/availability')
@login_required
def availability():
    plan=(request.args.get('plan') or '').strip();ddd=(request.args.get('ddd') or '').strip()
    rows=stockdb().execute("SELECT ddd,COUNT(*) AS quantity FROM inventory WHERE plan=? AND sold_at IS NULL AND (?='' OR ddd=?) GROUP BY ddd ORDER BY ddd",(plan,ddd,ddd)).fetchall()
    return jsonify(ddds=[{'ddd':r['ddd'],'quantity':r['quantity']} for r in rows])
@app.post('/api/purchase')
@login_required
def purchase():
    d=request.get_json() or {};plan=d.get('plan');ddd=(d.get('ddd') or '').strip();price=PLANS.get(plan)
    if not price:return jsonify(error='Plano inválido.'),400
    c=ops();s=stockdb()
    try:
        c.execute('BEGIN IMMEDIATE');s.execute('BEGIN IMMEDIATE');u=c.execute('SELECT * FROM users WHERE id=?',(g.user['id'],)).fetchone();item=s.execute("SELECT * FROM inventory WHERE plan=? AND sold_at IS NULL AND ddd=COALESCE(NULLIF(?, ''), ddd) ORDER BY id LIMIT 1",(plan,ddd)).fetchone()
        if not item:
            c.rollback();s.rollback();return jsonify(error='Sem eSIM disponível para este plano/DDD.'),409
        if u['balance_cents']<price*100:
            c.rollback();s.rollback();return jsonify(error='Saldo insuficiente para este plano.'),402
        s.execute('UPDATE inventory SET sold_at=CURRENT_TIMESTAMP,sold_to=? WHERE id=? AND sold_at IS NULL',(u['id'],item['id']))
        if s.execute('SELECT changes()').fetchone()[0]!=1:
            c.rollback();s.rollback();return jsonify(error='Este eSIM acabou de ser reservado. Escolha outro.'),409
        c.execute('UPDATE users SET balance_cents=balance_cents-? WHERE id=?',(price*100,u['id']));c.execute('UPDATE carts SET status="converted",updated_at=CURRENT_TIMESTAMP WHERE session_key=? AND plan=? AND status="active"',(session.get('cart_key',''),plan));c.execute('INSERT INTO purchases(user_id,inventory_id,plan,price_cents) VALUES(?,?,?,?)',(u['id'],item['id'],plan,price*100));s.commit();c.commit();return jsonify(ok=True)
    except Exception:c.rollback();s.rollback();raise
@app.get('/api/account/purchases')
@login_required
def my_purchases():
    rows=ops().execute('SELECT * FROM purchases WHERE user_id=? ORDER BY id DESC',(g.user['id'],)).fetchall();out=[]
    for p in rows:
        i=stockdb().execute('SELECT model,line,ddd,smdp,activation_code,photo FROM inventory WHERE id=?',(p['inventory_id'],)).fetchone();out.append({'id':p['id'],'plan':p['plan'],'price':p['price_cents']/100,'date':p['created_at'],'model':i['model'],'line':i['line'],'ddd':i['ddd'],'smdp':i['smdp'],'activation_code':i['activation_code'],'photo_url':('/api/account/purchases/%s/photo'%p['id']) if i['photo'] else None,'qr_url':'/api/account/purchases/%s/qr'%p['id'],'setup_guide':{'title':'Ajustes do aparelho · eSIM','steps':[{'title':'Ativar o 5G','iphone':'Ajustes › Celular › sua linha › Voz e Dados › 5G Automático','android':'Configurações › Conexões › Redes móveis › Modo de rede › 5G/LTE/3G/2G (automático)'},{'title':'Ativar o roaming de dados','iphone':'Ajustes › Celular › sua linha › Roaming de Dados › ligar','android':'Configurações › Conexões › Redes móveis › Roaming de dados › ligar'},{'title':'Ativar o VoLTE','iphone':'Ajustes › Celular › sua linha › Voz e Dados › VoLTE › ligar','android':'Configurações › Conexões › Rede móvel › Chamadas VoLTE › ligar'},{'title':'Ativar ligações por Wi-Fi','iphone':'Ajustes › Celular › sua linha › Ligações Wi-Fi › ligar','android':'Configurações › Conexões › Chamada por Wi-Fi › ligar'}],'install':{'iphone':'Ajustes › Celular › Adicionar eSIM › Usar código QR ou inserir detalhes manualmente.','android':'Configurações › Rede e Internet › SIMs › Adicionar eSIM › Inserir manualmente.','note':'Fique conectado ao Wi-Fi. O eSIM é de instalação única; remova-o do aparelho anterior antes de instalar em outro.'}}})
    return jsonify(purchases=out)
@app.get('/api/account/purchases/<int:purchase_id>/qr')
@login_required
def purchase_qr(purchase_id):
    row=ops().execute('SELECT inventory_id FROM purchases WHERE id=? AND user_id=?',(purchase_id,g.user['id'])).fetchone()
    if not row:abort(404)
    item=stockdb().execute('SELECT smdp,activation_code FROM inventory WHERE id=?',(row['inventory_id'],)).fetchone()
    if not item:abort(404)
    image=qrcode.make('LPA:1$%s$%s'%(item['smdp'],item['activation_code']));buffer=io.BytesIO();image.save(buffer,format='PNG');return app.response_class(buffer.getvalue(),mimetype='image/png',headers={'Cache-Control':'private, no-store'})
@app.get('/api/account/purchases/<int:purchase_id>/photo')
@login_required
def purchase_photo(purchase_id):
    row=ops().execute('SELECT inventory_id FROM purchases WHERE id=? AND user_id=?',(purchase_id,g.user['id'])).fetchone()
    if not row:abort(404)
    photo=stockdb().execute('SELECT photo,photo_mime FROM inventory WHERE id=?',(row['inventory_id'],)).fetchone()
    if not photo or not photo['photo']:abort(404)
    return app.response_class(photo['photo'],mimetype=photo['photo_mime'] or 'image/jpeg',headers={'Cache-Control':'private, no-store'})
@app.post('/api/admin/inventory/batch')
@admin_required
def add_inventory_batch():
    if request.is_json:data=request.get_json() or {};records=data.get('records') or [];files=[]
    else:
        try:records=json.loads(request.form.get('records','[]'));files=[f for f in request.files.getlist('photos')]
        except Exception:return jsonify(error='JSON de registros inválido.'),400
    if not isinstance(records,list) or not records or len(records)>500:return jsonify(error='Envie entre 1 e 500 registros.'),400
    if files and len(files)!=len(records):return jsonify(error='A quantidade de fotos deve ser igual à quantidade de registros.'),400
    seen=set();errors=[]
    normalized=[]
    for idx,r in enumerate(records,1):
        code=(r.get('activation_code') or '').strip();smdp=(r.get('smdp') or '').strip();plan=(r.get('plan') or '').strip();ddd=(r.get('ddd') or '').strip();tempo=(r.get('tempo') or '').strip();gigas=(r.get('gigas') or '').strip()
        if not plan and tempo and gigas:plan=f'{gigas} · {tempo}'
        if not plan or (plan not in PLANS and not (tempo and gigas)):errors.append(f'Registro {idx}: informe gigas e tempo ou um plano válido.')
        if not smdp:errors.append(f'Registro {idx}: SM-DP+ ausente.')
        if not code:errors.append(f'Registro {idx}: código ausente.')
        if not ddd.isdigit() or len(ddd) not in (2,3):errors.append(f'Registro {idx}: DDD inválido.')
        if code in seen:errors.append(f'Registro {idx}: código duplicado no lote.')
        seen.add(code);normalized.append({**r,'plan':plan,'ddd':ddd,'smdp':smdp,'activation_code':code})
    c=stockdb()
    for r in records:
        if c.execute('SELECT id FROM inventory WHERE activation_code=?',(r.get('activation_code','').strip(),)).fetchone():errors.append('Código já existente no estoque: '+r.get('activation_code',''))
    if errors:return jsonify(error='Validação falhou.',errors=errors),400
    for idx,r in enumerate(normalized):
        photo=files[idx] if files else None
        blob=photo.read() if photo else None
        c.execute('INSERT INTO inventory(plan,model,line,ddd,photo,photo_mime,smdp,activation_code) VALUES(?,?,?,?,?,?,?,?)',(r['plan'].strip(),r.get('model','').strip() or 'Não informado',r.get('line','').strip(),r['ddd'].strip(),blob,photo.mimetype if photo else None,r['smdp'].strip(),r['activation_code'].strip()))
    c.commit();return jsonify(ok=True,added=len(records))
@app.post('/api/admin/inventory')
@admin_required
def add_inventory():
    f=request.form;plan=f.get('plan');model=f.get('model','').strip();smdp=f.get('smdp','').strip();code=f.get('activation_code','').strip();photo=request.files.get('photo')
    if plan not in PLANS or not model or not smdp or not code:return jsonify(error='Preencha plano, modelo e códigos.'),400
    p=photo.read() if photo else None;stockdb().execute('INSERT INTO inventory(plan,model,line,ddd,photo,photo_mime,smdp,activation_code) VALUES(?,?,?,?,?,?,?,?)',(plan,model,f.get('line','').strip(),f.get('ddd','').strip(),p,photo.mimetype if photo else None,smdp,code));stockdb().commit();return jsonify(ok=True)
@app.get('/api/admin/dashboard')
@admin_required
def dashboard():
    o=ops();s=stockdb();sales=o.execute('SELECT COUNT(*) n,COALESCE(SUM(price_cents),0) v FROM purchases').fetchone();pix=o.execute("SELECT COUNT(*) n,COALESCE(SUM(amount_cents),0) v FROM wallet_charges WHERE status='PENDING'").fetchone();paid=o.execute("SELECT COUNT(*) n,COALESCE(SUM(amount_cents),0) v FROM wallet_charges WHERE status='PAID'").fetchone();stock=s.execute("SELECT COUNT(*) n FROM inventory WHERE sold_at IS NULL").fetchone();ab=o.execute("SELECT COUNT(*) n FROM carts WHERE status='active' AND updated_at < datetime('now','-30 minutes')").fetchone();recent=o.execute('SELECT p.plan,p.price_cents,p.created_at,u.name,u.email FROM purchases p JOIN users u ON u.id=p.user_id ORDER BY p.id DESC LIMIT 12').fetchall();return jsonify(metrics={'sales_count':sales['n'],'sales_value':sales['v']/100,'pending_pix_count':pix['n'],'pending_pix_value':pix['v']/100,'paid_topups':paid['v']/100,'available_stock':stock['n'],'abandoned_carts':ab['n']},recent=[{'plan':r['plan'],'price':r['price_cents']/100,'date':r['created_at'],'customer':r['name'],'email':mask_email(r['email'])} for r in recent])
@app.get('/api/admin/users')
@admin_required
def admin_users():
    rows=ops().execute('SELECT public_id,name,email,is_admin,profile_photo IS NOT NULL has_photo,created_at FROM users ORDER BY id DESC').fetchall()
    return jsonify(users=[{'id':r['public_id'],'name':r['name'],'email':r['email'],'is_admin':bool(r['is_admin']),'has_photo':bool(r['has_photo']),'created_at':r['created_at']} for r in rows])
@app.get('/api/admin/inventory')
@admin_required
def inventory():
    rows=stockdb().execute('SELECT id,plan,model,line,ddd,sold_at IS NOT NULL sold,created_at FROM inventory ORDER BY id DESC').fetchall();return jsonify(items=[dict(r) for r in rows])
if __name__=='__main__':init_db();app.run(host='0.0.0.0',port=int(os.environ.get('PORT',5000)),debug=False)
else:init_db()
