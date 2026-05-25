/**
 * Template Name: UBold - Admin & Dashboard Template
 * By (Author): Coderthemes
 * Module/App (File Name): Datatables Fixed Header
 */

document.addEventListener('DOMContentLoaded', () => {
    const tableElement = document.getElementById('fixed-header-data');
    if (tableElement) {
        new DataTable(tableElement, {
            fixedHeader: {
                header: true,
                headerOffset: 65
            },
            pageLength: 25,
            language: {
                paginate: {
                    first: '<i class="ti ti-chevrons-left"></i>',
                    previous: '<i class="ti ti-chevron-left"></i>',
                    next: '<i class="ti ti-chevron-right"></i>',
                    last: '<i class="ti ti-chevrons-right"></i>'
                }
            }
        });
    }
})