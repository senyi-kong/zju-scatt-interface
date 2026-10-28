"""CRTM application exports. Infrared optical table implementations live in ir."""

from .ir import validate_crtm_ir_optical_table, write_crtm_ir_bulk_tables

__all__ = ["validate_crtm_ir_optical_table", "write_crtm_ir_bulk_tables"]
