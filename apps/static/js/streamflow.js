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
/* ── Efeitos reduzidos: a máquina SEM GPU não paga o vidro ──────────────────
   Nas máquinas do JPM o navegador roda com a aceleração de hardware desligada
   (Firefox `about:support` → Compositing: "WebRender (Software)"), e aí o
   custo da camada muda de natureza: os dois fundos animados com blur de
   viewport inteira e os ~80 backdrop-filter recompositam a página inteira por
   software, quadro a quadro — a tela inteira fica lenta SEM erro nenhum.

   A decisão é feita aqui (o CSS não enxerga o compositor) e vira a classe
   `sf-reduced` no <html>; a seção 16 do streamflow.css faz o resto. Três
   sinais, na ordem:

   · override em localStorage `__OTC_TRACKER_FX__` = 'full' | 'reduced'
     (qualquer outro valor = auto) — é a saída de emergência nos dois
     sentidos, porque detecção de GPU por JS é heurística;
   · WebGL por software (SwiftShader / llvmpipe / Microsoft Basic Render
     Driver) ou indisponível — a assinatura do VDI e do driver bloqueado;
   · Firefox no Windows — o par da mesa, onde o "WebRender (Software)" foi
     CONFIRMADO e o WebGL pode responder pela GPU mesmo com o compositor em
     software (caminhos independentes no Firefox). O custo do falso positivo
     é estético (perde o desfoque, ficam tokens, cores e sombras); o do falso
     negativo é a mesa inteira com o app lento — a assimetria decide.       */
(function () {
  "use strict";

  function fxPref() {
    try {
      return String(localStorage.getItem("__OTC_TRACKER_FX__") || "auto").toLowerCase();
    } catch (e) {
      return "auto";
    }
  }

  function softwareGl() {
    try {
      var c = document.createElement("canvas");
      var gl = c.getContext("webgl") || c.getContext("experimental-webgl");
      if (!gl) return true;
      var ext = gl.getExtension("WEBGL_debug_renderer_info");
      var r = ext ? gl.getParameter(ext.UNMASKED_RENDERER_WEBGL)
                  : gl.getParameter(gl.RENDERER);
      return /swiftshader|llvmpipe|software|basic render/i.test(String(r || ""));
    } catch (e) {
      return true;
    }
  }

  var pref = fxPref();
  var ua = navigator.userAgent || "";
  var fxWin = /Windows/.test(ua) && /Firefox\//.test(ua);
  var reduced =
    pref === "reduced" ? true :
    pref === "full" ? false :
    (fxWin || softwareGl());

  if (reduced) {
    document.documentElement.classList.add("sf-reduced");
    if (window.console && console.info) {
      console.info(
        "[streamflow] efeitos reduzidos (" +
        (pref === "reduced" ? "localStorage" : fxWin ? "Firefox/Windows" : "WebGL por software") +
        ") — localStorage.__OTC_TRACKER_FX__ = 'full' força o vidro; 'reduced' força este modo"
      );
    }
  }
})();

(function () {
  "use strict";

  var reduce =
    document.documentElement.classList.contains("sf-reduced") ||
    (window.matchMedia &&
     window.matchMedia("(prefers-reduced-motion: reduce)").matches);
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
