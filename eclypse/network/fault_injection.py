from network import Network

from eclypse.workflow.event import once_at


@once_at(step=50, event_type="infrastructure", name="fault_injection")
def FaultInjectionEvent(infr: Network, placement_view, **kwargs):
    """
    Event that fires EXACTLY at step 50.
    Removes the link and forces an OSPF recalculation.
    """
    infr.logger.warning("\nstep 50: Gateway->R1 link broken! Routes recalculated.\n")
    # remove physically the link from the infrastructure graph. This simulates a real failure and allows us to test the OSPF reaction.
    infr.remove_edge("Gateway", "R1")
    # empty the infrastructure paths cache to force the recalculation of routes.
    infr._paths.clear()
    # recalculate the routes
    infr.install_shortest_path_routes()
