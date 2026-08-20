/**
 * Template Name: OTC Tracker - Admin & Dashboard Template
 * By (Author): JPMorgan Chase
 * Module/App (File Name): Apps Holidays Calendar
 */

/**
 * Os calendários vêm do REGISTRO (`/api/holidays/calendars`), não de literais:
 * um calendário criado pela tela não teria como estar escrito aqui. A lista
 * abaixo é o FALLBACK — os onze de sempre, idênticos ao seed do servidor —, e é
 * o que a página usa se o fetch falhar: melhor a tela de antes do que uma barra
 * lateral vazia.
 */
const HC_CAL_FALLBACK = [
    {name: 'ANBIMA',        file: 'anbima.json',        color: '#0d6efd', class: 'bg-primary-subtle text-primary',     drag: 'bg-primary-subtle text-primary border-primary'},
    {name: 'BURSA',         file: 'bursa.json',         color: '#6c757d', class: 'bg-secondary-subtle text-secondary', drag: 'bg-secondary-subtle text-secondary border-secondary'},
    {name: 'CBY_AGS',       file: 'cby_ags.json',       color: '#198754', class: 'bg-success-subtle text-success',     drag: 'bg-success-subtle text-success border-success'},
    {name: 'EURIBOR',       file: 'euribor.json',       color: '#dc3545', class: 'bg-danger-subtle text-danger',       drag: 'bg-danger-subtle text-danger border-danger'},
    {name: 'ICEAGS',        file: 'iceags.json',        color: '#0dcaf0', class: 'bg-info-subtle text-info',           drag: 'bg-info-subtle text-info border-info'},
    {name: 'IPE',           file: 'ipe.json',           color: '#f59e0b', class: 'bg-warning-subtle text-warning',     drag: 'bg-warning-subtle text-warning border-warning'},
    {name: 'LME',           file: 'lme.json',           color: '#374151', class: 'bg-dark-subtle text-dark',           drag: 'bg-dark-subtle text-dark border-dark'},
    {name: 'NYMEX',         file: 'nymex.json',         color: '#8b5cf6', class: 'bg-purple-subtle text-purple',       drag: 'bg-purple-subtle text-purple border-purple'},
    {name: 'PLATTS-ASIA',   file: 'platts_asia.json',   color: '#14b8a6', class: 'bg-teal-subtle text-teal',           drag: 'bg-teal-subtle text-teal border-teal'},
    {name: 'PLATTS-EUROPE', file: 'platts_europe.json', color: '#6366f1', class: 'bg-indigo-subtle text-indigo',       drag: 'bg-indigo-subtle text-indigo border-indigo'},
    {name: 'SOFR',          file: 'sofr.json',          color: '#ec4899', class: 'bg-pink-subtle text-pink',           drag: 'bg-pink-subtle text-pink border-pink'},
];

/** nome → cor, preenchido a partir do registro (o popup do feriado usa). */
const HC_CAL_COLORS = {};

function hcEsc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
        return {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c];
    });
}

/** '#8b5cf6' → '139,92,246'. Devolve null no que não for hex de 6 dígitos. */
function hcHexToRgb(hex) {
    const m = /^#?([0-9a-f]{6})$/i.exec(String(hex || '').trim());
    if (!m) return null;
    const n = parseInt(m[1], 16);
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255].join(',');
}

/**
 * CSS dos calendários criados pela tela. Os onze de sempre têm as classes
 * escritas no `<style>` da página; um calendário novo não teria como ter, e é
 * por isso que a regra dele nasce aqui, a partir da cor do registro — as MESMAS
 * cinco regras dos built-in (pill, borda do evento, ponto e link da list view e
 * a cor do pill do dayGrid), com o mesmo fundo a 15% de opacidade.
 */
function hcInjectCalendarCss(calendars) {
    const partes = [];
    calendars.forEach(function (c) {
        const cls = String(c.class || '').trim();
        if (!/^hc-cal-[a-z0-9_-]+$/.test(cls)) return;   // built-in: CSS já existe
        const rgb = hcHexToRgb(c.color);
        if (!rgb) return;
        const hex = c.color;
        partes.push(
            '.' + cls + '{background-color:rgba(' + rgb + ',.15)!important;color:' + hex + '!important}' +
            '.fc-event.' + cls + '{border-color:' + hex + '!important}' +
            '.fc-event.' + cls + ' .fc-event-title{color:' + hex + '!important}' +
            '.fc-list-event.' + cls + ' .fc-list-event-dot{border-color:' + hex + '!important}' +
            '.fc-list-event.' + cls + ' .fc-list-event-title a,.fc-list-event.' + cls + ' a{color:' + hex + '!important}' +
            '.fc-daygrid-event.' + cls + '{color:' + hex + '!important}'
        );
    });
    let tag = document.getElementById('hc-cal-styles');
    if (!tag) {
        tag = document.createElement('style');
        tag.id = 'hc-cal-styles';
        document.head.appendChild(tag);
    }
    tag.textContent = partes.join('\n');
}

