#!/usr/bin/env python3
from pprint import pprint

from base_client import AbercrombieClient, Config


def main() -> None:
    with AbercrombieClient(Config()) as client:
        pprint(client.build_navigation_headers())
        pprint(client.build_graphql_headers())
        pprint(client.probe())

        # Headers propios capturados desde DevTools:
        # client.load_browser_headers("browser_headers.txt")

        # Ejemplo para una cuenta propia autorizada:
        # result = client.sign_in(
        #     email="usuario@example.com",
        #     password="CONTRASENA",
        # )
        # pprint(result)


if __name__ == "__main__":
    main()
