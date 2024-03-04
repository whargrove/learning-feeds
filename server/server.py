from fastapi import FastAPI

app = FastAPI()


@app.get("/ruok")
async def ruok():
    return "imok"

