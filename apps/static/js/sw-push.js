/* OTC Tracker — Service Worker for Web Push.
 * Receives payloadless "tickle" pushes, fetches the latest notification from
 * the app (so no data transits the push service) and shows it — even when no
 * app tab is open (as long as the browser is running in the background). */

self.addEventListener('install', function (event) {
    self.skipWaiting();
});

self.addEventListener('activate', function (event) {
    event.waitUntil(self.clients.claim());
});

// Notification "page" label → the page it deep-links to when clicked. Kept in
// sync with PAGE_URL in partials/topbar.html so a push click and a bell click
// land on the same page.
var PAGE_URL = {
    'NDF Comm': '/new_deals-ndf-commodities', 'Opt Comm': '/new_deals-opt-commodities',
    'Opt FXO': '/new_deals-opt-fxo', 'NDF FWD Start': '/new_deals-ndf-fwdstart',
    'NDF Other Publisher': '/new_deals-ndf-otherpublisher',
    // Daily Settlement › NDF › Other Publisher — outra pagina, outro rotulo.
    'NDF Other Publisher (Settlement)': '/ndf-other-publisher',
    'NDF Vanilla': '/new_deals-ndf-vanilla', 'Index B3': '/index-b3',
    'Users': '/users-roles', 'Recon Comitente': '/reconciliation-comitente',
    'Recon FXO': '/reconciliation-fxo',
    'Reconciliation': '/reconciliation-payrec', 'Pending Confirmation': '/pending-confirmation',
    // A esteira de confirmacao manual.
    'Confirmation': '/manual-confirmation/monitor',
    'Reference Data': '/reference-data',
    'Control Panel': '/control-panel', 'Accrual': '/accrual-swap', 'MtM': '/mtm-swap',
    'Intrag Option': '/intrag-option', 'Intrag NDF': '/intrag-ndf',
    'Intrag DCE Option': '/intrag-dce-option',
    'Intrag Swap': '/intrag-swap',
    'Support': '/tickets-list',
    'Other Products Summary': '/other-products-summary',
    'NDF Summary': '/ndf-summary',
    'Operations B3': '/operations-b3',
    'OTM Settlements': '/otm-settlements',
    'Latam Desk Position': '/other-products-swap-latamdeskposition',
    'NDF Cockpit': '/ndf-cockpit',
    'Cognos': '/cognos',
    'File Interface': '/file-interpreter',
    'File Interpreter': '/file-interpreter',
    'Mapping': '/mapping',
    'Holidays Calendar': '/holidays-calendar'
};

