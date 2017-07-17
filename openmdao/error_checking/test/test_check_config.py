import unittest

from six.moves import range

from openmdao.api import Problem, Group, IndepVarComp, ExecComp
from openmdao.devtools.testutil import TestLogger
from openmdao.error_checking.check_config import get_sccs, get_relevant_vars, compute_sys_graph


class MyComp(ExecComp):
    def __init__(self):
        super(MyComp, self).__init__(["y = 2.0*a", "z = 3.0*b"])


class TestCheckConfig(unittest.TestCase):

    def test_hanging_inputs(self):
        p = Problem(model=Group())
        root = p.model

        G1 = root.add_subsystem("G1", Group(), promotes=['*'])
        G2 = G1.add_subsystem("G2", Group(), promotes=['*'])
        C2 = G2.add_subsystem("C2", IndepVarComp('x', 1.0), promotes=['*'])
        C1 = G2.add_subsystem("C1", ExecComp('y=x*2.0+w'), promotes=['*'])

        G3 = root.add_subsystem("G3", Group())
        G4 = G3.add_subsystem("G4", Group())
        C3 = G4.add_subsystem("C3", ExecComp('y=x*2.0+u'), promotes=['*'])
        C4 = G4.add_subsystem("C4", ExecComp('y=x*2.0+v'))

        testlogger = TestLogger()
        p.setup(logger=testlogger)

        self.assertEqual(len(testlogger.get('warning')), 1)

        expected = [
            'G1.G2.C1.w',
            'G3.G4.C3.u',
            'G3.G4.C3.x',
            'G3.G4.C4.v',
            'G3.G4.C4.x'
        ]

        actual = testlogger.get('warning')[0].split('[', 1)[1].split(']')[0].split(',')
        actual = [a.strip().strip("'") for a in actual]

        self.assertEqual(expected, actual)

    def test_dataflow_1_level(self):

        p = Problem(model=Group())
        root = p.model

        indep = root.add_subsystem("indep", IndepVarComp('x', 1.0))
        C1 = root.add_subsystem("C1", MyComp())
        C2 = root.add_subsystem("C2", MyComp())
        C3 = root.add_subsystem("C3", MyComp())
        C4 = root.add_subsystem("C4", MyComp())

        root.connect("C4.y", "C2.a")
        root.connect("C4.y", "C3.a")
        root.connect("C2.y", "C1.a")
        root.connect("C1.y", "C4.a")

        # make sure no system has dangling inputs so we avoid that warning
        root.connect("indep.x", "C1.b")
        root.connect("indep.x", "C2.b")
        root.connect("indep.x", "C3.b")
        root.connect("indep.x", "C4.b")

        testlogger = TestLogger()
        p.setup(logger=testlogger)

        warnings = testlogger.get('warning')
        self.assertEqual(len(warnings), 2)

        self.assertEqual(warnings[0], "Group '' has the following cycles: [['C1', 'C2', 'C4']]")
        self.assertEqual(warnings[1], "System 'C3' executes out-of-order with respect to its source systems ['C4']")

    def test_dataflow_multi_level(self):

        p = Problem(model=Group())
        root = p.model

        indep = root.add_subsystem("indep", IndepVarComp('x', 1.0))

        G1 = root.add_subsystem("G1", Group())

        C1 = G1.add_subsystem("C1", MyComp())
        C2 = G1.add_subsystem("C2", MyComp())

        C3 = root.add_subsystem("C3", MyComp())
        C4 = root.add_subsystem("C4", MyComp())

        root.connect("C4.y", "G1.C2.a")
        root.connect("C4.y", "C3.a")
        root.connect("G1.C2.y", "G1.C1.a")
        root.connect("G1.C1.y", "C4.a")

        # make sure no system has dangling inputs so we avoid that warning
        root.connect("indep.x", "G1.C1.b")
        root.connect("indep.x", "G1.C2.b")
        root.connect("indep.x", "C3.b")
        root.connect("indep.x", "C4.b")

        testlogger = TestLogger()
        p.setup(logger=testlogger)

        warnings = testlogger.get('warning')
        self.assertEqual(len(warnings), 3)

        self.assertEqual(warnings[0], "Group '' has the following cycles: [['C4', 'G1']]")
        self.assertEqual(warnings[1], "System 'C3' executes out-of-order with respect to its source systems ['C4']")
        self.assertEqual(warnings[2], "System 'G1.C1' executes out-of-order with respect to its source systems ['G1.C2']")

        # test comps_only cycle check
        sccs = [sorted(s) for s in get_sccs(root, comps_only=True) if len(s) > 1]
        self.assertEqual([['C4', 'G1.C1', 'G1.C2']], sccs)

    def test_relevance(self):
        p = Problem()
        model = p.model

        indep1 = model.add_subsystem("indep1", IndepVarComp('x', 1.0))
        G1 = model.add_subsystem('G1', Group())
        G1.add_subsystem('C1', ExecComp(['x=2.0*a', 'y=2.0*b', 'z=2.0*a']))
        G1.add_subsystem('C2', ExecComp(['x=2.0*a', 'y=2.0*b', 'z=2.0*b']))
        model.add_subsystem("C3", ExecComp(['x=2.0*a', 'y=2.0*b+3,0*c']))
        model.add_subsystem("C4", ExecComp(['x=2.0*a', 'y=2.0*b']))
        indep2 = model.add_subsystem("indep2", IndepVarComp('x', 1.0))
        G2 = model.add_subsystem('G2', Group())
        G2.add_subsystem('C5', ExecComp(['x=2.0*a', 'y=2.0*b+3.0*c']))
        G2.add_subsystem('C6', ExecComp(['x=2.0*a', 'y=2.0*b+3.0*c']))
        G2.add_subsystem('C7', ExecComp(['x=2.0*a', 'y=2.0*b']))
        model.add_subsystem("C8", ExecComp(['y=1.5*a+2.0*b']))
        
        model.connect('indep1.x', 'G1.C1.a')
        model.connect('indep2.x', 'G2.C6.a')
        model.connect('G1.C1.x', 'G1.C2.b')
        model.connect('G1.C2.z', 'C4.b')
        model.connect('G1.C1.z', ('C3.b', 'C3.c', 'G2.C5.a'))
        model.connect('C3.y', 'G2.C5.b')
        model.connect('C3.x', 'C4.a')
        model.connect('G2.C6.y', 'G2.C7.b')
        model.connect('G2.C5.x', 'C8.b')
        model.connect('G2.C7.x', 'C8.a')
        
        p.setup(check=False)
        
        g = compute_sys_graph(p.model, p.model._conn_global_abs_in2out, comps_only=True, save_vars=True)
        relevant = get_relevant_vars(g, ['indep1.x', 'indep2.x'], ['C8.y'])

        indep1_ins = set(['C3.b', 'C3.c', 'C8.b', 'G1.C1.a', 'G2.C5.a', 'G2.C5.b'])
        indep1_outs = set(['C3.y', 'C8.y', 'G1.C1.z', 'G2.C5.x', 'indep1.x'])
        indep1_sys = set(['C3', 'C8', 'G1.C1', 'G2.C5', 'indep1'])
        
        inputs, outputs, systems = relevant['indep1.x']['C8.y']
        
        self.assertEqual(inputs, indep1_ins)
        self.assertEqual(outputs, indep1_outs)
        self.assertEqual(systems, indep1_sys)

        inputs, outputs, systems = relevant['C8.y']['indep1.x']
        
        self.assertEqual(inputs, indep1_ins)
        self.assertEqual(outputs, indep1_outs)
        self.assertEqual(systems, indep1_sys)
        
        indep2_ins = set(['C8.a', 'G2.C6.a', 'G2.C7.b'])
        indep2_outs = set(['C8.y', 'G2.C6.y', 'G2.C7.x', 'indep2.x'])
        indep2_sys = set(['C8', 'G2.C6', 'G2.C7', 'indep2'])
        
        inputs, outputs, systems = relevant['indep2.x']['C8.y']
        
        self.assertEqual(inputs, indep2_ins)
        self.assertEqual(outputs, indep2_outs)
        self.assertEqual(systems, indep2_sys)
        
        inputs, outputs, systems = relevant['C8.y']['indep2.x']
        
        self.assertEqual(inputs, indep2_ins)
        self.assertEqual(outputs, indep2_outs)
        self.assertEqual(systems, indep2_sys)
        
        inputs, outputs, systems = relevant['C8.y']['@all']

        self.assertEqual(inputs, indep1_ins | indep2_ins)
        self.assertEqual(outputs, indep1_outs | indep2_outs)
        self.assertEqual(systems, indep1_sys | indep2_sys)


    def test_multi_cycles(self):
        p = Problem(model=Group())
        root = p.model

        indep = root.add_subsystem("indep", IndepVarComp('x', 1.0))

        def make_cycle(root, start, end):
            # systems within a cycle will be declared out of order, but
            # should not be reported since they're internal to a cycle.
            for i in range(end, start-1, -1):
                root.add_subsystem("C%d" % i, MyComp())

            for i in range(start, end):
                root.connect("C%d.y" % i, "C%d.a" % (i+1))
            root.connect("C%d.y" % end, "C%d.a" % start)

        make_cycle(root, 1, 3)

        root.add_subsystem("N1", MyComp())

        make_cycle(root, 11, 13)

        root.add_subsystem("N2", MyComp())

        make_cycle(root, 21, 23)

        root.add_subsystem("N3", MyComp())

        root.connect("N1.z", "C12.b")
        root.connect("C13.z", "N2.b")
        root.connect("N2.z", "C21.b")
        root.connect("C23.z", "N3.b")
        root.connect("N3.z", "C2.b")
        root.connect("C11.z", "C3.b")

        testlogger = TestLogger()
        p.setup(logger=testlogger)

        warnings = testlogger.get('warning')
        self.assertEqual(len(warnings), 4)

        self.assertTrue("The following inputs are not connected:" in warnings[0])
        self.assertEqual(warnings[1], "Group '' has the following cycles: [['C11', 'C12', 'C13'], ['C21', 'C22', 'C23'], ['C1', 'C2', 'C3']]")
        self.assertEqual(warnings[2], "System 'C2' executes out-of-order with respect to its source systems ['N3']")
        self.assertEqual(warnings[3], "System 'C3' executes out-of-order with respect to its source systems ['C11']")


if __name__ == "__main__":
    unittest.main()
