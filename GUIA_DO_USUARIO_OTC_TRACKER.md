# Guia do Usuário — OTC Tracker

**Brazil OTC Operations · JPMorgan Chase & Co.**

**Versão:** 1.0 · **Data:** 30/07/2026

---

> **Sobre as telas deste guia.** Todas as imagens foram capturadas do sistema real, porém com **dados fictícios**. Nenhum nome de cliente, CNPJ, conta ou valor real aparece nestas páginas.

---

## 1. Visão Geral

O **OTC Tracker** centraliza o ciclo de vida das operações de derivativos de balcão (OTC) da mesa Brasil — do momento em que o negócio é fechado até o arquivo de confirmação assinado e arquivado.

**Objetivo principal:** garantir que toda operação fechada no dia seja **registrada na B3**, **confirmada com a contraparte** e **instruída para liquidação**, sem que nenhuma se perca no caminho.

O sistema cobre quatro grandes blocos de trabalho:

| Bloco | O que faz |
|---|---|
| New Deals | Importa as operações do dia, valida os dados e registra na B3 |
| Confirmations | Gera os documentos de confirmação (Word, PDF e XML) e envia à contraparte |
| Daily Settlement | Calcula e instrui as liquidações do dia |
| Reconciliations | Concilia posição, comitente e pagamentos/recebimentos |

### 1.1. Como o sistema se organiza

Toda página segue o mesmo esqueleto: menu lateral à esquerda, barra superior com notificações e perfil, e a área de trabalho no centro.

![Painel inicial do OTC Tracker](docs/sop-screenshots/dashboard.png)

---

## 2. Primeiros Passos

### 2.1. Requisitos de acesso

Antes do primeiro login, confirme os três pontos abaixo:

1. Estar na **rede JPMorgan** (VPN ou escritório). Fora da rede o login não funciona, porque o sistema consulta o phonebook interno e envia e-mail pelo relay corporativo.
2. Ter um **SID** válido — uma letra seguida de seis dígitos, por exemplo `A123456`.
3. Ter as páginas liberadas no seu perfil. O acesso é concedido **por página**: se um administrador não liberou uma tela, ela não aparece no seu menu.

### 2.2. Entrar no sistema

1. Abra o endereço do OTC Tracker no navegador.
2. Digite o seu **SID** no campo **SID Number**.
3. Clique em **Sign In**.
4. Se este já for o seu computador de costume, você entra direto.
5. Se for uma máquina nova, o sistema envia um **código de 6 dígitos** para o seu e-mail corporativo.

### 2.3. Verificação em duas etapas

Quando o código for solicitado:

1. Abra o seu e-mail corporativo e copie o código de **6 dígitos**.
2. Digite o código na tela de verificação e confirme.

> **O código expira em 10 minutos.** Passado esse prazo, volte à tela de login e faça uma nova tentativa para receber outro código.

### 2.4. Ajustes da sua sessão

Na barra superior, à direita, você encontra:

- **Sol / Lua** — alterna entre tema claro e escuro.
- **Sino** — notificações do sistema (importações, mapeamentos, envios).
- **EN** — idioma da interface.
- **Seu nome** — perfil e sair.

---

## 3. Passo a Passo Principal

### 3.1. New Deals — a tela de trabalho do dia

Todas as páginas de **New Deals** funcionam da mesma forma. Muda o produto, não o fluxo.

![New Deals — NDF Vanilla](docs/sop-screenshots/new_deals-ndf-vanilla.png)

A tela tem quatro áreas, de cima para baixo:

| Área | Para que serve |
|---|---|
| Área de upload | Arrastar uma planilha de operações (quando o produto aceita importação por arquivo) |
| Barra de busca | Filtrar por qualquer coluna |
| Show entries | Quantas linhas por página e, em alguns produtos, os botões de documento e e-mail |
| Barra de ferramentas | Columns, Add Row, Export, Reference Date, Import, Mapping B3 e Clear Filters |

#### O que cada status significa

| Status | Significa |
|---|---|
| New | Acabou de chegar da API; ninguém revisou ainda |
| Amend | Já existia, mas a API alterou um dado econômico — precisa de revisão |
| Pending | Alguém editou e submeteu para aprovação |
| Approved | Aprovado, pronto para seguir |
| Sent | Arquivo gerado e enviado para registro |
| Success | Registrado na B3, com o número do B3 ID preenchido |
| Error | Voltou com erro da B3 |

---

### 3.2. Importar as operações do dia

1. Confira o campo **Reference Date**. Ele comanda tudo — é a data usada para puxar e para gravar. Por padrão vem a data de hoje.
2. Clique em **Import**.
3. O sistema busca as operações na API Athena e carrega a tabela.
4. O sino de notificações mostra quantas operações entraram.

