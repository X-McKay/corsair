"""Human-mode renderers behind ``Terminal``, one module per view family.

``Terminal`` in :mod:`corsair.entrypoints.terminal` chooses the output mode and dispatches
each value here; JSON and Markdown never pass through these modules. ``common`` holds the
shared cell, label, digest and duration primitives; ``result``, ``reports``, ``runs``,
``checks``, ``preview`` and ``progress`` each render one family of views, and ``remedies``
chooses the fixed next step printed beside a failed command.
"""
