#!/usr/bin/env python3
import argparse, os, sys
from pathlib import Path
from tvdata_api import BuildError, build

def main() -> int:
    parser = argparse.ArgumentParser(description="Generate the TVData static API")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, default=Path("_site"))
    parser.add_argument("--source-repository", default=os.getenv("GITHUB_REPOSITORY", ""))
    parser.add_argument("--source-ref", default=os.getenv("GITHUB_SHA", ""))
    args = parser.parse_args()
    try:
        manifest = build(args.root, args.output, args.source_repository, args.source_ref)
    except BuildError as error:
        print(f"TVData API build failed: {error}", file=sys.stderr)
        return 1
    print(f"Built TVData API: {manifest['counts']}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
