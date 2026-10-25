# Simulador de estabilização de embarcações

Aplicação local para simular o movimento de rolagem de uma embarcação e comparar os controladores PID, LQR e Fuzzy com a resposta sem controle.

A interface permite configurar os ensaios, visualizar as respostas em gráficos e animações sincronizadas, calcular métricas de desempenho e exportar os resultados. Desenvolvida em Python, Dash e Plotly.

## Funcionalidades

- Três cenários de perturbação: onda senoidal, impacto amortecido e mar multifrequencial.
- Configuração dos parâmetros físicos da embarcação, condições iniciais, duração e passo de simulação.
- Seleção dos controladores e edição de seus parâmetros.
- Comparação com a resposta da embarcação sem controle.
- Representação animada da rolagem, com valores de ângulo, velocidade angular e torques.
- Reprodução com pausa, reinício, ajuste de velocidade e navegação temporal.
- Gráficos de rolagem, velocidade angular, esforço de controle e inclinação efetiva da onda.
- Métricas de desempenho e exportação de dados e configurações.
- Visualização das funções de pertinência do controlador Fuzzy.
- Sintonia por algoritmo genético, executada separadamente da reprodução.

## Requisitos

- Python 3.11 ou superior.
- Navegador atualizado.
- Internet para a instalação inicial das bibliotecas.

Após a instalação das dependências, a aplicação funciona localmente sem conexão com a internet. As simulações são processadas no próprio computador.

## Instalação

Baixe ou clone o repositório e abra um terminal na pasta do projeto.

### Windows

Crie um ambiente virtual e instale as dependências:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Inicie a aplicação:

```powershell
.venv\Scripts\python.exe iniciar.py
```

Depois da instalação inicial, também é possível dar dois cliques em **Iniciar simulador.cmd**. O iniciador procura uma porta disponível entre 8050 e 8060 e abre o navegador quando o servidor estiver pronto.

