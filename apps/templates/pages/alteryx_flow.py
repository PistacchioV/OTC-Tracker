<?xml version="1.0"?>
<AlteryxDocument yxmdVer="2024.1" RunE2="T">
  <Nodes>
    <Node ToolID="1">
      <GuiSettings Plugin="AlteryxBasePluginsGui.Directory.Directory">
        <Position x="54" y="150" />
      </GuiSettings>
      <Properties>
        <Configuration>
          <Directory>I:\Confirmation\Derivativos\Alteryx\Posição B3\ARQUIVOS CETIP\2026\04\13</Directory>
          <FileSpec>*.*</FileSpec>
          <IncludeSubDirs value="False" />
        </Configuration>
        <Annotation DisplayMode="0">
          <Name />
          <DefaultAnnotationText>dir I:\Confirmation\Derivativos\Alteryx\Posição B3\ARQUIVOS CETIP\2026\04\13\*.*</DefaultAnnotationText>
          <Left value="False" />
        </Annotation>
      </Properties>
      <EngineSettings EngineDll="AlteryxBasePluginsEngine.dll" EngineDllEntryPoint="AlteryxDirectory" />
    </Node>
    <Node ToolID="3">
      <GuiSettings Plugin="AlteryxBasePluginsGui.BrowseV2.BrowseV2">
        <Position x="366" y="54" />
      </GuiSettings>
      <Properties>
        <Configuration>
          <TempFile>C:\Users\V823465\AppData\Local\Temp\Alteryx\Engine_20288_af7f4658709642c2bc633dec13e36e2e_\Engine_20288_567377f74d1d2344aba0c8ebfd8710c1~.yxdb</TempFile>
          <TempFileDataProfiling />
          <Layout>
            <ViewMode>Single</ViewMode>
            <ViewSize value="100" />
            <View1>
              <DefaultTab>Profile</DefaultTab>
              <Hints>
                <Table />
              </Hints>
            </View1>
            <View2 />
          </Layout>
        </Configuration>
        <Annotation DisplayMode="0">
          <Name />
          <DefaultAnnotationText />
          <Left value="False" />
        </Annotation>
      </Properties>
      <EngineSettings EngineDll="AlteryxBasePluginsEngine.dll" EngineDllEntryPoint="AlteryxBrowseV2" />
    </Node>
    <Node ToolID="25">
      <GuiSettings Plugin="PortfolioPluginsGui.Email.Email">
        <Position x="798" y="402" />
      </GuiSettings>
      <Properties>
        <Configuration>
          <SMTPServerName>mailhost.jpmchase.net</SMTPServerName>
          <ToIsField value="False" />
          <To>brazil.otc.ops@jpmchase.com</To>
          <CcIsField value="False" />
          <Cc />
          <BccIsField value="False" />
          <Bcc />
          <FromIsField value="False" />
          <From>brazil.otc.ops@jpmchase.com</From>
          <SubjectIsField value="False" />
          <Subject>Arquivos CETIP salvos!</Subject>
          <BodyIsField value="False" />
          <Body>Prezados,

Os arquivos da Cetip necessários para a geração do KPI foram salvos com sucesso!

Atenciosamente,

OTC Derivatives</Body>
          <UserName />
          <Enabled>True</Enabled>
          <Password />
          <Port>25</Port>
          <Encryption>None</Encryption>
          <SMTPAuth value="False" />
        </Configuration>
        <Annotation DisplayMode="0">
          <Name />
          <DefaultAnnotationText />
          <Left value="False" />
        </Annotation>
      </Properties>
      <EngineSettings EngineDll="PortfolioPluginsEngine.dll" EngineDllEntryPoint="AlteryxComposerEmail" />
    </Node>
    <Node ToolID="118">
      <GuiSettings Plugin="AlteryxGuiToolkit.ToolContainer.ToolContainer">
        <Position x="545" y="532" width="1908" height="1798" />
      </GuiSettings>
      <Properties>
        <Configuration>
          <Caption>Salvar Arquivos</Caption>
          <Style TextColor="#314c4a" FillColor="#ecf2f2" BorderColor="#314c4a" Transparency="25" Margin="25" />
          <Disabled value="False" />
          <Folded value="False" />
        </Configuration>
        <Annotation DisplayMode="0">
          <Name />
          <AnnotationText>Salvar Arquivos</AnnotationText>
          <DefaultAnnotationText />
          <Left value="False" />
        </Annotation>
      </Properties>
      <ChildNodes>
        <Node ToolID="9">
          <GuiSettings Plugin="AlteryxBasePluginsGui.Filter.Filter">
            <Position x="570" y="690" />
          </GuiSettings>
          <Properties>
            <Configuration>
              <Expression>Contains([FileName],"DPOSICAO_C21.txt")</Expression>
              <Mode>Custom</Mode>
            </Configuration>
            <Annotation DisplayMode="0">
              <Name />
              <DefaultAnnotationText>Contains([FileName],"DPOSICAO_C21.txt")</DefaultAnnotationText>
              <Left value="False" />
            </Annotation>
          </Properties>
          <EngineSettings EngineDll="AlteryxBasePluginsEngine.dll" EngineDllEntryPoint="AlteryxFilter" />
        </Node>
        <Node ToolID="31">
          <GuiSettings Plugin="AlteryxBasePluginsGui.DynamicInput.DynamicInput">
            <Position x="1650" y="582" />
          </GuiSettings>
          <Properties>
            <Configuration>
              <InputConfiguration>
                <Configuration>
                  <Passwords />
                  <File RecordLimit="" SearchSubDirs="False" FileFormat="0" OutputFileName="FileName">I:\Confirmation\Derivativos\Vernacci\ARQUIVOS CETIP\Arquivos Posiçao\2019\06\73760_190614_DPOSICAO.CETIP21</File>
                  <FormatSpecificOptions>
                    <HeaderRow>False</HeaderRow>
                    <IgnoreErrors>False</IgnoreErrors>
                    <AllowShareWrite>False</AllowShareWrite>
                    <ImportLine>1</ImportLine>
                    <FieldLen>9999999</FieldLen>
                    <SingleThreadRead>False</SingleThreadRead>
                    <IgnoreQuotes>DoubleQuotes</IgnoreQuotes>
                    <Delimeter>\0</Delimeter>
                    <QuoteRecordBreak>False</QuoteRecordBreak>
                    <CodePage>28591</CodePage>
                  </FormatSpecificOptions>
                </Configuration>
              </InputConfiguration>
              <Mode>ReadList</Mode>
              <ReadList_Field>FullPath</ReadList_Field>
              <ReadList_Type>Path</ReadList_Type>
              <ErrorBehaviour>Warning</ErrorBehaviour>
            </Configuration>
            <Annotation DisplayMode="0">
              <Name />
              <DefaultAnnotationText />
              <Left value="False" />
            </Annotation>
          </Properties>
          <EngineSettings EngineDll="AlteryxBasePluginsEngine.dll" EngineDllEntryPoint="AlteryxDynamicInput" />
        </Node>
        <Node ToolID="30">
          <GuiSettings Plugin="AlteryxBasePluginsGui.Formula.Formula">
            <Position x="1842" y="581" />
          </GuiSettings>
          <Properties>
            <Configuration>
              <FormulaFields>
                <FormulaField expression="Substring([FileName],8,6)" field="DateRef" size="2147483647" type="V_WString" />
                <FormulaField expression="'73760_' + [DateRef] + '_DPOSICAO.CETIP21'" field="NewFile" size="1073741823" type="V_WString" />
                <FormulaField expression="'I:\Confirmation\Derivativos\Vernacci\ARQUIVOS CETIP\Arquivos Posiçao\20' + Left([DateRef], 2) + '\' + Substring([DateRef],2,2)" field="NewPath" size="1073741823" type="V_WString" />
                <FormulaField expression="[NewPath] + '\' + [NewFile]" field="CompletePath" size="1073741823" type="V_WString" />
              </FormulaFields>
            </Configuration>
            <Annotation DisplayMode="0">
              <Name />
              <AnnotationText>Define output folder</AnnotationText>
              <DefaultAnnotationText>DateRef = Substring([FileName],8,6)