> **Você não precisa clicar em Import o tempo todo.** O sistema importa sozinho a cada **20 minutos** (NDF) e a cada **hora** (Opções). O botão serve para adiantar a importação ou para reimportar uma data passada.

---

### 3.3. Encontrar uma operação

1. Clique na barra de busca e escolha a **coluna** na lista que aparece.
2. Digite o valor e pressione **Enter** para criar a ficha do filtro.
3. Repita o processo para combinar filtros — por exemplo, data **e** status.
4. Clique em **Search**.
5. Para limpar tudo de uma vez, use **Clear Filters**.

> **Atenção.** Depois de uma busca, a tabela mostra apenas o resultado. Os botões de documento e e-mail trabalham com o que está carregado na tela — se você filtrou, filtrou para eles também. A única exceção é o **Mapping B3**, que sempre lê o dia inteiro.

---

### 3.4. Corrigir uma linha

Cada linha tem quatro botões na coluna **Actions**, nesta ordem:

| Botão | Cor | O que faz |
|---|---|---|
| Confirm | Verde | Aprova a operação |
| Edit | Azul | Abre o formulário de edição |
| Delete | Vermelho | Remove a linha |
| Send | Azul-escuro | Envia para registro na B3 |

**Para corrigir um dado:**

1. Clique em **Edit** na linha desejada.
2. Ajuste os campos no formulário.
3. Salve. O status passa a **Pending** e a operação precisa da aprovação de **outro usuário**.

**Para editar várias linhas de uma vez:**

1. Marque as caixas de seleção das linhas.
2. Use a ação em massa que aparece na barra.

---

### 3.5. Aprovar uma operação

1. Clique em **Confirm** (botão verde) na linha.
2. Operação com status **New** vai **direto para Approved** — como você não editou nada, não há o que submeter à revisão.
3. Operação com status **Amend** vai para **Pending**, porque a API alterou um dado econômico e alguém precisa conferir.
4. Operação com status **Pending** vai para **Approved**, mas **somente se for outro usuário**. Quem editou não aprova a própria alteração.

> **Duas travas antes de aprovar.** Se a contraparte não estiver cadastrada (badge vermelho **Missing Counterparty**) ou o ativo não estiver no **Index B3**, o sistema bloqueia a aprovação e avisa. Aprovar sem esses cadastros enviaria dado errado para a B3.

---

### 3.6. Enviar para registro na B3

Vale para **NDF FWD Start**, **NDF Other Publisher**, **NDF Commodities**, **Opção FXO** e **Opção Commodities**.

![New Deals — NDF FWD Start](docs/sop-screenshots/new_deals-ndf-fwdstart.png)

1. Com a linha em **Approved**, clique em **Send**.
2. O sistema gera o arquivo **Conecta** e grava na pasta de envio.
3. O status passa a **Sent** e você se torna o **Checker** da operação.

> **Na página NDF Vanilla este passo não existe.** O registro na B3 é feito por outra ferramenta, então a operação segue direto para o mapeamento do retorno.

---

### 3.7. Mapear o retorno da B3

Depois de processar o arquivo, a B3 devolve um arquivo de retorno com o **B3 ID** de cada operação aceita.

1. Confira o campo **Reference Date**.
2. Clique no **botão verde de atualizar**, ao lado do **Import**.
3. O sistema lê os arquivos da pasta de retorno e preenche a coluna **B3 ID**.
4. Uma janela informa quantas operações foram mapeadas e quantas voltaram com erro.

O que acontece com cada operação:

| Situação | Resultado |
|---|---|
| Encontrada no arquivo de retorno | Vira **Success** com o B3 ID preenchido |
| Não encontrada, e esperava retorno (New, Sent ou Error) | Vira **Error** |
| Não encontrada, mas ainda não foi registrada (Approved ou Pending) | Permanece como está |
| Já era **Success** com B3 ID | Não é alterada |

> **O mapeamento lê o dia inteiro**, inclusive o que não está visível na tela. Não é preciso limpar os filtros antes.

---

### 3.8. Gerar confirmações e e-mails

Disponível em **Opção FXO**, **Opção Commodities** e **NDF Commodities**. Os três botões ficam ao lado do **Show entries**.

![New Deals — Opção FXO](docs/sop-screenshots/new_deals-opt-fxo.png)

**Confirmation — documento da contraparte**

1. Clique em **Confirmation**.
2. Uma janela lista os grupos (contraparte × moeda × tipo de documento) e quantas operações cada um contém.
3. Somente operações com status **Success** entram — a confirmação só é gerada depois do registro na B3.
4. Abra o grupo, revise no painel lateral e gere. São produzidos o **Word**, o **PDF** e o **XML**, arquivados na pasta da contraparte.

