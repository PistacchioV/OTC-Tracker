/**
 * Template Name: UBold - Admin & Dashboard Template
 * By (Author): Coderthemes
 * Module/App (File Name): Datatables Fixed Header
 */

document.addEventListener('DOMContentLoaded', () => {
    const tableElement = document.getElementById('fixed-columns');
    if (tableElement) {
        new DataTable(tableElement, {
            fixedColumns: {
                start: 1,
                end: 1
            },
            paging: false,
            scrollCollapse: true,
            scrollX: true,
            scrollY: 300,
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