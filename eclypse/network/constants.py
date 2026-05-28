"""Constants specific to the physical network extension."""

# Default Values for Physical Links
DEFAULT_BANDWIDTH_MBPS = 100.0
"""Default link bandwidth in Mbps."""

DEFAULT_LENGTH_KM = 1.0
"""Default physical link length in kilometers."""

DEFAULT_PROPAGATION_SPEED_KM_S = 200000.0
"""Default signal propagation speed through the medium (e.g., fiber) in km/s."""

# Safety Lower Bounds
MIN_LENGTH_KM = 0.0
"""Minimum allowable physical length for a link."""

MIN_PROPAGATION_SPEED = 0.001
"""Minimum allowable propagation speed to prevent division by zero in delay calculations."""

# Mathematical Conversion Factors
MBPS_TO_BPS = 1_000_000.0
"""Multiplier to convert Megabits per second to bits per second."""

SEC_TO_MS = 1000.0
"""Multiplier to convert seconds to milliseconds."""

BYTES_TO_BITS = 8
"""Multiplier to convert packet size from Bytes to bits."""


# Default values for the application
DEFAULT_AVG_PACKETS_PER_STEP = 1.0
"""Default average rate of packet generation per time step."""

DEFAULT_PACKET_SIZE_BYTES = 1500
"""Default packet size in Bytes"""

__all__ = [
    "BYTES_TO_BITS",
    "DEFAULT_AVG_PACKETS_PER_STEP",
    "DEFAULT_BANDWIDTH_MBPS",
    "DEFAULT_LENGTH_KM",
    "DEFAULT_PACKET_SIZE_BYTES",
    "DEFAULT_PROPAGATION_SPEED_KM_S",
    "MBPS_TO_BPS",
    "MIN_LENGTH_KM",
    "MIN_PROPAGATION_SPEED",
    "SEC_TO_MS",
]
