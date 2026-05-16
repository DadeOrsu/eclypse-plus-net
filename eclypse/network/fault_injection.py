from network import Network
from eclypse.workflow.event import once_at


@once_at(step=50, event_type="infrastructure", name="fault_injection")
def FaultInjectionEvent(infr: Network, placement_view, **kwargs):
    """Event that fires EXACTLY at step 50.

    Removes the link and forces an OSPF recalculation.
    """
    infr.logger.warning("step 50: Gateway->R1 link broken! Routes recalculated.\n")
    infr.remove_edge("Gateway", "R1")
