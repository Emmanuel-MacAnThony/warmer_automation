"""
Field mapping CRUD endpoints.
"""
import logging
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/mappings", tags=["mappings"])


class SaveMappingRequest(BaseModel):
    base_id: str
    table_id: str
    name: str
    mappings: dict[str, Any]


@router.post("")
async def save_mapping(request: SaveMappingRequest):
    from backend.infra.db.mapping_repo import save_field_mapping
    try:
        mapping_id = await save_field_mapping(
            request.base_id, request.table_id, request.name, request.mappings
        )
        return {"success": True, "id": mapping_id}
    except Exception as e:
        logger.error(f"Failed to save mapping: {e}")
        return JSONResponse(status_code=500, content={"error": "Internal server error"})


@router.get("")
async def list_mappings(base_id: str, table_id: str):
    from backend.infra.db.mapping_repo import get_field_mappings
    try:
        results = await get_field_mappings(base_id, table_id)
        return {"mappings": results}
    except Exception as e:
        logger.error(f"Failed to list mappings: {e}")
        return JSONResponse(status_code=500, content={"error": "Internal server error"})


@router.get("/{mapping_id}")
async def get_mapping(mapping_id: int):
    from backend.infra.db.mapping_repo import get_field_mapping_by_id
    try:
        result = await get_field_mapping_by_id(mapping_id)
        if result is None:
            return JSONResponse(status_code=404, content={"error": "Mapping not found"})
        return result
    except Exception as e:
        logger.error(f"Failed to get mapping {mapping_id}: {e}")
        return JSONResponse(status_code=500, content={"error": "Internal server error"})


@router.put("/{mapping_id}")
async def update_mapping(mapping_id: int, request: SaveMappingRequest):
    from backend.infra.db.mapping_repo import update_field_mapping
    try:
        updated = await update_field_mapping(mapping_id, request.name, request.mappings)
        if not updated:
            return JSONResponse(status_code=404, content={"error": "Mapping not found"})
        return {"success": True, "id": mapping_id}
    except Exception as e:
        logger.error(f"Failed to update mapping {mapping_id}: {e}")
        return JSONResponse(status_code=500, content={"error": "Internal server error"})


@router.delete("/{mapping_id}")
async def delete_mapping(mapping_id: int):
    from backend.infra.db.mapping_repo import delete_field_mapping
    try:
        deleted = await delete_field_mapping(mapping_id)
        if not deleted:
            return JSONResponse(status_code=404, content={"error": "Mapping not found"})
        return {"success": True}
    except Exception as e:
        logger.error(f"Failed to delete mapping {mapping_id}: {e}")
        return JSONResponse(status_code=500, content={"error": "Internal server error"})
