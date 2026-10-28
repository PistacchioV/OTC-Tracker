# Migração dos bancos do OTC Tracker para o Snowflake — plano

Rascunho de 28/10/2026, revisto no mesmo dia com a página do Stratos sobre o
Snowflake (conexão, autenticação, liberação de rede — §3, D5 e D8). Ainda
**sem acesso**: o que depende dos valores do ambiente está marcado
**[A CONFIRMAR]** e se fecha com a Fase 0. O histórico das decisões vai para o
HANDOFF (§712 em diante).

---

## 1. Por que migrar, e o que muda

**Hoje** todo dado do app vive em DuckDB (§434): 188 arquivos `.db` na dev
(348 MB) e, na produção, 261 arquivos e 5,2 GB (o pacote do `exporta_dados.py`
de 27/10). Eles moram num share SMB — e, no Stratos, no EFS —, e quase toda
regra difícil do app nasceu daí:

- cada pessoa roda a própria instância sobre o MESMO `db/`, e a coordenação é
  por TRAVA DE ARQUIVO (`portalocker`, `.lock`, `.lock.w`, o portão
  `db_gate`, o permit por banco — §4 do CLAUDE.md);
- cada `stat`, abertura e trava é uma ida e volta de rede, e o "mudou?" do
  armazém é o `stat` do próprio `.db`;
- o limbo de checkpoint e o WAL que não replaya (§442, §447) exigem os scripts
  `recover_duckdb_wal.py`/`slim_duckdb.py` com todas as instâncias paradas;
- todas as máquinas precisam da mesma versão do DuckDB (§651);
- no Stratos, o EFS emula o `flock` com trava POSIX por processo (§689), e os
  bancos chegam por um pacote copiado à mão (§708).

**Com o Snowflake** o banco vira um SERVIDOR: transação no lugar da trava de
arquivo, nenhum pacote nem cópia de banco para levar ao Stratos, backup e Time
Travel do próprio serviço, nenhuma versão de motor para alinhar entre máquinas.

**Onde ele roda.** O caminho que o JPM oferece é o do `stratosblocks`: o token
vem do FID da solução e a rede passa pelo proxy do Stratos (D5, D8). Isso
existe no contêiner do Stratos e no Python do DevShell — não no Python com que
a instância Windows da equipe roda (o do `start-otc-tracker.bat`). Então o
Snowflake entra no app PELO STRATOS: a instância Windows segue em DuckDB até a
virada para o Stratos (§681) e é desligada depois dela. Os scripts de carga e de
conferência rodam no DevShell da máquina do JPM, como o `envia_dados.py`.

**O que não muda:** o que não é dado continua em disco ou no share — anexos,
imagens de ticket, `translations/`, os documentos do Electronic Inventory, os
insumos das recons, o Batch Conecta. A ponte do share do Stratos (§683)
continua existindo para esses arquivos.

**O custo novo:** cada consulta ao Snowflake leva de dezenas a centenas de
milissegundos e precisa de um *warehouse* ligado, que custa créditos enquanto
está acordado e leva segundos para acordar. O app faz MUITAS leituras pequenas
por request; o desenho abaixo existe para que nenhuma tela pague uma ida ao
Snowflake por linha.

---

## 2. O que o código tem hoje

### 2.1 As duas camadas por onde passa todo acesso

| Arquivo | Linhas | Papel |
|---|---|---|
| `apps/pages/database_access.py` | 1.154 | `duckdb_read`/`duckdb_write`/`duckdb_read_unlocked` (e os `sqlite_*` de leitura da migração antiga): semáforo por banco, trava de arquivo, portão, retentativa, o rastro `DbTrace` |
| `apps/pages/data_store.py` | 1.252 | o ARMAZÉM: o `DATA_DIR` como sistema de arquivos virtual — `read`, `write`, `remove`, `stat`, `isfile`, `exists`, `listdir`, `walk`, `day_files`, `prefetch`; os memos por carimbo; `BancoOcupado`/`BancoIlegivel`/`SemCanal` |
| `apps/pages/json_to_duckdb.py` | 1.999 | o motor: `target_of(rel)` diz banco, tabela e tipo de cada caminho; grava as formas (lista → `_seq`/`_raw`; objeto → `<tabela>__raw`; dataset tipado + `_raw`; Reference Data; calendários) e o `_manifest` |
| `apps/pages/duck_read.py` | 143 | fachada com os nomes antigos (`day_records`, `dataset_rows`…) |

