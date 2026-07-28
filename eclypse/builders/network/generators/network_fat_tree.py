"""Fat-Tree infrastructure generator.

This module provides a factory function to instantiate a Fat-Tree network topology
commonly used in data center environments. The topology includes core, aggregation,
and edge switches, as well as hosts connected to edge switches.

The size and structure of the topology are determined by the `k` parameter, which must
be an even number. The number of pods is equal to `k`, and the total number of hosts
is `k^3 / 4`.
"""

from collections.abc import Callable
from typing import TYPE_CHECKING

import networkx as nx

from eclypse.network import Network

if TYPE_CHECKING:
    from eclypse.graph.assets import Asset
    from eclypse.utils.types import (
        InitPolicy,
        UpdatePolicies,
    )


def get_network_fat_tree(
    k: int,
    infrastructure_id: str = "fat_tree_net",
    bandwidth_mbps: float = 1000,
    length_km: float = 2,
    host_cpu: int = 4,
    host_ram: int = 8,
    update_policies: "UpdatePolicies" = None,
    node_assets: dict[str, "Asset"] | None = None,
    link_assets: dict[str, "Asset"] | None = None,
    include_default_assets: bool = False,
    strict: bool = False,
    resource_init: "InitPolicy" = "min",
    path_algorithm: Callable[[nx.Graph, str, str], list[str]] | None = None,
    seed: int | None = None,
) -> Network:
    """Generates a Fat-Tree topology.

    Native Fat-Tree for Eclypse+NET, preserving all configuration parameters of the
    base Eclypse framework.
    """
    if k % 2 != 0:
        raise ValueError(f"k must be an even number (got {k}) for a Fat-Tree topology.")

    # Initialize your Network class by passing it ALL the parameters
    # originally required by the parent Infrastructure class
    infrastructure = Network(
        infrastructure_id=infrastructure_id,
        update_policies=update_policies,
        node_assets=node_assets,
        edge_assets=link_assets,
        include_default_assets=include_default_assets,
        resource_init=resource_init,
        path_algorithm=path_algorithm,
        seed=seed,
    )

    num_pods = k
    num_core_switches = (num_pods // 2) ** 2
    num_agg_switches_per_pod = num_pods // 2
    num_edge_switches_per_pod = num_pods // 2
    num_hosts_per_edge = num_pods // 2

    # --- Core switches ---
    for i in range(num_core_switches):
        core_id = f"core_{i}"
        infrastructure.add_router(core_id, processing_time=0.0001, strict=strict)

    # --- Pods ---
    for pod in range(num_pods):
        # Aggregation switches
        agg_switches = []
        for a in range(num_agg_switches_per_pod):
            agg_id = f"agg_{pod}_{a}"
            agg_switches.append(agg_id)
            infrastructure.add_router(agg_id, processing_time=0.0001, strict=strict)

        # Edge switches + Hosts
        for e in range(num_edge_switches_per_pod):
            edge_id = f"edge_{pod}_{e}"
            infrastructure.add_router(edge_id, processing_time=0.0001, strict=strict)

            # Edge <-> Aggregation
            for agg_id in agg_switches:
                infrastructure.add_edge(
                    edge_id,
                    agg_id,
                    bandwidth_mbps=bandwidth_mbps,
                    length_km=length_km,
                    symmetric=True,
                    strict=strict,
                )

            # Hosts under edge
            for h in range(num_hosts_per_edge):
                host_id = f"host_{pod}_{e}_{h}"
                infrastructure.add_host(
                    host_id,
                    processing_time=0.0001,
                    cpu=host_cpu,
                    ram=host_ram,
                    strict=strict,
                )
                infrastructure.add_edge(
                    host_id,
                    edge_id,
                    bandwidth_mbps=bandwidth_mbps,
                    length_km=length_km,
                    symmetric=True,
                    strict=strict,
                )

        # Aggregation <-> Core
        for i, agg_id in enumerate(agg_switches):
            for j in range(num_pods // 2):
                core_index = i * (num_pods // 2) + j
                core_id = f"core_{core_index}"
                infrastructure.add_edge(
                    agg_id,
                    core_id,
                    bandwidth_mbps=bandwidth_mbps,
                    length_km=length_km,
                    symmetric=True,
                    strict=strict,
                )

    return infrastructure