NewFile = '73760_' + [DateRef] + '_DPOSICAO....</DefaultAnnotationText>
              <Left value="False" />
            </Annotation>
          </Properties>
          <EngineSettings EngineDll="AlteryxBasePluginsEngine.dll" EngineDllEntryPoint="AlteryxFormula" />
        </Node>
        <Node ToolID="32">
          <GuiSettings Plugin="AlteryxBasePluginsGui.AlteryxSelect.AlteryxSelect">
            <Position x="2034" y="582" />
          </GuiSettings>
          <Properties>
            <Configuration>
              <OrderChanged value="False" />
              <CommaDecimal value="False" />
              <SelectFields>
                <SelectField field="Field_1" selected="True" />
                <SelectField field="CompletePath" selected="True" />
                <SelectField field="*Unknown" selected="False" />
              </SelectFields>
            </Configuration>
            <Annotation DisplayMode="0">
              <Name />
              <DefaultAnnotationText />
              <Left value="False" />
            </Annotation>
          </Properties>
          <EngineSettings EngineDll="AlteryxBasePluginsEngine.dll" EngineDllEntryPoint="AlteryxSelect" />
        </Node>
        <Node ToolID="29">
          <GuiSettings Plugin="AlteryxBasePluginsGui.DbFileOutput.DbFileOutput">
            <Position x="2226" y="581" />
          </GuiSettings>
          <Properties>
            <Configuration>
              <File MaxRecords="" FileFormat="0">I:\Confirmation\Derivativos\Vernacci\ARQUIVOS CETIP\Arquivos Posiçao\testeAlteryx\Example.txt</File>
              <Passwords />
              <Disable>False</Disable>
              <FormatSpecificOptions>
                <LineEndStyle>CRLF</LineEndStyle>
                <Delimeter>\0</Delimeter>
                <ForceQuotes>False</ForceQuotes>
                <HeaderRow>False</HeaderRow>
                <CodePage>28591</CodePage>
                <WriteBOM>True</WriteBOM>
              </FormatSpecificOptions>
              <MultiFile value="True" />
              <MultiFileType>Path</MultiFileType>
              <MultiFileField>CompletePath</MultiFileField>
              <KeepField value="False" />
            </Configuration>
            <Annotation DisplayMode="0">
              <Name />
              <DefaultAnnotationText>Example.txt</DefaultAnnotationText>
              <Left value="False" />
            </Annotation>
            <Dependencies>
              <Implicit />
            </Dependencies>
          </Properties>
          <EngineSettings EngineDll="AlteryxBasePluginsEngine.dll" EngineDllEntryPoint="AlteryxDbFileOutput" />
        </Node>
        <Node ToolID="23">
          <GuiSettings Plugin="AlteryxBasePluginsGui.Filter.Filter">
            <Position x="1290" y="1794" />
          </GuiSettings>
          <Properties>
            <Configuration>
              <Expression>Contains([FileName],"_DMOVIMENTO-SWAP.txt")</Expression>
              <Mode>Custom</Mode>
            </Configuration>
            <Annotation DisplayMode="0">
              <Name />
              <DefaultAnnotationText>Contains([FileName],"_DMOVIMENTO-SWAP.txt")</DefaultAnnotationText>
              <Left value="False" />
            </Annotation>
          </Properties>
          <EngineSettings EngineDll="AlteryxBasePluginsEngine.dll" EngineDllEntryPoint="AlteryxFilter" />
        </Node>
        <Node ToolID="21">
          <GuiSettings Plugin="AlteryxBasePluginsGui.Filter.Filter">
            <Position x="1193" y="1674" />
          </GuiSettings>
          <Properties>
            <Configuration>
              <Expression>Contains([FileName],"_DMOVIMENTO_C21.txt")</Expression>
              <Mode>Custom</Mode>
            </Configuration>
            <Annotation DisplayMode="0">
              <Name />
              <DefaultAnnotationText>Contains([FileName],"_DMOVIMENTO_C21.txt")</DefaultAnnotationText>
              <Left value="False" />
            </Annotation>
          </Properties>
          <EngineSettings EngineDll="AlteryxBasePluginsEngine.dll" EngineDllEntryPoint="AlteryxFilter" />
        </Node>
        <Node ToolID="19">
          <GuiSettings Plugin="AlteryxBasePluginsGui.Filter.Filter">
            <Position x="1062" y="1410" />
          </GuiSettings>
          <Properties>
            <Configuration>
              <Expression>Contains([FileName],"OPCAO_") and Contains([FileName],"_DMOVIMENTO.txt") and !Contains([FileName],"_15H00.txt") and !Contains([FileName],"_18H30.txt")</Expression>
              <Mode>Custom</Mode>
            </Configuration>
            <Annotation DisplayMode="0">
              <Name />
              <DefaultAnnotationText>Contains([FileName],"OPCAO_") and Contains([FileName],"_DMOVIMENTO.txt") and !Co...</DefaultAnnotationText>
              <Left value="False" />
            </Annotation>
          </Properties>
          <EngineSettings EngineDll="AlteryxBasePluginsEngine.dll" EngineDllEntryPoint="AlteryxFilter" />
        </Node>
        <Node ToolID="13">
          <GuiSettings Plugin="AlteryxBasePluginsGui.Filter.Filter">
            <Position x="1002" y="1194" />
          </GuiSettings>
          <Properties>
            <Configuration>
              <Expression>Contains([FileName],"OPCAO_") and Contains([FileName],"_DPOSICAO.txt")</Expression>
              <Mode>Custom</Mode>
            </Configuration>
            <Annotation DisplayMode="0">
              <Name />
              <DefaultAnnotationText>Contains([FileName],"OPCAO_") and Contains([FileName],"_DPOSI...</DefaultAnnotationText>
              <Left value="False" />
            </Annotation>
          </Properties>
          <EngineSettings EngineDll="AlteryxBasePluginsEngine.dll" EngineDllEntryPoint="AlteryxFilter" />
        </Node>
        <Node ToolID="11">
          <GuiSettings Plugin="AlteryxBasePluginsGui.Filter.Filter">
            <Position x="833" y="966" />
          </GuiSettings>
          <Properties>
            <Configuration>
              <Expression>Contains([FileName],"DPOSICAO-SWAP.txt")</Expression>
              <Mode>Custom</Mode>
            </Configuration>
            <Annotation DisplayMode="0">
              <Name />
              <DefaultAnnotationText>Contains([FileName],"DPOSICAO-SWAP.txt")</DefaultAnnotationText>
              <Left value="False" />
            </Annotation>
          </Properties>
          <EngineSettings EngineDll="AlteryxBasePluginsEngine.dll" EngineDllEntryPoint="AlteryxFilter" />
        </Node>
        <Node ToolID="33">
          <GuiSettings Plugin="AlteryxBasePluginsGui.DynamicInput.DynamicInput">
            <Position x="1686" y="954" />
          </GuiSettings>
          <Properties>
            <Configuration>
              <InputConfiguration>
                <Configuration>
                  <Passwords />
                  <File RecordLimit="" SearchSubDirs="False" FileFormat="0" OutputFileName="FileName">I:\Confirmation\Derivativos\Vernacci\ARQUIVOS CETIP\Arquivos Posiçao\2019\06\73760_190614_DPOSICAO.CETIP21</File>
                  <FormatSpecificOptions>
                    <HeaderRow>False</HeaderRow>
                    <IgnoreErrors>False</IgnoreErrors>
                    <AllowShareWrite>False</AllowShareWrite>
                    <ImportLine>1</ImportLine>
                    <FieldLen>9999999</FieldLen>
                    <SingleThreadRead>False</SingleThreadRead>
                    <IgnoreQuotes>DoubleQuotes</IgnoreQuotes>
                    <Delimeter>\0</Delimeter>
                    <QuoteRecordBreak>False</QuoteRecordBreak>
                    <CodePage>28591</CodePage>
                  </FormatSpecificOptions>
                </Configuration>
              </InputConfiguration>
              <Mode>ReadList</Mode>
              <ReadList_Field>FullPath</ReadList_Field>
              <ReadList_Type>Path</ReadList_Type>
              <ErrorBehaviour>Warning</ErrorBehaviour>
            </Configuration>
            <Annotation DisplayMode="0">
              <Name />
              <DefaultAnnotationText />
              <Left value="False" />
            </Annotation>
          </Properties>
          <EngineSettings EngineDll="AlteryxBasePluginsEngine.dll" EngineDllEntryPoint="AlteryxDynamicInput" />
        </Node>
        <Node ToolID="34">
          <GuiSettings Plugin="AlteryxBasePluginsGui.Formula.Formula">
            <Position x="1878" y="954" />
          </GuiSettings>
          <Properties>
            <Configuration>
              <FormulaFields>
                <FormulaField expression="Substring([FileName],8,6)" field="DateRef" size="2147483647" type="V_WString" />
                <FormulaField expression="'73760_' + [DateRef] + '_DPOSICAO-SWAP.CETIP21'" field="NewFile" size="1073741823" type="V_WString" />
                <FormulaField expression="'I:\Confirmation\Derivativos\Vernacci\ARQUIVOS CETIP\Arquivos Posiçao\20' + Left([DateRef], 2) + '\' + Substring([DateRef],2,2)" field="NewPath" size="1073741823" type="V_WString" />
                <FormulaField expression="[NewPath] + '\' + [NewFile]" field="CompletePath" size="1073741823" type="V_WString" />
              </FormulaFields>
            </Configuration>
            <Annotation DisplayMode="0">
              <Name />
              <AnnotationText>Define output folder</AnnotationText>
              <DefaultAnnotationText>DateRef = Substring([FileName],8,6)
NewFile = '73760_' + [DateRef] + '_DPOSICAO-...</DefaultAnnotationText>
              <Left value="False" />
            </Annotation>
          </Properties>
          <EngineSettings EngineDll="AlteryxBasePluginsEngine.dll" EngineDllEntryPoint="AlteryxFormula" />
        </Node>
        <Node ToolID="35">
          <GuiSettings Plugin="AlteryxBasePluginsGui.DbFileOutput.DbFileOutput">
            <Position x="2262" y="954" />
          </GuiSettings>
          <Properties>
            <Configuration>
              <File MaxRecords="" FileFormat="0">I:\Confirmation\Derivativos\Vernacci\ARQUIVOS CETIP\Arquivos Posiçao\testeAlteryx\Example.txt</File>
              <Passwords />
              <FormatSpecificOptions>
                <LineEndStyle>CRLF</LineEndStyle>
                <Delimeter>\0</Delimeter>
                <ForceQuotes>False</ForceQuotes>
                <HeaderRow>False</HeaderRow>
                <CodePage>28591</CodePage>
                <WriteBOM>True</WriteBOM>
              </FormatSpecificOptions>
              <MultiFile value="True" />
              <MultiFileType>Path</MultiFileType>
              <MultiFileField>CompletePath</MultiFileField>
              <KeepField value="False" />
            </Configuration>
            <Annotation DisplayMode="0">
              <Name />
              <DefaultAnnotationText>Example.txt</DefaultAnnotationText>
              <Left value="False" />
            </Annotation>
          </Properties>
          <EngineSettings EngineDll="AlteryxBasePluginsEngine.dll" EngineDllEntryPoint="AlteryxDbFileOutput" />
        </Node>
        <Node ToolID="36">
          <GuiSettings Plugin="AlteryxBasePluginsGui.AlteryxSelect.AlteryxSelect">
            <Position x="2070" y="954" />
          </GuiSettings>
          <Properties>
            <Configuration>
              <OrderChanged value="False" />
              <CommaDecimal value="False" />
              <SelectFields>
                <SelectField field="Field_1" selected="True" />
                <SelectField field="CompletePath" selected="True" />
                <SelectField field="*Unknown" selected="False" />
              </SelectFields>
            </Configuration>
            <Annotation DisplayMode="0">
              <Name />
              <DefaultAnnotationText />
              <Left value="False" />
            </Annotation>
          </Properties>
          <EngineSettings EngineDll="AlteryxBasePluginsEngine.dll" EngineDllEntryPoint="AlteryxSelect" />
        </Node>
        <Node ToolID="37">
          <GuiSettings Plugin="AlteryxBasePluginsGui.DynamicInput.DynamicInput">
            <Position x="1698" y="1182" />
          </GuiSettings>
          <Properties>
            <Configuration>
              <InputConfiguration>
                <Configuration>
                  <Passwords />
                  <File OutputFileName="FileName" RecordLimit="" SearchSubDirs="False" FileFormat="0">I:\Confirmation\Derivativos\Vernacci\ARQUIVOS CETIP\Arquivos Posiçao\2019\06\73760_190614_DPOSICAO.CETIP21</File>
                  <FormatSpecificOptions>
                    <CodePage>28591</CodePage>
                    <Delimeter>\0</Delimeter>
                    <IgnoreErrors>False</IgnoreErrors>
                    <FieldLen>9999999</FieldLen>
                    <AllowShareWrite>False</AllowShareWrite>
                    <HeaderRow>False</HeaderRow>
                    <IgnoreQuotes>DoubleQuotes</IgnoreQuotes>
                    <ImportLine>1</ImportLine>
                  </FormatSpecificOptions>
                </Configuration>
              </InputConfiguration>
              <Mode>ReadList</Mode>
              <ReadList_Field>FullPath</ReadList_Field>
              <ReadList_Type>Path</ReadList_Type>
            </Configuration>
            <Annotation DisplayMode="0">
              <Name />
              <DefaultAnnotationText />
              <Left value="False" />
            </Annotation>
          </Properties>
          <EngineSettings EngineDll="AlteryxBasePluginsEngine.dll" EngineDllEntryPoint="AlteryxDynamicInput" />
        </Node>
        <Node ToolID="38">
          <GuiSettings Plugin="AlteryxBasePluginsGui.Formula.Formula">
            <Position x="1890" y="1182" />
          </GuiSettings>
          <Properties>
            <Configuration>
              <FormulaFields>
                <FormulaField expression="Substring([FileName],6,6)" field="DateRef" size="2147483647" type="V_WString" />
                <FormulaField expression="'73760_' + [DateRef] + '_DPOSICAO.OPCAO'" field="NewFile" size="1073741823" type="V_WString" />
                <FormulaField expression="'I:\Confirmation\Derivativos\Vernacci\ARQUIVOS CETIP\Arquivos Posiçao\20' + Left([DateRef], 2) + '\' + Substring([DateRef],2,2)" field="NewPath" size="1073741823" type="V_WString" />
                <FormulaField expression="[NewPath] + '\' + [NewFile]" field="CompletePath" size="1073741823" type="V_WString" />
              </FormulaFields>
            </Configuration>
            <Annotation DisplayMode="0">
              <Name />
              <AnnotationText>Define output folder</AnnotationText>
              <DefaultAnnotationText>DateRef = Substring([FileName],6,6)
NewFile = '73760_' + [DateRef] + '_DPOSICAO....</DefaultAnnotationText>
              <Left value="False" />
            </Annotation>
          </Properties>
          <EngineSettings EngineDll="AlteryxBasePluginsEngine.dll" EngineDllEntryPoint="AlteryxFormula" />
        </Node>
        <Node ToolID="39">
          <GuiSettings Plugin="AlteryxBasePluginsGui.DbFileOutput.DbFileOutput">
            <Position x="2274" y="1182" />
          </GuiSettings>
          <Properties>
            <Configuration>
              <File MaxRecords="" FileFormat="0">I:\Confirmation\Derivativos\Vernacci\ARQUIVOS CETIP\Arquivos Posiçao\testeAlteryx\Example.txt</File>
              <Passwords />
              <FormatSpecificOptions>
                <LineEndStyle>CRLF</LineEndStyle>
                <Delimeter>\0</Delimeter>
                <ForceQuotes>False</ForceQuotes>
                <HeaderRow>False</HeaderRow>
                <CodePage>28591</CodePage>
                <WriteBOM>True</WriteBOM>
              </FormatSpecificOptions>
              <MultiFile value="True" />
              <MultiFileType>Path</MultiFileType>
              <MultiFileField>CompletePath</MultiFileField>
              <KeepField value="False" />
            </Configuration>
            <Annotation DisplayMode="0">
              <Name />
              <DefaultAnnotationText>Example.txt</DefaultAnnotationText>
              <Left value="False" />
            </Annotation>
          </Properties>
          <EngineSettings EngineDll="AlteryxBasePluginsEngine.dll" EngineDllEntryPoint="AlteryxDbFileOutput" />
        </Node>
        <Node ToolID="40">
          <GuiSettings Plugin="AlteryxBasePluginsGui.AlteryxSelect.AlteryxSelect">
            <Position x="2082" y="1182" />
          </GuiSettings>
          <Properties>
            <Configuration>
              <OrderChanged value="False" />
              <CommaDecimal value="False" />
              <SelectFields>
                <SelectField field="Field_1" selected="True" />
                <SelectField field="CompletePath" selected="True" />
                <SelectField field="*Unknown" selected="False" />
              </SelectFields>
            </Configuration>
            <Annotation DisplayMode="0">
              <Name />
              <DefaultAnnotationText />
              <Left value="False" />
            </Annotation>
          </Properties>
          <EngineSettings EngineDll="AlteryxBasePluginsEngine.dll" EngineDllEntryPoint="AlteryxSelect" />
        </Node>
        <Node ToolID="41">
          <GuiSettings Plugin="AlteryxBasePluginsGui.DynamicInput.DynamicInput">
            <Position x="1710" y="1398" />
          </GuiSettings>
          <Properties>
            <Configuration>
              <InputConfiguration>
                <Configuration>
                  <Passwords />
                  <File OutputFileName="FileName" RecordLimit="" SearchSubDirs="False" FileFormat="0">I:\Confirmation\Derivativos\Vernacci\ARQUIVOS CETIP\Arquivos Movimento\OPÇÃO\2019\06\73760_190603_DMOVIMENTO_3.OPCAO</File>
                  <FormatSpecificOptions>
                    <CodePage>28591</CodePage>
                    <Delimeter>\0</Delimeter>
                    <IgnoreErrors>False</IgnoreErrors>
                    <FieldLen>999999</FieldLen>
                    <AllowShareWrite>False</AllowShareWrite>
                    <HeaderRow>False</HeaderRow>
                    <IgnoreQuotes>DoubleQuotes</IgnoreQuotes>
                    <ImportLine>1</ImportLine>
                  </FormatSpecificOptions>
                </Configuration>
              </InputConfiguration>
              <Mode>ReadList</Mode>
              <ReadList_Field>FullPath</ReadList_Field>
              <ReadList_Type>Path</ReadList_Type>
            </Configuration>
            <Annotation DisplayMode="0">
              <Name />
              <DefaultAnnotationText />
              <Left value="False" />
            </Annotation>
          </Properties>
          <EngineSettings EngineDll="AlteryxBasePluginsEngine.dll" EngineDllEntryPoint="AlteryxDynamicInput" />
        </Node>
        <Node ToolID="42">
          <GuiSettings Plugin="AlteryxBasePluginsGui.Formula.Formula">
            <Position x="1902" y="1398" />
          </GuiSettings>
          <Properties>
            <Configuration>
              <FormulaFields>
                <FormulaField expression="Substring([FileName],6,6)" field="DateRef" size="2147483647" type="V_WString" />
                <FormulaField expression="'73760_' + [DateRef] + '_DMOVIMENTO_3.OPCAO'" field="NewFile" size="1073741823" type="V_WString" />
                <FormulaField expression="'I:\Confirmation\Derivativos\Vernacci\ARQUIVOS CETIP\Arquivos Movimento\OPÇÃO\20' + Left([DateRef], 2) + '\' + Substring([DateRef],2,2)" field="NewPath" size="1073741823" type="V_WString" />
                <FormulaField expression="[NewPath] + '\' + [NewFile]" field="CompletePath" size="1073741823" type="V_WString" />
              </FormulaFields>
            </Configuration>
            <Annotation DisplayMode="0">
              <Name />
              <AnnotationText>Define output folder</AnnotationText>
              <DefaultAnnotationText>DateRef = Substring([FileName],6,6)
NewFile = '73760_' + [DateRef] + '_DMOVIMENT...</DefaultAnnotationText>
              <Left value="False" />
            </Annotation>
          </Properties>
          <EngineSettings EngineDll="AlteryxBasePluginsEngine.dll" EngineDllEntryPoint="AlteryxFormula" />
        </Node>
        <Node ToolID="43">
          <GuiSettings Plugin="AlteryxBasePluginsGui.DynamicInput.DynamicInput">
            <Position x="1734" y="1662" />
          </GuiSettings>
          <Properties>
            <Configuration>
              <InputConfiguration>
                <Configuration>
                  <Passwords />
                  <File OutputFileName="FileName" RecordLimit="" SearchSubDirs="False" FileFormat="0">I:\Confirmation\Derivativos\Vernacci\ARQUIVOS CETIP\Arquivos Movimento\TERMO\2019\06\73760_190614_DMOVIMENTO.CETIP21</File>
                  <FormatSpecificOptions>
                    <CodePage>28591</CodePage>
                    <Delimeter>\0</Delimeter>
                    <IgnoreErrors>False</IgnoreErrors>
                    <FieldLen>9999999</FieldLen>
                    <AllowShareWrite>False</AllowShareWrite>
                    <HeaderRow>False</HeaderRow>
                    <IgnoreQuotes>DoubleQuotes</IgnoreQuotes>
                    <ImportLine>1</ImportLine>
                  </FormatSpecificOptions>
                </Configuration>
              </InputConfiguration>
              <Mode>ReadList</Mode>
              <ReadList_Field>FullPath</ReadList_Field>
              <ReadList_Type>Path</ReadList_Type>
            </Configuration>
            <Annotation DisplayMode="0">
              <Name />
              <DefaultAnnotationText />
              <Left value="False" />
            </Annotation>
          </Properties>
          <EngineSettings EngineDll="AlteryxBasePluginsEngine.dll" EngineDllEntryPoint="AlteryxDynamicInput" />
        </Node>
        <Node ToolID="44">
          <GuiSettings Plugin="AlteryxBasePluginsGui.Formula.Formula">
            <Position x="1926" y="1662" />
          </GuiSettings>
          <Properties>
            <Configuration>
              <FormulaFields>
                <FormulaField expression="Substring([FileName],8,6)" field="DateRef" size="2147483647" type="V_WString" />
                <FormulaField expression="'73760_' + [DateRef] + '_DMOVIMENTO.CETIP21'" field="NewFile" size="1073741823" type="V_WString" />
                <FormulaField expression="'I:\Confirmation\Derivativos\Vernacci\ARQUIVOS CETIP\Arquivos Movimento\TERMO\20' + Left([DateRef], 2) + '\' + Substring([DateRef],2,2)" field="NewPath" size="1073741823" type="V_WString" />
                <FormulaField expression="[NewPath] + '\' + [NewFile]" field="CompletePath" size="1073741823" type="V_WString" />
              </FormulaFields>
            </Configuration>
            <Annotation DisplayMode="0">
              <Name />
              <AnnotationText>Define output folder</AnnotationText>
              <DefaultAnnotationText>DateRef = Substring([FileName],8,6)
NewFile = '73760_' + [DateRef] + '_DMOVIMENT...</DefaultAnnotationText>
              <Left value="False" />
            </Annotation>
          </Properties>
          <EngineSettings EngineDll="AlteryxBasePluginsEngine.dll" EngineDllEntryPoint="AlteryxFormula" />
        </Node>
        <Node ToolID="45">
          <GuiSettings Plugin="AlteryxBasePluginsGui.AlteryxSelect.AlteryxSelect">
            <Position x="2118" y="1662" />
          </GuiSettings>
          <Properties>
            <Configuration>
              <OrderChanged value="False" />
              <CommaDecimal value="False" />
              <SelectFields>
                <SelectField field="Field_1" selected="True" />
                <SelectField field="CompletePath" selected="True" />
                <SelectField field="*Unknown" selected="False" />
              </SelectFields>
            </Configuration>
            <Annotation DisplayMode="0">
              <Name />
              <DefaultAnnotationText />
              <Left value="False" />
            </Annotation>
          </Properties>
          <EngineSettings EngineDll="AlteryxBasePluginsEngine.dll" EngineDllEntryPoint="AlteryxSelect" />
        </Node>
        <Node ToolID="46">
          <GuiSettings Plugin="AlteryxBasePluginsGui.DbFileOutput.DbFileOutput">
            <Position x="2310" y="1662" />
          </GuiSettings>
          <Properties>
            <Configuration>
              <File MaxRecords="" FileFormat="0">I:\Confirmation\Derivativos\Vernacci\ARQUIVOS CETIP\Arquivos Posiçao\testeAlteryx\Example.txt</File>
              <Passwords />
              <FormatSpecificOptions>
                <LineEndStyle>CRLF</LineEndStyle>
                <Delimeter>\0</Delimeter>
                <ForceQuotes>False</ForceQuotes>
                <HeaderRow>False</HeaderRow>
                <CodePage>28591</CodePage>
                <WriteBOM>True</WriteBOM>
              </FormatSpecificOptions>
              <MultiFile value="True" />
              <MultiFileType>Path</MultiFileType>
              <MultiFileField>CompletePath</MultiFileField>
              <KeepField value="False" />
            </Configuration>
            <Annotation DisplayMode="0">
              <Name />
              <DefaultAnnotationText>Example.txt</DefaultAnnotationText>
              <Left value="False" />
            </Annotation>
          </Properties>
          <EngineSettings EngineDll="AlteryxBasePluginsEngine.dll" EngineDllEntryPoint="AlteryxDbFileOutput" />
        </Node>
        <Node ToolID="47">
          <GuiSettings Plugin="AlteryxBasePluginsGui.DynamicInput.DynamicInput">
            <Position x="1734" y="1782" />
          </GuiSettings>
          <Properties>
            <Configuration>
              <InputConfiguration>
                <Configuration>
                  <Passwords />
                  <File OutputFileName="FileName" RecordLimit="" SearchSubDirs="False" FileFormat="0">I:\Confirmation\Derivativos\Vernacci\ARQUIVOS CETIP\Arquivos Movimento\SWAP\2019\06\73760_190612_DMOVIMENTO-SWAP.CETIP21</File>
                  <FormatSpecificOptions>
                    <CodePage>28591</CodePage>
                    <Delimeter>\0</Delimeter>
                    <IgnoreErrors>False</IgnoreErrors>
                    <FieldLen>999999</FieldLen>
                    <AllowShareWrite>False</AllowShareWrite>
                    <HeaderRow>False</HeaderRow>
                    <IgnoreQuotes>DoubleQuotes</IgnoreQuotes>
                    <ImportLine>1</ImportLine>
                  </FormatSpecificOptions>
                </Configuration>
              </InputConfiguration>
              <Mode>ReadList</Mode>
              <ReadList_Field>FullPath</ReadList_Field>
              <ReadList_Type>Path</ReadList_Type>
            </Configuration>
            <Annotation DisplayMode="0">
              <Name />
              <DefaultAnnotationText />
              <Left value="False" />
            </Annotation>
          </Properties>
          <EngineSettings EngineDll="AlteryxBasePluginsEngine.dll" EngineDllEntryPoint="AlteryxDynamicInput" />
        </Node>
        <Node ToolID="48">
          <GuiSettings Plugin="AlteryxBasePluginsGui.DbFileOutput.DbFileOutput">
            <Position x="2310" y="1782" />
          </GuiSettings>
          <Properties>
            <Configuration>
              <File MaxRecords="" FileFormat="0">I:\Confirmation\Derivativos\Vernacci\ARQUIVOS CETIP\Arquivos Posiçao\testeAlteryx\Example.txt</File>
              <Passwords />
              <FormatSpecificOptions>
                <LineEndStyle>CRLF</LineEndStyle>
                <Delimeter>\0</Delimeter>
                <ForceQuotes>False</ForceQuotes>
                <HeaderRow>False</HeaderRow>
                <CodePage>28591</CodePage>
                <WriteBOM>True</WriteBOM>
              </FormatSpecificOptions>
              <MultiFile value="True" />
              <MultiFileType>Path</MultiFileType>
              <MultiFileField>CompletePath</MultiFileField>
              <KeepField value="False" />
            </Configuration>
            <Annotation DisplayMode="0">
              <Name />
              <DefaultAnnotationText>Example.txt</DefaultAnnotationText>
              <Left value="False" />
            </Annotation>
          </Properties>
          <EngineSettings EngineDll="AlteryxBasePluginsEngine.dll" EngineDllEntryPoint="AlteryxDbFileOutput" />
        </Node>
        <Node ToolID="49">
          <GuiSettings Plugin="AlteryxBasePluginsGui.AlteryxSelect.AlteryxSelect">
            <Position x="2118" y="1782" />
          </GuiSettings>
          <Properties>
            <Configuration>
              <OrderChanged value="False" />
              <CommaDecimal value="False" />
              <SelectFields>
                <SelectField field="Field_1" selected="True" />
                <SelectField field="CompletePath" selected="True" />
                <SelectField field="*Unknown" selected="False" />
              </SelectFields>
            </Configuration>
            <Annotation DisplayMode="0">
              <Name />
              <DefaultAnnotationText />
              <Left value="False" />
            </Annotation>
          </Properties>
          <EngineSettings EngineDll="AlteryxBasePluginsEngine.dll" EngineDllEntryPoint="AlteryxSelect" />
        </Node>
        <Node ToolID="50">
          <GuiSettings Plugin="AlteryxBasePluginsGui.Formula.Formula">
            <Position x="1926" y="1782" />
          </GuiSettings>
          <Properties>
            <Configuration>
              <FormulaFields>
                <FormulaField expression="Substring([FileName],8,6)" field="DateRef" size="2147483647" type="V_WString" />
                <FormulaField expression="'73760_' + [DateRef] + '_DMOVIMENTO-SWAP.CETIP21'" field="NewFile" size="1073741823" type="V_WString" />
                <FormulaField expression="'I:\Confirmation\Derivativos\Vernacci\ARQUIVOS CETIP\Arquivos Movimento\SWAP\20' + Left([DateRef], 2) + '\' + Substring([DateRef],2,2)" field="NewPath" size="1073741823" type="V_WString" />
                <FormulaField expression="[NewPath] + '\' + [NewFile]" field="CompletePath" size="1073741823" type="V_WString" />
              </FormulaFields>
            </Configuration>
            <Annotation DisplayMode="0">
              <Name />
              <AnnotationText>Define output folder</AnnotationText>
              <DefaultAnnotationText>DateRef = Substring([FileName],8,6)
NewFile = '73760_' + [DateRef] + '_DMOVIMENT...</DefaultAnnotationText>
              <Left value="False" />
            </Annotation>
          </Properties>
          <EngineSettings EngineDll="AlteryxBasePluginsEngine.dll" EngineDllEntryPoint="AlteryxFormula" />
        </Node>
        <Node ToolID="51">
          <GuiSettings Plugin="AlteryxBasePluginsGui.AlteryxSelect.AlteryxSelect">
            <Position x="2094" y="1398" />
          </GuiSettings>
          <Properties>
            <Configuration>
              <OrderChanged value="False" />
              <CommaDecimal value="False" />
              <SelectFields>
                <SelectField field="Field_1" selected="True" />
                <SelectField field="CompletePath" selected="True" />
                <SelectField field="*Unknown" selected="False" />
              </SelectFields>
            </Configuration>
            <Annotation DisplayMode="0">
              <Name />
              <DefaultAnnotationText />
              <Left value="False" />
            </Annotation>
          </Properties>
          <EngineSettings EngineDll="AlteryxBasePluginsEngine.dll" EngineDllEntryPoint="AlteryxSelect" />
        </Node>
        <Node ToolID="52">
          <GuiSettings Plugin="AlteryxBasePluginsGui.DbFileOutput.DbFileOutput">
            <Position x="2286" y="1398" />
          </GuiSettings>
          <Properties>
            <Configuration>
              <File MaxRecords="" FileFormat="0">I:\Confirmation\Derivativos\Vernacci\ARQUIVOS CETIP\Arquivos Posiçao\testeAlteryx\Example.txt</File>
              <Passwords />
              <Disable>False</Disable>
              <FormatSpecificOptions>
                <LineEndStyle>CRLF</LineEndStyle>
                <Delimeter>\0</Delimeter>
                <ForceQuotes>False</ForceQuotes>
                <HeaderRow>False</HeaderRow>
                <CodePage>28591</CodePage>
                <WriteBOM>True</WriteBOM>
              </FormatSpecificOptions>
              <MultiFile value="True" />
              <MultiFileType>Path</MultiFileType>
              <MultiFileField>CompletePath</MultiFileField>
              <KeepField value="False" />
            </Configuration>
            <Annotation DisplayMode="0">
              <Name />
              <DefaultAnnotationText>Example.txt</DefaultAnnotationText>
              <Left value="False" />
            </Annotation>
          </Properties>
          <EngineSettings EngineDll="AlteryxBasePluginsEngine.dll" EngineDllEntryPoint="AlteryxDbFileOutput" />
        </Node>
        <Node ToolID="53">
          <GuiSettings Plugin="AlteryxBasePluginsGui.Filter.Filter">
            <Position x="918" y="1086" />
          </GuiSettings>
          <Properties>
            <Configuration>
              <Expression>Contains([FileName],"_DFLUXO_SWAP.txt")</Expression>
              <Mode>Custom</Mode>
            </Configuration>
            <Annotation DisplayMode="0">
              <Name />
              <DefaultAnnotationText>Contains([FileName],"_DFLUXO_SWAP.txt")</DefaultAnnotationText>
              <Left value="False" />
            </Annotation>
          </Properties>
          <EngineSettings EngineDll="AlteryxBasePluginsEngine.dll" EngineDllEntryPoint="AlteryxFilter" />
        </Node>
        <Node ToolID="54">
          <GuiSettings Plugin="AlteryxBasePluginsGui.DynamicInput.DynamicInput">
            <Position x="1698" y="1074" />
          </GuiSettings>
          <Properties>
            <Configuration>
              <InputConfiguration>
                <Configuration>
                  <Passwords />
                  <File OutputFileName="FileName" RecordLimit="" SearchSubDirs="False" FileFormat="0">I:\Confirmation\Derivativos\Vernacci\ARQUIVOS CETIP\Arquivos Posiçao\2019\06\73760_190614_DPOSICAO.CETIP21</File>
                  <FormatSpecificOptions>
                    <CodePage>28591</CodePage>
                    <Delimeter>\0</Delimeter>
                    <IgnoreErrors>False</IgnoreErrors>
                    <FieldLen>9999999</FieldLen>
                    <AllowShareWrite>False</AllowShareWrite>
                    <HeaderRow>False</HeaderRow>
                    <IgnoreQuotes>DoubleQuotes</IgnoreQuotes>
                    <ImportLine>1</ImportLine>
                  </FormatSpecificOptions>
                </Configuration>
              </InputConfiguration>
              <Mode>ReadList</Mode>
              <ReadList_Field>FullPath</ReadList_Field>
              <ReadList_Type>Path</ReadList_Type>
            </Configuration>
            <Annotation DisplayMode="0">
              <Name />
              <DefaultAnnotationText />
              <Left value="False" />
            </Annotation>
          </Properties>
          <EngineSettings EngineDll="AlteryxBasePluginsEngine.dll" EngineDllEntryPoint="AlteryxDynamicInput" />
        </Node>
        <Node ToolID="55">
          <GuiSettings Plugin="AlteryxBasePluginsGui.Formula.Formula">
            <Position x="1890" y="1074" />
          </GuiSettings>
          <Properties>
            <Configuration>
              <FormulaFields>
                <FormulaField expression="Substring([FileName],8,6)" field="DateRef" size="2147483647" type="V_WString" />
                <FormulaField expression="'73760_' + [DateRef] + '_DFLUXO.CETIP21'" field="NewFile" size="1073741823" type="V_WString" />
                <FormulaField expression="'I:\Confirmation\Derivativos\Vernacci\ARQUIVOS CETIP\Arquivos Posiçao\20' + Left([DateRef], 2) + '\' + Substring([DateRef],2,2)" field="NewPath" size="1073741823" type="V_WString" />
                <FormulaField expression="[NewPath] + '\' + [NewFile]" field="CompletePath" size="1073741823" type="V_WString" />
              </FormulaFields>
            </Configuration>
            <Annotation DisplayMode="0">
              <Name />
              <AnnotationText>Define output folder</AnnotationText>
              <DefaultAnnotationText>DateRef = Substring([FileName],8,6)
NewFile = '73760_' + [DateRef] + '_DFLUXO.CE...</DefaultAnnotationText>
              <Left value="False" />
            </Annotation>
          </Properties>
          <EngineSettings EngineDll="AlteryxBasePluginsEngine.dll" EngineDllEntryPoint="AlteryxFormula" />
        </Node>
        <Node ToolID="56">
          <GuiSettings Plugin="AlteryxBasePluginsGui.AlteryxSelect.AlteryxSelect">
            <Position x="2082" y="1074" />
          </GuiSettings>
          <Properties>
            <Configuration>
              <OrderChanged value="False" />
              <CommaDecimal value="False" />
              <SelectFields>
                <SelectField field="Field_1" selected="True" />
                <SelectField field="CompletePath" selected="True" />
                <SelectField field="*Unknown" selected="False" />
              </SelectFields>
            </Configuration>
            <Annotation DisplayMode="0">
              <Name />
              <DefaultAnnotationText />
              <Left value="False" />
            </Annotation>
          </Properties>
          <EngineSettings EngineDll="AlteryxBasePluginsEngine.dll" EngineDllEntryPoint="AlteryxSelect" />
        </Node>
        <Node ToolID="57">
          <GuiSettings Plugin="AlteryxBasePluginsGui.DbFileOutput.DbFileOutput">
            <Position x="2274" y="1074" />
          </GuiSettings>
          <Properties>
            <Configuration>
              <File MaxRecords="" FileFormat="0">I:\Confirmation\Derivativos\Vernacci\ARQUIVOS CETIP\Arquivos Posiçao\testeAlteryx\Example.txt</File>
              <Passwords />
              <FormatSpecificOptions>
                <LineEndStyle>CRLF</LineEndStyle>
                <Delimeter>\0</Delimeter>
                <ForceQuotes>False</ForceQuotes>
                <HeaderRow>False</HeaderRow>
                <CodePage>28591</CodePage>
                <WriteBOM>True</WriteBOM>
              </FormatSpecificOptions>
              <MultiFile value="True" />
              <MultiFileType>Path</MultiFileType>
              <MultiFileField>CompletePath</MultiFileField>
              <KeepField value="False" />
            </Configuration>
            <Annotation DisplayMode="0">
              <Name />
              <DefaultAnnotationText>Example.txt</DefaultAnnotationText>
              <Left value="False" />
            </Annotation>
          </Properties>
          <EngineSettings EngineDll="AlteryxBasePluginsEngine.dll" EngineDllEntryPoint="AlteryxDbFileOutput" />
        </Node>
        <Node ToolID="58">
          <GuiSettings Plugin="AlteryxBasePluginsGui.Filter.Filter">
            <Position x="714" y="858" />
          </GuiSettings>
          <Properties>
            <Configuration>
              <Expression>Contains([FileName],"_DOPERACOES.txt")</Expression>
              <Mode>Custom</Mode>
            </Configuration>
            <Annotation DisplayMode="0">
              <Name />
              <DefaultAnnotationText>Contains([FileName],"_DOPERACOES.txt")</DefaultAnnotationText>
              <Left value="False" />
            </Annotation>
          </Properties>
          <EngineSettings EngineDll="AlteryxBasePluginsEngine.dll" EngineDllEntryPoint="AlteryxFilter" />
        </Node>
        <Node ToolID="59">
          <GuiSettings Plugin="AlteryxBasePluginsGui.DynamicInput.DynamicInput">
            <Position x="1674" y="846" />
          </GuiSettings>
          <Properties>
            <Configuration>
              <InputConfiguration>
                <Configuration>
                  <Passwords />
                  <File RecordLimit="" SearchSubDirs="False" FileFormat="0" OutputFileName="FileName">I:\Confirmation\Derivativos\Vernacci\ARQUIVOS CETIP\Arquivos Posiçao\2019\06\73760_190614_DPOSICAO.CETIP21</File>
                  <FormatSpecificOptions>
                    <HeaderRow>False</HeaderRow>
                    <IgnoreErrors>False</IgnoreErrors>
                    <AllowShareWrite>False</AllowShareWrite>
                    <ImportLine>1</ImportLine>
                    <FieldLen>9999999</FieldLen>
                    <SingleThreadRead>False</SingleThreadRead>
                    <IgnoreQuotes>DoubleQuotes</IgnoreQuotes>
                    <Delimeter>\0</Delimeter>
                    <QuoteRecordBreak>False</QuoteRecordBreak>
                    <CodePage>28591</CodePage>
                  </FormatSpecificOptions>
                </Configuration>
              </InputConfiguration>
              <Mode>ReadList</Mode>
              <ReadList_Field>FullPath</ReadList_Field>
              <ReadList_Type>Path</ReadList_Type>
              <ErrorBehaviour>Warning</ErrorBehaviour>
            </Configuration>
            <Annotation DisplayMode="0">
              <Name />
              <DefaultAnnotationText />
              <Left value="False" />
            </Annotation>
          </Properties>
          <EngineSettings EngineDll="AlteryxBasePluginsEngine.dll" EngineDllEntryPoint="AlteryxDynamicInput" />
        </Node>
        <Node ToolID="60">
          <GuiSettings Plugin="AlteryxBasePluginsGui.Formula.Formula">
            <Position x="1866" y="846" />
          </GuiSettings>
          <Properties>
            <Configuration>
              <FormulaFields>
                <FormulaField expression="Substring([FileName],8,6)" field="DateRef" size="2147483647" type="V_WString" />
                <FormulaField expression="'73760_' + [DateRef] + '_DOPERACOES.CETIP21'" field="NewFile" size="1073741823" type="V_WString" />
                <FormulaField expression="'I:\Confirmation\Derivativos\Vernacci\ARQUIVOS CETIP\Arquivos Posiçao\20' + Left([DateRef], 2) + '\' + Substring([DateRef],2,2)" field="NewPath" size="1073741823" type="V_WString" />
                <FormulaField expression="[NewPath] + '\' + [NewFile]" field="CompletePath" size="1073741823" type="V_WString" />
              </FormulaFields>
            </Configuration>
            <Annotation DisplayMode="0">
              <Name />
              <AnnotationText>Define output folder</AnnotationText>
              <DefaultAnnotationText>DateRef = Substring([FileName],8,6)
NewFile = '73760_' + [DateRef] + '_DOPERACOE...</DefaultAnnotationText>
              <Left value="False" />
            </Annotation>
          </Properties>
          <EngineSettings EngineDll="AlteryxBasePluginsEngine.dll" EngineDllEntryPoint="AlteryxFormula" />
        </Node>
        <Node ToolID="61">
          <GuiSettings Plugin="AlteryxBasePluginsGui.AlteryxSelect.AlteryxSelect">
            <Position x="2058" y="846" />
          </GuiSettings>
          <Properties>
            <Configuration>
              <OrderChanged value="False" />
              <CommaDecimal value="False" />
              <SelectFields>
                <SelectField field="Field_1" selected="True" />
                <SelectField field="CompletePath" selected="True" />
                <SelectField field="*Unknown" selected="False" />
              </SelectFields>
            </Configuration>
            <Annotation DisplayMode="0">
              <Name />
              <DefaultAnnotationText />
              <Left value="False" />
            </Annotation>
          </Properties>
          <EngineSettings EngineDll="AlteryxBasePluginsEngine.dll" EngineDllEntryPoint="AlteryxSelect" />
        </Node>
        <Node ToolID="62">
          <GuiSettings Plugin="AlteryxBasePluginsGui.DbFileOutput.DbFileOutput">
            <Position x="2250" y="846" />
          </GuiSettings>
          <Properties>
            <Configuration>
              <File MaxRecords="" FileFormat="0">I:\Confirmation\Derivativos\Vernacci\ARQUIVOS CETIP\Arquivos Posiçao\testeAlteryx\Example.txt</File>
              <Passwords />
              <FormatSpecificOptions>
                <LineEndStyle>CRLF</LineEndStyle>
                <Delimeter>\0</Delimeter>
                <ForceQuotes>False</ForceQuotes>
                <HeaderRow>False</HeaderRow>
                <CodePage>28591</CodePage>
                <WriteBOM>True</WriteBOM>
              </FormatSpecificOptions>
              <MultiFile value="True" />
              <MultiFileType>Path</MultiFileType>
              <MultiFileField>CompletePath</MultiFileField>
              <KeepField value="False" />
            </Configuration>
            <Annotation DisplayMode="0">
              <Name />
              <DefaultAnnotationText>Example.txt</DefaultAnnotationText>
              <Left value="False" />
            </Annotation>
          </Properties>
          <EngineSettings EngineDll="AlteryxBasePluginsEngine.dll" EngineDllEntryPoint="AlteryxDbFileOutput" />
        </Node>
        <Node ToolID="63">
          <GuiSettings Plugin="AlteryxBasePluginsGui.Filter.Filter">
            <Position x="1134" y="1530" />
          </GuiSettings>
          <Properties>
            <Configuration>
              <Expression>Contains([FileName],"_DRESUMOEMISSOR-COE.txt")</Expression>
              <Mode>Custom</Mode>
            </Configuration>
            <Annotation DisplayMode="0">
              <Name />
              <DefaultAnnotationText>Contains([FileName],"_DRESUMOEMISSOR-COE.txt")</DefaultAnnotationText>
              <Left value="False" />
            </Annotation>
          </Properties>
          <EngineSettings EngineDll="AlteryxBasePluginsEngine.dll" EngineDllEntryPoint="AlteryxFilter" />
        </Node>
        <Node ToolID="64">
          <GuiSettings Plugin="AlteryxBasePluginsGui.DynamicInput.DynamicInput">
            <Position x="1722" y="1518" />
          </GuiSettings>
          <Properties>
            <Configuration>
              <InputConfiguration>
                <Configuration>
                  <Passwords />
                  <File OutputFileName="FileName" RecordLimit="" SearchSubDirs="False" FileFormat="0">I:\Confirmation\Derivativos\Vernacci\ARQUIVOS CETIP\Arquivos Movimento\OPÇÃO\2019\06\73760_190603_DMOVIMENTO_3.OPCAO</File>
                  <FormatSpecificOptions>
                    <CodePage>28591</CodePage>
                    <Delimeter>\0</Delimeter>
                    <IgnoreErrors>False</IgnoreErrors>
                    <FieldLen>999999</FieldLen>
                    <AllowShareWrite>False</AllowShareWrite>
                    <HeaderRow>False</HeaderRow>
                    <IgnoreQuotes>DoubleQuotes</IgnoreQuotes>
                    <ImportLine>1</ImportLine>
                  </FormatSpecificOptions>
                </Configuration>
              </InputConfiguration>
              <Mode>ReadList</Mode>
              <ReadList_Field>FullPath</ReadList_Field>
              <ReadList_Type>Path</ReadList_Type>
            </Configuration>
            <Annotation DisplayMode="0">
              <Name />
              <DefaultAnnotationText />
              <Left value="False" />
            </Annotation>
          </Properties>
          <EngineSettings EngineDll="AlteryxBasePluginsEngine.dll" EngineDllEntryPoint="AlteryxDynamicInput" />
        </Node>
        <Node ToolID="65">
          <GuiSettings Plugin="AlteryxBasePluginsGui.Formula.Formula">
            <Position x="1914" y="1518" />
          </GuiSettings>
          <Properties>
            <Configuration>
              <FormulaFields>
                <FormulaField expression="Substring([FileName],8,6)" field="DateRef" size="2147483647" type="V_WString" />
                <FormulaField expression="'CETIP21_' + [DateRef] + '_SP_DRESUMOEMISSOR-COE.TXT'" field="NewFile" size="1073741823" type="V_WString" />
                <FormulaField expression="'I:\Confirmation\Derivativos\Vernacci\ARQUIVOS CETIP\Arquivos Movimento\COE\20' + Left([DateRef], 2) + '\' + Substring([DateRef],2,2)" field="NewPath" size="1073741823" type="V_WString" />
                <FormulaField expression="[NewPath] + '\' + [NewFile]" field="CompletePath" size="1073741823" type="V_WString" />
              </FormulaFields>
            </Configuration>
            <Annotation DisplayMode="0">
              <Name />
              <AnnotationText>Define output folder</AnnotationText>
              <DefaultAnnotationText>DateRef = Substring([FileName],8,6)
NewFile = 'CETIP21_' + [DateRef] + '_SP_DRES...</DefaultAnnotationText>
              <Left value="False" />
            </Annotation>
          </Properties>
          <EngineSettings EngineDll="AlteryxBasePluginsEngine.dll" EngineDllEntryPoint="AlteryxFormula" />
        </Node>
        <Node ToolID="66">
          <GuiSettings Plugin="AlteryxBasePluginsGui.AlteryxSelect.AlteryxSelect">
            <Position x="2106" y="1518" />
          </GuiSettings>
          <Properties>
            <Configuration>
              <OrderChanged value="False" />
              <CommaDecimal value="False" />
              <SelectFields>
                <SelectField field="Field_1" selected="True" />
                <SelectField field="CompletePath" selected="True" />
                <SelectField field="*Unknown" selected="False" />
              </SelectFields>
            </Configuration>
            <Annotation DisplayMode="0">
              <Name />
              <DefaultAnnotationText />
              <Left value="False" />
            </Annotation>
          </Properties>
          <EngineSettings EngineDll="AlteryxBasePluginsEngine.dll" EngineDllEntryPoint="AlteryxSelect" />
        </Node>
        <Node ToolID="67">
          <GuiSettings Plugin="AlteryxBasePluginsGui.DbFileOutput.DbFileOutput">
            <Position x="2298" y="1518" />
          </GuiSettings>
          <Properties>
            <Configuration>
              <File MaxRecords="" FileFormat="0">I:\Confirmation\Derivativos\Vernacci\ARQUIVOS CETIP\Arquivos Posiçao\testeAlteryx\Example.txt</File>
              <Passwords />
              <FormatSpecificOptions>
                <LineEndStyle>CRLF</LineEndStyle>
                <Delimeter>\0</Delimeter>
                <ForceQuotes>False</ForceQuotes>
                <HeaderRow>False</HeaderRow>
                <CodePage>28591</CodePage>
                <WriteBOM>True</WriteBOM>
              </FormatSpecificOptions>
              <MultiFile value="True" />
              <MultiFileType>Path</MultiFileType>
              <MultiFileField>CompletePath</MultiFileField>
              <KeepField value="False" />
            </Configuration>
            <Annotation DisplayMode="0">
              <Name />
              <DefaultAnnotationText>Example.txt</DefaultAnnotationText>
              <Left value="False" />
            </Annotation>
          </Properties>
          <EngineSettings EngineDll="AlteryxBasePluginsEngine.dll" EngineDllEntryPoint="AlteryxDbFileOutput" />
        </Node>
        <Node ToolID="75">
          <GuiSettings Plugin="AlteryxBasePluginsGui.Formula.Formula">
            <Position x="1890" y="1290" />
          </GuiSettings>
          <Properties>
            <Configuration>
              <FormulaFields>
                <FormulaField expression="Substring([FileName],6,6)" field="DateRef" size="2147483647" type="V_WString" />
                <FormulaField expression="'73760_' + [DateRef] + '_DPOSICAO.OPCAO'" field="NewFile" size="1073741823" type="V_WString" />
                <FormulaField expression="'\\nawest.ad.jpmorganchase.com\lac\BRA\intra\CETIP_OPTIONS' //+ Left([DateRef], 2) + '\' + Substring([DateRef],2,2)" field="NewPath" size="1073741823" type="V_WString" />
                <FormulaField expression="[NewPath] + '\' + [NewFile]" field="CompletePath" size="1073741823" type="V_WString" />
              </FormulaFields>
            </Configuration>
            <Annotation DisplayMode="0">
              <Name />
              <AnnotationText>Define output folder</AnnotationText>
              <DefaultAnnotationText>DateRef = Substring([FileName],6,6)
NewFile = '73760_' + [DateRef] + '_DPOSICAO....</DefaultAnnotationText>
              <Left value="False" />
            </Annotation>
          </Properties>
          <EngineSettings EngineDll="AlteryxBasePluginsEngine.dll" EngineDllEntryPoint="AlteryxFormula" />
        </Node>
        <Node ToolID="76">
          <GuiSettings Plugin="AlteryxBasePluginsGui.AlteryxSelect.AlteryxSelect">
            <Position x="2082" y="1290" />
          </GuiSettings>
          <Properties>
            <Configuration>
              <OrderChanged value="False" />
              <CommaDecimal value="False" />
              <SelectFields>
                <SelectField field="Field_1" selected="True" />
                <SelectField field="CompletePath" selected="True" />
                <SelectField field="*Unknown" selected="False" />
              </SelectFields>
            </Configuration>
            <Annotation DisplayMode="0">
              <Name />
              <DefaultAnnotationText />
              <Left value="False" />
            </Annotation>
          </Properties>
          <EngineSettings EngineDll="AlteryxBasePluginsEngine.dll" EngineDllEntryPoint="AlteryxSelect" />
        </Node>
        <Node ToolID="77">
          <GuiSettings Plugin="AlteryxBasePluginsGui.DbFileOutput.DbFileOutput">
            <Position x="2274" y="1290" />
          </GuiSettings>
          <Properties>
            <Configuration>
              <File MaxRecords="" FileFormat="0">I:\Confirmation\Derivativos\Vernacci\ARQUIVOS CETIP\Arquivos Posiçao\testeAlteryx\Example.txt</File>
              <Passwords />
              <Disable>False</Disable>
              <FormatSpecificOptions>
                <LineEndStyle>CRLF</LineEndStyle>
                <Delimeter>\0</Delimeter>
                <ForceQuotes>False</ForceQuotes>
                <HeaderRow>False</HeaderRow>
                <CodePage>28591</CodePage>
                <WriteBOM>True</WriteBOM>
              </FormatSpecificOptions>
              <MultiFile value="True" />
              <MultiFileType>Path</MultiFileType>
              <MultiFileField>CompletePath</MultiFileField>
              <KeepField value="False" />
            </Configuration>
            <Annotation DisplayMode="0">
              <Name />
              <DefaultAnnotationText>Example.txt</DefaultAnnotationText>
              <Left value="False" />
            </Annotation>
          </Properties>
          <EngineSettings EngineDll="AlteryxBasePluginsEngine.dll" EngineDllEntryPoint="AlteryxDbFileOutput" />
        </Node>
        <Node ToolID="78">
          <GuiSettings Plugin="AlteryxBasePluginsGui.DynamicInput.DynamicInput">
            <Position x="1698" y="1290" />
          </GuiSettings>
          <Properties>
            <Configuration>
              <InputConfiguration>
                <Configuration>
                  <Passwords />
                  <File RecordLimit="" SearchSubDirs="False" FileFormat="0" OutputFileName="FileName">I:\Confirmation\Derivativos\Vernacci\ARQUIVOS CETIP\Arquivos Posiçao\2019\06\73760_190614_DPOSICAO.CETIP21</File>
                  <FormatSpecificOptions>
                    <HeaderRow>False</HeaderRow>
                    <IgnoreErrors>False</IgnoreErrors>
                    <AllowShareWrite>False</AllowShareWrite>
                    <ImportLine>1</ImportLine>
                    <FieldLen>9999999</FieldLen>
                    <SingleThreadRead>False</SingleThreadRead>
                    <IgnoreQuotes>DoubleQuotes</IgnoreQuotes>
                    <Delimeter>\0</Delimeter>
                    <QuoteRecordBreak>False</QuoteRecordBreak>
                    <CodePage>28591</CodePage>
                  </FormatSpecificOptions>
                </Configuration>
              </InputConfiguration>
              <Mode>ReadList</Mode>
              <ReadList_Field>FullPath</ReadList_Field>
              <ReadList_Type>Path</ReadList_Type>
            </Configuration>
            <Annotation DisplayMode="0">
              <Name />
              <DefaultAnnotationText />
              <Left value="False" />
            </Annotation>
          </Properties>
          <EngineSettings EngineDll="AlteryxBasePluginsEngine.dll" EngineDllEntryPoint="AlteryxDynamicInput" />
        </Node>
        <Node ToolID="79">
          <GuiSettings Plugin="AlteryxBasePluginsGui.Filter.Filter">
            <Position x="1398" y="1926" />
          </GuiSettings>
          <Properties>
            <Configuration>
              <Expression>Contains([FileName],"_MID_DAGENTEACELERADOR.txt")</Expression>
              <Mode>Custom</Mode>
            </Configuration>
            <Annotation DisplayMode="0">
              <Name />
              <DefaultAnnotationText>Contains([FileName],"_MID_DAGENTEACELERADOR.txt")</DefaultAnnotationText>
              <Left value="False" />
            </Annotation>
          </Properties>
          <EngineSettings EngineDll="AlteryxBasePluginsEngine.dll" EngineDllEntryPoint="AlteryxFilter" />
        </Node>
        <Node ToolID="80">
          <GuiSettings Plugin="AlteryxBasePluginsGui.DynamicInput.DynamicInput">
            <Position x="1734" y="1914" />
          </GuiSettings>
          <Properties>
            <Configuration>
              <InputConfiguration>
                <Configuration>
                  <Passwords />
                  <File RecordLimit="" SearchSubDirs="False" FileFormat="0" OutputFileName="FileName">I:\Confirmation\Derivativos\Vernacci\ARQUIVOS CETIP\Arquivos Movimento\SWAP\2019\06\73760_190612_DMOVIMENTO-SWAP.CETIP21</File>
                  <FormatSpecificOptions>
                    <HeaderRow>False</HeaderRow>
                    <IgnoreErrors>False</IgnoreErrors>
                    <AllowShareWrite>False</AllowShareWrite>
                    <ImportLine>1</ImportLine>
                    <FieldLen>999999</FieldLen>
                    <SingleThreadRead>False</SingleThreadRead>
                    <IgnoreQuotes>DoubleQuotes</IgnoreQuotes>
                    <Delimeter>\0</Delimeter>
                    <QuoteRecordBreak>False</QuoteRecordBreak>
                    <CodePage>28591</CodePage>
                  </FormatSpecificOptions>
                </Configuration>
              </InputConfiguration>
              <Mode>ReadList</Mode>
              <ReadList_Field>FullPath</ReadList_Field>
              <ReadList_Type>Path</ReadList_Type>
            </Configuration>
            <Annotation DisplayMode="0">
              <Name />
              <DefaultAnnotationText />
              <Left value="False" />
            </Annotation>
          </Properties>
          <EngineSettings EngineDll="AlteryxBasePluginsEngine.dll" EngineDllEntryPoint="AlteryxDynamicInput" />
        </Node>
        <Node ToolID="81">
          <GuiSettings Plugin="AlteryxBasePluginsGui.DbFileOutput.DbFileOutput">
            <Position x="2310" y="1914" />
          </GuiSettings>
          <Properties>
            <Configuration>
              <File MaxRecords="" FileFormat="0">I:\Confirmation\Derivativos\Vernacci\ARQUIVOS CETIP\Arquivos Posiçao\testeAlteryx\Example.txt</File>
              <Passwords />
              <FormatSpecificOptions>
                <LineEndStyle>CRLF</LineEndStyle>
                <Delimeter>\0</Delimeter>
                <ForceQuotes>False</ForceQuotes>
                <HeaderRow>False</HeaderRow>
                <CodePage>28591</CodePage>
                <WriteBOM>True</WriteBOM>
              </FormatSpecificOptions>
              <MultiFile value="True" />
              <MultiFileType>Path</MultiFileType>
              <MultiFileField>CompletePath</MultiFileField>
              <KeepField value="False" />
            </Configuration>
            <Annotation DisplayMode="0">
              <Name />
              <DefaultAnnotationText>Example.txt</DefaultAnnotationText>
              <Left value="False" />
            </Annotation>
          </Properties>
          <EngineSettings EngineDll="AlteryxBasePluginsEngine.dll" EngineDllEntryPoint="AlteryxDbFileOutput" />
        </Node>
        <Node ToolID="82">
          <GuiSettings Plugin="AlteryxBasePluginsGui.AlteryxSelect.AlteryxSelect">
            <Position x="2118" y="1914" />
          </GuiSettings>
          <Properties>
            <Configuration>
              <OrderChanged value="False" />
              <CommaDecimal value="False" />
              <SelectFields>
                <SelectField field="Field_1" selected="True" />
                <SelectField field="CompletePath" selected="True" />
                <SelectField field="*Unknown" selected="False" />
              </SelectFields>
            </Configuration>
            <Annotation DisplayMode="0">
              <Name />
              <DefaultAnnotationText />
              <Left value="False" />
            </Annotation>
          </Properties>
          <EngineSettings EngineDll="AlteryxBasePluginsEngine.dll" EngineDllEntryPoint="AlteryxSelect" />
        </Node>
        <Node ToolID="83">
          <GuiSettings Plugin="AlteryxBasePluginsGui.Formula.Formula">
            <Position x="1926" y="1914" />
          </GuiSettings>
          <Properties>
            <Configuration>
              <FormulaFields>
                <FormulaField expression="Substring([FileName],8,6)" field="DateRef" size="2147483647" type="V_WString" />
                <FormulaField expression="'73760_' + [DateRef] + '_MID_DAGENTEACELERADOR.CETIP21'" field="NewFile" size="1073741823" type="V_WString" />
                <FormulaField expression="'I:\Confirmation\Derivativos\Vernacci\ARQUIVOS CETIP\Arquivos Posiçao\20' + Left([DateRef], 2) + '\' + Substring([DateRef],2,2)" field="NewPath" size="1073741823" type="V_WString" />
                <FormulaField expression="[NewPath] + '\' + [NewFile]" field="CompletePath" size="1073741823" type="V_WString" />
              </FormulaFields>
            </Configuration>
            <Annotation DisplayMode="0">
              <Name />
              <AnnotationText>Define output folder</AnnotationText>
              <DefaultAnnotationText>DateRef = Substring([FileName],8,6)
NewFile = '73760_' + [DateRef] + '_MID_DAGEN...</DefaultAnnotationText>
              <Left value="False" />
            </Annotation>
          </Properties>
          <EngineSettings EngineDll="AlteryxBasePluginsEngine.dll" EngineDllEntryPoint="AlteryxFormula" />
        </Node>
        <Node ToolID="93">
          <GuiSettings Plugin="AlteryxBasePluginsGui.DynamicInput.DynamicInput">
            <Position x="1746" y="2058" />
          </GuiSettings>
          <Properties>
            <Configuration>
              <InputConfiguration>
                <Configuration>
                  <Passwords />
                  <File RecordLimit="" SearchSubDirs="False" FileFormat="0" OutputFileName="FileName">\\cdexmccxafpd03p.svr.us.jpmchase.net\ib_commod_pyrecs_prd$\Sourcefiles\Pyrecs\BrazilCommodities\PRD\NDF\73760_190807_DPOSICAO.CETIP21</File>
                  <FormatSpecificOptions>
                    <HeaderRow>False</HeaderRow>
                    <IgnoreErrors>False</IgnoreErrors>
                    <AllowShareWrite>False</AllowShareWrite>
                    <ImportLine>1</ImportLine>
                    <FieldLen>9999999</FieldLen>
                    <SingleThreadRead>False</SingleThreadRead>
                    <IgnoreQuotes>DoubleQuotes</IgnoreQuotes>
                    <Delimeter>\0</Delimeter>
                    <QuoteRecordBreak>False</QuoteRecordBreak>
                    <CodePage>28591</CodePage>
                  </FormatSpecificOptions>
                </Configuration>
              </InputConfiguration>
              <Mode>ReadList</Mode>
              <ReadList_Field>FullPath</ReadList_Field>
              <ReadList_Type>Path</ReadList_Type>
              <ErrorBehaviour>Warning</ErrorBehaviour>
            </Configuration>
            <Annotation DisplayMode="0">
              <Name />
              <DefaultAnnotationText />
              <Left value="False" />
            </Annotation>
          </Properties>
          <EngineSettings EngineDll="AlteryxBasePluginsEngine.dll" EngineDllEntryPoint="AlteryxDynamicInput" />
        </Node>
        <Node ToolID="94">
          <GuiSettings Plugin="AlteryxBasePluginsGui.AlteryxSelect.AlteryxSelect">
            <Position x="2130" y="2058" />
          </GuiSettings>
          <Properties>
            <Configuration>
              <OrderChanged value="False" />
              <CommaDecimal value="False" />
              <SelectFields>
                <SelectField field="Field_1" selected="True" />
                <SelectField field="CompletePath" selected="True" />
                <SelectField field="*Unknown" selected="False" />
              </SelectFields>
            </Configuration>
            <Annotation DisplayMode="0">
              <Name />
              <DefaultAnnotationText />
              <Left value="False" />
            </Annotation>
          </Properties>
          <EngineSettings EngineDll="AlteryxBasePluginsEngine.dll" EngineDllEntryPoint="AlteryxSelect" />
        </Node>
        <Node ToolID="95">
          <GuiSettings Plugin="AlteryxBasePluginsGui.Formula.Formula">
            <Position x="1938" y="2058" />
          </GuiSettings>
          <Properties>
            <Configuration>
              <FormulaFields>
                <FormulaField expression="Substring([FileName],4,6)" field="DateRef" size="2147483647" type="V_WString" />
                <FormulaField expression="'73760_' + [DateRef] + '_DPOSICAO-TER.TER'" field="NewFile" size="1073741823" type="V_WString" />
                <FormulaField expression="'\\nawest.ad.jpmorganchase.com\lac\BRA\intra\CETIP_NDF' //+ Left([DateRef], 2) + '\' + Substring([DateRef],2,2)" field="NewPath" size="1073741823" type="V_WString" />
                <FormulaField expression="[NewPath] + '\' + [NewFile]" field="CompletePath" size="1073741823" type="V_WString" />
              </FormulaFields>
            </Configuration>
            <Annotation DisplayMode="0">
              <Name />
              <AnnotationText>Define output folder</AnnotationText>
              <DefaultAnnotationText>DateRef = Substring([FileName],4,6)
NewFile = '73760_' + [DateRef] + '_DPOSICAO-...</DefaultAnnotationText>
              <Left value="False" />
            </Annotation>
          </Properties>
          <EngineSettings EngineDll="AlteryxBasePluginsEngine.dll" EngineDllEntryPoint="AlteryxFormula" />
        </Node>
        <Node ToolID="96">
          <GuiSettings Plugin="AlteryxBasePluginsGui.DbFileOutput.DbFileOutput">
            <Position x="2322" y="2058" />
          </GuiSettings>
          <Properties>
            <Configuration>
              <File MaxRecords="" FileFormat="0">I:\Confirmation\Derivativos\Vernacci\ARQUIVOS CETIP\Arquivos Posiçao\2019\08\73760_190801_DPOSICAO.CETIP21</File>
              <Passwords />
              <Disable>False</Disable>
              <FormatSpecificOptions>
                <LineEndStyle>CRLF</LineEndStyle>
                <Delimeter>\0</Delimeter>
                <ForceQuotes>False</ForceQuotes>
                <HeaderRow>False</HeaderRow>
                <CodePage>28591</CodePage>
                <WriteBOM>True</WriteBOM>
              </FormatSpecificOptions>
              <MultiFile value="True" />
              <MultiFileType>Path</MultiFileType>
              <MultiFileField>CompletePath</MultiFileField>
              <KeepField value="False" />
            </Configuration>
            <Annotation DisplayMode="0">
              <Name />
              <DefaultAnnotationText>73760_190801_DPOSICAO.CETIP21</DefaultAnnotationText>
              <Left value="False" />
            </Annotation>
          </Properties>
          <EngineSettings EngineDll="AlteryxBasePluginsEngine.dll" EngineDllEntryPoint="AlteryxDbFileOutput" />
        </Node>
        <Node ToolID="97">
          <GuiSettings Plugin="AlteryxBasePluginsGui.Filter.Filter">
            <Position x="1482" y="2070" />
          </GuiSettings>
          <Properties>
            <Configuration>
              <Expression>Contains([FileName],"_DPOSICAO-TER.TXT")</Expression>
              <Mode>Custom</Mode>
            </Configuration>
            <Annotation DisplayMode="0">
              <Name />
              <DefaultAnnotationText>Contains([FileName],"_DPOSICAO-TER.TXT")</DefaultAnnotationText>
              <Left value="False" />
            </Annotation>
          </Properties>
          <EngineSettings EngineDll="AlteryxBasePluginsEngine.dll" EngineDllEntryPoint="AlteryxFilter" />
        </Node>
        <Node ToolID="98">
          <GuiSettings Plugin="AlteryxBasePluginsGui.DynamicInput.DynamicInput">
            <Position x="1746" y="2214" />
          </GuiSettings>
          <Properties>
            <Configuration>
              <InputConfiguration>
                <Configuration>
                  <Passwords />
                  <File RecordLimit="" SearchSubDirs="False" FileFormat="0" OutputFileName="FileName">I:\Confirmation\Derivativos\Vernacci\ARQUIVOS CETIP\Batch Conecta\2023\10. October\24\TER_231024_DPOSICAO-TER.txt</File>
                  <FormatSpecificOptions>
                    <HeaderRow>False</HeaderRow>
                    <IgnoreErrors>False</IgnoreErrors>
                    <AllowShareWrite>False</AllowShareWrite>
                    <ImportLine>1</ImportLine>
                    <FieldLen>9999999</FieldLen>
                    <SingleThreadRead>False</SingleThreadRead>
                    <IgnoreQuotes>DoubleQuotes</IgnoreQuotes>
                    <Delimeter>\0</Delimeter>
                    <QuoteRecordBreak>False</QuoteRecordBreak>
                    <CodePage>28591</CodePage>
                  </FormatSpecificOptions>
                </Configuration>
              </InputConfiguration>
              <Mode>ReadList</Mode>
              <ReadList_Field>FullPath</ReadList_Field>
              <ReadList_Type>Path</ReadList_Type>
            </Configuration>
            <Annotation DisplayMode="0">
              <Name />
              <DefaultAnnotationText />
              <Left value="False" />
            </Annotation>
          </Properties>
          <EngineSettings EngineDll="AlteryxBasePluginsEngine.dll" EngineDllEntryPoint="AlteryxDynamicInput" />
        </Node>
        <Node ToolID="99">
          <GuiSettings Plugin="AlteryxBasePluginsGui.AlteryxSelect.AlteryxSelect">
            <Position x="2130" y="2214" />
          </GuiSettings>
          <Properties>
            <Configuration>
              <OrderChanged value="False" />
              <CommaDecimal value="False" />
              <SelectFields>
                <SelectField field="Field_1" selected="True" />
                <SelectField field="CompletePath" selected="True" />
                <SelectField field="*Unknown" selected="False" />
              </SelectFields>
            </Configuration>
            <Annotation DisplayMode="0">
              <Name />
              <DefaultAnnotationText />
              <Left value="False" />
            </Annotation>
          </Properties>
          <EngineSettings EngineDll="AlteryxBasePluginsEngine.dll" EngineDllEntryPoint="AlteryxSelect" />
        </Node>
        <Node ToolID="100">
          <GuiSettings Plugin="AlteryxBasePluginsGui.Formula.Formula">
            <Position x="1938" y="2214" />
          </GuiSettings>
          <Properties>
            <Configuration>
              <FormulaFields>
                <FormulaField expression="Substring([FileName],4,6)&#xA;" field="DateRef" size="2147483647" type="V_WString" />
                <FormulaField expression="'73760_' + [DateRef] + '_DPOSICAO-TER.TER'" field="NewFile" size="1073741823" type="V_WString" />
                <FormulaField expression="'I:\Confirmation\Derivativos\Vernacci\ARQUIVOS CETIP\Arquivos Posiçao\' + '20' + Left([DateRef], 2) + '\' + Substring([DateRef],2,2)" field="NewPath" size="1073741823" type="V_WString" />
                <FormulaField expression="[NewPath] + '\' + [NewFile]" field="CompletePath" size="1073741823" type="V_WString" />
              </FormulaFields>
            </Configuration>
            <Annotation DisplayMode="0">
              <Name />
              <AnnotationText>Define output folder</AnnotationText>
              <DefaultAnnotationText>DateRef = Substring([FileName],4,6)

NewFile = '73760_' + [DateRef] + '_DPOSICAO...</DefaultAnnotationText>
              <Left value="False" />
            </Annotation>
          </Properties>
          <EngineSettings EngineDll="AlteryxBasePluginsEngine.dll" EngineDllEntryPoint="AlteryxFormula" />
        </Node>
        <Node ToolID="101">
          <GuiSettings Plugin="AlteryxBasePluginsGui.DbFileOutput.DbFileOutput">
            <Position x="2322" y="2214" />
          </GuiSettings>
          <Properties>
            <Configuration>
              <File MaxRecords="" FileFormat="0">I:\Confirmation\Derivativos\Vernacci\ARQUIVOS CETIP\Arquivos Posiçao\2019\08\73760_190801_DPOSICAO.CETIP21</File>
              <Passwords />
              <FormatSpecificOptions>
                <LineEndStyle>CRLF</LineEndStyle>
                <Delimeter>\0</Delimeter>
                <ForceQuotes>False</ForceQuotes>
                <HeaderRow>False</HeaderRow>
                <CodePage>28591</CodePage>
                <WriteBOM>True</WriteBOM>
              </FormatSpecificOptions>
              <MultiFile value="True" />
              <MultiFileType>Path</MultiFileType>
              <MultiFileField>CompletePath</MultiFileField>
              <KeepField value="False" />
            </Configuration>
            <Annotation DisplayMode="0">
              <Name />
              <DefaultAnnotationText>73760_190801_DPOSICAO.CETIP21</DefaultAnnotationText>
              <Left value="False" />
            </Annotation>
          </Properties>
          <EngineSettings EngineDll="AlteryxBasePluginsEngine.dll" EngineDllEntryPoint="AlteryxDbFileOutput" />
        </Node>
        <Node ToolID="112">
          <GuiSettings Plugin="AlteryxBasePluginsGui.DynamicInput.DynamicInput">
            <Position x="1662" y="690" />
          </GuiSettings>
          <Properties>
            <Configuration>
              <InputConfiguration>
                <Configuration>
                  <Passwords />
                  <File RecordLimit="" SearchSubDirs="False" FileFormat="0" OutputFileName="FileName">I:\Confirmation\Derivativos\Vernacci\ARQUIVOS CETIP\Batch Conecta\2023\10. October\23\SIC_231023_DPOSCONTRATOSIC.txt</File>
                  <FormatSpecificOptions>
                    <HeaderRow>False</HeaderRow>
                    <IgnoreErrors>False</IgnoreErrors>
                    <AllowShareWrite>False</AllowShareWrite>
                    <ImportLine>1</ImportLine>
                    <FieldLen>9999999</FieldLen>
                    <SingleThreadRead>False</SingleThreadRead>
                    <IgnoreQuotes>DoubleQuotes</IgnoreQuotes>
                    <Delimeter>\0</Delimeter>
                    <QuoteRecordBreak>False</QuoteRecordBreak>
                    <CodePage>28591</CodePage>
                  </FormatSpecificOptions>
                </Configuration>
              </InputConfiguration>
              <Mode>ReadList</Mode>
              <ReadList_Field>FullPath</ReadList_Field>
              <ReadList_Type>Path</ReadList_Type>
              <ErrorBehaviour>Warning</ErrorBehaviour>
            </Configuration>
            <Annotation DisplayMode="0">
              <Name />
              <DefaultAnnotationText />
              <Left value="False" />
            </Annotation>
          </Properties>
          <EngineSettings EngineDll="AlteryxBasePluginsEngine.dll" EngineDllEntryPoint="AlteryxDynamicInput" />
        </Node>
        <Node ToolID="113">
          <GuiSettings Plugin="AlteryxBasePluginsGui.AlteryxSelect.AlteryxSelect">
            <Position x="2046" y="690" />
          </GuiSettings>
          <Properties>
            <Configuration>
              <OrderChanged value="False" />
              <CommaDecimal value="False" />
              <SelectFields>
                <SelectField field="Field_1" selected="True" />
                <SelectField field="CompletePath" selected="True" />
                <SelectField field="*Unknown" selected="False" />
              </SelectFields>
            </Configuration>
            <Annotation DisplayMode="0">
              <Name />
              <DefaultAnnotationText />
              <Left value="False" />
            </Annotation>
          </Properties>
          <EngineSettings EngineDll="AlteryxBasePluginsEngine.dll" EngineDllEntryPoint="AlteryxSelect" />
        </Node>
        <Node ToolID="114">
          <GuiSettings Plugin="AlteryxBasePluginsGui.Formula.Formula">
            <Position x="1854" y="690" />
          </GuiSettings>
          <Properties>
            <Configuration>
              <FormulaFields>
                <FormulaField expression="Substring([FileName],4,6)&#xA;" field="DateRef" size="2147483647" type="V_WString" />
                <FormulaField expression="'73760_' + [DateRef] + '_DPOSCONTRATOSIC.txt'" field="NewFile" size="1073741823" type="V_WString" />
                <FormulaField expression="'I:\Confirmation\Derivativos\Vernacci\ARQUIVOS CETIP\Arquivos Posiçao\' + '20' + Left([DateRef], 2) + '\' + Substring([DateRef],2,2)" field="NewPath" size="1073741823" type="V_WString" />
                <FormulaField expression="[NewPath] + '\' + [NewFile]" field="CompletePath" size="1073741823" type="V_WString" />
              </FormulaFields>
            </Configuration>
            <Annotation DisplayMode="0">
              <Name />
              <AnnotationText>Define output folder</AnnotationText>
              <DefaultAnnotationText>DateRef = Substring([FileName],4,6)

NewFile = '73760_' + [DateRef] + '_DPOSCONT...</DefaultAnnotationText>
              <Left value="False" />
            </Annotation>
          </Properties>
          <EngineSettings EngineDll="AlteryxBasePluginsEngine.dll" EngineDllEntryPoint="AlteryxFormula" />
        </Node>
        <Node ToolID="115">
          <GuiSettings Plugin="AlteryxBasePluginsGui.DbFileOutput.DbFileOutput">
            <Position x="2238" y="690" />
          </GuiSettings>
          <Properties>
            <Configuration>
              <File MaxRecords="" FileFormat="0">I:\Confirmation\Derivativos\Vernacci\ARQUIVOS CETIP\Arquivos Posiçao\2019\08\73760_190801_DPOSICAO.CETIP21</File>
              <Passwords />
              <Disable>False</Disable>
              <FormatSpecificOptions>
                <LineEndStyle>CRLF</LineEndStyle>
                <Delimeter>\0</Delimeter>
                <ForceQuotes>False</ForceQuotes>
                <HeaderRow>False</HeaderRow>
                <CodePage>28591</CodePage>
                <WriteBOM>True</WriteBOM>
              </FormatSpecificOptions>
              <MultiFile value="True" />
              <MultiFileType>Path</MultiFileType>
              <MultiFileField>CompletePath</MultiFileField>
              <KeepField value="False" />
            </Configuration>
            <Annotation DisplayMode="0">
              <Name />
              <DefaultAnnotationText>73760_190801_DPOSICAO.CETIP21</DefaultAnnotationText>
              <Left value="False" />
            </Annotation>
          </Properties>
          <EngineSettings EngineDll="AlteryxBasePluginsEngine.dll" EngineDllEntryPoint="AlteryxDbFileOutput" />
        </Node>
        <Node ToolID="116">
          <GuiSettings Plugin="AlteryxBasePluginsGui.Filter.Filter">
            <Position x="750" y="702" />
          </GuiSettings>
          <Properties>
            <Configuration>
              <Expression>Contains([FileName],"_DPOSCONTRATOSIC.TXT")</Expression>
              <Mode>Custom</Mode>
            </Configuration>
            <Annotation DisplayMode="0">
              <Name />
              <DefaultAnnotationText>Contains([FileName],"_DPOSCONTRATOSIC.TXT")</DefaultAnnotationText>
              <Left value="False" />
            </Annotation>
          </Properties>
          <EngineSettings EngineDll="AlteryxBasePluginsEngine.dll" EngineDllEntryPoint="AlteryxFilter" />
        </Node>
      </ChildNodes>
    </Node>
    <Node ToolID="117">
      <GuiSettings Plugin="AlteryxGuiToolkit.ToolContainer.ToolContainer">
        <Position x="653" y="77" width="637" height="219" />
      </GuiSettings>
      <Properties>
        <Configuration>
          <Caption>E-mail Sales Support</Caption>
          <Style TextColor="#314c4a" FillColor="#ecf2f2" BorderColor="#314c4a" Transparency="25" Margin="25" />
          <Disabled value="False" />
          <Folded value="False" />
        </Configuration>
        <Annotation DisplayMode="0">
          <Name />
          <AnnotationText>E-mail Sales Support</AnnotationText>
          <DefaultAnnotationText />
          <Left value="False" />
        </Annotation>
      </Properties>
      <ChildNodes>
        <Node ToolID="107">
          <GuiSettings Plugin="AlteryxBasePluginsGui.DynamicInput.DynamicInput">
            <Position x="846" y="138" />
          </GuiSettings>
          <Properties>
            <Configuration>
              <InputConfiguration>
                <Configuration>
                  <Passwords />
                  <File RecordLimit="" SearchSubDirs="False" FileFormat="0" OutputFileName="FileName">I:\Confirmation\Derivativos\Vernacci\ARQUIVOS CETIP\Batch Conecta\2023\10. October\23\SIC_231023_DPOSCONTRATOSIC.txt</File>
                  <FormatSpecificOptions>
                    <HeaderRow>False</HeaderRow>
                    <IgnoreErrors>False</IgnoreErrors>
                    <AllowShareWrite>False</AllowShareWrite>
                    <ImportLine>1</ImportLine>
                    <FieldLen>9999999</FieldLen>
                    <SingleThreadRead>False</SingleThreadRead>
                    <IgnoreQuotes>DoubleQuotes</IgnoreQuotes>
                    <Delimeter>\0</Delimeter>
                    <QuoteRecordBreak>False</QuoteRecordBreak>
                    <CodePage>28591</CodePage>
                  </FormatSpecificOptions>
                </Configuration>
              </InputConfiguration>
              <Mode>ReadList</Mode>
              <ReadList_Field>FullPath</ReadList_Field>
              <ReadList_Type>Path</ReadList_Type>
              <ErrorBehaviour>Warning</ErrorBehaviour>
            </Configuration>
            <Annotation DisplayMode="0">
              <Name />
              <DefaultAnnotationText />
              <Left value="False" />
            </Annotation>
          </Properties>
          <EngineSettings EngineDll="AlteryxBasePluginsEngine.dll" EngineDllEntryPoint="AlteryxDynamicInput" />
        </Node>
        <Node ToolID="108">
          <GuiSettings Plugin="AlteryxBasePluginsGui.Formula.Formula">
            <Position x="966" y="138" />
          </GuiSettings>
          <Properties>
            <Configuration>
              <FormulaFields>
                <FormulaField expression="Substring([FileName],4,6)&#xA;" field="DateRef" size="2147483647" type="V_WString" />
                <FormulaField expression="'73760_' + [DateRef] + '_DPOSCONTRATOSIC.txt'" field="NewFile" size="1073741823" type="V_WString" />
                <FormulaField expression="'I:\Confirmation\Derivativos\Vernacci\ARQUIVOS CETIP\Arquivos Posiçao\' + '20' + Left([DateRef], 2) + '\' + Substring([DateRef],2,2)" field="NewPath" size="1073741823" type="V_WString" />
                <FormulaField expression="[NewPath] + '\' + [NewFile]" field="CompletePath" size="1073741823" type="V_WString" />
                <FormulaField expression="'Consolidado CETIP - Corporate - ' + [DateRef]" field="Subject" size="1073741823" type="V_WString" />
              </FormulaFields>
            </Configuration>
            <Annotation DisplayMode="0">
              <Name />
              <AnnotationText>Define output folder</AnnotationText>
              <DefaultAnnotationText>DateRef = Substring([FileName],4,6)

NewFile = '73760_' + [DateRef] + '_DPOSCONT...</DefaultAnnotationText>
              <Left value="False" />
            </Annotation>
          </Properties>
          <EngineSettings EngineDll="AlteryxBasePluginsEngine.dll" EngineDllEntryPoint="AlteryxFormula" />
        </Node>
        <Node ToolID="109">
          <GuiSettings Plugin="AlteryxBasePluginsGui.Filter.Filter">
            <Position x="678" y="150" />
          </GuiSettings>
          <Properties>
            <Configuration>
              <Expression>Contains([FileName],"_DPOSCONTRATOSIC.TXT")</Expression>
              <Mode>Custom</Mode>
            </Configuration>
            <Annotation DisplayMode="0">
              <Name />
              <DefaultAnnotationText>Contains([FileName],"_DPOSCONTRATOSIC.TXT")</DefaultAnnotationText>
              <Left value="False" />
            </Annotation>
          </Properties>
          <EngineSettings EngineDll="AlteryxBasePluginsEngine.dll" EngineDllEntryPoint="AlteryxFilter" />
        </Node>
        <Node ToolID="110">
          <GuiSettings Plugin="PortfolioPluginsGui.Email.Email">
            <Position x="1206" y="126" />
          </GuiSettings>
          <Properties>
            <Configuration>
              <SMTPServerName>mailhost.jpmchase.net</SMTPServerName>
              <ToIsField value="False" />
              <To>brazil_sales_support_mo@jpmchase.com</To>
              <CcIsField value="False" />
              <Cc>brazil.otc.ops@jpmchase.com</Cc>
              <BccIsField value="False" />
              <Bcc />
              <FromIsField value="False" />
              <From>brazil.otc.ops@jpmchase.com</From>
              <SubjectIsField value="True" />
              <Subject>Subject</Subject>
              <BodyIsField value="False" />
              <Body>Bom dia, Sales Support.
Segue anexo conforme solicitado.

Atenciosamente,
Brazil OTC Ops</Body>
              <UserName />
              <Attachments>
                <Attachment>
                  <ValueIsField value="True" />
                  <Value>CompletePath</Value>
                </Attachment>
              </Attachments>
              <Enabled>True</Enabled>
              <Password />
              <Port>25</Port>
              <Encryption>None</Encryption>
              <SMTPAuth value="False" />
            </Configuration>
            <Annotation DisplayMode="0">
              <Name />
              <DefaultAnnotationText />
              <Left value="False" />
            </Annotation>
          </Properties>
          <EngineSettings EngineDll="PortfolioPluginsEngine.dll" EngineDllEntryPoint="AlteryxComposerEmail" />
        </Node>
        <Node ToolID="111">
          <GuiSettings Plugin="AlteryxBasePluginsGui.Unique.Unique">
            <Position x="1074" y="138" />
          </GuiSettings>
          <Properties>
            <Configuration>
              <UniqueFields>
                <Field field="CompletePath" />
              </UniqueFields>
            </Configuration>
            <Annotation DisplayMode="0">
              <Name />
              <DefaultAnnotationText />
              <Left value="False" />
            </Annotation>
          </Properties>
          <EngineSettings EngineDll="AlteryxBasePluginsEngine.dll" EngineDllEntryPoint="AlteryxUnique" />
        </Node>
      </ChildNodes>
    </Node>
  </Nodes>
  <Connections>
    <Connection>
      <Origin ToolID="1" Connection="Output" />
      <Destination ToolID="3" Connection="Input" />
    </Connection>
    <Connection>
      <Origin ToolID="1" Connection="Output" />
      <Destination ToolID="109" Connection="Input" />
    </Connection>
    <Connection>
      <Origin ToolID="1" Connection="Output" />
      <Destination ToolID="9" Connection="Input" />
    </Connection>
    <Connection>
      <Origin ToolID="9" Connection="True" />
      <Destination ToolID="31" Connection="Input" />
    </Connection>
    <Connection>
      <Origin ToolID="9" Connection="False" />
      <Destination ToolID="58" Connection="Input" />
    </Connection>
    <Connection>
      <Origin ToolID="9" Connection="True" />
      <Destination ToolID="25" Connection="Input" />
    </Connection>
    <Connection>
      <Origin ToolID="9" Connection="False" />
      <Destination ToolID="116" Connection="Input" />
    </Connection>
    <Connection>
      <Origin ToolID="31" Connection="Output" />
      <Destination ToolID="30" Connection="Input" />
    </Connection>
    <Connection>
      <Origin ToolID="30" Connection="Output" />
      <Destination ToolID="32" Connection="Input" />
    </Connection>
    <Connection>
      <Origin ToolID="32" Connection="Output" />
      <Destination ToolID="29" Connection="Input" />
    </Connection>
    <Connection>
      <Origin ToolID="23" Connection="True" />
      <Destination ToolID="47" Connection="Input" />
    </Connection>
    <Connection>
      <Origin ToolID="23" Connection="False" />
      <Destination ToolID="79" Connection="Input" />
    </Connection>
    <Connection>
      <Origin ToolID="21" Connection="False" />
      <Destination ToolID="23" Connection="Input" />
    </Connection>
    <Connection>
      <Origin ToolID="21" Connection="True" />
      <Destination ToolID="43" Connection="Input" />
    </Connection>
    <Connection>
      <Origin ToolID="19" Connection="True" />
      <Destination ToolID="41" Connection="Input" />
    </Connection>
    <Connection>
      <Origin ToolID="19" Connection="False" />
      <Destination ToolID="63" Connection="Input" />
    </Connection>
    <Connection>
      <Origin ToolID="13" Connection="False" />
      <Destination ToolID="19" Connection="Input" />
    </Connection>
    <Connection>
      <Origin ToolID="13" Connection="True" />
      <Destination ToolID="37" Connection="Input" />
    </Connection>
    <Connection>
      <Origin ToolID="13" Connection="True" />
      <Destination ToolID="78" Connection="Input" />
    </Connection>
    <Connection>
      <Origin ToolID="11" Connection="True" />
      <Destination ToolID="33" Connection="Input" />
    </Connection>
    <Connection>
      <Origin ToolID="11" Connection="False" />
      <Destination ToolID="53" Connection="Input" />
    </Connection>
    <Connection>
      <Origin ToolID="33" Connection="Output" />
      <Destination ToolID="34" Connection="Input" />
    </Connection>
    <Connection>
      <Origin ToolID="34" Connection="Output" />
      <Destination ToolID="36" Connection="Input" />
    </Connection>
    <Connection>
      <Origin ToolID="36" Connection="Output" />
      <Destination ToolID="35" Connection="Input" />
    </Connection>
    <Connection>
      <Origin ToolID="37" Connection="Output" />
      <Destination ToolID="38" Connection="Input" />
    </Connection>
    <Connection>
      <Origin ToolID="38" Connection="Output" />
      <Destination ToolID="40" Connection="Input" />
    </Connection>
    <Connection>
      <Origin ToolID="40" Connection="Output" />
      <Destination ToolID="39" Connection="Input" />
    </Connection>
    <Connection>
      <Origin ToolID="41" Connection="Output" />
      <Destination ToolID="42" Connection="Input" />
    </Connection>
    <Connection>
      <Origin ToolID="42" Connection="Output" />
      <Destination ToolID="51" Connection="Input" />
    </Connection>
    <Connection>
      <Origin ToolID="43" Connection="Output" />
      <Destination ToolID="44" Connection="Input" />
    </Connection>
    <Connection>
      <Origin ToolID="44" Connection="Output" />
      <Destination ToolID="45" Connection="Input" />
    </Connection>
    <Connection>
      <Origin ToolID="45" Connection="Output" />
      <Destination ToolID="46" Connection="Input" />
    </Connection>
    <Connection>
      <Origin ToolID="47" Connection="Output" />
      <Destination ToolID="50" Connection="Input" />
    </Connection>
    <Connection>
      <Origin ToolID="49" Connection="Output" />
      <Destination ToolID="48" Connection="Input" />
    </Connection>
    <Connection>
      <Origin ToolID="50" Connection="Output" />
      <Destination ToolID="49" Connection="Input" />
    </Connection>
    <Connection>
      <Origin ToolID="51" Connection="Output" />
      <Destination ToolID="52" Connection="Input" />
    </Connection>
    <Connection>
      <Origin ToolID="53" Connection="True" />
      <Destination ToolID="54" Connection="Input" />
    </Connection>
    <Connection>
      <Origin ToolID="53" Connection="False" />
      <Destination ToolID="13" Connection="Input" />
    </Connection>
    <Connection>
      <Origin ToolID="54" Connection="Output" />
      <Destination ToolID="55" Connection="Input" />
    </Connection>
    <Connection>
      <Origin ToolID="55" Connection="Output" />
      <Destination ToolID="56" Connection="Input" />
    </Connection>
    <Connection>
      <Origin ToolID="56" Connection="Output" />
      <Destination ToolID="57" Connection="Input" />
    </Connection>
    <Connection>
      <Origin ToolID="58" Connection="False" />
      <Destination ToolID="11" Connection="Input" />
    </Connection>
    <Connection>
      <Origin ToolID="58" Connection="True" />
      <Destination ToolID="59" Connection="Input" />
    </Connection>
    <Connection>
      <Origin ToolID="59" Connection="Output" />
      <Destination ToolID="60" Connection="Input" />
    </Connection>
    <Connection>
      <Origin ToolID="60" Connection="Output" />
      <Destination ToolID="61" Connection="Input" />
    </Connection>
    <Connection>
      <Origin ToolID="61" Connection="Output" />
      <Destination ToolID="62" Connection="Input" />
    </Connection>
    <Connection>
      <Origin ToolID="63" Connection="False" />
      <Destination ToolID="21" Connection="Input" />
    </Connection>
    <Connection>
      <Origin ToolID="63" Connection="True" />
      <Destination ToolID="64" Connection="Input" />
    </Connection>
    <Connection>
      <Origin ToolID="64" Connection="Output" />
      <Destination ToolID="65" Connection="Input" />
    </Connection>
    <Connection>
      <Origin ToolID="65" Connection="Output" />
      <Destination ToolID="66" Connection="Input" />
    </Connection>
    <Connection>
      <Origin ToolID="66" Connection="Output" />
      <Destination ToolID="67" Connection="Input" />
    </Connection>
    <Connection>
      <Origin ToolID="75" Connection="Output" />
      <Destination ToolID="76" Connection="Input" />
    </Connection>
    <Connection>
      <Origin ToolID="76" Connection="Output" />
      <Destination ToolID="77" Connection="Input" />
    </Connection>
    <Connection>
      <Origin ToolID="78" Connection="Output" />
      <Destination ToolID="75" Connection="Input" />
    </Connection>
    <Connection>
      <Origin ToolID="79" Connection="True" />
      <Destination ToolID="80" Connection="Input" />
    </Connection>
    <Connection>
      <Origin ToolID="79" Connection="False" />
      <Destination ToolID="97" Connection="Input" />
    </Connection>
    <Connection>
      <Origin ToolID="80" Connection="Output" />
      <Destination ToolID="83" Connection="Input" />
    </Connection>
    <Connection>
      <Origin ToolID="82" Connection="Output" />
      <Destination ToolID="81" Connection="Input" />
    </Connection>
    <Connection>
      <Origin ToolID="83" Connection="Output" />
      <Destination ToolID="82" Connection="Input" />
    </Connection>
    <Connection>
      <Origin ToolID="93" Connection="Output" />
      <Destination ToolID="95" Connection="Input" />
    </Connection>
    <Connection>
      <Origin ToolID="94" Connection="Output" />
      <Destination ToolID="96" Connection="Input" />
    </Connection>
    <Connection>
      <Origin ToolID="95" Connection="Output" />
      <Destination ToolID="94" Connection="Input" />
    </Connection>
    <Connection>
      <Origin ToolID="97" Connection="True" />
      <Destination ToolID="93" Connection="Input" />
    </Connection>
    <Connection>
      <Origin ToolID="97" Connection="True" />
      <Destination ToolID="98" Connection="Input" />
    </Connection>
    <Connection>
      <Origin ToolID="98" Connection="Output" />
      <Destination ToolID="100" Connection="Input" />
    </Connection>
    <Connection>
      <Origin ToolID="99" Connection="Output" />
      <Destination ToolID="101" Connection="Input" />
    </Connection>
    <Connection>
      <Origin ToolID="100" Connection="Output" />
      <Destination ToolID="99" Connection="Input" />
    </Connection>
    <Connection>
      <Origin ToolID="112" Connection="Output" />
      <Destination ToolID="114" Connection="Input" />
    </Connection>
    <Connection>
      <Origin ToolID="113" Connection="Output" />
      <Destination ToolID="115" Connection="Input" />
    </Connection>
    <Connection>
      <Origin ToolID="114" Connection="Output" />
      <Destination ToolID="113" Connection="Input" />
    </Connection>
    <Connection>
      <Origin ToolID="116" Connection="True" />
      <Destination ToolID="112" Connection="Input" />
    </Connection>
    <Connection name="#2">
      <Origin ToolID="119" Connection="Output" />
      <Destination ToolID="133" Connection="Input" />
    </Connection>
    <Connection name="#1">
      <Origin ToolID="154" Connection="Output" />
      <Destination ToolID="133" Connection="Input" />
    </Connection>
    <Connection>
      <Origin ToolID="120" Connection="Output" />
      <Destination ToolID="121" Connection="Input" />
    </Connection>
    <Connection>
      <Origin ToolID="121" Connection="Output" />
      <Destination ToolID="122" Connection="Input2" />
    </Connection>
    <Connection>
      <Origin ToolID="122" Connection="Output26" />
      <Destination ToolID="123" Connection="Input" />
    </Connection>
    <Connection>
      <Origin ToolID="123" Connection="True" />
      <Destination ToolID="124" Connection="Input" />
    </Connection>
    <Connection>
      <Origin ToolID="124" Connection="Output" />
      <Destination ToolID="125" Connection="Input" />
    </Connection>
    <Connection>
      <Origin ToolID="125" Connection="True" />
      <Destination ToolID="126" Connection="Input" />
    </Connection>
    <Connection>
      <Origin ToolID="126" Connection="True" />
      <Destination ToolID="129" Connection="Left" />
    </Connection>
    <Connection>
      <Origin ToolID="130" Connection="Unique" />
      <Destination ToolID="129" Connection="Right" />
    </Connection>
    <Connection>
      <Origin ToolID="127" Connection="Output" />
      <Destination ToolID="128" Connection="Input2" />
    </Connection>
    <Connection>
      <Origin ToolID="128" Connection="Output26" />
      <Destination ToolID="130" Connection="Input" />
    </Connection>
    <Connection name="#1">
      <Origin ToolID="129" Connection="Join" />
      <Destination ToolID="131" Connection="Input" />
    </Connection>
    <Connection name="#2">
      <Origin ToolID="129" Connection="Left" />
      <Destination ToolID="131" Connection="Input" />
    </Connection>
    <Connection>
      <Origin ToolID="131" Connection="Output" />
      <Destination ToolID="132" Connection="Input" />
    </Connection>
    <Connection>
      <Origin ToolID="131" Connection="Output" />
      <Destination ToolID="139" Connection="Input8" />
    </Connection>
    <Connection>
      <Origin ToolID="132" Connection="Output" />
      <Destination ToolID="138" Connection="Input" />
    </Connection>
    <Connection>
      <Origin ToolID="133" Connection="Output" />
      <Destination ToolID="134" Connection="Input" />
    </Connection>
    <Connection>
      <Origin ToolID="134" Connection="Output" />
      <Destination ToolID="135" Connection="Input" />
    </Connection>
    <Connection>
      <Origin ToolID="135" Connection="True" />
      <Destination ToolID="136" Connection="Input" />
    </Connection>
    <Connection>
      <Origin ToolID="136" Connection="Output" />
      <Destination ToolID="120" Connection="Input" />
    </Connection>
    <Connection>
      <Origin ToolID="138" Connection="Output" />
      <Destination ToolID="140" Connection="Input" />
    </Connection>
    <Connection name="#1">
      <Origin ToolID="139" Connection="Output9" />
      <Destination ToolID="143" Connection="Input" />
    </Connection>
    <Connection name="#2">
      <Origin ToolID="140" Connection="Output" />
      <Destination ToolID="143" Connection="Input" />
    </Connection>
    <Connection name="#1">
      <Origin ToolID="142" Connection="Output" />
      <Destination ToolID="157" Connection="Input" />
    </Connection>
    <Connection name="#2">
      <Origin ToolID="156" Connection="Output" />
      <Destination ToolID="157" Connection="Input" />
    </Connection>
    <Connection>
      <Origin ToolID="143" Connection="Output" />
      <Destination ToolID="142" Connection="Input" />
    </Connection>
    <Connection>
      <Origin ToolID="157" Connection="Output" />
      <Destination ToolID="158" Connection="Input" />
    </Connection>
    <Connection>
      <Origin ToolID="158" Connection="Output" />
      <Destination ToolID="159" Connection="Input" />
    </Connection>
    <Connection>
      <Origin ToolID="158" Connection="Output" />
      <Destination ToolID="160" Connection="Input" />
    </Connection>
    <Connection>
      <Origin ToolID="144" Connection="Output" />
      <Destination ToolID="146" Connection="Left" />
    </Connection>
    <Connection>
      <Origin ToolID="148" Connection="True" />
      <Destination ToolID="146" Connection="Right" />
    </Connection>
    <Connection>
      <Origin ToolID="145" Connection="Output" />
      <Destination ToolID="147" Connection="Input" />
    </Connection>
    <Connection>
      <Origin ToolID="146" Connection="Right" />
      <Destination ToolID="149" Connection="Input" />
    </Connection>
    <Connection>
      <Origin ToolID="147" Connection="Output" />
      <Destination ToolID="148" Connection="Input" />
    </Connection>
    <Connection>
      <Origin ToolID="149" Connection="Output" />
      <Destination ToolID="150" Connection="Input" />
    </Connection>
    <Connection>
      <Origin ToolID="150" Connection="Output" />
      <Destination ToolID="151" Connection="Input" />
    </Connection>
    <Connection>
      <Origin ToolID="151" Connection="Output" />
      <Destination ToolID="152" Connection="Input" />
    </Connection>
    <Connection>
      <Origin ToolID="152" Connection="Output" />
      <Destination ToolID="153" Connection="Input" />
    </Connection>
    <Connection>
      <Origin ToolID="153" Connection="Output" />
      <Destination ToolID="154" Connection="Input" />
    </Connection>
    <Connection>
      <Origin ToolID="107" Connection="Output" />
      <Destination ToolID="108" Connection="Input" />
    </Connection>
    <Connection>
      <Origin ToolID="108" Connection="Output" />
      <Destination ToolID="111" Connection="Input" />
    </Connection>
    <Connection>
      <Origin ToolID="109" Connection="True" />
      <Destination ToolID="107" Connection="Input" />
    </Connection>
    <Connection>
      <Origin ToolID="111" Connection="Unique" />
      <Destination ToolID="110" Connection="Input" />
    </Connection>
  </Connections>
  <Properties>
    <Memory default="True" />
    <GlobalRecordLimit value="0" />
    <TempFiles default="True" />
    <Annotation on="True" includeToolName="False" />
    <ConvErrorLimit value="10" />
    <ConvErrorLimit_Stop value="False" />
    <CancelOnError value="False" />
    <DisableBrowse value="False" />
    <EnablePerformanceProfiling value="False" />
    <RunWithE2 value="True" />
    <PredictiveToolsCodePage value="1252" />
    <DisableAllOutput value="False" />
    <ShowAllMacroMessages value="False" />
    <ShowConnectionStatusIsOn value="True" />
    <ShowConnectionStatusOnlyWhenRunning value="True" />
    <ZoomLevel value="0" />
    <LayoutType>Horizontal</LayoutType>
    <IsTemplate value="False" />
    <MetaInfo>
      <NameIsFileName value="True" />
      <Name>SalvarArquivos - v3</Name>
      <Description />
      <RootToolName />
      <ToolVersion />
      <ToolInDb value="False" />
      <CategoryName />
      <SearchTags />
      <Author />
      <Company />
      <Copyright />
      <DescriptionLink actual="" displayed="" />
      <Example>
        <Description />
        <File />
      </Example>
      <WorkflowId value="0a75ba91-249c-4513-97c9-dd34fea8f9ed" />
      <Telemetry>
        <PreviousWorkflowId value="ab265598-c3e0-495b-94d4-99fc0974bad0" />
        <OriginWorkflowId value="3a71c645-9839-4a41-b6a7-e0aec70a7b7d" />
      </Telemetry>
      <PlatformWorkflowId value="" />
    </MetaInfo>
    <Events>
      <Enabled value="True" />
    </Events>
  </Properties>
</AlteryxDocument>