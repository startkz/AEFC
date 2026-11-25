"""Contract and interface tests against the existing hydraulic SIL plant."""
import ast
import inspect
import textwrap
import tempfile
import unittest
from pathlib import Path
import numpy as np

from experiments.hydro_valve.run_hydro_valve_cps import Config, predict_next
from experiments.hydro_valve.run_tdsc_contract_chain import (
    interval_step, certified_margin, release_command,
    state_uncertainty, UnprivilegedController, run_episode,
)

class ContractTests(unittest.TestCase):
    def setUp(self):
        self.c=Config()

    def test_interval_contains_every_random_plant_successor(self):
        """Test 500 random nonlinear plant/command/attack/exogenous samples."""
        rng=np.random.default_rng(20261125)
        c=self.c
        for _ in range(500):
            x=np.array([rng.uniform(.96,1.04),rng.uniform(.40,.55),rng.uniform(.35,.48),
                        rng.uniform(.98,1.02),rng.uniform(.1,.95),rng.uniform(.1,.95)])
            delta=np.array([.001,.001,.001,.001,.003,.003]);lo=x-delta;hi=x+delta
            u=rng.uniform(c.command_attack_bound,1-c.command_attack_bound,2)
            post=rng.uniform(-c.command_attack_bound,c.command_attack_bound,2)
            qin=c.qin_nominal+rng.uniform(-c.qin_uncertainty,c.qin_uncertainty)
            load=c.load_nominal+rng.uniform(-c.load_uncertainty,c.load_uncertainty)
            actual=predict_next(x,u,qin,load,c,post)
            lb,ub=interval_step(lo,hi,u,c)
            self.assertTrue(np.all(actual>=lb-1e-11) and np.all(actual<=ub+1e-11),
                            msg=(x,u,actual,lb,ub))

    def test_no_unverified_backup_execution(self):
        c=self.c
        lo=np.array([1.2,.5,.4,1,.5,.5])
        hi=lo+.001
        out,status,margin,n=release_command(lo,hi,np.array([.5,.5]),np.array([.5,.5]),c)
        self.assertIsNone(out);self.assertEqual(status,'UNCERTIFIED_INITIAL_SET')
        self.assertIsNone(margin)

    def test_positive_margin_verified_for_released_command(self):
        c=self.c
        x=np.array([1,.46,.40,.995,.46/c.q_coeff[0],.40/c.q_coeff[1]])
        z=(x-np.array([1,*c.q_ref,1,*np.array(c.q_ref)/np.array(c.q_coeff)]))/np.array(c.observation_scales)
        lo,hi=state_uncertainty(z,c)
        command,status,margin,_=release_command(lo,hi,np.array([.85,.82]),np.array([.85,.82]),c)
        if command is None: self.fail('Expected simple safe initial point to have a feasible command')
        self.assertGreaterEqual(margin,-1e-12)
        self.assertGreaterEqual(certified_margin(lo,hi,command,c),-1e-12)
        self.assertTrue(status.startswith('CERTIFIED_'))

    def test_controller_decision_ast_has_no_oracle_fields(self):
        tree=ast.parse(textwrap.dedent(inspect.getsource(UnprivilegedController.decide)))
        names={n.id for n in ast.walk(tree) if isinstance(n,ast.Name)}
        self.assertFalse(names.intersection({'plant','true_before','true_after','scenario',
                                             'attack_active','malicious','seed','theta_shadow',
                                             'cleanBelief','oracle','tape'}))
        args=[a.arg for a in next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef)).args.args]
        self.assertEqual(args,['self','packet','memory'])

    def test_smoke_runs_original_sil_plant(self):
        from dataclasses import replace
        c=replace(self.c,steps=260,load_uncertainty=.020,qin_uncertainty=.008)
        with tempfile.TemporaryDirectory() as directory:
            row=run_episode(248,'joint',c,Path(directory))
            self.assertIn('initial_outside_recovery',row)
            self.assertTrue((Path(directory)/'seed_248_joint.jsonl').is_file())
            self.assertLessEqual(row['steps'],c.steps)
            if row['failure'] is None:
                self.assertEqual(row['violations'],0)

if __name__=='__main__': unittest.main()
