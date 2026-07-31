/**
 * Template Name: OTC Tracker - Admin & Dashboard Template
 * By (Author): JPM
 * Module/App (File Name): Form Fileupload
 */

class FileUpload {
    constructor() {
        this.init();
    }

    init() {
        if (typeof Dropzone === 'undefined') {
            console.warn("Dropzone is not loaded.");
            return;
        }

        Dropzone.autoDiscover = false;

        const dropzones = document.querySelectorAll('[data-plugin="dropzone"]');
        if (dropzones) {
            dropzones.forEach(dropzoneEl => {
                const actionUrl = dropzoneEl.getAttribute('action') || '/';
                const previewContainer = dropzoneEl.dataset.previewsContainer;
                const uploadPreviewTemplate = dropzoneEl.dataset.uploadPreviewTemplate;

                const options = {
                    url: actionUrl,
                    // acceptedFiles: 'image/*',
                };

                if (previewContainer) {
                    options.previewsContainer = previewContainer;
                }

                if (uploadPreviewTemplate) {
                    const template = document.querySelector(uploadPreviewTemplate);
                    if (template) {
                        options.previewTemplate = template.innerHTML;
                    }
                }

                try {
                    const dz = new Dropzone(dropzoneEl, options);

                    // Expose dropzone globally so the Import button can access queued files
                    window.myDropzone = dz;

                    dz.on("addedfile", function (file) {
                        const ext = file.name.split('.').pop().toLowerCase();
                        const iconMap = {
                            'pdf':  { icon: 'ti ti-file-type-pdf', color: 'text-danger' },
                            'xlsx': { icon: 'ti ti-file-spreadsheet', color: 'text-success' },
                            'xls':  { icon: 'ti ti-file-spreadsheet', color: 'text-success' },
                            'csv':  { icon: 'ti ti-file-spreadsheet', color: 'text-success' },
                            'doc':  { icon: 'ti ti-file-type-doc', color: 'text-primary' },
                            'docx': { icon: 'ti ti-file-type-doc', color: 'text-primary' },
                            'txt':  { icon: 'ti ti-file-text', color: 'text-secondary' },
                            'png':  { icon: 'ti ti-photo', color: 'text-info' },
                            'jpg':  { icon: 'ti ti-photo', color: 'text-info' },
                            'jpeg': { icon: 'ti ti-photo', color: 'text-info' },
                            'zip':  { icon: 'ti ti-file-zip', color: 'text-warning' },
                            'rar':  { icon: 'ti ti-file-zip', color: 'text-warning' },
                            'ppt':  { icon: 'ti ti-file-type-ppt', color: 'text-danger' },
                            'pptx': { icon: 'ti ti-file-type-ppt', color: 'text-danger' },
                            'xml':  { icon: 'ti ti-file-code', color: 'text-warning' },
                            'json': { icon: 'ti ti-file-code', color: 'text-warning' },
                            'msg':  { icon: 'ti ti-mail', color: 'text-primary' },
                            'eml':  { icon: 'ti ti-mail', color: 'text-primary' },
                            'htm':  { icon: 'ti ti-file-code', color: 'text-info' },
                            'html': { icon: 'ti ti-file-code', color: 'text-info' },
                        };

                        const fileInfo = iconMap[ext] || { icon: 'ti ti-file', color: 'text-muted' };
                        const iconEl = file.previewElement.querySelector('.file-icon');
                        if (iconEl) {
                            iconEl.className = `file-icon fs-24 ${fileInfo.icon} ${fileInfo.color}`;
                        }
                        // Files are queued here and processed when the Import button is clicked
                    });
                } catch (e) {
                    console.error("Dropzone initialization failed:", e);
                }
            });
        }
    }
}

