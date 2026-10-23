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

**No Stratos, os bancos moram no Shared Drive** (§681, que revê o §678): o EFS
da solução, montado como diretório comum, que sobrevive ao deploy e é o mesmo
para todos os web workers. A ponte (`_raiz_no_shared_drive`) pede a pasta
`otc-tracker` ao `get_shared_drive` e a usa como `OTC_STRATOS_ROOT`; o app roda
com o mesmo DuckDB da prod, sem porte. A chave da sessão fica lá também
(`secret_key.txt`), e por isso a sessão sobrevive ao deploy. O Stratos NoSQL
(MongoDB) ficou para depois da virada.

O pacote chega ao drive pelo `stratos file --save` (ou pelo cliente
`SharedDrive`, por HTTP) e **nunca por cima dos bancos em uso**: ele vai para uma
pasta própria, é conferido pelo sha256 do `manifest.json` e só então passa a
valer como raiz (os passos do §681). Ainda não está pronto, e enquanto isso o
Stratos começa com os bancos vazios, só com o que a semeadura traz.

**Backup:** o drive tem uma foto por noite, guardada 35 dias, sem versão por
arquivo. Na pior hora se perde até um dia; uma cópia de hora em hora para o File
Library (o S3, que guarda todas as versões por 70 dias) é um dos passos do §681.

## A ponte do share

O contêiner não enxerga o share, e as pastas dele são usadas fora do app: o
Batch Conecta da B3 lê a `New` e devolve na `Return`, a equipe abre o
Electronic Inventory pelo Explorer, a equipe global lê a planilha do Pending
Confirmation. A ponte mantém essas pastas iguais no share e no
`<raiz>/share` do Shared Drive (§683). São 16 pastas, com a lista e a regra
em `src/ponte_comum.py`.

A ponte tem duas metades:
- **No contêiner**, uma thread (`otc_stratos._ponte_manifestos`) escreve por
  pasta o manifesto do lado do Stratos, em `<raiz>/ponte/manifesto/`.
- **Numa máquina da rede do JPM**, roda o `ponte_share.py`, com o Python do
  DevShell, porque é ele que tem o `stratosblocks`. Ele lê o share e o
  manifesto e copia pelo cliente `SharedDrive`.

A tarefa agendada do Stratos também roda na nuvem, então essa metade só pode
morar numa máquina da rede.

```
set PY=C:\Users\e930179\ds\tools\python3.13\latest\python.exe
%PY% stratos\ponte_share.py --medir                         (arquivos e MB por pasta)
%PY% stratos\ponte_share.py --solution-id <ID> --env dev --dry-run    (o que faria)
%PY% stratos\ponte_share.py --solution-id <ID> --env dev --loop 20    (espelho, em laço)
```

O `<ID>` é o solution id da solução no Stratos, o mesmo do `stratos file`.
Também pode vir da variável `OTC_PONTE_SOLUTION_ID`.

O `--env` é obrigatório e é o ambiente em que a solução está publicada, com os
mesmos nomes do `stratos file` (`dev`, e `prod` quando ela for para a
produção). Cada ambiente tem o seu Shared Drive: errado, a ponte grava num
drive que o app não lê.

Para conferir sem log que o contêiner escreve os manifestos:

```
stratos file --listfiles --local-path "" --server-path "otc-tracker/ponte/manifesto" --env dev
```

- **Espelho** (o padrão, enquanto a equipe segue na instância de hoje): só do
  share para o Stratos. **A ponte não escreve nada no share**: um arquivo do
  Stratos em validação na `Batch Conecta\New` seria registro de verdade na B3.
- **Virada**, quando o Stratos virar a produção, em duas etapas:
  1. Uma vez, `--modo virada --alinhar`: o Stratos fica igual ao share, e o que
     ele gerou na validação vai para a lixeira dele.
  2. Depois, `--modo virada --loop 20`: os dois sentidos, com as remoções. O
     app esvazia a `Return` depois de ler e o Conecta esvazia a `New` depois de
     enviar, e as duas remoções chegam ao outro lado. Num conflito vence o
     sentido da pasta: o Stratos nas de saída, o share nas outras.

**Nada é apagado de verdade.** O que sai do Stratos vai para
`<raiz>/ponte/lixeira/<dia>/`. O que sai do share vai para
`%LOCALAPPDATA%\OTC-Tracker\ponte\lixeira\<dia>\` na máquina da ponte.

Três travas param a passada da pasta:
- muitas remoções de uma vez, mais de 10 ou de 20% da pasta (`--permitir-apagar`
  insiste);
- o drive do Stratos trocado ou zerado (o id do manifesto muda);
- a virada sem o `--alinhar` antes.

Uma subpasta do share que não abre (sem permissão) é pulada, e nada se decide
dentro dela. Só roda uma ponte por vez: ela renova um aviso no drive, e uma
segunda máquina espera.

As pastas por dia (CETIP, MtM, Accrual, Intrag, Comitente) levam só os
últimos 31 dias: o histórico de anos não serve ao app e custaria horas de
cópia. O Electronic Inventory vai inteiro, e a primeira passada dele é a
longa. Antes, o `--medir` diz quanto é.

**Pendente:** o cadastro `cetip-files` (/mapping) guarda as cópias extras como
`I:\CETIP_OPTIONS` e `I:\CETIP_NDF`. No Linux do Stratos isso é um caminho
relativo, e a cópia não cai na pasta da ponte.

## Variáveis de ambiente (task definition)

| Variável | Para quê |
|---|---|
| `OTC_STRATOS_ROOT` | raiz de dados e bancos. Sem ela, a ponte usa a pasta `otc-tracker` do Shared Drive (`get_shared_drive`); sem nenhum dos dois, o `/tmp`, que some a cada deploy (o log diz qual valeu: `[stratos] dados em …`) |
| `OTC_SECRET_KEY_FILE` | onde fica a chave da sessão quando não há `SECRET_KEY`; padrão: `secret_key.txt` na raiz de dados |
| `SECRET_KEY` | chave de sessão; vence o arquivo do drive |
| `OTC_PONTE=0` | desliga a thread dos manifestos da ponte |
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
`/login/callback`), o phonebook (com o do Stratos e sem nenhum), a raiz dos
dados (Shared Drive, variável, ou `/tmp` avisando), a ponte do share
(`check_ponte.py`: espelho, travas, alinhar e virada), o menu da
foto (Lock Screen e Log Out), o prefixo, o shim no node e a regra do scan do
proxy. E roda o `check_exporta_dados.py`: o pacote dos bancos sem WAL, lido de
volta pelo armazém, o banco EM USO e o `--zip`. A história de cada decisão está
no HANDOFF, §677 a §683.

## O que não funciona fora da rede do desktop

O contêiner não enxerga o share (`\\Nawest...`): confirmações, Batch Conecta,
CETIP e Electronic Inventory chegam e saem pela ponte (acima). Não há Outlook (box scan,
leitura de e-mail) e a Athena pede Kerberos, que no Linux não está configurado.
E o SMTP da rede (`mailhost.jpmchase.net`) provavelmente não responde do
contêiner: sem ele não saem os e-mails do app nem o código do login próprio
(`OTC_STRATOS_SSO=0`). Cada uma dessas faltas pede uma solução própria antes de
a equipe passar para o Stratos (§678, §681).
