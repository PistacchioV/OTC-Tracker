/**
 * Template Name: OTC Tracker - Admin & Dashboard Template
 * By (Author): 
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
                    autoProcessQueue: false,   // files are processed client-side via Import button
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
        'FCPO_BURSA_MYR': 'KO"MY"BNMK',
        // BRT_IPE vanilla tem linha PREFIX própria, restrita por trade type
        // ({V: …} = só vanilla; valor plano vale para os dois) — §251.
        'BRT_IPE':        { V: 'CO"MY"' }
    };

    // SPECIAL: o código depende de LÓGICA (a distância do contrato até a
    // liquidação), mas os dois códigos em si são cadastro — `near` é a coluna
    // B3 CODE e `far` a B3 CODE FAR. Fallback até o fetch. A linha do BRT_IPE
    // é SÓ da asiática ({A: …}); a vanilla sai da PREFIX acima (§251).
    var MARKET_SPECIAL_CODES = {
        'BRT_IPE': { A: { near: 'CO"MY"', far: 'CO1-2' } }
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
            Object.keys(MARKET_SPECIAL_CODES).forEach(function (k) { delete MARKET_SPECIAL_CODES[k]; });
            d.rows.forEach(function (row) {
                var typ  = String(row['TYPE'] || '').toUpperCase();
                var mkt  = String(row['MARKET'] || '').trim().toUpperCase();
                var code = String(row['B3 CODE'] || '');   // sem trim: 'C ' tem espaço no código
                var cal  = String(row['HOLIDAY CALENDAR'] || '').trim();
                // TRADE TYPE (§251): a linha só vale para o(s) tipo(s) da
                // coluna — 'V' vanilla, 'A' asiática; BOTH/vazio grava nas duas.
                var tt = String(row['TRADE TYPE'] || '').trim().toUpperCase();
                var flags = tt === 'VANILLA' ? ['V'] : tt === 'ASIAN' ? ['A'] : ['V', 'A'];
                if (mkt && cal) MARKET_TO_FX_HOLIDAY[mkt] = cal;
                if (typ === 'SPECIAL') {
                    if (mkt) flags.forEach(function (f) {
                        (MARKET_SPECIAL_CODES[mkt] = MARKET_SPECIAL_CODES[mkt] || {})[f] = {
                            near: code, far: String(row['B3 CODE FAR'] || '').trim()
                        };
                    });
                    return;
                }
                if (!mkt || !code) return;
                var alvo = typ.indexOf('PREFIX') !== -1 ? MARKET_DYNAMIC_PREFIX : MARKET_FIXED_CODES;
                flags.forEach(function (f) {
                    (alvo[mkt] = alvo[mkt] || {})[f] = code;
                });
            });
        })
        .catch(function () {});

    // -------------------------------------------------------------------------
    // Calculate B3 Underlying Asset Code from market + contract + vanilla flag
    // contract format: "May27", "Dec26", etc.
    // -------------------------------------------------------------------------
    // Ordem dos meses, para medir a DISTÂNCIA entre o contrato e a liquidação.
    // MONTH_CODES dá a LETRA da B3 ('H'), não o número do mês — e letra não se
    // subtrai.
    var MONTH_ABBR_ORDER = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                            'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

    function contractMonthYear(contract) {
        if (!contract) return null;
        var m = String(contract).trim().match(/^([A-Za-z]{3})(\d+)$/);
        if (!m) return null;
        var abbr = m[1].charAt(0).toUpperCase() + m[1].slice(1, 3).toLowerCase();
        var idx = MONTH_ABBR_ORDER.indexOf(abbr);
        if (idx < 0) return null;
        var y = parseInt(m[2], 10);
        if (m[2].length <= 2) y += 2000;       // 'Mar27' → 2027
        return { month: idx + 1, year: y };
    }

    function dateMonthYear(value) {
        // Os dois formatos que circulam: a tela grava dd/mm/yyyy, o input date
        // devolve yyyy-mm-dd.
        var s = String(value == null ? '' : value).trim().slice(0, 10);
        var m = s.match(/^(\d{2})\/(\d{2})\/(\d{4})$/);
        if (m) return { month: +m[2], year: +m[3] };
        m = s.match(/^(\d{4})-(\d{2})-(\d{2})$/);
        if (m) return { month: +m[2], year: +m[1] };
        return null;
    }

    // Quantos MESES de calendário o contrato está à frente da liquidação. O dia
    // não entra: o que define o código B3 é o mês. null = não deu para ler, e
    // quem chama trata isso como "não sei", não como zero.
    function monthsAhead(settleDate, contract) {
        var c = contractMonthYear(contract), d = dateMonthYear(settleDate);
        if (!c || !d) return null;
        return (c.year - d.year) * 12 + (c.month - d.month);
    }

    // Valor do mapa para este market E este trade type (§251): formato novo
    // {mkt: {V: …, A: …}} — a coluna TRADE TYPE restringe a linha à vanilla
    // ('V') ou à asiática ('A'). Valor plano (formato antigo) vale para os dois.
    function b3MapEntry(mapping, mkt, isVanilla) {
        var e = mapping[mkt];
        if (e && typeof e === 'object' && ('V' in e || 'A' in e)) {
            return e[isVanilla ? 'V' : 'A'];
        }
        return e;
    }

    function calculateB3Id(market, contract, isVanilla, settleDate) {
        if (!market || !contract) return '';
        var mkt = market.toUpperCase().trim();

        // Fixed code — return immediately
        var fx = b3MapEntry(MARKET_FIXED_CODES, mkt, isVanilla);
        if (fx) return fx;

        // SPECIAL: os dois códigos vêm do cadastro; qual dos dois sai é lógica.
        // No BRT_IPE a linha SPECIAL é hoje SÓ da asiática (a vanilla tem linha
        // PREFIX própria, CO"MY" — §251): contrato no mês seguinte à liquidação
        // usa o do mês, dois meses ou mais usa o distante (CO1-2) — §212. O
        // ramo isVanilla fica para linha SPECIAL cadastrada como BOTH/VANILLA.
        var sp = b3MapEntry(MARKET_SPECIAL_CODES, mkt, isVanilla);
        if (sp) {
            if (isVanilla || monthsAhead(settleDate, contract) === 1) {
                return buildB3Code(sp.near, contract) || sp.far;
            }
            return sp.far;
        }

        // Padrão do cadastro: parte fixa + mês/ano + parte fixa
        var pattern = b3MapEntry(MARKET_DYNAMIC_PREFIX, mkt, isVanilla);
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
        return fetch(assetsRoot + '/data/Subjacente.json', { cache: 'no-cache' })
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

    function quotedBadge(subjEntry) {
        if (!subjEntry) {
            return '<span class="badge text-bg-secondary rounded-pill">Missing B3</span>';
        }
        return isCentsFactor(subjEntry.fatorConversao)
            ? '<span class="badge text-bg-success rounded-pill">YES</span>'
            : '<span class="badge text-bg-warning rounded-pill">NO</span>';
    }

    // -------------------------------------------------------------------------
    // Generate a RFC-4122 v4 UUID (used as the cache file key for each deal)
    // -------------------------------------------------------------------------
    function generateUUID() {
        return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
            var r = Math.random() * 16 | 0;
            var v = c === 'x' ? r : (r & 0x3 | 0x8);
            return v.toString(16);
        });
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
    // Extract clean text from a table cell — strips HTML tags and normalises
    // non-breaking spaces ( ) that Outlook inserts in "empty" cells and
    // that String.prototype.trim() does NOT remove in some browsers.
    // -------------------------------------------------------------------------
    function getCellText(cell) {
        return (cell.textContent || '').replace(/ /g, ' ').replace(/\s+/g, ' ').trim();
    }

    // -------------------------------------------------------------------------
    // Parse email HTML and return deal objects.
    // Uses DOMParser on the full HTML to locate the correct table (the one
    // whose header row contains "DealName"), so emails with multiple tables
    // (forwarded headers, formatting wrappers, etc.) are handled correctly.
    // rows[headerIdx+1] = first client row (as-is)
    // rows[headerIdx+2] = second row (direction inverted → LAWTON) +
    //                     synthetic third row (JP Morgan side)
    // -------------------------------------------------------------------------
    function parseEmailHtml(htmlText) {
        if (!htmlText) return [];

        var parser = new DOMParser();
        var doc    = parser.parseFromString(htmlText, 'text/html');

        // Find the table that contains a "DealName" header cell
        var targetTable = null;
        var allTables   = doc.querySelectorAll('table');
        for (var ti = 0; ti < allTables.length; ti++) {
            var tbl   = allTables[ti];
            var cells = Array.from(tbl.querySelectorAll('th, td'));
            if (cells.some(function (c) {
                return getCellText(c).toLowerCase().replace(/[\s_]/g, '') === 'dealname';
            })) {
                targetTable = tbl;
                break;
            }
        }
        if (!targetTable) return [];

        var rows = Array.from(targetTable.querySelectorAll('tr'));
        if (rows.length < 2) return [];

        // Identify the header row
        var headerIdx = -1;
        for (var ri = 0; ri < rows.length; ri++) {
            var hcells = Array.from(rows[ri].querySelectorAll('th, td')).map(getCellText);
            if (hcells.some(function (h) { return h.toLowerCase().replace(/[\s_]/g, '') === 'dealname'; })) {
                headerIdx = ri;
                break;
            }
        }
        if (headerIdx === -1) return [];

        var headers = Array.from(rows[headerIdx].querySelectorAll('th, td')).map(getCellText);

        var deals = [];

        // First data row (as-is)
        var clientRow = rows[headerIdx + 1];
        if (clientRow) {
            var clientCells = Array.from(clientRow.querySelectorAll('td')).map(getCellText);
            if (clientCells.length) {
                var deal = {};
                headers.forEach(function (h, i) { deal[h] = clientCells[i] || ''; });
                deal._cells = clientCells;
                deals.push(deal);
            }
        }

        // Second data row (direction inverted → LAWTON client)
        var counterRow = rows[headerIdx + 2];
        if (counterRow) {
            var counterCells = Array.from(counterRow.querySelectorAll('td')).map(getCellText);
            if (counterCells.length) {
                var deal2 = {};
                headers.forEach(function (h, i) { deal2[h] = counterCells[i] || ''; });
                deal2._cells = counterCells;
                deal2._invertDirection = true;
                deals.push(deal2);

                // Synthetic third row — same data, JP Morgan client info
                var deal3 = {};
                headers.forEach(function (h, i) { deal3[h] = counterCells[i] || ''; });
                deal3._cells = counterCells;
                deal3._jpMorganRow = true;
                deals.push(deal3);
            }
        }

        return deals;
    }

    // -------------------------------------------------------------------------
    // Build DataTable row array (cols 0-34) from a parsed deal.
    // Returns { row: Array(35), data: Object } — row is added to the table,
    // data is the plain-value object saved to the JSON cache.
    // -------------------------------------------------------------------------
    // Escape untrusted, email-derived cell text before it is handed to
    // DataTables (which renders array cell data as HTML). Trusted, app-built
    // markup columns (checkbox, actions, status/quoted badges, client/taxid
    // inputs) are kept as-is via the `keep` index map.
    function _escHtml(v){ v = (v == null) ? '' : String(v); return v.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;'); }
    function _escRow(arr, keep){ return arr.map(function(c, i){ return keep[i] ? c : _escHtml(c); }); }

    function buildRow(deal, refMap, subjacenteIdx, makerSid, rowId, layout) {
        makerSid = makerSid || '';
        rowId    = rowId    || generateUUID();
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
        // A data de liquidação entra no cálculo do código B3 (BRT_IPE asiático),
        // por isso é lida ANTES dele.
        var settleDate   = fmtDateStr(getField(deal, 'SettlementDate') || getField(deal, 'SettleDate'));
        var b3Id         = calculateB3Id(market, contract, isVanilla, settleDate);

        // Subjacente lookup
        var subjEntry    = subjacenteIdx ? (subjacenteIdx[b3Id] || null) : null;
        var commodity    = subjEntry ? (subjEntry.commodity || '') : '';
        var quotedCents  = quotedBadge(subjEntry);

        // FX Holiday Schedule
        var fxHoliday    = MARKET_TO_FX_HOLIDAY[market] || '';

        // RefData lookup by Acronym
        var ref = (acronym && refMap[acronym]) ? refMap[acronym] : { spn: '', counterparty: '', taxId: '' };

        // Third row — JP Morgan side: original direction, JP Morgan client info
        if (deal._jpMorganRow) {
            acronym = 'JPMORGANBM';
            ref = { spn: '0023779', counterparty: 'BANCO J.P MORGAN S.A', taxId: '33.172.537/0001-98' };
        }

        // Second row always belongs to LAWTON — override ref data and acronym
        if (deal._invertDirection) {
            acronym = 'LAWTON';
            ref = { spn: '0037862', counterparty: 'LAWTON MULTIMERCADO EXCLUSIVO', taxId: '05.592.116/0001-80' };
        }

        // Date fields
        var spotDate     = fmtDateStr(getField(deal, 'SpotDate'));
        var fxConvDate   = fmtDateStr(getField(deal, 'FXConvDate') || getField(deal, 'FxConvDate'));
        var spotFxRate   = getField(deal, 'SpotFXRate') || getField(deal, 'SpotFxRate') || getField(deal, 'Spot FX Rate');

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
        if (deal._invertDirection) {
            if (direction === 'SELL') direction = 'BUY';
            else if (direction === 'BUY') direction = 'SELL';
        }

        var ACTIONS =
            '<div class="d-flex justify-content-center gap-1">' +
            '<a class="btn btn-success btn-sm rounded-circle btn-row-confirm" href="#" data-bs-toggle="tooltip" data-bs-placement="auto" data-bs-title="Confirm" data-bs-custom-class="tooltip-success"><i class="ti ti-check"></i></a>' +
            '<a class="btn btn-info btn-sm rounded-circle btn-row-edit" href="#" data-bs-toggle="tooltip" data-bs-placement="auto" data-bs-title="Edit" data-bs-custom-class="tooltip-info"><i class="ti ti-edit"></i></a>' +
            '<a class="btn btn-danger btn-sm rounded-circle btn-row-delete" href="#" data-bs-toggle="tooltip" data-bs-placement="auto" data-bs-title="Delete" data-bs-custom-class="tooltip-danger"><i class="ti ti-trash"></i></a>' +
            '<a class="btn btn-primary btn-sm rounded-circle btn-row-send" href="#" data-bs-toggle="tooltip" data-bs-placement="auto" data-bs-title="Send" data-bs-custom-class="tooltip-primary"><i class="ti ti-brand-telegram"></i></a>' +
            '</div>';

        var quotedPlain = !subjEntry
                            ? 'MISSING'
                            : isCentsFactor(subjEntry.fatorConversao) ? 'YES' : 'NO';

        var rowArray = _escRow([
            '<input class="form-check-input form-check-input-light fs-14 mt-0" type="checkbox" value="option">',  // col 0
            ACTIONS,                                                                                                // col 1
            '<span class="badge bg-info text-white bg-gradient">New</span>',                       // col 2  Status (match dealJsonToRow / filter render)
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
            spotFxRate,                                                                                             // col 27 SpotFXRate
            fxConvDate,                                                                                             // col 28 FXConvDate
            fixStart,                                                                                               // col 29 FixingStartDate
            fixEnd,                                                                                                 // col 30 FixingEndDate
            tradingBook,                                                                                            // col 31 TradingBook
            otherBook,                                                                                              // col 32 OtherBook
            quotedCents,                                                                                            // col 33 Quoted in Cents?
            makerSid,                                                                                               // col 34 Maker   (hidden)
            rowId                                                                                                   // col 35 RowID   (hidden)
        ], {0:1,1:1,2:1,10:1,11:1,33:1});

        // NDF-specific row (31 cols): no Premium, PremiumPerUnit, PremiumCCY, SpotDate
        var rowArrayNDF = _escRow([
            '<input class="form-check-input form-check-input-light fs-14 mt-0" type="checkbox" value="option">',  // col 0
            ACTIONS,                                                                                                // col 1
            '<span class="badge bg-info text-white bg-gradient">New</span>',                       // col 2  Status (match dealJsonToRow / filter render)
            dealName,                                                                                               // col 3  Deal
            '',                                                                                                     // col 4  B3 ID
            tradeDate,                                                                                              // col 5  Trade Date
            month,                                                                                                  // col 6  Month
            settleDate,                                                                                             // col 7  Settlement Date
            ref.spn,                                                                                                // col 8  SPN
            acronym,                                                                                                // col 9  Acronym
            ref.counterparty || '<input type="text" class="form-control form-control-sm" value="" placeholder="Client Name">',  // col 10 Client
            ref.taxId        || '<input type="text" class="form-control form-control-sm" value="" placeholder="Tax ID">',       // col 11 Tax ID
            tradeType,                                                                                              // col 12 Trade Type
            market,                                                                                                 // col 13 Market
            b3Id,                                                                                                   // col 14 Underlying Asset
            commodity,                                                                                              // col 15 Commodities
            fxHoliday,                                                                                              // col 16 FX Holiday Schedule
            notional,                                                                                               // col 17 Total Notional
            instrument,                                                                                             // col 18 Instrument
            contract,                                                                                               // col 19 Contract
            strike,                                                                                                 // col 20 Strike
            strikeCcy,                                                                                              // col 21 Strike Currency
            direction,                                                                                              // col 22 Direction
            spotFxRate,                                                                                             // col 23 SpotFXRate
            fxConvDate,                                                                                             // col 24 FXConvDate
            fixStart,                                                                                               // col 25 FixingStartDate
            fixEnd,                                                                                                 // col 26 FixingEndDate
            tradingBook,                                                                                            // col 27 TradingBook
            otherBook,                                                                                              // col 28 OtherBook
            quotedCents,                                                                                            // col 29 Quoted in Cents?
            makerSid,                                                                                               // col 30 Maker   (hidden)
        ], {0:1,1:1,2:1,10:1,11:1,29:1});

        var isNDF = (layout === 'ndf');

        var rowData = {
            Status:            'New',
            Deal:              dealName,
            B3_ID:             '',
            TradeDate:         tradeDate,
            Month:             month,
            SettlementDate:    settleDate,
            SPN:               ref.spn,
            Acronym:           acronym,
            Client:            ref.counterparty || '',
            TaxID:             ref.taxId        || '',
            TradeType:         tradeType,
            Market:            market,
            UnderlyingAsset:   b3Id,
            Commodities:       commodity,
            FXHolidaySchedule: fxHoliday,
            TotalNotional:     notional,
            Instrument:        instrument,
            Contract:          contract,
            Strike:            strike,
            StrikeCurrency:    strikeCcy,
            Direction:         direction,
            SpotFXRate:        spotFxRate,
            FXConvDate:        fxConvDate,
            FixingStartDate:   fixStart,
            FixingEndDate:     fixEnd,
            TradingBook:       tradingBook,
            OtherBook:         otherBook,
            QuotedInCents:     quotedPlain,
            Maker:             makerSid,
            Checker:           ''
        };

        // OPT layout keeps the 4 extra fields in the JSON cache
        if (!isNDF) {
            rowData.Premium       = premium;
            rowData.PremiumPerUnit = premiumPU;
            rowData.PremiumCCY    = premiumCcy;
            rowData.SpotDate      = spotDate;
        }

        return { row: isNDF ? rowArrayNDF : rowArray, data: rowData };
    }

    // -------------------------------------------------------------------------
    // Parse a Compound File Binary (OLE2/CFB) .msg and return the HTML body.
    // Properly follows the FAT sector chain so fragmented sector layouts
    // (common in older Outlook / Windows 10) are handled correctly.
    // Looks for MAPI property PR_HTML (0x1013): Unicode stream first, then Binary.
    // -------------------------------------------------------------------------
    function parseMsgHtml(arrayBuffer) {
        var dv = new DataView(arrayBuffer);
        var u8 = new Uint8Array(arrayBuffer);

        // OLE2 magic: D0 CF 11 E0 A1 B1 1A E1
        if (u8[0] !== 0xD0 || u8[1] !== 0xCF || u8[2] !== 0x11 || u8[3] !== 0xE0) return null;

        var sectorSize  = 1 << dv.getUint16(30, true);  // usually 512
        var miniSecSize = 1 << dv.getUint16(32, true);  // usually 64
        var fatCount    = dv.getUint32(44, true);
        var firstDirSec = dv.getUint32(48, true);
        var miniCutoff  = dv.getUint32(56, true);        // usually 4096
        var firstMFSec  = dv.getUint32(60, true);

        var END = 0xFFFFFFFE, FREE = 0xFFFFFFFF;
        function secOff(sec) { return (sec + 1) * sectorSize; }

        // Build FAT from the first 109 DIFAT entries in the header (covers ~7 MB files)
        var fat = [];
        for (var di = 0; di < Math.min(fatCount, 109); di++) {
            var fs = dv.getUint32(76 + di * 4, true);
            if (fs >= 0xFFFFFFFA) break;
            var foff = secOff(fs);
            for (var fi = 0; fi < sectorSize / 4; fi++) {
                fat.push(dv.getUint32(foff + fi * 4, true));
            }
        }

        // Follow a FAT sector chain and return the concatenated bytes (trimmed to maxBytes)
        function chainRead(startSec, maxBytes) {
            var parts = [], sec = startSec;
            while (sec !== END && sec !== FREE && sec < 0xFFFFFFFA) {
                parts.push(u8.slice(secOff(sec), secOff(sec) + sectorSize));
                sec = (fat[sec] !== undefined) ? fat[sec] : END;
            }
            var total = parts.reduce(function(a, p) { return a + p.length; }, 0);
            var out   = new Uint8Array(Math.min(total, maxBytes || total));
            var pos   = 0;
            for (var ci = 0; ci < parts.length && pos < out.length; ci++) {
                var n = Math.min(parts[ci].length, out.length - pos);
                out.set(parts[ci].subarray(0, n), pos);
                pos += n;
            }
            return out;
        }

        // Build mini-FAT
        var miniFat = [];
        if (firstMFSec !== END && firstMFSec !== FREE) {
            var mfb = chainRead(firstMFSec);
            var mfv = new DataView(mfb.buffer, mfb.byteOffset, mfb.byteLength);
            for (var mi = 0; mi < mfb.length / 4; mi++) miniFat.push(mfv.getUint32(mi * 4, true));
        }

        // Parse directory entries (each 128 bytes)
        var dirBuf  = chainRead(firstDirSec);
        var dirView = new DataView(dirBuf.buffer, dirBuf.byteOffset, dirBuf.byteLength);
        var entries = [];
        for (var ei = 0; ei * 128 < dirBuf.length; ei++) {
            var b  = ei * 128;
            var nl = dirView.getUint16(b + 64, true);
            var nm = '';
            for (var ni = 0; ni < (nl > 2 ? (nl - 2) / 2 : 0); ni++) {
                nm += String.fromCharCode(dirView.getUint16(b + ni * 2, true));
            }
            entries.push({
                name:     nm.toLowerCase(),
                type:     dirView.getUint8(b + 66),
                startSec: dirView.getUint32(b + 116, true),
                size:     dirView.getUint32(b + 120, true)
            });
        }

        // Root entry (index 0) holds the mini-stream container
        var miniStreamBuf = null;
        if (entries.length > 0 && entries[0].startSec !== END && entries[0].startSec !== FREE) {
            miniStreamBuf = chainRead(entries[0].startSec, entries[0].size);
        }

        function miniRead(startSec, maxBytes) {
            if (!miniStreamBuf) return new Uint8Array(0);
            var parts = [], sec = startSec;
            while (sec !== END && sec !== FREE && sec < 0xFFFFFFFA) {
                parts.push(miniStreamBuf.slice(sec * miniSecSize, sec * miniSecSize + miniSecSize));
                sec = (miniFat[sec] !== undefined) ? miniFat[sec] : END;
            }
            var total = parts.reduce(function(a, p) { return a + p.length; }, 0);
            var out   = new Uint8Array(Math.min(total, maxBytes || total));
            var pos   = 0;
            for (var ci = 0; ci < parts.length && pos < out.length; ci++) {
                var n = Math.min(parts[ci].length, out.length - pos);
                out.set(parts[ci].subarray(0, n), pos);
                pos += n;
            }
            return out;
        }

        function readEntry(e) {
            return (e.size < miniCutoff && miniStreamBuf)
                ? miniRead(e.startSec, e.size)
                : chainRead(e.startSec, e.size);
        }

        // Locate PR_HTML property streams:
        //   __substg1.0_1013001f = Unicode (UTF-16LE) — preferred
        //   __substg1.0_10130102 = Binary (UTF-8 or Windows-1252)
        var htmlBuf = null, isUnicode = false;
        for (var eid = 0; eid < entries.length; eid++) {
            var e = entries[eid];
            if (e.type !== 2) continue;  // stream entries only
            if (e.name === '__substg1.0_1013001f') {
                isUnicode = true;
                htmlBuf   = readEntry(e);
                break;
            }
            if (e.name === '__substg1.0_10130102' && !htmlBuf) {
                htmlBuf = readEntry(e);
                // keep scanning in case the Unicode variant appears later
            }
        }

        if (!htmlBuf || !htmlBuf.length) return null;

        var html;
        try {
            html = isUnicode
                ? new TextDecoder('utf-16le').decode(htmlBuf)
                : new TextDecoder('utf-8', { fatal: false }).decode(htmlBuf);
        } catch (ex) {
            try { html = new TextDecoder('windows-1252').decode(htmlBuf); } catch (ex2) { return null; }
        }

        var lo = html.toLowerCase();
        var ts = lo.indexOf('<table'), te = lo.lastIndexOf('</table>');
        if (ts !== -1 && te > ts) return html.slice(ts, te + 8);
        return html;  // return full HTML; parseEmailHtml will search for the table
    }

    // -------------------------------------------------------------------------
    // Extract HTML from .msg binary (Outlook compound document)
    // Pass 1: Proper OLE2/CFB parser  (handles sector fragmentation — root cause
    //         of failures on Windows 10 / older Outlook where sectors are not
    //         allocated contiguously in the file).
    // Pass 2: UTF-16LE byte scan (legacy heuristic fallback).
    // Pass 3: UTF-8 text scan (newer Outlook storing HTML as plain UTF-8).
    // -------------------------------------------------------------------------
    function extractHtmlFromMsg(arrayBuffer) {
        // Pass 1 — proper compound-file parser
        try {
            var r1 = parseMsgHtml(arrayBuffer);
            if (r1) return r1;
        } catch (e) { /* fall through */ }

        var bytes = new Uint8Array(arrayBuffer);

        // Pass 2 — UTF-16LE heuristic byte scan
        var startPat16 = [0x3C,0x00,0x74,0x00,0x61,0x00,0x62,0x00,0x6C,0x00,0x65,0x00];
        var endPat16   = [0x3C,0x00,0x2F,0x00,0x74,0x00,0x61,0x00,0x62,0x00,0x6C,0x00,0x65,0x00,0x3E,0x00];
        var startIdx = -1;
        outer16: for (var i = 0; i <= bytes.length - startPat16.length; i++) {
            for (var j = 0; j < startPat16.length; j++) { if (bytes[i + j] !== startPat16[j]) continue outer16; }
            startIdx = i; break;
        }
        if (startIdx !== -1) {
            var endIdx = -1;
            for (var k = startIdx; k <= bytes.length - endPat16.length; k++) {
                var ok16 = true;
                for (var l = 0; l < endPat16.length; l++) { if (bytes[k + l] !== endPat16[l]) { ok16 = false; break; } }
                if (ok16) { endIdx = k + endPat16.length; break; }
            }
            if (endIdx === -1) endIdx = bytes.length;
            try { return new TextDecoder('utf-16le').decode(bytes.slice(startIdx, endIdx)); } catch (e) {}
        }

        // Pass 3 — UTF-8 text scan
        try {
            var decoded = new TextDecoder('utf-8', { fatal: false }).decode(bytes);
            var lower   = decoded.toLowerCase();
            var s8 = lower.indexOf('<table'), e8 = lower.lastIndexOf('</table>');
            if (s8 !== -1 && e8 > s8) return decoded.slice(s8, e8 + 8);
        } catch (e2) {}

        return null;
    }

    // -------------------------------------------------------------------------
    // Extract the HTML body from a MIME-encoded text (EML files).
    // Handles multipart boundaries and Content-Transfer-Encoding: base64 / quoted-printable.
    // Returns the raw text unchanged when no MIME structure is detected.
    // -------------------------------------------------------------------------
    function extractHtmlFromMime(text) {
        if (!text || !/Content-Type\s*:/i.test(text)) return text;

        var boundaryMatch = text.match(/boundary\s*=\s*["']?([^"'\r\n;]+)/i);
        if (boundaryMatch) {
            var boundary = boundaryMatch[1].trim().replace(/["']/g, '');
            var parts = text.split(new RegExp('--' + boundary.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')));
            for (var i = 0; i < parts.length; i++) {
                if (/Content-Type\s*:\s*text\/html/i.test(parts[i])) {
                    return _decodeMimePart(parts[i]);
                }
            }
        }
        // Single-part: decode if needed
        return _decodeMimePart(text);
    }

    function _decodeMimePart(part) {
        var sepIdx = part.search(/\r?\n\r?\n/);
        var headers = sepIdx !== -1 ? part.slice(0, sepIdx) : '';
        var body    = sepIdx !== -1 ? part.slice(sepIdx).trim() : part;

        if (/Content-Transfer-Encoding\s*:\s*base64/i.test(headers)) {
            try { return atob(body.replace(/[\r\n\s]/g, '')); } catch (e) { return body; }
        }
        if (/Content-Transfer-Encoding\s*:\s*quoted-printable/i.test(headers)) {
            return body
                .replace(/=\r?\n/g, '')
                .replace(/=([0-9A-Fa-f]{2})/g, function (m, h) { return String.fromCharCode(parseInt(h, 16)); });
        }
        return body;
    }

    // -------------------------------------------------------------------------
    // Process a single email File object → returns Promise (resolves when row added)
    // -------------------------------------------------------------------------
    // Strip HTML tags and return trimmed plain text
    function _stripHtml(html) {
        var d = document.createElement('div');
        d.innerHTML = String(html || '');
        return (d.textContent || d.innerText || '').trim();
    }

    // -------------------------------------------------------------------------
    // Turn one email's HTML into deal rows: parse, add/amend DataTable rows and
    // persist to the cache. Shared by the dropzone path (processEmailFile) and
    // the automatic Outlook box scan (processBoxScan) so both routes process an
    // email identically. Returns the number of deals found.
    // -------------------------------------------------------------------------
    function importDealsFromHtml(htmlText, refMap, subjacenteIdx, tableInstance, makerSid, cacheEndpoint, rowLayout) {
        var deals   = parseEmailHtml(htmlText);
        var isNDF   = (rowLayout === 'ndf');
        var dataEnd = isNDF ? 29 : 33; // last data column index

        if (!window._OTC_AMEND_CHANGED_COLS) window._OTC_AMEND_CHANGED_COLS = {};

        deals.forEach(function (deal) {
            var built   = buildRow(deal, refMap, subjacenteIdx, makerSid, generateUUID(), rowLayout);
            var newRow  = built.row;
            var newData = built.data;

            var dealName = newData.Deal;
            var acronym  = newData.Acronym;

            // Search existing DataTable rows for same Deal + Acronym
            // Must use {search:'none', page:'all'} — default rows() only checks current page
            var existingRowApi = null, existingRowData = null;
            tableInstance.rows({search: 'none', page: 'all'}).every(function () {
                var d = this.data();
                if (_stripHtml(String(d[3] || '')) === dealName &&
                    _stripHtml(String(d[9] || '')) === acronym) {
                    existingRowApi  = this;
                    existingRowData = d;
                    return false; // break
                }
            });

            if (existingRowApi && existingRowData) {
                // ── AMEND: deal already imported, update with new email data ──
                var existingB3Id = _stripHtml(String(existingRowData[4] || ''));

                // Preserve B3 ID
                newRow[4]     = existingB3Id;
                newData.B3_ID = existingB3Id;

                // Set Amend status badge
                newRow[2]      = '<span class="badge text-bg-warning bg-gradient">Amend</span>';
                newData.Status = 'Amend';

                // Compute diff: which data columns changed?
                var changedCols = [];
                for (var c = 3; c <= dataEnd; c++) {
                    if (_stripHtml(String(newRow[c]            || '')) !==
                        _stripHtml(String(existingRowData[c]  || ''))) {
                        changedCols.push(c);
                    }
                }

                // Persist changed columns keyed by Deal name (used by drawCallback)
                window._OTC_AMEND_CHANGED_COLS[dealName] = changedCols;

                // Update DataTable row and redraw current page
                existingRowApi.data(newRow);
                tableInstance.draw(false);

                // Apply light-red background to changed cells on the fresh DOM node
                var freshNode = existingRowApi.node();
                if (freshNode && changedCols.length) {
                    changedCols.forEach(function (col) {
                        var cellNode = tableInstance.cell(freshNode, col).node();
                        if (cellNode) cellNode.style.backgroundColor = '#ffe0e0';
                    });
                }

                // PATCH the cache — Checker reset to '' intentionally (amended deal needs re-approval)
                var patchData = Object.assign({}, newData);
                var existingClient = _stripHtml(String(existingRowData[10] || ''));
                var patchUrl = isNDF
                    ? cacheEndpoint + '/' + encodeURIComponent(dealName) + '?client=' + encodeURIComponent(existingClient)
                    : cacheEndpoint + '/' + String(existingRowData[35] || '');
                if (!isNDF) {
                    var existingId = String(existingRowData[35] || '');
                    if (!existingId) {
                        // OPT: no UUID — treat as new row
                        tableInstance.row.add(newRow).draw(false);
                        fetch(cacheEndpoint, {
                            method: 'POST', headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify(newData)
                        }).catch(function (err) { console.warn('OTCFileUpload: cache save failed', err); });
                        return;
                    }
                    newRow[35]   = existingId;
                    newData.id   = existingId;
                    patchUrl     = cacheEndpoint + '/' + existingId;
                }
                fetch(patchUrl, {
                    method: 'PATCH', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(patchData)
                }).then(function(r) {
                    if (!r.ok) console.error('OTCFileUpload: cache PATCH failed', r.status, r.statusText, patchUrl);
                }).catch(function (err) { console.error('OTCFileUpload: cache PATCH error', err); });

            } else {
                // ── NEW ROW: deal not yet in table ───────────────────────────
                tableInstance.row.add(newRow).draw(false);
                fetch(cacheEndpoint, {
                    method:  'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body:    JSON.stringify(newData)
                }).then(function(r) {
                    if (!r.ok) console.error('OTCFileUpload: cache POST failed', r.status, r.statusText, newData.Deal);
                }).catch(function (err) {
                    console.error('OTCFileUpload: cache POST error', err);
                });
            }
        });
        return deals.length;
    }

    function processEmailFile(file, tableInstance, assetsRoot, makerSid, cacheEndpoint, rowLayout) {
        var ext = file.name.split('.').pop().toLowerCase();
        makerSid = makerSid || '';
        cacheEndpoint = cacheEndpoint || '/api/new-deals/opt-commodities/cache';
        rowLayout = rowLayout || 'opt';

        return Promise.all([loadRefData(assetsRoot), loadSubjacenteData(assetsRoot)])
            .then(function (results) {
                var refMap         = results[0];
                var subjacenteIdx  = results[1];

                return new Promise(function (resolve) {
                    function onText(htmlText) {
                        resolve(importDealsFromHtml(htmlText, refMap, subjacenteIdx,
                                                    tableInstance, makerSid, cacheEndpoint, rowLayout));
                    }

                    if (ext === 'msg') {
                        // Use backend to reliably extract HTML from .msg binary
                        var fd = new FormData();
                        fd.append('file', file);
                        fetch('/api/parse-msg-html', { method: 'POST', body: fd })
                            .then(function (r) { return r.json(); })
                            .then(function (data) {
                                if (data.ok && data.html) {
                                    onText(data.html);
                                } else {
                                    // Fallback: client-side binary parse
                                    var bin = new FileReader();
                                    bin.onload = function (e) {
                                        var html = extractHtmlFromMsg(e.target.result);
                                        if (html) { onText(html); }
                                        else {
                                            var txt = new FileReader();
                                            txt.onload = function (ev) { onText(extractHtmlFromMime(ev.target.result)); };
                                            txt.readAsText(file);
                                        }
                                    };
                                    bin.readAsArrayBuffer(file);
                                }
                            })
                            .catch(function () {
                                // Network error: fall back to client-side parse
                                var bin = new FileReader();
                                bin.onload = function (e) {
                                    var html = extractHtmlFromMsg(e.target.result);
                                    if (html) { onText(html); }
                                    else {
                                        var txt = new FileReader();
                                        txt.onload = function (ev) { onText(extractHtmlFromMime(ev.target.result)); };
                                        txt.readAsText(file);
                                    }
                                };
                                bin.readAsArrayBuffer(file);
                            });
                    } else {
                        // EML and HTML files: read as text then try MIME decoding
                        var reader = new FileReader();
                        reader.onload = function (e) { onText(extractHtmlFromMime(e.target.result)); };
                        reader.readAsText(file);
                    }
                });
            });
    }

    // -------------------------------------------------------------------------
    // Subject-based pre-filter helpers
    // -------------------------------------------------------------------------
    function _getEmlSubject(text) {
        // Extract Subject from MIME headers; handles folded continuation lines
        var m = text.match(/^Subject[ \t]*:[ \t]*([\s\S]*?)(?=\r?\n[^\t ]|$)/im);
        if (!m) return '';
        return m[1].replace(/\r?\n[\t ]+/g, ' ').trim();
    }

    function _getFileSubject(file) {
        var ext = file.name.split('.').pop().toLowerCase();
        if (ext === 'eml') {
            return new Promise(function(resolve) {
                var reader = new FileReader();
                reader.onload = function(e) {
                    var header = (e.target.result || '').slice(0, 4096);
                    resolve(_getEmlSubject(header) || file.name);
                };
                reader.onerror = function() { resolve(file.name); };
                reader.readAsText(file.slice(0, 4096));
            });
        }
        // .msg: Outlook names files after their subject; .html: use filename
        return Promise.resolve(file.name);
    }

    // -------------------------------------------------------------------------
    // i18n for the box-scan popups. Copy is authored in ENGLISH (rendered inline
    // so the popup is correct before/without translation) and tagged with
    // data-lang keys; _applyBoxTrans() then overrides each [data-lang] node from
    // the active language file (/static/data/translations/<lang>.json — the same
    // store app.js uses), interpolating {0},{1},… from the node's data-n* attrs.
    // Dynamic content (email counts, the raw error) stays outside the keys.
    // -------------------------------------------------------------------------
    var _BOX_EN = {
        'nd-box-unavailable-title': 'Box unavailable',
        'nd-box-unavailable-msg':   'Automatic box scan requires Outlook on the Windows environment.<br><br><small class="text-muted">Drop the files in the dropzone to import manually.</small>',
        'nd-box-none-title':        'No emails in the box',
        'nd-box-none-msg':          'No "Brazil Booking Recap" <strong>{0}</strong> email was found in the box.',
        'nd-box-nodeals-title':     'No Deals Found',
        'nd-box-nodeals-msg':       'No deal rows were found in the box emails.',
        'nd-box-complete-title':    'Import Complete',
        'nd-box-complete-msg':      '{0} deal(s) imported from {1} email(s) in the box.<br><small class="text-muted">{2} email(s) moved to New deals &gt; B2Bs Automatic.</small>',
        'nd-box-error-title':       'Box scan error',
        'nd-box-cancel-note':       '<br><br><small class="text-warning"><strong>{0} cancellation email(s) deleted from the box.</strong></small>'
    };
    var _boxTransCache = {};
    function _boxLang() {
        return (localStorage.getItem('__OTC_TRACKER_LANG__') || 'en').toLowerCase();
    }
    function _interp(s, args) {
        return String(s).replace(/\{(\d+)\}/g, function (_m, i) {
            return (args && args[i] != null) ? args[i] : '';
        });
    }
    // <span data-lang=key data-n0=.. > with the English text already inside.
    function _bxSpan(key, args) {
        var attrs = '';
        (args || []).forEach(function (v, i) {
            attrs += ' data-n' + i + '="' + String(v).replace(/&/g, '&amp;').replace(/"/g, '&quot;') + '"';
        });
        return '<span data-lang="' + key + '"' + attrs + '>' + _interp(_BOX_EN[key] || '', args) + '</span>';
    }
    function _applyBoxTrans(popup) {
        if (!popup) return;
        var lang = _boxLang();
        var apply = function (dict) {
            popup.querySelectorAll('[data-lang]').forEach(function (el) {
                var key = el.getAttribute('data-lang');
                var val = key.split('.').reduce(function (a, k) { return (a && a[k] != null) ? a[k] : null; }, dict);
                if (val == null) return;
                var args = [];
                for (var i = 0; el.getAttribute('data-n' + i) != null; i++) args.push(el.getAttribute('data-n' + i));
                el.innerHTML = _interp(val, args);
            });
        };
        if (lang === 'en') return;                       // English already inline
        if (_boxTransCache[lang]) { apply(_boxTransCache[lang]); return; }
        fetch('/static/data/translations/' + lang + '.json')
            .then(function (r) { return r.ok ? r.json() : {}; })
            .catch(function () { return {}; })
            .then(function (d) { _boxTransCache[lang] = d; apply(d); });
    }

    // -------------------------------------------------------------------------
    // Automatic route: when the Import button is clicked with an EMPTY dropzone,
    // sweep the shared Outlook box for this page's "Brazil Booking Recap" emails
    // (NDF Comm → Swap, Opt Comm → Option), process each one through the SAME
    // pipeline as a dropped file, then move it to Inbox > New deals > B2Bs
    // Automatic. 'Cancel' emails are deleted from the box server-side.
    // Returns { totalDeals, shownSwal } to match processDropzone's contract.
    // -------------------------------------------------------------------------
    function processBoxScan(tableInstance, assetsRoot, makerSid, cacheEndpoint, rowLayout) {
        var product = (rowLayout === 'ndf') ? 'ndf' : 'opt';
        var productLabel = (product === 'ndf') ? 'Swap' : 'Option';
        var importBtn = document.getElementById('importBtn');

        function setBtn(busy, label) {
            if (!importBtn) return;
            importBtn.disabled = busy;
            importBtn.innerHTML = busy
                ? '<i class="ti ti-loader-2 ti-spin me-1"></i> ' + (label || 'Scanning box...')
                : '<i class="ti ti-upload me-1"></i> Import';
        }
        setBtn(true, 'Scanning box...');

        return Promise.all([loadRefData(assetsRoot), loadSubjacenteData(assetsRoot)])
            .then(function (results) {
                var refMap        = results[0];
                var subjacenteIdx = results[1];
                return fetch('/api/new-deals/box-scan', {
                    method:  'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body:    JSON.stringify({ product: product })
                }).then(function (r) { return r.json(); })
                  .then(function (data) {
                    if (data && data.unavailable) {
                        setBtn(false);
                        Swal.fire({
                            title: _bxSpan('nd-box-unavailable-title'),
                            html:  _bxSpan('nd-box-unavailable-msg'),
                            icon:  'info', confirmButtonText: 'OK', confirmButtonColor: '#6c757d',
                            didOpen: function (p) { _applyBoxTrans(p); }
                        });
                        return { totalDeals: 0, shownSwal: true };
                    }
                    if (data && data.error) { throw new Error(data.error); }

                    var emails    = (data && data.emails) || [];
                    var cancelled = (data && data.cancelled) || [];
                    var totalDeals = 0, archived = 0;

                    // Process emails one at a time (same ordering guarantees as
                    // the dropzone), archiving each only after its deals import.
                    var chain = Promise.resolve();
                    emails.forEach(function (em) {
                        chain = chain.then(function () {
                            var count = importDealsFromHtml(em.html, refMap, subjacenteIdx,
                                                            tableInstance, makerSid, cacheEndpoint, rowLayout);
                            totalDeals += (count || 0);
                            if (count > 0 && em.entry_id) {
                                return fetch('/api/new-deals/box-archive', {
                                    method:  'POST',
                                    headers: { 'Content-Type': 'application/json' },
                                    body:    JSON.stringify({ entry_id: em.entry_id })
                                }).then(function (r) { return r.json(); })
                                  .then(function (res) { if (res && res.ok) archived++; })
                                  .catch(function () {});
                            }
                        });
                    });

                    return chain.then(function () {
                        setBtn(false);
                        if (totalDeals > 0) {
                            var _pageName = (cacheEndpoint || '').indexOf('ndf-commodities') !== -1 ? 'NDF Comm' : 'Opt Comm';
                            fetch('/api/notifications', {
                                method: 'POST', headers: { 'Content-Type': 'application/json' },
                                body: JSON.stringify({
                                    action: 'New Deals', page: _pageName,
                                    detail: totalDeals + ' deal' + (totalDeals !== 1 ? 's' : '') + ' imported (box)'
                                })
                            }).catch(function () {});
                        }

                        var cancelNote = cancelled.length
                            ? _bxSpan('nd-box-cancel-note', [cancelled.length])
                            : '';

                        if (emails.length === 0) {
                            Swal.fire({
                                title: _bxSpan('nd-box-none-title'),
                                html:  _bxSpan('nd-box-none-msg', [productLabel]) + cancelNote,
                                icon:  'info', confirmButtonText: 'OK', confirmButtonColor: '#6c757d',
                                didOpen: function (p) { _applyBoxTrans(p); }
                            });
                        } else if (totalDeals === 0) {
                            Swal.fire({
                                title: _bxSpan('nd-box-nodeals-title'),
                                html:  _bxSpan('nd-box-nodeals-msg') + cancelNote,
                                icon:  'warning', confirmButtonText: 'OK', confirmButtonColor: '#6c757d',
                                didOpen: function (p) { _applyBoxTrans(p); }
                            });
                        } else {
                            Swal.fire({
                                title: _bxSpan('nd-box-complete-title'),
                                html:  _bxSpan('nd-box-complete-msg', [totalDeals, emails.length, archived]) + cancelNote,
                                icon:  'success', confirmButtonText: 'OK', confirmButtonColor: '#0dcaf0',
                                didOpen: function (p) { _applyBoxTrans(p); }
                            });
                        }
                        return { totalDeals: totalDeals, shownSwal: true };
                    });
                  });
            })
            .catch(function (err) {
                console.error('OTCFileUpload: box scan error', err);
                setBtn(false);
                Swal.fire({
                    title: _bxSpan('nd-box-error-title'),
                    text:  err && err.message ? err.message : String(err),
                    icon:  'error', confirmButtonText: 'OK', confirmButtonColor: '#dc3545',
                    didOpen: function (p) { _applyBoxTrans(p); }
                });
                return { totalDeals: 0, shownSwal: true };
            });
    }

    // -------------------------------------------------------------------------
    // Process ALL files in the Dropzone and clear it afterwards.
    // Called by the Import button.
    // subjectBlockWords: string[] — files whose subject contains any of these
    //   words (case-insensitive) are silently skipped.
    // -------------------------------------------------------------------------
    function processDropzone(tableInstance, assetsRoot, makerSid, cacheEndpoint, rowLayout, subjectBlockWords) {
        makerSid = makerSid || '';
        cacheEndpoint = cacheEndpoint || '/api/new-deals/opt-commodities/cache';
        rowLayout = rowLayout || 'opt';
        subjectBlockWords = subjectBlockWords || [];

        var dz = window.myDropzone;
        if (!dz || !dz.files || dz.files.length === 0) {
            // Empty dropzone → automatic route: scan the shared Outlook box for
            // this page's booking-recap emails and process them identically.
            return processBoxScan(tableInstance, assetsRoot, makerSid, cacheEndpoint, rowLayout);
        }

        var importBtn = document.getElementById('importBtn');
        if (importBtn) {
            importBtn.disabled = true;
            importBtn.innerHTML = '<i class="ti ti-loader-2 ti-spin me-1"></i> Importing...';
        }

        var files = dz.files.slice(); // snapshot
        var blockUpper = subjectBlockWords.map(function(w) { return w.toUpperCase(); });

        function _isBlocked(subject) {
            var up = (subject || '').toUpperCase();
            return blockUpper.some(function(w) { return up.indexOf(w) !== -1; });
        }

        return Promise.all(files.map(function(f) { return _getFileSubject(f); }))
            .then(function(subjects) {
                var skippedFiles = [];
                var filesToProcess = [];
                files.forEach(function(file, i) {
                    if (_isBlocked(subjects[i])) {
                        skippedFiles.push(file.name);
                    } else {
                        filesToProcess.push(file);
                    }
                });
                if (skippedFiles.length) {
                    console.warn('[OTCFileUpload] Subject-blocked files skipped:', skippedFiles);
                }

                var totalDeals = 0;
                var chain = Promise.resolve();
                filesToProcess.forEach(function (file) {
                    chain = chain.then(function () {
                        return processEmailFile(file, tableInstance, assetsRoot, makerSid, cacheEndpoint, rowLayout)
                            .then(function (count) { totalDeals += (count || 0); });
                    });
                });
                return chain.then(function () {
                    dz.removeAllFiles(true);
                    if (importBtn) {
                        importBtn.disabled = false;
                        importBtn.innerHTML = '<i class="ti ti-upload me-1"></i> Import';
                    }
                    if (totalDeals > 0) {
                        var _pageName = (cacheEndpoint || '').indexOf('ndf-commodities') !== -1 ? 'NDF Comm' : 'Opt Comm';
                        fetch('/api/notifications', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({
                                action: 'New Deals',
                                page: _pageName,
                                detail: totalDeals + ' deal' + (totalDeals !== 1 ? 's' : '') + ' imported'
                            })
                        }).catch(function() {});
                    }
                    var skipNote = skippedFiles.length
                        ? '<br><br><small class="text-warning"><strong>' + skippedFiles.length +
                          ' file(s) ignored (subject contains: ' + subjectBlockWords.join(', ') +
                          '):</strong> ' + skippedFiles.join(', ') + '</small>'
                        : '';
                    if (filesToProcess.length === 0 && skippedFiles.length > 0) {
                        Swal.fire({
                            title: 'All Files Skipped',
                            html:  'All dropped files were ignored — their subject contains a blocked word (' +
                                   subjectBlockWords.join(', ') + ').' + skipNote,
                            icon:  'info',
                            confirmButtonText: 'OK',
                            confirmButtonColor: '#6c757d'
                        });
                    } else if (totalDeals === 0) {
                        Swal.fire({
                            title: 'No Deals Found',
                            html:  'No deal rows were found in the dropped file(s).<br><br>' +
                                   '<small class="text-muted">Supported formats: <strong>.msg</strong>, <strong>.eml</strong>, <strong>.html</strong>.<br>' +
                                   'The email must contain a table with a <em>DealName</em> column header.</small>' + skipNote,
                            icon:  'warning',
                            confirmButtonText: 'OK',
                            confirmButtonColor: '#6c757d'
                        });
                    } else if (skippedFiles.length > 0) {
                        Swal.fire({
                            title: 'Import Complete',
                            html:  skippedFiles.length + ' file(s) were ignored (blocked subject).' + skipNote,
                            icon:  'info',
                            confirmButtonText: 'OK',
                            confirmButtonColor: '#0dcaf0'
                        });
                    }
                    // Resolve with how many deals were imported and whether a Swal
                    // was already shown, so page-specific callers can chain extra
                    // post-import logic (e.g. premium-due-today alert) without
                    // clobbering an existing popup.
                    var _shownSwal = (filesToProcess.length === 0 && skippedFiles.length > 0)
                                     || totalDeals === 0 || skippedFiles.length > 0;
                    return { totalDeals: totalDeals, shownSwal: _shownSwal };
                }).catch(function (err) {
                    console.error('OTCFileUpload: error processing files', err);
                    dz.removeAllFiles(true);
                    if (importBtn) {
                        importBtn.disabled = false;
                        importBtn.innerHTML = '<i class="ti ti-upload me-1"></i> Import';
                    }
                    Swal.fire({
                        title: 'Import Error',
                        text:  err && err.message ? err.message : String(err),
                        icon:  'error',
                        confirmButtonText: 'OK',
                        confirmButtonColor: '#dc3545'
                    });
                    return { totalDeals: 0, shownSwal: true };
                });
            })
            .catch(function(err) {
                console.error('OTCFileUpload: subject extraction error', err);
                if (importBtn) {
                    importBtn.disabled = false;
                    importBtn.innerHTML = '<i class="ti ti-upload me-1"></i> Import';
                }
                return { totalDeals: 0, shownSwal: true };
            });
    }

    return {
        processDropzone:        processDropzone,
        processBoxScan:         processBoxScan,
        processEmailFile:       processEmailFile,
        calculateB3Id:          calculateB3Id,
        parseEmailHtml:         parseEmailHtml,
        MARKET_TO_FX_HOLIDAY:   MARKET_TO_FX_HOLIDAY,
        clearSubjacenteCache:   function() { _subjacenteCache = null; }
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