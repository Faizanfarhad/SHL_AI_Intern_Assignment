from fastapi import FastAPI

from app.api.routes import router


app = FastAPI(title="SHL Conversational Assessment Recommender")
app.include_router(router)

