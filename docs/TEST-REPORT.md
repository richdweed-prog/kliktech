# Relatório de testes e aceite

## Resultado executivo

A suíte de aceitação executada contra PostgreSQL 16 local foi concluída com **10 testes aprovados**. O Lighthouse final, executado na origem HTTPS pública, mediu **100 em Performance, 95 em Acessibilidade, 100 em Boas práticas e 100 em SEO**. O relatório HTML e JSON está em `qa/lighthouse-final.report.html` e `qa/lighthouse-final.report.json`. O ZAP Quick Scan executado na URL HTTPS pública terminou com **0 High, 0 Medium, 0 Low e 6 Informational**.

## Critérios automatizados

| # | Critério | Resultado |
|---:|---|---|
| 1 | Cinco senhas erradas bloqueiam a conta e a senha certa posterior é rejeitada | Aprovado |
| 2 | 429 nos limites de login, cadastro, mutações comuns e webhook | Aprovado |
| 3 | POST sem Origin válido ou token CSRF é recusado | Aprovado |
| 4 | IDOR de compra, QR Code e foto entre usuários | Aprovado |
| 5 | Vinte compras concorrentes não geram saldo negativo nem venda duplicada | Aprovado |
| 6 | Webhook repetido ou adulterado não credita duas vezes | Aprovado |
| 7 | Nome contendo `<script>` é tratado como texto no admin | Aprovado |
| 8 | SVG e arquivo falso são rejeitados no upload | Aprovado |
| 9 | Admin sem 2FA não acessa o painel | Aprovado |
| 10 | CSP sem `unsafe-inline` e sem estilos/scripts inline | Aprovado |

## Comandos executados

```bash
PYTHONPATH=/home/ubuntu/kliktech python3 -m pytest -q
node --check static/js/public.js
node --check static/js/admin.js
node --check static/js/admin-login.js
python3 -m py_compile app.py tests/conftest.py tests/test_acceptance.py
npx --yes lighthouse http://127.0.0.1:5000/ --output=json --output=html
```

O teste de concorrência usa vinte clientes Flask e vinte conexões PostgreSQL independentes. A garantia de não duplicação depende da transação do endpoint e das restrições do banco, não apenas de um contador em memória.

## Auditoria de superfície

Os templates ativos não contêm `<style>`, scripts inline, atributos `style=` ou `!important`. O site público carrega `static/css/public.css` e `static/js/public.js`. O admin carrega `static/css/admin.css` e `static/js/admin.js`. Erros e páginas legais carregam apenas `static/css/minimal.css`.

A verificação visual headless em 390×844 px e 1440×1000 px não mostrou overflow horizontal no hero, e confirmou o menu mobile, o CTA, o cartão eSIM e a navegação desktop. Também foi verificado que HTTP responde 308 para a origem HTTPS e HTTPS emite `Secure`, `HttpOnly`, HSTS e CSP.

## ZAP

O script reproduzível está em `qa/run_zap_baseline.sh`. Em versões do pacote ZAP que não incluem o wrapper Python `zap-baseline.py`, o script usa o Quick Scan nativo do ZAP 2.17 com `-quickurl`, `-quickout` e `-quickprogress`. O relatório final executado na URL HTTPS pública está em `qa/zap-public/zap-report.html`:

```bash
ZAP_HOME=/home/ubuntu/zap OUT_DIR=qa/zap-public ./qa/run_zap_baseline.sh https://seu-dominio.example/
```

O scan HTTP local anterior acusou `HTTP Only Site` por ser um endpoint de QA sem TLS. Esse alerta foi eliminado no scan HTTPS final após o redirecionamento 308 e a ativação de cookies Secure.

## Referências

[1]: https://developer.chrome.com/docs/lighthouse/overview "Chrome Lighthouse documentation"
[2]: https://www.zaproxy.org/docs/docker/baseline-scan/ "OWASP ZAP baseline scan documentation"