// =============================================================================
// OTCFileUpload — parses an Onshore/Offshore Deal Details HTML email and
// inserts rows into the new_deals-opt-commodities DataTable.
// =============================================================================
var OTCFileUpload = (function () {

    // -------------------------------------------------------------------------
    // Month code lookup — mirrors XLookup(contract[:3]) in Python
    // -------------------------------------------------------------------------
    var MONTH_CODES = {
        'January':   'F', 'February':  'G', 'March':    'H',
        'April':     'J', 'May':        'K', 'June':     'M',
        'July':      'N', 'August':     'Q', 'September':'U',
        'October':   'V', 'November':  'X', 'December': 'Z'
    };

    var MONTH_NAMES_ABBR = {
        'Jan':'January',  'Feb':'February', 'Mar':'March',
        'Apr':'April',    'May':'May',       'Jun':'June',
        'Jul':'July',     'Aug':'August',    'Sep':'September',
        'Oct':'October',  'Nov':'November',  'Dec':'December'
    };

    function expandMonth(abbr) {
        var key = abbr.charAt(0).toUpperCase() + abbr.slice(1, 3).toLowerCase();
        return MONTH_NAMES_ABBR[key] || abbr;
    }

    // -------------------------------------------------------------------------
    // Market → FX Holiday Schedule (exact user-provided table)
    // -------------------------------------------------------------------------
    var MARKET_TO_FX_HOLIDAY = {
        'BO_CBOT':                'CBY_AGS',
        'BRT_DTD':                'PLATTS-EUROPE',
        'BRT_IPE':                'IPE',
        'C_CBOT':                 'CBY_AGS',
        'CC_ICE':                 'ICEAGS',
        'COAL_HCC_FOB_AUS_TSI':   'PLATTS-ASIA',
        'CT_ICE':                 'ICEAGS',
        'FCPO_BURSA_MYR':         'BURSA',
        'FO_0.5%_ROT_BRG_FOB':    'PLATTS-EUROPE',
        'FO_0.5%_SING_FOB':       'PLATTS-ASIA',
        'HO_NYMEX':               'NYMEX',
        'HU_RBOB_NYMEX':          'NYMEX',
        'KC_ICE':                 'ICEAGS',
        'MAL_LME':                'LME',
        'MAL_MW_PREMIUM':         'LME',
        'MCU_LME':                'LME',
        'MFE_TSI':                'PLATTS-ASIA',
        'MNI_LME':                'LME',
        'MPB_LME':                'LME',
        'MSN_LME':                'LME',
        'MZN_LME':                'LME',
        'NG_NYMEX':               'NYMEX',
        'S_CBOT':                 'CBY_AGS',
        'SB_ICE':                 'ICEAGS',
        'SM_CBOT':                'CBY_AGS',
        'W_CBOT':                 'CBY_AGS',
        'WTI_NYMEX':              'NYMEX'
    };

    // -------------------------------------------------------------------------
    // Market → B3 Underlying Asset Code
    // Fixed codes: returned as-is regardless of contract month.
    // Dynamic codes: prefix + MONTH_CODE(contract[:3]) + contract[-1]
    // Special: só BRT_IPE (depende de vanilla/asian). O FCPO virou padrão no cadastro.
    // (Mirrors Python's market-to-code logic exactly.)
    // -------------------------------------------------------------------------
    var MARKET_FIXED_CODES = {
        'MPB_LME':              'LOPBDY',
        'MCU_LME':              'LOCADY',
        'MAL_LME':              'LOAHDY',
        'MZN_LME':              'LOZSDY',
        'MSN_LME':              'LOSNDY',
        'MNI_LME':              'LONIDY',
        'FO_0.5%_ROT_BRG_FOB':  'NAEB0011',
        'FO_0.5%_SING_FOB':     'NACX0005',
        'MAL_MW_PREMIUM':       'PMMUAKE0',
        'BRT_DTD':              'PCRUDTB1',
        'NG_NYMEX':             'NG1',
        'MFE_TSI':              'PFATIOCH',
        'COAL_HCC_FOB_AUS_TSI': 'PMTCLAUS'
    };

    // Padrões: "MY" = mês/ano do contrato, _ = espaço (ver buildB3Code).
    var MARKET_DYNAMIC_PREFIX = {
        'HU_RBOB_NYMEX':  'XB"MY"',
        'HO_NYMEX':       'HO"MY"',
        'SB_ICE':         'SB"MY"',
        'C_CBOT':         'C_"MY"',   // o _ é um espaço, e faz parte do código B3
        'S_CBOT':         'S_"MY"',
        'BO_CBOT':        'BO"MY"',
        'CC_ICE':         'CC"MY"',
        'W_CBOT':         'W_"MY"',
        'SM_CBOT':        'SM"MY"',
        'CT_ICE':         'CT"MY"',
        'KC_ICE':         'KC"MY"',
        'WTI_NYMEX':      'WTI"MY"', // not confirmed in B3 data; best guess
        'FCPO_BURSA_MYR': 'KO"MY"BNMK'
    };

    // De-para agora cadastrado na página Mapping (Commodities × B3). Os
    // literais acima são o fallback até o fetch responder — e se ele falhar, o
    // comportamento antigo continua. No sucesso os objetos são esvaziados e
    // repovoados, para uma linha REMOVIDA na tela não continuar valendo aqui.
    // A mesma resposta traz o HOLIDAY CALENDAR por market (MARKET_TO_FX_HOLIDAY)
    // e as linhas SPECIAL (BRT_IPE/FCPO), cujo código é calculado no código mas
    // cujo calendário vem daqui.
    fetch('/api/mappings/commodities-b3', { credentials: 'same-origin' })
        .then(function (r) { return r.json(); })
        .then(function (d) {
            if (!d || !d.success || !d.rows || !d.rows.length) return;
            Object.keys(MARKET_FIXED_CODES).forEach(function (k) { delete MARKET_FIXED_CODES[k]; });
            Object.keys(MARKET_DYNAMIC_PREFIX).forEach(function (k) { delete MARKET_DYNAMIC_PREFIX[k]; });
            Object.keys(MARKET_TO_FX_HOLIDAY).forEach(function (k) { delete MARKET_TO_FX_HOLIDAY[k]; });
            d.rows.forEach(function (row) {
                var typ  = String(row['TYPE'] || '').toUpperCase();
                var mkt  = String(row['MARKET'] || '').trim().toUpperCase();
                var code = String(row['B3 CODE'] || '');   // sem trim: 'C ' tem espaço no código
                var cal  = String(row['HOLIDAY CALENDAR'] || '').trim();
                if (mkt && cal) MARKET_TO_FX_HOLIDAY[mkt] = cal;
                if (!mkt || !code || typ === 'SPECIAL') return;
                if (typ.indexOf('PREFIX') !== -1) {
                    MARKET_DYNAMIC_PREFIX[mkt] = code;
                } else {
                    MARKET_FIXED_CODES[mkt] = code;
                }
            });
        })
        .catch(function () {});

    // -------------------------------------------------------------------------
    // Calculate B3 Underlying Asset Code from market + contract + vanilla flag
    // contract format: "May27", "Dec26", etc.
    // -------------------------------------------------------------------------
    function calculateB3Id(market, contract, isVanilla) {
        if (!market || !contract) return '';
        var mkt = market.toUpperCase().trim();

        // Fixed code — return immediately
        if (MARKET_FIXED_CODES[mkt]) return MARKET_FIXED_CODES[mkt];

        // BRT_IPE special: vanilla → CO + month + last_char, asian → CO1-2.
        // É o ÚNICO SPECIAL que sobrou: o código depende de vanilla/asian, que é
        // lógica, não de-para. O FCPO saiu daqui — virou o padrão KO"MY"BNMK no
        // cadastro Commodities × B3 (§164). Este arquivo emitia '.KOZ7BNMK F' e o
        // otc-fileupload.js emitia 'KOZ7BNMK' para o MESMO deal; com o cadastro
        // passa a existir um valor só.
        if (mkt === 'BRT_IPE') {
            if (isVanilla) {
                var mo = buildB3Code('CO', contract);
                return mo || 'CO1-2';
            }
            return 'CO1-2';
        }

        // Padrão do cadastro: parte fixa + mês/ano + parte fixa
        var pattern = MARKET_DYNAMIC_PREFIX[mkt];
        if (!pattern) {
            // Fallback: use part before first underscore
            var uIdx = mkt.indexOf('_');
            pattern = uIdx > 0 ? mkt.slice(0, uIdx) : mkt;
        }
        return buildB3Code(pattern, contract);
    }

    function contractParts(contract) {
        if (!contract) return null;
        var m = contract.trim().match(/^([A-Za-z]{3})(\d+)$/);
        if (!m) return null;
        var abbr = m[1].charAt(0).toUpperCase() + m[1].slice(1, 3).toLowerCase();
        var fullMonth = MONTH_NAMES_ABBR[abbr] || abbr;
        var monthCode = MONTH_CODES[fullMonth] || '';
        var yearLast = m[2].slice(-1); // last single digit e.g. "27" → "7"
        return { monthCode: monthCode, yearLast: yearLast };
    }

    // Notação do padrão B3 (coluna "B3 Code / Prefix" do cadastro Commodities × B3).
    //
    //   "MY"  → onde entram a letra do mês e o último dígito do ano do contrato.
    //           Vai entre ASPAS no cadastro justamente porque um código pode
    //           conter as letras M e Y como texto fixo — sem a marca não daria
    //           para saber qual é qual.
    //   _     → um ESPAÇO no código emitido. O código do milho na B3 é 'C ' (com
    //           o espaço), e um espaço no fim de um campo de texto é invisível na
    //           tela e some num trim distraído; o sublinhado torna-o visível.
    //
    //   KO"MY"BNMK  → KOZ7BNMK      XB"MY" → XBZ7      C_"MY" → 'C Z7'
    //
    // Padrão SEM aspas é lido como formato antigo (só o prefixo, mês/ano no
    // fim), o que mantém uma linha não migrada funcionando como antes.
    // ⚠️ Espelho de split_b3_pattern/build_b3_code em apps/pages/otc_boxparse.py —
    //    mexeu aqui, rode scripts/tests/check_b3_pattern.py.
    var B3_MY_RE = /"\s*MY\s*"/i;

    function splitB3Pattern(pattern) {
        var s = pattern == null ? '' : String(pattern);
        var m = B3_MY_RE.exec(s);
        var head = m ? s.slice(0, m.index) : s;
        var tail = m ? s.slice(m.index + m[0].length) : '';
        return { head: head.replace(/_/g, ' '), tail: tail.replace(/_/g, ' ') };
    }

    function buildB3Code(pattern, contract) {
        var parts = splitB3Pattern(pattern);
        var p = contractParts(contract);
        if (!p) return parts.head;
        return parts.head + p.monthCode + p.yearLast + parts.tail;
    }

    // -------------------------------------------------------------------------
    // Utility: format Date → dd/mm/yyyy
    // -------------------------------------------------------------------------
    function fmtDate(d) {
        if (!d || isNaN(d)) return '';
        return d.getDate().toString().padStart(2, '0') + '/' +
               (d.getMonth() + 1).toString().padStart(2, '0') + '/' +
               d.getFullYear();
    }

    // -------------------------------------------------------------------------
    // Parse common date strings → Date (or null)
    // Handles dd-mmm-yyyy (email TradeDate format), ISO, US, etc.
    // -------------------------------------------------------------------------
    function parseDate(s) {
        if (!s) return null;
        s = s.trim();
        // dd-mmm-yyyy or dd-mmm-yy  e.g. "21-May-2026"
        var dmy3 = s.match(/^(\d{1,2})[-\s\/]([A-Za-z]{3,})[-\s\/](\d{2,4})$/);
        if (dmy3) {
            var yr = +dmy3[3];
            if (yr < 100) yr += 2000;
            var abbr3 = dmy3[2].charAt(0).toUpperCase() + dmy3[2].slice(1, 3).toLowerCase();
            var moIdx3 = Object.keys(MONTH_NAMES_ABBR).indexOf(abbr3);
            if (moIdx3 === -1) moIdx3 = 0;
            return new Date(yr, moIdx3, +dmy3[1]);
        }
        // ISO: 2026-12-15
        var iso = s.match(/^(\d{4})-(\d{2})-(\d{2})$/);
        if (iso) return new Date(+iso[1], +iso[2] - 1, +iso[3]);
        // US: 12/15/2026
        var us = s.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
        if (us) return new Date(+us[3], +us[1] - 1, +us[2]);
        var d = new Date(s);
        return isNaN(d) ? null : d;
    }

    function fmtDateStr(s) {
        var d = parseDate(s);
        return d ? fmtDate(d) : (s || '');
    }

    // -------------------------------------------------------------------------
    // Extract full month name from TradeDate string (dd-mmm-yyyy)
    // e.g. "21-May-2026" → "May"  |  "19-Apr-2025" → "April"
    // -------------------------------------------------------------------------
    function extractMonthFromTradeDate(tradeDateRaw) {
        if (!tradeDateRaw) return '';
        // Matches dd-mmm-yyyy or dd/mmm/yyyy or dd mmm yyyy
        var m = tradeDateRaw.trim().match(/^\d{1,2}[-\/\s]([A-Za-z]{3,})[-\/\s]\d{2,4}$/);
        if (m) {
            var raw = m[1];
            // 3-char abbreviation → expand
            if (raw.length === 3) {
                var abbr = raw.charAt(0).toUpperCase() + raw.slice(1).toLowerCase();
                return MONTH_NAMES_ABBR[abbr] || (raw.charAt(0).toUpperCase() + raw.slice(1).toLowerCase());
            }
            // Full month name already
            return raw.charAt(0).toUpperCase() + raw.slice(1).toLowerCase();
        }
        // Fallback: try parseDate
        var d = parseDate(tradeDateRaw);
        if (d) {
            return Object.values(MONTH_NAMES_ABBR)[d.getMonth()];
        }
        return '';
    }

    // -------------------------------------------------------------------------
    // Extract Direction from Type column  e.g. "Sell Option (Put)" → "SELL"
    // -------------------------------------------------------------------------
    function extractDirection(typeStr) {
        if (!typeStr) return '';
        var t = typeStr.toUpperCase();
        if (t.indexOf('SELL') !== -1) return 'SELL';
        if (t.indexOf('BUY')  !== -1) return 'BUY';
        return '';
    }

    // -------------------------------------------------------------------------
    // Load RefData.json → acronym lookup map (cached)
    // -------------------------------------------------------------------------
    var _refDataCache = null;
    function loadRefData(assetsRoot) {
        if (_refDataCache) return Promise.resolve(_refDataCache);
        return fetch(assetsRoot + '/data/RefData.json')
            .then(function (r) { return r.json(); })
            .then(function (data) {
                var map = {};
                data.forEach(function (row) {
                    var commAcr = (row['COMMODITIES ACCRONYM'] || '').toUpperCase().trim();
                    var fxAcr   = (row['FX CASH ACCRONYM']     || '').toUpperCase().trim();
                    var entry   = {
                        spn:          row['SPN']          || '',
                        counterparty: row['COUNTERPARTY'] || '',
                        taxId:        row['TAX ID']       || ''
                    };
                    if (commAcr) map[commAcr] = entry;
                    if (fxAcr && !map[fxAcr]) map[fxAcr] = entry;
                });
                _refDataCache = map;
                return map;
            });
    }

    // -------------------------------------------------------------------------
    // "Quoted in Cents" ⇔ Fator Conversao = 0.01. Tolerant of string/comma
    // values and float noise so a 0.01 factor is never misread as "not cents".
    // (Mirrors _optIsCents/_ndfIsCents used in the New Deals templates.)
    // -------------------------------------------------------------------------
    function isCentsFactor(f) {
        if (f === null || f === undefined || f === '') return false;
        var n = (typeof f === 'string') ? parseFloat(f.replace(',', '.')) : Number(f);
        return isFinite(n) && Math.abs(n - 0.01) < 1e-9;
    }

    // Parse a raw Fator Conversao (number, "0.01", "0,01", null, "") → Number|null.
    function parseFator(fc) {
        if (fc === null || fc === undefined || fc === '') return null;
        var n = (typeof fc === 'string') ? parseFloat(fc.replace(',', '.')) : Number(fc);
        return isFinite(n) ? n : null;
    }

    // Merge one Subjacente row into the index under `key`. When a code appears
    // with conflicting factors, keep the cents factor (0.01); also let a defined
    // factor replace a null one and preserve the first non-empty commodity name.
    function _mergeSubjEntry(idx, key, commodity, fator) {
        if (!key) return;
        var prev = idx[key];
        if (!prev) {
            idx[key] = { commodity: commodity, fatorConversao: fator };
            return;
        }
        if (isCentsFactor(fator) || (prev.fatorConversao === null && fator !== null)) {
            prev.fatorConversao = fator;
        }
        if (!prev.commodity && commodity) prev.commodity = commodity;
    }

    // -------------------------------------------------------------------------
    // Load Subjacente.json → code lookup index (cached)
    // Index key: Ticker (when non-null) and Codigo do Ativo Subjacente
    // Value: { commodity, fatorConversao }  (fatorConversao is Number|null)
    // -------------------------------------------------------------------------
    var _subjacenteCache = null;
    function loadSubjacenteData(assetsRoot) {
        if (_subjacenteCache) return Promise.resolve(_subjacenteCache);
        return fetch(assetsRoot + '/data/Subjacente.json')
            .then(function (r) { return r.json(); })
            .then(function (data) {
                var idx = {};
                data.forEach(function (row) {
                    var commodity = row['Commodity'] || '';
                    var fator     = parseFator(row['Fator Conversao']);
                    var cod = (row['Codigo do Ativo Subjacente'] || '').trim();
                    var tkr = (row['Ticker'] || '').trim();
                    _mergeSubjEntry(idx, cod, commodity, fator);
                    _mergeSubjEntry(idx, tkr, commodity, fator);
                });
                _subjacenteCache = idx;
                return idx;
            });
    }

    // -------------------------------------------------------------------------
    // Build Quoted-in-Cents badge HTML from Fator Conversao value
    // 0.01 → badge success "YES"   |   other → badge warning "NO"
    // -------------------------------------------------------------------------
    // -------------------------------------------------------------------------
    // Format a numeric string as #,##0.00 (absolute value optional)
    // -------------------------------------------------------------------------
    function fmtNum2dp(val, absVal) {
        var n = parseFloat(String(val).replace(/,/g, ''));
        if (isNaN(n)) return val || '';
        if (absVal) n = Math.abs(n);
        return n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    }

    // -------------------------------------------------------------------------
    // Normalize currency codes: BRR → BRL, USB → USD
    // -------------------------------------------------------------------------
    function normalizeCcy(v) {
        if (!v) return '';
        var u = v.toUpperCase().trim();
        if (u === 'BRR') return 'BRL';
        if (u === 'USB') return 'USD';
        return v.trim();
    }

    function quotedBadge(fator) {
        return isCentsFactor(fator)
            ? '<span class="badge text-bg-success rounded-pill">YES</span>'
            : '<span class="badge text-bg-warning rounded-pill">NO</span>';
    }

    // -------------------------------------------------------------------------
    // Get field value from deal object by normalized name
    // (strips spaces and underscores before comparing)
    // -------------------------------------------------------------------------
    function getField(deal, name) {
        var lower = name.toLowerCase().replace(/[\s_]/g, '');
        var keys = Object.keys(deal);
        for (var i = 0; i < keys.length; i++) {
            if (keys[i].toLowerCase().replace(/[\s_]/g, '') === lower) {
                return deal[keys[i]];
            }
        }
        return '';
    }

    // -------------------------------------------------------------------------
    // Extract HTML table string from raw text (mirrors Python body.find logic)
    // -------------------------------------------------------------------------
    function extractTableHtml(bodyText) {
        var start = bodyText.indexOf('<table');
        if (start === -1) start = bodyText.indexOf('<TABLE');
        var end   = bodyText.indexOf('</table>');
        if (end   === -1) end = bodyText.indexOf('</TABLE>');
        if (start === -1 || end === -1) return null;
        return bodyText.slice(start, end + '</table>'.length);
    }

    // -------------------------------------------------------------------------
    // Parse email HTML and return deal objects.
    // rows[1] = header row,  rows[2] = client data  (mirrors Python indexing)
    // -------------------------------------------------------------------------
    function parseEmailHtml(htmlText) {
        var tableHtml = extractTableHtml(htmlText);
        if (!tableHtml) return [];

        var parser = new DOMParser();
        var doc    = parser.parseFromString(tableHtml, 'text/html');
        var table  = doc.querySelector('table');
        if (!table) return [];

        var rows = Array.from(table.querySelectorAll('tr'));
        if (rows.length < 3) return [];

        // Identify the header row (search for "DealName" in any row)
        var headerIdx = -1;
        for (var ri = 0; ri < rows.length; ri++) {
            var cells = Array.from(rows[ri].querySelectorAll('th, td')).map(function (c) { return c.textContent.trim(); });
            if (cells.some(function (h) { return h.toLowerCase().replace(/[\s_]/g, '') === 'dealname'; })) {
                headerIdx = ri;
                break;
            }
        }
        if (headerIdx === -1) return [];

        var headers = Array.from(rows[headerIdx].querySelectorAll('th, td')).map(function (c) { return c.textContent.trim(); });

        // Client data = headerIdx + 1 (mirrors Python rows[2] when header is rows[1])
        var clientRow = rows[headerIdx + 1];
        if (!clientRow) return [];

        var clientCells = Array.from(clientRow.querySelectorAll('td')).map(function (c) { return c.textContent.trim(); });
        if (!clientCells.length) return [];

        var deal = {};
        headers.forEach(function (h, i) { deal[h] = clientCells[i] || ''; });
        deal._cells = clientCells; // positional access: deal._cells[N] = column N+1
        return [deal];
    }

    // -------------------------------------------------------------------------
    // Build DataTable row array (32 values, cols 0-31) from a parsed deal.
    // -------------------------------------------------------------------------
    function buildRow(deal, refMap, subjacenteIdx) {
        var dealName     = getField(deal, 'DealName');
        var tradeDateRaw = getField(deal, 'TradeDate');
        var tradeDate    = fmtDateStr(tradeDateRaw);
        var month        = extractMonthFromTradeDate(tradeDateRaw);
        var contract     = getField(deal, 'Contract');
        var market       = (getField(deal, 'Market') || '').toUpperCase().trim();
        var acronym      = (getField(deal, 'Acronym') || '').toUpperCase().trim();
        var typeStr      = getField(deal, 'Type');

        // Fixing dates (raw strings for vanilla/asian comparison)
        var fixStartRaw  = getField(deal, 'FixingStartDate') || getField(deal, 'FixStart');
        var fixEndRaw    = getField(deal, 'FixingEndDate')   || getField(deal, 'FixEnd');
        var fixStart     = fmtDateStr(fixStartRaw);
        var fixEnd       = fmtDateStr(fixEndRaw);
        var isVanilla    = !!(fixStart && fixEnd && fixStart.trim() === fixEnd.trim());

        // Trade Type: VANILLA if start==end, else ASIAN (per user requirement)
        var tradeType    = isVanilla ? 'VANILLA' : 'ASIAN';

        // Instrument: comes directly from email column (5th col, header "Instrument")
        var instrument   = getField(deal, 'Instrument');

        // B3 ID (Codigo do Ativo Subjacente)
        var b3Id         = calculateB3Id(market, contract, isVanilla);

        // Subjacente lookup
        var subjEntry    = subjacenteIdx ? (subjacenteIdx[b3Id] || null) : null;
        var commodity    = subjEntry ? (subjEntry.commodity || '') : '';
        var quotedCents  = subjEntry && subjEntry.fatorConversao !== undefined
                            ? quotedBadge(subjEntry.fatorConversao)
                            : '';

        // FX Holiday Schedule
        var fxHoliday    = MARKET_TO_FX_HOLIDAY[market] || '';

        // RefData lookup by Acronym
        var ref = (acronym && refMap[acronym]) ? refMap[acronym] : { spn: '', counterparty: '', taxId: '' };

        // Date fields
        var settleDate   = fmtDateStr(getField(deal, 'SettlementDate') || getField(deal, 'SettleDate'));
        var spotDate     = fmtDateStr(getField(deal, 'SpotDate'));
        var fxConvDate   = fmtDateStr(getField(deal, 'FXConvDate') || getField(deal, 'FxConvDate'));

        // Numeric / text fields — try multiple header-name variants
        var notionalRaw  = getField(deal, 'TotalNotional') ||
                           getField(deal, 'Total Notional') ||
                           getField(deal, 'Notional') ||
                           getField(deal, 'Qty');
        var notional     = fmtNum2dp(notionalRaw, true); // absolute value, 2 dp

        var strike       = getField(deal, 'Strike');

        // Strike Currency: positional from email column 9 (index 8), normalized
        var strikeCcyRaw = (deal._cells && deal._cells[8]) ||
                           getField(deal, 'StrikeCCY') ||
                           getField(deal, 'StrikeCurrency') ||
                           getField(deal, 'Strike CCY') ||
                           getField(deal, 'StrikeCcy');
        var strikeCcy    = normalizeCcy(strikeCcyRaw);

        var premiumRaw   = getField(deal, 'Premium');
        var premium      = fmtNum2dp(premiumRaw, false); // keep sign, 2 dp
        var premiumPU    = getField(deal, 'PremiumPerUnit') || getField(deal, 'PremPU');

        var premiumCcyRaw = getField(deal, 'PremCCY') ||
                            getField(deal, 'PremiumCCY') ||
                            getField(deal, 'PremiumCurrency') ||
                            getField(deal, 'Prem CCY');
        var premiumCcy   = normalizeCcy(premiumCcyRaw);

        var tradingBook  = getField(deal, 'TradingBook') || getField(deal, 'Trading Book');
        var otherBook    = getField(deal, 'OtherBook')   || getField(deal, 'Other Book');
        var direction    = extractDirection(typeStr);

        var ACTIONS =
            '<div class="d-flex justify-content-center gap-1">' +
            '<a class="btn btn-success btn-sm rounded-circle btn-row-confirm" href="#" data-bs-toggle="tooltip" data-bs-placement="auto" data-bs-title="Confirm" data-bs-custom-class="tooltip-success"><i class="ti ti-check"></i></a>' +
            '<a class="btn btn-info btn-sm rounded-circle btn-row-edit" href="#" data-bs-toggle="tooltip" data-bs-placement="auto" data-bs-title="Edit" data-bs-custom-class="tooltip-info"><i class="ti ti-edit"></i></a>' +
            '<a class="btn btn-danger btn-sm rounded-circle btn-row-delete" href="#" data-bs-toggle="tooltip" data-bs-placement="auto" data-bs-title="Delete" data-bs-custom-class="tooltip-danger"><i class="ti ti-trash"></i></a>' +
            '<a class="btn btn-primary btn-sm rounded-circle btn-row-send" href="#" data-bs-toggle="tooltip" data-bs-placement="auto" data-bs-title="Send" data-bs-custom-class="tooltip-primary"><i class="ti ti-brand-telegram"></i></a>' +
            '</div>';

        return [
            '<input class="form-check-input form-check-input-light fs-14 mt-0" type="checkbox" value="option">',  // col 0
            ACTIONS,                                                                                                // col 1
            '<h4><span class="badge badge-label text-bg-info rounded-pill">New</span></h4>',                       // col 2  Status
            dealName,                                                                                               // col 3  Deal
            '',                                                                                                     // col 4  B3 ID (blank — filled manually later)
            tradeDate,                                                                                              // col 5  Trade Date
            month,                                                                                                  // col 6  Month
            settleDate,                                                                                             // col 7  Settlement Date
            ref.spn,                                                                                                // col 8  SPN
            acronym,                                                                                                // col 9  Acronym
            ref.counterparty || '<input type="text" class="form-control form-control-sm" value="" placeholder="Client Name">',  // col 10 Client
            ref.taxId        || '<input type="text" class="form-control form-control-sm" value="" placeholder="Tax ID">',       // col 11 Tax ID
            tradeType,                                                                                              // col 12 Trade Type (VANILLA/ASIAN)
            market,                                                                                                 // col 13 Market
            b3Id,                                                                                                   // col 14 Underlying Asset (Ativo Subjacente — B3 code)
            commodity,                                                                                              // col 15 Commodities
            fxHoliday,                                                                                              // col 16 FX Holiday Schedule
            notional,                                                                                               // col 17 Total Notional (abs, #,##0.00)
            instrument,                                                                                             // col 18 Instrument (from email)
            contract,                                                                                               // col 19 Contract
            strike,                                                                                                 // col 20 Strike
            strikeCcy,                                                                                              // col 21 Strike Currency (email col 9, normalized)
            direction,                                                                                              // col 22 Direction
            premium,                                                                                                // col 23 Premium (#,##0.00)
            premiumPU,                                                                                              // col 24 PremiumPerUnit
            premiumCcy,                                                                                             // col 25 PremiumCCY (normalized)
            spotDate,                                                                                               // col 26 SpotDate
            fxConvDate,                                                                                             // col 27 FXConvDate
            fixStart,                                                                                               // col 28 FixingStartDate
            fixEnd,                                                                                                 // col 29 FixingEndDate
            tradingBook,                                                                                            // col 30 TradingBook
            otherBook,                                                                                              // col 31 OtherBook
            quotedCents                                                                                             // col 32 Quoted in Cents?
        ];
    }

    // -------------------------------------------------------------------------
    // Extract HTML from .msg binary (Outlook compound document)
    // Scans for UTF-16LE encoded "<table" pattern and decodes the slice.
    // -------------------------------------------------------------------------
    function extractHtmlFromMsg(arrayBuffer) {
        var bytes = new Uint8Array(arrayBuffer);
        var startPat = [0x3C,0x00,0x74,0x00,0x61,0x00,0x62,0x00,0x6C,0x00,0x65,0x00];
        var endPat   = [0x3C,0x00,0x2F,0x00,0x74,0x00,0x61,0x00,0x62,0x00,0x6C,0x00,0x65,0x00,0x3E,0x00];

        var startIdx = -1;
        outer: for (var i = 0; i <= bytes.length - startPat.length; i++) {
            for (var j = 0; j < startPat.length; j++) { if (bytes[i + j] !== startPat[j]) continue outer; }
            startIdx = i;
            break;
        }
        if (startIdx === -1) return null;

        var endIdx = -1;
        for (var k = startIdx; k <= bytes.length - endPat.length; k++) {
            var ok = true;
            for (var l = 0; l < endPat.length; l++) { if (bytes[k + l] !== endPat[l]) { ok = false; break; } }
            if (ok) { endIdx = k + endPat.length; break; }
        }
        if (endIdx === -1) endIdx = bytes.length;

        try { return new TextDecoder('utf-16le').decode(bytes.slice(startIdx, endIdx)); }
        catch (e) { return null; }
    }

    // -------------------------------------------------------------------------
    // Process a single email File object → returns Promise (resolves when row added)
    // -------------------------------------------------------------------------
    function processEmailFile(file, tableInstance, assetsRoot) {
        var ext = file.name.split('.').pop().toLowerCase();

        return Promise.all([loadRefData(assetsRoot), loadSubjacenteData(assetsRoot)])
            .then(function (results) {
                var refMap         = results[0];
                var subjacenteIdx  = results[1];

                return new Promise(function (resolve) {
                    function onText(htmlText) {
                        var deals = parseEmailHtml(htmlText);
                        deals.forEach(function (deal) {
                            tableInstance.row.add(buildRow(deal, refMap, subjacenteIdx)).draw(false);
                        });
                        resolve(deals.length);
                    }

                    if (ext === 'msg') {
                        var bin = new FileReader();
                        bin.onload = function (e) {
                            var html = extractHtmlFromMsg(e.target.result);
                            if (html) { onText(html); }
                            else {
                                var txt = new FileReader();
                                txt.onload = function (ev) { onText(ev.target.result); };
                                txt.readAsText(file);
                            }
                        };
                        bin.readAsArrayBuffer(file);
                    } else {
                        var reader = new FileReader();
                        reader.onload = function (e) { onText(e.target.result); };
                        reader.readAsText(file);
                    }
                });
            });
    }

    // -------------------------------------------------------------------------
    // Process ALL files in the Dropzone and clear it afterwards.
    // Called by the Import button.
    // -------------------------------------------------------------------------
    function processDropzone(tableInstance, assetsRoot) {
        var dz = window.myDropzone;
        if (!dz || !dz.files || dz.files.length === 0) {
            alert('No files in the dropzone. Please drop email files (.msg, .eml, .html) first.');
            return;
        }
        var files = dz.files.slice(); // snapshot
        var chain = Promise.resolve();
        files.forEach(function (file) {
            chain = chain.then(function () {
                return processEmailFile(file, tableInstance, assetsRoot);
            });
        });
        chain.then(function () {
            dz.removeAllFiles(true);
        }).catch(function (err) {
            console.error('OTCFileUpload: error processing files', err);
            dz.removeAllFiles(true);
        });
    }

    return {
        processDropzone:  processDropzone,
        processEmailFile: processEmailFile,
        calculateB3Id:    calculateB3Id,
        parseEmailHtml:   parseEmailHtml
    };

}());

