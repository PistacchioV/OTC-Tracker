# `scripts/tests/` — verificações de regressão

Scripts autocontidos, sem framework. Cada um imprime `ok`/`FAIL` por asserção e sai com
código **0** (tudo passou) ou **1** (falhou), então servem tanto para rodar na mão quanto
para encadear.

Rodam de qualquer diretório: a raiz do repo é resolvida a partir do próprio arquivo
(`scripts/tests/` → `..` → `..`).

```bash
source .venv311/bin/activate
python scripts/tests/check_tickets.py
```

Nenhum deles encosta em dado real: o arquivo de tickets vai para um `tempfile`, o DuckDB é
recriado num tmp, o Outlook e o SMTP são stubados. Nada sai da máquina.

| script | o que protege | rodar quando mexer em |
|---|---|---|
| `check_boxparse.py` | **paridade JS ↔ Python** do parser de booking recap — executa o JS de verdade no JavaScriptCore e compara campo a campo | `otc_boxparse.py` **ou** `static/js/pages/otc-fileupload.js` (§157) |
| `check_boxsched.py` | varredura agendada do box: dedup `Deal`+`Acronym`, amend preservando o B3 ID, e-mail sem deal não arquivado, roteamento por produto | o bloco de box scan em `routes.py` (§157) |
| `check_cancel_remove.py` | `_nd_cancel_in_file`: cancelado apaga a linha, **exceto** `Success` com B3 ID, que vira `Canceled` e fica à vista — e **quem conta como cancelado é só o `isCancelled`**: `isDead` é importado normalmente | `_nd_cancel_in_file`, `_api_rec_is_cancelled` ou os pulls da API (§156/§173) |
| `check_spb_status.py` | Recon Pay/Rec: só linha com coluna A = `Sucesso` entra na recon, **nas duas trilhas** do HistoricoMensagens | `_cli_spb` em `recon_payrec.py` (§160) |
| `check_tickets.py` | Support Center ponta a ponta: CRUD, as seis regras de permissão, ID sequencial, transição do e-mail de encerramento, JSON corrompido | `otc_tickets.py`, as rotas `/api/tickets*` ou os templates de ticket (§161) |
| `check_notif_sid.py` | `notifications.target_sid`: a migração numa tabela **sem** a coluna e o isolamento do sino nos três alvos (SID · papel · broadcast) | `_create_notification`, `_push_notify` ou `api_get_notifications` (§161) |
| `check_b3_pattern.py` | notação `"MY"`/`_` do B3 Code e o padrão `YYMMDD` dos arquivos CETIP — inclui **paridade com as duas cópias JS** e a prova de que os 12 markets PREFIX emitem o mesmo código de antes | `split_b3_pattern`/`build_b3_code`, o seed de `commodities-b3`, `_cetip_rules` ou `_CETIP_BEHAVIOUR` (§164) |
| `check_cem_sheets.py` | Accrual/CEM: as abas são lidas por **posição** (1ª summary, 2ª Kapital CETIP), a inversão 228/199 e o erro explícito quando falta a 2ª aba | `_acc_parse_cem_factors` ou `_acc_read_sheets` (§165) |
| `check_publisher_ndf.py` | Publisher × B3: linha **sem Match Tokens casa só pelo texto completo**, `NOTES = BACEN` roteia para Vanilla, e o roteamento antigo (`!= 'PTAX'`) continua valendo com o seed padrão | `_ndf_publisher_row`, `_ndf_publisher_is_bacen` ou o roteamento em `_ndf_deal_from_api` (§166) |
| `check_quote_type.py` | Tipo de Cotação e Fonte de Informação saem do cadastro (Commodities × B3) e **coluna vazia devolve o valor histórico**; inclui o casamento do subjacente contra o padrão `"MY"` e a **paridade com a cópia do navegador** (`b3-quote-config.js`) | `_b3_quote_cfg`/`_b3_code_matches`, os builders do Conecta ou `static/js/b3-quote-config.js` (§177) |
| `check_quoted_in_cents.py` | Quoted in Cents: a divisão por 100 **não olha a moeda** do strike — varre os quatro caminhos (Conecta e Intrag × NDF Comm e Opt Comm) mais as duas cópias no navegador atrás de qualquer termo de moeda na regra | `div100=`/`_cents`/`strike_effective` em `routes.py`, o `buildConectaFields` das duas páginas ou `_is_cents_factor` (§172) |
| `check_co12_roll.py` | Ticker CO1-2 (Brent rolling): em **dezembro** as duas últimas Datas de Verificação são do 2º futuro, nos demais meses só a última — com a frase de dezembro fixada byte a byte, o recuo em dias úteis e os futuros vindos do settlement | `_conf_co12_text` ou os builders de linha das confirmações de Termo/Opção (§178) |
| `check_conf_optcomm_brl.py` | Confirmação de Opção de Commodities em BRL: os dois documentos (USD × BRL) seguem **idênticos palavra a palavra** fora do cabeçalho do Anexo I, o cabeçalho bate célula a célula com o Word, e o **PDF usa o mesmo cabeçalho do template** | `opt-comm-strike-{usd,brl}.html`, `opcao_anexo_heads`/`opcao_pdf` ou `_CONF_OPT_FAMILY_TEMPLATES` (§171) |
| `check_amend_counterparty.py` | Amend da API: SPN/Client/Tax ID são comparados e aplicados, o deal é reencontrado **pelo Deal ID** quando o Client muda (sem duplicar a linha) e um `Success` só volta para a fila se a contraparte mudou de entidade. Confere também `AMEND_FIELD_COLS` × `COL_TO_JSON_FIELD` campo a campo | `_nd_api_amend`, `_ND_AMEND_SKIP`, `_nd_amend_find`/`_nd_amend_index` ou os `AMEND_FIELD_COLS` das páginas (§176) |
| `check_counterparty_lookup.py` | A ordem da busca da contraparte (accronym → identidade da Legal Entity → SPN da API), as duas armadilhas que já shiparam contraparte errada (Settlement Location não vira LE; perna interna não usa o SPN da API), o upgrade do `le-spn` e o badge/filtro Missing Counterparty na tela | `_ndf_ref_by_accronym`, `_ndf_le_refdata`, `_le_spn_upgrade`, os builders de deal da API ou `missing-counterparty.js` (§174) |
| `check_api_links.py` | Link da API virou cadastro: o **seed reproduz a URL histórica byte a byte**, `product`/`date` são sempre do código (um `product=NDF` esquecido na linha não desvia o pull de FXO), e sem cadastro o New Deals cai no endereço antigo enquanto o Unwinds falha pedindo registro | `athena_api.build_url`/`registered_url`, o seed de `api-links` ou os call sites do pull (§173) |
| `check_payrec_run.py` | Pay/Rec com **um botão só**: a dropzone é que decide a fonte (anexos × pasta de insumos) e as **duas cópias da regra** concordam — o teste chama `_gather_sources` de verdade e prova que `manual` sem anexo cai na pasta | `_gather_sources` em `recon_payrec.py`, o `run()` de `reconciliation-payrec.js` ou a toolbar da página (§180) |
| `check_theme_toggle.py` | Toggle claro/escuro: o tema são **três** atributos (`data-bs-theme` + `data-menu-color` + `data-topbar-color`) e o botão do topbar tem de trocar os três, passando pelo `LayoutCustomizer` — mais a classe que suprime as transições, conferida nos dois lados (JS e CSS) | `initThemeToggle` em `visual-refresh.js`, `changeTheme`/`_adjustLayout` em `app.js` ou as regras de logo em `_layout.scss`/`_topbar.scss` (§179) |
| `check_ops_trade_swap.py` | Trade Level (Other Products Summary), linha de **SWAP**: o join das **cinco fontes** por código, o dedup do swap que chega uma vez por Tipo Operação, a tabela de IR contra a fórmula da planilha (incluindo o vão do 721) e a **ordem das colunas nas três listas posicionais** (`<th>` · `rowMaker` · `_OPS_TRADE_COLS`) | `_ops_swap_trade_rows`/`_ops_swap_ir_rate`/`_ops_swap_pos_terms`, os seeds `swap-b3-events`/`swap-ir-*` ou a tabela Trade Level de `other-products-summary.html` (§182) |
| `check_swap_advice.py` | Settlement Advice de Swap: o universo **compartilhado** com o Trade Level (`_ops_swap_settling`, uma implementação só), a Data de Operação do **trade** (termo antes de início — errar sobe a alíquota do cliente), o IR encolhendo o líquido nos dois sinais, branco ≠ 0%, e a página **ligada** (rota, endpoint, `data-api`, e o sidenav sem a âncora morta) | `_swadv_rows`/`_SWADV_COLUMNS`/`_ops_swap_settling` ou `other-products-swap-settlement-advice.html` (§184) |
| `check_ops_summary.py` | Settlement Summary (Other Products), porte do NDF: o IR **encolhendo** o caixa nos dois sinais, Total Net × Pay/Rec, o **cruzamento** da conta (banco PAY → `DEFAULT_RECEIVE` do cliente), o net que **não** atravessa produto/LOB, a observação persistida e a prova de que a regra vem das funções `_ndfsum_*` em vez de ser uma segunda cópia | `_opssum_rows`/`_opssum_key`, os helpers `_ndfsum_net_type`/`_ndfsum_account_fmt`/`_ndfsum_obs_auto` ou a tabela Settlement Summary de `other-products-summary.html` (§183) |
| `check_summary_glow.py` | NDF Summary: a luz de fundo dos cards de reconciliação (verde = bateu, âmbar = verificar). Prende o que quebra **sem erro no console** — o nome das classes nos dois lados (JS escreve, CSS lê), a ordem do `:hover` contra o cinza de `.ops-widget:hover`, e o tema **claro pesando mais** que o escuro | as regras `.ops-recon.is-ok`/`.is-check` ou o `setRecon()` de `ndf-summary.html` (§181) |
| `check_ndf_pdf_cpty.py` | Ficha em PDF no aviso de NDF: **seed do mapping == tupla de fallback**, cadastro vazio desliga o anexo, arquivo ausente volta à lista histórica, e o match tolera acento/caixa/travessão | `_ndf_pdf_set`/`_NDF_PDF_COUNTERPARTIES` em `otc_emails.py` ou o seed de `ndf-pdf-cpty` (§169) |

## Dependência externa

`check_boxparse.py` e a **seção 5** do `check_quote_type.py` precisam do **JavaScriptCore** (`jsc`), que já vem no macOS em
`/System/Library/Frameworks/JavaScriptCore.framework/Versions/A/Helpers/jsc`. Ele existe
porque `otc_boxparse.py` é a **segunda cópia** de uma regra de negócio que também vive no
navegador — sem executar os dois lados, uma divergência (arredondamento, data fora de faixa)
passa em silêncio e só aparece como número errado na tela. Ver §157.

No Windows da equipe o `check_boxparse.py` não roda; o `check_quote_type.py` roda, apenas
pulando a seção de paridade (ele avisa na saída). Os demais rodam inteiros.