O app inteiro fala em CAMINHOS de `.json`, e só o armazém sabe que existe
banco. **É essa a costura que torna a migração possível sem mexer em tela.**

### 2.2 Os bancos com SQL próprio (fora do armazém)

| Banco | Tabelas | Quem usa |
|---|---|---|
| `Users_OTCTracker.db` | `users`, `verification_codes` | `routes.py` (`get_db_connection`, singleton com trava até o `close()`) |
| `Notifications_OTCTracker.db` | `notifications`, `push_subscriptions`, sequência `seq_notif_id` | `platform/notifications.py` (inclusive a leitura sem trava do sino) |
| `pending-confirmation-{pending,ok,backlog}.db` | a fila do Pending Confirmation | `platform/pending_confirmation.py` |
| `manual_confirmations_{pending,ok}.db` | a esteira | `manual_conf.py` (`mutate_row`, `save_changes`) |
| `cgd_sharepoint.db` | o Onboarding (Tracking Docs) | `cgd_docs.py` |
| `Comitentes_OTCTracker.db` | a recon de comitentes | `recon_comitente.py` |
| todos | catálogo + `rowid` | `features/db_explorer` (Database Explorer, só do master) |

São 13 arquivos do app com chamada direta à camada de banco, 13 scripts e 38
testes.

### 2.3 O que é do dialeto do DuckDB e precisa de tradução

| No código hoje | Ocorrências | No Snowflake |
|---|---|---|
| `INSERT OR REPLACE` | 1 | `MERGE` |
| `CREATE SEQUENCE` / `nextval('x')` | 5 / 7 | `CREATE SEQUENCE` / `x.NEXTVAL` |
| `ALTER TABLE … ADD COLUMN IF NOT EXISTS` | 3 | existe igual |
| `PRAGMA`, `CHECKPOINT`, `ATTACH` | 5, 1, 3 | não existem: são manutenção de arquivo e somem |
| `read_json` | 2 | carga por stage (`COPY INTO`) |
| `rowid` (Database Explorer) | 12 | não existe: chave primária explícita |
| `read_only=True`, `unlocked=True` | 20, 3 | não se aplicam: o isolamento é da transação |
| parâmetros `?` | todo o app | `paramstyle='qmark'` no conector mantém o `?` (a regra de SQL injection do §2 do CLAUDE.md continua valendo sem reescrever consulta) |

### 2.4 Coordenação em disco que não é banco

Os *claims* diários dos schedulers (`platform/json_cache._claim_daily_slot`,
`features/user_home/commands._claim`) usam trava de arquivo para garantir que
UMA instância envia o e-mail do dia. Com várias instâncias e o Stratos sobre a
mesma base, eles passam a ser uma linha numa tabela (`INSERT` que só uma
instância consegue fazer).

---

## 3. Decisões de desenho

**D1. Duas costuras, nenhuma tela muda.** O motor passa a ser escolhido por
configuração, `OTC_DB_BACKEND = duckdb | snowflake`, no bloco de ambiente do
`config.py`. A dev continua em DuckDB: não tem acesso ao Snowflake, e a suíte
de testes roda sem rede. A instância Windows (bloco ENV:PROD) também fica em
DuckDB — ela não alcança o Snowflake (§1, "Onde ele roda"). Só o bloco
ENV:STRATOS liga o Snowflake, por domínio, na Fase 6.

**D2. O armazém no Snowflake é CHAVE → DOCUMENTO, não 188 bancos.** Não se
replica a quebra por produto nem uma tabela por dia: essa forma existe por
causa do catálogo do DuckDB (§437). O armazém já reconstrói tudo pelo texto
cru (`_raw`/`__raw`), então três tabelas bastam:

```
STORE_MANIFEST (path PK, kind, version, mtime, fsize, updated_at, updated_by)
STORE_DOC      (path PK, raw)            -- objeto e dataset inteiro
STORE_ROWS     (path, seq, raw)          -- lista de registros (arquivo-dia)
```

`path` é o caminho relativo ao `DATA_DIR` que o app já usa (`rel_of`). O que
hoje é tabela tipada para consulta vira VIEW sobre o `raw` (`raw:"Deal"`,
`LATERAL FLATTEN`), criada só onde alguém consulta fora do app.
**[A CONFIRMAR]** o teto de tamanho de um valor `VARIANT` na conta do JPM; a
Fase 1 mede o maior documento que existe.

