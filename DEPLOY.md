# Deploy do SITE ESIM no GitHub + Render

O projeto está preparado para ser versionado no GitHub e executado como serviço Python no Render. O processo usa Gunicorn em produção, health check em `/healthz`, uma única instância para manter a consistência do SQLite e um disco persistente montado em `/var/data`.

## Escolha de hospedagem

| Opção | Resultado | Trade-off | Custo/limite |
|---|---|---|---|
| Render Starter + disco persistente | Serviço ligado continuamente, deploy automático, HTTPS, banco SQLite preservado entre deploys | Uma única instância; para crescer horizontalmente, migrar o banco para PostgreSQL | Plano pago do Render + disco conforme a conta Render |
| Render Free | Bom para demonstração e testes | Pode dormir por inatividade, não é 24/7 e não deve ser usado para dados de produção | Gratuito, mas sem garantia de disponibilidade contínua |

Para o pedido de disponibilidade online 24/7, o arquivo `render.yaml` já escolhe a primeira opção (`plan: starter`) e configura o disco persistente de 1 GB.

## Publicar no GitHub

Crie um repositório vazio no GitHub e execute os comandos abaixo a partir da pasta `SITE ESIM`:

```bash
git init
git branch -M main
git add .
git commit -m "feat: redesign 3d e deploy de producao"
git remote add origin https://github.com/SEU_USUARIO/SEU_REPOSITORIO.git
git push -u origin main
```

O `.gitignore` impede o envio do `.env`, dos bancos SQLite locais, do cache Python e das capturas de QA. O arquivo `.env.example` documenta as variáveis sem conter credenciais.

## Publicar no Render

No painel do Render, escolha **New → Blueprint** e conecte o repositório GitHub. O Render detectará o `render.yaml`. Confirme o serviço `kliktech-esim`, o plano Starter e o disco persistente. Depois do primeiro deploy, abra o endereço HTTPS gerado e confirme que `/healthz` responde com `{"status":"ok","service":"kliktech-esim"}`.

As variáveis marcadas com `sync: false` no Blueprint devem ser preenchidas exclusivamente no painel do Render: `DATABASE_URL`, `KLIKTECH_ADMIN_EMAIL`, `KLIKTECH_ADMIN_PASSWORD`, `BRAVOPAY_API_KEY` e `BRAVOPAY_WEBHOOK_SECRET`. A `DATABASE_URL` contém a credencial de conexão do banco e nunca deve ser colocada no GitHub, em HTML, em JavaScript ou em mensagens de log. A `KLIKTECH_SECRET_KEY` é gerada pelo Render. Não faça commit de valores reais dessas variáveis.

## BravoPay

Depois que o domínio do Render estiver disponível, a URL do webhook deverá ser:

```text
https://SEU-SERVICO.onrender.com/webhooks/bravopay
```

Configure essa URL no painel da BravoPay junto com o segredo correspondente. O fluxo de recarga Pix já existe no backend; a configuração de produção fica separada por variável de ambiente.

## Persistência e escala

O banco atual é SQLite. O disco persistente evita a perda dos usuários, saldo, compras e estoque durante novos deploys, mas o serviço deve permanecer com uma instância enquanto utilizar SQLite. Caso o volume cresça ou seja necessário executar várias instâncias, o próximo passo é migrar as tabelas para PostgreSQL e remover a dependência do disco local.

## Comandos locais

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Para simular o processo de produção localmente:

```bash
PORT=5000 gunicorn --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 120 app:app
```
