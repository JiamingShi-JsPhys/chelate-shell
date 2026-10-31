"""ai-trace-remover -- pure-stdlib de-AI-flavour detection & rewriting engine.

Detects and scores traces of AI-generated writing in Chinese and English prose.
The model is never asked to "write around" the tells; every check is a
deterministic scan that the agent reports. No third-party dependency.
"""

__version__ = "1.2.0"
