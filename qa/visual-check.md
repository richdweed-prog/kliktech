# Verificação visual

As capturas finais foram geradas em Chromium headless contra a origem HTTPS pública temporária do sandbox após restaurar o markup, CSS e JavaScript visual originais.

A captura mobile em 390×844 px mostra o cabeçalho original, menu compacto, esfera orbital, cartão eSIM inclinado, grade de cena, anéis de energia, satélites, HUD de rede/latência/cobertura e partículas, além do hero original sem overflow horizontal.

A captura desktop em 1440×1000 px mostra a navegação original, composição orbital completa, grade, anéis, satélites numerados, indicadores de latência/cobertura, sinal conectado, coordenadas, cartão 3D, tipografia e ações originais.

Os estilos estão em `static/css/legacy-inline.css` e `static/css/legacy-3d.css`; o comportamento visual está em `static/js/legacy-public.js`. A camada foi externalizada e não usa handlers inline.

Arquivos: `qa/home-mobile.png` e `qa/home-desktop.png`.
