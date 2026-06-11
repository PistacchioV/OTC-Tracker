/**
 * Template Name: OTC Tracker - Admin & Dashboard Template
 * By (Author): JPM
 * Module/App (File Name): Apps Kanban
 */
document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll('[data-plugins="sortable"]').forEach(el => {
        new Sortable(el, {
            animation: 150,
            group: 'shared',
            ghostClass: 'sortable-item-ghost',
            forceFallback: true,
            emptyInsertThreshold: 100,
            chosenClass: 'sortable-item-active'
        });
    });
})