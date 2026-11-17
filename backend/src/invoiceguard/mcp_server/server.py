"""MCP server exposing read-only purchasing data (MCP Python SDK 2.x).

Run over stdio:  python -m invoiceguard.mcp_server.server
"""

from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from invoiceguard.db.session import SessionLocal
from invoiceguard.mcp_server import tools

mcp = MCPServer(
    "invoiceguard-readonly",
    instructions="Read-only lookups of vendors, purchase orders, goods receipts and invoices.",
)

# Advertised to clients; the database's read-only transaction is what actually enforces it.
READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True)


@mcp.tool(annotations=READ_ONLY)
def get_vendor(vendor_id: str) -> dict[str, Any] | None:
    """Look up a vendor by its code (for example V001). Returns null if it does not exist."""
    with tools.readonly_session(SessionLocal) as session:
        return tools.get_vendor(session, vendor_id)


@mcp.tool(annotations=READ_ONLY)
def get_purchase_order(po_number: str) -> dict[str, Any] | None:
    """Look up a purchase order and its ordered lines. Returns null if it does not exist."""
    with tools.readonly_session(SessionLocal) as session:
        return tools.get_purchase_order(session, po_number)


@mcp.tool(annotations=READ_ONLY)
def get_goods_receipts(po_number: str) -> list[dict[str, Any]]:
    """List the goods receipts recorded against a purchase order, oldest first."""
    with tools.readonly_session(SessionLocal) as session:
        return tools.get_goods_receipts(session, po_number)


@mcp.tool(annotations=READ_ONLY)
def get_invoice_history(vendor_id: str, limit: int = 20) -> list[dict[str, Any]]:
    """List a vendor's most recent invoices (at most 50) with their status."""
    with tools.readonly_session(SessionLocal) as session:
        return tools.get_invoice_history(session, vendor_id, limit)


if __name__ == "__main__":
    mcp.run(transport="stdio")
