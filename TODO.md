# ECLYPSE+Net

### Next steps

- [] Extend the application model to specify the flow transmission rate in packets/ticks and packet size.

- [] Extend the infrastructure model to define router nodes, currently modeled as a single M/M/1 queue.

- [] Extend the infrastructure model to specify the bandwidth, propagation speed, and transmission rate of the links.

- [] Extend the simulator to calculate network delays along paths and total flow transmission delays.

- [] Implement a first version of a routing table that allows selecting the outgoing links for each packet, assuming (for now) that all queued packets are transferred to the next hop within one simulation tick.