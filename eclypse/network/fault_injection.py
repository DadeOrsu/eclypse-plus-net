from network import Network

from eclypse.workflow.event import once_at

# tick 50 = 50 seconds
@once_at(sim_seconds=50, event_type="infrastructure", name="fault_injection")
def FaultInjectionEvent(infr: Network, placement_view, **kwargs):
    """
    Event that fires EXACTLY at 50 simulation seconds (Tick 50).
    Removes the link and forces an OSPF recalculation.
    """
    print("\n[💥 FAULT] Time 50s (Tick 50): Gateway->R1 link broken!")
    # remove physically the link from the infrastructure graph. This simulates a real failure and allows us to test the OSPF reaction.
    infr.remove_edge("Gateway", "R1")
    # empty the infrastructure paths cache to force the recalculation of routes.
    infr._paths.clear()
    # recalculate the routes
    infr.install_shortest_path_routes()
    print("[OSPF] Rotte ricalcolate d'emergenza su R2.\n")