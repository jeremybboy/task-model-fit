#!/usr/bin/env python3
"""Launch Task Model Fit's local slide experiment without installation."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from task_model_fit.app import main

if __name__ == "__main__":
    main()