self.addEventListener('push', function (event) {
    // `paginaCuida` fica FORA da cadeia porque o `.catch` do fim também precisa
    // dele: sem isso, uma falha no fetch fazia o balão genérico sair mesmo com
    // a janela aberta — a duplicata voltava justamente no caminho de erro, que
    // é o que ninguém testa.
    var paginaCuida = false;
    event.waitUntil(
        // QUEM AVISA É UM SÓ. O mesmo evento chega por dois caminhos — este
        // push e o `maybeNativeNotify` do topbar —, e com a aba ABERTA e sem
        // foco os dois disparavam: duas notificações para a mesma coisa, e com
        // `tag` diferente (`otc-activity` aqui, `otc-<id>` lá) o navegador nem
        // as sobrepunha. Aparecia uma embaixo da outra.
        //
        // Com uma janela do app aberta, quem avisa é a PÁGINA: ela tem o
        // `notification` inteiro na mão, sabe o id, marca como lida no clique e
        // navega sem recarregar. O push existe para quando NÃO há janela — é
        // por isso que ele existe. Basta UMA janela, focada ou não: o topbar já
        // decide sozinho se mostra (ele se cala quando a aba está em foco,
        // porque aí o toast da própria tela cobre).
        self.clients.matchAll({ type: 'window', includeUncontrolled: true })
            .then(function (janelas) {
                // Sentinela explícito: `null` também é o que o fetch devolve
                // quando a resposta não vem, e os dois casos pedem coisas
                // diferentes — sem janela e sem resposta, o balão genérico
                // ainda tem de sair.
                if (janelas && janelas.length) {
                    paginaCuida = true;
                    return 'PAGINA_CUIDA';
                }
                return fetch('/api/notifications', { credentials: 'include' })
                    .then(function (r) { return r.ok ? r.json() : null; });
            })
            .then(function (resp) {
                if (resp === 'PAGINA_CUIDA') { return; }
                var title = 'OTC Tracker';
                var body = 'Nova atividade no OTC Tracker';
                var url = '/dashboard';
                var tag = 'otc-activity';
                if (resp && resp.success && resp.notifications && resp.notifications.length) {
                    var n = resp.notifications[0];
                    var detail = (n.detail || '').replace(/\s*\[ND:\d{4}-\d{2}-\d{2}\]/, '');
                    // O TÍTULO começa pela marca. A linha de cima do balão é a
                    // ORIGEM (`localhost:8051`) e quem a escreve é o navegador —
                    // não há API que a troque —, então o nome do app tem de vir
                    // no primeiro pedaço que é nosso. Antes o título era o nome
                    // de quem agiu, e o balão não dizia de onde vinha.
                    // A AÇÃO fica no título junto com a marca: com só
                    // 'OTC Tracker', dois avisos empilhados ficariam idênticos e
                    // não daria para separá-los sem abrir.
                    title = 'OTC Tracker' + (n.action ? ' · ' + n.action : '');
                    body = (n.actor_name || n.actor_sid || '') +
                           (n.page ? ' · ' + n.page : '') +
                           (detail ? ' — ' + detail : '');
                    // A Recon FXO nasceu gravada com a página do Pay/Rec; as
                    // notificações antigas ainda carregam esse par. Mesma
                    // tradução do topbar.html e do `_notif_page_url`, senão o
                    // clique do push cai numa recon e o clique do sino noutra.
                    var nPage = (n.page === 'Reconciliation' && n.action === 'Recon FXO')
                                ? 'Recon FXO' : n.page;
                    url = PAGE_URL[nPage] || '/dashboard';
                    // A MESMA `tag` do topbar (`otc-<id>`). Ela é o que faz o
                    // navegador SOBREPOR em vez de empilhar: com tags
                    // diferentes, uma corrida entre os dois caminhos deixava as
                    // duas notificações na tela, uma embaixo da outra. O
                    // `matchAll` acima já evita a corrida; a tag é o cinto de
                    // segurança para o instante em que a janela fecha entre a
                    // checagem e o `showNotification`.
                    tag = 'otc-' + (Number(n.id) || 0);
                }
                return self.registration.showNotification(title, {
                    body: body,
                    // O `favicon-notif.png` é o chip AZUL do app com a marca em
                    // BRANCO, em 256×256. O fundo sólido é o motivo de ele
                    // existir: quem pinta o fundo do balão é o SISTEMA, claro ou
                    // escuro conforme o tema do Windows, então marca de fundo
                    // transparente só se lê num dos dois — as letras pretas somem
                    // no balão escuro e as brancas, no claro. O tamanho também é
                    // de propósito: o balão amplia o ícone para ~48px, e o
                    // `favicon.ico` de 16×16 saía lavado e borrado. A mesma
                    // imagem serve o caminho do `topbar.html` (aba aberta e sem
                    // foco); marcas diferentes fariam o mesmo aviso parecer de
                    // dois aplicativos.
                    icon: '/static/images/favicon-notif.png',
                    badge: '/static/images/favicon-notif.png',
                    tag: tag,
                    renotify: true,
                    data: { url: url }
                });
            })
            .catch(function () {
                if (paginaCuida) { return; }
                return self.registration.showNotification('OTC Tracker', {
                    body: 'Nova atividade no OTC Tracker',
                    icon: '/static/images/favicon-notif.png',
                    tag: 'otc-activity'
                });
            })
    );
});

self.addEventListener('notificationclick', function (event) {
    event.notification.close();
    var url = (event.notification.data && event.notification.data.url) || '/dashboard';
    event.waitUntil(
        self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then(function (list) {
            for (var i = 0; i < list.length; i++) {
                var c = list[i];
                if (c.url.indexOf(self.location.origin) === 0 && 'focus' in c) {
                    return c.focus();
                }
            }
            if (self.clients.openWindow) return self.clients.openWindow(url);
        })
    );
});
