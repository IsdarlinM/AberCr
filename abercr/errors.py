from pathlib import Path


class AbercrombieClientError(RuntimeError):
    """Error base del cliente."""


class HttpResponseError(AbercrombieClientError):
    """La capa HTTP rechazó o devolvió una respuesta inesperada."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        reference_id: str | None = None,
        diagnostic_path: Path | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.reference_id = reference_id
        self.diagnostic_path = diagnostic_path


class GraphQLError(AbercrombieClientError):
    """GraphQL devolvió errores o una estructura inválida."""
