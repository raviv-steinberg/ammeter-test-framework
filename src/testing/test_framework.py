"""
Unified testing framework that runs a sampling test on any configured ammeter.
"""

import logging
import platform
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional
from Ammeters.client import AmmeterClient
from Ammeters.fault_injection import FaultProfile
from src.testing.analysis import MeasurementStatistics, analyze_samples
from src.testing.sampler import Sample, Sampler
from src.utils.config import load_config

# Project root is two folders above this file: src/testing/test_framework.py.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / 'config' / 'config.yaml'

logger = logging.getLogger(__name__)

# Seconds the client waits for an ammeter when config.yaml sets no timeout.
DEFAULT_TIMEOUT_SECONDS = 5.0


def generate_run_id() -> str:
    """
    Create a unique id for a test run.

    :return: Id in the form YYYYMMDD_HHMMSS_xxxxxxxx.
    """
    # Timestamp first so ids sort by time, 8 random hex characters (32 bits) so runs in the same second do not clash.
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    return f'{timestamp}_{uuid.uuid4().hex[:8]}'


@dataclass
class AmmeterTestResult:
    """
    Everything known about one test run of one ammeter.
    """

    # Unique id of this run.
    run_id: str
    # Ammeter name as it appears in config.yaml.
    ammeter_type: str
    # Local start time of the test in ISO format.
    started_at: str
    # How long the whole test took in seconds.
    duration_seconds: float
    # Planned number of samples.
    measurements_count: int
    # Planned time between two samples in seconds.
    interval_seconds: float
    # Details about how the test was run: connection, sampling config and environment.
    metadata: dict
    # Every sample taken, including failed ones.
    samples: list[Sample]
    # Summary statistics of the successful samples.
    statistics: MeasurementStatistics

    def to_dict(self) -> dict:
        """
        Convert the result to plain dictionaries and lists so it can be saved as JSON.

        :return: The result as a dictionary.
        """
        # asdict also converts the nested Sample and MeasurementStatistics objects.
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> 'AmmeterTestResult':
        """
        Rebuild a result from a dictionary created by to_dict.
        :param data: Dictionary loaded from a saved result.
        :return: The rebuilt result.
        """
        # Copy so the caller's dictionary is not changed.
        data = dict(data)
        # Nested objects come back as dictionaries, so turn them into objects again.
        data['samples'] = [Sample(**sample) for sample in data['samples']]
        data['statistics'] = MeasurementStatistics(**data['statistics'])
        return cls(**data)

    def format_summary(self) -> str:
        """
        Build a readable summary of the result in the same format for every ammeter.
        :return: Multi-line text summary.
        """
        stats = self.statistics
        lines = [
            f'--- {self.ammeter_type} ---',
            f'run id:   {self.run_id}',
            f'started:  {self.started_at}  duration: {self.duration_seconds:.2f} s',
            f'samples:  {stats.count}  failed: {stats.failed_count}',
        ]

        # Without successful samples there are no numbers to show.
        if stats.count == 0:
            lines.append('All measurements failed.')
            return '\n'.join(lines)

        lines += [
            f'mean:     {stats.mean:.4f} A',
            f'median:   {stats.median:.4f} A',
            f'std:      {stats.std:.4f} A',
            f'min:      {stats.min_value:.4f} A',
            f'max:      {stats.max_value:.4f} A',
            f'cv:       {stats.cv_percent:.1f} %',
        ]
        return '\n'.join(lines)


class AmmeterTestFramework:
    """
    Runs the same sampling test on any ammeter defined in the config file.
    """

    def __init__(self, config_path: str | Path = DEFAULT_CONFIG_PATH):
        """
        Load the config and prepare the sampler.
        :param config_path: Path to config.yaml.
        """
        self.config = load_config(str(config_path))
        self.ammeters = self.config['ammeters']
        # One sampling plan is shared by all ammeters so the results are comparable.
        self.sampler = Sampler.from_config(self.config['testing']['sampling'])
        self.timeout = self.config['testing'].get('timeout_seconds') or DEFAULT_TIMEOUT_SECONDS

    def run_test(self, ammeter_type: str) -> AmmeterTestResult:
        """
        Sample one ammeter and analyze the results.
        :param ammeter_type: Ammeter name as it appears in config.yaml.
        :return: The full result of the test.
        :raises ValueError: If the ammeter is not defined in the config.
        """
        if ammeter_type not in self.ammeters:
            raise ValueError(f'Unknown ammeter {ammeter_type!r}. Available: {list(self.ammeters)}.')

        settings = self.ammeters[ammeter_type]
        # The config stores the command as text, but the server expects bytes.
        client = AmmeterClient(settings['port'], settings['command'].encode('utf-8'), timeout=self.timeout)

        # Everything needed to understand or repeat this run later.
        metadata = {
            'host': client.host,
            'port': settings['port'],
            'command': settings['command'],
            'sampling_config': dict(self.config['testing']['sampling']),
            'timeout_seconds': self.timeout,
            'error_simulation': self.simulated_faults(ammeter_type),
            'python_version': platform.python_version(),
            'platform': platform.platform(),
        }

        run_id = generate_run_id()
        logger.info('Testing %s (run %s): %d samples every %.3f s', ammeter_type, run_id,
                    self.sampler.measurements_count, self.sampler.interval_seconds)

        started_at = datetime.now().isoformat(timespec='seconds')
        start = time.perf_counter()
        samples = self.sampler.run(client)
        duration = time.perf_counter() - start
        statistics = analyze_samples(samples)

        logger.info('Finished %s in %.2f s, %d failed', ammeter_type, duration, statistics.failed_count)

        return AmmeterTestResult(
            run_id=run_id,
            ammeter_type=ammeter_type,
            started_at=started_at,
            duration_seconds=duration,
            measurements_count=self.sampler.measurements_count,
            interval_seconds=self.sampler.interval_seconds,
            metadata=metadata,
            samples=samples,
            statistics=statistics,
        )

    def simulated_faults(self, ammeter_type: str) -> Optional[dict]:
        """
        The error simulation settings of one ammeter, saved with the run so a reader knows the failures were on purpose.

        :param ammeter_type: Ammeter name as it appears in config.yaml.
        :return: The fault profile, or None when this ammeter is not simulating errors.
        """
        simulation = self.config.get('error_simulation') or {}
        profiles = simulation.get('ammeters') or {}
        if not simulation.get('enabled') or ammeter_type not in profiles:
            return None
        defaults = {key: simulation[key] for key in ('delay_seconds', 'spike_factor') if key in simulation}
        return FaultProfile.from_dict(profiles[ammeter_type], defaults).to_dict()

    def run_all(self) -> dict[str, AmmeterTestResult]:
        """
        Run the test on every ammeter in the config.
        :return: Results keyed by ammeter name.
        """
        return {ammeter_type: self.run_test(ammeter_type) for ammeter_type in self.ammeters}