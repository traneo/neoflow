import weaviate
from weaviate.config import AdditionalConfig, Timeout

from neoflow.config import Config


def create_weaviate_client(
    config: Config,
    timeout_init: int | None = None,
    timeout_query: int | None = None,
    timeout_insert: int | None = None,
):
    """Create a Weaviate client that always honors configured connection settings."""
    wv = config.weaviate
    additional_config = AdditionalConfig(
        timeout=Timeout(
            init=timeout_init if timeout_init is not None else wv.timeout_init,
            query=timeout_query if timeout_query is not None else wv.timeout_query,
            insert=timeout_insert if timeout_insert is not None else wv.timeout_insert,
        )
    )

    grpc_host = wv.grpc_host or wv.host

    return weaviate.connect_to_custom(
        http_host=wv.host,
        http_port=wv.port,
        http_secure=wv.http_secure,
        grpc_host=grpc_host,
        grpc_port=wv.grpc_port,
        grpc_secure=wv.grpc_secure,
        additional_config=additional_config,
    )