**D3. "Mudou?" sem `stat`.** Toda gravação incrementa `version` no
`STORE_MANIFEST`. Um laço de fundo por processo lê, a cada N segundos, só o
que mudou desde a última volta (`WHERE updated_at > ?`) e invalida o memo.
O request nunca vai ao Snowflake perguntar se algo mudou: lê do memo do
processo, chaveado por `(path, version)`. A gravação do próprio processo
atualiza o memo na hora. O preço: a edição feita por OUTRA instância aparece
em até N segundos (hoje é imediata, pelo `stat`). O N sai da Fase 0, pesando
o custo do warehouse acordado (§5).

**D4. Concorrência por transação e versão otimista.** No backend Snowflake
deixam de existir a trava de arquivo, o `.lock.w`, o permit por banco, o
`db_gate` e a leitura sem trava do sino. O que precisa de
ler-alterar-gravar (o `_cache_lock` dos caches, o `mutate_row` da esteira, o
upsert do Pending) grava com `UPDATE … WHERE path = ? AND version = ?`: zero
linhas afetadas quer dizer que outra instância gravou antes, e o código relê e
refaz, ou responde 409 — a mesma ideia da impressão digital que o Database
Explorer já confere. O `_cache_lock` em memória continua, porque protege o
processo.
**[A CONFIRMAR]** se a conta tem *hybrid tables* (Unistore). Elas impõem a
chave primária e travam por LINHA, o que serve ao `STORE_MANIFEST`, aos
usuários, ao sino, à esteira e ao Pending. Numa tabela padrão a chave primária
NÃO é imposta (duplicata entra calada; todo upsert tem de ser `MERGE`) e DML
concorrente na mesma tabela entra em fila.

**D5. Token OAuth do FID da SOLUÇÃO, nunca credencial guardada.** O Snowflake
aceita um *bearer token* OAuth (`authenticator="oauth"`, `token=…`), e o Stratos
o emite de duas formas: com a identidade de quem está logado
(`UserAuthentication().get_resource_token(resource)`) ou com a da própria
aplicação, o **FID da solução**
(`stratosblocks.authentication.solution_fid.token_retrieval(app_id,
resource_id, environment)`). O app usa o **FID**:

- os schedulers (sino, e-mails das 08:00 e das 19h, laços de importação,
  aquecimento dos Summaries) rodam sem ninguém logado, e a página diz que job
  sem usuário é do FID;
- quem decide o que cada pessoa vê é o próprio app (`Page_Access`, papéis,
  §5); a credencial do usuário exigiria provisionar cada pessoa da equipe no
  Snowflake, para o banco responder a mesma coisa.

Não há segredo para guardar: o token é pedido em tempo de execução. O
`app_id`, o `resource_id` (`JPMC:URI:RS-…-SnowflakeOIDC-PROD`, e a variante
`-UAT` com `environment="uat"`) e o FID vão em variáveis de ambiente da solução
(`OTC_SNOWFLAKE_*`), nunca no código. O `user=` é o FID **sem** o prefixo
`DOMAIN\` (o Snowflake compara com o `sub` do token), e o FID precisa de um
USER e de um papel provisionados no Snowflake — sem isso o token é emitido e a
conexão responde `390100: Incorrect username or password`. **[A CONFIRMAR]** a
validade do token: a conexão tem de pedir outro antes de ele vencer (o laço de
versão do D3 fica de pé o dia inteiro).

**D6. Ambientes e papéis.** Um database (ou schema) por ambiente —
`OTC_TRACKER_DEV`, `OTC_TRACKER_PROD` —, um papel de leitura e escrita para o
app, um só de leitura para análise e um de DDL para os scripts de schema;
warehouse pequeno com *auto-suspend* curto. **[A CONFIRMAR]** a convenção de
nomes do JPM.

**D7. Fuso horário fixo na sessão.** A consulta do sino filtra
`created_at >= CURRENT_DATE`; o `CURRENT_DATE` do Snowflake é o do fuso da
sessão. A conexão fixa `TIMEZONE = 'America/Sao_Paulo'`, que é o relógio dos
schedulers (`_br_now`).

**D8. A conexão mora no overlay do Stratos, e o app recebe uma fábrica.** O
`stratosblocks` só existe no Stratos e no DevShell, e a dev nunca o importa
(§678). Então a receita da página fica em `stratos/src/snowflake_stratos.py`
(só na branch do Stratos), e a ponte (`otc_stratos.py`) injeta no app a função
que abre a conexão — o mesmo desenho do `proxy_interno` (§709), que embrulha o
`athena_api.build_session`, e do `email_stratos` (§691), que troca o
`smtplib.SMTP`. A receita:

```python
import snowflake.connector
snowflake.connector.paramstyle = 'qmark'          # o `?` de sempre (§2.3)
from stratosblocks.authentication.solution_fid import token_retrieval
from stratosblocks.connectivity import get_proxies

