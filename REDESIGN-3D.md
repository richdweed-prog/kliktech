# KlikTech — Redesign 3D

O SITE ESIM recebeu uma camada visual neo-tech baseada no sistema de design 3D anexado ao projeto. A lógica Flask, os endpoints, os bancos SQLite, autenticação, carteira Pix, compras, estoque e ativações foram preservados.

## Direção visual

A interface usa uma base escura profunda, superfícies glass, bordas translúcidas, acentos mint/neon, violeta e metal dourado. A landing page ganhou um hero com cartão eSIM 3D construído em CSS, esfera de energia, órbita luminosa, chip metálico, sweep de luz e indicador de conectividade. Os cartões de conteúdo possuem profundidade, hover com tilt e brilho contextual.

## Arquivos adicionados

| Arquivo | Função |
|---|---|
| `static/klicktech-3d.css` | Tokens, componentes, responsividade, estados, glassmorphism, 3D e temas visuais compartilhados. |
| `static/klicktech-3d.js` | Tilt 3D por ponteiro em cards de conteúdo, respeitando `prefers-reduced-motion` e touch devices. |
| `REDESIGN-3D.md` | Registro da direção visual e dos pontos de manutenção. |

## Arquivos atualizados

`templates/index.html`, `static/index.html`, `templates/admin.html`, `templates/client.html` e `templates/error.html` passaram a carregar a folha de estilo e o script compartilhados. A navegação, os formulários e os fluxos JavaScript existentes foram mantidos.

## Validação realizada

O Flask foi iniciado localmente após instalar as dependências declaradas em `requirements.txt`. As rotas `/`, `/cliente`, `/cliente/dashboard` e `/ademiropto/dashboard` responderam; a landing e os assets CSS/JS foram entregues com HTTP 200. Também foi feita validação visual desktop e mobile, além da correção de um conflito entre a classe genérica `.card` das telas internas e o cartão 3D do hero.