**Premium — aviso de pagamento de prêmio (D0)**

1. Clique em **Premium**.
2. O sistema seleciona as operações cuja **Spot Date** (data de pagamento do prêmio) é o dia corrente.
3. Gera um e-mail por contraparte, já com os contatos de liquidação preenchidos.

**Econ. Affirmation — afirmação econômica**

1. Clique em **Econ. Affirmation**.
2. Aplica-se às operações do dia contra **instituições financeiras**.

![New Deals — Opção Commodities](docs/sop-screenshots/new_deals-opt-commodities.png)

---

### 3.9. Monitor — conferir se ficou algo pendente

Caminho no menu: **Products → Monitor**.

![Monitor de New Deals](docs/sop-screenshots/new-deals-monitor.png)

Como ler a tela:

1. Cada **coluna** é uma etapa do processo: registro na B3, confirmação e Intrag.
2. Cada **card** é um produto, com o total de operações da data de referência.
3. A **cor do card** indica o progresso: vermelho quando nada foi resolvido, âmbar no meio do caminho e verde quando tudo está **Success**.
4. As etiquetas mostram a quebra por status e por entidade legal.
5. Clique em **Open page** para ir direto à tela do produto.

> **Todo dia, às 19h00 e às 19h30**, o sistema envia um e-mail para a caixa de operações com a lista do que ainda está pendente. Quando não há nada pendente, o e-mail não é enviado.

---

### 3.10. Pending Confirmation — acompanhar as confirmações

Caminho no menu: **Documentation → Pending Confirmation**.

![Pending Confirmation](docs/sop-screenshots/pending-confirmation.png)

1. A tela lista as confirmações geradas e o estágio de cada uma.
2. Use os filtros por coluna para localizar uma contraparte ou um período.
3. As métricas de acompanhamento ficam em **Metrics**.

![Métricas de Pending Confirmation](docs/sop-screenshots/metrics-pending-confirmation.png)

---

### 3.11. Reference Data — cadastrar contrapartes

Caminho no menu: **Data Base → Reference Data**.

![Reference Data](docs/sop-screenshots/reference-data.png)

1. Localize a contraparte pelo **SPN** ou pelo nome.
2. Dê **duplo clique na linha** para abrir o editor de detalhes: conta CETIP, dados bancários e contatos.
3. Para uma contraparte nova, cadastre-a com o **accronym exatamente igual ao que a API envia** no campo *End Counterparty*.

> **Este é o ponto mais importante do cadastro.** O sistema identifica a contraparte pelo **accronym**, e não pelo SPN que a API envia. Accronym errado ou ausente resulta em linha marcada como **Missing Counterparty**.

---

### 3.12. Mapping — cadastrar de-para

Caminho no menu: **Data Base → Mapping**.

![Mapping](docs/sop-screenshots/mapping.png)

Esta é a tela onde se cadastra qualquer tradução entre o código de um sistema e o de outro. **Nada disso fica no código** — tudo é cadastrável aqui.

1. Escolha o **tipo de mapeamento** nas abas do topo.
2. Clique em **Add** para cadastrar um novo registro, ou no botão de edição para alterar um existente.
3. Preencha os campos e salve.

Tipos disponíveis:

| Tipo | Para que serve |
|---|---|
| Currency Base | Códigos e características das moedas |
| Interbook API (NDF) | Pares de books internos que não são negócio de cliente |
| Commodities × B3 | Código da mercadoria no sistema e na B3 |
| Publisher × B3 (NDF) | Fonte de informação e tela de consulta |
| Legal Entity × Accronym | Entidade legal de cada accronym e settlement location |
| Bank Name | Nome dos bancos |
| FXO Conversion Rate | Taxa de conversão por moeda base |
| Swap Curves (Athena × B3) | Curvas de swap |

> **Mapping não exige reinício do sistema.** A alteração vale já na próxima tela que você abrir.

---

### 3.13. Index B3 — cadastrar ativos

Caminho no menu: **Data Base → Index B3**.

![Index B3](docs/sop-screenshots/index-b3.png)

Aqui ficam os ativos subjacentes aceitos pela B3. Um ativo não cadastrado impede a aprovação da operação que o utiliza.

---

### 3.14. Control Panel — rotinas e destinatários de e-mail

Caminho no menu: **Apps → Control Panel**.

![Control Panel](docs/sop-screenshots/control-panel.png)

Cada card é uma rotina automática. Para configurar:

