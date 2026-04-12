from __future__ import annotations

from providers.apple_health import AppleHealthProvider
from providers.base import ProviderBase, ProviderDescriptor, ProviderSlug
from providers.garmin import GarminProvider
from providers.oura import OuraProvider
from providers.whoop import WhoopProvider


PROVIDER_REGISTRY: dict[ProviderSlug, ProviderBase] = {
    "garmin": GarminProvider(),
    "oura": OuraProvider(),
    "whoop": WhoopProvider(),
    "apple_health": AppleHealthProvider(),
}


def get_provider(slug: ProviderSlug | str) -> ProviderBase:
    provider = PROVIDER_REGISTRY.get(slug)  # type: ignore[arg-type]
    if provider is None:
        raise KeyError(f"Unsupported provider: {slug}")
    return provider


def list_provider_descriptors() -> list[ProviderDescriptor]:
    return [provider.descriptor for provider in PROVIDER_REGISTRY.values()]
