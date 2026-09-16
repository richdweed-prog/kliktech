Fonte oficial: https://bravopay.club/docs

Base da API: https://bravopay.club/api/v1
Autenticação: Authorization: Bearer bp_live_...
Criação de cobrança: POST /transactions
Pix mínimo: amount_cents >= 500
Idempotência: header Idempotency-Key em POST /transactions
Webhook: POST configurado pelo painel, header BravoPay-Signature ou X-Bravopay-Signature no formato t=<timestamp>,v1=<hmac>; HMAC-SHA256 de `${t}.${rawBody}`, tolerância recomendada de 300 segundos.
Evento de crédito: transaction.paid
Envelope: {id, type, created, data}; data.id é o ID da transação, data.external_reference e data.metadata retornam intactos.
Eventos também disponíveis: transaction.created, transaction.expired, transaction.refunded, transaction.failed.
Retentativas: o mesmo event id é reenviado; deduplicar por event id e responder 2xx rapidamente.
