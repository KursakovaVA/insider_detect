from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.rules_engine import load_rules
from app.settings import settings

@asynccontextmanager
async def lifespan(app: FastAPI):
    rules_path = getattr(settings, "RULES_PATH", None) or "rules/rules.yaml"
    app.state.ruleset = load_rules(rules_path)
    yield
