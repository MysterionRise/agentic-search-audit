"""Exceptions raised by the audit orchestration layer."""


class QuerySubmitError(RuntimeError):
    """The search could not be submitted for a query (search box not found, submit failed).

    Retryable: the page is usually recoverable by re-navigating to the site.
    """
