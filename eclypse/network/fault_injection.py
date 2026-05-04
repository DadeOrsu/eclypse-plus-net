from eclypse.workflow.event import EclypseEvent
from eclypse.workflow.trigger import CascadeTrigger


class FaultInjectionEvent(EclypseEvent):
    def __init__(self):
        super().__init__(
            name="fault_injection",
            event_type="infrastructure",
            triggers=[CascadeTrigger("step")]
        )
        self.current_tick = 0

    def __call__(self, infr, placement_view, **kwargs):
        self.current_tick += 1

        if self.current_tick == 50:
            print(f"\n[💥 GUASTO] Tick {self.current_tick}: Rottura del link Gateway -> R1!")
            infr.remove_edge("Gateway", "R1")
            
            if hasattr(infr, "_paths"):
                infr._paths.clear()

            if hasattr(infr, "install_shortest_path_routes"):
                infr.install_shortest_path_routes()
                print("[OSPF] Rotte ricalcolate d'emergenza su R2.\n")
