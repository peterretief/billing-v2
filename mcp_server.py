import os

from mcp.server.fastmcp import FastMCP

# Initialize FastMCP - the easiest way to build MCP servers in Python
mcp = FastMCP("Billing-Project-Manager")

PROJECT_ROOT = "/opt/billing_v2"


@mcp.tool()
def list_billing_files(path: str = "."):
    """Lists files in the billing project to help with organization."""
    full_path = os.path.join(PROJECT_ROOT, path)
    try:
        return os.listdir(full_path)
    except Exception as e:
        return str(e)


@mcp.tool()
def read_project_file(file_path: str):
    """Reads a specific file (like a .tex or .py file) from the project."""
    full_path = os.path.join(PROJECT_ROOT, file_path)
    try:
        with open(full_path, "r") as f:
            return f.read()
    except Exception as e:
        return str(e)


@mcp.tool()
def write_project_file(file_path: str, content: str):
    """Writes or updates a file in the project. Use with caution."""
    # Safety: Ensure the path stays within the project root
    full_path = os.path.abspath(os.path.join(PROJECT_ROOT, file_path))
    if not full_path.startswith(PROJECT_ROOT):
        return "Error: Cannot write outside of project directory."

    try:
        # Create directories if they don't exist
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Successfully wrote to {file_path}"
    except Exception as e:
        return str(e)


if __name__ == "__main__":
    print("MCP Server script started.")
    try:
        print("Starting MCP server...")
        mcp.run()
    except Exception as e:
        print(f"An exception occurred: {e}")
    finally:
        print("MCP Server script finished.")
