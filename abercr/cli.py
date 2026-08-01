from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
from pathlib import Path

import requests

from .client import AbercrombieClient
from .config import Config
from .errors import AbercrombieClientError


VERSION = "0.1.0"


def _add_runtime_arguments(
    parser: argparse.ArgumentParser,
    *,
    allow_no_bootstrap: bool = True,
) -> None:
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument(
        "--diagnostics-dir",
        type=Path,
        default=Path("diagnostics"),
    )
    parser.add_argument("--quiet", action="store_true")
    if allow_no_bootstrap:
        parser.add_argument(
            "--no-bootstrap",
            action="store_true",
            help="Omite el GET inicial solo para comparar comportamiento.",
        )


def _add_account_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--email", required=True)
    parser.add_argument(
        "--password",
        help="Usa ABERCR_PASSWORD o entrada oculta cuando se omite.",
    )
    parser.add_argument("--keep-signed-in", action="store_true")
    _add_runtime_arguments(parser)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="AberCr: cliente base para pruebas autorizadas.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {VERSION}",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    probe = subparsers.add_parser(
        "probe",
        help="Comprueba la navegación inicial sin autenticar.",
    )
    _add_runtime_arguments(probe, allow_no_bootstrap=False)

    signin = subparsers.add_parser("signin", help="Iniciar sesión.")
    _add_account_arguments(signin)
    signin.add_argument("--no-merge-bag", action="store_true")
    signin.add_argument("--accept-loyalty-terms", action="store_true")
    signin.add_argument("--fast-enroll-campaign-id")

    create = subparsers.add_parser("create-user", help="Crear un usuario.")
    _add_account_arguments(create)
    create.add_argument("--first-name", required=True)
    create.add_argument("--last-name", required=True)
    create.add_argument("--phone")
    create.add_argument("--accept-legal", action="store_true")
    create.add_argument("--marketing-opt-in", action="store_true")
    create.add_argument(
        "--age-above-or-below",
        action=argparse.BooleanOptionalAction,
    )
    create.add_argument("--gender")
    create.add_argument("--birth-month", type=int)
    create.add_argument("--birth-day", type=int)
    create.add_argument("--birth-year", type=int)
    create.add_argument("--referral-code")
    create.add_argument("--fast-enroll-campaign-id")
    return parser


def _read_password(args: argparse.Namespace) -> str:
    password = getattr(args, "password", None) or os.getenv("ABERCR_PASSWORD")
    return password or getpass.getpass("Contraseña: ")


def main() -> int:
    args = build_parser().parse_args()
    config = Config(
        timeout=args.timeout,
        diagnostics_dir=args.diagnostics_dir,
        bootstrap_enabled=not getattr(args, "no_bootstrap", False),
        verbose=not args.quiet,
    )
    try:
        with AbercrombieClient(config) as client:
            if args.command == "probe":
                result = client.probe()
            elif args.command == "signin":
                result = client.sign_in(
                    email=args.email,
                    password=_read_password(args),
                    keep_me_signed_in=args.keep_signed_in,
                    merge_bag=not args.no_merge_bag,
                    accept_loyalty_terms=(
                        True if args.accept_loyalty_terms else None
                    ),
                    fast_enroll_campaign_id=args.fast_enroll_campaign_id,
                )
            else:
                result = client.create_user(
                    email=args.email,
                    password=_read_password(args),
                    first_name=args.first_name,
                    last_name=args.last_name,
                    primary_phone=args.phone,
                    keep_me_signed_in=args.keep_signed_in,
                    marketing_opt_in=args.marketing_opt_in,
                    legal_accept=args.accept_legal,
                    age_above_or_below=args.age_above_or_below,
                    gender=args.gender,
                    birth_month=args.birth_month,
                    birth_day=args.birth_day,
                    birth_year=args.birth_year,
                    referral_code=args.referral_code,
                    fast_enroll_campaign_id=args.fast_enroll_campaign_id,
                )
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0
    except (requests.RequestException, AbercrombieClientError, ValueError) as exc:
        print(f"[!] {exc}", file=sys.stderr)
        return 1
