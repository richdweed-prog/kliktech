from pathlib import Path
import os, sqlite3, sys
from werkzeug.security import generate_password_hash, check_password_hash

BASE=Path(__file__).resolve().parent
ENV=BASE/'.env'
if not ENV.exists():
    print('ERRO: .env não encontrado em', ENV)
    sys.exit(1)
for line in ENV.read_text(encoding='utf-8-sig').splitlines():
    line=line.strip()
    if line and not line.startswith('#') and '=' in line:
        key,value=line.split('=',1)
        os.environ[key.strip()]=value.strip().strip('"').strip("'")
email=os.environ.get('KLIKTECH_ADMIN_EMAIL','').strip().lower()
password=os.environ.get('KLIKTECH_ADMIN_PASSWORD','')
if not email or not password:
    print('ERRO: KLIKTECH_ADMIN_EMAIL ou KLIKTECH_ADMIN_PASSWORD não foi encontrado no .env')
    sys.exit(1)

db=BASE/'kliktech_operations.sqlite3'
if not db.exists():
    print('ERRO: banco não encontrado:', db)
    print('Execute este script na mesma pasta que contém app.py e o banco.')
    sys.exit(1)
conn=sqlite3.connect(db)
conn.row_factory=sqlite3.Row
conn.execute('''CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY,email TEXT UNIQUE NOT NULL,name TEXT NOT NULL,password_hash TEXT NOT NULL,balance_cents INTEGER NOT NULL DEFAULT 0,is_admin INTEGER NOT NULL DEFAULT 0,created_at TEXT DEFAULT CURRENT_TIMESTAMP)''')
user=conn.execute('SELECT * FROM users WHERE email=?',(email,)).fetchone()
new_hash=generate_password_hash(password)
if user:
    conn.execute('UPDATE users SET password_hash=?,is_admin=1,name=? WHERE id=?',(new_hash,'Administrador',user['id']))
else:
    old_admin=conn.execute('SELECT id FROM users WHERE is_admin=1 ORDER BY id LIMIT 1').fetchone()
    if old_admin:
        conn.execute('UPDATE users SET email=?,password_hash=?,is_admin=1,name=? WHERE id=?',(email,new_hash,'Administrador',old_admin['id']))
    else:
        conn.execute('INSERT INTO users(email,name,password_hash,is_admin) VALUES(?,?,?,1)',(email,'Administrador',new_hash))
conn.commit()
check=conn.execute('SELECT * FROM users WHERE email=?',(email,)).fetchone()
print('Banco:', db)
print('E-mail administrativo configurado:', check['email'])
print('Permissão administrativa:', bool(check['is_admin']))
print('Senha do .env confere:', check_password_hash(check['password_hash'],password))
print('REPARO CONCLUÍDO. Feche e reinicie o Flask antes de tentar novamente.')
