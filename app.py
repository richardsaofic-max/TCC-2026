"""Painel local do TCC. Execute python app.py e abra http://127.0.0.1:8050."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent / ".deps"))
import base64
import csv
import io
import json
import threading
import uuid
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timezone
from dash import Dash, dcc, html, Input, Output, State, ctx, no_update
from dash.exceptions import PreventUpdate
from simulation import Config, DEFAULT_GAINS, NAMES, simulate, validate_gains, genetic_optimize

app = Dash(__name__, title="Simulação de rolagem | TCC", update_title=None)
server = app.server
INITIAL = simulate()
INITIAL["id"] = "initial"
CONFIG_FIELDS = [
    ("amplitude", "Amplitude da onda", "°", 0, 30, .5),
    ("frequency_ratio", "Frequência / ωd", "×", .01, 5, .05),
    ("decay", "Decaimento", "s⁻¹", 0, 10, .05),
    ("duration", "Duração", "s", 1, 120, 1),
    ("dt", "Passo numérico", "s", .005, .1, .005),
    ("phi0", "Rolagem inicial", "°", -30, 30, .5),
    ("velocity0", "Velocidade inicial", "°/s", -180, 180, .5),
    ("ixx", "Inércia do casco · Ixx", "kg·m²", .000001, 10000, .0001),
    ("jxx", "Inércia adicionada · Jxx", "kg·m²", 0, 10000, .0001),
    ("displacement", "Deslocamento · Δ", "N", .0001, 1e7, .01),
    ("gm", "Altura metacêntrica · GM", "m", .000001, 100, .0001),
    ("zeta", "Amortecimento · ζ", "—", 0, 5, .001),
    ("chi", "Sensibilidade da onda · χA", "—", 0, 10, .05),
    ("torque_limit", "Limite numérico de torque", "N·m", .001, 10000, 1),
]
FIELD_IDS = [f"cfg-{f[0]}" for f in CONFIG_FIELDS]


def field(spec):
    key, label, unit, low, high, step = spec
    return html.Label([html.Span([label, html.Small(unit)]),
        dcc.Input(id=f"cfg-{key}", type="number", value=getattr(Config(), key),
                  min=low, max=high, step="any", debounce=True)], className="field")


def boat(name):
    slug = name.replace(" ", "-")
    return html.Div([
        html.Div([html.Span(className=f"dot dot-{slug}"), name], className="boat-label"),
        html.Div([
            html.Div(className="horizon"),
            html.Div([html.Div(className="mast"), html.Div(className="cabin"),
                      html.Div(className="hull"), html.Div(className="porthole")],
                     id=f"boat-{slug}", className=f"vessel vessel-{slug}"),
            html.Span("0°", id=f"angle-{slug}", className="boat-angle")
        ], className="boat-scene"),
    ], id=f"boat-card-{slug}", className="boat-card")


def metric_card(label, ident, unit):
    return html.Div([html.Span(label, className="eyebrow"),
                     html.Div([html.Strong("—", id=ident), html.Small(unit)])], className="metric-card")


def table(result):
    headers = ["Controlador", "Máx. |φ| (°)", "RMS (°)", "Redução RMS (%)", "IAE (°·s)",
               "ISU ((N·m)²·s)", "TV (N·m)", "Chat (N·m/s)", "Saturação (%)"]
    rows = []
    for name, s in result["series"].items():
        m = s["metrics"]
        values = [m["peak"], m["rms"], m["reduction"], m["iae"], m["isu"], m["tv"], m["chat"], s["saturation"]]
        rows.append(html.Tr([html.Td(name, style={"color": s["color"], "fontWeight": 600})] +
                            [html.Td("—" if v is None else f"{v:.4f}") for v in values]))
    return html.Table([html.Thead(html.Tr([html.Th(h) for h in headers])), html.Tbody(rows)])


def layout():
    return html.Div([
        dcc.Store(id="result", data=INITIAL), dcc.Store(id="frame", data={"time": 0, "playing": False}),
        dcc.Store(id="job-id"), dcc.Store(id="optimized-gains"),
        dcc.Interval(id="ticker", interval=100, disabled=True),
        dcc.Interval(id="job-poll", interval=1000), dcc.Download(id="download"),
        html.Aside([
            html.Div(html.H2("Parâmetros do ensaio"), className="section-title"),
            html.Label([html.Span("Cenário de excitação"), dcc.Dropdown(id="scenario", clearable=False,
                options=[{"label": v, "value": k} for k, v in NAMES.items()], value="regular")], className="field"),
            html.Div([field(s) for s in CONFIG_FIELDS[:2]], className="field-grid"),
            html.Div(field(CONFIG_FIELDS[2]), id="decay-field"),
            html.Label([html.Span("Controladores comparados"), dcc.Checklist(id="controllers",
                options=[{"label": n, "value": n} for n in DEFAULT_GAINS], value=list(DEFAULT_GAINS), inline=True)], className="field controller-check"),
            html.Details([html.Summary("Tempo e condições iniciais"), html.Div([field(s) for s in CONFIG_FIELDS[3:7]], className="field-grid")], open=True),
            html.Details([html.Summary("Parâmetros da embarcação"), html.Div([field(s) for s in CONFIG_FIELDS[7:]], className="field-grid")], open=True),
            html.Button("Calcular ensaio", id="run", className="primary"),
            html.Button("Restaurar parâmetros padrão", id="restore", className="text-button"),
            dcc.Upload(id="upload", children=html.Button("Importar configuração JSON", className="import-button"), multiple=False, accept=".json"),
            html.Div(id="import-status", className="small-note"),
            html.P("Modelo linear de 1 grau de liberdade · atuador ideal com limite numérico · execução local", className="sidebar-footer"),
        ], className="sidebar"),
        html.Main([
            html.Header(html.Div([html.H1("Estabilização de embarcações"),
                                  html.P("Simulação de rolagem · Comparação entre PID, LQR e Fuzzy")])),
            dcc.Tabs(id="tabs", value="sim", className="tabs", children=[
                dcc.Tab(label="Simulação", value="sim"), dcc.Tab(label="Ganhos e modelo", value="model"),
                dcc.Tab(label="Otimização por AG", value="ga")]),
            html.Div([
                html.Div([html.H3(id="run-title", children="Onda senoidal"),
                          html.Span("Reprodução da simulação", className="mode-badge")], className="panel-heading"),
                html.Div(id="run-status", className="small-note", children="Configuração padrão carregada. Pressione Reproduzir para acompanhar o ensaio."),
                html.Div(id="dirty", className="warning"), html.Div(id="warnings"),
                html.Div([boat(n) for n in ["Sem controle", "PID", "LQR", "Fuzzy"]], className="boats"),
                html.Div([html.Div([html.Label("Telemetria de"), dcc.Dropdown(id="monitor", clearable=False,
                    options=list(DEFAULT_GAINS), value="LQR")], className="monitor-select"),
                    metric_card("Rolagem", "live-phi", "°"), metric_card("Velocidade angular", "live-velocity", "°/s"),
                    metric_card("Torque de controle", "live-torque", "N·m"),
                    metric_card("Torque externo", "live-external", "N·m")], className="telemetry"),
                html.Div([html.Div([html.Button("▶ Reproduzir", id="play", className="play-button"),
                    html.Button("↺", id="restart", title="Voltar ao início", className="restart-button"),
                    html.Strong("0,00 / 15,00 s", id="clock"),
                    dcc.Dropdown(id="speed", options=[{"label": f"{x}×", "value": x} for x in [.25,.5,1,2,4]], value=1,
                                 clearable=False, searchable=False)], className="transport-controls"),
                    dcc.Slider(id="seek", min=0, max=15, step=.02, value=0, marks=None,
                               tooltip={"placement": "bottom", "always_visible": False}, updatemode="mouseup")], className="transport"),
                html.Div([html.H3("Resposta temporal"), dcc.Checklist(id="focus", options=[{"label": "Ampliar respostas controladas", "value": "focus"}], value=[])], className="chart-heading"),
                html.Div([html.Div([html.H4("Ângulo de rolagem"), dcc.Graph(id="roll-chart", config={"displaylogo": False})], className="chart-panel wide"),
                          html.Div([html.H4("Velocidade angular"), dcc.Graph(id="velocity-chart", config={"displaylogo": False})], className="chart-panel"),
                          html.Div([html.H4("Esforço de controle"), dcc.Graph(id="torque-chart", config={"displaylogo": False})], className="chart-panel"),
                          html.Div([html.H4("Perturbação · inclinação efetiva da onda"), dcc.Graph(id="wave-chart", config={"displaylogo": False})], className="chart-panel wide")], className="charts"),
                html.Div([html.Div([html.H3("Desempenho do ensaio completo"), html.P("Métricas finais; independem do ponto da reprodução. Redução RMS relativa à malha aberta.")]),
                          html.Div([html.Button("↓ Dados CSV", id="export-csv"), html.Button("↓ Métricas CSV", id="export-metrics"),
                                    html.Button("↓ Configuração JSON", id="export-json")], className="export-buttons")], className="results-heading"),
                html.Div(id="metrics-table", children=table(INITIAL), className="table-wrap"),
                html.P("ISU é um indicador de esforço quadrático, não uma medição de energia elétrica. Animação em escala angular real; a linha d’água é uma referência visual.", className="small-note"),
            ], id="simulation-panel"),
            html.Div([
                html.H3("Ganhos dos controladores"),
                html.P("Ajuste os ganhos de cada controlador ou importe uma configuração JSON. As alterações serão aplicadas ao calcular um novo ensaio."),
                html.Div([html.Div([html.H4("PID · forma paralela"), html.Code("u = −Kp·φ + Ki·∫(−φ)dt − Kd·φ̇"),
                    html.Div([html.Label([n, dcc.Input(id=f"gain-pid-{i}", type="number", min=0, step="any", value=v)]) for i,(n,v) in enumerate(zip(["Kp", "Ki", "Kd"], DEFAULT_GAINS["PID"]))], className="gain-grid")], className="model-card"),
                    html.Div([html.H4("LQR · tempo discreto"), html.Code("u = −Kx  ·  Q = diag(Q11, Q22)"),
                    html.Div([html.Label([n, dcc.Input(id=f"gain-lqr-{i}", type="number", min=.000001, step="any", value=v)]) for i,(n,v) in enumerate(zip(["Q11", "Q22", "R"], DEFAULT_GAINS["LQR"]))], className="gain-grid")], className="model-card")], className="model-grid"),
                html.Div([html.H4("Fuzzy · Mamdani com centroide"), html.P("Três conjuntos gaussianos por variável: Negativo, Zero e Positivo. Cada par é [centro, largura]. Unidades internas: rad, rad/s e N·m."),
                    dcc.Textarea(id="gain-fuzzy", value=json.dumps(DEFAULT_GAINS["Fuzzy"], indent=2), className="fuzzy-editor"),
                    html.P("Ordem: φN, φZ, φP, velocidade N, Z, P, torque N, Z, P. Larguras devem ser positivas."),
                    html.Table([html.Thead(html.Tr([html.Th("φ \\ φ̇"), html.Th("N"), html.Th("Z"), html.Th("P")])),
                                html.Tbody([html.Tr([html.Th("N"),html.Td("P"),html.Td("P"),html.Td("Z")]),
                                            html.Tr([html.Th("Z"),html.Td("P"),html.Td("Z"),html.Td("N")]),
                                            html.Tr([html.Th("P"),html.Td("Z"),html.Td("N"),html.Td("N")])])]),
                    dcc.Graph(id="membership-chart", config={"displaylogo": False})], className="model-card"),
                html.Div([html.H3("Planta do ensaio calculado"), html.Div(id="derived"),
                    html.Code("(Ixx + Jxx)·φ̈ + Beq·φ̇ + Δ·GM·φ = Kext + u"),
                    html.P("Discretização exata ZOH. Frequência da onda = razão × ωd. Se ζ ≥ 1, a referência passa a ser ωn."),
                    html.P("O perfil multifrequencial é determinístico. O modelo não inclui dinâmica elétrica, velocidade ou saturação de momento angular da roda. O limite numérico de torque padrão é de ±100 N·m."),
                    html.P("Amostragem: estado inicial em t = 0; comando u[k] aplicado até t[k+1]. A última amostra não possui novo comando. IAE e ISU são calculados por somas retangulares.")], className="model-card"),
            ], id="model-panel", style={"display": "none"}),
            html.Div([
                html.H3("Sintonia por algoritmo genético"),
                html.P("Executada em segundo plano, separadamente da reprodução. O AG avalia os três cenários com os parâmetros atuais da barra lateral. Os ganhos encontrados só entram no próximo ensaio após serem aplicados."),
                html.Div([html.Label(["Controlador", dcc.Dropdown(id="ga-controller", options=list(DEFAULT_GAINS), value="PID", clearable=False)]),
                          html.Label(["Gerações", dcc.Input(id="ga-generations", type="number", min=1, max=300, step=1, value=20)]),
                          html.Button("Iniciar otimização", id="ga-start", className="primary"),
                          html.Button("Cancelar", id="ga-cancel")], className="ga-controls"),
                html.P("População 10 · seleção SSS · 5 pais · cruzamento em um ponto · mutação de um gene · seed 42. A configuração inicial é de 20 gerações e pode ser ajustada até 300."),
                html.Code("J = Σcenários [IAE(rad·s) + 0,001·ISU + 0,01·TV + 0,01·Chat]"),
                html.Div(id="ga-status", className="small-note", children="Nenhuma otimização em execução."),
                html.Progress(id="ga-progress", value=0, max=100),
                dcc.Graph(id="ga-chart", config={"displaylogo": False}),
                html.Button("Aplicar ganhos encontrados", id="ga-apply", disabled=True),
                html.Div(id="ga-apply-status", className="small-note"),
            ], id="ga-panel", style={"display": "none"}),
            html.Footer(["Richard Silva de Abreu", html.Span("TCC · Engenharia de Controle e Automação · 2026")]),
        ], className="main"),
    ], className="app-shell")


app.layout = layout


@app.callback(Output("simulation-panel", "style"), Output("model-panel", "style"), Output("ga-panel", "style"), Input("tabs", "value"))
def tabs(tab):
    return tuple({} if tab == name else {"display": "none"} for name in ["sim", "model", "ga"])


GAIN_IDS = [f"gain-pid-{i}" for i in range(3)]+[f"gain-lqr-{i}" for i in range(3)]+["gain-fuzzy"]

def read_gains(values):
    return validate_gains({"PID": list(values[:3]), "LQR": list(values[3:6]), "Fuzzy": json.loads(values[6])})


@app.callback(Output("result", "data"), Output("run-status", "children"),
              Input("run", "n_clicks"), [State(i, "value") for i in FIELD_IDS],
              State("scenario", "value"), State("controllers", "value"), [State(i, "value") for i in GAIN_IDS],
              prevent_initial_call=True, running=[(Output("run", "disabled"), True, False)])
def calculate(clicks, *values):
    try:
        n = len(FIELD_IDS)
        cfg = Config(**dict(zip([s[0] for s in CONFIG_FIELDS], values[:n])))
        result = simulate(cfg, values[n], values[n+1], read_gains(values[n+2:]))
        result["id"] = str(uuid.uuid4()); result["created_utc"] = datetime.now(timezone.utc).isoformat()
        return result, "Ensaio calculado. Os botões abaixo controlam a reprodução dos resultados."
    except (ValueError, TypeError, KeyError, OverflowError) as exc:
        return no_update, f"Não foi possível calcular: {exc} O ensaio anterior foi mantido."


@app.callback(Output("run-title", "children"), Output("metrics-table", "children"), Output("warnings", "children"),
              Output("monitor", "options"), Output("monitor", "value"), Output("seek", "max"),
              Output("seek", "step"), Output("derived", "children"), Input("result", "data"), State("monitor", "value"))
def describe(result, selected):
    names = list(result["series"])
    selected = selected if selected in names else names[-1]
    d = result["derived"]
    derived = html.Div([html.Div([html.Small(label), html.Strong(f"{d[key]:.5f} {unit}")]) for key,label,unit in
                       [("inertia", "Inércia total", "kg·m²"), ("wn", "ωn", "rad/s"), ("wd", "ωd", "rad/s"),
                        ("beq", "Beq", "N·m·s/rad"), ("wave_frequency", "Frequência da onda", "rad/s")]], className="derived-grid")
    warnings = [html.Div(w, className="warning") for w in result["warnings"]]
    return result["scenario_label"], table(result), warnings, names, selected, result["t"][-1], result["config"]["dt"], derived


@app.callback(Output("dirty", "children"), Output("decay-field", "style"),
              [Input(i, "value") for i in FIELD_IDS], Input("scenario", "value"), Input("controllers", "value"),
              [Input(i, "value") for i in GAIN_IDS], Input("result", "data"))
def dirty(*values):
    n = len(FIELD_IDS); scenario, controllers = values[n:n+2]; result = values[-1]
    try:
        config = dict(zip([s[0] for s in CONFIG_FIELDS], values[:n]))
        changed = config != result["config"] or scenario != result["scenario"] or set(controllers) != set(result["series"])-{"Sem controle"} or read_gains(values[n+2:-1]) != result["gains"]
    except (ValueError, TypeError):
        changed = True
    return ("Há alterações pendentes. Clique em Calcular ensaio para atualizar os resultados." if changed else ""), ({} if scenario == "damped" else {"display": "none"})


@app.callback([Output(i,"value") for i in FIELD_IDS], Output("scenario","value"), Output("controllers","value"),
              [Output(i,"value") for i in GAIN_IDS], Output("import-status","children"), Output("ga-apply-status","children"),
              Input("restore","n_clicks"), Input("upload","contents"), Input("ga-apply","n_clicks"),
              State("optimized-gains","data"), [State(i,"value") for i in FIELD_IDS],
              State("scenario","value"), State("controllers","value"), [State(i,"value") for i in GAIN_IDS], prevent_initial_call=True)
def restore_or_import(restore, upload, apply, optimized, *current):
    count = len(FIELD_IDS)+2+len(GAIN_IDS)
    try:
        if ctx.triggered_id == "restore":
            cfg, scenario, controllers, gains = Config(), "regular", list(DEFAULT_GAINS), deepcopy(DEFAULT_GAINS)
            message = "Parâmetros restaurados. Calcule o ensaio para aplicar."
        elif ctx.triggered_id == "ga-apply":
            if not optimized:
                raise PreventUpdate
            n = len(FIELD_IDS)
            gains = read_gains(current[n+2:]); gains[optimized["controller"]] = optimized["genes"]
            return [no_update]*(n+2)+gains["PID"]+gains["LQR"]+[json.dumps(gains["Fuzzy"],indent=2), no_update,
                "Ganhos aplicados aos campos. Clique em Calcular ensaio para usá-los."]
        else:
            if len(upload) > 150000:
                raise ValueError("Arquivo muito grande; limite de 100 KB.")
            data = json.loads(base64.b64decode(upload.split(",",1)[1], validate=True).decode("utf-8-sig"))
            cfg = Config(**data["config"]); cfg.validate()
            gains = validate_gains(data["gains"]); scenario = data["scenario"]
            controllers = data.get("controllers", list(DEFAULT_GAINS))
            if scenario not in NAMES or not isinstance(controllers,list) or any(c not in DEFAULT_GAINS for c in controllers):
                raise ValueError("Cenário ou controladores inválidos.")
            message = "Configuração importada. Clique em Calcular ensaio para aplicar."
        return [getattr(cfg,s[0]) for s in CONFIG_FIELDS]+[scenario,controllers]+gains["PID"]+gains["LQR"]+[json.dumps(gains["Fuzzy"],indent=2),message,""]
    except (ValueError, KeyError, TypeError, UnicodeError) as exc:
        return [no_update]*count+[f"Falha na importação: {exc}", no_update]


@app.callback(Output("download","data"), Input("export-csv","n_clicks"), Input("export-metrics","n_clicks"),
              Input("export-json","n_clicks"), State("result","data"), prevent_initial_call=True)
def export(csv_click, metrics_click, json_click, result):
    stem = f"nautica_{result['scenario']}"
    if ctx.triggered_id == "export-json":
        payload = {k:result[k] for k in ["config","gains","scenario","provenance"]}
        payload.update(schema_version=1, controllers=[n for n in result["series"] if n != "Sem controle"],
                       source_run=result["id"], note="Configuração do ensaio calculado; alterações pendentes não estão incluídas.")
        return dict(content=json.dumps(payload,ensure_ascii=False,indent=2),filename=stem+"_config.json",type="application/json")
    out = io.StringIO(); writer = csv.writer(out, delimiter=";")
    if ctx.triggered_id == "export-metrics":
        writer.writerow(["controlador","max_abs_phi_deg","rms_deg","reducao_rms_pct","iae_deg_s","iae_rad_s","isu_Nm2_s","tv_Nm","chat_Nm_s","saturacao_pct"])
        for name,s in result["series"].items():
            m=s["metrics"]; writer.writerow([name]+[m[k] for k in ["peak","rms","reduction","iae","iae_rad","isu","tv","chat"]]+[s["saturation"]])
        suffix = "_metricas.csv"
    else:
        writer.writerow(["tempo_s","onda_deg","torque_externo_Nm"]+[f"{name}_{v}" for name in result["series"] for v in ["phi_deg","vel_deg_s","torque_Nm"]])
        for i,t in enumerate(result["t"]):
            writer.writerow([t,result["wave"][i],result["external"][i]]+[s[k][i] for s in result["series"].values() for k in ["phi","velocity","torque"]])
        suffix = "_dados.csv"
    return dict(content="\ufeff"+out.getvalue(), filename=stem+suffix,type="text/csv;charset=utf-8")


@app.callback(Output("membership-chart","figure"), Input("gain-fuzzy","value"))
def membership(text):
    import numpy as np
    from plotly.subplots import make_subplots
    import plotly.graph_objects as go
    try:
        gs=deepcopy(DEFAULT_GAINS); gs["Fuzzy"]=json.loads(text); genes=validate_gains(gs)["Fuzzy"]
    except (ValueError,TypeError):
        return {"data":[],"layout":{"annotations":[{"text":"Corrija os parâmetros Fuzzy para visualizar as pertinências.","showarrow":False}],"paper_bgcolor":"#ffffff","font":{"color":"#505963"}}}
    fig=make_subplots(rows=1,cols=3,subplot_titles=["Ângulo (rad)","Velocidade (rad/s)","Torque (N·m)"])
    for j,(lo,hi) in enumerate([(-.5,.5),(-1,1),(-10,10)]):
        x=np.linspace(lo,hi,201)
        for i,(name,color) in enumerate(zip(["N","Z","P"],["#a16b2f","#2e7067","#78618c"])):
            center,width=genes[6*j+2*i:6*j+2*i+2]
            fig.add_trace(go.Scatter(x=x,y=np.exp(-(x-center)**2/(2*width**2)),name=name,line_color=color,legendgroup=name,showlegend=j==0),row=1,col=j+1)
    fig.update_layout(template="plotly_white",paper_bgcolor="#ffffff",plot_bgcolor="#ffffff",height=300,margin=dict(l=35,r=15,t=45,b=35),font=dict(family="Arial",color="#505963"))
    return fig


JOBS = {}; JOB_LOCK=threading.Lock()

@app.callback(Output("job-id","data"), Input("ga-start","n_clicks"), State("ga-controller","value"),
              State("ga-generations","value"), [State(i,"value") for i in FIELD_IDS], State("job-id","data"), prevent_initial_call=True)
def start_job(clicks,name,generations,*values):
    old=values[-1]
    with JOB_LOCK:
        # Local single-user app: allow only one worker to bound resource use.
        active=next((key for key,job in JOBS.items() if job["state"]=="running"),None)
        if active:
            return active
        # Bound retained history without discarding an active job.
        while len(JOBS)>20:
            JOBS.pop(next(iter(JOBS)))
        job_id=str(uuid.uuid4())
        JOBS[job_id]={"state":"running","generation":0,"total":generations,"fitness":[],"cancel":False,"controller":name}
    try:
        cfg=Config(**dict(zip([s[0] for s in CONFIG_FIELDS],values[:-1]))); cfg.validate()
        if name not in DEFAULT_GAINS or not isinstance(generations,(int,float)) or not float(generations).is_integer() or not 1<=generations<=300:
            raise ValueError("Escolha um controlador e de 1 a 300 gerações inteiras.")
    except (ValueError,TypeError) as exc:
        JOBS[job_id].update(state="error",error=str(exc)); return job_id
    def worker():
        try:
            def report(generation,fitness):
                with JOB_LOCK:
                    JOBS[job_id]["generation"]=generation; JOBS[job_id]["fitness"].append(fitness)
            genes,fitness=genetic_optimize(cfg,name,int(generations),report,lambda:JOBS[job_id]["cancel"])
            with JOB_LOCK:
                JOBS[job_id].update(state="cancelled" if JOBS[job_id]["cancel"] else "done",genes=genes,best=fitness,config=asdict(cfg))
        except Exception as exc:
            with JOB_LOCK:
                JOBS[job_id].update(state="error",error=str(exc))
    threading.Thread(target=worker,daemon=True).start()
    return job_id


@app.callback(Output("ga-cancel","title"), Input("ga-cancel","n_clicks"), State("job-id","data"), prevent_initial_call=True)
def cancel_job(clicks,job_id):
    with JOB_LOCK:
        if job_id in JOBS and JOBS[job_id]["state"]=="running":
            JOBS[job_id]["cancel"]=True
    return "Cancelamento solicitado; aguarde o término da avaliação atual."


@app.callback(Output("ga-status","children"),Output("ga-progress","value"),Output("ga-chart","figure"),
              Output("optimized-gains","data"),Output("ga-apply","disabled"),Output("ga-start","disabled"),
              Input("job-poll","n_intervals"),Input("job-id","data"))
def poll_job(ticks,job_id):
    fig={"data":[],"layout":{"paper_bgcolor":"#ffffff","plot_bgcolor":"#ffffff","font":{"color":"#505963","family":"Arial"},"xaxis":{"title":"Geração","gridcolor":"#e7e8e6"},"yaxis":{"title":"Melhor fitness","gridcolor":"#e7e8e6"},"margin":{"l":55,"r":20,"t":20,"b":45}}}
    with JOB_LOCK:
        job=deepcopy(JOBS.get(job_id))
    if not job:
        return "Nenhuma otimização em execução.",0,fig,None,True,False
    fig["data"]=[{"x":list(range(1,len(job["fitness"])+1)),"y":job["fitness"],"type":"scatter","mode":"lines","line":{"color":"#254b6c"}}]
    state=job["state"]; total=job["total"] or 1
    labels={"running":"Executando", "done":"Concluída", "cancelled":"Cancelada", "error":"Falhou"}
    msg=f"{labels[state]} · {job['controller']} · geração {job['generation']}/{total}"
    if job["cancel"] and state=="running": msg+=" · cancelamento solicitado"
    if state=="error": msg+=" · "+job.get("error","")
    if state=="done": msg+=f" · fitness {job['best']:.6f}. A sintonia usou os três cenários e os parâmetros capturados ao iniciar."
    optimized={"controller":job["controller"],"genes":job["genes"],"training_config":job["config"]} if state=="done" else None
    return msg,100*job["generation"]/total,fig,optimized,state!="done",state=="running"


app.clientside_callback(
    "window.dash_clientside.nautica.transport",
    Output("frame","data"), Output("ticker","disabled"), Output("seek","value"),Output("play","children"),
    Input("ticker","n_intervals"),Input("play","n_clicks"),Input("restart","n_clicks"),Input("seek","value"),Input("result","data"),
    State("frame","data"),State("speed","value"))

app.clientside_callback(
    "window.dash_clientside.nautica.render",
    Output("roll-chart","figure"),Output("velocity-chart","figure"),Output("torque-chart","figure"),Output("wave-chart","figure"),
    Output("live-phi","children"),Output("live-velocity","children"),Output("live-torque","children"),Output("live-external","children"),Output("clock","children"),
    *[Output(f"boat-{n.replace(' ','-')}","style") for n in ["Sem controle","PID","LQR","Fuzzy"]],
    *[Output(f"angle-{n.replace(' ','-')}","children") for n in ["Sem controle","PID","LQR","Fuzzy"]],
    *[Output(f"boat-card-{n.replace(' ','-')}","style") for n in ["Sem controle","PID","LQR","Fuzzy"]],
    Input("frame","data"),Input("result","data"),Input("monitor","value"),Input("focus","value"))


if __name__ == "__main__":
    import argparse
    parser=argparse.ArgumentParser(); parser.add_argument("--port",type=int,default=8050)
    args=parser.parse_args()
    print(f"\nNautica: http://127.0.0.1:{args.port}\nCtrl+C para encerrar.\n",flush=True)
    app.run(host="127.0.0.1",port=args.port,debug=False)
