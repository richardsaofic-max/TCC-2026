from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/".deps"))
import unittest
import numpy as np
from simulation import Config,simulate,DEFAULT_GAINS,genetic_optimize,validate_gains


class PhysicsTests(unittest.TestCase):
    def test_rest_equilibrium(self):
        r=simulate(Config(amplitude=0),controllers=["PID","LQR"])
        for s in r["series"].values():
            self.assertEqual(max(np.abs(s["phi"])),0)
            self.assertIsNone(s["metrics"]["reduction"])

    def test_unforced_analytic_response(self):
        cfg=Config(amplitude=0,phi0=2,zeta=.076)
        r=simulate(cfg,controllers=[]); t=np.array(r["t"]);d=cfg.derived()
        exact=2*np.exp(-cfg.zeta*d["wn"]*t)*(np.cos(d["wd"]*t)+cfg.zeta*d["wn"]/d["wd"]*np.sin(d["wd"]*t))
        np.testing.assert_allclose(r["series"]["Sem controle"]["phi"],exact,atol=1e-11)

    def test_published_baseline_and_pid(self):
        r=simulate()
        self.assertAlmostEqual(r["series"]["Sem controle"]["metrics"]["peak"],6.2697,places=4)
        self.assertAlmostEqual(r["series"]["PID"]["metrics"]["peak"],.3712,places=4)

    def test_scenarios_and_metrics(self):
        for scenario in ["regular","damped","multi"]:
            r=simulate(scenario=scenario)
            self.assertEqual(r["t"][0],0);self.assertEqual(r["t"][-1],15)
            for name,s in r["series"].items():
                self.assertEqual(len(s["phi"]),751);self.assertIsNone(s["torque"][-1])
                u=np.array(s["torque"][:-1]);phi=np.array(s["phi"][1:])
                self.assertAlmostEqual(s["metrics"]["isu"],float(np.dot(u,u)*.02))
                self.assertAlmostEqual(s["metrics"]["iae"],float(np.sum(np.abs(phi))*.02))
                self.assertTrue(all(np.isfinite(v) for k,v in s["metrics"].items() if v is not None))
                if name!="Sem controle":self.assertLess(s["metrics"]["rms"],r["series"]["Sem controle"]["metrics"]["rms"])

    def test_saturation_and_domain_warning(self):
        r=simulate(Config(phi0=15,torque_limit=.01),controllers=["PID"])
        self.assertTrue(r["warnings"])
        self.assertLessEqual(max(abs(v) for v in r["series"]["PID"]["torque"][:-1]),.01)
        self.assertGreater(r["series"]["PID"]["saturation"],0)

    def test_reject_bad_inputs(self):
        for cfg in [Config(dt=0),Config(gm=-1),Config(amplitude=float('nan'))]:
            with self.assertRaises(ValueError):simulate(cfg)
        gs={k:list(v) for k,v in DEFAULT_GAINS.items()};gs["Fuzzy"][1]=0
        with self.assertRaises(ValueError):validate_gains(gs)

    def test_ga_executes_and_reproduces(self):
        cfg=Config(duration=1,dt=.05)
        a,fa=genetic_optimize(cfg,"PID",1)
        b,fb=genetic_optimize(cfg,"PID",1)
        np.testing.assert_allclose(a,b);self.assertEqual(fa,fb);self.assertGreater(fa,1e-9)


class WebTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import app
        cls.module=app;cls.client=app.server.test_client()

    def test_serves_local_application(self):
        for path in ["/","/_dash-layout","/_dash-dependencies","/assets/replay.js","/assets/style.css"]:
            with self.client.get(path) as response:
                self.assertEqual(response.status_code,200,path)

    def test_calculate_callback(self):
        m=self.module
        key=next(k for k in m.app.callback_map if k.startswith('..result.data'))
        values=[getattr(Config(),s[0]) for s in m.CONFIG_FIELDS]+["multi",["PID","LQR","Fuzzy"]]+DEFAULT_GAINS["PID"]+DEFAULT_GAINS["LQR"]+[__import__('json').dumps(DEFAULT_GAINS["Fuzzy"])]
        states=[{"id":i,"property":"value","value":v} for i,v in zip(m.FIELD_IDS+["scenario","controllers"]+m.GAIN_IDS,values)]
        response=self.client.post('/_dash-update-component',json={"output":key,"outputs":[{"id":"result","property":"data"},{"id":"run-status","property":"children"}],"changedPropIds":["run.n_clicks"],"inputs":[{"id":"run","property":"n_clicks","value":1}],"state":states})
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json["response"]["result"]["data"]["scenario"],"multi")


if __name__=='__main__':unittest.main()
