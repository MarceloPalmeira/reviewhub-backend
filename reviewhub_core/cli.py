import argparse
import json
from pathlib import Path

import yaml
from pydantic import ValidationError

from reviewhub_core.features import Product


def main():
    parser = argparse.ArgumentParser(description="Valida e deriva produtos ReviewHub")
    parser.add_argument("command", choices=["validate", "derive"])
    parser.add_argument("config", type=Path)
    parser.add_argument("--output", type=Path, default=Path("generated/product.json"))
    args = parser.parse_args()
    try:
        product = Product.model_validate(
            yaml.safe_load(args.config.read_text(encoding="utf-8"))
        )
    except (OSError, yaml.YAMLError, ValidationError, ValueError) as exc:
        parser.exit(1, f"Configuração inválida: {exc}\n")
    if args.command == "derive":
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(product.model_dump(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"Produto gerado: {args.output}")
    else:
        print(f"Configuração válida: {product.name}")


if __name__ == "__main__":
    main()