1. Preencha os campos **To** e **Cc**. Separe vários endereços por ponto e vírgula.
2. Saia do campo — o sistema salva automaticamente.
3. Use o botão **Run** para disparar a rotina na hora, sem esperar o horário automático.

Rotinas disponíveis:

- Save CETIP Files
- Save Daily Settlement Files
- Settlement Forecast
- Update Contacts
- Daily Metric — Outstanding Confirmation Brazil OTC
- Pending Confirmation — Weekly Escalation
- Pending Signature Confirmations — Collection
- Deals Monitor — Pending Action

---

### 3.15. Live Position — conferir a posição em custódia

Caminho no menu: **Live Position → NDF** (e demais produtos).

![Live Position NDF](docs/sop-screenshots/live-position-ndf.png)

1. Escolha a **Reference date**.
2. Os cards no topo classificam a carteira por tipo de operação.
3. A tabela mostra os contratos em custódia. É uma tela **somente leitura**.

---

### 3.16. Reconciliations — conciliar

Caminho no menu: **Reconciliations**.

![Conciliação por comitente](docs/sop-screenshots/reconciliation-comitente.png)

![Conciliação Pay/Rec](docs/sop-screenshots/reconciliation-payrec.png)

1. **Comitente** — confronta a posição por comitente.
2. **Pay/Rec** — confronta pagamentos e recebimentos.
3. As divergências aparecem destacadas na própria tabela.

---

## 4. Perguntas Frequentes

### 4.1. A linha está marcada como "Missing Counterparty" e não consigo aprovar

**O que está acontecendo.** O accronym enviado pela API não existe nem no **Reference Data**, nem no mapeamento **Legal Entity × Accronym**. O sistema prefere deixar os campos em branco a exibir uma contraparte errada.

**Como resolver:**

1. Abra a operação e verifique qual accronym a API enviou, no campo *End Counterparty*.
2. Se for um **cliente**, cadastre-o em **Data Base → Reference Data**, com o accronym idêntico ao da API.
3. Se for uma **perna interna JPM** (JPM, MGT ou Lawton), cadastre em **Data Base → Mapping → Legal Entity × Accronym**.
4. Volte à linha, clique no badge vermelho e escolha **Reload Data**. A marcação desaparece sem precisar recarregar a página.

---

### 4.2. Cliquei em Premium e apareceu "Nothing to Generate", mas há operação com Spot Date de hoje

Há duas causas possíveis, nesta ordem de probabilidade:

1. **A contraparte não está resolvida.** O aviso de prêmio é gerado apenas para contrapartes da conta CETIP de cliente. Se as colunas **Accronym** ou **Client** estiverem vazias, o sistema não consegue chegar até a conta. Cadastre a contraparte conforme o item 4.1.
2. **A Spot Date não é hoje de fato.** O filtro compara com o **dia corrente**, e não com a Reference Date da tela. Se você está consultando uma data passada, o prêmio daquele dia já não é D0.

---

### 4.3. Puxaram uma correção, mas a tela continua com o comportamento antigo

**O que está acontecendo.** O servidor da equipe roda sem recarga automática. Depois de uma atualização que altere código ou telas, o sistema precisa ser **reiniciado** — caso contrário continua servindo a versão anterior.

**Como resolver:**

1. Solicite o **reinício do sistema** ao responsável pela instância.
2. No seu navegador, force uma atualização sem cache (**Ctrl + Shift + R**).

> **Exceção:** alterações feitas na tela **Mapping** valem imediatamente, sem reinício.
>
> **Se o sintoma for "o e-mail das 19h não chegou"**, verifique antes se havia algo pendente no **Monitor** naquele horário. Quando está tudo resolvido, o e-mail não é enviado.

---

## 5. Suporte

| Situação | Para quem falar |
|---|---|
| Dúvida de processo operacional | Brazil OTC Operations |
| Erro de sistema ou comportamento inesperado de tela | Time de tecnologia responsável pelo OTC Tracker |
| Falta de acesso a uma página | Administrador do sistema (tela Page Access) |

---

## 6. Manutenção deste guia

Este documento é gerado a partir do arquivo `GUIA_DO_USUARIO_OTC_TRACKER.md`, que é a **fonte única**. Para atualizar:

1. Edite o Markdown.
2. Recapture as telas, se o layout tiver mudado:
   - Suba o app local com o launcher de desenvolvimento.
   - Rode `python scripts/sop-capture/capture_screens.py`.
3. Gere o Word novamente:
   - `python scripts/build_sop_docx.py GUIA_DO_USUARIO_OTC_TRACKER.md`

> **Ao trocar as telas, garanta que os dados exibidos sejam sempre fictícios.** Nenhum dado real de cliente, conta, servidor ou credencial pode aparecer nas imagens.
