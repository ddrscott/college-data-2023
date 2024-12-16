import json
import os
import httpx
from rich import print

UTR_HEADERS = {
    'cookie': f"jwt={os.getenv('UTR_JWT')}",
}

async def utr_api(path, **params):
    base_url = 'https://api.utrsports.net/v2'
    url = f"{base_url}/{path}"
    async with httpx.AsyncClient() as client:
        print(f"Fetching {url} with params {params}")
        response = await client.get(url=url, headers=UTR_HEADERS, params=params)
        if not response.status_code == 200:
            raise Exception(f"Failed to fetch the webpage at {url} [{response.status_code}] {response.text}")
    return response.json()

async def utr_colleges(**params):
    defaults = {
        'top': 10,
        'skip': 0,
        'utrType': 'verified',
        'utrTeamType': 'singles',
        'schoolClubSearch': 'true',
        'sort': 'school.power6:desc',
        'gender': 'M',
    }
    final_params = {**defaults, **params}
    return await utr_api('search/colleges', **final_params)
