from fastapi import FastAPI
from api.routes.notifications import router as notifications_router

app = FastAPI(title="PulseNotify", version="0.1.0")

app.include_router(notifications_router, prefix="/api/v1")


@app.get("/health")
async def health():
    return {"status": "ok"}