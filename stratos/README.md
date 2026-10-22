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
  sozinho, porque num servidor novo a tabela nasce vazia. O IP deixa de ser
  critério e a trava de tela não existe aqui. `OTC_STRATOS_SSO=0` volta ao login
  próprio (SID + código por e-mail).
- **Prefixo.** O app foi escrito para morar em `/` e aqui mora em
  `/76521/otc-tracker-ops-ai-citizen`. O HTML que sai é reescrito
  (`href`/`src`/`action`, Speculation Rules, `Location`), o `ASSETS_ROOT` leva a
  base, e um shim no `<head>` corrige o que o JavaScript monta depois (fetch, XHR,
  setters de `href`/`src`, `innerHTML`, `location.href` pela Navigation API).
- **Cookie** próprio (`otc_tracker_session`) no caminho da solução: o domínio do
  Stratos é compartilhado com outras soluções.

## Variáveis de ambiente (task definition)

| Variável | Para quê |
|---|---|
| `OTC_STRATOS_ROOT` | raiz de dados e bancos. **Aponte para um volume persistente** — sem ela vai para o `/tmp`, que some a cada deploy |
| `SECRET_KEY` | chave de sessão estável entre tasks e deploys |
| `OTC_TRACKER_URL` | endereço completo da solução, para os botões de e-mail |
| `OTC_FOUR_EYES=0` | desliga o maker/checker (padrão: ligado, como na prod) |

## Verificar

```
OTC_SHARED_DRIVE_ROOT=/tmp/otc-share python stratos/tests/check_stratos.py
python stratos/build_requirements.py --check
```

O `check_stratos.py` monta o layout do destino e sobe o `solution.py` com um
Stratos de mentira (o `stratos-blocks` é interno do JPM).

## O que não funciona fora da rede do desktop

O contêiner não enxerga o share (`\\Nawest...`): confirmações, Batch Conecta,
CETIP e Electronic Inventory ficam sem destino. Também não há Outlook (box scan,
leitura de e-mail) e a Athena pede Kerberos, que no Linux não está configurado.
