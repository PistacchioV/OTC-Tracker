# OTC Tracker no Stratos

Esta branch (`OTC-Tracker-Stratos`) é a **dev (`StreamFlow`) mais o que o Stratos
precisa**. O código do app continua nascendo na dev e chega aqui por merge; só o
que está listado abaixo existe apenas nesta branch.

| Aqui | Vai para o `singing-moose-flask` | O que é |
|---|---|---|
| `apps/` | `src/apps/` | o OTC Tracker, igual à dev |
| `stratos/src/solution.py` | `src/solution.py` | o template do Stratos, com os blocos `DO NOT DELETE` intactos e o OTC montado na área liberada |
| `stratos/src/run.py` | `src/run.py` | o do template, sem mudança |
| `stratos/src/otc_stratos.py` | `src/otc_stratos.py` | a ponte: monta o OTC no `app` do template, SSO, prefixo de URL |
| `stratos/requirements.txt` | `requirements.txt` | o bloco do template + o que o OTC precisa (gerado) |
| `apps/config.py` (bloco `ENV:STRATOS`) | — | caminhos de dados no contêiner |
| `stratos-sync.bat` | — | copia o que mudou para o repositório do Stratos |
| `stratos/exporta_dados.py` | — | tira do share a cópia dos bancos que vai para o Stratos |
| `stratos/sonda_codex.py` | — | confere, na máquina do JPM, se o Codex responde pelos ativos da seed do `quotes-equity`, para saber se ele pode tomar o lugar do Yahoo na Quotes do Stratos (§679) |
| `stratos/build_requirements.py`, `stratos/tests/` | — | gerador e verificação |

Dockerfile, terraform, Jenkinsfile, jules, `tests/` e o `favicon.ico` são do
template e ninguém aqui os toca.

## Levar para o Stratos (máquina do JPM)

Uma vez, de dentro do clone do OTC Tracker:

```
git worktree add ..\OTC-Tracker-Stratos OTC-Tracker-Stratos
```

Depois, a cada entrega, da pasta `..\OTC-Tracker-Stratos`:

```
stratos-sync           (lista o que vai mudar)
stratos-sync apply     (copia; em src\apps também remove o que saiu da branch)
```

e, no `singing-moose-flask`, `stratos status` e `stratos push "mensagem"`. O
destino padrão é `%USERPROFILE%\ds\python-solutions\stratos\76521\singing-moose-flask`
na ramificação `feature/stratos`, a do Stratos CLI — fora dela o CLI não
reconhece o projeto (`OTC_STRATOS_DEST` / `OTC_STRATOS_BRANCH` mudam).

## Como o OTC roda dentro do template

- **Um app só.** `otc_stratos.mount` pendura o OTC no `app` que o template cria,
  instrumenta e autentica — a autenticação e o rastreamento do Stratos valem para
  toda rota do OTC.
- **Subida em segundo plano.** O `app.run` do template só abre a porta quando o
  módulo termina, e semear os bancos num contêiner com fração de CPU passava da
  janela do health check (os três primeiros deploys foram derrubados a ~2 min 20 s).
  O `mount` põe um portão na frente do app e sobe o OTC numa thread: o health
  check responde na hora, as páginas dizem "starting" e se recarregam, e uma
  subida que quebra mostra o erro na tela (o health check segue 200 de propósito,
  senão o contêiner morreria levando o erro junto). O log diz quanto a subida
  levou: `[stratos] OTC Tracker pronto em ..., em Ns`.
- **SSO.** Quem autentica é o Stratos. A identidade dele (o SID) abre a sessão do
  OTC; papel, páginas e status continuam saindo da tabela de usuários. SID sem
  cadastro vira pedido de acesso (aviso ao ADMIN); o master (`E930179`) é ativado
  sozinho, porque num servidor novo a tabela nasce vazia. Nome, e-mail e cargo do
  pedido de acesso saem do phonebook do Stratos
  (`stratosblocks.utilities.get_phonebook_data`, as mesmas chaves do `awmpy`, que
  não existe no contêiner e vira uma casca dele). O IP deixa de ser critério. `OTC_STRATOS_SSO=0` volta ao login
  próprio (SID + código por e-mail).
  A ponte só age nas rotas do OTC: as do Stratos — o `/login/callback`, onde a
  identidade nasce — passam intactas, e ela limpa só as chaves do OTC, nunca a
  sessão inteira (o StratosAuth guarda o login dele na mesma sessão).
- **O menu da foto.** O **Lock Screen** trava de verdade, e o Unlock é digitar o
  SID que o SSO identificou. O do OTC conferia o IP do cadastro e, sem ele,
  mandava código por e-mail, o que atrás do proxy do Stratos travaria a tela para
  sempre. O **Log Out** encerra só a sessão do OTC e para numa tela "You have
  signed out", que segura a sessão fechada até o "Sign in again". O do OTC
  (`session.clear()`) levava junto o login do Stratos, o SSO entrava sozinho no
  request seguinte e o clique devolvia o dashboard. Uma aba que ficou aberta
  recebe 401 na API e o `session-guard.js` a leva à mesma tela.
- **Prefixo.** O app foi escrito para morar em `/` e aqui mora em
  `/76521/otc-tracker-ops-ai-citizen`. O HTML que sai é reescrito
  (`href`/`src`/`action`, Speculation Rules, `Location`), o `ASSETS_ROOT` leva a
  base, e um shim no `<head>` corrige o que o JavaScript monta depois (fetch, XHR,
  setters de `href`/`src`, `innerHTML`, `location.href` pela Navigation API).
