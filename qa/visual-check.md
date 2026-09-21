# Verificação visual

As capturas finais foram geradas em Chromium headless contra a origem HTTPS pública temporária do sandbox após restaurar o markup, CSS e JavaScript visual originais.

A captura mobile em 390×844 px mostra o cabeçalho original, menu compacto, esfera orbital, cartão eSIM inclinado, grade de cena, anéis de energia, satélites, HUD de rede/latência/cobertura e partículas, além do hero original sem overflow horizontal.

A captura desktop em 1440×1000 px mostra a navegação original, composição orbital completa, grade, anéis, satélites numerados, indicadores de latência/cobertura, sinal conectado, coordenadas, cartão 3D, tipografia e ações originais.

Os estilos estão em `static/css/legacy-inline.css` e `static/css/legacy-3d.css`; o comportamento visual está em `static/js/legacy-public.js`. A camada foi externalizada e não usa handlers inline.

Arquivos: `qa/home-mobile.png` e `qa/home-desktop.png`.

## Menu mobile — validação 2026-09-21

O menu público foi consolidado em um único botão `<button>` com `aria-expanded`, sem checkbox, `details/summary` ou regra de `:focus` que force o painel aberto. Em viewport mobile, o painel abre somente após toque ou clique no botão, mantém itens com área mínima de toque, fecha ao selecionar um item, fecha ao clicar fora e fecha com `Escape`, devolvendo foco ao botão. O `body` bloqueia a rolagem enquanto o painel está aberto para evitar deslocamento acidental atrás do menu.

A validação estática passou em `node --check static/js/legacy-public.js` e `git diff --check`. A validação visual final deve ser repetida após o deploy nos tamanhos 360×800, 390×844 e 430×932, incluindo abertura e fechamento por toque e teclado.
