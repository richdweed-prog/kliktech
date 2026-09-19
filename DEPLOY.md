# Deploy e operação da KlikTech

A aplicação roda como Flask/Gunicorn e usa PostgreSQL como fonte única de verdade para usuários, saldo, estoque, pedidos e ledger de pagamentos. O backend executa apenas inicialização idempotente das tabelas básicas; em produção, as migrações versionadas devem ser aplicadas antes do deploy.

## Checklist de deploy

1. Crie um banco PostgreSQL de produção e restrinja o acesso por rede e credenciais dedicadas.
2. Copie `.env.example` para o gerenciador de segredos do provedor. Nunca versione `.env`.
3. Gere `KLIKTECH_SECRET_KEY` com pelo menos 32 bytes aleatórios.
4. Defina `KLIKTECH_ADMIN_PASSWORD` com uma senha exclusiva e `KLIKTECH_ADMIN_TOTP_SECRET` com uma chave Base32 exclusiva. Cadastre a mesma chave em um autenticador TOTP.
5. Defina `KLIKTECH_ADMIN_PATH` com um caminho administrativo não óbvio. O caminho não substitui senha e 2FA.
6. Defina `KLIKTECH_PUBLIC_ORIGIN` com a origem HTTPS exata do domínio público, sem barra final.
7. Defina o CNPJ em `KLIKTECH_CNPJ` para que ele apareça no rodapé e mantenha as páginas de Termos, Privacidade e Reembolso revisadas pelo responsável legal.
8. Aplique `schema.sql`, `migrations/001_initial.sql` e `migrations/002_security.sql` em ordem. Em uma base já existente, valide duplicidades de `purchases.inventory_id` antes de aplicar a restrição única.
9. Configure no provedor de pagamentos a URL `https://seu-dominio/webhooks/bravopay` e o mesmo `BRAVOPAY_WEBHOOK_SECRET` do ambiente.
10. Faça deploy com `gunicorn --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 120 app:app`.
11. Valide `/healthz`, `/robots.txt`, `/sitemap.xml`, criação de conta, login, 2FA administrativo, compra concorrente e entrega de QR Code em um ambiente de homologação.
12. Habilite HTTPS, logs de erro sem dados de ativação e alertas para falhas de webhook, banco e limite de disco.

## Configuração Render

O `render.yaml` remove o disco SQLite legado e declara PostgreSQL, 2FA, origem pública, CNPJ e os segredos de pagamento como variáveis. O valor de `DATABASE_URL` deve ser obtido do banco gerenciado e não deve aparecer em logs, tickets ou código do navegador.

## Rotação de segredos

A rotação deve ser planejada e registrada. Gere uma nova `KLIKTECH_SECRET_KEY`, faça deploy controlado e aceite a invalidação das sessões existentes. Para trocar a senha administrativa, altere `KLIKTECH_ADMIN_PASSWORD`, faça deploy e valide o login com 2FA. Para trocar o autenticador TOTP, cadastre a nova chave antes da janela de troca e remova a chave antiga logo após a validação. Para trocar o webhook, atualize `BRAVOPAY_WEBHOOK_SECRET` no provedor e na aplicação em uma janela curta; eventos inválidos devem continuar sendo rejeitados. Para trocar `DATABASE_URL`, crie o novo usuário com menor privilégio necessário, teste a conexão, altere a variável e revogue a credencial anterior após confirmar saúde e consultas.

Nunca reutilize segredos entre desenvolvimento, homologação e produção. Não envie valores reais em issues, commits, screenshots ou relatórios de teste.

## Comandos locais

```bash
python3 -m pip install -r requirements.txt
sudo pg_ctlcluster 16 main start
PYTHONPATH=. python3 -m pytest -q
KLIKTECH_COOKIE_SECURE=0 PORT=5000 python3 app.py
```

Para teste de produção local:

```bash
KLIKTECH_COOKIE_SECURE=0 PORT=5000 gunicorn --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 120 app:app
```
