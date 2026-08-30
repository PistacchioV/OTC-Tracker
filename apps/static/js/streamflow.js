/* ============================================================================
   streamflow.js  —  Spotlight: o glow que acompanha o cursor dentro do cartão
   ----------------------------------------------------------------------------
   O gesto vem do cogni (os "spotlight cards"): ao passar o mouse, um halo
   radial acende SOB o ponteiro e o segue enquanto ele anda pelo cartão.

   O CSS não enxerga o ponteiro, então o desenho continua sendo dele — o
   `.card::after` do streamflow.css já é o halo — e este arquivo só escreve
   ONDE ele fica, em duas custom properties (`--sf-mx` / `--sf-my`). Se este
   script não carregar, o `var(--sf-mx, 50%)` do CSS devolve o halo fixo no
   topo do cartão: degrada para o desenho anterior, nunca para cartão quebrado.

   Três decisões que sustentam isso num app de tabela pesada:

   · UM listener delegado no document, `passive`, em vez de um por cartão. As
     telas do app trocam o corpo da tabela a cada redraw do DataTables, e um
     laço que prendesse listener no load pegaria só as linhas da primeira
     página — o mesmo motivo pelo qual os tooltips da casa são delegados.

   · a escrita é coalescida por requestAnimationFrame. O `pointermove` dispara
     dezenas de vezes por quadro; sem isso seriam dezenas de gravações de
     estilo e de `getBoundingClientRect` por quadro, cada uma forçando o
     navegador a recalcular layout no meio da rolagem.

   · só se escreve CUSTOM PROPERTY, nunca geometria. O DataTables mede as
     colunas no init e num segundo passe atrasado, e o que muda tamanho no meio
     dessa janela desalinha o cabeçalho do corpo sem dar erro nenhum.
   ========================================================================== */
(function () {
  "use strict";

  var reduce =
    window.matchMedia &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (reduce) return;

  // As superfícies que têm halo. São as mesmas do streamflow.css — se uma
  // entrar lá e não aqui, ela acende no topo e não segue o cursor.
  var SELECTOR =
    ".card, .ndm-card, .fxo-widget, .mc-card, .otm-widget, .ob-widget," +
    ".ndfc-widget, .ln-widget, .ops-widget";

  var pending = null; // último evento visto, ainda não desenhado
  var frame = 0;
  var current = null; // cartão sob o ponteiro no último quadro

  function draw() {
    frame = 0;
    var ev = pending;
    pending = null;
    if (!ev) return;

    var card = ev.target && ev.target.closest ? ev.target.closest(SELECTOR) : null;

    if (card !== current) {
      // Limpa o cartão anterior. Sem isto o halo dele congela na última
      // posição — invisível enquanto o `opacity: 0` do CSS vale, mas visível
      // no instante em que o ponteiro voltasse, entrando pelo lugar errado.
      if (current) {
        current.style.removeProperty("--sf-mx");
        current.style.removeProperty("--sf-my");
      }
      current = card;
    }
    if (!card) return;

    var r = card.getBoundingClientRect();
    card.style.setProperty("--sf-mx", (ev.clientX - r.left).toFixed(1) + "px");
    card.style.setProperty("--sf-my", (ev.clientY - r.top).toFixed(1) + "px");
  }

  document.addEventListener(
    "pointermove",
    function (ev) {
      // mouse e caneta seguem o cursor; toque não tem "hover" e ficaria com o
      // halo aceso no ponto do último toque até a próxima interação
      if (ev.pointerType === "touch") return;
      pending = ev;
      if (!frame) frame = window.requestAnimationFrame(draw);
    },
    { passive: true }
  );

  // Sair da janela apaga o halo do cartão que ficou marcado.
  document.addEventListener(
    "pointerleave",
    function () {
      if (current) {
        current.style.removeProperty("--sf-mx");
        current.style.removeProperty("--sf-my");
        current = null;
      }
    },
    { passive: true }
  );
})();
