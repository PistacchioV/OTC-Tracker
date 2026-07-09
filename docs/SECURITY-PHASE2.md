# Segurança — Fase 2 (passo a passo)

> Contexto: os achados **críticos** e **altos** do scan de vulnerabilidade já
> foram corrigidos, verificados e commitados (`e3526bc`), assim como o
> **hardening da Fase 1** — headers, admin gates, path traversal, SECRET_KEY
> (`ead2a35`). Este documento registra o que falta, em ordem de execução.
>
> Nenhum item aqui é urgente. É a camada "cinto **e** suspensório".

---

## Fase 2A — Content-Security-Policy (CSP)

**Objetivo:** dizer ao navegador quais scripts ele pode rodar, para que um
código malicioso injetado na página seja **ignorado** (segunda trava por cima
da correção de XSS já feita).

**Risco:** a app usa muito script inline dentro do HTML. Uma CSP rígida
barraria também os scripts legítimos e quebraria telas. Por isso ligamos
primeiro em **modo observação** (só relata, não bloqueia).

### Passos
- [ ] **2A.1 — Ligar CSP em modo report-only.** Em `apps/pages/routes.py`, no
      `@blueprint.after_request` `add_security_headers`, adicionar o header
      `Content-Security-Policy-Report-Only` com uma política inicial permissiva
      (`default-src 'self'`, permitindo por ora `'unsafe-inline'` em scripts/estilos
      e as origens de fontes/CDN realmente usadas). **Não bloqueia nada** ainda.
- [ ] **2A.2 — Criar endpoint de coleta de violações.** Uma rota `POST` (ex.:
      `/api/csp-report`) que recebe os relatórios do navegador e os grava em log.
      Apontar a diretiva `report-uri`/`report-to` para ela.
- [ ] **2A.3 — Navegar por todas as telas** (login, dashboards, New Deals,
      control-panel, reconciliação, e-mails, users/page-access) e **coletar** o
      que a CSP *teria* bloqueado.
- [ ] **2A.4 — Ajustar a política** com base no relatório: mapear as origens
      legítimas (fontes, imagens data:, CDNs) e, idealmente, mover os scripts
      inline críticos para arquivos `.js` ou adicionar `nonce`/hash — para poder
      **remover o `'unsafe-inline'`** (é ele que enfraquece a CSP).
- [ ] **2A.5 — Repetir 2A.3/2A.4** até o relatório ficar limpo (zero violações
      em uso normal).
- [ ] **2A.6 — Virar a chave:** trocar `Content-Security-Policy-Report-Only`
      por `Content-Security-Policy` (agora **bloqueia** de verdade).

**Verificação:** com a CSP ativa, injetar um `<img onerror=…>` de teste numa
célula e confirmar no console do navegador que o navegador **recusou** executá-lo.

**Reversão:** remover/retornar o header a report-only — mudança de uma linha,
sem tocar em dados.

---

## Fase 2B — Proteção CSRF por token

**Objetivo:** exigir, além do cookie de sessão, um **token secreto que muda a
cada sessão** em toda ação que altera dados, para que um site malicioso não
consiga disparar ações em nome do usuário logado.

**Estado atual:** o `SameSite=Lax` (Fase 1) já **bloqueia a maior parte** dos
ataques CSRF. O token é a camada que fecha o restante.

**Risco:** o token precisa acompanhar **todos** os ~120 endpoints POST/PATCH/DELETE
e todas as chamadas `fetch` do frontend. Esquecer um quebra aquele botão — por
isso o rollout é gradual e testado tela por tela.

### Passos
- [ ] **2B.1 — Inventário.** Listar todos os endpoints que alteram estado
      (`grep` por `methods=['POST'|'PATCH'|'DELETE']` em `routes.py`) e todos os
      `fetch(...)` correspondentes no frontend (`apps/static/js`, templates).
- [ ] **2B.2 — Ativar o CSRFProtect.** Inicializar o `flask_wtf` `CSRFProtect(app)`
      em `apps/__init__.py` (`create_app`). A partir daqui, **todos** os POST
      passam a exigir token — por isso os próximos passos são obrigatórios.
- [ ] **2B.3 — Expor o token ao frontend.** Publicar o token num `<meta>` no
      layout base (`apps/templates/layouts/…`) para o JS conseguir lê-lo.
- [ ] **2B.4 — Anexar o token nas chamadas.** Ajustar as chamadas `fetch` para
      enviar o header `X-CSRFToken` (idealmente num wrapper central, para não ter
      que editar 120 chamadas uma a uma), e adicionar o campo oculto nos formulários
      HTML tradicionais.
- [ ] **2B.5 — Tratar exceções conscientes.** Endpoints que legitimamente recebem
      chamadas externas (se houver algum webhook/integração) devem ser isentados
      explicitamente com justificativa.
- [ ] **2B.6 — Testar tela por tela.** Percorrer cada fluxo que salva/edita/apaga
      e confirmar que continua funcionando (agora com token) e que uma chamada
      **sem** token é recusada (403).

**Verificação:** um `POST` sem o header `X-CSRFToken` deve retornar **403**;
o mesmo `POST` pela UI real deve funcionar normalmente.

**Reversão:** desligar `CSRFProtect` em `create_app` — volta ao estado atual
(protegido só por `SameSite`).

---

## Itens adiados (menor prioridade — tratar quando conveniente)

- [ ] **Mensagens de erro genéricas** — trocar os `str(e)` devolvidos ao cliente
      (~9 pontos em `routes.py`) por mensagem genérica + log no servidor. Requer
      análise caso a caso para não remover feedback de validação útil. *(Baixo; só
      exposto a usuário autenticado.)*
- [ ] **`DEBUG` default `False`** — inverter o padrão em `run.py` para *opt-in* de
      debug. Muda o comportamento do ambiente de dev; alinhar antes.
- [ ] **Infra hardcoded** — mover host SMTP (`mailhost…:25`) e SID master para
      config/env.
- [ ] **Dependências JS** (`pdfjs-dist` HIGH e libs moderate/low) — exige rebuild
      dos assets (gulp/bun); tratar na toolchain de frontend, separada do backend.

---

## Já concluído (para referência)

| Commit | Conteúdo |
|--------|----------|
| `e3526bc` | Críticos/Altos: bypass de 2FA (X-Forwarded-For), escalonamento de privilégio, XSS armazenado, endpoints sem auth, MAX_CONTENT_LENGTH, SameSite, bump de 6 deps Python |
| `ead2a35` | Fase 1: headers de segurança, /users-roles admin-only, catch-all com auth, 2 path traversals, SECRET_KEY (secrets + exigência em prod) |
