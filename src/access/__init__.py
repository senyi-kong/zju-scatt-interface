"""Public exports for the access domain. Implementations live in its modules."""

from importlib import import_module

_EXPORTS = {
    "ApiClient": ("zju_scatt_interface.access.client", "ApiClient"),
    "RemoteObject": ("zju_scatt_interface.access.models", "RemoteObject"),
    "RemoteDirectory": ("zju_scatt_interface.access.models", "RemoteDirectory"),
    "RetrievalResult": ("zju_scatt_interface.access.models", "RetrievalResult"),
    "DownloadResult": ("zju_scatt_interface.access.models", "DownloadResult"),
    "ScanStats": ("zju_scatt_interface.access.models", "ScanStats"),
    "WavelengthProcessing": ("zju_scatt_interface.access.models", "WavelengthProcessing"),
    "register_direct": ("zju_scatt_interface.access.registration", "register_direct"),
    "load_session_token": ("zju_scatt_interface.access.registration", "load_session_token"),
    "save_session_token": ("zju_scatt_interface.access.registration", "save_session_token"),
    "search_data": ("zju_scatt_interface.access.retrieval", "search_data"),
    "estimate_data": ("zju_scatt_interface.access.retrieval", "estimate_data"),
    "retrieve_sources": ("zju_scatt_interface.access.retrieval", "retrieve_sources"),
    "retrieve": ("zju_scatt_interface.access.workflow", "retrieve"),
    "load_retrieval_config": ("zju_scatt_interface.access.workflow", "load_retrieval_config"),
    "RetrievalRunResult": ("zju_scatt_interface.access.workflow", "RetrievalRunResult"),
    "RetrievalRunError": ("zju_scatt_interface.access.workflow", "RetrievalRunError"),
    "initialize_data_directory": ("zju_scatt_interface.access.cache", "initialize_data_directory"),
}
__all__ = list(_EXPORTS)


def __getattr__(name):
    try:
        module, symbol = _EXPORTS[name]
    except KeyError:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from None
    value = getattr(import_module(module), symbol)
    globals()[name] = value
    return value