/** Pills da barra lateral e opções do modal — as duas do mesmo registro. */
function hcRenderCalendarList(calendars) {
    const box = document.getElementById('external-events');
    const sel = document.getElementById('event-category');
    if (box) {
        box.querySelectorAll('.external-event').forEach(function (el) { el.remove(); });
        calendars.forEach(function (c) {
            const el = document.createElement('div');
            el.className = 'external-event fc-event fw-semibold ' + String(c.class || '');
            el.setAttribute('data-class', String(c.drag || c.class || ''));
            el.innerHTML = '<i class="ti ti-circle-filled me-2"></i>' + hcEsc(c.name);
            box.appendChild(el);
        });
    }
    if (sel) {
        const atual = sel.value;
        sel.innerHTML = '<option disabled value="">Select a Calendar</option>' +
            calendars.map(function (c) {
                return '<option value="' + hcEsc(c.class) + '">' + hcEsc(c.name) + '</option>';
            }).join('');
        // Mantém a escolha de quem já tinha o modal aberto; senão, o primeiro.
        sel.value = atual && sel.querySelector('option[value="' + CSS.escape(atual) + '"]')
            ? atual : (calendars[0] ? calendars[0].class : '');
    }
}

/** O registro, com queda para os literais quando o endpoint não responde. */
async function hcLoadCalendars() {
    let cals = HC_CAL_FALLBACK;
    try {
        const r = await fetch('/api/holidays/calendars');
        const d = r.ok ? await r.json() : null;
        if (d && d.ok && Array.isArray(d.calendars) && d.calendars.length) {
            cals = d.calendars;
        }
    } catch (e) {
        console.warn('[holidays] registro de calendários indisponível, usando o padrão', e);
    }
    Object.keys(HC_CAL_COLORS).forEach(function (k) { delete HC_CAL_COLORS[k]; });
    cals.forEach(function (c) { HC_CAL_COLORS[c.name] = c.color; });
    hcInjectCalendarCss(cals);
    hcRenderCalendarList(cals);
    return cals;
}

class CalendarSchedule {

    constructor() {
        this.body = document.body;
        this.modal = new bootstrap.Modal(document.getElementById('event-modal'), {backdrop: 'static'});
        this.calendar = document.getElementById('calendar');
        this.formEvent = document.getElementById('forms-event');
        this.btnNewEvent = document.querySelectorAll('.btn-new-event');
        this.btnDeleteEvent = document.getElementById('btn-delete-event');
        this.btnSaveEvent = document.getElementById('btn-save-event');
        this.modalTitle = document.getElementById('modal-title');
        this.calendarObj = null;
        this.selectedEvent = null;
        this.newEventData = null;
    }

