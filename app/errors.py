class Conflito(Exception):
    """HTTP 409 - ex.: 'outra pessoa alterou a licitação' (F5 e refaça)."""


class NaoEncontrado(Exception):
    """HTTP 404."""


class LimiteTentativas(Exception):
    """HTTP 429 - reenvio de e-mail antes de 1 minuto."""
