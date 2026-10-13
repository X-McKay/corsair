"""Production entrypoint; an explicit origin is mandatory before accepting traffic."""
import os

from corsair.web.server import Application, configured_evidence

application = Application(configured_evidence(), (os.environ['CORSAIR_UI_PUBLIC_ORIGIN'],))
