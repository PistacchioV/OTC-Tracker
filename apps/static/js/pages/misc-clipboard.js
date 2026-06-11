/**
 * Template Name: OTC Tracker - Admin & Dashboard Template
 * By (Author): JPM
 * Module/App (File Name): Misc Clipboard
 */

const elements = document.querySelectorAll('[data-clipboard-target]');

if (elements && elements.length > 0) {
    new ClipboardJS(elements);
}