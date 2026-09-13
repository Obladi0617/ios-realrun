import yaml
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent

class Config:
    def __init__(self):
        with open(BASE_DIR / "config.yaml", 'r') as f:
            config = yaml.safe_load(f)
        for i in config:
            setattr(self, i, config[i])
        self.routeConfig = str((BASE_DIR / self.routeConfig).resolve())


config = Config()
