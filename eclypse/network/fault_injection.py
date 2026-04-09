from eclypse.workflow.event import event


@event(event_type="infrastructure", activates_on="step")
class FaultInjectionEvent:
    """
    Event to simulate a fault in the network by removing an edge at a specific tick.
    In this example, we simulate the failure of the link between the Gateway and R1 at tick 50,
    and we trigger an emergency recalculation of routes on R2 (simulating OSPF behavior).
    """
    def __init__(self):
        self.current_tick = 0

    def __call__(self, infr, placement_view, **kwargs):
        self.current_tick += 1

        if self.current_tick == 50:
            print(f"\n[FAILURE] Tick {self.current_tick}: Gateway link broken -> R1!")
            infr.remove_edge("Gateway", "R1")
            if hasattr(infr, "_paths"):
                infr._paths.clear()

            if hasattr(infr, "install_shortest_path_routes"):
                infr.install_shortest_path_routes()
                print("[OSPF] Emergency recalculated routes on R2.\n")
