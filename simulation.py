"""Modelo de roll do Anexo A do TCC v7, sem dependências de interface.

SI internamente. A amostra de estado em t=0 é a condição inicial;
u[k] é aplicado no intervalo [t[k], t[k+1]).
"""
from copy import deepcopy
from dataclasses import asdict, dataclass
import math
import numpy as np
from scipy.signal import cont2discrete
from scipy.linalg import solve_discrete_are
import skfuzzy as fuzz

NAMES = {"regular": "Onda senoidal", "damped": "Impacto amortecido", "multi": "Mar multifrequencial"}
COLORS = {"Sem controle": "#747b82", "PID": "#a16b2f", "LQR": "#2e7067", "Fuzzy": "#78618c"}
DEFAULT_GAINS = {
    "PID": [9.907, 0.075, 4.928],
    "LQR": [999.544, 1.453, 0.154],
    "Fuzzy": [-0.261, 0.299, 0.006, 0.116, 0.118, 0.131,
              -0.549, 0.243, 0.120, 0.157, 0.875, 0.219,
              -7.301, 4.971, -1.812, 1.040, 7.083, 4.520],
}

@dataclass
class Config:
    ixx: float = 0.0444
    jxx: float = 0.00888
    displacement: float = 63.2745
    gm: float = 0.0229183
    zeta: float = 0.076
    chi: float = 0.80
    amplitude: float = 5.0
    frequency_ratio: float = 0.5
    decay: float = 0.2
    duration: float = 15.0
    dt: float = 0.02
    phi0: float = 0.0
    velocity0: float = 0.0
    torque_limit: float = 100.0

    def validate(self):
        for name, value in asdict(self).items():
            if not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(f"Valor inválido para {name}.")
        limits = {"ixx": (1e-6, 10000), "jxx": (0, 10000),
                  "displacement": (1e-4, 1e7), "gm": (1e-6, 100),
                  "zeta": (0, 5), "chi": (0, 10), "amplitude": (0, 30),
                  "frequency_ratio": (0.01, 5), "decay": (0, 10),
                  "duration": (1, 120), "dt": (0.005, 0.1),
                  "phi0": (-30, 30), "velocity0": (-180, 180),
                  "torque_limit": (0.001, 10000)}
        for name, (lo, hi) in limits.items():
            if not lo <= getattr(self, name) <= hi:
                raise ValueError(f"{name}: informe um valor entre {lo} e {hi}.")
        if self.duration / self.dt > 12000:
            raise ValueError("Limite de 12.000 passos por ensaio. Aumente Δt ou reduza a duração.")

    def derived(self):
        inertia = self.ixx + self.jxx
        wn = math.sqrt(self.displacement * self.gm / inertia)
        wd = wn * math.sqrt(max(0, 1 - self.zeta**2))
        # Same default frequency as executable code, omega_d/2 (not omega_n/2 in prose).
        base = wd if wd > 0 else wn
        return {"inertia": inertia, "wn": wn, "wd": wd,
                "beq": 2 * self.zeta * wn * inertia,
                "wave_frequency": self.frequency_ratio * base}

    def matrices(self):
        d = self.derived()
        a = np.array([[0, 1], [-d["wn"]**2, -2*self.zeta*d["wn"]]])
        b = np.array([[0], [1/d["inertia"]]])
        ad, bd, _, _, _ = cont2discrete((a, b, np.eye(2), np.zeros((2, 1))), self.dt)
        return ad, bd[:, 0]


def validate_gains(gains):
    if not isinstance(gains, dict) or set(gains) != set(DEFAULT_GAINS):
        raise ValueError("Os ganhos devem conter PID, LQR e Fuzzy.")
    clean = {}
    for name, defaults in DEFAULT_GAINS.items():
        a = np.asarray(gains[name], dtype=float)
        if a.shape != (len(defaults),) or not np.isfinite(a).all() or np.max(np.abs(a)) > 1e6:
            raise ValueError(f"Parâmetros inválidos para {name}.")
        if name == "PID" and (a < 0).any():
            raise ValueError("Ganhos PID devem ser não negativos.")
        if name == "LQR" and (a <= 0).any():
            raise ValueError("Q11, Q22 e R devem ser positivos.")
        if name == "Fuzzy" and (a[1::2] <= 0).any():
            raise ValueError("As larguras gaussianas devem ser positivas.")
        clean[name] = a.tolist()
    return clean


