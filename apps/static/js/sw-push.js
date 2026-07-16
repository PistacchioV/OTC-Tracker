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
    'NDF Other Publisher': '/new_deals-ndf-otherpublisher', 'Index B3': '/index-b3',
    'Users': '/users-roles', 'Recon Comitente': '/reconciliation-comitente',
    'Reconciliation': '/reconciliation-payrec', 'Reference Data': '/reference-data',
    'Control Panel': '/control-panel', 'Accrual': '/accrual-swap', 'MtM': '/mtm-swap',
    'Intrag Option': '/intrag-option', 'Intrag NDF': '/intrag-ndf'
};

self.addEventListener('push', function (event) {
    event.waitUntil(
        fetch('/api/notifications', { credentials: 'include' })
            .then(function (r) { return r.ok ? r.json() : null; })
            .then(function (resp) {
                var title = 'OTC Tracker';
                var body = 'Nova atividade no OTC Tracker';
                var url = '/dashboard';
                if (resp && resp.success && resp.notifications && resp.notifications.length) {
                    var n = resp.notifications[0];
                    var detail = (n.detail || '').replace(/\s*\[ND:\d{4}-\d{2}-\d{2}\]/, '');
                    title = n.actor_name || n.actor_sid || 'OTC Tracker';
                    body = (n.action || '') + ' in ' + (n.page || '') +
                           (detail ? ' — ' + detail : '');
                    url = PAGE_URL[n.page] || '/dashboard';
                }
                return self.registration.showNotification(title, {
                    body: body,
                    icon: '/static/images/favicon.ico',
                    badge: '/static/images/favicon.ico',
                    tag: 'otc-activity',
                    renotify: true,
                    data: { url: url }
                });
            })
            .catch(function () {
                return self.registration.showNotification('OTC Tracker', {
                    body: 'Nova atividade no OTC Tracker',
                    icon: '/static/images/favicon.ico',
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