### Linux e macOS

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python app.py
```

Abra o endereço exibido no terminal, normalmente:

```text
http://127.0.0.1:8050
```

### Execução direta

Com as dependências instaladas no ambiente utilizado, execute:

```bash
python app.py
```

Para escolher outra porta:

```bash
python app.py --port 8052
```

Mantenha o terminal aberto durante o uso. Para encerrar o servidor, pressione **Ctrl+C**. O endereço `127.0.0.1` funciona somente no computador em que a aplicação está sendo executada.

## Como usar

1. Na barra lateral, escolha o cenário e os controladores que deseja comparar.
2. Ajuste os parâmetros da onda, as condições iniciais e as características da embarcação.
3. Na aba **Ganhos e modelo**, ajuste os parâmetros dos controladores, se necessário.
4. Clique em **Calcular ensaio**.
5. Use **Reproduzir**, **Pausar**, o ajuste de velocidade e a barra temporal para acompanhar a resposta.
6. Selecione o controlador da telemetria para consultar seus valores no instante exibido.
7. Consulte as métricas finais e exporte os resultados.

A simulação é calculada antes da reprodução. A animação e os gráficos exibem os históricos de forma sincronizada; não representam aquisição de dados de sensores ou controle de uma embarcação física em tempo real.

Alterações nos parâmetros e nos ganhos só entram em vigor ao calcular um novo ensaio. Uma mensagem indica alterações pendentes. O botão **Restaurar parâmetros padrão** repõe os valores iniciais dos campos.

A opção **Ampliar respostas controladas** facilita a comparação entre os controladores ao ocultar inicialmente a curva sem controle e ajustar a escala dos gráficos.

## Modelo de rolagem

O modelo linear possui um grau de liberdade e dois estados: ângulo de rolagem e velocidade angular. A dinâmica é descrita por:

```text
(Ixx + Jxx) · φ̈ + Beq · φ̇ + Δ · GM · φ = Kext + u
```

| Símbolo | Significado | Unidade |
| --- | --- | --- |
| Ixx | Momento de inércia do casco | kg·m² |
| Jxx | Momento de inércia adicionada | kg·m² |
| Beq | Coeficiente de amortecimento linear | N·m·s/rad |
| Δ | Deslocamento em peso | N |
| GM | Altura metacêntrica | m |
| φ | Ângulo de rolagem | rad |
| Kext | Torque externo | N·m |
| u | Torque de controle | N·m |

A referência angular é nula. A planta é discretizada pelo método ZOH. Os cálculos internos usam radianos; os ângulos exibidos na interface usam graus.

A inércia total, as frequências naturais e o coeficiente de amortecimento são calculados a partir dos parâmetros físicos. A frequência de base da onda é definida pela razão configurada multiplicada pela frequência natural amortecida, ωd. Para amortecimento ζ ≥ 1, utiliza-se a frequência natural não amortecida, ωn, como referência.

O cenário multifrequencial utiliza uma superposição determinística de três senoides, com pesos 0,5, 0,3 e 0,2; frequências relativas 0,8, 1,0 e 1,2; e fases de 0, 0,5 e 1,0 rad.

### Amostragem

O estado inicial é registrado em `t = 0`. O comando `u[k]` é aplicado no intervalo entre `t[k]` e `t[k+1]`. A última amostra de estado não possui um novo comando de controle, aparecendo como campo vazio no CSV e como “—” na telemetria de torque.

A duração efetiva é arredondada para o múltiplo do passo de simulação mais próximo e pode ser consultada no relógio da reprodução.

### Hipóteses e limites

- O modelo linear considera pequenas oscilações. A interface indica respostas que ultrapassam 10° de rolagem.
- O atuador é representado pelo torque de controle, com limite numérico ajustável. O valor padrão é ±100 N·m.
- Não são modelados a dinâmica elétrica do motor, a velocidade da roda ou a saturação de momento angular.
- O PID acumula a ação integral sem compensação anti-windup.
- A animação representa somente a rolagem, em escala angular real. A linha d’água serve como referência visual.

## Controladores

### PID

Parâmetros editáveis: `Kp`, `Ki` e `Kd`. A ação derivativa utiliza a velocidade angular:

```text
u = −Kp · φ + Ki · integral(−φ) − Kd · φ̇
```

### LQR

Parâmetros editáveis: `Q11`, `Q22` e `R`, com `Q = diag(Q11, Q22)`. O vetor de realimentação é calculado a partir da equação algébrica de Riccati no domínio discreto e atualizado ao recalcular o ensaio.

### Fuzzy

Controlador Mamdani com funções de pertinência gaussianas, inferência max–min e defuzzificação por centroide.

O vetor de configuração possui 18 valores, organizados em pares `[centro, largura]`, nesta ordem:

1. Conjuntos Negativo, Zero e Positivo do ângulo de rolagem.
2. Conjuntos Negativo, Zero e Positivo da velocidade angular.
3. Conjuntos Negativo, Zero e Positivo do torque.

As unidades são rad, rad/s e N·m, respectivamente. As larguras devem ser positivas. As curvas de pertinência são apresentadas na aba **Ganhos e modelo**.

## Métricas de desempenho

| Métrica | Descrição | Unidade |
| --- | --- | --- |
| Máx. \|φ\| | Maior módulo do ângulo, incluindo a condição inicial | ° |
| RMS | Valor eficaz da rolagem nos estados atualizados | ° |
| Redução RMS | Redução relativa ao RMS da resposta sem controle | % |
| IAE | Integral do módulo do erro angular | °·s |
| ISU | Integral do quadrado do torque de controle | (N·m)²·s |
| TV | Soma dos módulos das variações do torque | N·m |
| Chat | RMS da taxa de variação do torque | N·m/s |
| Saturação | Percentual dos comandos que atingem o limite de torque | % |

IAE e ISU são calculados por somas retangulares. A redução RMS fica indefinida quando a resposta de referência possui RMS nulo. O ISU é um indicador de esforço de controle, não uma medição de energia elétrica.

A tabela apresenta as métricas do ensaio completo, independentemente do instante selecionado na reprodução.

## Otimização por algoritmo genético

Na aba **Otimização por AG**, selecione um controlador e o número de gerações. A busca avalia os três cenários para cada indivíduo e utiliza os parâmetros da barra lateral capturados ao iniciar a execução.

Configuração da busca:

- População de 10 indivíduos e seleção de 5 pais.
- Seleção SSS, cruzamento em um ponto e mutação de um gene.
- Semente pseudoaleatória 42.
- Valor inicial de 20 gerações, ajustável até 300.

A função de custo agrega os três cenários:

```text
J = soma[IAE(rad·s) + 0,001 · ISU + 0,01 · TV + 0,01 · Chat]
fitness = 1 / (J + 10⁻⁶)
```

A otimização é executada em segundo plano. O cancelamento é cooperativo e pode aguardar o término da avaliação atual. Ao concluir a busca, clique em **Aplicar ganhos encontrados** e depois em **Calcular ensaio**.

Mantenha os parâmetros físicos e de simulação iguais aos utilizados na busca para avaliar a sintonia nas mesmas condições. Cada nova otimização inicia uma nova busca, sem retomar a população anterior. A execução Fuzzy pode demandar mais tempo.

## Importação e exportação

- **Dados CSV:** histórico temporal, inclinação da onda, torque externo e respostas dos controladores.
- **Métricas CSV:** indicadores de desempenho por controlador.
- **Configuração JSON:** parâmetros, cenário, controladores e ganhos do ensaio calculado.

A exportação corresponde ao ensaio calculado; alterações pendentes nos campos não são incluídas. Para reutilizar uma configuração, importe o arquivo JSON e clique em **Calcular ensaio**.

Os arquivos CSV usam separador `;`, ponto decimal e codificação UTF-8 com BOM. Caso o Excel não reconheça os números automaticamente, utilize **Dados > De Texto/CSV** e selecione a configuração regional adequada.

Os resultados e as otimizações ficam em memória durante a execução. Exporte os arquivos que deseja preservar antes de encerrar a aplicação. O painel foi projetado para uso local por uma pessoa.

## Estrutura do projeto

```text
simulador/
├── app.py
├── simulation.py
├── iniciar.py
├── Iniciar simulador.cmd
├── requirements.txt
├── README.md
├── .gitignore
├── assets/
│   ├── style.css
│   ├── dash-controls.css
│   └── replay.js
└── tests/
    └── test_simulation.py
```

| Arquivo | Responsabilidade |
| --- | --- |
| `app.py` | Interface, validação, importação, exportação e gerenciamento da otimização |
| `simulation.py` | Modelo, perturbações, controladores, métricas e algoritmo genético |
| `iniciar.py` | Inicialização do servidor local e abertura do navegador |
| `Iniciar simulador.cmd` | Atalho de execução no Windows |
| `assets/replay.js` | Reprodução sincronizada e atualização dos gráficos no navegador |
| `assets/*.css` | Estilos da interface |
| `requirements.txt` | Dependências Python |
| `tests/` | Verificações do modelo e da aplicação |

Não inclua no repositório as pastas `.venv/`, `.deps/` ou `__pycache__/`, nem arquivos temporários. Elas contêm dependências ou arquivos gerados durante o uso.

## Verificação

Execute os testes a partir da pasta do projeto, com as dependências instaladas:

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

No Linux ou macOS:

```bash
.venv/bin/python -m unittest discover -s tests -v
```

## Autor

Richard Silva de Abreu — Engenharia de Controle e Automação.