def wave(t, cfg, scenario):
    w = cfg.derived()["wave_frequency"]
    amp = np.radians(cfg.amplitude)
    if scenario == "regular":
        return amp * np.sin(w*t)
    if scenario == "damped":
        return amp * np.exp(-cfg.decay*t) * np.sin(w*t)
    if scenario == "multi":
        return amp * (0.5*np.sin(0.8*w*t) + 0.3*np.sin(w*t+0.5) + 0.2*np.sin(1.2*w*t+1))
    raise ValueError("Cenário desconhecido.")


class Controller:
    def __init__(self, name, gains, cfg, ad, bd):
        self.name, self.genes, self.cfg = name, gains, cfg
        self.integral = 0.0
        if name == "LQR":
            q = np.diag(gains[:2]); r = np.array([[gains[2]]]); b = bd[:, None]
            p = solve_discrete_are(ad, b, q, r)
            self.k = np.linalg.solve(r+b.T@p@b, b.T@p@ad)[0]
        if name == "Fuzzy":
            self.domains = [np.linspace(-0.5, 0.5, 101), np.linspace(-1, 1, 101), np.linspace(-10, 10, 201)]
            self.mfs = [[fuzz.gaussmf(x, gains[6*j+2*i], gains[6*j+2*i+1]) for i in range(3)]
                        for j, x in enumerate(self.domains)]

    def command(self, state):
        phi, velocity = state
        if self.name == "Sem controle":
            return 0.0
        if self.name == "PID":
            kp, ki, kd = self.genes
            self.integral -= phi * self.cfg.dt
            u = -kp*phi + ki*self.integral - kd*velocity
        elif self.name == "LQR":
            u = -float(self.k@state)
        else:
            values = [phi, velocity]
            m = [[float(np.interp(np.clip(v, x[0], x[-1]), x, mf)) for mf in fs]
                 for v, x, fs in zip(values, self.domains, self.mfs)]
            n, z, p = m[0]; dn, dz, dp = m[1]
            wp = max(min(n, dn), min(n, dz), min(z, dn))
            wz = max(min(n, dp), min(z, dz), min(p, dn))
            wn = max(min(p, dp), min(p, dz), min(z, dp))
            agg = np.maximum.reduce([np.minimum(wn, self.mfs[2][0]),
                                     np.minimum(wz, self.mfs[2][1]), np.minimum(wp, self.mfs[2][2])])
            u = float(fuzz.defuzz(self.domains[2], agg, "centroid")) if np.sum(agg) else 0.0
        if not math.isfinite(u):
            raise ValueError("Controlador produziu um torque não finito.")
        return float(np.clip(u, -self.cfg.torque_limit, self.cfg.torque_limit))


def metrics(states, torque, dt):
    # Right-end rectangles match the fitness accumulation in the original notebook.
    phi = states[1:, 0]
    differences = np.diff(torque)
    return {"peak": float(np.degrees(np.max(np.abs(states[:, 0])))),
            "rms": float(np.degrees(np.sqrt(np.mean(phi**2)))),
            "iae": float(np.degrees(np.sum(np.abs(phi))*dt)),
            "iae_rad": float(np.sum(np.abs(phi))*dt),
            "isu": float(np.sum(torque**2)*dt),
            "tv": float(np.sum(np.abs(differences))),
            "chat": float(np.sqrt(np.mean((differences/dt)**2))) if len(differences) else 0.0}