- **Cookie** próprio (`otc_tracker_session`) no caminho da solução: o domínio do
  Stratos é compartilhado com outras soluções.
- **Rede.** A saída para a internet (BCB, Yahoo, IBGE, NY Fed) é pelo proxy do
  Stratos: o `configure_proxy_env_vars` do `stratosblocks.connectivity` roda na
  subida, e o `QUOTES_PROXY` vazio tira da fila o proxy corporativo do desktop.
  O pre-push scan do `stratos push` recusa qualquer citação do proxy on-premise
  nas portas antigas (ou sem porta), **até em comentário** — a correção vai na
  dev, porque `apps/` é código da dev.

## Levar os dados (os bancos do share)

O contêiner não enxerga o share, então os dados chegam lá como ARQUIVO. Quem
monta o arquivo é o `exporta_dados.py`, na máquina do JPM, com o MESMO python
do `start-otc-tracker.bat`: é a versão de duckdb que escreveu os WALs.

```
python stratos\exporta_dados.py --medir        (quantos bancos, quantos MB)
python stratos\exporta_dados.py --zip          (monta o pacote)
```

Banco a banco, ele toma a trava de leitura da camada, copia o `.db` com os WALs
para o disco local, faz o `CHECKPOINT` lá (o limbo do §442 sai pela rotina do
`recover_duckdb_wal.py`) e confere que não sobrou WAL. O pacote não leva WAL:
WAL de uma versão de duckdb replayado por outra é o banco ILEGÍVEL do §442. O
pacote vai para `%LOCALAPPDATA%\OTC-Tracker\exporta-stratos`, fora do Desktop
porque o Desktop pode estar no OneDrive. A pasta `data/` dentro dele tem a forma
do `OTC_STRATOS_ROOT`, e o `manifest.json` lista bytes e sha256 de cada arquivo.

Rode com as instâncias do time FECHADAS (fim do dia). Um banco preso por uma
instância de pé fica de fora como EM USO e o pacote sai INCOMPLETO;
`--insistir 60` fica tentando. O share não é alterado.

Ficam de fora: sobras (`.lock`, `_recuperado/`, `.corrupt-*`), `translations/`,
que vem com o código, e o JSON legado em disco, isto é, o histórico de mais de 12
meses que só existe como arquivo (§434). `--com-json-legado` leva o legado junto.

**O lado do Stratos ainda não existe**, mas o destino está decidido (§678): os
dados vão morar no Stratos NoSQL (MongoDB, o `NoSqlDatabase` do
`stratosblocks`), por porte de verdade — a dev e a prod seguem no DuckDB, e o
mesmo código vai escolher o banco pelo config. O pacote vai entrar por um
dropzone da Database Explorer do Stratos (só do master), que confere o sha256 do
`manifest.json`, abre cada `.db` com o duckdb do contêiner, grava no NoSQL e
recusa pacote INCOMPLETO (passo 5). A rotina de exportação vai para um módulo do
app, com um botão na Database Explorer da instância da equipe, e o
`exporta_dados.py` vira casca dela (passo 1). Até lá, o que entrar no `/tmp`
some no próximo deploy.

## Variáveis de ambiente (task definition)

| Variável | Para quê |
|---|---|
| `OTC_STRATOS_ROOT` | raiz de dados e bancos; sem ela vai para o `/tmp`, que some a cada deploy. Quem vai guardar os bancos é o Stratos NoSQL (o porte do §678, ainda não feito), não esta pasta |
| `SECRET_KEY` | chave de sessão estável entre tasks e deploys |
| `OTC_TRACKER_URL` | endereço completo da solução, para os botões de e-mail |
| `OTC_FOUR_EYES=0` | desliga o maker/checker (padrão: ligado, como na prod) |

## Verificar

```
OTC_SHARED_DRIVE_ROOT=/tmp/otc-share python stratos/tests/check_stratos.py
python stratos/build_requirements.py --check
```

O `check_stratos.py` monta o layout do destino e sobe o `solution.py` com um
Stratos de mentira (o `stratos-blocks` é interno do JPM): os blocos DO NOT
DELETE, a subida em segundo plano e o portão, o login (inclusive o
`/login/callback`), o phonebook (com o do Stratos e sem nenhum), o menu da
foto (Lock Screen e Log Out), o prefixo, o shim no node e a regra do scan do
proxy. E roda o `check_exporta_dados.py`: o pacote dos bancos sem WAL, lido de
volta pelo armazém, o banco EM USO e o `--zip`. A história de cada decisão está
no HANDOFF, §677 a §679.

## O que não funciona fora da rede do desktop

O contêiner não enxerga o share (`\\Nawest...`): confirmações, Batch Conecta,
CETIP e Electronic Inventory ficam sem destino. Também não há Outlook (box scan,
leitura de e-mail) e a Athena pede Kerberos, que no Linux não está configurado.
E o SMTP da rede (`mailhost.jpmchase.net`) provavelmente não responde do
contêiner: sem ele não saem os e-mails do app nem o código do login próprio
(`OTC_STRATOS_SSO=0`). Cada uma dessas faltas pede uma solução própria antes de
a equipe passar para o Stratos (§678).
