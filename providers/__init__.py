from __future__ import annotations

from providers.base import ProviderDescriptor


def get_provider(slug: str):
    from providers.registry import get_provider as _get_provider

    return _get_provider(slug)


def list_provider_descriptors() -> list[ProviderDescriptor]:
    from providers.registry import list_provider_descriptors as _list_provider_descriptors

    return _list_provider_descriptors()


__all__ = [
    "get_provider",
    "list_provider_descriptors",
]