def simulate(cfg=None, scenario="regular", controllers=None, gains=None):
    cfg = cfg or Config(); cfg.validate()
    gains = validate_gains(gains or deepcopy(DEFAULT_GAINS))
    controllers = list(controllers if controllers is not None else DEFAULT_GAINS)
    if any(name not in DEFAULT_GAINS for name in controllers):
        raise ValueError("Controlador desconhecido.")
    names = ["Sem controle"] + list(dict.fromkeys(controllers))
    ad, bd = cfg.matrices()
    steps = int(round(cfg.duration/cfg.dt))
    t = np.arange(steps+1) * cfg.dt
    alpha = wave(t, cfg, scenario)
    external = cfg.displacement*cfg.gm*cfg.chi*alpha
    series = {}; warnings = []
    for name in names:
        ctrl = Controller(name, gains.get(name), cfg, ad, bd)
        states = np.zeros((steps+1, 2)); states[0] = np.radians([cfg.phi0, cfg.velocity0])
        u = np.zeros(steps)
        for k in range(steps):
            u[k] = ctrl.command(states[k])
            states[k+1] = ad@states[k] + bd*(external[k]+u[k])
            if not np.isfinite(states[k+1]).all() or np.max(np.abs(states[k+1])) > 1e6:
                raise ValueError(f"A resposta de {name} divergiu. Revise os parâmetros e os ganhos.")
        met = metrics(states, u, cfg.dt)
        if met["peak"] > 10:
            warnings.append(f"{name}: rolagem acima de 10°; fora da aproximação de pequenos ângulos adotada.")
        saturation = float(np.mean(np.abs(u) >= cfg.torque_limit*(1-1e-10))*100)
        # Terminal torque has no following interval: null avoids inventing an extra command.
        series[name] = {"phi": np.degrees(states[:, 0]).tolist(),
                        "velocity": np.degrees(states[:, 1]).tolist(),
                        "torque": u.tolist()+[None], "metrics": met,
                        "saturation": saturation, "color": COLORS[name]}
    baseline = series["Sem controle"]["metrics"]["rms"]
    for s in series.values():
        s["metrics"]["reduction"] = (100*(1-s["metrics"]["rms"]/baseline)) if baseline > 1e-12 else None
    return {"config": asdict(cfg), "derived": cfg.derived(), "scenario": scenario,
            "scenario_label": NAMES[scenario], "gains": gains, "t": t.tolist(),
            "wave": np.degrees(alpha).tolist(), "external": external.tolist(),
            "series": series, "warnings": warnings,
            "provenance": "Ganhos iniciais transcritos das Tabelas 3 e 4, arredondados a 3 casas; modelo do Anexo A, TCC v7."}


def genetic_optimize(cfg, name, generations=20, on_generation=None, cancelled=None):
    """AG separado da reprodução. Avalia os três cenários, como no TCC."""
    import pygad
    spaces = {"PID": [(0, 10)]*3, "LQR": [(0.1, 1000), (0.1, 1000), (0.1, 10)],
              "Fuzzy": [(-0.5,-0.1),(.05,.3),(-.1,.1),(.05,.3),(.1,.5),(.05,.3),
                        (-1,-.1),(.1,.5),(-.2,.2),(.1,.5),(.1,1),(.1,.5),
                        (-10,-1),(1,5),(-2,2),(1,5),(1,10),(1,5)]}
    def fitness(ga, solution, index):
        if cancelled and cancelled():
            return 1e-9
        try:
            gs = deepcopy(DEFAULT_GAINS); gs[name] = list(solution)
            cost = 0.0
            for scenario in NAMES:
                result = simulate(cfg, scenario, [name], gs)
                m = result["series"][name]["metrics"]
                cost += m["iae_rad"]+.001*m["isu"]+.01*m["tv"]+.01*m["chat"]
            return 1/(cost+1e-6) if math.isfinite(cost) else 1e-9
        except (ValueError, np.linalg.LinAlgError, OverflowError):
            return 1e-9
    def generation(ga):
        if on_generation:
            on_generation(ga.generations_completed, float(np.max(ga.last_generation_fitness)))
        if cancelled and cancelled():
            return "stop"
    ga = pygad.GA(num_generations=generations, num_parents_mating=5,
                  fitness_func=fitness, sol_per_pop=10, num_genes=len(spaces[name]),
                  gene_space=[{"low": lo, "high": hi} for lo, hi in spaces[name]],
                  mutation_num_genes=1, parent_selection_type="sss",
                  crossover_type="single_point", mutation_type="random",
                  save_best_solutions=False, random_seed=42, on_generation=generation)
    ga.run()
    genes, fit, _ = ga.best_solution()
    return genes.tolist(), float(fit)
