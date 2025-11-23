import asyncio
from src.mcp.server import audit_file, AuditInput
from src.mcp.tools.audit_file import AuditFileTool

# Mock de datos
TEST_PAYLOAD = {
    "doc_id": "69228ff3530648a264d992d2",  # ID real usado en logs
    "user_id": "bc43ac28-8880-4a8d-ad14-70aa08d10795",
    "policy_id": "auto",
}

async def test_direct_invocation():
    print("--- TEST 1: Invocación Directa a la Clase ---")
    tool = AuditFileTool()
    try:
        result = await tool.execute(
            doc_id=TEST_PAYLOAD["doc_id"],
            user_id=TEST_PAYLOAD["user_id"],
        )
        print("✅ Clase AuditFileTool: ÉXITO")
        print(result)
    except Exception as e:
        print(f"❌ Clase AuditFileTool: FALLO - {e}")

async def test_fastmcp_invocation():
    print("\n--- TEST 2: Invocación vía FastMCP Wrapper (server.py) ---")
    try:
        input_model = AuditInput(**TEST_PAYLOAD)
        result = await audit_file(input_model)
        print("✅ Función @mcp.tool: ÉXITO")
        print(result)
    except Exception as e:
        print(f"❌ Función @mcp.tool: FALLO - {e}")

if __name__ == "__main__":
    asyncio.run(test_direct_invocation())
    asyncio.run(test_fastmcp_invocation())