token = token_retrieval(app_id=…, resource_id=…, environment=…).access_token
kwargs = dict(account=…, user=<FID sem DOMAIN\>, role=…, warehouse=…,
              database=…, schema=…,                # sem eles: 090105 (sem database)
              authenticator='oauth', token=token, login_timeout=30,
              session_parameters={'TIMEZONE': 'America/Sao_Paulo'})   # D7
host, porta = <proxy de get_proxies()['https'] ou ['http']>   # (None, None) no DevShell
if host and porta:
    kwargs.update(proxy_host=host, proxy_port=porta)
snowflake.connector.connect(**kwargs)
```

O `warehouse=` não aparece no exemplo da página: sem ele vale o padrão do USER
do FID, se houver. **[A CONFIRMAR]** qual. O conector NÃO é um cliente HTTP do
`stratosblocks`: sem o `proxy_host`/`proxy_port` explícitos ele tenta sair
direto, e o sintoma é intermitente (`250001: Could not connect to Snowflake
backend` / `ConnectTimeoutError`). O erro do driver vai CRU para o log —
`errno`, `SQLSTATE` e o id da consulta (`sfqid`) —, que é o que o time de
dados pede para rastrear, e é a regra do §476 da casa. A dev e os testes
injetam um conector falso.

---

## 4. Passo a passo

Cada fase termina num critério verificável. Até a Fase 7, voltar atrás é
trocar a flag.

### Fase 0 — Acesso e ambiente **[depende do acesso]**
Os pedidos (o que a equipe precisa conseguir):

1. **Do time do Snowflake / plataforma de dados:** a conta (`<account>` de
   `<account>.snowflakecomputing.com`), os databases e schemas de UAT e PROD, o
   papel do app e o warehouse (D6) — e o **USER do FID da solução**
   provisionado com esse papel (sem ele: `390100`).
2. **Do Stratos (página *Solution Specific FID*):** o `app_id` da solução, o
   `resource_id` do recurso Snowflake OIDC de UAT e de PROD e o nome do FID.
3. **Ticket em go/stratossupport, liberação de rede** (o processo de serviço
   externo), com TODOS os hosts que o driver usa, não só o da conta: o
   `<account>.snowflakecomputing.com`, o respondedor OCSP, o stage interno
   (`*.snowflakecomputing.com`) e o stage S3 da conta — o `PUT` da carga (Fase
   4) e os resultados grandes passam por ele. Liberação pela metade é o erro
   intermitente do D8.
4. `snowflake-connector-python` no `stratos/build_requirements.py` (o
   `requirements.txt` do Stratos é gerado; o da raiz não muda, a dev não o
   instala) e a versão homologada no Artifactory.

O que se constrói (na branch do Stratos):

5. `stratos/src/snowflake_stratos.py` com a receita do D8, e a rota
   `/stratos/snowflake` (só do master, como a `/stratos/pacotes`): conecta,
   mostra `CURRENT_USER()`, `CURRENT_ROLE()`, `CURRENT_DATABASE()`,
   `CURRENT_WAREHOUSE()` e, na falha, o erro CRU do driver.
6. `stratos/snowflake_ping.py` para o DevShell da máquina do JPM (a mesma
   receita; ali o `get_proxies` devolve nada e a saída é direta, pelo Alpaca).
7. Medir, do contêiner e do DevShell: `SELECT 1`, leitura por chave primária,
   200 chaves num `IN`, `MERGE` de uma linha, o warehouse acordando e quanto
   dura o token.

Se o deploy der `SSLError`/falha de certificado, é o proxy do Stratos
interceptando o TLS: `stratos upgrade` e novo deploy.

**Saída:** os números medidos. São eles que fixam o N do D3 e decidem entre
tabela padrão e *hybrid table* no D4.

### Fase 1 — Medir o que vai migrar
1. Script a criar, `scripts/inventario_dados.py`, sobre o pacote do
   `exporta_dados.py` (a cópia consistente que já existe): por banco, os
   caminhos, o tipo, as linhas, o MAIOR documento em bytes e a maior lista.
2. Pelo `DbTrace`, contar as leituras por request das telas mais pesadas (os
   Summaries, o Intraday Monitor, o New Deals) — é o número que o memo do D3
   tem de absorver.

**Saída:** o maior documento cabe no `VARIANT`, ou a lista de quem precisa ser
quebrado; e o número de leituras por request das telas críticas.

### Fase 2 — A costura, ainda tudo em DuckDB
1. Extrair do `data_store` a interface do backend do armazém (ler texto cru,
   gravar, remover, manifest, listar por prefixo, ler em lote, versão). A
   implementação DuckDB é o código de hoje, movido sem mudar comportamento.
2. Para os bancos do §2.2: um módulo `platform/sql.py` com
   `conectar(banco, modo)` e o dialeto em funções (`upsert`, `proximo_id`,
   `garante_coluna`). Os sete módulos passam a usar só ele.
3. Guarda por AST, no estilo do `check_duck_writers.py`: nenhum
   `duckdb.connect`/`duckdb_read`/`duckdb_write` fora das duas costuras.
4. Teste de contrato novo, `check_store_backend_contract.py`, que roda o mesmo
   roteiro contra qualquer backend (DuckDB sempre; Snowflake quando houver
   credencial).

**Saída:** a suíte inteira passa sem mudança de comportamento, e o guarda
prova que não sobrou acesso fora das costuras.

### Fase 3 — Backend Snowflake
1. `scripts/snowflake_schema.py` (a criar): DDL idempotente das tabelas do D2
   e das tabelas de plataforma do §2.2, com as chaves primárias explícitas.
2. A implementação Snowflake das duas costuras; o laço de versão do D3; a
   gravação com versão otimista do D4; os *claims* do §2.4 numa tabela.
3. O contrato da Fase 2 passa contra o Snowflake de dev.

**Saída:** o contrato verde nos dois backends.

### Fase 4 — Carga
1. `stratos/carga_snowflake.py` (a criar, roda no DevShell da máquina do JPM
   como o `envia_dados.py`): lê o pacote do `exporta_dados.py`, escreve arquivos
   Parquet por banco, sobe para o stage interno (`PUT`) e carrega
   (`COPY INTO`). Incremental pelo `_manifest`: rodar de novo só leva o que
   mudou. O pacote também já está no Shared Drive do Stratos (§708), então a
   mesma carga pode rodar de dentro do contêiner, se o DevShell não alcançar o
   stage.
2. Conferência por caminho: contagem de linhas e hash do texto cru dos dois
   lados.

**Saída:** relatório com 100% dos caminhos batidos.

### Fase 5 — Sombra
A sombra precisa das gravações de VERDADE, e enquanto a produção é a
instância Windows elas não alcançam o Snowflake (§1). Por isso a ordem
recomendada é: primeiro a virada para o Stratos com o DuckDB no EFS (§681 —
uma mudança por vez), depois a sombra DENTRO do Stratos. Se a prova das travas
no EFS (§689) reprovar, a alternativa é virar o Stratos direto para o
Snowflake, com a carga da Fase 4 feita com as instâncias paradas.

1. O Stratos segue com o DuckDB como fonte. Toda gravação vai também para o
   Snowflake, por uma fila em segundo plano com retentativa — a gravação na
   sombra NUNCA derruba nem atrasa o request.
2. Uma amostra das leituras compara os dois lados e loga a divergência
   (`[sf-shadow] diverge`, com o caminho).
3. Duração: pelo menos duas semanas, cobrindo um fechamento de mês (o Swap
   Accrual e o Swap MtM são mensais).

**Saída:** dias seguidos sem divergência.

### Fase 6 — Virada por domínio
Flag por domínio, na ordem do menor risco para o maior:

1. cadastros (`/mapping`), Reference Data, calendários — quase só leitura;
2. arquivos-dia do `cache/`;
3. Pending Confirmation, esteira, notificações e usuários — escrita
   concorrente entre instâncias.

Cada domínio: a carga incremental final (Fase 4), a flag ligada no Stratos
(leitura e escrita no Snowflake) e o restart da solução.

**Saída:** os três domínios no Snowflake, com a sombra invertida (DuckDB como
cópia) por mais uma semana.

### Fase 7 — Desligar o que só existia por causa do arquivo
Depois de um mês estável: a trava de arquivo e o permit no backend Snowflake,
o `recover_duckdb_wal.py`, o `slim_duckdb.py`, o pacote do Stratos
(`exporta_dados.py`, `envia_dados.py`, `/stratos/pacotes`), a regra da mesma
versão do DuckDB em todas as máquinas. Os testes que provam essas peças seguem
rodando no backend DuckDB, que continua sendo o da dev.

### Volta atrás
Até a Fase 7, trocar a flag. Da Fase 6 em diante, `scripts/snowflake_to_duckdb.py`
(a criar) reconstrói os bancos a partir do que o Snowflake tem — o mesmo papel
do `export_duckdb_to_json.py` no cutover do §434.

---

## 5. Riscos

| Risco | Como se trata |
|---|---|
| Latência × leituras por request | memo por `(path, version)` + laço de versão (D3); leitura em lote vira um `WHERE path IN (…)` (o `prefetch` já agrupa) |
| O laço de versão mantém o warehouse acordado o dia inteiro (custo) | o N do D3 sai da Fase 0 com o custo na conta; consulta numa *hybrid table* ou no cache de resultados, se a conta permitir |
| Chave primária não imposta em tabela padrão | todo upsert é `MERGE`; *hybrid table* onde houver escrita concorrente (D4) |
| Escrita concorrente na mesma tabela em fila | *hybrid table*, ou lote (o import já grava em lote, §622) |
| Fuso do `CURRENT_DATE` | fuso fixo na sessão (D7) |
| A dev não alcança o Snowflake | a dev segue em DuckDB; o backend Snowflake se prova pelo contrato onde há credencial |
| Documento maior que o teto do `VARIANT` | medido na Fase 1; quebrado em linhas antes da carga |
| Liberação de rede incompleta (erro intermitente `250001`) | o ticket da Fase 0 com TODOS os hosts, e o conector sempre pelo proxy (D8) |
| Token do FID vencendo com o app de pé | validade medida na Fase 0; a fábrica pede token novo antes do vencimento |
| Certificado do proxy do Stratos depois de um deploy (`SSLError`) | `stratos upgrade` e novo deploy |
| A instância Windows não alcança o Snowflake | o Snowflake entra com a virada para o Stratos (§1); a instância fica em DuckDB até ser desligada |

---

## 6. O que a página do Stratos respondeu, e o que falta

| Pergunta | Resposta |
|---|---|
| Como se pede o acesso | Rede: ticket em go/stratossupport, com todos os hosts (Fase 0, item 3). Banco: USER e papel do FID provisionados pelo time do Snowflake. **[A CONFIRMAR]** quem aprova |
| Conta e endereço | `<account>.snowflakecomputing.com`. **[A CONFIRMAR]** o valor da conta |
| Autenticação de uma aplicação | OAuth com o token do FID da solução (D5) ✔ |
| Nomes de database, schema, papel, warehouse | **[A CONFIRMAR]** |
| Warehouse e custo | **[A CONFIRMAR]** tamanho, auto-suspend, quem paga o crédito |
| *Hybrid tables* | **[A CONFIRMAR]** |
| Rede | Stratos: pelo proxy do `get_proxies` (D8) ✔. DevShell: direto, pelo Alpaca ✔. Instância Windows fora do DevShell: não coberta, fica em DuckDB (§1) |
| Classificação de dados (CNPJ, contas, e-mails de cliente) | **[A CONFIRMAR]** |
| Backup, Time Travel, retenção | **[A CONFIRMAR]** |
| Pacote Python | `snowflake.connector` ✔. **[A CONFIRMAR]** a versão homologada |

**Valores a juntar para a Fase 0** (nada disso é segredo; vai nas variáveis
de ambiente da solução):

```
OTC_SNOWFLAKE_ACCOUNT       a conta (sem .snowflakecomputing.com)
OTC_SNOWFLAKE_USER          o FID, sem DOMAIN\
OTC_SNOWFLAKE_ROLE          o papel do app
OTC_SNOWFLAKE_WAREHOUSE     o warehouse
OTC_SNOWFLAKE_DATABASE      o database (UAT e PROD)
OTC_SNOWFLAKE_SCHEMA        o schema
OTC_SNOWFLAKE_APP_ID        o app_id da solução
OTC_SNOWFLAKE_RESOURCE_ID   JPMC:URI:RS-…-SnowflakeOIDC-PROD (e o de UAT)
OTC_SNOWFLAKE_ENVIRONMENT   prod | uat
```
