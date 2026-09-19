# Verificação visual

As capturas finais foram geradas em Chromium headless contra a origem HTTPS pública temporária do sandbox, após restaurar o `templates/index.html` e a camada visual do commit original.

A captura mobile em 390×844 px mostra o cabeçalho compacto, marca KlicTech Sem Fronteiras, menu hambúrguer, esfera orbital com cartão eSIM 3D, hero original, CTA de compatibilidade e ausência de overflow horizontal aparente.

A captura desktop em 1440×1000 px mostra a navegação horizontal original, hero em duas colunas, composição orbital completa, tipografia grande, gradientes neon, ações originais e espaçamento do design anterior.

Os estilos foram externalizados para `static/css/legacy-inline.css` e `static/css/legacy-3d.css`; os handlers foram substituídos por `data-legacy-action` e JavaScript externo com CSRF/try-catch.

Arquivos: `qa/home-mobile.png` e `qa/home-desktop.png`.
