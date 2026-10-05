"""One-click edge launcher for POLAR EMS.
Runs the FastAPI async backend, HiGHS MILP optimizer, and hosts the operator dashboard on http://127.0.0.1:8000.
"""

import sys
import os
import uvicorn

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

if __name__ == "__main__":
    print("\n" + "="*60)
    print("  POLAR EMS - EDGE MICROGRID CONTROLLER (SIH26061)")
    print("="*60)
    print("  • Station: Bharati Polar Research Station (70.9°S)")
    print("  • Mode: Offline-First Edge Supervisor (Fanless Rugged PC)")
    print("  • Optimizer: HiGHS Dual Simplex MILP (< 1s Rolling Horizon)")
    print("  • Safety Layer: Active (0 kWh Unserved Critical Energy)")
    print("  • Operator Dashboard: http://127.0.0.1:8000")
    print("  • OpenAPI Swagger Documentation: http://127.0.0.1:8000/docs")
    print("="*60 + "\n")

    uvicorn.run(
        "polar_ems.api.main:app",
        host="127.0.0.1",
        port=8000,
        reload=False,
        log_level="info"
    )
