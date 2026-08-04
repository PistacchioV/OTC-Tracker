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
| `check_quoted_in_cents.py` | Quoted in Cents: a divisão por 100 **não olha a moeda** do strike — varre os quatro caminhos (Conecta e Intrag × NDF Comm e Opt Comm) mais as duas cópias no navegador atrás de qualquer termo de moeda na regra | `div100=`/`_cents`/`strike_effective` em `routes.py`, o `buildConectaFields` das duas páginas ou `_is_cents_factor` (§172) |
| `check_conf_optcomm_brl.py` | Confirmação de Opção de Commodities em BRL: os dois documentos (USD × BRL) seguem **idênticos palavra a palavra** fora do cabeçalho do Anexo I, o cabeçalho bate célula a célula com o Word, e o **PDF usa o mesmo cabeçalho do template** | `opt-comm-strike-{usd,brl}.html`, `opcao_anexo_heads`/`opcao_pdf` ou `_CONF_OPT_FAMILY_TEMPLATES` (§171) |
| `check_counterparty_lookup.py` | A ordem da busca da contraparte (accronym → identidade da Legal Entity → SPN da API), as duas armadilhas que já shiparam contraparte errada (Settlement Location não vira LE; perna interna não usa o SPN da API), o upgrade do `le-spn` e o badge/filtro Missing Counterparty na tela | `_ndf_ref_by_accronym`, `_ndf_le_refdata`, `_le_spn_upgrade`, os builders de deal da API ou `missing-counterparty.js` (§174) |
| `check_api_links.py` | Link da API virou cadastro: o **seed reproduz a URL histórica byte a byte**, `product`/`date` são sempre do código (um `product=NDF` esquecido na linha não desvia o pull de FXO), e sem cadastro o New Deals cai no endereço antigo enquanto o Unwinds falha pedindo registro | `athena_api.build_url`/`registered_url`, o seed de `api-links` ou os call sites do pull (§173) |
| `check_ndf_pdf_cpty.py` | Ficha em PDF no aviso de NDF: **seed do mapping == tupla de fallback**, cadastro vazio desliga o anexo, arquivo ausente volta à lista histórica, e o match tolera acento/caixa/travessão | `_ndf_pdf_set`/`_NDF_PDF_COUNTERPARTIES` em `otc_emails.py` ou o seed de `ndf-pdf-cpty` (§169) |

## Dependência externa

`check_boxparse.py` precisa do **JavaScriptCore** (`jsc`), que já vem no macOS em
`/System/Library/Frameworks/JavaScriptCore.framework/Versions/A/Helpers/jsc`. Ele existe
porque `otc_boxparse.py` é a **segunda cópia** de uma regra de negócio que também vive no
navegador — sem executar os dois lados, uma divergência (arredondamento, data fora de faixa)
passa em silêncio e só aparece como número errado na tela. Ver §157.

No Windows da equipe esse script não roda; os outros rodam.
