from pathlib import Path
import os, sys, sqlite3, importlib.util

base=Path(__file__).resolve().parent
print('ARQUIVO EXECUTADO:', Path(__file__).resolve())
print('PASTA DO PROJETO:', base)
print('ENV EXISTE:', (base/'.env').exists())
print('APP EXISTE:', (base/'app.py').exists())
print('BANCO OPERACIONAL:', (base/'kliktech_operations.sqlite3').exists())
print('BANCO ESTOQUE:', (base/'kliktech_stock.sqlite3').exists())

env=base/'.env'
values={}
if env.exists():
    for line in env.read_text(encoding='utf-8-sig').splitlines():
        line=line.strip()
        if line and not line.startswith('#') and '=' in line:
            k,v=line.split('=',1);values[k.strip()]=v.strip().strip('"').strip("'")
    print('ENV ADMIN_EMAIL:', values.get('KLIKTECH_ADMIN_EMAIL','(ausente)'))
    print('ENV ADMIN_PATH:', values.get('KLIKTECH_ADMIN_PATH','(ausente)'))
    print('ENV COOKIE_SECURE:', values.get('KLIKTECH_COOKIE_SECURE','(ausente)'))
else:
    print('ERRO: crie .env nesta pasta antes do login.')

try:
    app_file=base/'app.py'
    spec=importlib.util.spec_from_file_location('kliktech_app',app_file)
    module=importlib.util.module_from_spec(spec)
    sys.modules['kliktech_app']=module
    spec.loader.exec_module(module)
    print('APP CARREGADO DE:', app_file)
    print('ROTAS PRIVADAS:')
    for rule in module.app.url_map.iter_rules():
        if 'admin' in str(rule) or 'painel' in str(rule) or str(rule) in ('/<path:slug>',): print(' ',rule)
except Exception as exc:
    print('ERRO AO CARREGAR app.py:', repr(exc))
    print('Execute antes: python -m pip install -r requirements.txt')
    sys.exit(1)

for filename in ('kliktech_operations.sqlite3','kliktech_stock.sqlite3'):
    db=base/filename
    if db.exists() and filename.startswith('kliktech_operations'):
        try:
            c=sqlite3.connect(db);c.row_factory=sqlite3.Row
            rows=c.execute('select email,is_admin from users order by id').fetchall()
            print('USUARIOS NO BANCO:')
            for row in rows: print(' ',row['email'],'admin=',bool(row['is_admin']))
        except Exception as exc: print('ERRO AO LER BANCO:',repr(exc))
print('DIAGNOSTICO CONCLUIDO')
