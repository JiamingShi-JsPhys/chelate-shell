"""multi-dim-manager: state management for multi-dimensional experiments.

The package only *orchestrates* an experiment loop. It never performs the
domain computation itself; a user-supplied plugin (any shell command that
reads a JSON parameter file and writes a JSON result file) does the math.
"""

__version__ = "1.2.0"
