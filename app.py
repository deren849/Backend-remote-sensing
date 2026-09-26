import os
from datetime import datetime
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import httpx

load_dotenv()

def get_real_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return get_remote_address(request)

limiter = Limiter(key_func=get_real_client_ip)

app = FastAPI(title="NASA Worldview Backend API")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

raw_origin = os.getenv("ALLOWED_ORIGIN", "http://localhost:5173")
origins = [origin.strip() for origin in raw_origin.split(",") if origin.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def home():
    return {"status": "NASA Worldview Python Backend Running"}

@app.get("/api/check-date/{date_str}")
@limiter.limit("60/minute")
async def check_nasa_data(request: Request, date_str: str):
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Format tanggal tidak valid. Gunakan format YYYY-MM-DD yang benar."
        )

    nasa_url = f"https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/MODIS_Terra_CorrectedReflectance_TrueColor/default/{date_str}/GoogleMapsCompatible_Level9/0/0/0.jpg"

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.head(nasa_url)
            if response.status_code == 200:
                return {"status": "available", "date": date_str}
            return {"status": "not_available", "date": date_str}
        except httpx.RequestError:
            raise HTTPException(
                status_code=500,
                detail="Gagal menghubungi server NASA GIBS."
            )

@app.get("/api/neows")
@limiter.limit("30/minute")
async def get_neows_data(request: Request, start_date: str, end_date: str):
    try:
        d_start = datetime.strptime(start_date, "%Y-%m-%d")
        d_end = datetime.strptime(end_date, "%Y-%m-%d")

        if d_end < d_start:
            raise HTTPException(
                status_code=400,
                detail="end_date tidak boleh lebih awal dari start_date."
            )
        if (d_end - d_start).days > 7:
            raise HTTPException(
                status_code=400, 
                detail="Rentang waktu maksimal untuk API NeoWs adalah 7 hari."
            )
    except ValueError:
        raise HTTPException(
            status_code=400, 
            detail="Format tanggal tidak valid. Gunakan format YYYY-MM-DD."
        )

    api_key = os.getenv("NASA_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=500,
            detail="NASA_API_KEY belum dikonfigurasi pada server backend."
        )

    url = f"https://api.nasa.gov/neo/rest/v1/feed?start_date={start_date}&end_date={end_date}&api_key={api_key}"

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.get(url)
            if response.status_code != 200:
                raise HTTPException(
                    status_code=response.status_code, 
                    detail="Gagal mengambil data NeoWs dari NASA."
                )    
            return response.json()
        except httpx.RequestError:
            raise HTTPException(
                status_code=500, 
                detail="Gagal menghubungi server NASA NeoWs."
            )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)