    onEventClick(info) {
        // Se for um feriado carregado do JSON (tem extendedProps.calendar)
        if (info.event.extendedProps && info.event.extendedProps.calendar) {
            const calendar = info.event.extendedProps.calendar;
            const holidayName = info.event.extendedProps.holidayName || info.event.extendedProps.description;
            const date = info.event.start.toLocaleDateString('pt-BR', {
                weekday: 'long',
                year: 'numeric',
                month: 'long',
                day: 'numeric'
            });
            
            // Detectar tema para adaptar logo
            const isDark = document.documentElement.getAttribute('data-bs-theme') === 'dark'
                        || document.documentElement.classList.contains('dark')
                        || window.matchMedia('(prefers-color-scheme: dark)').matches;
            const logoSrc  = isDark ? '/static/images/logo-sm.png' : '/static/images/logo-sm-black.png';
            const calColor = HC_CAL_COLORS[calendar] || '#0066cc';
            const divider  = isDark ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.08)';

            const popupHtml = `
<div>
  <div style="text-align:center;margin-bottom:16px">
    <img src="${logoSrc}"
         style="height:28px;opacity:0.85;"
         alt="OTC Tracker">
  </div>
  <div style="display:flex;align-items:center;gap:9px;margin-bottom:14px;padding-bottom:14px;border-bottom:1px solid ${divider}">
    <span style="width:10px;height:10px;border-radius:50%;background:${calColor};flex-shrink:0;display:inline-block;box-shadow:0 0 0 3px ${calColor}30"></span>
    <span style="font-size:1rem;font-weight:700;letter-spacing:-0.015em;line-height:1">${calendar}</span>
  </div>
  <div class="hc-swal-row" style="display:flex;align-items:flex-start;gap:10px;margin-bottom:9px;opacity:0;transform:translateY(7px)">
    <span style="font-size:0.63rem;font-weight:700;color:#0066cc;background:rgba(0,102,204,0.08);border:1px solid rgba(0,102,204,0.16);padding:1px 7px;border-radius:999px;white-space:nowrap;margin-top:2px;flex-shrink:0">Holiday</span>
    <span style="font-size:0.87rem;line-height:1.45">${holidayName}</span>
  </div>
  <div class="hc-swal-row" style="display:flex;align-items:center;gap:10px;opacity:0;transform:translateY(7px)">
    <span style="font-size:0.63rem;font-weight:700;color:#0066cc;background:rgba(0,102,204,0.08);border:1px solid rgba(0,102,204,0.16);padding:1px 7px;border-radius:999px;white-space:nowrap;flex-shrink:0">Date</span>
    <span style="font-size:0.87rem">${date}</span>
  </div>
</div>`;

            Swal.fire({
                html: popupHtml,
                showCloseButton: true,
                confirmButtonText: 'OK',
                buttonsStyling: false,
                showClass: { popup: 'hc-swal-enter' },
                hideClass: { popup: 'hc-swal-exit'  },
                customClass: {
                    popup:         'hc-swal-popup',
                    htmlContainer: 'p-0',
                    confirmButton: 'btn btn-primary px-4',
                },
                didOpen: (popup) => {
                    popup.querySelectorAll('.hc-swal-row').forEach((row, i) => {
                        setTimeout(() => {
                            row.style.transition = 'opacity 300ms cubic-bezier(0.23,1,0.32,1), transform 300ms cubic-bezier(0.23,1,0.32,1)';
                            row.style.opacity    = '1';
                            row.style.transform  = 'translateY(0)';
                        }, 80 + i * 60);
                    });
                }
            });
            
            return;
        }
        
        // Comportamento padrão para eventos criados manualmente
        this.formEvent?.reset();
        this.formEvent.classList.remove('was-validated');
        this.newEventData = null;
        this.btnDeleteEvent.style.display = "block";
        this.modalTitle.text = ('Edit Event');
        this.modal.show();
        this.selectedEvent = info.event;
        
        // Preencher nome do feriado
        document.getElementById('event-title').value = this.selectedEvent.title;
        
        // Preencher data do feriado (converter para formato dd/mm/yyyy)
        const eventDate = this.selectedEvent.start;
        if (eventDate) {
            const year = eventDate.getFullYear();
            const month = String(eventDate.getMonth() + 1).padStart(2, '0');
            const day = String(eventDate.getDate()).padStart(2, '0');
            document.getElementById('event-date').value = `${day}/${month}/${year}`;
        }
        
