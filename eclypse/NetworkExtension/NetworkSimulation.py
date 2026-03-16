from eclypse.simulation.simulation import Simulation
import pandas as pd


class NetworkSimulation(Simulation):

    def __init__(self, infrastructure, simulation_config=None):
        super().__init__(infrastructure, simulation_config)
        self.network_results = []
        self.current_time_s = 0.0

    def run_network_ticks(self, duration_ticks: int, tick_duration_s: float = 0.001):
        """
        Runs the network simulation for a specified number of ticks.
        Each tick represents a discrete time step in the simulation, during which applications can generate traffic,
        and the infrastructure will simulate packet routing and delivery.
        """
        self.logger.info(f"Starting Network Simulation for {duration_ticks} ticks...")
        self.network_results = []
        self.current_time_s = 0.0
        apps = self.applications.values()

        for tick in range(1, duration_ticks + 1):
            for app in apps:
                if hasattr(app, "generate_traffic_for_tick"):
                    packets = app.generate_traffic_for_tick(tick)

                    for packet in packets:
                        result = self.infrastructure.simulate_packet_routing(
                            packet=packet,  
                            start_time=self.current_time_s
                        )
                        if result['status'] == 'DELIVERED':
                            self.network_results.append({
                                "Tick": tick,
                                "Packet_ID": packet['id'],
                                "App": app.name,
                                "Src": packet['src'],
                                "Dst": packet['dst'],
                                "Start_Time": self.current_time_s,
                                "End_Time": result['end_time'],
                                "Total_Delay_ms": result['total_e2e_delay'] * 1000,
                                "Hops_Count": len(result['path']) - 1,
                                "Hops_Details": result['hops']
                            })

            self.current_time_s += tick_duration_s

        self.logger.info("Network Simulation Completed.")
        return pd.DataFrame(self.network_results)
