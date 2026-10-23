# SPDX-License-Identifier: Apache-2.0
import json
import sys
from pathlib import Path

def main():
    requested = Path("allowed") / sys.argv[1]
    result = requested.read_text()
    print(json.dumps(result))

if __name__ == "__main__":
    main()