        // Preencher categoria
        const categoryInput = document.getElementById('event-category');
        if (categoryInput) {
            const {classNames} = this.selectedEvent;
            categoryInput.value = Array.isArray(classNames) ? classNames.join(' ') : classNames || '';
        }
    }

    onSelect(info) {
        this.formEvent?.reset();
        this.formEvent?.classList.remove('was-validated');
        this.selectedEvent = null;
        this.newEventData = info;
        this.btnDeleteEvent.style.display = "none";
        this.modalTitle.text = ('Add New Event');
        this.modal.show();
        this.calendarObj.unselect();
        
        // Preencher data automaticamente com a data clicada
        if (info.date) {
            const year = info.date.getFullYear();
            const month = String(info.date.getMonth() + 1).padStart(2, '0');
            const day = String(info.date.getDate()).padStart(2, '0');
            document.getElementById('event-date').value = `${day}/${month}/${year}`;
        }
    }

    // Função para converter data do formato yyyy-mm-dd para dd/mm/yyyy
    formatDateToBR(dateStr) {
        if (!dateStr) return '';
        const [year, month, day] = dateStr.split('-');
        return `${day}/${month}/${year}`;
    }

    // Função para converter data do formato dd/mm/yyyy para yyyy-mm-dd
    formatDateToISO(dateStr) {
        if (!dateStr) return '';
        const [day, month, year] = dateStr.split('/');
        return `${year}-${month}-${day}`;
    }

    async init() {
        /*  Initialize the calendar  */
        const today = new Date();
        const self = this;
        const externalEventContainerEl = document.getElementById('external-events');

        // Pills, opções do modal, cores e CSS — tudo antes do Draggable, que
        // precisa dos `.external-event` já no DOM para reconhecê-los.
        self.calendars = await hcLoadCalendars();

        new FullCalendar.Draggable(externalEventContainerEl, {
            itemSelector: '.external-event',
            eventData: function (eventEl) {
                return {
                    title: eventEl.innerText,
                    classNames: eventEl.getAttribute('data-class')
                };
            }
        });

        // Carregar eventos dos JSONs. É o MESMO `fetchCalendarEvents` que o
        // "Create New Calendar" usa para pôr o calendário novo na tela sem
        // recarregar a página — duas conversões produziriam eventos diferentes
        // para o mesmo arquivo.
        const defaultEvents = [];
        for (const cal of self.calendars) {
            const evs = await self.fetchCalendarEvents(cal);
            console.log(`✅ ${cal.name}: ${evs.length} feriados carregados`);
            defaultEvents.push(...evs);
        }

        // cal - init
        self.calendarObj = new FullCalendar.Calendar(self.calendar, {

            plugins: [],
            slotDuration: '00:30:00', /* If we want to split day time each 15minutes */
            slotMinTime: '07:00:00',
            slotMaxTime: '19:00:00',
            themeSystem: 'bootstrap',
            bootstrapFontAwesome: false,
            buttonText: {
                today: 'Today',
                year: 'Year',
                month: 'Month',
                week: 'Week',
                day: 'Day',
                list: 'List',                
                prev: '<',
                next: '>'
            },
            buttonIcons: false,
            initialView: 'dayGridMonth',
            handleWindowResize: true,
            height: window.innerHeight - 240,
            headerToolbar: {
                left: 'prev,next today',
                center: 'title',
                right: 'multiMonthYear,dayGridMonth,timeGridWeek,timeGridDay,listMonth'
            },
            
            // Configuração específica para Year View
            views: {
                multiMonthYear: {
                    type: 'multiMonth',
                    duration: { years: 1 },
                    buttonText: 'Year',
                    multiMonthMaxColumns: 3,  // 3 meses por linha
                    multiMonthMinWidth: 350
                }
            },
            
            initialEvents: defaultEvents,
            editable: true,
            droppable: true, // this allows things to be dropped onto the calendar !!!
            dayMaxEventRows: 3, // Limita eventos por dia na year view
            selectable: true,
            
            // Click simples em uma data
            dateClick: function (info) {
                const currentView = self.calendarObj.view.type;
                
                // Se estiver na year view, navegar para o mês
                if (currentView === 'multiMonthYear') {
                    // Navegar para o mês da data clicada
                    self.calendarObj.changeView('dayGridMonth', info.dateStr);
                    console.log(`📅 Navegando para o mês: ${info.dateStr}`);
                    return;
                }
                
                // Comportamento padrão para outras views (abrir modal)
                self.onSelect(info);
            },
            
            // Evento de clique
            eventClick: function (info) {
                self.onEventClick(info);
            }
        });

        self.calendarObj.render();
        
        // Log de resumo
        console.log(`📅 Calendário de Feriados carregado com ${defaultEvents.length} eventos`);
        console.log('🗓️ Eventos por calendário:');
        const eventsByCalendar = defaultEvents.reduce((acc, event) => {
            const cal = event.extendedProps.calendar;
            acc[cal] = (acc[cal] || 0) + 1;
            return acc;
        }, {});
        console.table(eventsByCalendar);

        // Adicionar máscara de data dd/mm/yyyy
        const eventDateInput = document.getElementById('event-date');
        if (eventDateInput) {
            eventDateInput.addEventListener('input', function (e) {
                let value = e.target.value.replace(/\D/g, ''); // Remove tudo que não é número
                
                if (value.length >= 2) {
                    value = value.substring(0, 2) + '/' + value.substring(2);
                }
                if (value.length >= 5) {
                    value = value.substring(0, 5) + '/' + value.substring(5, 9);
                }
                
                e.target.value = value;
            });

            // Validação customizada de data
            eventDateInput.addEventListener('blur', function (e) {
                const value = e.target.value;
                if (value && value.length === 10) {
                    const [day, month, year] = value.split('/');
                    const date = new Date(year, month - 1, day);
                    
                    // Verificar se a data é válida
                    if (date.getDate() != day || date.getMonth() != (month - 1) || date.getFullYear() != year) {
                        e.target.setCustomValidity('Invalid date');
                    } else {
                        e.target.setCustomValidity('');
                    }
                }
            });
        }

        // on new event button click
        self.btnNewEvent.forEach(function (btn) {
            btn.addEventListener('click', function (e) {
                self.onSelect({
                    date: new Date(),
                    allDay: true
                });
            });
        });

        // save event
        self.formEvent?.addEventListener('submit', function (e) {
            e.preventDefault();
            const form = self.formEvent;

            // validation
            if (form.checkValidity()) {
                if (self.selectedEvent) {
                    // Editar evento existente
                    self.selectedEvent.setProp('title', document.getElementById('event-title').value);
                    self.selectedEvent.setProp('classNames', document.getElementById('event-category').value);
                    
                    // Atualizar data se foi editada (converter dd/mm/yyyy para yyyy-mm-dd)
                    const eventDateInput = document.getElementById('event-date').value;
                    if (eventDateInput) {
                        const [day, month, year] = eventDateInput.split('/');
                        const isoDate = `${year}-${month}-${day}`;
                        self.selectedEvent.setStart(isoDate);
                    }

                } else {
                    // Criar novo evento (converter dd/mm/yyyy para Date object)
                    const eventDateInput = document.getElementById('event-date').value;
                    let eventDate = self.newEventData.date;
                    let isoDate   = null;

                    if (eventDateInput) {
                        const [day, month, year] = eventDateInput.split('/');
                        eventDate = new Date(year, month - 1, day);
                        isoDate   = `${year}-${month}-${day}`;
                    }

                    const titleVal      = document.getElementById('event-title').value;
                    const categoryEl    = document.getElementById('event-category');
                    const calendarName  = categoryEl.options[categoryEl.selectedIndex].text;
                    const className     = categoryEl.value;

                    // Adiciona no FullCalendar de forma consistente com os eventos carregados do JSON
                    self.calendarObj.addEvent({
                        title: calendarName,
                        start: eventDate,
                        allDay: true,
                        className: className,
                        extendedProps: {
                            calendar:    calendarName,
                            holidayName: titleVal,
                            description: titleVal
                        }
                    });

                    // Persiste no JSON via API
                    if (isoDate) {
                        fetch('/api/holidays/save', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ calendar: calendarName, date: isoDate, title: titleVal })
                        })
                        .then(r => r.json())
                        .then(data => {
                            if (!data.ok) {
                                Swal.fire({
                                    title: 'Save error',
                                    text: data.error || 'Could not save holiday',
                                    icon: 'error',
                                    confirmButtonText: 'OK',
                                    buttonsStyling: false,
                                    customClass: { confirmButton: 'btn btn-danger mt-2' }
                                });
                            } else {
                                Swal.fire({
                                    title: 'Holiday saved',
                                    html: `<span style="font-size:.88rem"><strong>${titleVal}</strong> added to <strong>${calendarName}</strong></span>`,
                                    icon: 'success',
                                    timer: 2000,
                                    timerProgressBar: true,
                                    showConfirmButton: false
                                });
                            }
                        })
                        .catch(() => {
                            Swal.fire({
                                title: 'Network error',
                                text: 'Could not save the holiday.',
                                icon: 'error',
                                confirmButtonText: 'OK',
                                buttonsStyling: false,
                                customClass: { confirmButton: 'btn btn-danger mt-2' }
                            });
                        });
                    }
                }
                self.modal.hide();
            } else {
                e.stopPropagation();
                form.classList.add('was-validated');
            }
        });

        // delete event
        self.btnDeleteEvent.addEventListener('click', function (e) {
            if (self.selectedEvent) {
                self.selectedEvent.remove();
                self.selectedEvent = null;
                self.modal.hide();
            }
        });

        self.initNewCalendar();
    }

    /**
     * "Create New Calendar": nome + planilha na dropzone.
     *
     * A planilha tem UMA aba com três colunas (Holiday · Description · Holiday
     * Type) e só as duas primeiras viram feriado — a data da coluna A e o texto
     * da coluna B. Quem lê é o servidor (`/api/holidays/calendars`), que é onde
     * o arquivo é gravado; o navegador só entrega os bytes.
     */
    initNewCalendar() {
        const self = this;
        const modalEl = document.getElementById('calendar-modal');
        if (!modalEl) return;

        const modal   = new bootstrap.Modal(modalEl, {backdrop: 'static'});
        const dz      = document.getElementById('hc-dropzone');
        const input   = document.getElementById('hc-cal-file');
        const chip    = document.getElementById('hc-dz-file');
        const nameEl  = document.getElementById('hc-cal-name');
        const btnSave = document.getElementById('hc-cal-save');
        const errEl   = document.getElementById('hc-cal-error');
        let picked = null;

        const showErr = (msg) => {
            errEl.textContent = msg || '';
            errEl.classList.toggle('d-none', !msg);
        };
        const setFile = (f) => {
            picked = f || null;
            chip.innerHTML = picked
                ? '<i class="ti ti-file-spreadsheet me-1"></i>' + hcEsc(picked.name)
                : '';
            chip.classList.toggle('d-none', !picked);
            if (picked) showErr('');
        };

        document.querySelectorAll('.btn-new-calendar').forEach(function (btn) {
            btn.addEventListener('click', function () {
                nameEl.value = '';
                setFile(null);
                showErr('');
                input.value = '';
                modal.show();
            });
        });

        dz.addEventListener('click', () => input.click());
        dz.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); input.click(); }
        });
        input.addEventListener('change', () => setFile(input.files[0]));
        ['dragenter', 'dragover'].forEach(function (ev) {
            dz.addEventListener(ev, function (e) {
                e.preventDefault(); e.stopPropagation();
                dz.classList.add('hc-dz-over');
            });
        });
        ['dragleave', 'drop'].forEach(function (ev) {
            dz.addEventListener(ev, function (e) {
                e.preventDefault(); e.stopPropagation();
                dz.classList.remove('hc-dz-over');
            });
        });
        dz.addEventListener('drop', function (e) {
            const f = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
            if (f) setFile(f);
        });

        btnSave.addEventListener('click', async function () {
            const nome = (nameEl.value || '').trim();
            if (!nome)   { showErr('Please give the calendar a name.'); nameEl.focus(); return; }
            if (!picked) { showErr('Please drop the holidays spreadsheet.'); return; }

            const original = btnSave.innerHTML;
            btnSave.disabled = true;
            btnSave.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>Importing…';
            try {
                const fd = new FormData();
                fd.append('name', nome);
                fd.append('file', picked);
                const r = await fetch('/api/holidays/calendars', {method: 'POST', body: fd});
                const d = await r.json();
                if (!d.ok) { showErr(d.error || 'Could not create the calendar.'); return; }

                // Recarrega o registro (a pill, a opção do modal, a cor e o CSS
                // do calendário novo saem dele) e só então põe os feriados na
                // tela — sem recarregar a página.
                self.calendars = await hcLoadCalendars();
                const cal = self.calendars.find(c => c.name === d.calendar.name) || d.calendar;
                const events = await self.fetchCalendarEvents(cal);
                events.forEach(ev => self.calendarObj.addEvent(ev));

                modal.hide();
                Swal.fire({
                    title: 'Calendar created',
                    html: `<span style="font-size:.88rem"><strong>${hcEsc(cal.name)}</strong> · ${d.total} holiday(s) imported</span>`,
                    icon: 'success',
                    timer: 2400,
                    timerProgressBar: true,
                    showConfirmButton: false
                });
            } catch (e) {
                showErr('Network error. Could not create the calendar.');
            } finally {
                btnSave.disabled = false;
                btnSave.innerHTML = original;
            }
        });
    }

    /** Feriados de um calendário do registro, prontos para o FullCalendar. */
    async fetchCalendarEvents(cal) {
        try {
            const r = await fetch('/static/data/' + cal.file, {cache: 'no-store'});
            if (!r.ok) return [];
            const holidays = await r.json();
            return holidays.map(h => ({
                title: cal.name,
                start: h.date,
                allDay: true,
                className: cal.class,
                extendedProps: {
                    calendar: cal.name,
                    description: h.description || h.title,
                    holidayName: h.title
                }
            }));
        } catch (e) {
            return [];
        }
    }

}

document.addEventListener('DOMContentLoaded', function (e) {
    new CalendarSchedule().init();
});