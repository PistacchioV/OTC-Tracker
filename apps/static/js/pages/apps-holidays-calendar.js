/**
 * Template Name: OTC Tracker - Admin & Dashboard Template
 * By (Author): JPMorgan Chase
 * Module/App (File Name): Apps Holidays Calendar
 */

const HC_CAL_COLORS = {
    'ANBIMA':        '#0d6efd',
    'BURSA':         '#6c757d',
    'CBY_AGS':       '#198754',
    'EURIBOR':       '#dc3545',
    'ICEAGS':        '#0dcaf0',
    'IPE':           '#f59e0b',
    'LME':           '#374151',
    'NYMEX':         '#8b5cf6',
    'PLATTS-ASIA':   '#14b8a6',
    'PLATTS-EUROPE': '#6366f1',
    'SOFR':          '#ec4899',
};

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

        new FullCalendar.Draggable(externalEventContainerEl, {
            itemSelector: '.external-event',
            eventData: function (eventEl) {
                return {
                    title: eventEl.innerText,
                    classNames: eventEl.getAttribute('data-class')
                };
            }
        });

        // Mapeamento de calendários para arquivos JSON e cores
        const CALENDAR_CONFIG = {
            'ANBIMA': {
                file: 'anbima.json',
                className: 'bg-primary-subtle text-primary'
            },
            'BURSA': {
                file: 'bursa.json',
                className: 'bg-secondary-subtle text-secondary'
            },
            'CBY_AGS': {
                file: 'cby_ags.json',
                className: 'bg-success-subtle text-success'
            },
            'EURIBOR': {
                file: 'euribor.json',
                className: 'bg-danger-subtle text-danger'
            },
            'ICEAGS': {
                file: 'iceags.json',
                className: 'bg-info-subtle text-info'
            },
            'IPE': {
                file: 'ipe.json',
                className: 'bg-warning-subtle text-warning'
            },
            'LME': {
                file: 'lme.json',
                className: 'bg-dark-subtle text-dark'
            },
            'NYMEX': {
                file: 'nymex.json',
                className: 'bg-purple-subtle text-purple'
            },
            'PLATTS-ASIA': {
                file: 'platts_asia.json',
                className: 'bg-teal-subtle text-teal'
            },
            'PLATTS-EUROPE': {
                file: 'platts_europe.json',
                className: 'bg-indigo-subtle text-indigo'
            },
            'SOFR': {
                file: 'sofr.json',
                className: 'bg-pink-subtle text-pink'
            }
        };

        // Função para carregar feriados de todos os calendários
        const loadHolidays = async () => {
            const allEvents = [];
            const baseURL = '/static/data/';
            
            for (const [calendarName, config] of Object.entries(CALENDAR_CONFIG)) {
                try {
                    const response = await fetch(baseURL + config.file);
                    if (!response.ok) {
                        console.warn(`⚠️ Arquivo não encontrado: ${config.file}`);
                        continue;
                    }
                    
                    const holidays = await response.json();
                    
                    // Converter cada feriado para formato FullCalendar
                    const events = holidays.map(holiday => ({
                        title: calendarName,
                        start: holiday.date,
                        allDay: true,
                        className: config.className,
                        extendedProps: {
                            calendar: calendarName,
                            description: holiday.description || holiday.title,
                            holidayName: holiday.title
                        }
                    }));
                    
                    allEvents.push(...events);
                    console.log(`✅ ${calendarName}: ${holidays.length} feriados carregados`);
                    
                } catch (error) {
                    console.error(`❌ Erro ao carregar ${calendarName}:`, error);
                }
            }
            
            return allEvents;
        };

        // Carregar eventos dos JSONs
        const defaultEvents = await loadHolidays();

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
    }

}

document.addEventListener('DOMContentLoaded', function (e) {
    new CalendarSchedule().init();
});