"""
Error simulation: makes an emulator misbehave on purpose, like a faulty ammeter would.

The faults happen inside the emulator, so the client and the framework see a real faulty device
and are tested exactly as they would be in the field.
"""

import random
from dataclasses import asdict, dataclass, fields
from typing import Optional

# The faults in the order they are drawn.
FAULT_TYPES = ('no_reply', 'invalid_reply', 'delay', 'spike')

# What the emulator sends back for an invalid_reply fault.
INVALID_REPLY = b'ERR:SIMULATED'


@dataclass
class FaultProfile:
    """
    How often each fault happens for one ammeter. Every probability is between 0 and 1.
    """

    # Close the connection without answering.
    no_reply: float = 0.0
    # Answer with text instead of a number.
    invalid_reply: float = 0.0
    # Answer only after delay_seconds, longer than the client timeout makes the request fail.
    delay: float = 0.0
    # Answer with the real value multiplied by spike_factor, a wrong reading that still looks like a number.
    spike: float = 0.0
    # How late a delayed answer comes, in seconds.
    delay_seconds: float = 3.0
    # How much a spike multiplies the value.
    spike_factor: float = 50.0

    def __post_init__(self):
        """
        Check that the profile makes sense.

        :raises ValueError: If a probability is outside 0-1, they add up to more than 1, or a setting is not positive.
        """
        for name in FAULT_TYPES:
            value = getattr(self, name)
            if not 0 <= value <= 1:
                raise ValueError(f'Fault probability {name} must be between 0 and 1, got {value}.')
        total = sum(getattr(self, name) for name in FAULT_TYPES)
        if total > 1 + 1e-9:
            raise ValueError(f'Fault probabilities add up to {total:.2f}, they can add up to 1 at most.')
        if self.delay_seconds <= 0 or self.spike_factor <= 0:
            raise ValueError('delay_seconds and spike_factor must be positive.')

    @classmethod
    def from_dict(cls, settings: dict, defaults: Optional[dict] = None) -> 'FaultProfile':
        """
        Build a profile from the config, with shared defaults for delay_seconds and spike_factor.

        :param settings: The settings of one ammeter.
        :param defaults: Settings shared by every ammeter.
        :return: The profile.
        :raises ValueError: If the config contains an unknown setting.
        """
        known = {f.name for f in fields(cls)}
        merged = {**(defaults or {}), **(settings or {})}
        unknown = set(merged) - known
        if unknown:
            raise ValueError(f'Unknown error simulation settings {sorted(unknown)}. Known settings: {sorted(known)}.')
        return cls(**merged)

    def to_dict(self) -> dict:
        """
        The profile as a dictionary, for the run metadata and the report.

        :return: The settings.
        """
        return asdict(self)


class FaultInjector:
    """
    Decides, request by request, whether the emulator misbehaves and how.
    """

    def __init__(self, profile: FaultProfile, seed: Optional[int] = None):
        """
        Prepare the injector.

        :param profile: How often each fault happens.
        :param seed: Fixed seed makes the sequence of faults repeatable, None makes it different every run.
        """
        self.profile = profile
        # An own random generator, so the faults never change the random values of the measurement itself.
        self.random = random.Random(seed)

    def choose(self) -> Optional[str]:
        """
        Draw the fault for the next request.

        :return: The name of the fault, or None for a normal answer.
        """
        draw = self.random.random()
        threshold = 0.0
        # One draw for all faults, so their probabilities add up instead of overlapping.
        for name in FAULT_TYPES:
            threshold += getattr(self.profile, name)
            if draw < threshold:
                return name
        return None


def build_injectors(simulation_config: Optional[dict], ammeter_names) -> dict[str, FaultInjector]:
    """
    Build one injector per ammeter from the error_simulation section of config.yaml.

    :param simulation_config: The error_simulation section, may be None.
    :param ammeter_names: Names of the ammeters that will run.
    :return: Injectors per ammeter name, empty when the simulation is off.
    :raises ValueError: If the section names an ammeter that is not in the config.
    """
    if not simulation_config or not simulation_config.get('enabled'):
        return {}

    profiles = simulation_config.get('ammeters') or {}
    unknown = set(profiles) - set(ammeter_names)
    if unknown:
        raise ValueError(f'Error simulation for unknown ammeters {sorted(unknown)}. Known ammeters: {sorted(ammeter_names)}.')

    defaults = {key: simulation_config[key] for key in ('delay_seconds', 'spike_factor') if key in simulation_config}
    seed = simulation_config.get('seed')
    injectors = {}
    for position, name in enumerate(ammeter_names):
        if name in profiles:
            # A different seed per ammeter, so the ammeters do not fail on the same samples.
            injectors[name] = FaultInjector(FaultProfile.from_dict(profiles[name], defaults),
                                            None if seed is None else seed + position)
    return injectors