// =============================================================================

document.addEventListener("DOMContentLoaded", () => {
    new FileUpload();

    if (typeof FilePond !== 'undefined') {
        // FilePond Plugins
        try {
            FilePond.registerPlugin(FilePondPluginImagePreview);
        } catch (e) {
            console.warn("FilePond plugins registration failed:", e);
        }

        // multiple-file inputs
        const multiInputs = document.querySelectorAll("input.filepond-input-multiple");
        multiInputs.forEach(input => {
            FilePond.create(input);
        });

        // circle-style FilePond inputs
        const circleInputs = document.querySelectorAll("input.filepond-input-circle");
        circleInputs.forEach(input => {
            FilePond.create(input, {
                imageCropAspectRatio: "1:1",
                imageResizeTargetWidth: 200,
                imageResizeTargetHeight: 200,
                stylePanelLayout: "compact circle",
                styleLoadIndicatorPosition: "center bottom",
                styleProgressIndicatorPosition: "right bottom",
                styleButtonRemoveItemPosition: "left bottom",
                styleButtonProcessItemPosition: "right bottom",
                allowImagePreview: true,
                imagePreviewHeight: 100,
                labelIdle: `<i class="fs-32 text-muted ti ti-camera"></i>`,
            });
        });
    } else {
        console.warn("FilePond is not loaded.");
    }
});