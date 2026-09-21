# Auditoria defensiva de segurança — KlikTech

**Data:** 21 de setembro de 2026  
**Escopo:** revisão estática do repositório `richdweed-prog/kliktech` e verificações HTTP públicas de `https://www.kliktech.com.br/`.  
**Método:** análise de código, templates, JavaScript, esquema SQL, histórico Git, testes sintáticos e requisições GET/HEAD de baixa carga. Não foram executados brute force, fuzzing destrutivo, exploração de pagamentos, alteração de dados ou negação de serviço.

## Resumo executivo

A aplicação já possui uma base razoável: consultas parametrizadas, hash de senhas via Werkzeug, sessão `HttpOnly`/`Secure`/`SameSite=Lax`, proteção CSRF com validação de origem, CSP sem `unsafe-inline`, autorização por titularidade nas compras, HMAC com janela de tempo para webhook e transação concorrente para estoque/saldo.

Foram aplicadas correções locais de baixo risco para reduzir exposição do TOTP, impedir confiança implícita em `X-Forwarded-For`, evitar arredondamento binário em valores monetários e impedir crédito de cobranças que não estejam no estado `PENDING`. O repositório não foi publicado nem sofreu push.

## Achados

| ID | Severidade | Situação | Evidência | Impacto |
|---|---|---|---|---|
| A-01 | Alta | Corrigido localmente | `app.py`, rota `/api/auth/admin-2fa/setup`; agora exige `KLIKTECH_ADMIN_TOTP_SETUP_ENABLED=1` | Antes da correção, um administrador que passasse apenas pela senha poderia requisitar QR, segredo manual e URI `otpauth`, expondo o segredo TOTP antes da validação do segundo fator. |
| A-11 | Alta | Corrigido localmente | `users.admin_2fa_disabled_at`, `users.admin_2fa_version`, `PATCH /api/admin/users/<id>/2fa`, `admin.js` | A recuperação agora é por conta, não global: somente uma sessão administrativa já autorizada pode alterar outra conta administrativa; auto-desativação é recusada, o motivo é obrigatório, o evento é auditado em `admin_events` e a alteração invalida sessões administrativas antigas do alvo. Não existe rota de desativação para o cliente. |
| A-12 | Alta | Corrigido localmente | `legacy-public.js`, `admin-login.js` | O catálogo legado deixou de usar a construção dinâmica `innerHTML`/`onclick` para planos vindos do backend; os cartões usam DOM e `textContent`. O login administrativo agora respeita `requires_2fa` retornado pelo servidor para contas recuperadas pelo suporte. |
| A-02 | Alta | Pendente — requer infraestrutura | `app.py:81-90,149-156,293-300,645-663` | Rate limiting e lockout usam dicionários em memória. Com Gunicorn em múltiplos workers/instâncias, o limite de cinco tentativas não é global, desaparece em restart e pode ser contornado alternando workers/IPs. |
| A-03 | Alta | Pendente — rotação operacional necessária | `BRAVOPAY-INTEGRATION-NOTES.md:4` e histórico Git | O histórico contém o marcador de uma credencial live (`bp_live_...`). Não há evidência de valor completo no clone atual, mas qualquer segredo que tenha sido real deve ser revogado/rotacionado no provedor e o histórico deve ser reescrito apenas após preservar evidência e coordenar com a equipe. |
| A-04 | Alta | Pendente — desenho de armazenamento | `schema.sql:61-73`, `app.py:946-950,1246-1252` | `smdp`, `activation_code`, PIX e dados relacionados ficam em claro no banco e são retornados ao cliente autorizado. Hash não serve para recuperar esses valores: para uso posterior é necessária criptografia autenticada reversível, com chave fora do banco (KMS/secret manager), rotação e controle de acesso. |
| A-05 | Média | Corrigido parcialmente localmente | `app.py:777-779` | Conversão via `float` podia aceitar/representar valores monetários de forma imprecisa. Foi trocada por `Decimal`. |
| A-06 | Média | Corrigido localmente | `app.py:856` | Webhook `transaction.paid` podia tentar creditar qualquer estado diferente de `PAID`, inclusive estados terminais como `FAILED` ou `REFUNDED`, dependendo do fluxo. Agora só credita `PENDING`. |
| A-07 | Média | Corrigido localmente | `client_ip()` e `render.yaml` | O padrão confiava em `X-Forwarded-For`; esse cabeçalho é controlável pelo cliente se a aplicação for acessada diretamente ou houver proxy mal configurado. O padrão agora é não confiar; habilite somente quando a topologia garantir que o tráfego passa pelo proxy confiável. |
| A-08 | Média | Pendente | `app.py:676-687` | O endpoint de validação TOTP não possui um bucket específico de cinco tentativas nem bloqueio progressivo; ele fica sujeito apenas ao limitador genérico. Recomenda-se limitar por conta/IP, registrar falhas e exigir reautenticação após várias falhas. |
| A-09 | Média | Pendente | `app.py:53-58,480-499` | O bootstrap regrava o hash da senha administrativa em cada inicialização usando a variável de ambiente. Isso aumenta a superfície operacional e pode invalidar sessões/credenciais em deploys. Preferir provisionamento idempotente e rotação explícita, sem resetar senha a cada boot. |
| A-10 | Baixa | Observação | resposta pública do domínio | A superfície pública respondeu com HTTPS/HSTS, CSP, `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, COOP/CORP e cookies `Secure; HttpOnly; SameSite=Lax`. `/api/me` e `/api/auth/csrf` são públicos por desenho e retornam apenas estado/CSRF. |

## Verificações públicas realizadas

As requisições GET/HEAD de baixa carga confirmaram: `/healthz` retorna `200`; `/api/plans` retorna apenas o catálogo público; `/api/me` não revela usuário sem sessão; `/api/admin/dashboard` retorna `403`; a rota administrativa exige sessão; e o site público entrega HSTS e os cabeçalhos de segurança esperados. Não foi realizado login de teste, tentativa de senha, compra, webhook real ou envio de arquivo.

## Alterações locais aplicadas

1. `KLIKTECH_ADMIN_TOTP_SETUP_ENABLED=0` foi adicionado ao exemplo e ao `render.yaml`; a rota de setup retorna `404` quando não for habilitada explicitamente.
2. `KLIKTECH_TRUST_PROXY` passou a ter padrão seguro `0` no código e no deploy descrito em `render.yaml`.
3. Valores de recarga passaram a ser convertidos com `Decimal`, evitando erros de ponto flutuante.
4. O webhook de pagamento só credita uma cobrança no estado `PENDING`.
5. O documento de integração foi preservado como nota técnica, mas o marcador de credencial live no histórico deve ser tratado como potencial segredo exposto.

## Plano recomendado antes do próximo deploy

1. **Rotacionar imediatamente** qualquer chave BravoPay que tenha sido real, além de `KLIKTECH_SECRET_KEY`, `KLIKTECH_ADMIN_PASSWORD`, `KLIKTECH_ADMIN_TOTP_SECRET` e `BRAVOPAY_WEBHOOK_SECRET` se houver qualquer suspeita de exposição. Invalidar sessões após a rotação da chave de sessão.
2. Mover rate limiting e lockout para Redis ou PostgreSQL atômico, com chaves por IP e por conta, TTL, limites específicos para senha e TOTP, e observabilidade. Não confiar em IP fornecido pelo cliente.
3. Implementar criptografia autenticada (por exemplo, envelope encryption com AES-GCM ou equivalente gerenciado por KMS) para dados de ativação e segredos operacionais. Guardar somente ciphertext, nonce e versão da chave; nunca registrar plaintext em logs; descriptografar apenas na resposta autorizada.
4. Remover ou tornar inacessível o provisioning TOTP depois da configuração inicial; se for necessário provisionar, usar fluxo único, expiração curta e confirmação administrativa fora do endpoint público.
5. Corrigir o bootstrap da senha administrativa para não substituir o hash em todo restart e adicionar alertas para alteração de credencial.
6. Instalar as dependências de desenvolvimento em ambiente isolado e executar `pytest`, testes de concorrência, lint/scan de segredos e um baseline ZAP autenticado somente contra staging.
7. Remover ou substituir do histórico Git qualquer material que tenha sido segredo real, após a rotação e coordenação com todos os clones/CI.
8. Aplicar `migrations/003_admin_2fa_support.sql` antes do deploy. O botão do painel solicita motivo, envia CSRF e o servidor valida admin, titularidade da ação, alvo administrativo e motivo; não confie no JavaScript como controle de segurança.

## Validação local

A compilação Python e a checagem sintática dos quatro arquivos JavaScript passaram. A suíte `pytest` não foi executada neste ambiente porque `pytest`/`psycopg` não estão instalados no interpretador disponível; o repositório declara essas dependências em `requirements.txt`.

## Nota sobre hash versus criptografia

**Hash é unidirecional** e serve para verificar senhas; não permite recuperar um código de ativação. Para dados que o sistema precisa exibir ou enviar posteriormente, use criptografia autenticada reversível com a chave separada do banco. Para senhas, mantenha hash adaptativo com salt e nunca implemente descriptografia.

## Arquivos alterados

- `app.py`
- `.env.example`
- `render.yaml`
- `SECURITY-AUDIT-2026-09-21.md`

Nenhum segredo real foi exibido neste relatório.

> Antes de qualquer push, revisar o diff, configurar os secrets no provedor e confirmar a rotação das credenciais potencialmente expostas.

## Referências

- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)
- [OWASP Cryptographic Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html)
- [OWASP CSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html)
- [Flask session security](https://flask.palletsprojects.com/en/stable/web-security/)

## Observação de revisão

Este relatório é uma revisão defensiva e não constitui garantia de ausência de vulnerabilidades. A validação final deve ocorrer em staging, com credenciais de teste e autorização formal para qualquer teste ativo.
