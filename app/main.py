from fastapi import FastAPI

from app.api.router import router
from app.core.lifespan import lifespan

app = FastAPI(title="Insider Detection MVP", version="0.1.0", lifespan=lifespan)
app.include_router(router)
