from abc import ABC, abstractmethod


class BaseService(ABC):
    """Abstract base for every supported platform (Google, Instagram, etc.)."""

    name: str = "unknown"
    login_url: str = ""

    @abstractmethod
    async def login(self, browser) -> bool:
        """Open login page and wait for the user to authenticate manually."""

    @abstractmethod
    async def login_interactive(self, browser) -> str | None:
        """Open the login page, wait for the user to sign in, and return the account
        identifier (email / username). Returns "" if logged in but the identifier
        couldn't be read, or None on timeout. Service-agnostic entry used by the CLI
        `login add` command so each platform owns its own login URL + detection."""

    @abstractmethod
    async def scan(self, browser) -> dict:
        """Discover all data categories and approximate item counts.
        Returns: {category_name: {service_name: count_or_None}}
        """

    @abstractmethod
    async def delete(self, browser, targets: list, progress_cb=None) -> dict:
        """Delete data for the given list of service names.
        Returns: {service_name: deleted_count}
        """

    @abstractmethod
    async def toggle_off(self, browser) -> dict:
        """Turn off all activity tracking toggles.
        Returns: {toggle_name: 'turned_off' | 'already_off'}
        """
