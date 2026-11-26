from pathlib import Path

import config

from util.route import load_route


def get_route():
    return load_route(Path(config.config.routeConfig))
