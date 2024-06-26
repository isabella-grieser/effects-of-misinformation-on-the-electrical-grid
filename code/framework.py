import math
import pytz

#from sim.parameterEstimator import *
from sim.diffParamEstimator import *
from gen.model import *
from sim.simulator import Simulator
from demandlib import bdew

class EstimationFramework:

    def __init__(self, config, year=2013, plot=True, save=False, save_path="./output/video.mp4"):
        self.config = config
        self.year = year
        self.plot = plot
        self.threshold = None
        self.save = save
        self.save_path = save_path

    def estimate_power_outage(self, start, action_start=None, data=None,
                              factor=1,
                              days=1, beta=0.1, alpha=0.4,
                              p_verify=0.4, iterations=200,
                              y_max=5000, index_shift=100,
                              minutes=15, estimation_end_time=None,
                              degree_ratio=0.02):

        # estimate parameters
        if data is not None:
            vals = data

            start_time, time_step = 0, 1
            beta, alpha, p_verify = 0.1, 0.4, 0.4

            if estimation_end_time is None:
                estimation_end_time = len(vals)
            #return_dict = solve_params(s, i, r, start_time, time_step, vals, beta, alpha, degree_ratio,
            #                           p_verify, estimation_end_time)

            return_dict = solve_params(vals, beta, alpha, p_verify, 1000, degree_ratio, estimation_end_time)
            # create dynamic config for model generation
            nodes = self.config["network"]["nodes"]
            edges = int(degree_ratio * nodes)

            model_config = {
                "seed": self.config["seed"],
                "edges": degree_ratio
            }


            social_network_model = create_social_network_graph(nodes, "barabasi_albert", model_config)
            self.config["sim"]["p_verify"] = return_dict["p_verify"]
            self.config["sim"]["alpha"] = return_dict["alpha"]
            # define b as = k * b_i /N
            self.config["sim"]["beta"] = 2 * return_dict["beta"] * degree_ratio / nodes

            print(f"estimated params: p_verify: {self.config['sim']['p_verify']}, "
                f"alpha: {self.config['sim']['alpha']}, beta: {self.config['sim']['beta']}"
                f" N: {return_dict['n']}")
        else:
            model_config = {
                "seed": self.config["seed"],
                "edges": round(degree_ratio * self.config["network"]["nodes"])
            }
            social_network_model = create_social_network_graph(self.config["network"]["nodes"],
                                                               "barabasi_albert", model_config)

        social_network_model = define_appliance_use(social_network_model, self.config["model_args"])
        social_network_model = define_availability(social_network_model, self.config["network"])

        # load profiles are all in kWh
        load_profile = bdew.elec_slp.ElecSlp(self.year)
        df = load_profile.get_profile({'h0': self.year})
        x = df.index.to_list()
        x = [x_i.replace(tzinfo=pytz.UTC) for x_i in x]
        y = df.h0.apply(lambda h: h * factor).to_list()

        comparable_starts = [x_i[0] for x_i in enumerate(x) if x_i[1].time() > start.time()
                             and x_i[1].day == start.day and x_i[1].month == start.month]
        start_index = comparable_starts[0] - index_shift
        spread_start = x[comparable_starts[0]]
        y_val = [y[start_index:]]
        x_val = x[start_index:]

        simulator = Simulator(social_network_model, x_val, y_val, args=self.config["sim"],
                              seed=self.config["seed"], spread_start=spread_start, si="kW",
                              power_start=action_start, days=days, y_max=y_max,
                              nr_init_nodes=1, minutes=minutes)

        x_all, y_true, y_ref, s_true, i_true, r_true = \
            simulator.iterate(iterations, plot=self.plot, save=self.save,
                              save_name=self.save_path, intervall_time=50)

        self.threshold = simulator.power_thresh
        # find first occurrence where value is true
        index = next(iter([y_i[0] for y_i in enumerate(y_ref) if y_i[1] > self.threshold]), -1)

        return index, x_all, y_true, y_ref, s_true, i_true, r_true
