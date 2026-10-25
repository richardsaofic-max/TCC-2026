# Náutica — laboratório de rolagem

Interface local em Python, Dash e Plotly para o modelo do Anexo A do **TCC v7** de Richard Silva de Abreu. O código do PDF foi usado como referência científica; não é executado diretamente.

## Abrir neste computador

Dê dois cliques em **Iniciar simulador.cmd**. As bibliotecas já foram instaladas na pasta local `.deps`. O iniciador abre o navegador assim que o servidor fica disponível. Mantenha a janela do terminal aberta e encerre com Ctrl+C. Se uma porta estiver ocupada, o iniciador escolhe outra entre 8050 e 8060.

Alternativamente, execute `python app.py` e acesse http://127.0.0.1:8050. O `app.py` procura primeiro as bibliotecas locais em `.deps`.

## Instalar em outro computador

Requer Python 3.11 ou superior. No terminal, dentro desta pasta:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe iniciar.py
```

Depois, também é possível usar **Iniciar simulador.cmd**. Após instalar, não há necessidade de internet para simular, visualizar ou otimizar. Nada é enviado para serviços externos. O servidor escuta apenas em 127.0.0.1; não há publicação nem hospedagem na internet.

## Usar

1. Escolha o cenário e os controladores na barra lateral. A malha aberta sempre é calculada como referência.
2. Ajuste onda, duração, condições iniciais e parâmetros da embarcação. Os parâmetros derivados são calculados automaticamente e podem ser consultados na aba **Ganhos e modelo**.
3. Clique em **Calcular ensaio**. Alterações de parâmetros ou ganhos não afetam um ensaio já calculado; uma mensagem sinaliza alterações pendentes.
4. Use **Reproduzir**, **Pausar**, **Voltar ao início**, velocidade e a barra temporal. A telemetria e os gráficos seguem o mesmo instante discreto. A caixa **Ampliar respostas controladas** oculta inicialmente a curva sem controle e ajusta a escala, facilitando a comparação PID/LQR/Fuzzy.
5. Selecione o controlador da telemetria. As quatro embarcações mostram os ângulos em escala real, sem amplificação visual.
6. Exporte os dados, as métricas e a configuração do ensaio calculado. O JSON pode ser importado posteriormente. CSV usa separador `;`, números com ponto decimal e UTF-8 com BOM; no Excel, use **Dados > De Texto/CSV** se a configuração regional não reconhecer os números.

As métricas na tabela são do ensaio **completo**, mesmo quando a reprodução está no início. O cálculo é feito primeiro; trata-se de reprodução sincronizada, não de controle de hardware nem de alteração de perturbação durante a execução.

## Ganhos e otimização

PID: `[Kp, Ki, Kd]`. LQR: `[Q11, Q22, R]`; o ganho discreto K é recalculado usando DARE sempre que a planta ou Δt muda. Fuzzy: 18 valores `[centro, largura]` para os conjuntos N/Z/P do ângulo, da velocidade e do torque, nessa ordem. As curvas de pertinência são exibidas na aba do modelo.

A aba **Otimização por AG** usa PyGAD em uma thread separada e avalia os três cenários para cada indivíduo. A planta e as condições do ensaio são capturadas ao iniciar a otimização. População 10, 5 pais, seleção SSS, cruzamento em um ponto, mutação de um gene e seed 42. Os intervalos de busca e a função de custo seguem o anexo. A configuração inicial usa 20 gerações para exploração; 300 corresponde ao TCC. A otimização Fuzzy pode demorar. O cancelamento é cooperativo e preserva os resultados do ensaio anterior. Uma nova otimização começa uma nova busca; não retoma a população anterior.

Ao terminar, clique **Aplicar ganhos encontrados**, depois **Calcular ensaio**. As configurações atuais da barra lateral podem ter mudado desde o início da busca: mantenha-as iguais às condições de treinamento para avaliar a sintonia nessas condições. Jobs e dados da sessão ficam em memória e são perdidos ao encerrar o processo; exporte o JSON para preservar a sintonia. O painel foi projetado para uso local por uma pessoa.

## Fidelidade ao TCC e convenções

- Modelo linear de roll com dois estados: φ (rad) e φ̇ (rad/s). Integração exata da planta por ZOH; controlador atualizado a cada Δt. Referência angular nula.
- Valores físicos iniciais do código: Ixx = 0,0444; Jxx = 20% de Ixx; Δ = 63,2745 N; GM = 0,0229183 m; ζ = 0,076; χA = 0,80; Δt = 0,02 s; duração 15 s.
- A frequência inicial da onda é **ωd/2**, como no código executável. O texto descreve ωn/2 em alguns trechos. A interface preserva o código. Se ζ ≥ 1, usa ωn como referência, pois não há frequência natural amortecida oscilatória real.
- Onda multifrequencial determinística: pesos 0,5/0,3/0,2, frequências 0,8/1/1,2 vezes a frequência de base e fases 0/0,5/1 rad.
- Ganhos iniciais das Tabelas 3 e 4, disponíveis apenas arredondados a três casas. No cenário senoidal, a malha aberta resulta em 6,2697° e o PID em 0,3712°, como na Tabela 5. LQR resulta em cerca de 0,1519° e Fuzzy em cerca de 0,2390°, enquanto a tabela registra 0,1518° e 0,2487°. A versão implementada não foi calibrada para forçar esses resultados. Para investigar a diferença Fuzzy e confirmar equivalência exata, são necessários os ganhos completos e o notebook original; o arredondamento pode contribuir, mas não foi comprovado como única causa.
- O anexo inclui PID em cascata no código; a comparação desta interface usa PID, LQR e Fuzzy, conforme o escopo principal do TCC. Não foram inventados ganhos para o cascata.
- As funções gaussianas são amostradas nos mesmos universos do anexo; interpolação das entradas, regras max–min e centroide por scikit-fuzzy.
- Limite de torque padrão ±100 N·m, conforme o código. É um limite numérico, não a especificação de um atuador físico. O PID mantém a integração sem anti-windup, como no anexo.
- O histórico original salva o estado já atualizado com o rótulo `i*dt`. Aqui, a condição inicial é salva em **t = 0**, e o estado atualizado em **t = (i+1)Δt**. Isso evita deslocar o estado um passo para trás. O torque u[k] se aplica em [t[k], t[k+1]); o último torque é vazio no CSV e aparece como “—” na telemetria, pois não há próximo intervalo.
- A duração efetiva é arredondada ao múltiplo de Δt mais próximo e aparece no relógio.
- IAE usa soma retangular à direita sobre os estados atualizados, como na função de fitness original; apresenta graus·s, usa rad·s na otimização. ISU = Σu²Δt em (N·m)²·s. TV = Σ|Δu| em N·m. Chat = RMS(Δu/Δt) em N·m/s. RMS e inclinação máxima são dados em graus. A máxima inclui a condição inicial. A redução usa RMS em relação ao caso sem controle, e fica indefinida quando a referência tem RMS nulo.
- ISU não mede energia elétrica. A animação representa apenas a rolagem; não modela deslocamento vertical, velocidade de roda, dinâmica elétrica ou limite de momento angular. Uma mensagem indica quando a resposta ultrapassa 10°, fora da aproximação adotada de pequenos ângulos.

## Arquivos

- `simulation.py`: modelo, ondas, controladores, métricas e AG, independente do painel.
- `app.py`: interface, validação, importação/exportação e execução de jobs.
- `assets/replay.js`: reprodução e gráficos no navegador, sem requisição ao Python por quadro.
- `assets/*.css`: apresentação responsiva.
- `iniciar.py` e `Iniciar simulador.cmd`: inicialização local.
- `tests/`: verificações físicas, regressão numérica e callbacks.

## Verificar

```powershell
python -m unittest discover -s tests -v
```

Se estiver usando as dependências locais `.deps`, os testes as adicionam automaticamente ao caminho. Para verificar apenas o JavaScript: `node --check assets/replay.js`.
