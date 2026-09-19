# Vulnerabilidades corrigidas

A revisão substituiu o front-end legado e reorganizou o backend em torno de PostgreSQL, sessões protegidas e autorização por titular. A tabela resume as mudanças verificadas no código entregue.

| Área | Antes | Depois | Evidência |
|---|---|---|---|
| Entry point | O código estava em um arquivo chamado `app py`, não compatível com `app:app`. | `app.py` é o entrypoint único usado por Gunicorn e pelos testes. | `Procfile`, `render.yaml`, `app.py` |
| CSRF e origem | Requisições mutáveis podiam chegar sem `Origin` ou token CSRF. | Todas as mutações, exceto o webhook assinado, exigem `Origin` exato e `X-CSRF-Token` comparado em tempo constante. | `before_request`, teste de CSRF |
| Rate limit | Havia um limite genérico amplo e sem cobertura de todas as rotas. | Há buckets separados para login, cadastro, mutações comuns e webhook. | `RATE_LIMITS`, teste de 429 |
| Brute force | Cinco tentativas erradas não bloqueavam de forma comprovável a conta. | A quinta falha grava `blocked_at`; a senha correta posterior é rejeitada. | `login()`, teste de lockout |
| Sessão | O cliente dependia de múltiplas áreas e scripts inline. | `/api/me` restaura sessão, uma única área do cliente atualiza o estado e o logout limpa a sessão. | `public.js`, `/api/me` |
| 2FA administrativo | O painel não exigia segundo fator. | O login administrativo exige senha e TOTP; sem `KLIKTECH_ADMIN_TOTP_SECRET` o painel permanece bloqueado. | `/api/auth/admin-2fa`, `admin-login.js` |
| IDOR | A proteção dependia de consultas espalhadas. | QR Code, foto e histórico usam `purchase_id AND user_id`; usuário sem titularidade recebe 404. | `require_own_purchase` e joins nas rotas privadas |
| Corrida de compra | Débito e reserva podiam não ser persistidos juntos e o estoque podia duplicar venda. | PostgreSQL bloqueia usuário e item com `FOR UPDATE SKIP LOCKED`; saldo, reserva e pedido ficam na mesma transação. Há `CHECK balance_cents >= 0` e `UNIQUE inventory_id`. | `purchase()`, `schema.sql`, teste com 20 concorrências |
| Webhook | O corpo poderia fornecer valor ou usuário para crédito. | Assinatura HMAC, timestamp, idempotência por `event_id`, charge bloqueada e valor lido do pedido local. | `bravopay_webhook()`, `wallet_ledger`, teste de repetição/adulteração |
| XSS administrativo | Nomes recebidos poderiam ser interpolados em HTML. | O painel cria células via DOM e usa `textContent`; não há `innerHTML` no `admin.js`. | `admin.js`, teste de nome com `<script>` |
| Upload | O MIME do cliente era aceito sem verificar conteúdo. | SVG é recusado; JPG, PNG e WebP precisam de MIME permitido e magic bytes compatíveis, com limite de 5 MB. | `image_bytes()`, teste de arquivo falso |
| CSP | Havia múltiplos `<style>`, scripts inline e `unsafe-inline`. | CSS e JS são externos; `script-src 'self'`, sem `unsafe-inline`; páginas de erro carregam apenas CSS mínimo. | templates, `security_headers`, teste de CSP |
| Colisão de CSS | Classes genéricas `.card`, `.nav` e `.top` eram compartilhadas por público, cliente e admin. | Público/cliente usam `public-*` e `client-*`; admin usa `admin-*`, com arquivos CSS separados. | `static/css/public.css`, `static/css/admin.css` |
| Acessibilidade de modal | O fluxo usava modais com handlers inline e foco não controlado. | Diálogos têm `role=dialog`, `aria-modal`, foco inicial, ciclo de Tab e Escape. | `index.html`, `public.js` |
| SEO e erro | Havia títulos e URLs inconsistentes e erro carregando a camada legada. | Há description, Open Graph, canonical, `robots.txt`, `sitemap.xml` e template de erro minimalista. | `index.html`, rotas SEO, `error.html` |
| Transporte | O ambiente de QA aceitava conteúdo HTTP sem redirecionamento. | Quando `KLIKTECH_PUBLIC_ORIGIN` é HTTPS, o backend responde 308 para HTTP; cookies são Secure e HSTS é emitido em HTTPS. | `before_request`, `security_headers`, ZAP HTTPS |

## Limites conhecidos

A confirmação de compatibilidade de aparelho é uma triagem inicial e não substitui a confirmação da variante regional. A política de reembolso deve ser validada pelo responsável legal antes da publicação. O CNPJ exibido no rodapé vem de `KLIKTECH_CNPJ` e não deve permanecer com o valor de exemplo em produção.

## Referências

[1]: https://owasp.org/www-project-top-ten/ "OWASP Top 10"
[2]: https://owasp.org/www-community/attacks/csrf "OWASP Cross-Site Request Forgery Prevention"
[3]: https://developer.mozilla.org/en-US/docs/Web/HTTP/CSP "MDN Content Security Policy"
