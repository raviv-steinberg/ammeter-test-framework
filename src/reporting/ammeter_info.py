"""
Display details and theoretical values of every known ammeter, used by the HTML report.
"""

import math

# Colors for ammeters that are not listed below, picked in order.
FALLBACK_COLORS = ['#ec4899', '#0ea5e9', '#84cc16', '#f97316', '#14b8a6']

# Details of every known ammeter. The ranges and expected means follow from the input ranges in README.md.
AMMETER_INFO = {
    'greenlee': {
        'label': 'Greenlee',
        'color': '#f59e0b',
        'method': "Ohm's law",
        'formula': 'I = V / R',
        # I = V / R, V in 1-10 V, R in 0.1-100 ohm.
        'range': [1 / 100, 10 / 0.1],
        # Mean of V times the mean of 1/R for a uniform R in 0.1-100: 5.5 * ln(100 / 0.1) / 99.9.
        'expected_mean': 5.5 * math.log(100 / 0.1) / 99.9,
    },
    'entes': {
        'label': 'ENTES',
        'color': '#6366f1',
        'method': 'Hall effect',
        'formula': 'I = B × K',
        # I = B * K, B in 0.01-0.1 T, K in 500-2000.
        'range': [0.01 * 500, 0.1 * 2000],
        'expected_mean': 0.055 * 1250,
    },
    'circutor': {
        'label': 'CIRCUTOR',
        'color': '#10b981',
        'method': 'Rogowski coil',
        'formula': 'I = Σ V·dt',
        # I = sum(V * dt), 10 samples, V in 0.1-1.0 V, dt in 0.001-0.01 s.
        'range': [10 * 0.1 * 0.001, 10 * 1.0 * 0.01],
        'expected_mean': 10 * 0.55 * 0.0055,
    },
}


def get_ammeter_info(name: str, position: int = 0) -> dict:
    """
    Return the display details of an ammeter, with sensible defaults for an unknown one.

    :param name: Ammeter name as it appears in config.yaml.
    :param position: Position of the ammeter in the report, used to pick a fallback color.
    :return: Label, color, method, formula, range and expected mean.
    """
    if name in AMMETER_INFO:
        return dict(AMMETER_INFO[name])

    # An ammeter added to the config later still gets a readable entry in the report.
    return {
        'label': name.title(),
        'color': FALLBACK_COLORS[position % len(FALLBACK_COLORS)],
        'method': 'unknown',
        'formula': '–',
        'range': None,
        'expected_mean': None,
    }
